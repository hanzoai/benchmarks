# decision/capability

What a decision model can do beyond the frozen 62 suites, measured on Kai, Laya and Jev with the same questions. Each suite's docstring states its data, seed, variants and metrics; results merge into `results/<suite>.json`, and `results/cap.json` holds every key as `cap/<suite>/<who>/<metric>`.

| suite | measures |
|---|---|
| `cardinality` | choice over K = 4 … 100,000: accuracy, recall@k, rejection, truncation, time; Laya's own recipes (`wide.`, `sl.`) |
| `questions` | 1 … 1,000 typed questions on one state: latency p50/p95, questions/s, Jev cost |
| `joint` | five dependent questions with known rules: per-variable accuracy, exact match, rule violations |
| `sensors` | HAR, bearing, turbofan remaining life, machine sound: text renderings for the baselines |
| `invariance` | option order, noul side swap, label aliases |
| `calibration` | ECE, Brier, risk–coverage, split conformal coverage at 90/95% over every answer on disk |
| `refresh` | a program re-run after one evidence change: nodes run, time against a cold re-run |
| `deploy` | offline in a no-network sandbox, data leaving the machine, self-hosting, fee, pinning |
| `orig` | the 62 frozen suites through `harness/merge.py` |

```sh
./py cardinality.py --who laya,jev            # a suite's baselines; ./py is uv with Laya 0.3.20 ($LAYA_SRC)
./py run_all.py --kai hanzoai/kai@REV --bench BENCH   # every suite for one Kai checkpoint, baselines kept
```

Jev's key is read from `~/scratch/capability/.or_key` (never tracked); every call is ledgered in `results/jev_spend.json` and refused past `JEV_CAP_USD` (5). A failure — refusal, truncation, error, timeout — is counted in `unanswered`/`rejected`, never dropped. `CAP_N=5 CAP_RESULTS=dir` is a smoke run.
