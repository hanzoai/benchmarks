# CronQuestions — two temporal fact stores, one plan

The same 327,983 Wikidata facts with start and end years, and the same 26,168
test questions, asked of Hanzo's graph assertion plane (`apps/graph` in the
cloud source) and of Semantica's temporal query engine. Both run in-process on
one machine; nothing crosses a network and no model reads anything. How each
store is driven, and why, is in [METHOD.md](METHOD.md).

| test, Hits@1 | all | simple_entity | simple_time | before_after | first_last |
|---|---|---|---|---|---|
| control: the plan over dictionaries | 99.88% | 100.00% | 100.00% | 98.56% | 100.00% |
| Semantica 0.7.0 | 99.88% | 100.00% | 100.00% | 98.56% | 100.00% |
| Hanzo graph, the API's clock (`hanzo-wire`) | **99.88%** | **100.00%** | 100.00% | 98.56% | 100.00% |
| Hanzo graph, replayed clock (`hanzo-replay`) | 99.88% | 100.00% | 100.00% | 98.56% | 100.00% |

Questions: 7,812 · 5,046 · 2,151 · 11,159. Intervals are in each
`runs/*/metrics.json`; `time_join` (3,832) is not covered, and METHOD.md says
why. All three stores give the control's answer to every covered question;
before_after at 98.56% is the plan's own ceiling.

| | load, 327,983 facts | query p50 | query p99 |
|---|---|---|---|
| Semantica 0.7.0 | 0.1 s — a list of dicts, no index | 5,357 ms | 7,531 ms |
| Hanzo graph, the API's clock (`hanzo-wire`) | 116 s — 655,856 assertions, 284 MB | 0.063 ms | 2.4 ms |
| Hanzo graph, replayed clock (`hanzo-replay`) | 145 s — 655,966 assertions, 284 MB | 0.058 ms | 2.1 ms |

Per-op figures are in `runs/*/metrics.json`. The Hanzo rows time every one of
the 27,096 calls; the Semantica rows time 50 calls of each op, in full, and
answer the rest from one call per distinct instant (METHOD.md). The Hanzo rows
were taken at a one-minute load average of 19 to 42 on a shared machine, and
each run records the load it had; the Semantica row at 11 to 19.

## What it says

**Both stores answer everything the plan can.** Hanzo's rows are the control's,
question for question, through `POST /v1/graph` and `POST /v1/graph/resolve` as
any caller uses them — the replayed clock changes nothing, which is the point:
when a fact became known no longer decides what the world was.

**The difference is the price of a question.** A point-in-time read about one
entity costs Hanzo one indexed read of that pair, 0.06 ms at the median.
Semantica's calls take no entity, so every question about one player
reconstructs all 328k facts at that year, deep copy included: 5.4 s. That is
about 85,000 times the cost for the same answer. Semantica loads faster
because it builds nothing — the load is a list — and Hanzo's 116 s is admission,
content addressing, two index trees and the full-text index for 655,856
assertions.

**What changed to get here** (cloud `1fffdf408`). The first run of this lane
answered 70.03% through the API and 0.00% on simple_entity: `as_of` bounded
when the plane knew a fact, not when it was so, so history filed today was
invisible to a question about its own year. And a retraction retracted the
whole pair, so one holder's term ending erased every other holder. A read now
takes the two instants apart — `as_of` for the world, `as_known` for what had
been heard — a statement carries its own `until`, and a relation holds one
value at a time or many, as the organization declares it. Two runs of the
harness along the way found two more defects of the new code before it
shipped: `until` stored as zero for "open" collided with 1970-01-01, the end
of every term through 1969; and two accounts of one statement filed together
were treated as a correction of one by the other.

**Found in the wire run:** 110 facts start in a year after today — Wikidata
states planned terms — and admission refuses an `at` more than five minutes
ahead of the server clock. No covered question asks about them.

## Found along the way

- **Hanzo: year 1 was refused as no instant** (fixed in `1fffdf408`). `admit`
  tested `At.IsZero()`, and `0001-01-01T00:00:00Z` is Go's zero time. 7 facts
  here.
- **Hanzo: a read truncated without saying so** (fixed in `1fffdf408`).
  `GET /v1/graph` returned at most 10,000 assertions with no field saying it
  stopped; it now reports `truncated` as `resolve` and `neighbors` do.
- **Semantica: one inverted interval stops every point-in-time query.**
  `GraphBuilder.build` accepts a relationship whose `valid_from` is after its
  `valid_until` (`rejected_relationships: 0`), and every later `query_at_time`
  on that graph raises `ValueError: Temporal intervals must satisfy start <=
  end.` This KG has 652; the lane drops them for both stores.
- **Semantica: `query_time_range(…, "9999-12-31")` raises `OverflowError`.**
  The day-granularity end is widened past `datetime.max`. `TemporalBound.OPEN`
  works, and is what the lane passes.

## Run

```bash
bash cronquestions/run.sh           # test; `valid` for the other split
```

It fetches `data_v2.zip` into `cronquestions/data/` (gitignored) if it is not
there, then:

```bash
python3 cron.py facts                  # data/facts.tsv, what both stores load
python3 cron.py plan test              # data/plan-test.jsonl, the store calls
python3 cron.py exact test             # the control
# the graph store, compiled into its own package from the cloud source
(cd $CLOUD_SRC && GOWORK=off go test -c -overlay <overlay.json> -o graph.test ./apps/graph)
./graph.test -test.run '^TestCronQuestions$' -test.timeout 0 \
  -cq.facts … -cq.plan … -cq.out … -cq.clock wire|replay
.venv/bin/python temporal.py data/facts.tsv data/plan-test.jsonl data/results-semantica-test.jsonl
python3 cron.py score test <row> data/results-<row>-test.jsonl
python3 cron.py site test > benchmarks-cronquestions.json   # what hanzo.ai renders
```

`run.sh` writes the overlay, which maps `apps/graph/cronquestions_test.go` to
`_graph_test.go` here; the cloud tree is not modified. The cloud source is found
as the other lanes find it (`CLOUD_SRC`, `../cloud`, `~/work/hanzo/cloud`);
Semantica is `SEMANTICA_SRC` (default `~/work/semantica/semantica`), installed
editable into `cronquestions/.venv` with uv. `SAMPLE` sets how many Semantica
calls per op are timed (default 50). Before each store runs, `run.sh` waits up
to ten minutes for the one-minute load average to fall under 2, and every run
records the subject's commit and the load it had in its `meta.json`.

Data: `data_v2.zip`, 83,537,446 bytes, sha256
`0a2f77148977afb02a159b23cc942925b9455c98fcbe61ef164706324fd4734e`; unzipped,
`kg/full.txt` is 10,321,920 bytes and `questions/test.pickle` 7,864,820.
