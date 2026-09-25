"""The "Kai in the loop" study, one command per study.

    uv run --with huggingface_hub --with pyarrow python enso/study.py smoke [--kai LIB --device metal]
    uv run --with huggingface_hub --with pyarrow python enso/study.py full --kai LIB [--traces ~/.claude/projects zen]
    uv run python enso/study.py estimate            # expected GPU time of `full` from the grid so far

Steps: tasks (work.py) -> the counterfactual grid (grid.py: every task x served tier x level)
-> the offline conditions B0, B1, R1, K1, K2 over the grid -> the online conditions K3, K4, K5
(they change the prompt or loop) -> enso/results/<study>.json, a flat object keyed
enso/<study>/<condition>/<metric>. Everything a run touched stays in enso/data/<study>/
(gitignored): tasks.jsonl, grid.jsonl, router.jsonl, kai.jsonl, online.jsonl; each step
resumes from its file. Without --kai the K conditions are skipped and say so.

The thesis under test: Kai does not make Zen generate faster; it makes Zen generate less.
So every condition reports decode tokens, KV GB-seconds and GPU-seconds per successful task
beside success, and decode_tps (decode tokens per decode second), which Kai should not move.
"""
import argparse
import copy
import json
import os
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import grid as G  # noqa: E402
import oracle as O  # noqa: E402
import policy as P  # noqa: E402
import work as W  # noqa: E402
from serve import Cap, Spent  # noqa: E402

STUDIES = {
    # <= 50 requests to live endpoints, split so the K run on another host fits beside it.
    "smoke": {"n": {"synthetic": 3, "gsm8k": 1}, "families": ["arith", "needle", "tool", "gsm8k"],
              "tiers": {"flash-halo": ["none", "short", "medium", "deep"], "flash-dgx": ["none", "deep"]},
              "max_tokens": {"none": 1024, "short": 2048, "medium": 4096, "deep": 8192},
              "primary": "flash-halo", "cap": 50, "concurrency": 1, "k": 2, "attempts": 3},
    "full": {"n": {"synthetic": 200, "gsm8k": 200, "mbpp": 100, "bfcl": 100, "trace": 200}, "families": None,
             "tiers": None, "max_tokens": None, "primary": None, "cap": None, "concurrency": 2, "k": 4, "attempts": 3},
}


def jsonl(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def put(path, row):
    G.append(path, row)


def spec(cfg):
    s = json.load(open(os.path.join(HERE, "tiers.json")))
    s = copy.deepcopy(s)
    for t in s["tiers"]:
        for lv, b in (t.get("budgets") or {}).items():
            if cfg["max_tokens"]:
                b["max_tokens"] = min(b["max_tokens"], cfg["max_tokens"][lv])
    return s


def tasks(cfg, data, traces):
    path = os.path.join(data, "tasks.jsonl")
    if not os.path.exists(path):
        ts = W.build(cfg["n"], random.Random(W.SEED), traces)
        if cfg["families"]:
            ts = [t for t in ts if t["family"] in cfg["families"]]
        with open(path, "w") as f:
            for t in ts:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return jsonl(path)


def cells(tiers, cfg):
    """[(tier, [levels])] the grid covers."""
    if cfg["tiers"] is None:
        return [(t, tiers.levels) for t in tiers.served]
    return [(tiers.by[i], lv) for i, lv in cfg["tiers"].items()]


def run_grid(ts, tiers, cfg, data, cap):
    path = os.path.join(data, "grid.jsonl")
    for tier, levels in cells(tiers, cfg):
        try:
            G.grid(ts, [tier], levels, path, cap, cfg["concurrency"])
        except Spent:
            break
    return jsonl(path)


def cellrun(r):
    return {m: r.get(m) for m in O.METRICS} | {"success": r["success"]}


def offline(ts, tiers, g, data, cap, kai):
    """{condition: {task: (pick, overhead run or None)}} and the Kai decisions made."""
    picks = {"B0": {t["id"]: (P.b0(t, tiers), None) for t in ts},
             "B1": {t["id"]: (P.b1(t, tiers), None) for t in ts}}
    rpath = os.path.join(data, "router.jsonl")
    routed = {r["task"].removesuffix("/router"): r for r in jsonl(rpath) if not r.get("error")}
    picks["R1"] = {}
    for t in ts:
        if t["id"] not in routed:
            try:
                pick, row = P.r1(t, tiers, cap, G.run)
            except Spent:
                break
            row["pick"] = pick
            put(rpath, row)
            routed[t["id"]] = row
        row = routed[t["id"]]
        picks["R1"][t["id"]] = (tuple(row["pick"]), cellrun(row))
    if kai is None:
        return picks, {}
    kpath = os.path.join(data, "kai.jsonl")
    seen = {(r["task"], r["program"]): r for r in jsonl(kpath)}
    k1, k2 = {}, {}
    for t in ts:
        if (t["id"], "router.model@1") not in seen:
            tier, r = P.k1(t, tiers, kai)
            seen[(t["id"], "router.model@1")] = {"task": t["id"], "program": "router.model@1", "pick": tier, "result": r}
            put(kpath, seen[(t["id"], "router.model@1")])
        if (t["id"], "reasoning.budget@1") not in seen:
            level, r = P.k2(t, tiers, kai)
            seen[(t["id"], "reasoning.budget@1")] = {"task": t["id"], "program": "reasoning.budget@1", "pick": level, "result": r}
            put(kpath, seen[(t["id"], "reasoning.budget@1")])
        a, b = seen[(t["id"], "router.model@1")], seen[(t["id"], "reasoning.budget@1")]
        k1[t["id"]] = ((a["pick"], tiers.default), {"kai_ms": a["result"]["ms"]})
        k2[t["id"]] = ((a["pick"], b["pick"]), {"kai_ms": a["result"]["ms"] + b["result"]["ms"]})
    picks["K1"], picks["K2"] = k1, k2
    return picks, seen


def online(ts, tiers, cfg, data, cap, kai, picks, g):
    """K3, K4, K5: {condition: {task: run}}, each run summed over its requests. A condition
    whose selection keeps everything (nothing to select, or Kai not enforced) reuses the
    previous condition's run; K5's first attempt is K4's answer."""
    path = os.path.join(data, "online.jsonl")
    rows = {(r["task"], r["condition"], r["attempt"]): r for r in jsonl(path) if not r.get("error")}
    out = {"K3": {}, "K4": {}, "K5": {}}

    def attempt(t, cond, n, tier, level, chunks, tools):
        key = (t["id"], cond, n)
        if key not in rows:
            row = G.run(t, tier, level, cap, variant=cond, chunks=chunks, tools=tools)
            row["content"] = row.pop("_content", "")[:3000]
            row |= {"condition": cond, "attempt": n, "kept_chunks": chunks, "kept_tools": tools}
            put(path, row)
            rows[key] = row
        return rows[key]

    for t in ts:
        (tier_id, level), _ = picks["K2"][t["id"]]
        tier = tiers.by[tier_id]
        try:
            prev = g.get(t["id"], {}).get((tier_id, level)) or attempt(t, "K2", 0, tier, level, None, None)
            keep_c, rc = P.k3(t, kai, cfg["k"]) if t["chunks"] else (None, None)
            keep_t, rt = P.k4(t, kai, cfg["k"]) if t["tools"] else (None, None)
            ms = sum(r["ms"] for r in (rc, rt) if r)
            if keep_c is not None:
                prev = attempt(t, "K3", 0, tier, level, keep_c, None)
            out["K3"][t["id"]] = cellrun(prev) | {"kai_ms": rc["ms"] if rc else 0}
            if keep_t is not None:
                prev = attempt(t, "K4", 0, tier, level, keep_c, keep_t)
            out["K4"][t["id"]] = cellrun(prev) | {"kai_ms": ms}
            if "content" not in prev:  # a row written without its reply: answer again for K5
                prev = attempt(t, "K5", 0, tier, level, keep_c, keep_t)
            total, steps, cur_tier, cur_level = cellrun(prev) | {"kai_ms": ms}, [], tier, level
            for n in range(1, cfg["attempts"] + 1):
                fin, rd = P.done(t, prev.get("content", ""), kai)
                total["kai_ms"] += rd["ms"]
                if fin or n == cfg["attempts"]:
                    break
                steps.append({"tool": "answer", "result": prev.get("content", "")[:300]})
                st, rp = P.stuck(t, steps, kai)
                total["kai_ms"] += rp["ms"]
                if st:
                    cur_tier = tiers.up(cur_tier)
                cur_level = tiers.levels[min(tiers.levels.index(cur_level) + 1, len(tiers.levels) - 1)]
                prev = attempt(t, "K5", n, cur_tier, cur_level, keep_c, keep_t)
                total = O.add(total, cellrun(prev)) | {"success": prev["success"], "kai_ms": total["kai_ms"]}
            out["K5"][t["id"]] = total | {"attempts": n}
        except Spent:
            break
    return out


def report(study, ts, g, best, conds, extra):
    """Flat results: enso/<study>/<condition>/<metric>."""
    res = {}
    n = len(ts)
    base = {t: runs for t, runs in conds.get("B0", {}).items()}
    for c, runs in conds.items():
        s = O.summary(list(runs.values()), n)
        tps = [r["decode_tokens"] / r["decode_s"] for r in runs.values()
               if r.get("success") and r.get("decode_s") and r.get("decode_tokens")]
        s["decode_tps"] = statistics.fmean(tps) if tps else None
        ms = [r.get("kai_ms") for r in runs.values() if r.get("kai_ms")]
        s["kai_ms"] = statistics.fmean(ms) if ms else None
        if c in extra:
            rg = extra[c]
            reg = [x["regret_usd"] for x in rg.values() if x.get("regret_usd") is not None]
            s["regret_usd"] = statistics.fmean(reg) if reg else None
            s["success_lost"] = sum(1 for x in rg.values() if x.get("lost"))
            s["missing"] = sum(1 for x in rg.values() if x.get("missing"))
        # Paired with B0 on the tasks this condition ran and both answered.
        both = [t for t in runs if runs[t].get("success") and base.get(t, {}).get("success")]
        for m in ("decode_tokens", "kv_gb_s", "gpu_s", "usd"):
            a = sum(runs[t][m] or 0 for t in both)
            b = sum(base[t][m] or 0 for t in both)
            s[f"{m}_vs_b0"] = a / b if b else None
        s["paired"] = len(both)
        for k, v in s.items():
            res[f"enso/{study}/{c}/{k}"] = v
    res[f"enso/{study}/oracle/coverage"] = len(best) / n if n else None
    for (tier, level), rs in sorted(by_cell(g).items()):
        s = O.summary(rs, len(rs))
        for k in ("success_rate", "gpu_s", "kv_gb_s", "decode_tokens", "latency_p50", "latency_p95", "usd"):
            res[f"enso/{study}/grid/{tier}/{level}/{k}"] = s[k]
    return res


def by_cell(g):
    out = {}
    for cs in g.values():
        for key, r in cs.items():
            out.setdefault(key, []).append(r)
    return out


def estimate(g, tiers, full, routed=()):
    """Expected GPU time of `full`: measured mean GPU-seconds per cell x cells, by tier and
    level, with a level-mean fallback for cells the grid has not measured on that tier."""
    means = {k: statistics.fmean([r["gpu_s"] for r in rs]) for k, rs in by_cell(g).items() if rs}
    level = {}
    for (tier, lv), m in means.items():
        level.setdefault(lv, []).append(m)
    n = sum(full["n"].values())
    total, parts = 0.0, {}
    for t in tiers.served:
        for lv in tiers.levels:
            m = means.get((t["id"], lv)) or (statistics.fmean(level[lv]) if lv in level else None)
            if m is None:
                continue
            parts[f"{t['id']}/{lv}"] = m * n / 3600
            total += m * n
    router = statistics.fmean([r["gpu_s"] for r in routed]) if routed else 0.0
    online = 1.0 + 1.0 + 1.5  # K3, K4, K5 runs per task at about a grid cell each (K5: 1.5 attempts)
    cell = total / (len(tiers.served) * len(tiers.levels) * n) if n else 0
    extra = n * (router + online * cell)
    return {"tasks": n, "cells": n * len(tiers.served) * len(tiers.levels), "grid_gpu_h": total / 3600,
            "online_gpu_h": extra / 3600, "gpu_h": (total + extra) / 3600, "by_cell_gpu_h": parts,
            "assumptions": "per-cell GPU-seconds from this grid's mean over its tasks (smoke tasks are "
                           "shorter than full's; scale by the full workload's prompt and decode lengths), "
                           "no queueing, concurrency as run"}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("study", choices=list(STUDIES) + ["estimate"])
    ap.add_argument("--kai", help="path to libcontrol (.so/.dylib); without it K1..K5 are skipped")
    ap.add_argument("--models", default="kai-1-agent")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--traces", nargs="*", default=[])
    ap.add_argument("--cap", type=int, help="most requests this run may send (default: the study's)")
    ap.add_argument("--from", dest="source", default="smoke", help="estimate: the study whose grid to read")
    a = ap.parse_args(argv)
    if a.study == "estimate":
        g = O.cells(jsonl(os.path.join(a.data, a.source, "grid.jsonl")))
        routed = jsonl(os.path.join(a.data, a.source, "router.jsonl"))
        print(json.dumps(estimate(g, P.Tiers(spec(STUDIES["full"])), STUDIES["full"], routed), indent=1))
        return
    cfg = STUDIES[a.study]
    data = os.path.join(a.data, a.study)
    os.makedirs(data, exist_ok=True)
    tiers = P.Tiers(spec(cfg), cfg["primary"])
    cap = Cap(a.cap if a.cap is not None else (cfg["cap"] or 10**9))
    ts = tasks(cfg, data, a.traces)
    print(f"{a.study}: {len(ts)} tasks; tiers {[t['id'] for t, _ in cells(tiers, cfg)]}; cap {cfg['cap']}")
    kai = None
    if a.kai:
        from kai import Kai
        kai = Kai(a.kai, a.models.split(","), a.device)
    t0 = time.time()
    rows = run_grid(ts, tiers, cfg, data, cap)
    g = O.cells(rows)
    best = O.oracle(g)
    picks, _ = offline(ts, tiers, g, data, cap, kai)
    conds, extra = {}, {}
    for c, ps in picks.items():
        conds[c] = {}
        for task, (pick, over) in ps.items():
            cell = g.get(task, {}).get(tuple(pick))
            if cell is None:
                continue
            run = cellrun(cell)
            if over:
                run = O.add(run, over) if "usd" in over else run | over
            conds[c][task] = run
        extra[c] = O.regret(g, best, {t: tuple(p) for t, (p, _) in ps.items()})
    if kai:
        conds |= online(ts, tiers, cfg, data, cap, kai, picks, g)
    res = report(a.study, ts, g, best, conds, extra)
    res[f"enso/{a.study}/meta/requests"] = cap.used
    res[f"enso/{a.study}/meta/seconds"] = time.time() - t0
    res[f"enso/{a.study}/meta/kai"] = bool(kai)
    est = estimate(g, P.Tiers(spec(STUDIES["full"])), STUDIES["full"], jsonl(os.path.join(data, "router.jsonl")))
    for k, v in est.items():
        if not isinstance(v, (dict, str)):
            res[f"enso/{a.study}/estimate/{k}"] = v
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    out = os.path.join(HERE, "results", f"{a.study}.json")
    json.dump(res, open(out, "w"), indent=1, sort_keys=True)
    print(json.dumps({k: v for k, v in res.items() if "/grid/" not in k}, indent=1, sort_keys=True))
    print(f"-> {out}; {cap.used} requests")
    print("full estimate:", json.dumps(est, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
