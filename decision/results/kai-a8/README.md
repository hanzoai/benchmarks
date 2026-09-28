# kai-a8: Kai stage a8, from a7

Scored on the frozen harness beside Laya and Jev. In `scores.json` the backend `kai` is this checkpoint.

| | |
|---|---|
| checkpoint | `dbc:scratch/decision/runs/a8` (not published), `model.safetensors` SHA-256 `see checkpoint` |
| stage | `a8`: 1 epoch, `ordinal: false`, a7's takes plus synthetic tickets, HarmBench and JailbreakBench, rated and multiple-choice sets converted to score and choice questions; dbc + evo + dgx, 38,055 batches |
| data | build `a8-e9608077b653178d` |
| calibration | `train calibrate` on the build's calibration split |
| preds | `bench preds` on dbc |
| scores | `bench score` (merge.py's metrics) |

## Accuracy against Laya and Jev

7 won, 2 tied (within two questions of 400), 3 behind.

| suite | Kai | Laya | Jev | |
|---|---|---|---|---|
| AG News | 0.943 | **0.950** | 0.860 | behind -0.7 |
| emotion | **0.938** | 0.595 | 0.603 | win |
| Banking77 | **0.897** | 0.425 | 0.835 | win |
| support triage | 0.435 | **0.502** | 0.365 | behind -6.7 |
| email spam | 0.995 | **0.998** | 0.978 | tie |
| phishing | **0.993** | 0.983 | 0.900 | win |
| jailbreak | 0.920 | 0.705 | **0.940** | behind -2.0 |
| toxicity | **0.820** | 0.530 | 0.662 | win |
| RAG relevance | **0.690** | 0.625 | 0.620 | win |
| routing | **1.000** | 0.639 | 0.977 | win |
| typed decisions | 0.761 | **0.766** (typed ckpt) | 0.736 | tie |
| MASSIVE, 51 languages | 0.906 | 0.382 | 0.890 | win |

Typed decisions by question type (Kai / Laya typed / Jev): choice 0.722 / 0.733 / 0.732, noul 0.833 / 0.857 / 0.785, score 0.738 / 0.723 / 0.701.

## Gates

`bench gate` on 100 drawn cases a suite: Laya reject (harness/app.support_triage); Jev reject (harness/app.moderation_toxicity, harness/typed_decisions, harness/massive.en, harness/massive.he, harness/massive.hu, harness/massive.it, harness/massive.ka, harness/massive.km, harness/massive.ko, harness/massive.ml, harness/massive.sv, harness/massive.ta, harness/massive.te, harness/massive.tr).

## By training sibling

`harness/siblings.py` over the a3 build's barrier (see `../kai-a4`):

```
items 400, with a sibling 0, without 400
```

## Acceptance against a6 and a7

Reject: support triage 0.435, jailbreak 0.920, typed decisions 0.761 and AG News 0.943 are each under their floor (0.505, 0.942, 0.768, 0.951), and Banking77 0.897 falls 2.5 points under a6 and 1.0 under a7 (0.5 allowed). Toxicity +1.7 and RAG relevance +1.5 over a7. The next stage starts from a7 without a8's broad additions.
