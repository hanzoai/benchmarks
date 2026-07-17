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

## Next
- **ZAP transport** throughput (needs a ZAP load client — `hey` speaks HTTP only).
- **HTTPS** (`https://` transport) vs HTTP.
- Drive **cloud's real `/health`** and compare — isolates cloud's middleware stack tax
  from the bare framework.
