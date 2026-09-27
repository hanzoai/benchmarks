# decision/capability

What a decision model can do beyond the frozen 62 suites, measured on Kai, Laya and Jev with the same cases. Every suite is `bench cap` in `hanzoai/decision` (Rust, no Python): it builds its cases, puts them to each backend, and merges `results/<suite>.json`, `{"meta", "keys", "detail"}`, every key `cap/<suite>/<who>/<metric>`. `bench speed` writes `results/questions.json`; `bench tex` writes the paper's tables from these files.

| suite | measures |
|---|---|
| `orig` | the 62 frozen suites for a Kai checkpoint beside Laya and Jev, scored as `harness/merge.py` scores (`bench score` writes its `scores.json`) |
| `cardinality` | choice over K = 4 … 100,000: accuracy, recall@k, rejection, truncation, time; Laya's own recipes (`wide.`, `sl.`) and a bi-encoder shortlist (`bi.`) for every backend |
| `joint` | five dependent questions with known rules: per-variable accuracy, exact match, rule violations, and after projection onto the rules |
| `media` | human activity (UCI HAR), turbofan remaining life (C-MAPSS FD001), valve sound (MIMII): text renderings for the baselines, the signals as evidence for Kai |
| `invariance` | option order, noul side swap, label aliases |
| `refresh` | a program re-run after one evidence change: questions asked, time against a cold re-run |
| `deploy` | offline in a no-network sandbox, data leaving the machine, self-hosting, fee, pinning |
| `conformal` | ECE, Brier, risk–coverage, split conformal coverage at 90/95% over every answer on disk |
| `questions` | `bench speed`: 1 … 1,000 questions on one state and 1 … 128 cases a call, latency p50/p95 and questions/s; Kai (and `kai-cold`, its option cache emptied each call) and Laya on one device and dtype, their calls interleaved, Laya's multilingual checkpoint (Kai's encoder) bare and its typed-decisions one (ModernBERT-large) as `-agent`; Jev over the network |

```sh
B=bench   # hanzoai/decision: cargo build --release -p bench --features metal
$B cap --harness decision --who kai,laya,jev --kai <checkpoint>              # every suite
$B cap --harness decision --suites cardinality --who kai --kai <checkpoint>   # one suite, one backend; the others' results stay
$B speed --states decision/results/states.json.gz --results decision/capability/results \
  --who kai,kai-cold,laya --laya multilingual,typed-decisions --device metal --dtype f32 --kai <checkpoint>  # and --device cpu; --who jev once
$B score --harness decision --kai <preds.json.gz> --out scores.json          # merge.py's scores.json
$B tex --harness decision --out <paper>/kai/tables                           # harness, languages, capability, speed
```

Laya is the three kai-1 checkpoints on the same runtime (`kai::joint`, at parity with Laya 0.3.20's reference: `results/laya/parity.json`), answered as the harness's engine answers, each case on the checkpoint Laya's router picks unless a suite names one. Jev is `typesafe/jev-1.13` through OpenRouter's Decisions API (`OPENROUTER_API_KEY`, else the file `OR_KEY_FILE` names; never tracked); every call is ledgered in `results/jev_spend.json` and refused past `--jev-cap` (USD 5). A failure (refusal, truncation, error, timeout) is counted in `unanswered`/`rejected`, never dropped; a backend or suite that fails is recorded and the rest still run. Cases are drawn as the Python reference drew them (CPython's `random`, numpy's PCG64 permutation), so a kept baseline reproduces; `--limit 5 --results <dir>` is a smoke run. `--data` (default `~/scratch/capability/data`) holds the sources (WordNet 3.0, UCI HAR, C-MAPSS, MIMII), fetched and checked against their pinned hashes when absent; `cases/*.json.gz` (MIMII audio among them, used, not redistributed) are never tracked.

The port was checked against the Python runs it replaces (4e57fb2): every case set is equal (C-MAPSS but one slope of a flat series, ~1e-16 either way), Laya's keys equal to four decimals in every suite except timings, Jev's within 0.03 (its answers drift between calls). Two Python results did not reproduce, by design: WordNet at K ≥ 1,000, whose labels took `hypernyms()[0]` from a set ordered by Python's string hash (four hash seeds gave four label spaces sharing 820–889 of 1,000 labels; the port names each by the relation with the greatest offset, keeping the 200 targets and 795 of the kept labels), and conformal's `joint` population, which read a 2-state smoke case file (n = 14; the port reads the 400 states, n = 2,000). The results here are the port's: Kai is stage A (`runs/a`, Metal bf16, running centers at zero), Laya and Jev rerun.
