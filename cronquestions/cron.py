"""CronQuestions: one query plan, two temporal stores.

    python3 cron.py facts                          # data/facts.tsv: what both stores load
    python3 cron.py plan <split>                   # data/plan-<split>.jsonl: the store calls per question
    python3 cron.py exact <split>                  # the control: the same calls over dictionaries
    python3 cron.py score <split> <row> <results> [subject]  # runs/<row>-<split>/

A question becomes one or two store calls built from its annotation alone, and
its answer is a pure function of what those calls return. The calls and the
function live here, once; a driver only executes calls. See METHOD.md.
"""

import hashlib
import json
import os
import pickle
import random
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
KG = os.path.join(DATA, "data/wikidata_big/kg/full.txt")
QUESTIONS = os.path.join(DATA, "data/wikidata_big/questions")
COVERED = ("simple_entity", "simple_time", "before_after", "first_last")
OPEN = 9999  # an interval whose close the store did not return


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def facts():
    """Every KG line whose interval is ordered. The 652 with start > end are
    dropped for both stores: Semantica refuses every point-in-time query while
    one is loaded (METHOD.md), so keeping them would measure a crash."""
    kept = dropped = 0
    with open(KG) as src, open(os.path.join(DATA, "facts.tsv"), "w") as out:
        for line, text in enumerate(src, 1):
            s, r, o, a, b = text.rstrip("\n").split("\t")
            if int(a) > int(b):
                dropped += 1
                continue
            out.write(f"{line}\t{s}\t{r}\t{o}\t{int(a)}\t{int(b)}\n")
            kept += 1
    print(f"facts: {kept} kept, {dropped} dropped (start > end)")


def calls(q):
    """The store calls for one question. `at` is what is in force for
    (entity, relation) at a year; `history` is every interval of that pair;
    `touch` is every interval of any relation into or out of an entity."""
    a, r = q["annotation"], next(iter(q["relations"]))
    t = q["type"]
    if t == "simple_entity":
        e, d = (a["head"], "out") if "head" in a else (a["tail"], "in")
        return [{"op": "at", "entity": e, "relation": r, "dir": d, "t": int(a["time"])}]
    if t in ("simple_time", "first_last"):
        e, d = (a["head"], "out") if "head" in a else (a["tail"], "in")
        return [{"op": "history", "entity": e, "relation": r, "dir": d}]
    if t == "before_after":
        if "event_head" in a:
            return [{"op": "touch", "entity": a["event_head"]},
                    {"op": "history", "entity": a["tail"], "relation": r, "dir": "in"}]
        if r == "P39":  # the answer holds the same position
            return [{"op": "history", "entity": a["tail"], "relation": r, "dir": "in"}]
        return [{"op": "history", "entity": a["head"], "relation": r, "dir": "out"}]
    return None


def answer(q, rows):
    """The top-1 answer from what the calls returned, or None. The rules were
    chosen on valid against the KG itself and frozen (METHOD.md)."""
    a, t = q["annotation"], q["type"]
    iv = [(o, s, OPEN if e is None else e) for o, s, e in rows[-1]]
    by_start = lambda z: (z[1], z[2], z[0])
    by_end = lambda z: (z[2], z[1], z[0])
    if t == "simple_entity":
        return max(iv, key=by_start)[0] if iv else None
    if t == "simple_time":
        mine = [z for z in iv if z[0] == a["tail"]]
        return min(mine, key=by_start)[1] if mine else None
    if t == "first_last":
        if "head" in a and "tail" in a:
            iv = [z for z in iv if z[0] == a["tail"]]
        if not iv:
            return None
        z = min(iv, key=by_start) if a["adj"] == "first" else max(iv, key=by_end)
        if q["answer_type"] == "entity":
            return z[0]
        return z[1] if a["adj"] == "first" else z[2]
    if t == "before_after":
        if "event_head" in a:
            ev = [(o, s, OPEN if e is None else e) for o, s, e in rows[0]]
            others = iv
        else:
            anchor = a["head"] if next(iter(q["relations"])) == "P39" else a["tail"]
            ev = [z for z in iv if z[0] == anchor]
            others = [z for z in iv if z[0] != anchor]
        if not ev:
            return None
        start, end = min(z[1] for z in ev), max(z[2] for z in ev)
        if a["type"] == "before":
            c = [z for z in others if z[1] < start]
            return max(c, key=by_end)[0] if c else None
        c = [z for z in others if z[2] > end]
        return min(c, key=by_start)[0] if c else None
    return None


def load(split):
    with open(os.path.join(QUESTIONS, f"{split}.pickle"), "rb") as f:
        return pickle.load(f)


def plan(split):
    qs = load(split)
    n = 0
    with open(os.path.join(DATA, f"plan-{split}.jsonl"), "w") as out:
        for i, q in enumerate(qs):
            c = calls(q)
            if c is None:
                continue
            out.write(json.dumps({"i": i, "type": q["type"], "calls": c}) + "\n")
            n += 1
    print(f"plan {split}: {n} of {len(qs)} questions ({', '.join(COVERED)})")


def exact(split):
    """The control: the same calls answered by dictionaries over facts.tsv, so a
    store's loss is measured against what the plan can reach, not against 1."""
    out, inn, touch = {}, {}, {}
    with open(os.path.join(DATA, "facts.tsv")) as f:
        for text in f:
            _, s, r, o, a, b = text.rstrip("\n").split("\t")
            a, b = int(a), int(b)
            out.setdefault((s, r), []).append([o, a, b])
            inn.setdefault((o, r), []).append([s, a, b])
            touch.setdefault(s, []).append([o, a, b])
            touch.setdefault(o, []).append([s, a, b])

    def run(c):
        if c["op"] == "touch":
            return touch.get(c["entity"], [])
        rows = (out if c["dir"] == "out" else inn).get((c["entity"], c["relation"]), [])
        if c["op"] == "at":
            return [z for z in rows if z[1] <= c["t"] <= z[2]]
        return rows

    with open(os.path.join(DATA, f"plan-{split}.jsonl")) as f, \
            open(os.path.join(DATA, f"results-kg-{split}.jsonl"), "w") as w:
        w.write(json.dumps({"store": "dictionaries over facts.tsv, no store", "host": "",
                            "load_1m": {"at_start": os.getloadavg()[0]}, "load": {}}) + "\n")
        for text in f:
            p = json.loads(text)
            w.write(json.dumps({"i": p["i"], "rows": [run(c) for c in p["calls"]], "ms": []}) + "\n")


def interval(xs, seed=0, n=1000):
    """Mean and bootstrap 95% interval, fixed seed so a rerun prints the same."""
    if not xs:
        return {"mean": 0, "lo": 0, "hi": 0}
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(xs, k=len(xs))) / len(xs) for _ in range(n))
    return {"mean": sum(xs) / len(xs), "lo": means[int(0.025 * n)], "hi": means[int(0.975 * n) - 1]}


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def latency(xs):
    return {"n": len(xs), "p50": pct(xs, 0.5), "p99": pct(xs, 0.99), "mean": sum(xs) / len(xs) if xs else None}


def git(path, *args):
    return subprocess.run(["git", "-C", path, *args], capture_output=True, text=True).stdout.strip()


def score(split, row, results, subject=""):
    qs = load(split)
    with open(results) as f:
        head = json.loads(f.readline())  # the driver's own record of the load
        res = [json.loads(line) for line in f]
    with open(os.path.join(DATA, f"plan-{split}.jsonl")) as f:
        ops = {p["i"]: [c["op"] for c in p["calls"]] for p in map(json.loads, f)}
    hits, ms, preds = {}, {}, []
    for r in res:
        q = qs[r["i"]]
        p = answer(q, r["rows"])
        hit = int(p is not None and p in q["answers"])
        hits.setdefault(q["type"], []).append(hit)
        for op, m in zip(ops[r["i"]], r["ms"]):
            if m is not None:
                ms.setdefault(op, []).append(m)
        preds.append({"i": r["i"], "id": q["uniq_id"], "type": q["type"], "prediction": p, "hit": hit})
    every = [h for t in COVERED for h in hits.get(t, [])]
    metrics = {
        "benchmark": "cronquestions",
        "row": row,
        "split": split,
        "n": len(every),
        "of": len(qs),
        "hits@1": {"overall": interval(every), **{t: {"n": len(hits.get(t, [])), **interval(hits.get(t, []))} for t in COVERED}},
        "load": head["load"],
        "query_ms": {op: latency(xs) for op, xs in [("all", sum(ms.values(), [])), *sorted(ms.items())]},
        "notes": head.get("notes", {}),
    }
    out = os.path.join(HERE, "runs", f"{row}-{split}")
    os.makedirs(out, exist_ok=True)
    meta = {
        "bench": "CronQuestions (Saxena et al., ACL 2021), data_v2",
        "dataset_sha256": sha(os.path.join(DATA, "data_v2.zip")),
        "facts_sha256": sha(os.path.join(DATA, "facts.tsv")),
        "plan_sha256": sha(os.path.join(DATA, f"plan-{split}.jsonl")),
        "split": split,
        "row": row,
        "store": head["store"],
        "subject": subject,
        "reader": "none",
        "commit": git(HERE, "rev-parse", "--short=12", "HEAD"),
        "host": head["host"],
        "load_1m": head["load_1m"],
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for name, value in (("meta.json", meta), ("metrics.json", metrics)):
        with open(os.path.join(out, name), "w") as f:
            json.dump(value, f, indent=1)
            f.write("\n")
    with open(os.path.join(out, "predictions.jsonl"), "w") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    h = metrics["hits@1"]
    print(f"{row}-{split}: hits@1 {h['overall']['mean']:.4f} over {len(every)} · "
          + " · ".join(f"{t} {h[t]['mean']:.4f}" for t in COVERED)
          + f" · p50 {metrics['query_ms']['all']['p50']} ms · p99 {metrics['query_ms']['all']['p99']} ms")


def site(split="test"):
    """The table the hanzo.ai benchmark page renders: every scored row of a
    split, with its hits@1 intervals, latency and load, in one JSON document.
    Regenerated from runs/, never written by hand."""
    rows = []
    for row in ("kg", "semantica", "hanzo-wire", "hanzo-replay"):
        path = os.path.join(HERE, "runs", f"{row}-{split}")
        with open(os.path.join(path, "metrics.json")) as f:
            m = json.load(f)
        with open(os.path.join(path, "meta.json")) as f:
            meta = json.load(f)
        rows.append({"row": row, "store": meta.get("store", ""), "subject": meta.get("subject", ""),
                     "hits": m["hits@1"], "query_ms": m.get("query_ms", {}), "load": m.get("load", {}),
                     "load_1m": meta.get("load_1m", {})})
    json.dump({"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "split": split,
               "covered": COVERED, "rows": rows}, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "facts":
        facts()
    elif cmd == "plan":
        plan(sys.argv[2])
    elif cmd == "exact":
        exact(sys.argv[2])
    elif cmd == "score":
        score(*sys.argv[2:6])
    elif cmd == "site":
        site(*sys.argv[2:3])
    else:
        sys.exit(__doc__)
