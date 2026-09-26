"""Calibration and abstention over every answer already on disk; no model is called.

Populations, each pooled over its questions:
    orig       the 62 frozen suites (results/{laya,jev,kai}/preds.json.gz; Laya is the router's
               checkpoint per case, typed_decisions on laya:typed-decisions, merge.OWN)
    apps       the 10 suites that are neither typed decisions nor MASSIVE
    td         typed decisions
    massive    MASSIVE, 51 languages
    joint      joint coherence (results/joint), as answered
    choice     cardinality K = 4, 16, 77, 150 (results/cardinality)
Metrics: merge.metrics' ECE (15 bins, top-label confidence), Brier, log loss, and merge's AURC and
risk at coverage (the error rate of the most confident answers when the rest defer), and split
conformal prediction sets (LAC: a label is in the set when 1 - p(label) is at most the
calibration half's conformal quantile) at 90% and 95%: coverage and mean set size on the other
half, averaged over 20 seeded splits. Unanswered questions are counted and left out.

    python calibration.py
"""
import os

import numpy as np

import cap

FROZEN = os.path.join(cap.HERE, "..", "results")
ALPHAS, SPLITS = (0.10, 0.05), 20


def pairs(rows, p):
    """[(gold idx, vector)] of the answered questions, and the unanswered count."""
    out, un = [], 0
    for ci, (_, qs, g) in enumerate(rows):
        for qid in qs:
            v = p.get("%d/%s" % (ci, qid))
            if v is None:
                un += 1
            else:
                out.append((g[qid]["idx"], np.asarray(v, float)))
    return out, un


def conformal(items, alpha, seed):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(items))
    cal, test = idx[: len(idx) // 2], idx[len(idx) // 2:]
    s = np.sort([1 - items[i][1][items[i][0]] for i in cal])
    n = len(s)
    q = s[min(n - 1, int(np.ceil((n + 1) * (1 - alpha))) - 1)]
    cover, size = [], []
    for i in test:
        y, v = items[i]
        inset = 1 - v <= q + 1e-12
        cover.append(bool(inset[y]))
        size.append(int(inset.sum()))
    return float(np.mean(cover)), float(np.mean(size))


def sources():
    """{who: {population: [(gold, vector)]}}, and unanswered counts."""
    S = cap.load(os.path.join(FROZEN, "states.json.gz"))
    gold = {n: [[st, qs, g] for st, qs, g in rows] for n, rows in S.items()}
    raw = {w: cap.load(os.path.join(FROZEN, w, "preds.json.gz")) for w in ("laya", "jev", "kai")
           if os.path.exists(os.path.join(FROZEN, w, "preds.json.gz"))}
    out, un = {}, {}
    for w, d in raw.items():
        for name, rows in gold.items():
            if w == "laya":
                m = cap.merge.OWN.get(name, "laya").split(":")[-1]
                p = cap.merge.routed(d, name, [[g, qs] for _, qs, g in rows]) if m == "laya" else d["models"][m][name]["p"]
            else:
                p = d["suites"].get(name, {}).get("p", {})
            pop = "td" if name == "typed_decisions" else "massive" if name.startswith("massive.") else "apps"
            its, u = pairs(rows, p)
            for k in (pop, "orig"):
                out.setdefault(w, {}).setdefault(k, []).extend(its)
                un[(w, k)] = un.get((w, k), 0) + u
    J = os.path.join(cap.RESULTS, "joint")
    jc = os.path.join(cap.CASES, "joint.json.gz")
    if os.path.exists(jc):
        rows = cap.load(jc)["joint"]
        for w in ("laya", "jev", "kai"):
            f = os.path.join(J, "%s.preds.json.gz" % w)
            if os.path.exists(f):
                its, u = pairs(rows, cap.load(f))
                out.setdefault(w, {})["joint"] = its
                un[(w, "joint")] = u
    import cardinality
    C = os.path.join(cap.RESULTS, "cardinality")
    for k in (4, 16, 77, 150):
        rows = None
        for w in ("laya", "jev", "kai"):
            f = os.path.join(C, "%s.k%d.preds.json.gz" % (w, k))
            if os.path.exists(f):
                rows = rows or cardinality.cases([k])["k%d" % k]
                its, u = pairs(rows, cap.load(f))
                out.setdefault(w, {}).setdefault("choice", []).extend(its)
                un[(w, "choice")] = un.get((w, "choice"), 0) + u
    return out, un


def main():
    src, un = sources()
    keys, detail = cap.Keys("calibration"), {}
    for w, pops in src.items():
        for pop, items in pops.items():
            m = cap.merge.metrics(items)
            m["aurc"], m["risk_at_coverage"] = cap.merge.risk_coverage(
                [float(v.max()) for _, v in items], [float(int(v.argmax()) == y) for y, v in items])
            for a in ALPHAS:
                cs = [conformal(items, a, s) for s in range(SPLITS)]
                m["conf%d.cover" % round(100 * (1 - a))] = float(np.mean([c for c, _ in cs]))
                m["conf%d.size" % round(100 * (1 - a))] = float(np.mean([z for _, z in cs]))
            m["unanswered"] = un.get((w, pop), 0)
            detail.setdefault(pop, {})[w] = m
            for f in ("n", "accuracy", "ece", "brier", "nll", "aurc", "unanswered", "conf90.cover", "conf90.size",
                      "conf95.cover", "conf95.size"):
                keys.put(w, "%s.%s" % (pop, f), m.get(f))
            for c in ("0.5", "0.75", "0.9"):
                keys.put(w, "%s.risk%d" % (pop, round(100 * float(c))), m["risk_at_coverage"].get(c))
    return cap.save("calibration", keys, detail, {"splits": SPLITS})


if __name__ == "__main__":
    main()
