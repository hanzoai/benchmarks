"""Score every backend side by side with the harness's own metric code.

Reads the committed results: questions.json.gz (gold), laya/preds.json.gz (three_way.py kai:
the three kai-1 checkpoints and the router's choice per case), jev/preds.json.gz, and
kai/preds.json.gz when present (Kai's Rust bench, `bench preds`). Writes results/scores.json and
results/table.md.

ece_score, macro_f1 and metrics are copied verbatim from research/scripts/bench_local.py, so a
number here means what it means in the upstream report. A question a backend did not answer
(a dropped sequence, an API error) counts as unanswered, not as wrong; the count is reported.
"""
import gzip
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")


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
    m["aurc"], m["risk_at_coverage"] = risk_coverage(
        [float(np.max(p)) for _, p in answered],
        [float(int(np.argmax(p)) == g["idx"]) for g, p in answered])
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


# --- added: selective prediction, backends side by side, MASSIVE by language ----------
COVERAGE = (0.1, 0.25, 0.5, 0.75, 0.9, 1.0)


def risk_coverage(conf, corr):
    """AURC, and the error rate of the most confident answers at each coverage.

    Answers are taken by confidence, highest first; answers tied in confidence are taken
    together, so inside a tie the error accrues at the tie's mean rate. Risk at coverage c is
    the error rate of the first max(1, floor(c n)); AURC is the mean risk over k/n, k = 1..n.
    """
    conf, corr = np.asarray(conf, float), np.asarray(corr, float)
    n = len(conf)
    if not n:
        return None, {}
    order = np.argsort(-conf, kind="stable")
    c, err = conf[order], 1 - corr[order]
    cum, before = np.empty(n), 0.0
    starts = np.r_[0, np.flatnonzero(np.diff(c)) + 1]
    for s, t in zip(starts, np.r_[starts[1:], n]):
        cum[s:t] = before + err[s:t].mean() * np.arange(1, t - s + 1)
        before += err[s:t].sum()
    risk = cum / np.arange(1, n + 1)
    return round(float(risk.mean()), 4), {str(k): round(float(risk[max(1, int(k * n)) - 1]), 4)
                                          for k in COVERAGE}


LAYA = ("english", "multilingual", "typed-decisions")
# the kai-1 checkpoint Laya ships for a suite, which its router does not pick
OWN = {"typed_decisions": "laya:typed-decisions"}
SHOWN = ("kai", "laya", "jev")
PAIRS = (("kai", "laya"), ("kai", "jev"), ("laya", "jev"))
# the metrics a MASSIVE summary averages over languages, in table order
MACRO = ("accuracy", "macro_f1", "ece", "brier", "nll", "aurc", "acc_at_50_coverage", "zero_prob")


def read(path):
    """A committed results file, or None when it is not there."""
    path = os.path.join(RESULTS, path)
    return json.load(gzip.open(path)) if os.path.exists(path) else None


def routed(laya, name, gold):
    """Each case answered by the kai-1 checkpoint Laya's router chose for it."""
    out = {}
    for ci, (_, qs) in enumerate(gold):
        p = laya["models"][laya["route"][name][ci]][name]["p"]
        for qid in qs:
            out["%d/%s" % (ci, qid)] = p.get("%d/%s" % (ci, qid))
    return out


def backends(name, gold, kai, laya, jev):
    """{backend: preds} for one suite: kai, laya (routed), each kai-1 checkpoint, jev."""
    out = {}
    if kai and name in kai["suites"]:
        out["kai"] = kai["suites"][name]["p"]
    if laya and name in laya["route"]:
        out["laya"] = routed(laya, name, gold)
        for m in LAYA:
            if name in laya["models"].get(m, {}):
                out["laya:" + m] = laya["models"][m][name]["p"]
    if jev and name in jev["suites"]:
        out["jev"] = jev["suites"][name]["p"]
    return out


def massive(suites):
    """Per backend, MASSIVE's languages summarized: every metric in MACRO averaged over them."""
    langs = {n.split(".", 1)[1]: r for n, r in suites.items() if n.startswith("massive.")}
    mean = lambda v: round(float(np.mean(v)), 4) if v else None
    out = {}
    for who in sorted({w for r in langs.values() for w in r if w != "agreement"}):
        rs = {lg: r[who] for lg, r in langs.items() if who in r and r[who].get("n")}
        if not rs:
            continue
        out[who] = {"languages": len(rs), "n": sum(r["n"] for r in rs.values()),
                    "unanswered": sum(r["unanswered"] for r in rs.values()),
                    "questions": sum(r["questions"] for r in rs.values()),
                    "english": mean([r["accuracy"] for lg, r in rs.items() if lg.startswith("en")]),
                    "non_english_macro": mean([r["accuracy"] for lg, r in rs.items() if not lg.startswith("en")]),
                    "above_3x_random": int(sum(1 for r in rs.values() if r["accuracy"] > 3.0 / 20)),
                    "risk_at_coverage": {str(k): mean([r["risk_at_coverage"][str(k)] for r in rs.values()])
                                         for k in COVERAGE}}
        out[who].update({"macro_" + k: mean([r[k] for r in rs.values()]) for k in MACRO})
    return out


def f(v):
    return "–" if v is None else "%.3f" % v


def shown(name, row):
    """The backends a table shows for a suite, in column order."""
    return [w for w in ("kai", "laya", OWN.get(name), "jev") if w in row]


def table(out):
    """The scores as markdown."""
    suites, mass = out["suites"], out["massive_summary"]
    lines = ["# decision: Kai, Laya and Jev on the frozen harness", "",
             "Written by `harness/merge.py` from the committed results; every backend is scored by the same functions.", ""]
    for who, s in out["sources"].items():
        lines.append("- **%s**: %s" % (who, ", ".join("%s `%s`" % (k, v) for k, v in s.items())))
    lines += ["- **laya** answers each case with the kai-1 checkpoint Laya 0.3.20's router picked for it; "
              "**laya:typed-decisions** is the checkpoint Laya ships for typed decisions, which the router does not pick.",
              "", "## Every suite", ""]
    cols = ("suite", "backend", "answered", "acc", "macro F1", "ECE", "Brier", "log loss", "AURC", "acc@50%",
            "P(gold)≈0", "score MAE")
    lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for name, row in suites.items():
        if not name.startswith("massive."):
            for w in shown(name, row):
                m = row[w]
                lines.append("| %s | %s | %d/%d | %s |" % (name, w, m["n"], m["questions"], " | ".join(
                    f(m.get(k)) for k in MACRO + ("score_mae",))))
    for w in SHOWN:
        if w in mass:
            m = mass[w]
            lines.append("| MASSIVE, %d langs, macro | %s | %d/%d | %s | – |" % (
                m["languages"], w, m["n"], m["questions"], " | ".join(f(m["macro_" + k]) for k in MACRO)))
    lines += ["", "## Risk at coverage", "",
              "Error rate of the most confident answers, ties in confidence taken together.", "",
              "| suite | backend | " + " | ".join("%d%%" % round(100 * k) for k in COVERAGE) + " |",
              "|" + "---|" * (2 + len(COVERAGE))]
    for name, row in suites.items():
        if not name.startswith("massive."):
            for w in shown(name, row):
                lines.append("| %s | %s | %s |" % (name, w, " | ".join(
                    f(row[w]["risk_at_coverage"].get(str(k))) for k in COVERAGE)))
    for w in SHOWN:
        if w in mass:
            lines.append("| MASSIVE, macro | %s | %s |" % (w, " | ".join(
                f(mass[w]["risk_at_coverage"][str(k)]) for k in COVERAGE)))
    who = [w for w in SHOWN if w in mass]
    per = (("accuracy", "acc"), ("ece", "ECE"), ("nll", "log loss"))
    lines += ["", "## MASSIVE by language", "",
              "| language | " + " | ".join("%s %s" % (w, label) for _, label in per for w in who) + " |",
              "|" + "---|" * (1 + len(per) * len(who))]
    for name, row in suites.items():
        if name.startswith("massive."):
            lines.append("| %s | %s |" % (name.split(".", 1)[1], " | ".join(
                f(row[w][k]) if w in row else "–" for k, _ in per for w in who)))
    lines.append("| macro | %s |" % " | ".join(f(mass[w]["macro_" + k]) for k, _ in per for w in who))
    lines += ["", "| MASSIVE | " + " | ".join(who) + " |", "|" + "---|" * (1 + len(who)),
              "| English | %s |" % " | ".join(f(mass[w]["english"]) for w in who),
              "| other languages, macro | %s |" % " | ".join(f(mass[w]["non_english_macro"]) for w in who),
              "| languages above 3× random | %s |" % " | ".join(str(mass[w]["above_3x_random"]) for w in who)]
    lat = out.get("jev_sequential_latency") or {}
    if lat.get("n"):
        lines += ["", "Jev: %d sequential calls, p50 %s ms, p95 %s ms; the whole run cost $%s." % (
            lat["n"], lat["p50_ms"], lat["p95_ms"], out["jev_total_cost_usd"])]
    lines += ["", "## Metrics", "",
              "- acc, macro F1, ECE (15 bins, top-label confidence), Brier (summed over options), log loss "
              "(natural log, p floored at 1e-12), acc@50% (accuracy of the more confident half): upstream "
              "`bench_local.py`, verbatim.",
              "- AURC: area under the risk-coverage curve, the mean error rate over coverages k/n; lower is better.",
              "- P(gold)≈0: share of answers that give the gold option a probability under 1e-6.",
              "- score MAE: typed decisions' score questions, |expected level − the teacher's mean level|.",
              "- answered: questions with a probability vector; an unanswered question is not scored as wrong."]
    return "\n".join(lines) + "\n"


def main():
    gold = read("questions.json.gz")
    kai, laya, jev = read("kai/preds.json.gz"), read("laya/preds.json.gz"), read("jev/preds.json.gz")
    out = {"sources": {}, "suites": {}}
    if kai:
        out["sources"]["kai"] = {k: kai[k] for k in ("model", "weights", "device", "dtype")}
    if laya:
        out["sources"]["laya"] = {k: laya[k] for k in ("bundle", "revision", "runtime", "device", "dtype")}
    if jev:
        out["sources"]["jev"] = {"model": jev["model"],
                                 "served": sorted({m for s in jev["suites"].values() for m in s["served"]})}
    for name, g in gold.items():
        preds = backends(name, g, kai, laya, jev)
        row = {w: score(g, p, name == "typed_decisions") for w, p in preds.items()}
        if "jev" in row:
            js = jev["suites"][name]
            row["jev"].update({"latency_p50_ms": pct(js["latency_ms"], 50), "latency_p95_ms": pct(js["latency_ms"], 95),
                               "cost_usd": round(js["cost_usd"], 5), "input_tokens": js["input_tokens"],
                               "served": js["served"], "n_errors": js["n_errors"]})
        row["agreement"] = {"%s~%s" % (a, b): agreement(g, preds[a], preds[b])
                            for a, b in PAIRS if a in preds and b in preds}
        out["suites"][name] = row
    if jev:
        lat = jev.get("sequential_latency_ms") or []
        out["jev_sequential_latency"] = {"n": len(lat), "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95)}
        out["jev_total_cost_usd"] = round(sum(s["cost_usd"] for s in jev["suites"].values()), 4)
    out["massive_summary"] = massive(out["suites"])
    json.dump(out, open(os.path.join(RESULTS, "scores.json"), "w"), indent=1)
    md = table(out)
    open(os.path.join(RESULTS, "table.md"), "w").write(md)
    print(md)


if __name__ == "__main__":
    main()
