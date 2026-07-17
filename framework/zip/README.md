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
see 1M+: a 10GbE/RDMA link, multiple NICs, or the **ZAP binary transport** — tighter
framing than HTTP ⇒ more req/sec per byte on the same wire, and it's what the cloud
stack already speaks natively.

## ZAP vs HTTP — the native binary transport (`./zapload`)
zip is ZAP-native, so this is the one that matters. `zapload` is the bombardier-for-ZAP
(HTTP tools can't speak it). Same handler, loopback c125:

| transport | req/sec | note |
|---|--:|---|
| zip HTTP (fasthttp) | 338–400k | zero-alloc HTTP path |
| zip ZAP (default GOGC) | 91k | **alloc/GC-bound** |
| zip ZAP (GOGC=800) | 203k | 2.2× — confirms GC-bound |

Surprise: ZAP is *slower today*, and it's the codec, not the wire. `zap-proto/http`
v0.2.0 allocates per request — `MarshalRequest` mints a fresh `[]byte`, header decode
does `string()` copies into a `map[string][]string` — so it's GC-bound (GOGC 100→800
more than doubles it, p99 12ms→4.6ms). fasthttp's HTTP path is zero-alloc, so it wins
now. The ZAP **wire** is tighter (fewer bytes than HTTP text ⇒ more req/sec per byte on
a saturated link); the real win is gated on a **zero-alloc codec** (bytebufferpool
frames, no header string-copies) — the optimization target in `zap-proto/http`, and
where ZAP overtakes HTTP.

## System tuning (spark)
- `enP7s7` (2.5GbE) has ONE hardware RX queue and the driver refuses `ethtool -L`
  ("Operation not supported") → enabled **RPS** (`rps_cpus=fffff`) to spread RX softirq
  across all 20 cores in software.
- Both loaders wired: `enP7s7` 2.5GbE (evo) + `enx…` 1GbE (dbc) — dual-NIC ingress is
  the path to higher aggregate, each NIC its own RX path.

## Next
- **Zero-alloc ZAP codec** in `zap-proto/http`, then re-bench (should pass HTTP).
- **PQ transports**: PQ-TLS 1.3 vs PQ-QUIC vs PQ-TLS+ZAP — handshake cost (ML-KEM) +
  steady-state AEAD throughput.
- Drive **cloud's real `/health`** (cloud middleware tax vs bare zip).
