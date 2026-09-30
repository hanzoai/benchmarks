# held

Two held-out suites, `held.phishing` and `held.support_triage`, that replace the frozen harness's `app.phishing` and `app.support_triage` when Kai, Laya and Jev are compared: Laya trained on the rows those two draw from (the train splits of `zefang-liu/phishing-email-dataset` and `Tobi-Bueck/customer-support-tickets`), and neither dataset has other rows.

Each suite asks its frozen suite's question verbatim (`research/scripts/bench_apps.py`, Laya 0.3.20) and keeps its state keys and gold format. Seed 13. `build.py build` reads only the files here, the frozen harness and pinned dataset revisions, and writes the same bytes every run.

| File | Contents |
|---|---|
| `states.json.gz` | `{suite: [[state, questions, gold], ...]}`, the format of `results/states.json.gz` |
| `questions.json.gz` | `{suite: [[gold, questions], ...]}`, the format of `results/questions.json.gz` |
| `build.py` | `generate`, `check` and `build`; every prompt is in it |
| `support/generate.jsonl` | every generation call: specifications, messages, raw answer, parsed tickets, the model that served it |
| `support/check.jsonl` | every label-check answer, with the model that served it |
| `laya/preds.json.gz` | Laya 0.3.20 on both suites |

## held.phishing

400 cases: 200 phishing, gold `{"is_phishing": {"idx": 1}}` (noul options are ordered `false, true`, as in `app.phishing`), and 200 legitimate. State `{"email": body[:3000]}`.

Source: `kudzaiprichard/aura-phishing-email-corpus` @ `539567cee21d03c83bd2fb1b142c18a80904eb72`, a byte-identical mirror (MD5s match Zenodo's) of *Phishing Email Curated Datasets*, Champa, Rabbi and Zibran 2024, doi:10.5281/zenodo.8339691. It is not in Laya's training mix.

| Class | File | Cases |
|---|---|---|
| phishing | `Nazario.csv`, the Nazario phishing corpus | 100 |
| phishing | `Nigerian_Fraud.csv`, advance-fee fraud | 100 |
| legitimate | `CEAS_08.csv`, label 0 | 100 |
| legitimate | `TREC_07.csv`, label 0 | 100 |

Spam is left out, since the criteria call a promotional email legitimate. So is SpamAssassin's ham: 1,401 of a 1,500-row sample match a `zefang-liu/phishing-email-dataset` row by the exact or jaccard rule below. The legitimate class is mostly mailing-list mail.

Candidates are the first 400 of each file's seeded shuffle, 1,600 in all; 6 under five words are dropped. The rest are checked against every row of `zefang-liu/phishing-email-dataset` @ `34085a03` (18,650, `Email Text`), `SetFit/enron_spam` @ `1916f66c` (train and test, 33,716, `message`) and the 800 states of the frozen `app.phishing` and `app.email_spam`:

| Rule | zefang-liu | enron_spam | frozen suites |
|---|---|---|---|
| exact | 0 | 0 | 0 |
| jaccard | 21 | 41 | 3 |
| contained | 42 | 71 | 1 |

98 of the 99 candidates these remove are Nigerian letters. Within suite: 127 more (Nigerian_Fraud 41, Nazario 36, TREC_07 36, CEAS_08 14). 226 of 1,594 removed; survivors: Nazario 358, Nigerian_Fraud 261, CEAS_08 385, TREC_07 364. The first 100 of each, in shuffle order, are the suite.

## held.support_triage

400 cases, 40 per queue, gold `{"queue": {"idx": i}}`, i the queue's position in `bench_apps.py`'s `QUEUES`. State `{"subject", "body": body[:3000]}`; 30 have no subject.

**Generation.** `zen6` on `api.hanzo.ai`, served as `qwen/qwen3.8-flash` (184 of 187 calls; the gateway named the other 3 `zen6`), temperature 1.0, streamed: 510 English tickets, 60 for Technical Support and 50 for each other queue, 2 to 5 per call. Each ticket gets a specification drawn from `Random("13/<queue>/<i>")`: industry (30), product or service (35), length (1–3 sentences, 60–120 words, 150–250 words; 3:5:2), tone (8), writer (8, from fluent professional to hurried with typos), a subject line for 90%, and for 30% a boundary case that also touches a neighbouring queue while its request clearly belongs to its own (143 tickets). The prompt lists all ten queues with the harness's descriptions and requires that a reader route the ticket to its queue and no other.

**Label check.** `zen5`, served as `z-ai/glm-5.3`, temperature 0, answers the harness's instruction with its ten options and descriptions, verbatim, for each ticket's state. It agrees with the generation label on 503 of 510 (98.6%); on boundary cases 139 of 143 (97.2%). Disagreements: General Inquiry 5 (to Customer Service 3, Sales and Pre-Sales 1, IT Support 1), Human Resources 1, Technical Support 1. Only agreed tickets are kept.

**Dedup.** Against all 61,765 rows of `Tobi-Bueck/customer-support-tickets` @ `ddf1c81a` (its three CSVs, every language, subject and body) and the 400 frozen `app.support_triage` states: 0 removed by any rule, 0 within suite. The largest share of a ticket's 5-grams found in any one Tobi-Bueck row is 0.083. Positive control: 20 Tobi-Bueck rows, uppercased and with `.` replaced by `!`, are all removed.

The agreed tickets of each queue are shuffled with seed 13 and the first 40 kept.

## Near-duplicate rules

Texts are lowercased and split into `\w+` words; a text's shingles are its set of word 5-grams. A candidate is dropped when, against any one reference text:

- **exact**: the two are equal after lowercasing and collapsing whitespace;
- **jaccard**: |A ∩ B| / |A ∪ B| ≥ 0.5;
- **contained**: |A ∩ B| / |A| ≥ 0.5, A the candidate's shingles; counted only where jaccard did not fire. Jaccard alone misses a copy inside a longer text: a quoted or forwarded email, a template with a different tail;
- **within suite**: a surviving candidate is dropped when |A ∩ B| / min(|A|, |B|) ≥ 0.5 against an earlier survivor.

A candidate can match several rules, so per-rule counts overlap; "removed" counts each once.

## Laya

`harness/three_way.py kai --states held/states.json.gz`: Laya 0.3.20's reference runtime, CPU f32, `hanzoai/kai-1` @ `b50502c2` (Laya's weights), every question under each checkpoint and the checkpoint the router picks per case (English for all of support triage; English for 394 phishing cases, multilingual for 6). On four cases of each frozen suite the `--states` path reproduces `results/laya/preds.json.gz` to within 1e-6.

Scored with `merge.py`'s `score` and `routed`; `merge.py` itself reads only `results/`. The frozen suite's number, from `results/scores.json`, is beside each.

| Suite | Backend | acc | macro F1 | ECE | Brier | frozen acc |
|---|---|---|---|---|---|---|
| held.phishing | laya (routed) | 0.923 | 0.922 | 0.028 | 0.114 | 0.983 |
| held.phishing | laya:english | 0.925 | 0.925 | 0.022 | 0.106 | 0.980 |
| held.phishing | laya:multilingual | 0.908 | 0.907 | 0.087 | 0.170 | 0.993 |
| held.phishing | laya:typed-decisions | 0.795 | 0.791 | 0.093 | 0.267 | 0.940 |
| held.support_triage | laya (routed) | 0.580 | 0.549 | 0.093 | 0.559 | 0.503 |
| held.support_triage | laya:english | 0.580 | 0.549 | 0.093 | 0.559 | 0.503 |
| held.support_triage | laya:multilingual | 0.588 | 0.546 | 0.146 | 0.598 | 0.540 |
| held.support_triage | laya:typed-decisions | 0.658 | 0.625 | 0.251 | 0.547 | 0.505 |

All 800 questions answered by every checkpoint. Routed Laya on held.phishing: legitimate 195/200, phishing 174/200. On held.support_triage, per queue: Billing and Payments 40/40, Technical Support 35/40, Returns and Exchanges 33/40, Human Resources 32/40, Service Outages and Maintenance 29/40, Sales and Pre-Sales 26/40, Customer Service 24/40, Product Support 9/40, IT Support 4/40, General Inquiry 0/40. The frozen support suite follows Tobi-Bueck's label mix (120 of 400 Technical Support); this one is balanced, so the two accuracies are not the same measurement.

```sh
uv run --with numpy python -c '
import gzip, json, sys; sys.path.insert(0, "harness"); import merge
S = json.load(gzip.open("held/states.json.gz")); P = json.load(gzip.open("held/laya/preds.json.gz"))
for n, rows in S.items():
    g = [[gold, qs] for _, qs, gold in rows]
    for who, p in [("laya", merge.routed(P, n, g))] + [("laya:" + m, P["models"][m][n]["p"]) for m in merge.LAYA]:
        print(n, who, merge.score(g, p))'
```

## Kai

`bench preds` (hanzoai/decision), Kai stage a5 (weights `df1c16a2`; its predictions are kept with Kai), Metal bf16. Scored with `merge.score`, as Laya above.

| Suite | Backend | acc | macro F1 | ECE | Brier | frozen acc |
|---|---|---|---|---|---|---|
| held.phishing | kai a5 | 0.900 | 0.900 | 0.097 | 0.192 | 0.990 |
| held.support_triage | kai a5 | 0.417 | 0.361 | 0.132 | 0.730 | 0.490 |

Laya leads both. On phishing Kai loses 9 legitimate and 31 phishing (Laya 5 and 26). On support triage Kai answers Billing and Payments 111 times for 40 such tickets: pricing and payment words pull Sales and Pre-Sales (0/40) and Customer Service (6/40) there. Kai leads on IT Support (23/40 against 4/40), Service Outages and Maintenance and Product Support. The frozen suites' rows are Laya's training rows; these are not, and Kai's lead on the frozen phishing suite does not hold on them.

## Reproduce

```sh
cd decision
HANZO_TOKEN=$(hanzo auth token) uv run --python 3.11 python held/build.py generate   # exits 3 while work remains; rerun
HANZO_TOKEN=$(hanzo auth token) uv run --python 3.11 python held/build.py check      # likewise
uv run --python 3.11 --with huggingface_hub python held/build.py build
LAYA_SRC=/path/to/laya uv run --python 3.11 --with torch --with pandas --with pyarrow --with datasets --with "$LAYA_SRC" \
  python harness/three_way.py kai --states held/states.json.gz --out held/laya   # preds_kai.json, gzipped to preds.json.gz
```

`generate` and `check` stop starting calls after 480 s (a token lives about 11 minutes) and resume from their files. They are the only steps that call a model and their outputs are committed, so `build` reproduces the suites exactly.
