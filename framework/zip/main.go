// Command zipbench stands up a minimal server on either the zip framework or
// raw fasthttp so `hey`/`wrk`/`bombardier` (HTTP) and `./zapload` (ZAP binary
// transport) can measure END-TO-END max req/sec (accept → parse → respond over
// TCP) — the number the in-process Go benches (handler cost only) don't capture.
//
// Two scenarios:
//
//   - hello: trivial "ok" handler — the framing/transport tax (existing test).
//
//   - rpc:   the eth-style /rpc record from the record package — HTTP+JSON vs
//     native ZAP, same logical work both sides, isolating the JSON-skip advantage.
//
//     go run . -fw zip      -addr :8091 -scenario hello
//     go run . -fw zip      -addr :8091 -scenario rpc -transport http -json goccy   # bombardier
//     go run . -fw zip      -addr :8091 -scenario rpc -transport zap                # ./zapload
//     go run . -fw fasthttp -addr :8092
package main

import (
	"flag"
	"log"

	rec "github.com/hanzoai/benchmarks/framework/zip/record"
	"github.com/valyala/fasthttp"
	"github.com/zap-proto/zip"
)

func main() {
	fw := flag.String("fw", "zip", "framework: zip | fasthttp")
	addr := flag.String("addr", ":8091", "listen address")
	transport := flag.String("transport", "http", "zip transport: http | zap")
	scenario := flag.String("scenario", "hello", "handler: hello | rpc")
	jsonLib := flag.String("json", "stdlib", "rpc JSON codec on the http transport: stdlib | goccy | sonic")
	flag.Parse()

	switch *fw {
	case "zip":
		// zip is ZAP-native: a bare addr binds the ZAP binary transport; "http://"
		// binds fasthttp HTTP. Same handler either way — only the wire differs.
		app := zip.New(zip.Config{ServerHeader: "-"})
		app.Get("/health", func(c *zip.Ctx) error { return c.String(200, "ok") })

		if *scenario == "rpc" {
			h, desc := rpcHandler(*transport, *jsonLib)
			app.Post("/rpc", h)
			log.Printf("rpc handler: %s", desc)
		}

		laddr := *addr // bare = ZAP (driven by ./zapload)
		if *transport == "http" {
			laddr = "http://" + *addr // HTTP (driven by hey/bombardier)
		}
		log.Printf("zip listening (%s transport, scenario=%s) on %s", *transport, *scenario, *addr)
		log.Fatal(app.Listen(laddr))
	case "fasthttp":
		h := func(ctx *fasthttp.RequestCtx) {
			ctx.SetStatusCode(200)
			ctx.SetBodyString("ok")
		}
		log.Printf("fasthttp listening on %s", *addr)
		log.Fatal(fasthttp.ListenAndServe(*addr, h))
	default:
		log.Fatalf("unknown -fw %q", *fw)
	}
}

// rpcHandler builds the /rpc handler for the configured wire. On the zap
// transport the body is a native ZAP-typed message (decoded zero-copy); on the
// http transport it is JSON decoded with the selected codec. Both run the same
// serverCompute* path from rpc.go — same fields in, same compute, same fields
// out — so the only difference measured end-to-end is the serialization wire.
func rpcHandler(transport, jsonLib string) (zip.Handler, string) {
	if transport == "zap" {
		return func(c *zip.Ctx) error {
			out, err := rec.ServerComputeZAP(c.Body())
			if err != nil {
				return c.String(400, "bad zap body")
			}
			return c.Bytes(200, out)
		}, "zap-typed (zero-copy decode)"
	}

	codec, ok := rec.LookupJSONCodec(jsonLib)
	if !ok {
		log.Fatalf("unknown/unavailable -json %q", jsonLib)
	}
	return func(c *zip.Ctx) error {
		out, err := rec.ServerComputeJSON(codec, c.Body())
		if err != nil {
			return c.String(400, "bad json body")
		}
		return c.Bytes(200, out)
	}, "http+json codec=" + codec.Name
}
