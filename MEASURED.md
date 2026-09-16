# bench

One lane per claim a competitor makes about us, and two for the claims they
cannot make: that you can have the software, and what it costs to ask it for
something.

Every number below was taken between 2026-09-07 and 2026-09-11, and every script
here re-runs to produce it. Where we lose, the row says so — a benchmark suite
that only contains wins is a brochure.

**Say which machine.** "An M-series laptop" covered an M1 Max with 10 cores and
an M4 Max with 16, and the goroutine lane reads about twice as fast on the
second — 452 ns to spawn against 187, 347 ns to wake against 114, while the
memory figure moved by five bytes. A timing without its host is not reproducible
and not comparable, including against itself next month. Every lane that
measures time prints its host now, from `bench/host.sh`, and the tables below
carry it.

Timings are the median of the pass; memory is deterministic and has no range
**on a quiet machine**, which is a condition this line did not used to carry.

On a host at load average 3, the goroutine lane reads 573.0 MB and 601 bytes per
agent on every run — twelve for twelve, byte-identical, across three separately
built binaries. On a second host at load 17 to 73 the same lane read 594, 595,
596 and 599 bytes. Two things differ between those readings and this pass cannot
separate them: the machines are not the same machine, and only one of them was
busy. The cross-machine part is already known — an M1 Max and an M4 Max differ
by about five bytes here — so the honest statement is that determinism has been
observed under quiet conditions and variation of about 1% under load, cause
unresolved.

Take memory figures from an idle host, and say which one.

This is the same pass the paper cites, and it carries the ranges:
`hanzoai/papers` `hanzo-dormant-agents`. One set of numbers, one run behind
them — if you re-run and get different figures, update both.

```
bench/self/run.sh                   # build it, boot it, ask each transport: can you have this
bench/self/modules.sh               # and whether anyone else can fetch what it is built from
bench/egress/run.sh                 # and whether having it means anyone hears about it
bench/cipher/run.sh                 # write a value through the API, look for it on the disk
bench/transport/run.sh              # what an agent pays per call, per envelope
node fleet/fleet.mjs /tmp/fleet     # 1M dormant agents: bytes, write rate, resume
node fleet/cost.mjs                 # the same, as a monthly bill
cd goroutine && go build -o /tmp/g . && /tmp/g   # agent as goroutine; goja, gpython, wasm
node sandbox/sandbox.mjs            # cold start: V8 context, isolate, hanzo-vm
node pricing/pricing.mjs            # what a call costs, and what it could sell for
```

`node bench/platform.mjs` runs the five lanes above that measure the software
itself and writes `bench/benchmarks-platform.json` — the same numbers, as data,
for anything that renders them. Each lane emits its own rows, so a rerun that
changes a number changes the file, and a lane that fails leaves its section out
rather than a stale one in.

## What was measured

### Ownership — the row a hosted competitor has no way to fill

`self/run.sh` builds the binary from this repository, starts it, asks it what it
serves, and reaches one operation through every transport it opens.

| | measured |
|---|---|
| private modules required | **0** |
| modules the binary needs, fetchable with no credential | **127 of 127** |
| this module, published as | **v1.801.572** — the first semver release the repo has carried |
| build from source | 13 s |
| binary | 80 MB |
| boot to a healthy answer | **1.2 s** |
| operations served by default | 13 over 8 paths |

The second row is the load-bearing one. Counting private paths in `go.mod` is a
property of a file; asking the public Go proxy for every module the binary
actually needs, with no credential, is a property of whether anyone else can
build it. All 127 answer, and the run ends by asking for a module that does not
exist — 404, or the sweep above would not be evidence.

Everything else here measures what the software does; this measures whether you
can have it.

### Privacy — nothing in the default path phones anyone, including us

`egress/run.sh` starts the binary with no configuration, asks every transport for an
operation sixty times, and watches what it connects to throughout.

| | measured |
|---|---|
| attempts to leave | **0** |
| peers off this machine | **0** |

Two observers, because one of them can miss. A listener standing in for the
internet takes `HTTP_PROXY`, so every attempt is recorded with what it asked for
and timing cannot defeat it. `lsof` sampling watches the sockets directly and
**can** miss — the run reports how much it missed of traffic it generated
itself, which on this machine is all of it, so that row is corroboration and
never the proof. Both end pointed at something that does reach out, and the lane
fails if either reports nothing.

The claim is narrow and checkable: nothing in the default path phones home. A
deployment that enables a subsystem with an upstream connects to it, on purpose.

### At rest — the value is not in the file

`cipher/run.sh` writes a value nothing else could have written through two
operations, stops the server, and searches every file under the data directory.
The same binary runs twice.

| build, given a master key | result |
|---|---|
| `CGO_ENABLED=0` | 7 distinct headers · canary in **0** files |
| `CGO_ENABLED=1`, as built | **refuses**, and names the recipe |
| `CGO_ENABLED=1 -tags libsqlite3` | 7 distinct headers · canary in **0** files |
| control: `CLOUD_DEV_UNENCRYPTED=1` | 1 header, `SQLite format 3` · canary in **1** file |

The refusal is a result. cgo is on by default on macOS and that build links
ordinary SQLite, so given a key it stops rather than writing a plaintext store
and reporting success — which is what it did before the check existed.

Each store gets its own data encryption key, so seven files begin with seven
different ciphertexts; a plaintext run writes the same magic seven times.

The right-hand column is not a competitor. It is the proof the left-hand one
measures anything: same binary, same writes, same search, on a store that is
deliberately not encrypted. Without it, a zero could mean the write never
reached the disk or that the search does not read binary files — and the second
of those happened while the lane was being written, which is why the lane fails
if the control ever reads zero.

### The per-call tax — same handler, three envelopes

An agent's loop is call, read, decide, call again, so what the envelope costs is
multiplied by every step of every task. `transport/run.sh` asks the same operation
over each transport, interleaved, n=200.

Three samples of each phase, `n=200` interleaved, Apple M1 Max:

| transport | min | p50 | p50 against REST |
|---|---|---|---|
| **ZAP unix** | **0.07–0.09 ms** | **0.14–0.18 ms** | **0.67–0.75×** |
| ZAP tcp | 0.08–0.12 ms | 0.19–0.24 ms | 0.86–0.90× |
| REST | 0.10–0.13 ms | 0.21–0.28 ms | 1.00 |
| MCP | 0.10–0.14 ms | 0.21–0.25 ms | 0.96–1.09× |
| op-call plane | 0.09–0.12 ms | 0.19–0.23 ms | 1.00× |

**ZAP is the fastest transport and the socket is faster than the port** — two thirds
of REST's median over a unix socket, nine tenths over loopback TCP, ahead of
every HTTP transport in every sample. Among the three HTTP transports the differences are
inside the noise and they trade places between runs.

A process serves one ZAP address, so the socket is a second phase rather than a
fifth row. The three HTTP transports are measured again in that phase to carry the
drift between them, and the ratio to REST is the column that survives it. All of
it is under a third of a millisecond at the median, so the practical reading is
still to pick the transport that fits the caller.

The harness is one Go program calling all four round-robin. The previous table
was measured from Python and read 0.22–0.31 ms at `min` where the same transports now
read 0.09–0.15 — that difference was the client, silently in every row, and it
had to go before a fourth transport could be added that no script can speak.

### Fleet residency — we win, decisively

| | Hanzo, measured | Naïve, published |
|---|---|---|
| state per dormant agent | **477 bytes** | ~1 MB *(their assumption)* |
| 1M agents on disk | **455 MB** | ~977 GB |
| storage at list | **$0.01/mo** | $22/mo |
| write | 309,789 agents/s | — |
| resume | **0.034 ms** in-process | — |

Their row is marked *"MODELLED, NEVER BILLED."* Ours is a file you can `ls`.
2,198× is the distance between an assumption and a measurement.

### Sandbox — the primitives, measured on the runtime we actually ship

| | measured here | attributed elsewhere |
|---|---|---|
| V8 context | 0.13 ms | — |
| V8 isolate, isolated-vm 7.0.1 | **0.35 ms**, 1.00 MiB each | 2.79 ms, 1.2 MB |
| hanzo-vm, cold boot | **309 ms** (p95 335) | E2B <200 ms · Modal ~1 s · Cloudflare 1–3 s |
| hanzo-vm, from checkpoint | **311 ms** (p95 343) | Morph <250 ms resume · E2B ~1 s from pause |

**The container rows were docker, and nothing here runs docker.** The lane shelled
out to `docker run` and `docker exec` on machines that do not have it — the
builds run buildkit inside a microVM, which is why `hanzo-vm checkpoint list`
has a buildkit entry — so both rows printed "unavailable" while this table
carried numbers anyway. They now measure `hanzo-vm`, which is what a sandbox on
this stack actually is.

**That moves us out of the container column and into the microVM one, and we do
not win it.** 309 ms is slower than E2B's published <200 ms Firecracker cold
start. Their figure is uncontrolled — their hardware, their harness — which is
the same objection this file raises when the uncontrolled comparison runs the
other way, so it is not a defence, just the reason neither number settles it.

**A checkpoint saves the disk, not the boot.** Starting from a 403 MB checkpoint
costs 311 ms against a cold boot's 309 ms: no difference. `--from` hands a VM the
filesystem an earlier run left behind and the kernel boots either way. Morph's
"<250 ms" and E2B's "~1 s from pause" are MEMORY snapshots, a mechanism hanzo-vm
does not have — so that row has no counterpart of ours, and pairing it with this
one would claim the feature by borrowing its name.

**The isolate row used to be the context row.** A `vm.createContext` makes a
fresh global inside the isolate already running; it is cheap because it shares
the heap, which is exactly what an isolate does not do. Reporting 0.15 ms
against a published 2.79 ms and calling it 17× was comparing two different
primitives in our favour. Running the library the number is attributed to, on
this laptop, an isolate costs **0.35 ms** — under the figure cited at us by 8.0×,
and a measurement rather than an argument. It read 0.59 ms here once; five
consecutive runs give 0.35 ms p50 with a p95 of 0.41, and the first run of a
session reads high for the same reason the goroutine lane now discards a round.

**The megabyte is V8's, not a vendor's.** A fresh isolate's heap measures 1.00
MiB here, which is close to the 1.2 MB cited — because it is what any V8 isolate
costs, including one of ours. It is not a competitor's weakness.

An isolate runs JavaScript: no pytest, no pip, no cargo, no shell — which is what
a coding agent was asked to do. A microVM runs all of it behind a kernel
boundary and costs three orders of magnitude more to start. The rows are
different primitives and the comparison is per workload, not per millisecond.

### Agent as goroutine — the execution half of the fleet claim

A dormant agent is a row. An agent that is *running* still has to hold its
place, and that is a goroutine rather than a container.

| | measured here | attributed elsewhere |
|---|---|---|
| per live agent | **601 bytes** of heap | isolated-vm: 1.2 MB — and 1.00 MiB measured |
| spawn | **125 ns** | 2.79 ms — and 0.35 ms measured |
| wake 1M | 107 ms (107 ns each) | — |
| wazero (WASM) | 7.8 µs instantiate, 20 ns call | — |
| goja (JavaScript) | 2.4 µs per VM, 740 ns warm eval | — |
| gpython (Python) | 25.0 µs per context | — |

601 bytes against a 128 MB container floor is ~223,000×. Against a V8 isolate it
is ~1,745× — and that one is a goroutine against a JavaScript VM, so read it as
what each primitive costs rather than as one beating the other. Memory was
identical on every run; the timings are medians of eight.

**The spawn row was 187 ns and is 125 ns, because the old one timed the program
starting.** A built binary's FIRST run reads 202, 210 and 201 ns on three fresh
builds and 123, 125 and 123 ns on the next — the same 200,000 goroutines in a 41
ms window rather than a 25 ms one, so it is one fixed cost per binary (text-segment
paging, the kernel's first-exec signature check), not a cost per goroutine. The
lane now discards a warm-up round and names it. This is the neighbour of the note
that used to sit here — *benchmark a built binary, under `go run` the compile is
counted*, which reads 253 ns — and that note stopped one step short. The
correction favours us, which is why the method is printed beside it. See
`goroutine/README.md`.

WASM is not one language: CPython, QuickJS for TypeScript, Rust and Go all
target it. A V8 isolate is JavaScript only.

### Pricing — compute is not where the difference is

Our costs from `railway.com/pricing`; their prices from `usenaive.ai/pricing`,
read 2026-09-11 and recorded verbatim in [naive.md](naive.md); volumes measured
above.

- one call ≈ **51 ms** of 0.5 vCPU and 0.25 GB
- that slice at cost: **$0.00000025** · at their published rates: **$0.00000042**
- so their compute carries a **1.68×** markup — thin, and not a multiple

Both axes, because ours has both: their $0.0504/vCPU-hr against our vCPU plus
memory plus egress would be the same mistake in the other direction. Egress is
out of both sides — they publish no price for it and ours contributes four
ten-thousandths of a cent.

This row has been wrong twice. It first said they charge $0.05 a credit and
called that 79,614× marginal; no per-credit price is published, and $0.0504 is
an hour of a vCPU, so reading it as a call overstated them by the ratio of an
hour to a call. The correction then compared their compute price against our
all-in marginal cost and reported 1.1×, which was the same error smaller. 1.68×
is the two rates on the same slice. Both corrections went against us.

Where their published prices do carry a markup is the metered tools —
`$0.002158` for one web search — and the model tokens, which every stack bills
and which dominate both columns.

- at **$0.005** a call, 1B calls/month returns **$3.7M** after giving 25%
  to open source, three availability zones, twelve months of retained history,
  and twice the infrastructure bill in people

**Which numbers are whose.** The 25% is not this lane's to set: `hanzoai/commerce`
declares the OSS developer payout in `config/oss-payout.json` and `ossattr` caps
it at 0.25 in code, so raising it anywhere has no effect. What Hanzo charges
lives in commerce's PriceSet and PricingRule; the ladder above is not a price
list but a question about what a price would have to clear. Railway's rails and
naïve's rates are third-party price lists and stay here beside their citations —
a competitor's published prices in our own billing service would be a category
error, not a single source of truth.

The line that grows is not agents, it is **history**: a dormant agent stays 477
bytes, its transcript does not. At 2 KB retained per call, a billion calls a
month is 22 TB after a year, and that eventually exceeds compute.

Excluded, and it dominates all of the above: **model tokens**. A turn that
thinks costs 100–1000× the infrastructure under it. Any per-call price sits
beside token billing rather than pretending to include it — which is what Naïve
do when they keep LLM routing out of credits.

## Method notes

`fleet.mjs` pipes SQL on stdin rather than argv: a 50,000-row insert is 20 MB
and argv tops out well before that.

`sandbox.mjs` needs a container runtime for two of its four rows — `colima
start` is enough on macOS — and `npm i isolated-vm` in `bench/sandbox/` for the
isolate row. Each row says so and is skipped rather than guessed when its
dependency is absent.

`self/run.sh` and `transport/run.sh` build and start the binary themselves and need
nothing fetched. `transport/run.sh` measures round-robin rather than transport by transport:
measured in blocks the three rows disagreed about which transport was fastest on
every run, because drift between phases on a busy machine is larger than the
difference being measured.
