"""The oracle over the counterfactual grid, routing regret, and the per-condition metrics.

    from oracle import cells, oracle, regret, summary
    g = cells(rows)                 # {task: {(tier, level): row}}
    best = oracle(g)                # {task: (tier, level)}: the CHEAPEST cell that succeeded
    r = regret(g, best, picks)      # per task: $ over the oracle, and success lost

The oracle is the cheapest successful cell by $ (ties: fewer GPU-seconds, then fewer decode
tokens), never the largest that succeeded: the training target is "the least that works".
"""
import statistics

METRICS = ("gpu_s", "kv_gb_s", "prompt_tokens", "decode_tokens", "reasoning_tokens", "prefill_s", "decode_s", "latency_s", "usd")


def cells(rows, variant="full"):
    """Rows by task and cell; a row whose request failed (server down, cut stream) is not a
    cell: the model was never measured there."""
    g = {}
    for r in rows:
        if r.get("variant", "full") == variant and not r.get("error"):
            g.setdefault(r["task"], {})[(r["tier"], r["level"])] = r
    return g


def cost(r):
    return (r["usd"], r["gpu_s"], r["decode_tokens"])


def oracle(g):
    out = {}
    for task, cs in g.items():
        ok = [(cost(r), key) for key, r in cs.items() if r["success"]]
        if ok:
            out[task] = min(ok)[1]
    return out


def regret(g, best, picks):
    """picks: {task: (tier, level)}. Per task: usd over the oracle (0 when both succeed at the
    same cost; the pick's usd when there is no oracle), whether success was lost, whether the
    pick's cell is missing from the grid."""
    out = {}
    for task, pick in picks.items():
        cs = g.get(task, {})
        r = cs.get(pick)
        o = cs.get(best[task]) if task in best else None
        if r is None:
            out[task] = {"missing": True}
            continue
        out[task] = {"missing": False, "success": r["success"],
                     "lost": o is not None and not r["success"],
                     "regret_usd": (r["usd"] - o["usd"]) if o is not None and r["success"] else None,
                     "oracle": o is not None}
    return out


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def summary(runs, n):
    """runs: one dict per task with success and the METRICS summed over the task's requests
    (router calls included). Means are over successful tasks; success_rate over n tasks."""
    ok = [r for r in runs if r.get("success")]
    out = {"tasks": n, "ran": len(runs), "success": len(ok), "success_rate": len(ok) / n if n else None}
    for m in METRICS:
        xs = [r[m] for r in ok if r.get(m) is not None]
        out[m] = statistics.fmean(xs) if xs else None
    lat = [r["latency_s"] for r in ok if r.get("latency_s") is not None]
    out["latency_p50"], out["latency_p95"] = pct(lat, 0.5), pct(lat, 0.95)
    out["usd_total"] = sum(r.get("usd") or 0.0 for r in runs)
    out["gpu_s_total"] = sum(r.get("gpu_s") or 0.0 for r in runs)
    out["kv_gb_s_total"] = sum(r.get("kv_gb_s") or 0.0 for r in runs)
    out["decode_tokens_total"] = sum(r.get("decode_tokens") or 0 for r in runs)
    return out


def add(a, b):
    """Two sequential task runs summed metric by metric (a retry, a router call)."""
    out = dict(a)
    for m in METRICS:
        out[m] = (a.get(m) or 0) + (b.get(m) or 0)
    return out
