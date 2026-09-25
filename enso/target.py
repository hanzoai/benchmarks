"""Training rows for Kai from the counterfactual grid: the target is the CHEAPEST cell that
succeeded (oracle.py), never the largest.

    uv run python enso/target.py <data/study> --programs <hanzoai/decision>/program/programs <out dir>
        [--traces enso-trace.jsonl ...] [--val 100]

Writes enso-router.{train,val}.jsonl.gz in hanzoai/decision's train format (train/src/data:
one {source, lang, state, questions, target} per line, gzip): the state is router.model's
(kai.route over the task's messages), the questions router.model@1's `tier` and
reasoning.budget@1's `budget` read from the program files, the targets one-hot on the oracle
cell's tier label and level. The split is decision's `is_val`: the first content unit's hash.

With --traces (Enso's JSONL request traces), production requests are joined to grid tasks by
the model op's state hash, and join.json records per matched task what Enso served and how it
went beside the oracle; traces carry hashes, never text, so they add outcomes, not states.
"""
import argparse
import gzip
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import oracle as O  # noqa: E402
import policy as P  # noqa: E402

DOCUMENT = 200


def unit(domain, text):
    h = hashlib.sha256(domain.encode() + b"\x00" + text.encode()).digest()
    return h[:16].hex()


def leaves(v, out):
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, list):
        for x in v:
            leaves(x, out)
    elif isinstance(v, dict):
        for x in v.values():
            leaves(x, out)


def units(state):
    """decision's train::data::units: the whole-state unit, then one per long leaf's opening."""
    ls = []
    if isinstance(state, str):
        try:
            v = json.loads(state)
            if isinstance(v, (dict, list)):
                return units(v)
        except ValueError:
            pass
        ls.append(state)
    else:
        leaves(state, ls)
    out = [unit("state", "\x1f".join(" ".join(l.split()) for l in ls))]
    for l in ls:
        if len(l) >= DOCUMENT:
            out.append(unit("open", "".join(c.lower() for c in l if c.isalnum())[:DOCUMENT]))
    return out


def is_val(state, per_mille):
    return int(units(state)[0][:8], 16) % 1000 < per_mille


def question(programs, pid, qid):
    p = json.load(open(os.path.join(programs, pid + ".json")))
    return p["questions"][qid]


def onehot(i, n):
    return [1.0 if j == i else 0.0 for j in range(n)]


def rows(tasks, grid, spec, programs):
    g = O.cells(grid)
    best = O.oracle(g)
    by = {t["id"]: t for t in tasks}
    tier_q = question(programs, "router.model@1", "tier")
    budget_q = question(programs, "reasoning.budget@1", "budget")
    labels = list(tier_q["criteria"])
    tiers = {t["id"]: t for t in spec["tiers"]}
    out = []
    for task, (tier, level) in sorted(best.items()):
        t = by.get(task)
        if t is None:
            continue
        out.append({"source": "enso-router", "lang": "en", "state": P.route(t),
                    "questions": {"tier": tier_q, "budget": budget_q},
                    "target": {"tier": onehot(labels.index(tiers[tier]["label"]), len(labels)),
                               "budget": onehot(spec["levels"].index(level), len(budget_q["criteria"]))},
                    "_task": task})
    return out


def join(examples, kai_rows, traces):
    """Production requests whose model-op state hash equals a grid task's (as Kai hashed it)."""
    hashes = {}
    for r in kai_rows:
        if r["program"] == "router.model@1":
            for x in r["result"]["results"]:
                hashes[x["state"]] = r["task"]
    out = []
    for path in traces:
        for line in open(path):
            try:
                tr = json.loads(line)
            except ValueError:
                continue
            op = (tr.get("ops") or {}).get("model") or {}
            for h in ([op["state"]] if isinstance(op.get("state"), str) else op.get("states") or []):
                if h in hashes:
                    out.append({"task": hashes[h], "state": h, "served": tr.get("served"), "outcome": tr.get("outcome"),
                                "kai": op.get("signals"), "applied": op.get("applied")})
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--programs", required=True)
    ap.add_argument("out")
    ap.add_argument("--traces", nargs="*", default=[])
    ap.add_argument("--val", type=int, default=100, help="validation share, per mille")
    a = ap.parse_args(argv)
    load = lambda f: [json.loads(l) for l in open(os.path.join(a.data, f))] if os.path.exists(os.path.join(a.data, f)) else []
    spec = json.load(open(os.path.join(HERE, "tiers.json")))
    ex = rows(load("tasks.jsonl"), load("grid.jsonl"), spec, a.programs)
    os.makedirs(a.out, exist_ok=True)
    split = {"train": [], "val": []}
    for e in ex:
        e.pop("_task")
        split["val" if is_val(e["state"], a.val) else "train"].append(e)
    for name, es in split.items():
        with gzip.open(os.path.join(a.out, f"enso-router.{name}.jsonl.gz"), "wt") as f:
            for e in es:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    if a.traces:
        j = join(ex, load("kai.jsonl"), a.traces)
        json.dump(j, open(os.path.join(a.out, "join.json"), "w"), indent=1)
        print(f"join: {len(j)} production requests matched grid tasks")
    print(f"{len(split['train'])} train, {len(split['val'])} val -> {a.out}")


if __name__ == "__main__":
    main(sys.argv[1:])
