"""Kai vs Jev on identical questions.

The suites are the upstream Laya harness's own builders (research/scripts/bench_apps.py and
bench_local.py), unchanged: the thirteen application suites, typed-decisions, and MASSIVE
intent. Each backend answers every question and writes one probability vector per question,
in the harness's option order, to preds_<backend>.json. merge.py scores all backends from
those files with the harness's metric code, so every backend is scored by the same function.

    python three_way.py kai    # the three Kai checkpoints, reference runtime, CPU f32
    python three_way.py jev    # typesafe/jev-1.13 through OpenRouter's Decisions API

Kai's weights are byte-identical to upstream Laya's (SHA-256 checked), so the kai run is
also the Laya run.
"""
import concurrent.futures as cf
import importlib.util
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ["LAYA_SRC"]  # a checkout of github.com/NandhaKishorM/laya at 0.3.20
BUNDLE, REV = "hanzoai/kai-1", "b50502c28537df49a3621f6fa543f9e8521e8a9c"
JEV = "typesafe/jev-1.13"
PER_LANG = int(os.environ.get("PER_LANG", "100"))
DATA = os.path.join(HERE, "data")

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("BENCH_N", "400")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bl = module("bl", os.path.join(SRC, "research/scripts/bench_local.py"))
ba = module("ba", os.path.join(SRC, "research/scripts/bench_apps.py"))
bl.REPO = DATA


def suites():
    """name -> list of (state, questions, gold) where gold maps qid -> harness gold record."""
    out = {}
    ba.build()
    for name, S in ba.SUITES.items():
        rows = []
        for (state, qs), g in zip(S["cases"], S["gold"]):
            (qid,) = qs.keys()
            rows.append((state, qs, {qid: {"idx": g}}))
        out[name] = rows
    cases, gold, wfs = bl.build_typed_decisions()
    out["typed_decisions"] = [(st, qs, dict(g, **{"_wf": w})) for (st, qs), g, w in zip(cases, gold, wfs)]
    langs = bl.massive_languages()
    for lg, (cases, gold, _) in bl.build_massive(langs, PER_LANG).items():
        out["massive." + lg] = [(st, qs, {"intent": {"idx": g}}) for (st, qs), g in zip(cases, gold)]
    return out


def order(qdef):
    """The harness's option order for a question: what a probability vector is indexed by."""
    t, c = qdef["type"], qdef.get("criteria")
    if t == "noul":
        return ["false", "true"]
    if t == "score":
        return [str(i) for i in range(len(c))]
    return list(c.keys()) if isinstance(c, dict) else list(c)


# ------------------------------------------------------------------ kai
def run_kai(S):
    import laya
    from huggingface_hub import snapshot_download
    from laya.router import Router

    local = snapshot_download(BUNDLE, revision=REV)
    sub = {"english": None, "multilingual": "multilingual", "typed-decisions": "typed-decisions"}
    router = Router()
    route = {}
    for name, rows in S.items():
        route[name] = [router.route(st, qs).model for st, qs, _ in rows]
    preds = {"backend": "kai", "bundle": BUNDLE, "revision": REV, "runtime": "laya " + laya.__version__,
             "device": "cpu", "dtype": "f32", "route": route, "models": {}}
    for m in ("english", "multilingual", "typed-decisions"):
        ag = laya.load(local, device="cpu", subfolder=sub[m])
        ag.model.eval()
        preds["models"][m] = {}
        for name, rows in S.items():
            cases = [(st, qs) for st, qs, _ in rows]
            lgs, idx, secs, dropped = bl.score_cases(ag, cases, tag="%s/%s" % (m, name))
            out = {}
            for (ci, qid, qt, k), z in zip(idx, lgs):
                out["%d/%s" % (ci, qid)] = None if z is None else \
                    [float(x) for x in bl.softmax_t(z, bl.temp_for(ag, qt, k))]
            preds["models"][m][name] = {"p": out, "seconds": secs, "dropped": dropped}
            print("kai %-16s %-28s %6.1fs" % (m, name, secs), flush=True)
            json.dump(preds, open(os.path.join(HERE, "preds_kai.json"), "w"))
        del ag
    return preds


# ------------------------------------------------------------------ jev
KEY = None
_lock = threading.Lock()


def jev_call(state, qs):
    qs = json.loads(json.dumps(qs))
    for q in qs.values():  # the harness allows a bare label; the wire wants a description
        c = q.get("criteria")
        if isinstance(c, dict):
            q["criteria"] = {k: (v if isinstance(v, str) and v else k) for k, v in c.items()}
    body = json.dumps({"model": JEV, "state": state, "questions": qs}).encode()
    err = "retries exhausted"
    for attempt in range(8):
        req = urllib.request.Request("https://openrouter.ai/api/alpha/decisions", data=body,
                                     headers={"Authorization": "Bearer " + KEY,
                                              "Content-Type": "application/json"})
        t = time.time()
        try:
            r = urllib.request.urlopen(req, timeout=120)
            d = json.load(r)
            return d, 1000 * (time.time() - t), None
        except urllib.error.HTTPError as e:
            msg = e.read()[:300].decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504):
                err = "HTTP %d %s" % (e.code, msg)
                time.sleep(min(60, 2 ** attempt))
                continue
            return None, 1000 * (time.time() - t), "HTTP %d %s" % (e.code, msg)
        except Exception as e:  # network
            time.sleep(min(60, 2 ** attempt))
            err = str(e)[:200]
    return None, 0.0, "gave up: " + err


def vector(qdef, a):
    keys = order(qdef)
    if not a:
        return None
    t = qdef["type"]
    if t == "noul":
        p = float(a.get("noul", 0.5))
        return [1 - p, p]
    probs = a.get("probabilities") or {}
    v = [float(probs.get(k, 0.0)) for k in keys]
    if sum(v) <= 0:
        pick = a.get("choice") if t == "choice" else None
        if pick in keys:
            v = [1.0 if k == pick else 0.0 for k in keys]
        elif t == "score" and a.get("score") is not None:
            i = min(len(keys) - 1, max(0, int(round(float(a["score"])))))
            v = [1.0 if j == i else 0.0 for j in range(len(keys))]
        else:
            return None
    s = sum(v)
    return [x / s for x in v]


def run_jev(S, workers=8):
    global KEY
    KEY = open(os.path.join(HERE, ".or_key")).read().strip()
    path = os.path.join(HERE, "preds_jev.json")
    preds = json.load(open(path)) if os.path.exists(path) else {"backend": "jev", "model": JEV, "suites": {}}
    # a clean single-call latency sample first, one request at a time
    lat = []
    for st, qs, _ in S["jev.ag_news"][:50]:
        _, ms, err = jev_call(st, qs)
        if not err:
            lat.append(ms)
    preds["sequential_latency_ms"] = sorted(lat)
    for name, rows in S.items():
        if name in preds["suites"] and preds["suites"][name].get("complete"):
            continue
        out, ms_all, errors, served, cost, tin = {}, [], [], {}, 0.0, 0

        def one(ci):
            st, qs, _ = rows[ci]
            return ci, jev_call(st, qs)

        with cf.ThreadPoolExecutor(workers) as ex:
            for ci, (d, ms, err) in ex.map(one, range(len(rows))):
                qs = rows[ci][1]
                if err:
                    errors.append("%d: %s" % (ci, err))
                    for qid in qs:
                        out["%d/%s" % (ci, qid)] = None
                    continue
                ms_all.append(ms)
                served[d.get("model")] = served.get(d.get("model"), 0) + 1
                u = d.get("usage") or {}
                cost += float(u.get("cost") or 0)
                tin += int(u.get("input_tokens") or 0)
                for qid, q in qs.items():
                    out["%d/%s" % (ci, qid)] = vector(q, (d.get("answers") or {}).get(qid))
        preds["suites"][name] = {"p": out, "latency_ms": sorted(ms_all), "errors": errors[:50],
                                 "n_errors": len(errors), "served": served, "cost_usd": cost,
                                 "input_tokens": tin, "complete": True}
        print("jev %-28s %4d cases  %d errors  $%.4f" % (name, len(rows), len(errors), cost), flush=True)
        json.dump(preds, open(path, "w"))
    return preds


if __name__ == "__main__":
    which = sys.argv[1]
    S = suites()
    json.dump({n: [[g, qs] for _, qs, g in rows] for n, rows in S.items()},
              open(os.path.join(HERE, "gold_%s.json" % which), "w"))
    run_kai(S) if which == "kai" else run_jev(S)
    print("done", which, flush=True)
