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
uv run --with numpy python harness/merge.py
```

## Results

| Path | Backend | Weights / model |
|---|---|---|
| `results/laya/` | Laya 0.3.20 reference runtime, CPU f32 | `hanzoai/kai-1@b50502c2`; the SHA-256 of all three `model.safetensors` equals `convaiinnovations/laya@55cf4c4e`, so these are Laya's results |
| `results/jev/` | OpenRouter Decisions API | `typesafe/jev-1.13`, served as `typesafe/jev-1.13-20260917`, 2026-09-24; the full run cost $0.25 |
| `results/questions.json.gz` | the question set | every question with its gold label, in harness order |

Kai checkpoints trained in Rust (hanzo-ml) are scored against these baselines on the same question set.
