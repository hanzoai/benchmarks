// zapload is a concurrent load generator for zip's native ZAP binary transport —
// the bombardier/hey equivalent for ZAP, which those HTTP tools can't speak. It
// hammers a ZAP-HTTP server with N goroutines (each on a pooled ZAP conn) for a
// duration and reports req/sec + latency percentiles, so ZAP is measured
// apples-to-apples with the HTTP number.
//
// Two scenarios, matching the server's -scenario flag:
//
//   - hello: GET /health, trivial "ok" — transport/framing tax.
//
//   - rpc:   POST /rpc carrying the native ZAP-typed eth-call body from the
//     shared record package — the JSON-skip end-to-end number.
//
//     go run ./zapload -addr 127.0.0.1:8391 -c 125 -d 6s -scenario rpc
package main

import (
	"flag"
	"fmt"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	rec "github.com/hanzoai/benchmarks/framework/zip/record"
	"github.com/valyala/fasthttp"
	zaphttp "github.com/zap-proto/http"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:8391", "zap server host:port")
	path := flag.String("path", "/health", "request path (hello scenario)")
	scenario := flag.String("scenario", "hello", "hello | rpc")
	conns := flag.Int("c", 100, "concurrency (goroutines)")
	dur := flag.Duration("d", 8*time.Second, "duration")
	flag.Parse()

	// Build the ZAP-typed request body once (identical bytes every worker sends)
	// from the shared record package — the exact record the JSON side carries.
	rpcBody := rec.ZapEncodeReq(rec.SampleID, rec.SampleBlock, rec.SampleMethod, rec.SampleAccount[:])
	reqPath := *path
	if *scenario == "rpc" {
		reqPath = "/rpc"
	}

	var ops, errs int64
	lat := make([][]time.Duration, *conns)
	var wg sync.WaitGroup
	deadline := time.Now().Add(*dur)
	start := time.Now()

	for w := 0; w < *conns; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			// Per-worker Transport: its own hot conn, no shared pool mutex (the
			// shared pool serializes N goroutines and dominates the tail).
			t := zaphttp.Dial("tcp", *addr)
			t.SetMaxIdleConns(2)
			t.SetReadTimeout(10 * time.Second)
			defer t.CloseIdleConnections()
			req := fasthttp.AcquireRequest()
			resp := fasthttp.AcquireResponse()
			defer fasthttp.ReleaseRequest(req)
			defer fasthttp.ReleaseResponse(resp)
			req.SetRequestURI(reqPath)
			req.Header.SetHost(*addr)
			if *scenario == "rpc" {
				req.Header.SetMethod(fasthttp.MethodPost)
				req.Header.SetContentType("application/zap")
				req.SetBody(rpcBody)
			} else {
				req.Header.SetMethod(fasthttp.MethodGet)
			}
			var s []time.Duration
			for time.Now().Before(deadline) {
				t0 := time.Now()
				if err := t.Do(req, resp); err != nil {
					atomic.AddInt64(&errs, 1)
					continue
				}
				s = append(s, time.Since(t0))
				resp.Reset()
				atomic.AddInt64(&ops, 1)
			}
			lat[w] = s
		}(w)
	}
	wg.Wait()
	elapsed := time.Since(start)

	var all []time.Duration
	for _, s := range lat {
		all = append(all, s...)
	}
	sort.Slice(all, func(i, j int) bool { return all[i] < all[j] })
	pct := func(p float64) time.Duration {
		if len(all) == 0 {
			return 0
		}
		i := int(float64(len(all)) * p)
		if i >= len(all) {
			i = len(all) - 1
		}
		return all[i]
	}
	fmt.Printf("ZAP  addr=%s  scenario=%s  path=%s  c=%d  d=%s\n", *addr, *scenario, reqPath, *conns, elapsed.Round(time.Millisecond))
	fmt.Printf("  Reqs/sec  %.0f\n", float64(ops)/elapsed.Seconds())
	fmt.Printf("  Requests  %d  (errors %d)\n", ops, errs)
	if len(all) > 0 {
		fmt.Printf("  Latency   p50=%s  p90=%s  p99=%s  max=%s\n",
			pct(0.50).Round(time.Microsecond), pct(0.90).Round(time.Microsecond),
			pct(0.99).Round(time.Microsecond), all[len(all)-1].Round(time.Microsecond))
	}
}
