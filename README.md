# hanzoai/benchmarks — unified benchmark + load framework for Hanzo cloud products

One place to prove what the cloud stack does under load and at scale. Before this,
cloud-product benchmarks did not exist as a framework — perf work was scattered across
unrelated repos (`engine-v4bench`, `enso-bench`, `lux/benchmarks`, `zap/bench`, GPU/
consensus/model harnesses). This is the home for **api.hanzo.ai / the `hanzoai/cloud`
unified binary and its subsystems** (gateway, ai, kms, commerce, iam, …).

## Layout

```
cloud/<suite>/      Go property + micro benchmarks that need no cluster (fast, CI-able)
  shard/            horizontal writer-scale routing (hanzoai/ha HRW/rendezvous)  ✅
k3s/                local N-pod INTEGRATION harness (k3s is installed at /usr/local/bin/k3s)
load/               HTTP/gRPC load profiles (k6 / ghz) — wired when the tools are present
```

Two tiers, on purpose:
- **Property/micro (`cloud/<suite>`)** — pure Go, deterministic, runs in seconds, proves
  an *invariant* (e.g. one-owner-per-org) and measures a *primitive* (routing ns/op). No
  cluster, so it runs in CI on every PR.
- **Integration (`k3s/`)** — stands the real StatefulSet up locally and drives end-to-end
  load, so throughput scaling and failover are measured against the actual binary.

## Run

```bash
make scale     # print the horizontal-scale proof (1M tenants across N=3/10/100 pods)
make bench     # routing throughput (ns/op, allocs) across ring sizes
make k3s-up    # (integration) stand up cloud StatefulSet N=3 in local k3s
make k3s-down
```

## What the shard suite proves (why horizontal scale is safe)

`cloud/shard` benchmarks the exact routing primitive the in-binary shard router uses —
`hanzoai/ha` HRW/rendezvous org→owner election — the thing that guarantees **no two pods
ever write one tenant's SQLite file** (the unrecoverable failure). Measured over **1,000,000
tenants** (see `make scale`):

| N pods | per-pod mean | stddev | max skew | verdict |
|-------:|-------------:|-------:|---------:|---------|
| 3      | 333,333      | 0.05%  | 0.10%    | dead-even |
| 10     | 100,000      | 0.31%  | 1.05%    | even |
| 100    | 10,000       | 0.98%  | 4.46%    | even |

- **One owner per org, deterministic** — 100k orgs × 6 re-elections all agree → the
  no-dual-writer invariant holds mathematically (`TestDeterministicSingleOwner`).
- **Even load** — 0.05% stddev at N=3 → no hot shard → write capacity scales ~linearly
  (per-org SQLite has no shared lock).
- **Minimal rebalance** — growing 4→5 pods remaps only **20.1%** of tenants (ideal 20%),
  so a scale-up moves the fewest tenant files (`TestMinimalReshuffleOnScale`).
- **Routing tax** — ~**545 ns/op at N=3** (~1.8M routes/sec/core); scales O(N) per lookup.

### Finding (benchmark-driven)
`ha.Owner` allocates O(N) per election (5 allocs @ N=3 → 102 @ N=100). Negligible at the
target N=3, but an allocation-free rendezvous in `hanzoai/ha` would help large rings — a
tracked optimization, not a blocker.

## Adding a suite
Drop `cloud/<name>/<name>_test.go` with `Benchmark*` (perf) and `Test*ScaleProof`-style
property tests that print with `-v`. Keep it cluster-free where possible; push end-to-end
load into `k3s/`.
