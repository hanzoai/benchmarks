"""The harness's evaluation cases with their states: results/states.json.gz.

{suite: [[state, questions, gold], ...]}, from the same builders, seed and order as
three_way.py suites(). Dropping the states gives results/questions.json.gz exactly; the script
checks that. Kai's Rust bench reads this file (`bench preds`, `bench speed`).

    LAYA_SRC=/path/to/laya uv run --python 3.11 --with torch --with pandas --with pyarrow \\
      --with datasets --with "$LAYA_SRC" python harness/states.py
"""
import gzip, importlib.util, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
SRC = os.environ["LAYA_SRC"]  # a checkout of github.com/NandhaKishorM/laya at 0.3.20
os.environ.setdefault("USE_TF", "0"); os.environ.setdefault("BENCH_N", "400")
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
bl = module("bl", os.path.join(SRC, "research/scripts/bench_local.py"))
ba = module("ba", os.path.join(SRC, "research/scripts/bench_apps.py"))
bl.REPO = os.path.join(HERE, "data")
out = {}
ba.build()
for name, S in ba.SUITES.items():
    rows = []
    for (state, qs), g in zip(S["cases"], S["gold"]):
        (qid,) = qs.keys(); rows.append([state, qs, {qid: {"idx": g}}])
    out[name] = rows
cases, gold, wfs = bl.build_typed_decisions()
out["typed_decisions"] = [[st, qs, dict(g, **{"_wf": w})] for (st, qs), g, w in zip(cases, gold, wfs)]
for lg, (cases, gold, _) in bl.build_massive(bl.massive_languages(), 100).items():
    out["massive." + lg] = [[st, qs, {"intent": {"idx": g}}] for (st, qs), g in zip(cases, gold)]
with gzip.open(os.path.join(RESULTS, "states.json.gz"), "wt") as f:
    json.dump(out, f, ensure_ascii=False)
# the frozen file is [gold, questions]; confirm this dump reproduces it exactly
frozen = json.load(gzip.open(os.path.join(RESULTS, "questions.json.gz")))
mine = {n: [[g, qs] for _, qs, g in rows] for n, rows in out.items()}
print("suites", len(mine), "match", json.dumps(mine, sort_keys=True) == json.dumps(frozen, sort_keys=True))
