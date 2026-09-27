# kai-a5: Kai stage a5, one epoch on from a4

Scored on the frozen harness beside Laya and Jev. In `scores.json` and `table.md` the backend `kai` is this checkpoint.

| | |
|---|---|
| checkpoint | `dbc:scratch/decision/runs/a5` (not published), `model.safetensors` SHA-256 `df1c16a2fef7ec93f2b34a6a194f6dc3c2eee70e936473b802151543c5d46e83` |
| init | `runs/a4` (see `../kai-a4`) |
| data | build `a5-eb438a72b2fc6853`, 3,693,938 train rows. Typed decisions' train split is official: checked for exact copies and keys only, so all 1,185 records train (a4's build dropped 547 near duplicates) |
| fit | stage `a5` (`hanzoai/decision` bcdc01d): 1 epoch, 23,788 batches, dbc (Metal bf16) with dgx (CUDA bf16) and evo (ROCm bf16, `--scale 0.25`) joining at round 3 |
| calibration | `train calibrate` on the build's calibration split |
| preds | `bench preds` on dbc, Metal bf16, 11,099 questions |
| scores | `harness/merge.py`, unchanged, in a scratch tree with `preds.json.gz` as `results/kai/preds.json.gz` |

## Accuracy against Laya and Jev

| suite | a4 | Kai a5 | Laya | Jev |
|---|---|---|---|---|
| AG News | 0.935 | **0.950** | **0.950** | 0.860 |
| emotion | 0.938 | **0.925** | 0.595 | 0.603 |
| Banking77 | 0.885 | **0.907** | 0.425 | 0.835 |
| support triage | 0.453 | **0.490** | 0.502 (trained on these rows) | 0.365 |
| email spam | 0.995 | 0.995 | **0.998** | 0.978 |
| phishing | 0.990 | **0.990** | 0.983 (trained on these rows) | 0.900 |
| jailbreak | 0.907 | 0.915 | 0.705 | **0.940** |
| toxicity | 0.833 | **0.820** | 0.530 | 0.662 |
| RAG relevance | 0.672 | **0.667** | 0.625 | 0.620 |
| routing | 1.000 | **1.000** | 0.639 | 0.977 |
| typed decisions | 0.523 | 0.705 | **0.766** (Laya's typed checkpoint) | 0.736 |
| MASSIVE, 51 languages | 0.858 | 0.888 | 0.382 | **0.890** |
| macro, 11 suites | 0.830 | **0.851** | 0.702 | 0.770 |

Best of three, among backends that did not train on a suite's rows: Kai 8, Laya 3, Jev 2 of 12 (AG News a tie).

## Gates

`bench gate` on 100 drawn cases a suite (`gate.laya.json`, `gate.jev.json`): both reject. Against
Laya: AG News on calibration (ECE 0.097 against 0.050 at the same accuracy), support triage
(0.39 against 0.48) and typed decisions. Against Jev: typed decisions and 15 of the 51 MASSIVE
languages.

## By training sibling

`harness/siblings.py` over the a3 build's barrier (see `../kai-a4`): a5 trains on the official
typed split, siblings included, so the split no longer costs it. Accuracy over every question of
the state, choice / noul / score in parentheses:

| | all 400 | without a sibling (235) | with a sibling (165) |
|---|---|---|---|
| Kai a5 | 0.705 (0.713 / 0.833 / 0.603) | 0.697 (0.741 / 0.796 / 0.589) | 0.716 (0.676 / 0.888 / 0.621) |
| Laya typed | 0.766 (0.733 / 0.857 / 0.723) | 0.773 (0.744 / 0.835 / 0.747) | 0.756 (0.719 / 0.888 / 0.688) |
| Jev | 0.736 (0.732 / 0.785 / 0.701) | 0.770 (0.784 / 0.765 / 0.764) | 0.686 (0.660 / 0.814 / 0.612) |

What remains is the score head: 0.589 against Laya's 0.747 on the clean half, with choice within
a point and noul above Jev.

