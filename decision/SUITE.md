# The Decision Suite

Kai against `typesafe/jev-1.13` on the sixteen rows hanzo.ai publishes, each with the file it is read from and one command that reads it again. The suite's membership was fixed on 2026-10-15: these sixteen rows and nothing else.

Rows 1 to 15 are recomputed from committed files by scripts in this directory, with the standard library alone except numpy for `merge.py`, `datasets` for CLINC150 and `pyarrow` for the jailbreak sets; row 16 is the live price list. Jev is never called: its numbers are its recorded answers, and every scorer reads them as `--jev recorded`.

| # | row | Kai | Jev | result file | command |
|---|---|---|---|---|---|
| 1 | AG News | .9425 | .8600 | `results/kai-1/scores.json` | `uv run --with numpy python harness/merge.py --kai results/kai-1/preds.json.gz --out results/kai-1` |
| 2 | DAIR emotion | .9350 | .6025 | same | same |
| 3 | Banking77 | .9075 | .8350 | same | same |
| 4 | Support triage | .4400 | .3650 | same | same |
| 5 | Email spam | .9975 | .9775 | same | same |
| 6 | Phishing | .9900 | .9000 | same | same |
| 7 | Toxicity | .8025 | .6625 | same | same |
| 8 | RAG relevance | .6800 | .6200 | same | same |
| 9 | Model routing | 1.0000 | .9774 | same | same |
| 10 | Typed decisions | .7590 | .7355 | same | same |
| 11 | MASSIVE, 51 languages, macro | .9096 | .8902 | same | same |
| 12 | Choice among 16 options | 374 / 400 (.9350) | 341 / 400 (.8525) | `capability/results/cardinality.json` | `python capability/cardinality.py --score` |
| 13 | Choice among 77 options | 363 / 400 (.9075) | 337 / 400 (.8425) | same | same |
| 14 | Same request three times, identical answers | 4,200 / 4,200 | 1,858 / 4,200 | `stability/results/*.json.gz` | `python stability/score.py` |
| 15 | False alarms on real benign prompts (in the wild) | 24 / 600 (4.0%) | 126 / 600 (21.0%) | `jailbreak-suite/results/report.txt` | `python3 jailbreak-suite/score.py` |
| 16 | Price, per million input tokens | $0.021 | $0.042 | `GET https://api.hanzo.ai/v1/models` | `curl -s https://api.hanzo.ai/v1/models` |

Commands run from `decision/`. Rows 1 to 11 are accuracy as `merge.py` reports it, over 400 questions a suite (model routing 399, typed decisions 2,000; MASSIVE the mean over 51 languages of 100), every question answered by both; rows 12 and 13 are correct answers over all questions.

## What each row was measured on

| rows | Kai | Jev | measured |
|---|---|---|---|
| 1-11 | kai-1: the a7-512 checkpoint, `model.safetensors` SHA-256 `0834a74f2d140642a453373da09e5a128e3d2c8d9e8bb1dcaf86d7210a4ecdfc`, `bench preds` on CUDA in BF16 | `typesafe/jev-1.13`, answered as `typesafe/jev-1.13-20260917`, through OpenRouter | Kai 2026-10-03, Jev 2026-09-25 |
| 12-13 | kai-1, the same weights, `bench cap --suites cardinality` on CUDA in F32 | the same Jev | Kai 2026-10-03, Jev 2026-09-27 |
| 14 | the kai-1.2 release (the same base weights and its yes/no reader `3b85b6bd…`), `kai serve --device cpu`, four replicas | the same Jev | 2026-10-14, both |
| 15 | the kai-1.2 release, `kai serve --device cpu` | the same Jev | 2026-10-14, both |
| 16 | the list price of model `kai` | the list price of `typesafe/jev-1.13` | read 2026-10-15 |

## Where each number is

**Rows 1 to 11, the frozen harness** (`README.md`): 9,499 cases built by the Laya 0.3.20 harness builders at seed 13, `results/states.json.gz`, gold in `results/questions.json.gz`. Kai's answers are `results/kai-1/preds.json.gz`, Jev's `results/jev/preds.json.gz`; `merge.py` scores both with the harness's own metric code and writes `results/kai-1/scores.json` and `table.md`. `python harness/digest.py results/kai-1/preds.json.gz` prints each suite's digest, equal to the `preds sha256` in the notes of that suite's research run (`https://api.hanzo.ai/v1/research/runs?org=hanzo`), Kai's and Jev's alike. The harness's twelfth suite, jailbreak (toxic-chat), is not a row: there Kai reads 91.8% and Jev 94.0%, in the same file.

**Rows 12 and 13, choosing among many options** (`capability/README.md`): Banking77's 400 harness cases, at 16 options the gold label and its 15 nearest labels by word overlap, at 77 every Banking77 label; `cardinality.py` rebuilds the same cases, and `--check` scores kai-1's and Jev's recorded answers on the rebuilt cases and reproduces both records question by question. The same file holds the other sizes, the board's rows aside: 4 options Kai 96.8%, Jev 90.5%; 150 (CLINC150) Kai 90.8%, Jev 94.0%; 1,000 and more (WordNet) both near zero.

**Row 14, stability** (`stability/README.md`): 4,200 requests, each sent three times; identical when the three answers are the same decision with the same probabilities. The answers' digests are committed per request.

**Row 15, false alarms on real benign input** (`jailbreak-suite/README.md`): in-the-wild jailbreak prompts' benign side (TrustAIRLab, `regular_2023_12_25`), 600 human-written prompts, under the frozen harness's own jailbreak question. On the suite's whole real-attack pool Kai flags 3.6% of 1,006 benign prompts and Jev 13.0%; on that pool Kai also catches far fewer attacks, 26.9% of 1,163 against Jev's 77.4% (AUROC .725 against .896). Both lines are in `results/report.txt`.

**Row 16, price**: the `pricing` of each model in `GET https://api.hanzo.ai/v1/models`, which answers without a key: `input_per_million` 0.021 for `kai` and 0.042 for `typesafe/jev-1.13`, output 0 for both. A Kai decision bills the request's input tokens in Kai's tokenizer; Jev's recorded harness run reports $0.2486 for 5,919,448 input tokens, $0.042 per million.

```sh
curl -s https://api.hanzo.ai/v1/models | python3 -c 'import json,sys; [print(m["id"], m["pricing"]["input_per_million"]) for m in json.load(sys.stdin)["data"] if m["id"] in ("kai", "typesafe/jev-1.13")]'
```

## Asking Kai again

Each row's directory has a runner that sends its cases to `POST /v1/decisions` (api.hanzo.ai with `HANZO_API_KEY`, or a local `kai serve` by `--url`):

```sh
export HANZO_API_KEY=...
python harness/run_kai.py && uv run --with numpy python harness/merge.py               # rows 1-11
uv run --with datasets python capability/cardinality.py --url https://api.hanzo.ai --out runs/kai   # rows 12-13
python stability/run.py --url https://api.hanzo.ai --out runs/kai.jsonl && python stability/score.py runs/kai.jsonl   # row 14
python3 -I jailbreak-suite/fetch.py data && uv run --with pyarrow python3 -I jailbreak-suite/build.py data items
python3 -I jailbreak-suite/read.py items/items.jsonl H runs/kai-H.jsonl --clean --same jailbreak-suite/results/kai-H.jsonl.gz
python3 jailbreak-suite/score.py --kai runs                                               # row 15
```

Kai's weights are not public, so a new run measures the Kai api.hanzo.ai serves when it runs, not the recorded bits: on 2026-10-15 that is kai-1.3, the kai-1.2 release with one more capability routed on a key no question here uses. kai-1.2 answers yes/no questions with a reader kai-1 does not have, and production runs on x86-64 CPUs where rows 1 to 13 were read on CUDA; its choices come from the same base weights. Each runner was run on a sample on 2026-10-15 through api.hanzo.ai, every answer served by kai-1.3, none refused:

| rows | sample | against the record |
|---|---|---|
| 1-11 | the first 5 cases of each of the 62 suites: 310 requests, 330 questions | 321 of 330 answers the same option as kai-1's record; 264 correct against kai-1's 266 on those questions |
| 12-13 | the first 40 cases at 4, 16, 77 and 150 options | 158 of 160 the same option; 40, 35, 33 and 37 correct against kai-1's 40, 36, 34 and 37 |
| 14 | the first 100 requests, three times each | 100 of 100 identical |
| 15 | the first 150 clean in-the-wild items under H: 32 attacks, 118 benign | 150 of 150 flagged as kai-1.2's record flags them (largest difference in p .018): 0 of 118 benign and 16 of 32 attacks, now and recorded |
