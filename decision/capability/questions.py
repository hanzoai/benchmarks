"""Questions per state: one state, N typed questions per call, N = 1, 10, 50, 100, 500, 1000.

The workload is bench speed's (hanzoai/decision bench/src/speed.rs), rebuilt here so all three
backends make the same calls: the states are the harness's typed-decision states in turn, and a
call's N questions are the harness's distinct question definitions in harness order, continuing
from where the previous call stopped and wrapping (ids renamed q0.. so a JSON object holds them).
At each N the first call is discarded and the next ROUNDS are timed, one call at a time;
percentiles are nearest-rank. Throughput is questions per second of timed wall time.

    laya  the harness engine (bench_local.score_cases): every question its own sequence carrying
          the whole state, batched up to 8,192 tokens a forward pass (Agent.system_one puts all N
          in one pass, which at N = 1,000 does not fit this machine's memory). On the
          typed-decisions checkpoint (mmBERT-base, 1,024), which Laya ships for these states, and
          on the English one (ModernBERT-large, 512) as large.
    jev   one Decisions API call; a call Jev refuses is recorded, then the N questions go in
          chunks of the most it took, 8 in flight, timed together as one call.
    kai   bench speed on the same sizes and rounds.

    python questions.py [--who laya,jev,kai] [--kai CHECKPOINT]
"""
import argparse
import concurrent.futures as cf
import json
import os
import resource
import time

import cap

SIZES = [1, 10, 50, 100, 500, 1000]
ROUNDS = 10


def pool():
    S = cap.load(os.path.join(cap.HERE, "..", "results", "states.json.gz"))
    states = [r[0] for r in S["typed_decisions"]]
    seen, qs = set(), []
    for rows in S.values():
        for r in rows:
            for d in r[1].values():
                k = json.dumps(d)  # key order as in the file, as serde_json::to_string
                if k not in seen:
                    seen.add(k)
                    qs.append(d)
    return states, qs


def calls(states, qs, sizes, rounds):
    """[(n, [(state, {qid: def}), ...rounds + 1])], bench speed's sequence of calls."""
    s = q = 0
    out = []
    for n in sizes:
        cs = []
        for _ in range(rounds + 1):
            cs.append((states[s % len(states)], {"q%d" % i: qs[(q + i) % len(qs)] for i in range(n)}))
            s, q = s + 1, q + n
        out.append((n, cs))
    return out


def summary(n, ms, extra=None):
    total = sum(ms)
    return dict({"questions": n, "rounds": len(ms), "p50_ms": round(cap.pct(ms, 50), 2),
                 "p95_ms": round(cap.pct(ms, 95), 2), "mean_ms": round(total / len(ms), 2),
                 "questions_per_s": round(n * len(ms) / (total / 1e3), 2)}, **(extra or {}))


def peak_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1)  # bytes on macOS


def laya(L, plan, model):
    out = []
    for n, cs in plan:
        ms, drop = [], 0
        ag = L.agent(model)
        for i, (st, qs) in enumerate(cs):
            t = time.perf_counter()
            _, _, _, d = L.bl.score_cases(ag, [(st, qs)])
            t = 1e3 * (time.perf_counter() - t)
            if i:
                ms.append(t)
                drop += d
        s = summary(n, ms, {"device": str(ag.device), "peak_rss_mb": peak_mb(), "dropped": drop})
        out.append(s)
        print("laya %s %4d  %s" % (model, n, s), flush=True)
    return out


def jev(J, plan):
    out, most = [], None
    for n, cs in plan:
        ms, cost, tin, refused, errs = [], 0.0, 0, 0, []
        for i, (st, qs) in enumerate(cs):
            t = time.perf_counter()
            d, _, err = J.call(st, qs, "questions")
            if err:
                refused += 1
                errs.append(err[:200])
                most = most or probe(J, st, qs)
                ids = list(qs)
                chunks = [{k: qs[k] for k in ids[j:j + most]} for j in range(0, n, most)]
                t = time.perf_counter()
                with cf.ThreadPoolExecutor(8) as ex:
                    rs = list(ex.map(lambda c: J.call(st, c, "questions"), chunks))
                if any(r[2] for r in rs):
                    errs.extend(r[2][:200] for r in rs if r[2])
                    continue
                ds = [r[0] for r in rs]
            else:
                ds = [d]
            dt = 1e3 * (time.perf_counter() - t)
            if i:
                ms.append(dt)
                cost += sum(float((x.get("usage") or {}).get("cost") or 0) for x in ds)
                tin += sum(int((x.get("usage") or {}).get("input_tokens") or 0) for x in ds)
        s = summary(n, ms, {"usd_per_call": round(cost / max(1, len(ms)), 6), "input_tokens_per_call":
                            tin // max(1, len(ms)), "refused_whole": refused, "chunk": most if refused else None,
                            "errors": errs[:5], "n_errors": len(errs)}) if ms else {"questions": n, "errors": errs[:5]}
        out.append(s)
        print("jev %4d  %s" % (n, s), flush=True)
    return out


def probe(J, st, qs):
    """The most questions one call takes, by halving from the refused size; each probe is a real
    call, ledgered like any other."""
    ids, n = list(qs), len(qs)
    while n > 1:
        n //= 2
        d, _, err = J.call(st, {k: qs[k] for k in ids[:n]}, "questions.probe")
        if not err:
            return n
    return 1


def kai(K, sizes, rounds):
    out = os.path.join(cap.SCRATCH, "questions.kai.json")
    K.run("speed", "--model", K.model, "--states", os.path.join(cap.HERE, "..", "results", "states.json.gz"),
          "--sizes", ",".join(map(str, sizes)), "--rounds", str(rounds), "--out", out)
    d = cap.load(out)
    return d.get("sizes", d)


def main(who, kai_model, sizes, rounds):
    states, qs = pool()
    plan = calls(states, qs, sizes, rounds)
    B = cap.backends(who, kai_model)
    keys, detail, pending = cap.Keys("questions"), {}, {}
    for w, b in B.items():
        if w == "laya":
            runs = {"": laya(b, plan, "typed-decisions"), "large.": laya(b, plan, "english")}
        elif w == "jev":
            runs = {"": jev(b, plan)}
        else:
            try:
                runs = {"": kai(b, sizes, rounds)}
            except cap.Pending as e:
                pending[w] = str(e)
                continue
        for v, rs in runs.items():
            detail["%s%s" % (v, w)] = rs
            for s in rs:
                c = "n%d.%s" % (s["questions"], v)
                for f in ("p50_ms", "p95_ms", "questions_per_s", "usd_per_call", "refused_whole", "n_errors",
                          "dropped", "peak_mb"):
                    if s.get(f) is not None:
                        keys.put(w, c + f.replace("_", "").replace("questionsper", "qper"), s[f])
    meta = {w: b.meta for w, b in B.items()}
    meta.update(pending=pending, pool={"states": len(states), "questions": len(qs)}, rounds=rounds)
    return cap.save("questions", keys, detail, meta)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    a.add_argument("--sizes", default=",".join(map(str, SIZES)))
    a.add_argument("--rounds", type=int, default=ROUNDS)
    x = a.parse_args()
    main(x.who.split(","), x.kai, [int(n) for n in x.sizes.split(",")], x.rounds)
