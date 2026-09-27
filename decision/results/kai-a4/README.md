# kai-a4: Kai stage a4, 2 epochs, mmBERT-base from Laya multilingual

Scored on the frozen harness beside Laya and Jev. In `scores.json` and `table.md` the backend `kai` is this checkpoint.

| | |
|---|---|
| checkpoint | `dbc:scratch/decision/runs/a4` (not published), `model.safetensors` SHA-256 `dcd35aa61f0123063d366cccde37f8fc052c6c4be04a80941124410113f4b54e` |
| init | `hanzoai/kai-1-multilingual@3119843b` (mmBERT-base) |
| data | build `a3-d7a9a437cf484811`. The barrier caught 547 of 1,185 typed-decisions train records (near-duplicates of test states); Laya's typed checkpoint trained on all of them |
| fit | stage `a4`: 2 epochs, 32,681 batches, dbc (Metal bf16) and evo (ROCm bf16, `--scale 0.25`) |
| calibration | `train calibrate` on the build's calibration split (`kai.json`; the original is `kai.json.orig` on dbc) |
| preds | `bench preds` (dbc `target-score` build), 11,099 questions |
| scores | `harness/merge.py`, unchanged, run in a scratch tree with `preds.json.gz` as `results/kai/preds.json.gz` |

## Accuracy against Laya and Jev

| suite | Kai | Laya | Jev |
|---|---|---|---|
| emotion | **0.938** | 0.595 | 0.603 |
| Banking77 | **0.885** | 0.425 | 0.835 |
| phishing | **0.990** | 0.983 | 0.900 |
| toxicity | **0.833** | 0.530 | 0.662 |
| RAG relevance | **0.672** | 0.625 | 0.620 |
| routing | **1.000** | 0.639 | 0.977 |
| AG News | 0.935 | **0.950** | 0.860 |
| email spam | 0.995 | **0.998** | 0.978 |
| support triage | 0.453 | **0.502** | 0.365 |
| jailbreak | 0.907 | 0.705 | **0.940** |
| MASSIVE, 51 languages | 0.858 | 0.382 | **0.890** |
| typed decisions | 0.523 | 0.766 (Laya's typed checkpoint) | 0.736 |

Typed decisions by question type (Kai / Laya typed / Jev): choice 0.518 / 0.733 / 0.732, noul 0.667 / 0.857 / 0.785, score 0.419 / 0.723 / 0.701.
