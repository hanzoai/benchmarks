# decision

Typed-decision benchmarks: Kai, Laya and Jev on identical questions.

## Harness

The questions come from the Laya 0.3.20 harness builders (`research/scripts/bench_apps.py` and `bench_local.py`), used unchanged. The seed is 13.

| Suite | Size |
|---|---|
| Application suites (10) | 400 cases each |
| Typed decisions (`LocalLLaMA/typed-decisions`, test split) | 400 cases, 2,000 decisions |
| MASSIVE intent | 51 languages × 100 utterances, 20 options each |

All backends are scored by the harness's metric functions, copied verbatim into `merge.py`. A question with no answer counts as unanswered, not wrong.

```sh
export LAYA_SRC=/path/to/laya          # github.com/NandhaKishorM/laya @ 0.3.20
uv run --python 3.11 --with torch --with pandas --with pyarrow --with datasets --with "$LAYA_SRC" \
  python harness/three_way.py kai      # reference runtime, CPU f32
uv run ... python harness/three_way.py jev   # typesafe/jev-1.13 via OpenRouter; key in harness/.or_key
uv run ... python harness/states.py          # results/states.json.gz: every case with its state
uv run --with numpy python harness/merge.py  # results/scores.json and results/table.md
uv run --with numpy python -m unittest discover -s harness   # merge.py's metrics on hand-computed cases
```

Kai is run by `bench` in `hanzoai/decision`, on the same states:

```sh
bench preds --model <dir | owner/name[@rev]> --states results/states.json.gz --out results/kai/preds.json.gz
bench speed --model <dir | owner/name[@rev]> --states results/states.json.gz --out speed.json
```

## Results

| Path | Backend | Weights / model |
|---|---|---|
| `results/laya/` | Laya 0.3.20 reference runtime, CPU f32 | `hanzoai/kai-1@b50502c2`; the SHA-256 of all three `model.safetensors` equals `convaiinnovations/laya@55cf4c4e`, so these are Laya's results |
| `results/jev/` | OpenRouter Decisions API | `typesafe/jev-1.13`, served as `typesafe/jev-1.13-20260917`, 2026-09-24; the full run cost $0.25 |
| `results/questions.json.gz` | the question set | every question with its gold label, in harness order |
| `results/states.json.gz` | the question set with states | `[state, questions, gold]` per case, in harness order; `harness/states.py` writes it from the same builders and checks it reproduces `questions.json.gz` |
| `results/laya/preds.json.gz` | Laya 0.3.20 reference runtime, CPU f32 | `three_way.py kai` on all 62 suites: every question under each kai-1 checkpoint, and the checkpoint Laya's router picks per case |
| `results/kai/preds.json.gz` | Kai, hanzo-ml | `bench preds`: one factorized Kai checkpoint's probability vectors; `merge.py` scores it when present |
| `results/kai-en/` | Kai factorized head, English baseline (not Kai), hanzo-ml, Metal bf16 | kai-1-agent trained 2 epochs on the harness train splits in English (`hanzoai/decision` 7f735f6), calibrated on its val split; its preds, `merge.py` scores beside Laya and Jev, and `bench speed`; see its README |
| `results/scores.json`, `results/table.md` | all of the above | `merge.py`: Kai, Laya and Jev side by side on every suite, with accuracy, macro F1, ECE, Brier, log loss, risk-coverage (AURC and risk at 10–100% coverage), the rate of zero probability on gold, score MAE, and MASSIVE by language |

Laya's row in the table is the router's pick per case; its typed-decisions checkpoint, which the router does not pick, is listed beside it on typed decisions. Scoring `results/laya/preds.json.gz` through `merge.py` reproduces `results/laya/typed_decisions.json` (upstream Part B) to the fourth decimal for all three checkpoints. Kai checkpoints trained in Rust (hanzo-ml) are scored against these baselines on the same question set.
