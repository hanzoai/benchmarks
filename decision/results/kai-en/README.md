# kai-en: the English baseline of Kai's factorized head

Not Kai: the factorized option head trained in Rust (`hanzoai/decision`), in English only,
scored on the frozen harness. In `scores.json` and `table.md` the backend `kai` is this checkpoint.

| | |
|---|---|
| checkpoint | `dbc:scratch/kai/runs/en` (not published), `model.safetensors` SHA-256 `b7977f40c29713491b6e41439b9b61c1579b9a21e2a300342cc50230f3833a4d` |
| init | `hanzoai/kai-1-agent@e3e41649` (ModernBERT-large, 28 layers, d 1024); the ordinal and retrieval heads fresh |
| data | the harness suites' train splits, guarded against the harness states: 12 suites, 404,304 rows, English mix (MASSIVE `en` only) |
| fit | `hanzoai/decision` 7f735f6, `train fit`: 2 epochs, 53,322 steps, 7.9 h, Metal bf16 on dbc (M4 Max) |
| calibration | that build's `train calibrate`: one temperature per bucket, fit on the val split carved from train (11,966 rows) |
| preds | `hanzoai/decision` 19838e2, `bench preds`: Metal bf16 on dbc, 11,099 questions in 141 s |
| scores | `harness/merge.py` over `preds.json.gz` |

Files: `preds.json.gz` (harness preds format), `scores.json` and `table.md` (merge.py's output),
`checkpoint.json` (the run's spec, mixture, val, calibration and temperatures).

## Calibration

| bucket | val rows | T | log loss at T = 1 → T |
|---|---|---|---|
| choice:3-5 | 3,718 | 1.231 | 0.228 → 0.219 |
| choice:6-10 | 1,939 | 1.054 | 0.580 → 0.580 |
| choice:11-30 | 227 | 2.019 | 0.585 → 0.427 |
| choice:31+ | 488 | 1.893 | 0.575 → 0.445 |
| noul:2 | 5,418 | 1.524 | 0.397 → 0.386 |
| score:* | 176 | 8.000 (bound) | 20.93 → 17.85 |

The score head (cumulative link) is not learned: its temperature sits at the search bound, val
log loss near 18.

## Harness

Accuracy, Brier, ECE and the share of answers giving gold a probability under 1e-6, as
kai-en / Laya / Jev. Laya is the router's pick per case; on typed decisions it is
`laya:typed-decisions` (kai-1-agent, this run's init).

| suite | accuracy | Brier | ECE | P(gold)≈0 |
|---|---|---|---|---|
| jev.ag_news | 0.940 / 0.950 / 0.860 | 0.091 / 0.081 / 0.232 | 0.025 / 0.032 / 0.102 | 0.000 / 0.000 / 0.058 |
| jev.emotion | 0.932 / 0.595 / 0.603 | 0.091 / 0.696 / 0.646 | 0.026 / 0.306 / 0.280 | 0.000 / 0.000 / 0.142 |
| jev.banking77_full | 0.917 / 0.425 / 0.835 | 0.128 / 0.925 / 0.257 | 0.030 / 0.381 / 0.073 | 0.005 / 0.098 / 0.035 |
| app.support_triage | 0.440 / 0.502 / 0.365 | 0.686 / 0.644 / 1.056 | 0.089 / 0.091 / 0.483 | 0.000 / 0.000 / 0.335 |
| app.email_spam | 1.000 / 0.998 / 0.978 | 0.000 / 0.005 / 0.038 | 0.004 / 0.011 / 0.060 | 0.000 / 0.000 / 0.000 |
| app.phishing | 0.983 / 0.983 / 0.900 | 0.031 / 0.026 / 0.152 | 0.015 / 0.010 / 0.039 | 0.000 / 0.000 / 0.000 |
| app.guardrails_jailbreak | 0.917 / 0.705 / 0.940 | 0.153 / 0.543 / 0.104 | 0.073 / 0.262 / 0.047 | 0.000 / 0.003 / 0.000 |
| app.moderation_toxicity | 0.840 / 0.530 / 0.662 | 0.283 / 0.602 / 0.432 | 0.130 / 0.297 / 0.177 | 0.000 / 0.000 / 0.000 |
| app.rag_relevance | 0.682 / 0.625 / 0.620 | 0.403 / 0.466 / 0.628 | 0.064 / 0.117 / 0.279 | 0.000 / 0.000 / 0.000 |
| app.model_routing_domain | 1.000 / 0.639 / 0.977 | 0.000 / 0.494 / 0.040 | 0.001 / 0.089 / 0.014 | 0.000 / 0.000 / 0.000 |
| typed_decisions | 0.574 / 0.766 / 0.736 | 0.810 / 0.400 / 0.366 | 0.392 / 0.213 / 0.047 | 0.292 / 0.000 / 0.003 |
| massive.en | 0.890 / 0.820 / 0.920 | 0.170 / 0.288 / 0.108 | 0.079 / 0.138 / 0.025 | 0.000 / 0.020 / 0.020 |
| MASSIVE, 51 langs, macro | 0.192 / 0.382 / 0.890 | 0.918 / 0.987 / 0.161 | 0.151 / 0.418 / 0.064 | 0.000 / 0.030 / 0.018 |

- Typed decisions by question type, kai-en / kai-1-agent / Jev: choice 0.715 / 0.733 / 0.732,
  noul 0.838 / 0.857 / 0.785, score 0.269 / 0.723 / 0.701 (score MAE 1.366 / 0.242 / 0.391). The
  score head accounts for the loss: 584 of its 800 answers give gold under 1e-6, and no choice or
  noul answer does.
- MASSIVE: English 0.890 (Laya 0.820, Jev 0.920); the other 50 languages 0.178 macro, as an
  English-only encoder does (Laya routes them to its multilingual checkpoint: 0.373).
- Above Laya on emotion, Banking77, guardrails, toxicity, RAG relevance and routing; within 0.01
  on AG News, spam and phishing; below on support triage (0.440 against 0.502). ECE at most
  0.089 on every app suite but toxicity (0.130).
