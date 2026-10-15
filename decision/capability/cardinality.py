"""Choice among K options, K = 4, 16, 77 and 150, through POST /v1/decisions.

K = 4, 16, 77  the frozen jev.banking77_full cases (Banking77 test, 400, harness seed 13). At 4
               and 16 the candidates are the gold label and its K-1 nearest labels by word overlap
               (hard negatives; ties by seed), in seeded order; at 77 the case is the frozen one.
K = 150        CLINC150 test (clinc/clinc_oos plus @155b9c71, in scope), 400 by seed 13.

These are the cases `results/cardinality.json` was measured on (`bench cap`, which builds them with
the same draws); rebuilding them here and scoring kai-1's and Jev's recorded answers against them
gives each record question by question (--check). Accuracy is `accall`: correct over every question, an
unanswered question counted against. K of 1,000 and more (WordNet) and the shortlist variants
(`sl.`, `bi.`) are kept as recorded and are not rebuilt by this file.

    python capability/cardinality.py --score                        # the recorded runs, kai-1 and Jev
    uv run --with datasets python capability/cardinality.py --check  # rebuilt cases reproduce kai-1's record
    export HANZO_API_KEY=...
    uv run --with datasets python capability/cardinality.py --url https://api.hanzo.ai --model kai \\
        --out runs/kai [--k 16,77] [--limit 20]

A run writes <out>/<model>.k<K>.preds.json.gz ({"ci/qid": [p, ...]}) and prints its accuracy beside
the recorded kai-1 and Jev at each K. Jev is never called: --jev recorded (the only value) reads
results/cardinality/jev.k<K>.sums.json.gz. A K of 4, 16 or 77 needs only the standard library; 150
needs `datasets` for CLINC150.
"""
import argparse
import concurrent.futures as cf
import gzip
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results", "cardinality")
STATES = os.path.join(HERE, "..", "results", "states.json.gz")
KS = [4, 16, 77, 150]
SEED = 13
INS = {"clinc": "Which intent does `message` express?"}
RETRY = {429, 500, 502, 503, 504, 529}


def load(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def words(s):
    return set(re.findall(r"[a-z]+", s.lower()))


def banking(k):
    rows = load(STATES)["jev.banking77_full"]
    if k == 77:
        return rows
    out = []
    for ci, (st, qs, g) in enumerate(rows):
        labels = list(qs["intent"]["criteria"])
        gl = labels[g["intent"]["idx"]]
        rng = random.Random("%d/%d/%d" % (SEED, k, ci))
        w = words(gl)
        rest = sorted((l for l in labels if l != gl),
                      key=lambda l: (-len(w & words(l)) / len(w | words(l)), rng.random()))
        opts = [gl] + rest[:k - 1]
        rng.shuffle(opts)
        q = dict(qs["intent"], criteria={l: None for l in opts})
        out.append([st, {"intent": q}, {"intent": {"idx": opts.index(gl)}}])
    return out


def clinc():
    from datasets import load_dataset
    ds = load_dataset("clinc/clinc_oos", "plus", split="test", revision="155b9c710419136e17307b80d0a13e68cd46b4ec")
    names = ds.features["intent"].names
    keep = [i for i, n in enumerate(names) if n != "oos"]
    labels = [names[i].replace("_", " ") for i in keep]
    rows = [r for r in ds if names[r["intent"]] != "oos"]
    random.Random(SEED).shuffle(rows)
    q = {"type": "choice", "instructions": INS["clinc"], "criteria": {l: None for l in labels}}
    return [[{"message": r["text"]}, {"intent": q}, {"intent": {"idx": keep.index(r["intent"])}}] for r in rows[:400]]


def cases(k):
    return banking(k) if k <= 77 else clinc()


def argmax(v):
    """The first index of the largest value, as numpy's argmax."""
    return max(range(len(v)), key=lambda i: (v[i], -i))


def oks(rows, p):
    """Per question, in case order, whether its answer's first argmax is gold; unanswered is False."""
    return [p.get("%d/%s" % (ci, qid)) is not None and argmax(p["%d/%s" % (ci, qid)]) == g[qid]["idx"]
            for ci, (_, qs, g) in enumerate(rows) for qid in qs]


def accall(rows, p):
    """(correct, questions): an unanswered question counts against."""
    ok = oks(rows, p)
    return sum(ok), len(ok)


def recorded(who, k, n=0):
    """(correct, questions) of a recorded run over its first n cases (0: all), from its summaries."""
    path = os.path.join(RESULTS, "%s.k%d.sums.json.gz" % (who, k))
    if not os.path.exists(path):
        return None
    s = load(path)["sums"]
    s = s[:n] if n else s
    return sum(1 for x in s if x and x["ok"]), len(s)


def ask(url, key, body, tries=6, timeout=300):
    raw = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    err = "no attempt"
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=raw, headers=headers), timeout=timeout) as r:
                return json.load(r), None
        except urllib.error.HTTPError as e:
            err = "HTTP %d %s" % (e.code, e.read()[:300].decode("utf-8", "replace"))
            if e.code not in RETRY:
                return None, err
            time.sleep(min(60, 2 ** attempt))
        except Exception as e:  # transport, timeout
            err = "%s: %s" % (type(e).__name__, str(e)[:200])
            time.sleep(min(60, 2 ** attempt))
    return None, "gave up: " + err


def run(url, key, model, rows, workers):
    """{"ci/qid": vector over the question's options in order} for every case."""
    p, errors = {}, []

    def one(ci):
        st, qs, _ = rows[ci]
        return ci, ask(url, key, {"model": model, "state": st, "questions": qs})

    with cf.ThreadPoolExecutor(workers) as ex:
        for ci, (d, err) in ex.map(one, range(len(rows))):
            for qid, q in rows[ci][1].items():
                a = None if err else (d.get("answers") or {}).get(qid)
                probs = (a or {}).get("probabilities") or {}
                p["%d/%s" % (ci, qid)] = [float(probs.get(l, 0.0)) for l in q["criteria"]] if probs else None
            if err:
                errors.append("%d: %s" % (ci, err))
    return p, errors


def cell(x):
    return "%16s" % ("–" if x is None else "%d/%d %6.2f%%" % (x[0], x[1], 100.0 * x[0] / x[1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--k", default=",".join(map(str, KS)))
    ap.add_argument("--url", help="a server; /v1/decisions is appended")
    ap.add_argument("--model", default="kai")
    ap.add_argument("--out", default="runs")
    ap.add_argument("--limit", type=int, default=0, help="the first N cases at each K (a sample)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--jev", default="recorded", choices=["recorded"], help="Jev is scored from its recorded answers")
    ap.add_argument("--score", action="store_true", help="print the recorded runs and stop")
    ap.add_argument("--check", action="store_true", help="rebuild the cases and score kai-1's recorded answers on them")
    a = ap.parse_args()
    ks = [int(k) for k in a.k.split(",")]
    print("%7s %16s %16s %16s" % ("options", "this run", "kai-1", "jev-1.13"))
    for k in ks:
        mine = None
        if a.check or a.url:
            rows = cases(k)
            rows = rows[:a.limit] if a.limit else rows
        if a.check:
            for who in ("kai", "jev"):
                p = load(os.path.join(RESULTS, "%s.k%d.preds.json.gz" % (who, k)))
                want = [bool(x and x["ok"]) for x in load(os.path.join(RESULTS, "%s.k%d.sums.json.gz" % (who, k)))["sums"]]
                if oks(rows, p) != want[:len(rows)]:
                    sys.exit("k%d: %s's recorded answers scored on the rebuilt cases differ from its record" % (k, who))
            mine = accall(rows, load(os.path.join(RESULTS, "kai.k%d.preds.json.gz" % k)))
        elif a.url:
            p, errors = run(a.url.rstrip("/") + "/v1/decisions", os.environ.get("HANZO_API_KEY"), a.model, rows, a.workers)
            os.makedirs(a.out, exist_ok=True)
            with gzip.open(os.path.join(a.out, "%s.k%d.preds.json.gz" % (a.model.replace("/", "_"), k)), "wt") as f:
                json.dump(p, f)
            mine = accall(rows, p)
            if errors:
                print("  k%d: %d cases unanswered, first: %s" % (k, len(errors), errors[0]))
        print("%7d %s %s %s" % (k, cell(mine), cell(recorded("kai", k, a.limit)), cell(recorded("jev", k, a.limit))))
    if a.check:
        print("rebuilt cases reproduce kai-1's and Jev's records question by question at every K")


if __name__ == "__main__":
    main()
