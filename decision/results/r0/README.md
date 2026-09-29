# r0: where kai-1's transferable decision ability went by a7

Kai's lineage on Jev's own benchmarks (jevlab B1, B3, B3b), with the encoder and the head taken
apart. Lineage: `jhu-clsp/mmBERT-base` (`base`) → Laya's fine-tune `hanzoai/kai-1-multilingual@3119843b`
(`kai1-ml`) → Kai stage a4 (new factorized head, init kai1-ml) → a5 → a6 → a7 (weights
`0834a74f…`); `ties2` is the TIES merge of a8 and a9 onto a7 (density 0.2, λ 1, weights
`f248d34b…`). `kai1` is `hanzoai/kai-1@b50502c2` (ModernBERT-large), routed as Laya routes.
Scripts: `hanzoai/decision` `forensics/`. The benchmark items are sealed: read to score, never to
train, mine or distil; no item text is kept here, only answers keyed by item id.

## Answer

- **a7's ordering is wrong, not compressed.** B1 nouls: ROC-AUC of P(true) 0.539 (kai1-ml 0.723,
  kai1 0.812); the best any single threshold does is 0.577 (kai1-ml 0.692); log-odds SD 0.49
  against 3.71. Calibration cannot recover it.
- **The encoder forgot; the head did not hide it.** Laya's own head over a4's or a7's encoder
  falls from 0.690 to 0.510 / 0.500 on B1. Fresh probes trained on the same generic decision data
  read 0.62–0.63 from kai1-ml's encoder in Laya's layout and 0.46–0.55 from a4–a7's in either
  layout, within a standard error of a7's own head (0.480), while all of them score alike on the
  probe data's own validation (0.63–0.71): the loss is off-distribution, in the encoder.
- **It happened at a4, in one step.** B1 0.690 → 0.470 at a4, then 0.450 / 0.490 / 0.480. At a4
  the encoder's [CLS] massive activation at layer 12 (norm 11,748 on text, 18,607 in Kai's layout;
  base 9,467) fell to 96–167, and the upper layers' representation followed (standardized CKA to
  kai1-ml ≤ 0.14 from layer 12 on; a4 → a7 ≥ 0.68). The [SEP] sink stayed. Kai's retrieval query
  is the context's first token.
- **B3 and B3b are capacity, not recipe.** Every mmBERT encoder under every head or probe answers
  ANLI r3 and B3b at chance (0.27–0.34), kai1-ml included; kai1's larger encoder reaches 0.455 on
  CommonsenseQA, where kai1-ml's 0.345 fell to 0.19–0.26 in a4–a7.
- **The open-label dev probes see the loss.** `labels.dev` top-1: kai1 0.649, kai1-ml 0.583, a7
  0.438 (kai1 − a7 +0.211, 95% [+0.129, +0.303]); renamed-label flips 0.224 / 0.369 / 0.514.
- **ties2 moved a7 as far as one ordinary stage, along a4's directions.** Against a6 → a7:
  context cosine 0.976 / 0.976, retrieval-score correlation 0.922 / 0.929, head flips 10.5% /
  11.0%; its update's top-16 subspaces overlap a4's 9–19× chance, rising with depth, most in the
  residual writes (attn.Wo, mlp.Wo) of layers 16–21. Its dev differences from a7 are all within
  the task-bootstrap interval.

## Runs

Every checkpoint served by the decision runtime (`decision serve`, commit 86c2690) on dgx's CPU,
8 threads, nice 19, one request at a time; Kai's encoder projections Q8_0 there, Laya F32. Before
the corpus each service answered 100 frozen-harness questions against the checkpoint's recorded
predictions (`results/<run>/preds.json.gz`): argmax agreement kai1 100 (max |Δp| 1.7e-5), kai1-ml
100 (5.5e-6), a4 98, a5 100, a6 100, a7 100 (max |Δp| 0.03–0.10: Q8_0 against F32 and Metal bf16
references); ties2 has no
recorded predictions and was checked against a7's (93). `runs.json` holds each service's model
list, SHA-256, calibration and load. The head swaps, probes, CKA and drift run enc.py, a torch
port of the runtime's layouts and heads, checked against the same recorded predictions on 32–40
harness questions each (`parity.json`): Laya's head over kai1-ml and kai1, and Kai's over a4–a7,
40/40 or 32/32 argmax, max |Δp| 3.2e-6 against CPU F32 references, ≤ 0.047 against Metal bf16
(kai1's recorded predictions carry its temperatures, so it is checked by argmax alone).

## B1, B3, B3b (`lineage.json`, `answers.json.gz`)

Accuracy / ROC-AUC (option probabilities pooled one-vs-rest) / Brier (full vector) / ECE (p_max,
ten bins). Jev and `laya-jevlab` are jevlab's recorded answers; kai1 reproduces the latter
(0.770).

| | B1 (100) | B3 (500) | B3b (300) |
|---|---|---|---|
| kai1 | 0.770 / 0.909 / 0.332 / 0.067 | 0.382 / 0.624 / 0.921 / 0.353 | 0.290 / 0.512 / 0.939 / 0.298 |
| kai1-ml | 0.690 / 0.851 / 0.462 / 0.176 | 0.338 / 0.578 / 1.067 / 0.473 | 0.247 / 0.484 / 1.122 / 0.473 |
| a4 | 0.470 / 0.745 / 0.555 / 0.153 | 0.282 / 0.539 / 0.863 / 0.247 | 0.240 / 0.537 / 0.834 / 0.221 |
| a5 | 0.450 / 0.757 / 0.534 / 0.127 | 0.288 / 0.570 / 0.762 / 0.131 | 0.230 / 0.543 / 0.777 / 0.145 |
| a6 | 0.490 / 0.775 / 0.521 / 0.121 | 0.270 / 0.562 / 0.815 / 0.226 | 0.240 / 0.539 / 0.810 / 0.190 |
| a7 | 0.480 / 0.755 / 0.540 / 0.116 | 0.274 / 0.563 / 0.815 / 0.219 | 0.207 / 0.526 / 0.824 / 0.221 |
| ties2 | 0.540 / 0.787 / 0.505 / 0.083 | 0.278 / 0.560 / 0.824 / 0.221 | 0.240 / 0.533 / 0.812 / 0.188 |
| Jev | 0.980 / 1.000 / 0.024 / 0.034 | 0.766 / 0.942 / 0.336 / 0.110 | 0.813 / 0.962 / 0.260 / 0.029 |

| | B1 noul / choice / score | noul AUC | P(true) on true / false | best threshold | log-odds SD | margin p50, share \|m\| < 0.2 | ANLI r3 / CSQA | NLI / MCQ (B3b) |
|---|---|---|---|---|---|---|---|---|
| kai1 | 0.712 / 0.789 / 1.000 | 0.812 | 0.593 / 0.224 | 0.788 | 3.33 | +1.68, 0.06 | 0.333 / 0.455 | 0.340 / 0.240 |
| kai1-ml | 0.654 / 0.711 / 0.800 | 0.723 | 0.560 / 0.286 | 0.692 | 3.71 | +1.72, 0.00 | 0.333 / 0.345 | 0.313 / 0.180 |
| a4 | 0.481 / 0.474 / 0.400 | 0.544 | 0.449 / 0.436 | 0.615 | 0.46 | −0.08, 0.23 | 0.343 / 0.190 | 0.307 / 0.173 |
| a7 | 0.500 / 0.447 / 0.500 | 0.539 | 0.476 / 0.440 | 0.577 | 0.49 | −0.02, 0.32 | 0.307 / 0.225 | 0.233 / 0.180 |
| ties2 | 0.596 / 0.447 / 0.600 | 0.615 | 0.481 / 0.418 | 0.615 | 0.57 | +0.06, 0.26 | 0.317 / 0.220 | 0.293 / 0.187 |
| Jev | 0.962 / 1.000 / 1.000 | 1.000 | 0.964 / 0.088 | 1.000 | 3.75 | +4.60, 0.00 | 0.703 / 0.860 | 0.780 / 0.847 |

B1 by category, kai1 / kai1-ml / a4 / a7: moderation 1.00 / 1.00 / 0.25 / 0.25, sentiment (score)
1.00 / 0.80 / 0.40 / 0.50, routing 1.00 / 0.75 / 0.50 / 0.50, reading 0.79 / 0.57 / 0.36 / 0.50,
urgency 0.75 / 0.50 / 0.25 / 0.25, intent 0.90 / 0.90 / 0.80 / 0.70. The best threshold is an
oracle on the items, never a fitted setting. B1 has 100 items: a difference under ~0.07 is one
standard error.

## Encoder against head

`transplant.json`: heads moved between encoders, no training. `probe.json`: each frozen encoder
under the same simple heads, trained on generic decision data (`probe-data.json`: 31,801 train
and 3,862 validation rows of MNLI, BoolQ, typed decisions, SST-5, AG News, emotion, MS MARCO
relevance, toxic-chat, routing from the a5 data build, and ARC, OpenBookQA, SciQ and Social IQa,
which no stage trained on; every state checked against every sealed state by content unit and
word-trigram Jaccard, none caught): `joint` reads the final state at each option's marker in
Laya's row, `apart` reads [c, o, c·o, |c−o|] of the mean context and option tokens in Kai's
layout; `lin` a linear scorer, `mlp` one hidden layer of 256. L2 penalty and epoch chosen on the
probe data's validation macro accuracy alone.

B1 accuracy (noul AUC):

| encoder | Laya's head | a7's head | joint lin | joint mlp | apart lin | apart mlp | probe val macro |
|---|---|---|---|---|---|---|---|
| base | 0.360 (0.465) | 0.300 (0.404) | 0.370 | 0.410 | 0.420 | 0.440 | 0.51–0.61 |
| kai1-ml | **0.690** (0.723) | 0.400 (0.607) | **0.620** (0.677) | **0.630** (0.735) | 0.540 | 0.540 | 0.63–0.69 |
| a4 | 0.510 (0.532) | 0.480 (0.517) | 0.540 | 0.490 | 0.510 | 0.480 | 0.66–0.68 |
| a5 | 0.570 (0.520) | 0.490 (0.563) | 0.510 | 0.500 | 0.530 | 0.520 | 0.66–0.69 |
| a6 | 0.520 (0.517) | 0.520 (0.566) | 0.460 | 0.480 | 0.530 | 0.470 | 0.66–0.70 |
| a7 | 0.500 (0.449) | **0.470** (0.535) | 0.470 (0.527) | 0.520 (0.686) | 0.550 | 0.460 | 0.67–0.69 |
| ties2 | 0.510 (0.479) | 0.530 (0.618) | 0.440 | 0.570 | 0.510 | 0.530 | 0.67–0.71 |

On B3 and B3b every cell is 0.26–0.34 and 0.21–0.30: no head or probe over any of these encoders
reads ANLI r3 or B3b's written items.

## Where along the lineage (`weights.json`, `cka*.json`, `sink.json`)

Relative Frobenius change of the encoder (token embeddings, frozen in every Kai stage, excluded):
base → kai1-ml 7.9% (Laya's whole fine-tune), kai1-ml → a4 7.7%, a4 → a5 3.3%, a5 → a6 2.4%,
a6 → a7 2.2%, a7 → ties2 2.9%; kai1-ml → a7 9.4%, 8–13% per layer, uniform with depth. Kai's
update is orthogonal to Laya's (flattened cosine −0.016 to +0.012 per layer). a4's update and
a4 → a7's share their top-16 subspaces at 0.16–0.29 (output) and 0.20–0.38 (input) against chance
0.014 / 0.019: the later stages continued along a4's directions.

The [CLS] token's norm (layer 11 / 12 / 18, Kai's layout on the probe's validation rows):

| | base | kai1-ml | a3 (stage A line) | a4 | a5 | a6 | a7 | ties2 |
|---|---|---|---|---|---|---|---|---|
| [CLS] | 57 / 12,179 / 12,100 | 95 / 18,607 / 18,572 | 801 / 944 / 3,097 | 99 / 103 / 160 | 98 / 101 / 161 | 94 / 97 / 155 | 94 / 96 / 148 | 94 / 96 / 148 |
| [SEP] from layer 13 | 3,522 | 3,273 | 1,037 | 2,145 | 2,011 | 1,934 | 2,028 | 1,907 |
| median token, layer 12 / 18 | 54 / 82 | 66 / 109 | 732 / 3,019 | 88 / 154 | 87 / 158 | 84 / 152 | 83 / 147 | 83 / 147 |

Layer-wise CKA is ruled by those activations (one dimension holds 43–56% of the token variance
in base and kai1-ml from layer 12, 91–94% in a4–a7 from layer 13), so it is reported raw,
standardized per dimension (`token_std`) and as the cosine of mean tokens. Standardized, on
generic text / on Kai's question-conditioned rows: kai1-ml ~ a4 0.97–0.72 through layer 11, then
0.05–0.11 / 0.02–0.06 from layer 12; kai1-ml ~ a7 the same; a4 ~ a7 0.89 at layer 12, 0.74 / 0.68
after; a6 ~ a7 0.93 / 0.90; a7 ~ ties2 0.92 / 0.91; base ~ kai1-ml 0.87 at layer 12, 0.71–0.76 after.

## ties2 against a7 (`drift.json`, `views.json`, `weights.json`)

Before the head, over the probe's validation rows, a7 → ties2 beside a6 → a7: mean context
cosine 0.976 / 0.976, option 0.985 / 0.986, retrieval query 0.930 / 0.949, key 0.973 / 0.970,
per-row retrieval-score correlation 0.922 / 0.929 (top-1 moved 13.4% / 12.7%), head argmax flips
10.5% / 11.0%, mean |Δp| 0.041 / 0.043. Its update (2.4–4.2% per layer) overlaps a4's top-16
subspaces at 0.12–0.26 (output) and 0.17–0.34 (input), and a4 → a7's at 0.13–0.35 and 0.21–0.44,
both rising with depth; by projection, attn.Wo and mlp.Wo output sides (0.24 and 0.43 with a4's;
0.31 and 0.54 with a4 → a7's); 9.5–12.5% of its energy in layers 18–21 lies in a4's top-16
output subspace (chance 1.4%).

Open-label dev probes (`labels.dev`: 23 tasks of 11 held ontologies, 920 items in every view;
the runtime's argmax through each view's option map; kai1 is the English checkpoint on every
row). Differences carry a 95% paired bootstrap over tasks:

| | top-1 | renamed flips | irrelevant flips (1 − retention) | description flips | opaque flips |
|---|---|---|---|---|---|
| kai1 | 0.649 | 0.224 | 0.249 | 0.116 | 0.205 |
| kai1-ml | 0.583 | 0.369 | 0.342 | 0.191 | 0.246 |
| a7 | 0.438 | 0.514 | 0.307 | 0.272 | 0.290 |
| ties2 | 0.441 | 0.451 | 0.259 | 0.316 | 0.329 |
| kai1 − a7 | +0.211 [+0.129, +0.303] | −0.290 [−0.410, −0.168] | −0.058 [−0.173, +0.060] | −0.155 [−0.230, −0.072] | −0.085 [−0.177, +0.016] |
| kai1-ml − a7 | +0.145 [+0.073, +0.224] | −0.145 [−0.280, −0.015] | +0.036 [−0.074, +0.161] | −0.080 [−0.150, −0.003] | −0.045 [−0.137, +0.057] |
| ties2 − a7 | +0.003 [−0.020, +0.026] | −0.063 [−0.172, +0.031] | −0.048 [−0.101, +0.010] | +0.045 [−0.012, +0.103] | +0.039 [−0.035, +0.123] |

a7 through this port and through `bench cap --suites labels` (CPU F32) agree within 0.012 on
every key. ESCO dev, the runtime's own retrieval before the head (`bench cap` on ra, CPU F32),
ties2 − a7: recall@32 −0.006 / −0.020 / −0.012 at 100 / 300 / 1,000 options, top-1 of the answer
+0.020 at 100.

## Taking a4's update back, no training (`views.json`, `sink-revert.json`)

a7 with α·(a4 − kai1-ml) subtracted from encoder layers `lo..hi`, a7's head untouched
(`forensics/revert.py`), on the same dev probes:

| | layers | [CLS] norm, layer 12 | top-1 | renamed flips | irrelevant flips | description flips |
|---|---|---|---|---|---|---|
| a7 | – | 96 | 0.438 | 0.514 | 0.307 | 0.272 |
| α 0.5 | 12–21 | 96 | 0.432 | 0.512 | 0.271 | 0.292 |
| α 1 | 12–21 | 96 | 0.400 | 0.558 | 0.343 | 0.413 |
| α 1 | 0–21 | 15,782 | 0.404 | 0.592 | 0.366 | 0.534 |

The [CLS] activation comes back only when layers 0–11 are reverted too, and with a7's head no
revert recovers transfer: top-1 falls 0.007–0.038 and description flips rise up to +0.262
[+0.165, +0.354]. a7's head reads a7's encoder; weight arithmetic does not reach kai1-ml's
behavior.

## jev-harness (`verdicts-kai1.json`)

jev-harness's own `decide()` and `routeTools()` over kai1 through the runtime (compat/bench's
driver, `model` renamed by a proxy): proposal review v4 84/150 (the score of holding every case,
as a7), routing v5 54/114 (a7 36/114, the score of always asking; Jev 150 and 114).
