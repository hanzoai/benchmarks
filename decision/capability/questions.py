"""Questions per state: one state, N typed questions per call, N = 1, 10, 50, 100, 500, 1000.

The workload is bench speed's (hanzoai/decision bench/src/speed.rs), rebuilt here so all three
backends make the same calls: the states are the harness's typed-decision states in turn, and a
call's N questions are the harness's 130 distinct question definitions, shuffled once with seed 13
(train::rng::Rng, as speed.rs since 049b135), continuing from where the previous call stopped and
wrapping (ids renamed q0.. so a JSON object holds them). Laya's kept run (ra, 2026-09-25, MPS)
drew them unshuffled, in harness order: the same questions, in other calls below N = 130.
At each N the first call is discarded and the next ROUNDS are timed, one call at a time;
percentiles are nearest-rank. Throughput is questions per second of timed wall time.

    laya  the harness engine (bench_local.score_cases): every question its own sequence carrying
          the whole state, batched up to 8,192 tokens a forward pass (Agent.system_one puts all N
          in one pass, which at N = 1,000 does not fit this machine's memory). On the
          typed-decisions checkpoint (mmBERT-base, 1,024), which Laya ships for these states, and
          on the English one (ModernBERT-large, 512) as large.
    jev   one Decisions API call. Jev refuses a call over its 32,000-token context
          (max_tokens_exceeded); such a call is recorded (refusedwhole) and its N questions go
          again in chunks planned under 28,000 tokens, any chunk still refused split in two
          (splits), 8 in flight, timed together from the first chunk as one call. A round with a
          question left unanswered is an error (nerrors) and is not timed.
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


class Rng:
    """train::rng::Rng (hanzoai/decision): SplitMix64, and its unbiased below and shuffle."""
    M = (1 << 64) - 1

    def __init__(self, seed):
        self.s = seed

    def next(self):
        self.s = (self.s + 0x9E3779B97F4A7C15) & self.M
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & self.M
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & self.M
        return z ^ (z >> 31)

    def below(self, n):
        zone = self.M - self.M % n
        while True:
            v = self.next()
            if v < zone:
                return v % n

    def shuffle(self, xs):
        for i in range(len(xs) - 1, 0, -1):
            j = self.below(i + 1)
            xs[i], xs[j] = xs[j], xs[i]


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
    Rng(13).shuffle(qs)  # as bench speed's pool (049b135)
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


BUDGET = 28000  # tokens a chunk is planned to hold; Jev's context is 32,000


def split(qs):
    """Questions in consecutive chunks of at most BUDGET estimated tokens (4 bytes a token)."""
    out, cur, size = [], {}, 0
    for k, v in qs.items():
        n = len(json.dumps(v)) // 4
        if cur and size + n > BUDGET:
            out.append(cur)
            cur, size = {}, 0
        cur[k], size = v, size + n
    return out + [cur] if cur else out


def ask(J, st, qs):
    """(responses, errors, splits): one call, and a chunk Jev refuses as over its token limit
    split in two and asked again, as a client that honours the limit does."""
    d, _, err = J.call(st, qs, "questions")
    if not err:
        return [d], [], 0
    if "max_tokens_exceeded" not in err or len(qs) == 1:
        return [], [err[:200]], 0
    ids = list(qs)
    halves = [{k: qs[k] for k in ids[:len(ids) // 2]}, {k: qs[k] for k in ids[len(ids) // 2:]}]
    out = [ask(J, st, h) for h in halves]
    return [x for o in out for x in o[0]], [x for o in out for x in o[1]], 1 + sum(o[2] for o in out)


def jev(J, plan):
    out = []
    for n, cs in plan:
        ms, cost, tin, refused, errs, splits, chunks = [], 0.0, 0, 0, [], 0, 0
        for i, (st, qs) in enumerate(cs):
            t = time.perf_counter()
            d, _, err = J.call(st, qs, "questions")
            if err:  # refused whole: the questions go again in planned chunks, 8 in flight
                refused += 1
                parts = split(qs)
                t = time.perf_counter()
                with cf.ThreadPoolExecutor(8) as ex:
                    rs = list(ex.map(lambda c: ask(J, st, c), parts))
                ds = [x for r in rs for x in r[0]]
                bad = [x for r in rs for x in r[1]]
                splits += sum(r[2] for r in rs)
                chunks += len(ds)
                if bad:
                    errs.extend(bad)
                    continue
            else:
                ds = [d]
            dt = 1e3 * (time.perf_counter() - t)
            if i:
                ms.append(dt)
                cost += sum(float((x.get("usage") or {}).get("cost") or 0) for x in ds)
                tin += sum(int((x.get("usage") or {}).get("input_tokens") or 0) for x in ds)
        s = summary(n, ms, {"usd_per_call": round(cost / max(1, len(ms)), 6), "input_tokens_per_call":
                            tin // max(1, len(ms)), "refused_whole": refused, "chunks": chunks, "splits": splits,
                            "errors": errs[:5], "n_errors": len(errs)}) if ms else \
            {"questions": n, "errors": errs[:5], "n_errors": len(errs), "refused_whole": refused}
        out.append(s)
        print("jev %4d  %s" % (n, s), flush=True)
    return out


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
                for f in ("p50_ms", "p95_ms", "questions_per_s", "usd_per_call", "refused_whole", "splits", "n_errors",
                          "dropped", "peak_mb"):
                    if s.get(f) is not None:
                        keys.put(w, c + f.replace("_", "").replace("questionsper", "qper"), s[f])
    meta = {w: b.meta for w, b in B.items()}
    meta.update(pending=pending, pool={"states": len(states), "questions": len(qs), "order": "shuffled, seed 13"},
                rounds=rounds)
    return cap.save("questions", keys, detail, meta)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    a.add_argument("--sizes", default=",".join(map(str, SIZES)))
    a.add_argument("--rounds", type=int, default=ROUNDS)
    x = a.parse_args()
    main(x.who.split(","), x.kai, [int(n) for n in x.sizes.split(",")], x.rounds)
