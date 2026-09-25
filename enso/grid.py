"""The counterfactual grid: every task on every served tier at every budget level.

    from grid import grid, run
    rows = grid(tasks, tiers, levels, "data/smoke/grid.jsonl", Cap(50), concurrency=1)

Rows append to a JSONL file and a rerun skips every (task, tier, level, variant) already
answered without error, so a stopped grid resumes. A row: task, family, tier, label, level,
variant, success, the serve.measure metrics, the parsed answer (not for trace tasks) and the
first 3000 characters of the reply; rows live under enso/data/, which git ignores.
"""
import concurrent.futures as cf
import json
import os
import threading

from serve import Spent, chat, measure
from work import final, messages, score

LOCK = threading.Lock()


def load(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def append(path, row):
    with LOCK:
        with open(path, "a") as f:
            f.write(json.dumps(row) + "\n")


def run(t, tier, level, cap, variant="full", chunks=None, tools=None):
    """One task on one tier at one level; chunks/tools are the kept indices (None: all)."""
    r = chat(tier, messages(t, chunks, tools), tier["budgets"][level], cap)
    m = measure(r, tier)
    ok = r["error"] is None and score(t, r["content"])
    row = {"task": t["id"], "family": t["family"], "tier": tier["id"], "label": tier["label"], "level": level,
           "variant": variant, "success": bool(ok), **m}
    if t["family"] != "trace":
        row["answer"] = (final(r["content"]) or r["content"][-200:])[:200]
    row["_content"] = r["content"]  # for callers in this process; dropped before writing
    return row


def grid(tasks, tiers, levels, path, cap, concurrency=1):
    done = {(r["task"], r["tier"], r["level"], r.get("variant", "full")) for r in load(path) if not r.get("error")}
    todo = [(t, tier, lv) for t in tasks for tier in tiers for lv in levels
            if (t["id"], tier["id"], lv, "full") not in done]

    def one(job):
        t, tier, lv = job
        row = run(t, tier, lv, cap)
        row["content"] = row.pop("_content", "")[:3000]  # data/ only, for K5's completion check
        append(path, row)
        return row

    stop = False
    with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = []
        for job in todo:
            futs.append(ex.submit(one, job))
        for f in cf.as_completed(futs):
            try:
                f.result()
            except Spent:
                stop = True
        if stop:
            print(f"grid: request cap reached; {len(todo)} cells asked")
    return load(path)
