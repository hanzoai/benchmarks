# CronQuestions — two temporal fact stores, one plan

The same 327,983 Wikidata facts with start and end years, and the same 26,168
test questions, asked of Hanzo's graph assertion plane (`apps/graph` in the
cloud source) and of Semantica's temporal query engine. Both run in-process on
one machine; nothing crosses a network and no model reads anything. How each
store is driven, and why, is in [METHOD.md](METHOD.md).

| test, Hits@1 | all | simple_entity | simple_time | before_after | first_last |
|---|---|---|---|---|---|
| control: the plan over dictionaries | 99.88% | 100.00% | 100.00% | 98.56% | 100.00% |
| Semantica 0.7.0 | **99.88%** | **100.00%** | 100.00% | 98.56% | 100.00% |
| Hanzo graph, replayed clock (`hanzo-replay`) | 95.58% | 85.59% | 100.00% | 98.56% | 100.00% |
| Hanzo graph, the API's clock (`hanzo-wire`) | 70.03% | **0.00%** | 100.00% | 98.56% | 100.00% |

Questions: 7,812 · 5,046 · 2,151 · 11,159. Intervals are in each
`runs/*/metrics.json`; `time_join` (3,832) is not covered, and METHOD.md says
why.

| | load, 327,983 facts | query p50 | query p99 |
|---|---|---|---|
| Semantica 0.7.0 | 0.1 s — a list of dicts, no index | 5.4 s | 7.5 s |
| Hanzo graph, replayed clock (`hanzo-replay`) | 266 s — 1,311,918 assertions, 478 MB | 0.051 ms | 3.0 ms |
| Hanzo graph, the API's clock (`hanzo-wire`) | 174 s — 1,311,666 assertions, 477 MB | 0.044 ms | 2.6 ms |

Per-op figures are in `runs/*/metrics.json`. The Hanzo rows time every one of
the 27,096 calls; the Semantica rows time 50 calls of each op, in full, and
answer the rest from one call per distinct instant (METHOD.md). Taken at a
one-minute load average of 11 to 19. This machine is shared: sampled every 15
seconds for three days — 19,975 readings, median 10.4 — its load average never
fell below 4.65, so these are numbers from a busy machine and each run records
the load it had.

## What it says

**Semantica answers everything the plan can.** Its row is the control's,
question for question; before_after at 98.56% is the plan's own ceiling. The
price is the call: neither query takes an entity, so asking about one player
reconstructs all 328k facts at that year, deep copy included.

**Hanzo answers every history question the same, and no point-in-time question
about history filed today.** `as_of` bounds when the plane *knew* a fact — the
later of `seen` and its own clock at the write — not when the fact was so.
Through `POST /v1/graph` that is the moment of loading for every backfilled
fact, so `resolve` at any past year holds nothing: 0 of 7,812. It is
deliberate (HIP-1198 calls a caller-chosen as-of "backdating"), and it means
the plane has no valid-time query: `at` is stored and returned, and no
operation reads it.

**With the clock replayed, `resolve` answers 85.6%.** Setting the write clock to
each assertion's own instant — only code inside the package can — makes
knowable the same as valid time. `resolve` still returns one winner per
(entity, relation), so two facts in force at once on one pair collide, and the
retraction of the one that ended is the newest thing about the pair. Every one
of the 1,126 misses is that: 552 positions, 540 teams, 29 employers, 4 awards,
1 spouse. Mark Ford in 1998: Leeds 1993–97, England U21 1996, Burnley 1997–99.
Leeds' retraction at the end of 1997 is newer than Burnley's opening at its
start, so nothing is in force in 1998; the answer is Burnley.

Filing no retraction at all — letting a later assertion supersede an earlier
one — would answer 97.4% to 98.8% of those questions by the same rule,
depending on how same-year ties fall. That is arithmetic over `facts.tsv`
rather than a run, and the price of it is that every fact that ended would read
as still in force, which is the distinction this plane exists to keep.

## Found along the way

- **Hanzo: year 1 is refused as no instant.** `admit` tests `At.IsZero()`, and
  `0001-01-01T00:00:00Z` is Go's zero time, so an assertion dated then is
  refused with "at is required" while its retraction is admitted, leaving a
  close with no open. 7 facts here, 14 assertions. `…00:00:01Z` is accepted.
- **Hanzo: a read truncates without saying so.** `GET /v1/graph` returns at most
  10,000 assertions and `graphReadOut` has no field that says it stopped;
  `resolve` and `neighbors` both report theirs. Not reached by these questions,
  but one position in this KG — United States representative, 6,843 facts —
  files 13,686 assertions on one pair.
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
