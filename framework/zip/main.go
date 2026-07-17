// Command zipbench stands up a minimal hello server on either the zip framework or
// raw fasthttp, so `hey`/`wrk` can measure END-TO-END max req/sec (accept → parse →
// respond over TCP) — the number the in-process Go benches (handler cost only) don't
// capture. Same trivial handler on both, so the delta is the framework's live tax.
//
//	go run . -fw zip      -addr :8091
//	go run . -fw fasthttp -addr :8092
package main

import (
	"flag"
	"log"

	"github.com/valyala/fasthttp"
	"github.com/zap-proto/zip"
)

func main() {
	fw := flag.String("fw", "zip", "framework: zip | fasthttp")
	addr := flag.String("addr", ":8091", "listen address")
	transport := flag.String("transport", "http", "zip transport: http | zap")
	flag.Parse()

	switch *fw {
	case "zip":
		// zip is ZAP-native: a bare addr binds the ZAP binary transport; "http://"
		// binds fasthttp HTTP. Same handler either way — only the wire differs.
		app := zip.New(zip.Config{ServerHeader: "-"})
		app.Get("/health", func(c *zip.Ctx) error { return c.String(200, "ok") })
		laddr := *addr // bare = ZAP (driven by ./zapload)
		if *transport == "http" {
			laddr = "http://" + *addr // HTTP (driven by hey/bombardier)
		}
		log.Printf("zip listening (%s transport) on %s", *transport, *addr)
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
