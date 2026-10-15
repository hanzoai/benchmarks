"""Kai on the frozen harness through POST /v1/decisions: results/kai/preds.json.gz.

Reads results/states.json.gz ({suite: [[state, questions, gold], ...]}), sends each case as one
request {"model", "state", "questions"} to URL/v1/decisions, and writes one probability vector per
question in the harness's option order (three_way.order), the shape of results/jev/preds.json.gz,
so merge.py scores it beside Laya and Jev. A question with no answer (a refusal, an error after
six tries) is written as null and counted by merge.py as unanswered, never as wrong.

    export HANZO_API_KEY=...                                    # api.hanzo.ai; a local kai serve needs none
    python harness/run_kai.py                                   # every case: 9,499 requests, 11,099 questions
    python harness/run_kai.py --limit 5 --out /tmp/kai.json.gz  # the first 5 cases of every suite
    python harness/run_kai.py --url http://127.0.0.1:8080       # a local `kai serve`
    python harness/merge.py --kai results/kai/preds.json.gz     # score it

Standard library only. A suite already complete in OUT is not asked again, so a stopped run
resumes where it stopped.
"""
import argparse
import concurrent.futures as cf
import gzip
import json
import os
import time
import urllib.error
import urllib.request

from three_way import vector

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
RETRY = {429, 500, 502, 503, 504, 529}


def ask(url, key, body, tries=6, timeout=300):
    """(response, ms, error): one POST /v1/decisions, retried on a refusal to queue or a 5xx."""
    raw = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    err = "no attempt"
    for attempt in range(tries):
        t = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=raw, headers=headers), timeout=timeout) as r:
                return json.load(r), 1e3 * (time.time() - t), None
        except urllib.error.HTTPError as e:
            err = "HTTP %d %s" % (e.code, e.read()[:300].decode("utf-8", "replace"))
            if e.code not in RETRY:
                return None, 1e3 * (time.time() - t), err
            try:
                wait = float(e.headers.get("retry-after") or 0)
            except ValueError:
                wait = 0
            time.sleep(min(60, max(wait, 2 ** attempt)))
        except Exception as e:  # transport, timeout
            err = "%s: %s" % (type(e).__name__, str(e)[:200])
            time.sleep(min(60, 2 ** attempt))
    return None, 0.0, "gave up: " + err


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="https://api.hanzo.ai", help="the server; /v1/decisions is appended")
    ap.add_argument("--model", default="kai")
    ap.add_argument("--states", default=os.path.join(RESULTS, "states.json.gz"))
    ap.add_argument("--out", default=os.path.join(RESULTS, "kai", "preds.json.gz"))
    ap.add_argument("--suites", help="comma-separated suite names; default every suite")
    ap.add_argument("--limit", type=int, default=0, help="the first N cases of each suite (a sample)")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    url = a.url.rstrip("/") + "/v1/decisions"
    key = os.environ.get("HANZO_API_KEY")
    S = json.load(gzip.open(a.states))
    if a.suites:
        S = {n: S[n] for n in a.suites.split(",")}
    preds = json.load(gzip.open(a.out)) if os.path.exists(a.out) else \
        {"backend": "kai", "model": a.model, "url": a.url, "weights": None, "device": None, "dtype": "as served",
         "served": {}, "suites": {}}
    for name, rows in S.items():
        rows = rows[:a.limit] if a.limit else rows
        done = preds["suites"].get(name)
        if done and done.get("complete") and done.get("cases") == len(rows):
            continue
        p, ms, errors = {}, [], []

        def one(ci):
            st, qs, _ = rows[ci]
            return ci, ask(url, key, {"model": a.model, "state": st, "questions": qs})

        with cf.ThreadPoolExecutor(a.workers) as ex:
            for ci, (d, t, err) in ex.map(one, range(len(rows))):
                qs = rows[ci][1]
                if err:
                    errors.append("%d: %s" % (ci, err))
                    p.update({"%d/%s" % (ci, qid): None for qid in qs})
                    continue
                ms.append(round(t, 1))
                r = d.get("routing") or {}
                c = r.get("checkpoint") or d.get("model")
                preds["served"][c] = preds["served"].get(c, 0) + 1
                preds["weights"] = preds["weights"] or r.get("sha256")
                preds["device"] = preds["device"] or r.get("device")
                for qid, q in qs.items():
                    p["%d/%s" % (ci, qid)] = vector(q, (d.get("answers") or {}).get(qid))
        preds["suites"][name] = {"p": p, "latency_ms": sorted(ms), "errors": errors[:50], "n_errors": len(errors),
                                 "cases": len(rows), "complete": True}
        print("%-28s %4d cases  %d errors" % (name, len(rows), len(errors)), flush=True)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with gzip.open(a.out + ".tmp", "wt") as f:
            json.dump(preds, f)
        os.replace(a.out + ".tmp", a.out)
    print("wrote %s: served %s" % (a.out, preds["served"]), flush=True)


if __name__ == "__main__":
    main()
