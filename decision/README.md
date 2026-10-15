# decision

Typed-decision benchmarks: Kai and Jev on identical questions.

[`SUITE.md`](SUITE.md) is the Decision Suite hanzo.ai publishes: sixteen rows of Kai against Jev, each with its result file here and the command that reads it again. Its other parts live beside the harness: [`capability/`](capability/) (choosing among many options), [`stability/`](stability/) (the same request three times) and [`jailbreak-suite/`](jailbreak-suite/) (17 public jailbreak and injection sets).

## Harness

The questions come from the upstream harness builders (`research/scripts/bench_apps.py` and `bench_local.py`, at the release `harness/three_way.py` pins), used unchanged. The seed is 13.

| Suite | Size |
|---|---|
| Application suites (10) | 400 cases each |
| Typed decisions (`LocalLLaMA/typed-decisions`, test split) | 400 cases, 2,000 decisions |
| MASSIVE intent | 51 languages × 100 utterances, 20 options each |

Support triage and phishing draw their rows from their datasets' train splits (`Tobi-Bueck/customer-support-tickets`, `zefang-liu/phishing-email-dataset`), so a model trained on those splits has read them.

All backends are scored by the harness's metric functions, copied verbatim into `merge.py`. A question with no answer counts as unanswered, not wrong.

```sh
uv run --with numpy python harness/merge.py --kai results/kai-1/preds.json.gz --out results/kai-1   # kai-1's record
uv run --with numpy python -m unittest discover -s harness   # merge.py's metrics on hand-computed cases
python3 harness/digest.py results/kai-1/preds.json.gz        # each suite's digest, as its research run's notes record it
```

Kai answers the same states over HTTP, at api.hanzo.ai or a local `kai serve`; Jev is scored from its recorded preds (`--jev recorded`, the default), never called:

```sh
HANZO_API_KEY=... python3 harness/run_kai.py [--limit 5] [--url http://127.0.0.1:8080]   # results/kai/preds.json.gz
uv run --with numpy python harness/merge.py   # results/scores.json and results/table.md, or --out <dir>
```

`harness/states.py` rebuilds `results/states.json.gz` from the upstream builders and checks it against `questions.json.gz`; `harness/three_way.py jev` is the runner that recorded Jev's answers (`typesafe/jev-1.13` through OpenRouter, key in `harness/.or_key`). Each script's docstring gives its command and the checkout it reads.

`bench` in hanzo-inc/kai (private) runs Kai in process on the same states and scores and times it:

```sh
bench preds --model <dir | owner/name[@rev]> --states results/states.json.gz --out results/kai/preds.json.gz
bench score --harness . --kai results/kai/preds.json.gz --out results/scores.json   # merge.py's scores.json
bench cap --harness . --who kai,jev --kai <checkpoint>                               # capability/, every suite
bench speed --states results/states.json.gz --results capability/results --who kai --kai <checkpoint>
bench tex --harness . --out <paper>/kai/tables                                       # the paper's tables
```

`bench score` equals `merge.py`'s `scores.json` (7,454 of 7,461 values) except `acc_at_50_coverage` where a confidence tie straddles the half: numpy's argsort orders ties by machine, `bench` by case order (7 of 378, at most 0.025).

## Results

| Path | Backend | Weights / model |
|---|---|---|
| `results/jev/` | OpenRouter Decisions API | `typesafe/jev-1.13`, served as `typesafe/jev-1.13-20260917`; the full run cost $0.25 |
| `results/questions.json.gz` | the question set | every question with its gold label, in harness order |
| `results/states.json.gz` | the question set with states | `[state, questions, gold]` per case, in harness order; `harness/states.py` writes it from the same builders and checks it reproduces `questions.json.gz` |
| `results/kai-1/` | kai-1, CUDA BF16 | `model.safetensors` SHA-256 `0834a74f…`; its preds, and `merge.py`'s `scores.json` and `table.md` over them beside Jev: the Decision Suite's harness rows (`results/kai-1/README.md`) |
| `results/kai/preds.json.gz` | Kai over HTTP | `harness/run_kai.py`, or `bench preds`: one Kai's probability vectors; `merge.py` scores it when present (not committed) |

`table.md` sets Kai and Jev side by side on every suite, with accuracy, macro F1, ECE, Brier, log loss, risk-coverage (AURC and risk at 10–100% coverage), the rate of zero probability on gold, score MAE, and MASSIVE by language; `scores.json` holds every number it shows and the agreement between backends.
