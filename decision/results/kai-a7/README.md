# kai-a7: Kai stage a7, from a6

Scored on the frozen harness beside Laya and Jev. In `scores.json` the backend `kai` is this checkpoint.

| | |
|---|---|
| checkpoint | `dbc:scratch/decision/runs/a7` (not published), `model.safetensors` SHA-256 `see checkpoint` |
| stage | `a7`: 1 epoch, `ordinal: false`, AG News whole, support triage x2, jailbreak x2 balanced by class, typed x10 on the official split, MASSIVE 300k, score questions as a choice over their levels with the ranked probability score; dbc + evo + dgx, 30,928 batches |
| data | build `a5-eb438a72b2fc6853` |
| calibration | `train calibrate` on the build's calibration split |
| preds | `bench preds` on dbc |
| scores | `bench score` (merge.py's metrics) |

## Accuracy against Laya and Jev

7 won, 1 tied (within two questions of 400), 4 behind.

| suite | Kai | Laya | Jev | |
|---|---|---|---|---|
| AG News | 0.943 | **0.950** | 0.860 | behind -0.7 |
| emotion | **0.935** | 0.595 | 0.603 | win |
| Banking77 | **0.907** | 0.425 | 0.835 | win |
| support triage | 0.443 | **0.502** | 0.365 | behind -6.0 |
| email spam | 0.998 | **0.998** | 0.978 | tie |
| phishing | **0.990** | 0.983 | 0.900 | win |
| jailbreak | 0.920 | 0.705 | **0.940** | behind -2.0 |
| toxicity | **0.802** | 0.530 | 0.662 | win |
| RAG relevance | **0.675** | 0.625 | 0.620 | win |
| routing | **1.000** | 0.639 | 0.977 | win |
| typed decisions | 0.759 | **0.766** (typed ckpt) | 0.736 | behind -0.7 |
| MASSIVE, 51 languages | 0.909 | 0.382 | 0.890 | win |

Typed decisions by question type (Kai / Laya typed / Jev): choice 0.723 / 0.733 / 0.732, noul 0.835 / 0.857 / 0.785, score 0.729 / 0.723 / 0.701.

## Gates

`bench gate` on 100 drawn cases a suite: Laya reject (harness/app.support_triage); Jev reject (harness/app.moderation_toxicity, harness/typed_decisions, harness/massive.de, harness/massive.he, harness/massive.hi, harness/massive.hu, harness/massive.it, harness/massive.ka, harness/massive.ko, harness/massive.ml, harness/massive.ro, harness/massive.ta, harness/massive.te).

## By training sibling

`harness/siblings.py` over the a3 build's barrier (see `../kai-a4`):

```
items 400, with a sibling 0, without 400
```

## Acceptance against a6

Reject: Banking77 0.907 against a6's 0.922 (-1.5; one point allowed). Every other a6 win holds within a point; RAG relevance +2.3.
