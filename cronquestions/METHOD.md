# Method

## Data

CronQuestions `data_v2.zip` (Saxena et al., ACL 2021; the release with the
`{tail2}` fix), from the Drive folder the CronKGQA README links. The KG is
`kg/full.txt`: 328,635 facts `(subject, relation, object, start year, end
year)` over 125,726 Wikidata entities. 652 facts have start > end; `cron.py
facts` drops them for both stores (Semantica cannot answer any point-in-time
query while one is loaded), leaving 327,983 in `data/facts.tsv`. Both stores
load that file and nothing else.

Questions: the test pickle, 30,000 questions. Covered: `simple_entity`
(7,812), `simple_time` (5,046), `before_after` (2,151), `first_last` (11,159) —
26,168. Not covered: `time_join` (3,832). 1,407 of those name their second
position only in the question text (`{tail2}`), which the annotation does not
carry, so they cannot be built from annotations at all; the other 2,425 are an
overlap join — who else was in this team while that player was — which one
`history` call would answer. They were out of this pass's scope and were not
run.

The valid pickle is where the answer rules were chosen (26,122 covered). Only
the control was run on it; the stores ran on test, once.

## Time

A fact holds for whole years: it opens at `<start>-01-01T00:00:00Z` and closes
at `<end>-12-31T23:59:59Z`. A question about year T asks at
`T-07-01T00:00:00Z`. Both drivers use these instants.

## The plan

`cron.py plan` turns each question's annotation (entities, time, relation,
before/after, first/last — the dataset provides all of them) into store calls:

| call | returns |
|---|---|
| `at(e, r, dir, T)` | what is in force for (e, r) at T |
| `history(e, r, dir)` | every interval of (e, r) |
| `touch(e)` | every interval of any relation into or out of e |

`dir` is `out` (e is the subject) or `in` (e is the object). The answer is a
pure function of the returned intervals (`cron.answer`), identical for every
store:

| type | calls | answer |
|---|---|---|
| simple_entity | `at` | the interval with the latest start |
| simple_time | `history` on the head | the earliest start among intervals to the tail |
| first_last | `history` | first: earliest start; last: latest end — the entity, or that year |
| before_after | `history` (P39: the position, `in`; else the head, `out`) | before: of the others that start before the anchor starts, the latest end; after: of the others that end after the anchor ends, the earliest start |
| before_after, event | `touch` on the event, then `history` on the position | the same, with the event's span as the anchor |

These rules were chosen on **valid** by answering from the KG directly and
frozen; test ran once. Nothing is tuned per store. The `kg` row is that
control: the same calls answered by dictionaries over `facts.tsv`, which is
the ceiling the plan can reach.

Metric: Hits@1 — the answer is in the question's gold set — per type and over
all covered questions, with bootstrap 95% intervals. No answer scores 0.

## Hanzo — `apps/graph`

`_graph_test.go` is compiled into the package by `go test -overlay` from the
cloud source; nothing in the cloud tree changes. It opens the store as
production does minus the key (`sqlite.OpenDB`, one connection,
`openStore`), and every assertion goes through `fromWire`, the API's own
admission. Each KG fact is four assertions:

- an edge `(s, r, o)` and its inverse `(o, ~r, s)` at the open instant;
- a retraction of each — an empty property on the same pair — at the close.

The evidence is the KG line, so an open and its close pair. The inverse exists
because `resolve` answers one (entity, relation); "who held P in T" needs the
fact filed about P.

| call | store |
|---|---|
| `at` | `read(entity, relation, as_of, newest)` then `Resolve` — what `POST /v1/graph/resolve` does |
| `history`, `touch` | `read(entity[, relation])`, opens paired with closes by evidence — what `GET /v1/graph` does |

The store's `as_of` bounds **knowable** — the later of `seen` and the server
clock at the write — not `at`. So the clock decides everything, and the lane
runs two:

- **wire** — the clock is now, as for any caller of `POST /v1/graph`. History
  filed today is knowable today, so `resolve` at any past year holds nothing.
- **replay** — the clock is each assertion's own instant, as if a pipeline had
  filed each fact when it became so. Only in-package code can set this; the
  API cannot.

`resolve` returns one winner per (entity, relation). A relation with two facts
in force at once (a club and a national team) resolves to whichever is newest,
and a retraction of one is the newest thing about the pair until something
else is asserted. That is the store's model, not a driver choice, and the
simple_entity row measures it.

Latency: every call, in-process, from before the read to the returned rows.

## Semantica — `TemporalGraphQuery`

`temporal.py` builds the graph with
`GraphBuilder(enable_temporal=True).build({"relationships": …})`, each
relationship carrying `valid_from` / `valid_until`, and answers with the
documented calls:

| call | store |
|---|---|
| `at` | `query_at_time(graph, "", at_time=T)`, then the relationships naming (e, r) |
| `history`, `touch` | `query_time_range(graph, "", 0001-01-01, OPEN)`, then the same |

Neither call takes an entity — `query` is documented as unused — so the answer
depends only on the instant. Each distinct instant is called once (339 calls)
and every question is answered from that call's output. Latency is timed first,
on the first 50 calls of each op in plan order, back to back, each made in full
— the store call plus the filter — and each is checked against the shared
answer afterwards (`timed_calls_differing_from_shared`, 0 in every run).

## Load

Wall time from the parsed fact list to a store ready to answer. For Hanzo
that is admission, digest and SQLite writes of four assertions per fact
(index and full-text triggers included); for Semantica it is `build`, which
copies the dicts and indexes nothing.

## Host

One Apple M1 Max, both stores in-process, nothing on the network. The machine
is shared, so a timing is only taken on a quiet one: the graph driver is
compiled first, and before each store runs `run.sh` waits for the one-minute
load average to fall under 2. Every `meta.json` carries `load_1m`: the reading
at the start and the peak sampled through each timed phase (every second for
the graph store, after every timed call for Semantica). A peak above 2 means the
timing was taken on a busy machine, and the table says so.

Hits@1 does not depend on the machine: every store answers deterministically,
and a rerun reproduces it question for question.
