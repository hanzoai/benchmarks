"""Typed decisions on the harness items with and without a same-wording training sibling.

    python3 siblings.py <decision/> <contamination_report.json> name=preds.json.gz[:model] ...


A sibling: a training record the contamination barrier caught as a near duplicate of the item
(the build's contamination_report.json, `catches` with suite typed_decisions). Laya's typed
checkpoint trained on those records; Kai's build dropped them.
"""
import gzip, json, sys
H, report = sys.argv[1], sys.argv[2]
q = json.load(gzip.open(f"{H}/results/questions.json.gz"))["typed_decisions"]
gold = {f"{i}/{k}": v["idx"] for i, it in enumerate(q) for k, v in it[0].items() if isinstance(v, dict) and "idx" in v}
catches = json.load(open(report))["catches"]
sib = {int(c["item"].split("/")[1]) for c in catches if c["source"] == "typed_decisions" and c["item"].startswith("typed_decisions/")}
print(f"items {len(q)}, with a sibling {len(sib)}, without {len(q) - len(sib)}")
def probs(path, model=None):
    p = json.load(gzip.open(path))
    if "models" in p: t = p["models"][model]["typed_decisions"]
    else: t = p["suites"]["typed_decisions"]
    return t[1] if isinstance(t, list) else t["p"]
def acc(pr, keep):
    keys = [k for k in gold if int(k.split("/")[0]) in keep]
    by = {}
    for k in keys:
        qn = k.split("/")[1]; typ = q[int(k.split("/")[0])][1][qn]["type"]
        ok = max(range(len(pr[k])), key=lambda j: pr[k][j]) == gold[k]
        by.setdefault(typ, []).append(ok)
    allv = [x for v in by.values() for x in v]
    return round(sum(allv) / len(allv), 3), {t: round(sum(v) / len(v), 3) for t, v in sorted(by.items())}
allitems = set(range(len(q))); clean = allitems - sib
for name, path, model in [(a.split("=")[0], a.split("=")[1].split(":")[0], (a.split("=")[1].split(":") + [None])[1]) for a in sys.argv[3:]]:
    pr = probs(path, model)
    print(f"{name:22s} all {acc(pr, allitems)}   without siblings {acc(pr, clean)}   with {acc(pr, sib)}")
