# hanzoai/benchmarks

Every benchmark for the Hanzo stack, in one repository, with the records they
produced. Clone it, run a lane, compare against the committed run.

## Two kinds of measurement, and they answer different questions

**Lanes** — one directory per claim, at the root. What a thing costs, measured,
with a control beside it. `brain/` `code/` `fleet/` `goroutine/` `sandbox/`
`cipher/` `egress/` `self/` `transport/` `pricing/` `market/`. The tables and
what each one found are in **[MEASURED.md](MEASURED.md)**; what competitors
publish, and where it was read from, is in **[naive.md](naive.md)**.

**Load and scale** — `cloud/` Go property benchmarks, `k3s/` an integration
harness that stands the real StatefulSet up, plus `bench-agents/`
`bench-inference/` `bench-serialize/` `bench-blockchain/`. Written up in
**[LOAD.md](LOAD.md)** and [METHODOLOGY.md](METHODOLOGY.md).

## Does this checkout work

```bash
make check                          # or: bash check.sh
CLOUD_SRC=/path/to/cloud make check # including the four that build the binary
```

Twelve lanes, in the order that needs the least, so the first failure names the
smallest missing piece. A lane whose data nobody has fetched is **skipped** and
says which command fetches it — a green over four silent skips is the same green
a broken suite prints, so it counts them separately.

## Run one

```bash
node fleet/fleet.mjs /tmp/fleet     # 1M dormant agents: bytes, write rate, resume
cd goroutine && go build -o /tmp/g . && /tmp/g
node sandbox/sandbox.mjs            # V8 context, isolate, hanzo-vm
node pricing/pricing.mjs            # what a call costs and what it could charge
bash transport/run.sh               # what an agent pays per call, per transport
bash self/run.sh                    # build it, boot it, ask each transport
bash cipher/run.sh                  # write a value, look for it on the disk
bash egress/run.sh                  # what leaves the machine
```

`BENCH_JSON=out.json` on any lane writes its rows to a file as well as the
terminal.

## What you need

Node 20+ and Go for everything; `uv` for the two Python readers in `brain/`.

**Four lanes build the cloud binary** — `self`, `egress`, `cipher`, `transport`
— because they measure a binary rather than a library. They look for the source
next to this repo, then at `~/work/hanzo/cloud`:

```bash
git clone https://github.com/hanzoai/cloud ../cloud
CLOUD_SRC=/path/to/cloud bash self/run.sh    # or name it outright
```

They do not clone it for you. A benchmark that fetches its own subject decides
which revision you measured.

`brain/` needs its vectors built once (`node brain/brain.mjs`, then
`embed-facts.mjs`) and a local Ollama for the embedder; `code/` needs
RepoBench-R fetched into `data/`. Both are gitignored — large, and derived.

## The records are here too

`brain/runs/` and `code/runs/` hold the predictions and metrics every published
table was generated from, committed. `node brain/results.mjs` rebuilds
RESULTS.md from them, and `brain/mab/freeze.mjs --tag=v1 --verify` re-runs the
frozen MemoryAgentBench lane and checks it still produces the same predictions.

That is the point of keeping them: a number you cannot re-derive is a claim, and
a claim is not a benchmark.

## Where a number came from

Lanes that measure time print their host, because they have to — the same lane
reads about twice as fast on an M4 Max as on an M1 Max. Frozen configurations
carry a digest of the engine files that decide their rows, so an edit to the
engine is visible against the record rather than silent. Commit hashes were
tried first and did not survive a rebase.
