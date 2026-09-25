"""Score every backend from preds_*.json with the harness's own metric code.

ece_score, macro_f1 and metrics are copied verbatim from research/scripts/bench_local.py, so a
number here means what it means in the upstream report. A question a backend did not answer
(a dropped sequence, an API error) counts as unanswered, not as wrong; the count is reported.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


# --- verbatim from bench_local.py -----------------------------------------------------
def ece_score(conf, corr, bins=15):
    conf, corr = np.asarray(conf, float), np.asarray(corr, float)
    if not len(conf):
        return float("nan")
    e, edges = 0.0, np.linspace(0, 1, bins + 1)
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        s = (conf >= lo if i == 0 else conf > lo) & (conf <= hi)
        if s.any():
            e += s.mean() * abs(conf[s].mean() - corr[s].mean())
    return float(e)


def macro_f1(g, p):
    g, p = np.asarray(g), np.asarray(p)
    f = []
    for c in sorted(set(g.tolist()) | set(p.tolist())):
        tp = int(((p == c) & (g == c)).sum()); fp = int(((p == c) & (g != c)).sum())
        fn = int(((p != c) & (g == c)).sum())
        f.append(2 * tp / max(1, 2 * tp + fp + fn))
    return float(np.mean(f))


def metrics(rows):
    rows = [r for r in rows if r[1] is not None]
    if not rows:
        return {"n": 0}
    g = np.array([x[0] for x in rows]); p = np.array([int(np.argmax(x[1])) for x in rows])
    c = np.array([float(np.max(x[1])) for x in rows]); corr = (p == g).astype(float)
    return {"n": len(rows), "accuracy": round(float(corr.mean()), 4),
            "macro_f1": round(macro_f1(g, p), 4), "ece": round(ece_score(c, corr), 4),
            "brier": round(float(np.mean([((np.asarray(x[1]) - np.eye(len(x[1]))[x[0]]) ** 2).sum()
                                          for x in rows])), 4),
            "nll": round(float(np.mean([-math.log(max(float(x[1][x[0]]), 1e-12)) for x in rows])), 4),
            "mean_confidence": round(float(c.mean()), 4),
            "acc_at_50_coverage": round(float(corr[np.argsort(-c)[:max(1, len(c)//2)]].mean()), 4)}
# ---------------------------------------------------------------------------------------


def typed_extra(items):
    """Part B's extra metrics: soft accuracy, Brier against the teacher, score MAE, within-1."""
    soft, brier, mae, w1 = [], [], [], []
    for g, p in items:
        if p is None:
            continue
        p = np.asarray(p, float)
        gp = np.asarray(g.get("soft") or [], float)
        if gp.size and gp.sum() > 0:
            gp = gp / gp.sum()
            pp = p[:len(gp)] if len(p) >= len(gp) else np.pad(p, (0, len(gp) - len(p)))
            pp = pp / max(pp.sum(), 1e-12)
            soft.append(float((pp * gp).sum())); brier.append(float(((pp - gp) ** 2).sum()))
        if "gold_score" in g:
            e = float((np.arange(len(p)) * p).sum())
            mae.append(abs(e - g["gold_score"])); w1.append(float(abs(e - g["gold_score"]) <= 1))
    r = lambda v: round(float(np.mean(v)), 4) if v else None
    return {"soft_accuracy": r(soft), "brier_vs_soft": r(brier), "score_mae": r(mae), "within_1_level": r(w1)}


def items(gold, preds):
    """(gold record, prediction) per question, in suite order."""
    out = []
    for ci, (g, qs) in enumerate(gold):
        for qid, q in qs.items():
            out.append((g[qid], preds.get("%d/%s" % (ci, qid)), q["type"], g.get("_wf")))
    return out


def score(gold, preds, typed=False):
    its = items(gold, preds)
    m = metrics([(g["idx"], None if p is None else np.asarray(p, float)) for g, p, _, _ in its])
    m["unanswered"] = sum(1 for _, p, _, _ in its if p is None)
    answered = [(g, p) for g, p, _, _ in its if p is not None]
    # the share of answers that gave the true option no probability at all: a caller that
    # branches on confidence cannot recover from these
    m["zero_prob"] = round(sum(1 for g, p in answered if float(p[g["idx"]]) < 1e-6) / len(answered), 4) \
        if answered else None
    m["questions"] = len(its)
    if typed:
        m.update(typed_extra([(g, p) for g, p, _, _ in its]))
        by_wf, by_qt = {}, {}
        for g, p, qt, wf in its:
            if p is not None:
                by_wf.setdefault(wf, []).append((g["idx"], np.asarray(p, float)))
                by_qt.setdefault(qt, []).append((g["idx"], np.asarray(p, float)))
        m["by_workflow"] = {k: metrics(v)["accuracy"] for k, v in sorted(by_wf.items())}
        m["by_question_type"] = {k: metrics(v)["accuracy"] for k, v in sorted(by_qt.items())}
    return m


def agreement(gold, a, b):
    same, both = 0, 0
    for ci, (g, qs) in enumerate(gold):
        for qid in qs:
            pa, pb = a.get("%d/%s" % (ci, qid)), b.get("%d/%s" % (ci, qid))
            if pa is None or pb is None:
                continue
            both += 1
            same += int(np.argmax(pa) == np.argmax(pb))
    return round(same / both, 4) if both else None


def pct(v, q):
    return round(float(np.percentile(v, q)), 1) if v else None


def main():
    gold = json.load(open(os.path.join(HERE, "gold_jev.json")))
    kai = json.load(open(os.path.join(HERE, "preds_kai.json")))
    jev = json.load(open(os.path.join(HERE, "preds_jev.json")))
    out = {"suites": {}, "kai_meta": {k: kai[k] for k in ("bundle", "revision", "runtime", "device", "dtype")},
           "jev_meta": {"model": jev["model"]}}
    for name, g in gold.items():
        typed = name == "typed_decisions"
        row = {}
        for m, res in kai["models"].items():
            if name in res:
                row["kai:" + m] = score(g, res[name]["p"], typed)
        # routed: each case answered by the checkpoint the router chose for it
        if name in kai.get("route", {}):
            routed = {}
            for ci, (gg, qs) in enumerate(g):
                m = kai["route"][name][ci]
                for qid in qs:
                    routed["%d/%s" % (ci, qid)] = kai["models"].get(m, {}).get(name, {}).get("p", {}).get("%d/%s" % (ci, qid))
            row["kai:routed"] = score(g, routed, typed)
        if name in jev["suites"]:
            js = jev["suites"][name]
            row["jev"] = score(g, js["p"], typed)
            row["jev"].update({"latency_p50_ms": pct(js["latency_ms"], 50), "latency_p95_ms": pct(js["latency_ms"], 95),
                               "cost_usd": round(js["cost_usd"], 5), "input_tokens": js["input_tokens"],
                               "served": js["served"], "n_errors": js["n_errors"]})
            if "kai:routed" in row:
                row["agreement_routed_jev"] = agreement(g, routed, js["p"])
        out["suites"][name] = row
    lat = jev.get("sequential_latency_ms") or []
    out["jev_sequential_latency"] = {"n": len(lat), "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95)}
    out["jev_total_cost_usd"] = round(sum(s["cost_usd"] for s in jev["suites"].values()), 4)
    # MASSIVE summary over languages
    mass = {n: r for n, r in out["suites"].items() if n.startswith("massive.")}
    if mass:
        summ = {}
        for who in ("kai:english", "kai:multilingual", "kai:routed", "jev"):
            accs = {n.split(".", 1)[1]: r[who]["accuracy"] for n, r in mass.items() if who in r and r[who].get("n")}
            eces = [r[who]["ece"] for r in mass.values() if who in r and r[who].get("n")]
            if accs:
                en = [v for k, v in accs.items() if k.startswith("en")]
                other = [v for k, v in accs.items() if not k.startswith("en")]
                summ[who] = {"languages": len(accs), "macro_accuracy": round(float(np.mean(list(accs.values()))), 4),
                             "english": round(float(np.mean(en)), 4) if en else None,
                             "non_english_macro": round(float(np.mean(other)), 4) if other else None,
                             "above_3x_random": int(sum(1 for v in accs.values() if v > 3.0 / 20)),
                             "macro_ece": round(float(np.mean(eces)), 4)}
        out["massive_summary"] = summ
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=2)
    print(json.dumps({k: v for k, v in out.items() if k != "suites"}, indent=1))
    for name, row in out["suites"].items():
        if name.startswith("massive."):
            continue
        print("%-28s " % name + "  ".join("%s %.3f" % (k.replace("kai:", ""), v["accuracy"])
                                          for k, v in row.items() if isinstance(v, dict) and v.get("n")))


if __name__ == "__main__":
    main()
