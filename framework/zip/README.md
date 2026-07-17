# framework/zip — live end-to-end req/sec: zip vs raw fasthttp

**zip is ZAP-native.** The address *scheme* picks the wire transport:
`Listen(":8080")` binds the **ZAP binary transport** (default); `Listen("http://:8080")`
binds fasthttp HTTP; `Listen(":9653","http://:8080")` binds both in one call. The Go
benches in `zap/zip` measure *handler* cost (zip's tax over raw fiber is ~24 ns + one
48 B alloc — <1% on real work). This suite measures **end-to-end max req/sec** on a live
server with `hey` — the number handler benches don't capture.

## Run
```
./run.sh                    # zip(http) vs raw fasthttp, same no-op /health handler
DUR=10s CONN=200 ./run.sh
```

## Result — GB10 (arm64), `hey -z 6s -c 100`, localhost
| framework | req/sec | vs fasthttp |
|---|--:|--:|
| raw fasthttp | 98,478 | 1.00× |
| **zip (http)** | **92,684** | **0.94×** |

**~94% of raw fasthttp on a no-op handler** — a ~6% tax at the extreme where the
framework layer is maximally visible; on any handler doing real work it is <1%. zip is
at parity with the fasthttp it wraps. (Localhost + `hey`'s client overhead cap the
*absolute* ceiling — the zip/fasthttp **ratio** is the signal, not the raw number.)

## Distributed — server on spark, load from evo (32c x86) over the wire
`./distributed.sh` runs the server here and drives bombardier from evo. Same handler.

| loader → target | req/sec (fasthttp / zip) | latency | note |
|---|--:|--:|---|
| loopback c500 (spark) | 365k / 348k | <1 ms | server + load share 20 cores |
| evo → spark c1000 | 194k / 194k | 5.1 ms | **link-bound** |
| evo → spark c4000 | 167k | 24 ms | congestion collapse |
| evo → spark c8000 | 154k | 52 ms | worse — link saturated |

## The ceiling is I/O, not the box
More connections make it *slower* (c8000 < c4000 < c1000) while latency explodes —
textbook link saturation on the `eno1` 192.168.77.0/24 (1GbE-class) path. spark's 20
cores sit mostly idle at 194k. **The box is not maxed; the network link is.** fasthttp
does ~150–250k req/sec *per core* on tiny requests, so spark's serving ceiling is
comfortably seven figures — you just can't *deliver* that many requests over 1GbE. To
see 1M+: a 10GbE/RDMA link, multiple NICs, or the **ZAP binary transport** — whose
zero-alloc codec spends fewer CPU cycles per request than HTTP (it beats HTTP ~1.2× on
loopback, see below), and it's what the cloud stack already speaks natively.

## ZAP vs HTTP — the native binary transport (`zapbench`)
zip is ZAP-native, so this is the one that matters. The load tool is
`zap-proto/bench`'s `cmd/zapbench` — the bombardier-for-ZAP (HTTP tools can't speak
it). Same `/health` handler, warm keep-alive, default GOGC, default GOMAXPROCS.

**FIXED — the ZAP codec is now zero-alloc and ZAP beats HTTP.** The alloc/GC bound
below is gone: `zap-proto/http` hand-rolls the frame encode/decode straight into
pooled buffers (no `zap.Builder`, no `map[string][]string`, no `json.Marshal`; headers
stream into the frame tail as compact sorted-key JSON, byte-identical to the old wire —
golden tests still pass), and the server holds one `RequestCtx` per connection instead
of one per request. Codec allocs/op: MarshalRequest 11→0, MarshalResponse 19→0,
UnmarshalResponse 11→0. Full round trip: **0 allocs/req at default GOGC**.

Loopback (spark, c125, both server+load share 20 cores):

| transport | req/sec (default GOGC) | note |
|---|--:|---|
| zip ZAP — before (this finding) | 91k | alloc/GC-bound (GOGC=800 → 203k) |
| zip HTTP (fasthttp) | ~460–500k | zero-alloc HTTP path |
| **zip ZAP — after** | **~540–590k** | **zero-alloc; beats HTTP ~1.18×** |

Over the wire (evo→spark, 2.5GbE): both **tie at ~530k** at c500–c1000 — the link
saturates, so the codec is no longer the bottleneck (I/O-bound, not CPU-bound). ZAP
holds a much tighter tail there (p99 ~2.1ms @ c500 vs HTTP outliers to ~78ms).

Honest caveat: the ZAP **wire is not smaller** for small messages — a `/health` request
is ~124 B on ZAP vs ~75 B on HTTP (16 B header + 48 B fixed object section + JSON header
blob). ZAP's win is **CPU** (zero-alloc, no open-ended HTTP-header tokenizing), not bytes.
On body-heavy responses ZAP ties or slightly trails HTTP because the encoder copies the
body into the frame tail (a `writev`-style split body is the follow-up there).

## System tuning (`../../tune.sh`) — 2.67× over the wire
Run `sudo ../../tune.sh <nic>` on the server AND every loader. It sets: performance
governor, NIC ring→max, **RPS+RFS+XPS** (spread RX/TX softirq across all cores — the
2.5GbE NIC has 1 hardware queue and the driver refuses `ethtool -L`), `netdev_max_backlog`
1k→300k, `somaxconn`→65535, 256 MiB socket buffers, wide ephemeral ports, `tw_reuse`.

evo→spark, same handler, 2.5GbE:

| concurrency | untuned | tuned |
|---|--:|--:|
| c1000 | 194k | **518k** |
| c2000 | collapsed | **518k** |
| c4000 | 154k | **474k** (peak 696k) |

**2.67×.** RPS killed the single-core-softirq cap; deep backlog + buffers stopped drops.
Tuned network (518k) now *beats* loopback (365-400k) — over the wire spark's 20 cores
serve full-time instead of sharing with the load gen, so 518k ≈ spark's real ceiling.
Next lever to seven figures: **dual loader** (evo 2.5G on `enP7s7` + dbc 1G on `enx…`,
each its own NIC/RX path) for aggregate ingress.

## Next
- ~~**Zero-alloc ZAP codec** in `zap-proto/http`~~ — DONE (codec 0 allocs/op; ZAP beats
  HTTP ~1.18× loopback, ties over the saturated 2.5GbE link). See `zap-proto/http`
  branch `perf/zero-alloc-codec` and `zap-proto/bench` branch `perf/zero-alloc-loadgen`.
- **`writev` body split** in `zap-proto/http` — stop copying large response bodies into
  the frame tail (currently ties/trails HTTP on 64 KiB bodies for that one memcpy).
- **PQ transports**: PQ-TLS 1.3 vs PQ-QUIC vs PQ-TLS+ZAP — handshake cost (ML-KEM) +
  steady-state AEAD throughput.
- Drive **cloud's real `/health`** (cloud middleware tax vs bare zip).
