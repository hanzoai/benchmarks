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
uv run ... python harness/three_way.py kai --states held/states.json.gz --out held/laya   # any states file instead of the builders
uv run ... python harness/states.py          # results/states.json.gz: every case with its state
uv run --with numpy python harness/merge.py  # results/scores.json and results/table.md
uv run --with numpy python -m unittest discover -s harness   # merge.py's metrics on hand-computed cases
```

`bench` in `hanzoai/decision` runs Kai on the same states and scores and times all three:

```sh
bench preds --model <dir | owner/name[@rev]> --states results/states.json.gz --out results/kai/preds.json.gz
bench score --harness . --kai results/kai/preds.json.gz --out results/scores.json   # merge.py's scores.json
bench cap --harness . --who kai,laya,jev --kai <checkpoint>                          # capability/, every suite
bench speed --states results/states.json.gz --results capability/results --who kai,laya --kai <checkpoint>
bench tex --harness . --out <paper>/kai/tables                                       # the paper's tables
```

`bench score` equals `merge.py`'s `scores.json` (7,454 of 7,461 values on Kai stage A's predictions) except `acc_at_50_coverage` where a confidence tie straddles the half: numpy's argsort orders ties by machine, `bench` by case order (7 of 378, at most 0.025).

## Results

| Path | Backend | Weights / model |
|---|---|---|
| `results/laya/` | Laya 0.3.20 reference runtime, CPU f32 | `hanzoai/kai-1@b50502c2`; the SHA-256 of all three `model.safetensors` equals `convaiinnovations/laya@55cf4c4e`, so these are Laya's results |
| `results/jev/` | OpenRouter Decisions API | `typesafe/jev-1.13`, served as `typesafe/jev-1.13-20260917`; the full run cost $0.25 |
| `results/questions.json.gz` | the question set | every question with its gold label, in harness order |
| `results/states.json.gz` | the question set with states | `[state, questions, gold]` per case, in harness order; `harness/states.py` writes it from the same builders and checks it reproduces `questions.json.gz` |
| `results/laya/preds.json.gz` | Laya 0.3.20 reference runtime, CPU f32 | `three_way.py kai` on all 62 suites: every question under each kai-1 checkpoint, and the checkpoint Laya's router picks per case |
| `results/kai/preds.json.gz` | Kai, hanzo-ml | `bench preds`: one factorized Kai checkpoint's probability vectors; `merge.py` scores it when present |
| Kai's own results | Kai stages a, a4–a8 and the English baseline | kept with Kai in hanzo-inc/kai (`results/kai-*`, `held/kai-a5`, Kai's rows of `capability/results`) |
| `results/scores.json`, `results/table.md` | all of the above | `merge.py`: Kai, Laya and Jev side by side on every suite, with accuracy, macro F1, ECE, Brier, log loss, risk-coverage (AURC and risk at 10–100% coverage), the rate of zero probability on gold, score MAE, and MASSIVE by language |
| `results/r0/` | kai-1, kai-1-multilingual, Kai a4–a7 and the ties2 merge on jevlab B1, B3, B3b, with the encoder and the head taken apart | `hanzoai/decision` `forensics/`: the runtime on dgx's CPU for the lineage, a torch port of its layouts and heads for head swaps, frozen-encoder probes, CKA, massive activations, weight geometry and the open-label dev probes; see its README |
| `held/` | `held.phishing`, `held.support_triage` | the frozen `app.phishing` and `app.support_triage` questions on rows outside Laya's training data, 400 cases each, with Laya's and Kai a5's predictions; see `held/README.md` |
| `trained/overlap.json` | every headline suite | the share of its rows in the data Laya trained on; see [Trained on](#trained-on) |

Laya's row in the table is the router's pick per case; its typed-decisions checkpoint, which the router does not pick, is listed beside it on typed decisions. Scoring `results/laya/preds.json.gz` through `merge.py` reproduces `results/laya/typed_decisions.json` (upstream Part B) to the fourth decimal for all three checkpoints.

## Trained on

`trained/measure.py` compares each headline suite's rows (`results/states.json.gz`) with the training split of every dataset they are drawn from that a Laya checkpoint trained on, at a pinned revision, by `held/`'s rules: exact (equal after lowercasing and collapsing whitespace) or contained (at least half of the row's word 5-grams in one training row). Which checkpoint trained on what is hanzo-inc/kai `train/src/data/laya.rs`, from Laya's own README, BENCHMARKS.md, builders and cards; `laya-typed-decisions` is fine-tuned from `laya`, so it holds `laya`'s data too.

| Suite | Rows | Exact | Contained | Share | Compared with (train split) |
|---|---|---|---|---|---|
| AG News | 400 | 2 | 78 | 0.200 | `fancyzhx/ag_news` @ `eb185aad` |
| DAIR Emotion | 400 | | | 0 | held out |
| Banking77 | 400 | | | 0 | held out |
| Support triage | 400 | 400 | 0 | 1.000 | `Tobi-Bueck/customer-support-tickets` @ `ddf1c81a`, its three CSVs |
| Email spam | 400 | 68 | 136 | 0.510 | `SetFit/enron_spam` @ `1916f66c` |
| Phishing | 400 | 350 | 50 | 1.000 | `zefang-liu/phishing-email-dataset` @ `34085a03` |
| Jailbreak | 400 | | | 0 | held out |
| Toxicity | 400 | | | 0 | held out |
| RAG relevance | 400 | 0 | 0 | 0 | `microsoft/ms_marco` v1.1 @ `a47ee7aa`, by whole state |
| Model routing | 399 | 0 | 22 | 0.055 | `fancyzhx/ag_news` @ `eb185aad` |
| Typed decisions | 400 | 0 | 93 | 0.233 | `LocalLLaMA/typed-decisions` all @ `c76749ec` (`laya-typed-decisions` only) |
| MASSIVE, 51 languages | 5,100 | | | 0 | held out |

Support triage and phishing are drawn from the very rows Laya trained on. Model routing's 22 are among its 133 AG News rows; its GSM8K and MBPP rows are held out. Each of the 93 typed decisions shares its task and constraints with a training state whose autonomy and trace numbers differ. RAG relevance is compared as whole states, query and passage together: none of its 400 queries is a v1.1 training query, though 47 of its passages recur there under other queries. Held out means upstream reports no checkpoint trained on the dataset; `laya-multilingual` names no training sources, so nothing is known to compare it with.

`bench post` (hanzo-inc/kai) adds each share to the notes of the Laya runs whose checkpoint trained on what was compared, as `trained on <share> of the rows`; hanzo.ai/kai and /benchmarks show a dash, not a number, for a baseline at 0.01 or more on a suite.

```sh
uv run --python 3.11 --with huggingface_hub --with pyarrow python trained/measure.py   # trained/overlap.json
```
