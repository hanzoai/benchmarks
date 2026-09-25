# decision: Kai, Laya and Jev on the frozen harness

Written by `harness/merge.py` from the committed results; every backend is scored by the same functions.

- **laya**: bundle `hanzoai/kai-1`, revision `b50502c28537df49a3621f6fa543f9e8521e8a9c`, runtime `laya 0.3.20`, device `cpu`, dtype `f32`
- **jev**: model `typesafe/jev-1.13`, served `['typesafe/jev-1.13-20260917']`
- **laya** answers each case with the kai-1 checkpoint Laya 0.3.20's router picked for it; **laya:typed-decisions** is the checkpoint Laya ships for typed decisions, which the router does not pick.

## Every suite

| suite | backend | answered | acc | macro F1 | ECE | Brier | log loss | AURC | acc@50% | P(gold)≈0 | score MAE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| jev.ag_news | laya | 400/400 | 0.950 | 0.944 | 0.032 | 0.081 | 0.164 | 0.007 | 1.000 | 0.000 | – |
| jev.ag_news | jev | 400/400 | 0.860 | 0.849 | 0.102 | 0.232 | 1.805 | 0.083 | 0.925 | 0.058 | – |
| jev.emotion | laya | 400/400 | 0.595 | 0.475 | 0.306 | 0.696 | 2.019 | 0.266 | 0.715 | 0.000 | – |
| jev.emotion | jev | 400/400 | 0.603 | 0.515 | 0.280 | 0.646 | 4.683 | 0.231 | 0.785 | 0.142 | – |
| jev.banking77_full | laya | 400/400 | 0.425 | 0.112 | 0.381 | 0.925 | 4.797 | 0.356 | 0.600 | 0.098 | – |
| jev.banking77_full | jev | 400/400 | 0.835 | 0.314 | 0.073 | 0.257 | 1.347 | 0.058 | 0.965 | 0.035 | – |
| app.support_triage | laya | 400/400 | 0.502 | 0.480 | 0.091 | 0.644 | 1.424 | 0.321 | 0.595 | 0.000 | – |
| app.support_triage | jev | 400/400 | 0.365 | 0.368 | 0.483 | 1.056 | 10.120 | 0.487 | 0.480 | 0.335 | – |
| app.email_spam | laya | 400/400 | 0.998 | 0.998 | 0.011 | 0.005 | 0.013 | 0.000 | 1.000 | 0.000 | – |
| app.email_spam | jev | 400/400 | 0.978 | 0.977 | 0.060 | 0.038 | 0.097 | 0.001 | 1.000 | 0.000 | – |
| app.phishing | laya | 400/400 | 0.983 | 0.982 | 0.010 | 0.026 | 0.044 | 0.001 | 1.000 | 0.000 | – |
| app.phishing | jev | 400/400 | 0.900 | 0.887 | 0.039 | 0.152 | 0.249 | 0.021 | 0.995 | 0.000 | – |
| app.guardrails_jailbreak | laya | 400/400 | 0.705 | 0.682 | 0.262 | 0.543 | 1.912 | 0.230 | 0.820 | 0.003 | – |
| app.guardrails_jailbreak | jev | 400/400 | 0.940 | 0.918 | 0.047 | 0.104 | 0.189 | 0.012 | 0.995 | 0.000 | – |
| app.moderation_toxicity | laya | 400/400 | 0.530 | 0.400 | 0.297 | 0.602 | 0.886 | 0.281 | 0.735 | 0.000 | – |
| app.moderation_toxicity | jev | 400/400 | 0.662 | 0.628 | 0.177 | 0.432 | 0.619 | 0.138 | 0.860 | 0.000 | – |
| app.rag_relevance | laya | 400/400 | 0.625 | 0.623 | 0.117 | 0.466 | 0.671 | 0.280 | 0.720 | 0.000 | – |
| app.rag_relevance | jev | 400/400 | 0.620 | 0.592 | 0.279 | 0.628 | 1.113 | 0.331 | 0.670 | 0.000 | – |
| app.model_routing_domain | laya | 399/399 | 0.639 | 0.320 | 0.089 | 0.494 | 1.089 | 0.176 | 0.874 | 0.000 | – |
| app.model_routing_domain | jev | 399/399 | 0.977 | 0.592 | 0.014 | 0.040 | 0.085 | 0.003 | 1.000 | 0.000 | – |
| typed_decisions | laya | 2000/2000 | 0.361 | 0.327 | 0.175 | 0.750 | 1.323 | 0.593 | 0.428 | 0.000 | 0.694 |
| typed_decisions | laya:typed-decisions | 2000/2000 | 0.766 | 0.750 | 0.213 | 0.400 | 0.707 | 0.099 | 0.903 | 0.000 | 0.242 |
| typed_decisions | jev | 2000/2000 | 0.736 | 0.738 | 0.047 | 0.366 | 0.707 | 0.128 | 0.885 | 0.003 | 0.391 |
| MASSIVE, 51 langs, macro | laya | 5100/5100 | 0.382 | 0.357 | 0.418 | 0.987 | 3.828 | 0.480 | 0.504 | 0.030 | – |
| MASSIVE, 51 langs, macro | jev | 5099/5100 | 0.890 | 0.886 | 0.064 | 0.161 | 0.775 | 0.020 | 0.995 | 0.018 | – |

## Risk at coverage

Error rate of the most confident answers, ties in confidence taken together.

| suite | backend | 10% | 25% | 50% | 75% | 90% | 100% |
|---|---|---|---|---|---|---|---|
| jev.ag_news | laya | 0.000 | 0.000 | 0.000 | 0.007 | 0.025 | 0.050 |
| jev.ag_news | jev | 0.077 | 0.077 | 0.077 | 0.078 | 0.103 | 0.140 |
| jev.emotion | laya | 0.150 | 0.200 | 0.285 | 0.353 | 0.383 | 0.405 |
| jev.emotion | jev | 0.127 | 0.127 | 0.217 | 0.331 | 0.375 | 0.398 |
| jev.banking77_full | laya | 0.075 | 0.240 | 0.400 | 0.497 | 0.542 | 0.575 |
| jev.banking77_full | jev | 0.025 | 0.025 | 0.032 | 0.097 | 0.116 | 0.165 |
| app.support_triage | laya | 0.000 | 0.190 | 0.405 | 0.457 | 0.481 | 0.497 |
| app.support_triage | jev | 0.263 | 0.371 | 0.522 | 0.610 | 0.639 | 0.635 |
| app.email_spam | laya | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.003 |
| app.email_spam | jev | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.022 |
| app.phishing | laya | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.018 |
| app.phishing | jev | 0.000 | 0.000 | 0.005 | 0.050 | 0.075 | 0.100 |
| app.guardrails_jailbreak | laya | 0.225 | 0.180 | 0.180 | 0.253 | 0.275 | 0.295 |
| app.guardrails_jailbreak | jev | 0.000 | 0.000 | 0.004 | 0.021 | 0.037 | 0.060 |
| app.moderation_toxicity | laya | 0.125 | 0.160 | 0.265 | 0.383 | 0.442 | 0.470 |
| app.moderation_toxicity | jev | 0.000 | 0.005 | 0.142 | 0.239 | 0.311 | 0.338 |
| app.rag_relevance | laya | 0.175 | 0.200 | 0.280 | 0.320 | 0.350 | 0.375 |
| app.rag_relevance | jev | 0.282 | 0.296 | 0.324 | 0.367 | 0.385 | 0.380 |
| app.model_routing_domain | laya | 0.103 | 0.051 | 0.126 | 0.264 | 0.329 | 0.361 |
| app.model_routing_domain | jev | 0.000 | 0.000 | 0.000 | 0.006 | 0.008 | 0.023 |
| typed_decisions | laya | 0.605 | 0.604 | 0.572 | 0.603 | 0.624 | 0.638 |
| typed_decisions | laya:typed-decisions | 0.005 | 0.028 | 0.097 | 0.165 | 0.204 | 0.234 |
| typed_decisions | jev | 0.025 | 0.077 | 0.114 | 0.186 | 0.231 | 0.265 |
| MASSIVE, macro | laya | 0.345 | 0.407 | 0.496 | 0.559 | 0.592 | 0.618 |
| MASSIVE, macro | jev | 0.001 | 0.001 | 0.005 | 0.031 | 0.062 | 0.110 |

## MASSIVE by language

| language | laya acc | jev acc | laya ECE | jev ECE | laya log loss | jev log loss |
|---|---|---|---|---|---|---|
| af | 0.340 | 0.870 | 0.484 | 0.087 | 5.041 | 0.934 |
| am | 0.150 | 0.850 | 0.484 | 0.096 | 4.266 | 1.004 |
| ar | 0.460 | 0.870 | 0.315 | 0.076 | 2.714 | 0.916 |
| az | 0.360 | 0.880 | 0.393 | 0.048 | 3.340 | 1.120 |
| bn | 0.450 | 0.860 | 0.354 | 0.067 | 2.868 | 0.632 |
| cy | 0.160 | 0.760 | 0.611 | 0.088 | 6.992 | 1.776 |
| da | 0.460 | 0.880 | 0.452 | 0.044 | 4.489 | 0.811 |
| de | 0.530 | 0.939 | 0.304 | 0.057 | 2.805 | 0.421 |
| el | 0.440 | 0.940 | 0.430 | 0.057 | 3.226 | 0.431 |
| en | 0.820 | 0.920 | 0.138 | 0.025 | 1.228 | 0.689 |
| es | 0.530 | 0.930 | 0.348 | 0.063 | 3.748 | 0.493 |
| fa | 0.510 | 0.950 | 0.298 | 0.053 | 2.691 | 0.414 |
| fi | 0.300 | 0.890 | 0.462 | 0.038 | 4.621 | 0.784 |
| fr | 0.600 | 0.900 | 0.268 | 0.065 | 2.671 | 0.498 |
| he | 0.370 | 0.940 | 0.419 | 0.043 | 2.835 | 0.430 |
| hi | 0.460 | 0.950 | 0.368 | 0.029 | 2.870 | 0.408 |
| hu | 0.340 | 0.920 | 0.437 | 0.039 | 3.798 | 1.054 |
| hy | 0.250 | 0.840 | 0.513 | 0.090 | 4.126 | 0.629 |
| id | 0.360 | 0.930 | 0.486 | 0.045 | 5.072 | 0.727 |
| is | 0.330 | 0.840 | 0.486 | 0.073 | 4.837 | 0.978 |
| it | 0.470 | 0.960 | 0.380 | 0.050 | 3.954 | 0.357 |
| ja | 0.640 | 0.970 | 0.234 | 0.059 | 1.743 | 0.375 |
| jv | 0.160 | 0.750 | 0.663 | 0.086 | 7.501 | 1.835 |
| ka | 0.150 | 0.880 | 0.542 | 0.108 | 4.372 | 0.962 |
| km | 0.200 | 0.810 | 0.445 | 0.073 | 3.726 | 1.260 |
| kn | 0.300 | 0.870 | 0.388 | 0.070 | 3.364 | 0.555 |
| ko | 0.470 | 0.940 | 0.311 | 0.042 | 2.340 | 0.397 |
| lv | 0.300 | 0.850 | 0.486 | 0.075 | 3.955 | 0.935 |
| ml | 0.280 | 0.910 | 0.443 | 0.050 | 3.586 | 0.552 |
| mn | 0.160 | 0.840 | 0.577 | 0.083 | 5.073 | 0.691 |
| ms | 0.270 | 0.920 | 0.506 | 0.068 | 5.337 | 1.028 |
| my | 0.160 | 0.890 | 0.477 | 0.057 | 3.989 | 0.557 |
| nb | 0.500 | 0.860 | 0.368 | 0.071 | 3.818 | 0.620 |
| nl | 0.400 | 0.900 | 0.479 | 0.055 | 5.621 | 0.827 |
| pl | 0.470 | 0.920 | 0.374 | 0.036 | 2.901 | 0.478 |
| pt | 0.440 | 0.900 | 0.396 | 0.099 | 4.207 | 1.078 |
| ro | 0.370 | 0.940 | 0.473 | 0.082 | 4.923 | 0.753 |
| ru | 0.570 | 0.940 | 0.296 | 0.033 | 2.577 | 0.408 |
| sl | 0.330 | 0.890 | 0.487 | 0.058 | 4.971 | 0.596 |
| sq | 0.290 | 0.760 | 0.500 | 0.094 | 4.024 | 1.175 |
| sv | 0.480 | 0.940 | 0.370 | 0.074 | 3.286 | 0.531 |
| sw | 0.130 | 0.700 | 0.628 | 0.112 | 6.762 | 2.696 |
| ta | 0.310 | 0.920 | 0.448 | 0.092 | 3.804 | 0.876 |
| te | 0.220 | 0.910 | 0.497 | 0.037 | 3.585 | 0.498 |
| th | 0.480 | 0.940 | 0.356 | 0.047 | 2.651 | 0.422 |
| tl | 0.300 | 0.850 | 0.492 | 0.085 | 4.942 | 1.125 |
| tr | 0.410 | 0.920 | 0.385 | 0.061 | 3.137 | 0.834 |
| ur | 0.420 | 0.900 | 0.336 | 0.064 | 2.784 | 0.564 |
| vi | 0.330 | 0.890 | 0.467 | 0.052 | 3.904 | 0.520 |
| zh-CN | 0.650 | 0.940 | 0.219 | 0.036 | 1.872 | 0.426 |
| zh-TW | 0.610 | 0.930 | 0.266 | 0.062 | 2.293 | 0.464 |
| macro | 0.382 | 0.890 | 0.418 | 0.064 | 3.828 | 0.775 |

| MASSIVE | laya | jev |
|---|---|---|
| English | 0.820 | 0.920 |
| other languages, macro | 0.373 | 0.890 |
| languages above 3× random | 48 | 51 |

Jev: 50 sequential calls, p50 227.3 ms, p95 333.9 ms; the whole run cost $0.2486.

## Metrics

- acc, macro F1, ECE (15 bins, top-label confidence), Brier (summed over options), log loss (natural log, p floored at 1e-12), acc@50% (accuracy of the more confident half): upstream `bench_local.py`, verbatim.
- AURC: area under the risk-coverage curve, the mean error rate over coverages k/n; lower is better.
- P(gold)≈0: share of answers that give the gold option a probability under 1e-6.
- score MAE: typed decisions' score questions, |expected level − the teacher's mean level|.
- answered: questions with a probability vector; an unanswered question is not scored as wrong.
