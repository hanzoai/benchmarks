# kai-a: Kai stage A, 1 epoch, mmBERT-base; retrieval uncentered

The first Kai stage-A checkpoint, scored on the frozen harness the way `kai-en` was, beside Laya,
Jev and kai-en. In `scores.json` and `table.md` the backend `kai` is this checkpoint. It predates
retrieval centering (`hanzoai/decision` fe4d636), so main's `Decider` cannot load it; every step
here ran the build that trained it, 96150d1.

| | |
|---|---|
| checkpoint | `dbc:scratch/decision/runs/a` (not published), `model.safetensors` SHA-256 `6c77ab57873d303faa2191175047c7f53e5df228ac49209f6f84e6ec36425b98` |
| init | `hanzoai/kai-1-multilingual@3119843b` (mmBERT-base, 22 layers, d 768, 256k vocabulary, token embeddings frozen); the ordinal and retrieval heads fresh |
| data | stage A build `a-189e99d2fd11f7be` (`train stage a`: GREEN, YELLOW and RED, barriered against the harness): 33 sources, 3,686,475 train rows; the harness's English suites other than RAG (nine sources, typed decisions among them) take 6.8% of the draws (typed decisions 1.6%), RAG relevance 10.8%, MASSIVE 11.3% |
| fit | `hanzoai/decision` 96150d1 with 8704424's stage file: 1 epoch, 91,899 batches, 6.2 h, 71 rounds of 300 s over dbc (Metal bf16), evo (ROCm bf16) and dgx (CUDA bf16, left after round 59); `max_len` 1024; a choice over 64 options trains on a sample of them, and inference narrows a choice over 32 by retrieval |
| calibration | 96150d1 `train calibrate`: one temperature per bucket, fit on the build's calibration split (`validation/calibration`, 21,605 records, 47,081 questions), 1,535 s; the original is `kai.uncal.json` beside `kai.json` |
| preds | 96150d1 `bench preds`: Metal bf16 on dbc, 11,099 questions in 67 s |
| scores | `harness/merge.py`, unchanged, run in a scratch tree with `preds.json.gz` as `results/kai/preds.json.gz` |
| speed | 96150d1 `bench speed`, Metal bf16 on dbc, 20 timed rounds per size |
| gate | 96150d1 `bench gate --baseline laya`: 100 cases per suite, seed 13, `results/laya/parity.json` |

Files: `preds.json.gz` (harness preds format), `scores.json` and `table.md` (merge.py's output),
`speed.json`, `gate.json` (the verdict), `checkpoint.json` (the run's spec, mixture, val,
calibration and temperatures).

## Calibration

| bucket | questions | T | log loss at T = 1 → T |
|---|---|---|---|
| choice:3-5 | 8,307 | 1.290 | 1.209 → 1.201 |
| choice:6-10 | 4,857 | 1.279 | 1.589 → 1.571 |
| choice:11-30 | 4,767 | 0.963 | 1.582 → 1.581 |
| choice:31+ | 2,469 | 1.088 | 3.286 → 3.281 |
| noul:2 | 21,856 | 1.072 | 0.585 → 0.585 |
| score:* | 4,825 | 1.918 | 1.629 → 1.472 |

The score bucket's temperature is off the bound now (kai-en's sat at 8.0 with log loss 17.8). The build's
`calibrate` records the split as "val (carved from train)"; stage A's build has no val split, so
the rows are its `calibration` split.

## Harness

Accuracy, Brier, ECE and the share of answers giving gold a probability under 1e-6, as
kai-a / Laya / Jev / kai-en. Laya is the router's pick per case; on typed decisions it is
`laya:typed-decisions` (kai-1-agent). The last column is kai-a's accuracy against Laya, Jev and
kai-en at three decimals: + above, − below, = equal. kai-en's numbers are
`results/kai-en/scores.json`, merge.py's output over the same questions.

| suite | accuracy | Brier | ECE | P(gold)≈0 | acc vs Laya Jev kai-en |
|---|---|---|---|---|---|
| jev.ag_news | 0.877 / 0.950 / 0.860 / 0.940 | 0.214 / 0.081 / 0.232 / 0.091 | 0.045 / 0.032 / 0.102 / 0.025 | 0.000 / 0.000 / 0.058 / 0.000 | − + − |
| jev.emotion | 0.662 / 0.595 / 0.603 / 0.932 | 0.435 / 0.696 / 0.646 / 0.091 | 0.048 / 0.306 / 0.280 / 0.026 | 0.000 / 0.000 / 0.142 / 0.000 | + + − |
| jev.banking77_full | 0.245 / 0.425 / 0.835 / 0.917 | 0.844 / 0.925 / 0.257 / 0.128 | 0.078 / 0.381 / 0.073 / 0.030 | 0.003 / 0.098 / 0.035 / 0.005 | − − − |
| app.support_triage | 0.352 / 0.502 / 0.365 / 0.440 | 0.743 / 0.644 / 1.056 / 0.686 | 0.036 / 0.091 / 0.483 / 0.089 | 0.000 / 0.000 / 0.335 / 0.000 | − − − |
| app.email_spam | 0.975 / 0.998 / 0.978 / 1.000 | 0.049 / 0.005 / 0.038 / 0.000 | 0.021 / 0.011 / 0.060 / 0.004 | 0.000 / 0.000 / 0.000 / 0.000 | − − − |
| app.phishing | 0.932 / 0.983 / 0.900 / 0.983 | 0.120 / 0.026 / 0.152 / 0.031 | 0.059 / 0.010 / 0.039 / 0.015 | 0.000 / 0.000 / 0.000 / 0.000 | − + − |
| app.guardrails_jailbreak | 0.630 / 0.705 / 0.940 / 0.917 | 0.427 / 0.543 / 0.104 / 0.153 | 0.061 / 0.262 / 0.047 / 0.073 | 0.000 / 0.003 / 0.000 / 0.000 | − − − |
| app.moderation_toxicity | 0.748 / 0.530 / 0.662 / 0.840 | 0.367 / 0.602 / 0.432 / 0.283 | 0.082 / 0.297 / 0.177 / 0.130 | 0.000 / 0.000 / 0.000 / 0.000 | + + − |
| app.rag_relevance | 0.510 / 0.625 / 0.620 / 0.682 | 0.507 / 0.466 / 0.628 / 0.403 | 0.044 / 0.117 / 0.279 / 0.064 | 0.000 / 0.000 / 0.000 / 0.000 | − − − |
| app.model_routing_domain | 0.983 / 0.639 / 0.977 / 1.000 | 0.028 / 0.494 / 0.040 / 0.000 | 0.029 / 0.089 / 0.014 / 0.001 | 0.000 / 0.000 / 0.000 / 0.000 | + + − |
| typed_decisions | 0.455 / 0.766 / 0.736 / 0.574 | 0.644 / 0.400 / 0.366 / 0.810 | 0.064 / 0.213 / 0.047 / 0.392 | 0.000 / 0.000 / 0.003 / 0.292 | − − − |
| massive.en | 0.800 / 0.820 / 0.920 / 0.890 | 0.261 / 0.288 / 0.108 / 0.170 | 0.103 / 0.138 / 0.025 / 0.079 | 0.000 / 0.020 / 0.020 / 0.000 | − − − |
| MASSIVE, 51 langs, macro | 0.635 / 0.382 / 0.890 / 0.192 | 0.455 / 0.987 / 0.161 / 0.918 | 0.113 / 0.418 / 0.064 / 0.151 | 0.000 / 0.030 / 0.018 / 0.000 | + − + |

- Above Laya on DAIR emotion, toxicity, routing and MASSIVE: 50 of 51 languages (all but
  English), macro 0.635 against 0.382, every language above 3× random.
- Below Laya on AG News, Banking77, support triage, email spam, phishing, jailbreak, RAG
  relevance, typed decisions and MASSIVE English; below Jev everywhere but AG News, emotion,
  phishing, toxicity and routing; below kai-en on every suite but the MASSIVE macro.
- ECE at most 0.082 on every app suite and 0.064 on typed decisions (Laya 0.213); no answer
  gives gold under 1e-6 outside Banking77 (0.003).

### Where it loses

- **Typed decisions** (0.455; Laya 0.766, Jev 0.736, kai-en 0.574). The init never learned them:
  kai-1-multilingual answers 0.352 (`laya:multilingual`), while kai-en started from kai-1-agent,
  which Laya fine-tuned on them. Stage A draws 1.6% typed decisions. The score head is calibrated
  (MAE 0.647 against kai-en's 1.366, no zero on gold) but its argmax does not depend on the case:
  on 7 of the 8 score questions it answers one level for all 100 states (every `urgency` 3,
  `security_incidents.severity` 4), so its accuracy is that level's share of gold. Choice 0.483 and
  noul 0.640 against kai-en's 0.715 and 0.838; agent traces are the worst workflow (`action` 0.29,
  `outcome` 0.23, `needs_review` 0.48, against kai-en 0.70, 0.66, 0.89).
- **Banking77** (0.245; Laya 0.425, Jev 0.835, kai-en 0.917). 77 options is over the stage's
  64, so it trained on a sample of them and answers by retrieval's top 32, then the head. Retrieval
  is not the loss: gold stays in its top 32 for 98.5% of questions (median rank 2, top 5 0.81).
  The head is: top 1 0.26, macro F1 0.073. It never trained on retrieval's own negatives. Val
  rose over the run (0.216 at 24,082 batches, 0.474 at 84,900) and ended at 0.429.
- **Jailbreak** (0.630; Laya 0.705). Both safety suites read toxic-chat prompts, and the train
  split holds 54 jailbreak positives, balanced up to half of 6,000 draws. Val swung between the
  two over the run (jailbreak / toxicity 0.965 / 0.798 at 49,071, 0.972 / 0.686 at 84,900,
  0.707 / 0.909 at the end); at the final checkpoint it flags 217 of 400 prompts against 91 gold.
- **RAG relevance** (0.510; Laya 0.625). At chance: val 0.47–0.53 from 13,101 batches on
  (0.625 at 2,325), and on the harness it answers one side for 316 of 400 against gold 200 / 200,
  though the MS MARCO train rows are balanced and take 10.8% of the draws. The cause is not
  established here.
- **AG News, email spam, phishing, support triage, MASSIVE English** (0.02–0.15 under Laya).
  Each of the four app suites is 0.5–0.9% of the draws (MASSIVE's 11.3% spreads over 51
  locales), for one epoch, on a smaller encoder (22 layers, d 768, against ModernBERT-large's 28,
  1024); kai-en saw only the harness suites, in English, twice. Val AG News rose from 0.807 at
  24,082 batches to 0.860 at 84,900 and ended at 0.845.

## MASSIVE by language

Accuracy, kai-a / Laya / Jev / kai-en, and kai-a's ECE.

| language | kai-a | Laya | Jev | kai-en | kai-a ECE | kai-a vs Laya Jev kai-en |
|---|---|---|---|---|---|---|
| af | 0.670 | 0.340 | 0.870 | 0.210 | 0.091 | + − + |
| am | 0.540 | 0.150 | 0.850 | 0.050 | 0.151 | + − + |
| ar | 0.590 | 0.460 | 0.870 | 0.100 | 0.125 | + − + |
| az | 0.660 | 0.360 | 0.880 | 0.150 | 0.087 | + − + |
| bn | 0.540 | 0.450 | 0.860 | 0.110 | 0.122 | + − + |
| cy | 0.490 | 0.160 | 0.760 | 0.170 | 0.192 | + − + |
| da | 0.710 | 0.460 | 0.880 | 0.240 | 0.069 | + − + |
| de | 0.710 | 0.530 | 0.939 | 0.210 | 0.106 | + − + |
| el | 0.610 | 0.440 | 0.940 | 0.070 | 0.116 | + − + |
| en | 0.800 | 0.820 | 0.920 | 0.890 | 0.103 | − − − |
| es | 0.720 | 0.530 | 0.930 | 0.350 | 0.084 | + − + |
| fa | 0.690 | 0.510 | 0.950 | 0.090 | 0.121 | + − + |
| fi | 0.560 | 0.300 | 0.890 | 0.150 | 0.110 | + − + |
| fr | 0.720 | 0.600 | 0.900 | 0.460 | 0.114 | + − + |
| he | 0.570 | 0.370 | 0.940 | 0.120 | 0.143 | + − + |
| hi | 0.650 | 0.460 | 0.950 | 0.120 | 0.132 | + − + |
| hu | 0.600 | 0.340 | 0.920 | 0.120 | 0.100 | + − + |
| hy | 0.530 | 0.250 | 0.840 | 0.070 | 0.141 | + − + |
| id | 0.720 | 0.360 | 0.930 | 0.220 | 0.085 | + − + |
| is | 0.580 | 0.330 | 0.840 | 0.140 | 0.140 | + − + |
| it | 0.720 | 0.470 | 0.960 | 0.240 | 0.088 | + − + |
| ja | 0.770 | 0.640 | 0.970 | 0.350 | 0.073 | + − + |
| jv | 0.580 | 0.160 | 0.750 | 0.150 | 0.127 | + − + |
| ka | 0.460 | 0.150 | 0.880 | 0.070 | 0.106 | + − + |
| km | 0.490 | 0.200 | 0.810 | 0.090 | 0.126 | + − + |
| kn | 0.570 | 0.300 | 0.870 | 0.060 | 0.068 | + − + |
| ko | 0.670 | 0.470 | 0.940 | 0.120 | 0.076 | + − + |
| lv | 0.560 | 0.300 | 0.850 | 0.100 | 0.136 | + − + |
| ml | 0.600 | 0.280 | 0.910 | 0.070 | 0.096 | + − + |
| mn | 0.450 | 0.160 | 0.840 | 0.050 | 0.162 | + − + |
| ms | 0.710 | 0.270 | 0.920 | 0.190 | 0.098 | + − + |
| my | 0.600 | 0.160 | 0.890 | 0.050 | 0.092 | + − + |
| nb | 0.740 | 0.500 | 0.860 | 0.260 | 0.079 | + − + |
| nl | 0.660 | 0.400 | 0.900 | 0.250 | 0.124 | + − + |
| pl | 0.660 | 0.470 | 0.920 | 0.200 | 0.129 | + − + |
| pt | 0.660 | 0.440 | 0.900 | 0.310 | 0.134 | + − + |
| ro | 0.670 | 0.370 | 0.940 | 0.250 | 0.078 | + − + |
| ru | 0.720 | 0.570 | 0.940 | 0.270 | 0.115 | + − + |
| sl | 0.630 | 0.330 | 0.890 | 0.150 | 0.156 | + − + |
| sq | 0.540 | 0.290 | 0.760 | 0.210 | 0.118 | + − + |
| sv | 0.690 | 0.480 | 0.940 | 0.210 | 0.105 | + − + |
| sw | 0.600 | 0.130 | 0.700 | 0.180 | 0.126 | + − + |
| ta | 0.640 | 0.310 | 0.920 | 0.070 | 0.138 | + − + |
| te | 0.560 | 0.220 | 0.910 | 0.090 | 0.114 | + − + |
| th | 0.740 | 0.480 | 0.940 | 0.110 | 0.116 | + − + |
| tl | 0.600 | 0.300 | 0.850 | 0.320 | 0.145 | + − + |
| tr | 0.690 | 0.410 | 0.920 | 0.250 | 0.082 | + − + |
| ur | 0.590 | 0.420 | 0.900 | 0.060 | 0.123 | + − + |
| vi | 0.620 | 0.330 | 0.890 | 0.140 | 0.128 | + − + |
| zh-CN | 0.770 | 0.650 | 0.940 | 0.510 | 0.072 | + − + |
| zh-TW | 0.770 | 0.610 | 0.930 | 0.360 | 0.086 | + − + |
| macro | 0.635 | 0.382 | 0.890 | 0.192 | 0.113 | |

| MASSIVE | kai-a | Laya | Jev | kai-en |
|---|---|---|---|---|
| English | 0.800 | 0.820 | 0.920 | 0.890 |
| other 50 languages, macro | 0.632 | 0.373 | 0.890 | 0.178 |
| languages above 3× random | 51 | 48 | 51 | 24 |

kai-a's worst languages: mn 0.45, ka 0.46, cy 0.49, km 0.49, hy 0.53, am, bn and sq 0.54; its
best: en 0.80, zh-CN, zh-TW and ja 0.77. Above Laya and kai-en in 50 of 51 languages (all but
English), below Jev in all 51.

## Typed decisions

Accuracy by workflow and by question type, and the question-level metrics; Laya is
`laya:typed-decisions` (kai-1-agent). The zero-on-gold counts are counted from each backend's
preds under merge.py's rule.

| | kai-a | Laya (kai-1-agent) | Jev | kai-en |
|---|---|---|---|---|
| agent_trace_observability | 0.290 | 0.730 | 0.634 | 0.520 |
| customer_service | 0.518 | 0.764 | 0.790 | 0.590 |
| invoice_processing | 0.488 | 0.804 | 0.778 | 0.604 |
| security_incidents | 0.524 | 0.766 | 0.740 | 0.580 |
| choice | 0.483 | 0.733 | 0.732 | 0.715 |
| noul | 0.640 | 0.857 | 0.785 | 0.838 |
| score | 0.295 | 0.723 | 0.701 | 0.269 |
| accuracy | 0.455 | 0.766 | 0.736 | 0.574 |
| soft_accuracy | 0.356 | 0.471 | 0.538 | 0.412 |
| score_mae | 0.647 | 0.242 | 0.391 | 1.366 |
| within_1_level | 0.738 | 0.995 | 0.946 | 0.384 |
| ece | 0.064 | 0.213 | 0.047 | 0.392 |
| zero_prob | 0.000 | 0.000 | 0.003 | 0.292 |

| P(gold)≈0, of answers | kai-a | Laya (kai-1-agent) | Jev | kai-en |
|---|---|---|---|---|
| choice | 0 / 600 | 0 / 600 | 1 / 600 | 0 / 600 |
| noul | 0 / 600 | 0 / 600 | 0 / 600 | 0 / 600 |
| score | 0 / 800 | 0 / 800 | 5 / 800 | 584 / 800 |

## Speed

One call is one typed-decision state with N of the harness's 130 distinct questions (`bench
speed`); load 0.4 s, peak footprint 3.9 GB. dbc was quiet: its 1-minute load average was 3.7
before and 3.3 after. p95 at 100 and 500 is still about twice p50. kai-en's p50 is in the last
column.

| questions | p50 ms | p95 ms | questions/s | kai-en p50 ms |
|---|---|---|---|---|
| 1 | 24.9 | 26.5 | 42.2 | 48.2 |
| 5 | 49.7 | 56.7 | 95.7 | 122.4 |
| 10 | 82.0 | 112.3 | 118.4 | 184.3 |
| 50 | 299.4 | 380.7 | 157.9 | 751.9 |
| 100 | 627.2 | 1,320.0 | 133.2 | 1,534.4 |
| 500 | 5,673.8 | 10,913.1 | 79.5 | 12,830.6 |

## Gate against Laya

`bench gate --baseline laya`: **reject** (exit 1). Laya answers only the harness suites, so its
62 are gated and the capability and robustness suites are reported. Macro accuracy over the 62:
0.639 against Laya's 0.438 (+0.201, carried by the 51 MASSIVE languages). Parity holds (108 of
108 labels, max |Δlogit| 2.9e-5 under 1e-4). Seven suites regress (accuracy down more than 0.02
or ECE up more than 0.03), on the drawn cases:

| suite | questions | accuracy kai-a / Laya | ECE kai-a / Laya |
|---|---|---|---|
| AG News | 100 | 0.910 / 0.940 | 0.093 / 0.050 |
| Banking77 | 100 | 0.230 / 0.420 | 0.114 / 0.394 |
| support triage | 100 | 0.330 / 0.480 | 0.061 / 0.114 |
| email spam | 100 | 0.940 / 1.000 | 0.058 / 0.004 |
| jailbreak | 100 | 0.600 / 0.700 | 0.075 / 0.275 |
| RAG relevance | 100 | 0.440 / 0.480 | 0.101 / 0.262 |
| typed decisions | 500 | 0.454 / 0.746 | 0.069 / 0.200 |

No MASSIVE language regresses. Not gated: CLINC150 0.300, SST-5 0.150, XNLI 0.450 (sw) to 0.630
(de, zh) over 15 languages; robustness shuffle 0.629, alias 0.703, swap 0.702, subset 0.795,
near 0.682.
