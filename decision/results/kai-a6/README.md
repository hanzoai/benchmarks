# kai-a6: Kai stage a6, from a5

Scored on the frozen harness beside Laya and Jev. In `scores.json` the backend `kai` is this checkpoint.

| | |
|---|---|
| checkpoint | `dbc:scratch/decision/runs/a6` (not published), `model.safetensors` SHA-256 `see checkpoint` |
| stage | `a6`: 1 epoch, `ordinal: false`, typed x10 on the official split, support triage x5, jailbreak x2, all spam rows, MASSIVE 300k, score questions as a choice over their levels with the ranked probability score; dbc + evo + dgx, 30,615 batches |
| data | build `a5-eb438a72b2fc6853` |
| calibration | `train calibrate` on the build's calibration split |
| preds | `bench preds` on dbc |
| scores | `bench score` (merge.py's metrics) |

## Accuracy against Laya and Jev

7 won, 1 tied (within two questions of 400), 4 behind.

| suite | Kai | Laya | Jev | |
|---|---|---|---|---|
| AG News | 0.940 | **0.950** | 0.860 | behind -1.0 |
| emotion | **0.935** | 0.595 | 0.603 | win |
| Banking77 | **0.922** | 0.425 | 0.835 | win |
| support triage | 0.435 | **0.502** | 0.365 | behind -6.7 |
| email spam | 0.998 | **0.998** | 0.978 | tie |
| phishing | **0.993** | 0.983 | 0.900 | win |
| jailbreak | 0.920 | 0.705 | **0.940** | behind -2.0 |
| toxicity | **0.807** | 0.530 | 0.662 | win |
| RAG relevance | **0.652** | 0.625 | 0.620 | win |
| routing | **1.000** | 0.639 | 0.977 | win |
| typed decisions | 0.750 | **0.766** (typed ckpt) | 0.736 | behind -1.6 |
| MASSIVE, 51 languages | 0.910 | 0.382 | 0.890 | win |

Typed decisions by question type (Kai / Laya typed / Jev): choice 0.722 / 0.733 / 0.732, noul 0.830 / 0.857 / 0.785, score 0.711 / 0.723 / 0.701.

## Gates

`bench gate` on 100 drawn cases a suite: Laya reject (harness/app.support_triage); Jev reject (harness/app.guardrails_jailbreak, harness/app.moderation_toxicity, harness/typed_decisions, harness/massive.de, harness/massive.en, harness/massive.hi, harness/massive.hu, harness/massive.it, harness/massive.ka, harness/massive.ml, harness/massive.te).

## By training sibling

`harness/siblings.py` over the a3 build's barrier (see `../kai-a4`):

```
items 400, with a sibling 165, without 235
kai-a6                 all (0.75, {'choice': 0.722, 'noul': 0.83, 'score': 0.711})   without siblings (0.734, {'choice': 0.749, 'noul': 0.782, 'score': 0.685})   with (0.773, {'choice': 0.684, 'noul': 0.901, 'score': 0.748})
laya-typed             all (0.766, {'choice': 0.733, 'noul': 0.857, 'score': 0.723})   without siblings (0.773, {'choice': 0.744, 'noul': 0.835, 'score': 0.747})   with (0.756, {'choice': 0.719, 'noul': 0.888, 'score': 0.688})
jev                    all (0.736, {'choice': 0.732, 'noul': 0.785, 'score': 0.701})   without siblings (0.77, {'choice': 0.784, 'noul': 0.765, 'score': 0.764})   with (0.686, {'choice': 0.66, 'noul': 0.814, 'score': 0.612})
```
