"""How many requests answer identically three times: the recorded runs, or run.py's answer files.

A request is identical when its three answers are the same JSON object (keys sorted): the same
decision with the same probabilities, to the last bit the wire carries. Each answer is kept as
the first 16 hex digits of the SHA-256 of that text, its digest. A request with fewer than three
answers is not counted.

    python stability/score.py                        # the recorded runs: results/*.json.gz
    python stability/score.py runs/kai.jsonl         # an answer file run.py wrote

--jev recorded (the default and only value) is Jev's recorded run; no line of this file calls Jev.
"""
import glob
import gzip
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def digest(answer):
    return hashlib.sha256(json.dumps(answer, sort_keys=True).encode()).hexdigest()[:16]


def count(reps):
    """(identical, differ) over requests that have all three answers."""
    full = [v for v in reps.values() if len(v) == 3 and None not in v]
    same = sum(1 for v in full if len(set(v)) == 1)
    return same, len(full) - same


def recorded(path):
    d = json.load(gzip.open(path))
    return d["model"], count(d["requests"])


def answers(path):
    reps = {}
    for l in open(path):
        x = json.loads(l)
        if x["status"] == 200:
            reps.setdefault(x["id"], {}).setdefault(x["rep"], x["digest"])
    return count({i: [r.get(n) for n in (1, 2, 3)] for i, r in reps.items()})


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a != "recorded"]
    rows = [(os.path.basename(p)[:-len(".json.gz")], *recorded(p)) for p in sorted(glob.glob(os.path.join(HERE, "results", "*.json.gz")))]
    rows += [(p, "this run", answers(p)) for p in args]
    print("%-24s %-20s %22s" % ("run", "model", "identical"))
    for name, model, (same, diff) in rows:
        n = same + diff
        print("%-24s %-20s %6d / %-6d %6.1f%%" % (name, model, same, n, 100.0 * same / n if n else 0.0))


if __name__ == "__main__":
    main()
