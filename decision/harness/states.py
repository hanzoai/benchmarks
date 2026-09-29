"""The harness's evaluation cases with their states: results/states.json.gz.

{suite: [[state, questions, gold], ...]}, from three_way.py suites(). Dropping the states gives
results/questions.json.gz exactly; the script checks that. Kai's Rust bench reads this file
(`bench preds`, `bench speed`).

    LAYA_SRC=/path/to/laya uv run --python 3.11 --with torch --with pandas --with pyarrow \\
      --with datasets --with "$LAYA_SRC" python harness/states.py
"""
import gzip, json, os
from three_way import suites
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
out = suites()
with gzip.open(os.path.join(RESULTS, "states.json.gz"), "wt") as f:
    json.dump(out, f, ensure_ascii=False)
frozen = json.load(gzip.open(os.path.join(RESULTS, "questions.json.gz")))
mine = {n: [[g, qs] for _, qs, g in rows] for n, rows in out.items()}
print("suites", len(mine), "match", json.dumps(mine, sort_keys=True) == json.dumps(frozen, sort_keys=True))
