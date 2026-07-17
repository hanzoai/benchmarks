// serde_test.go — the HEADLINE microbench isolating the JSON-skip axis.
//
// Round trip = encode request + decode request + encode response + decode
// response: the real "deserialize and serialize" cost a server pays per call.
// ZAP does it with typed zero-copy field reads (no JSON anywhere); HTTP+JSON
// does it against text with the fastest general Go libraries (goccy, sonic) as
// well as stdlib. Decode-only and Encode-only benches decompose where the win
// (and the honest cost) actually lives.
//
//	go test -bench 'Serde|Handler|Decode|Encode' -benchmem -count=3
//	go test -run 'WireSizes|RoundTripEquivalence' -v
package main

import (
	"bytes"
	"encoding/hex"
	"testing"

	rec "github.com/hanzoai/benchmarks/framework/zip/record"
)

// sink defeats dead-code elimination: every decoded field on every codec is
// folded in, so no serializer's work can be optimized away and neither codec
// can silently skip a field the other parses.
var sink uint64

// Pre-encoded buffers for the decode-only benches (the deserialize half a
// server pays). Built once at init off each format's own encoder.
var (
	zapReqWire   = rec.ZapEncodeReq(rec.SampleID, rec.SampleBlock, rec.SampleMethod, rec.SampleAccount[:])
	zapRespWire  = rec.ZapEncodeResp(rec.SampleID, rec.RespBalance, rec.RespNonce, rec.SampleBlockHash[:])
	jsonReqWire  = mustMarshal(rec.CodecStdlib, &rec.JSONReq{Method: rec.SampleMethod, Account: rec.SampleAccountHex, Block: rec.SampleBlock, ID: rec.SampleID})
	jsonRespWire = mustMarshal(rec.CodecStdlib, &rec.JSONResp{ID: rec.SampleID, Balance: rec.RespBalance, Nonce: rec.RespNonce, BlockHash: rec.SampleBlockHashHex})
)

func mustMarshal(c rec.JSONCodec, v any) []byte {
	b, err := c.Marshal(v)
	if err != nil {
		panic(err)
	}
	return b
}

func newJSONReq() *rec.JSONReq {
	return &rec.JSONReq{Method: rec.SampleMethod, Account: rec.SampleAccountHex, Block: rec.SampleBlock, ID: rec.SampleID}
}

// ---------- Decode only: the zero-copy vs scan+reflect+alloc axis ----------
// This is where native ZAP's structural advantage is starkest — typed field
// reads alias the wire (no scan, no reflect, no per-field allocation), while
// every JSON library must walk the text and materialize each field.

func decodeJSON(c rec.JSONCodec) {
	var rq rec.JSONReq
	_ = c.Unmarshal(jsonReqWire, &rq)
	sink += rq.ID + rq.Block + uint64(len(rq.Method)) + uint64(rq.Account[0])
	var rs rec.JSONResp
	_ = c.Unmarshal(jsonRespWire, &rs)
	sink += rs.ID + rs.Balance + rs.Nonce + uint64(rs.BlockHash[0])
}

func decodeZAP() {
	id, block, method, account, _ := rec.ZapDecodeReq(zapReqWire)
	sink += id + block + uint64(len(method)) + uint64(account[0])
	rid, bal, nonce, bhash, _ := rec.ZapDecodeResp(zapRespWire)
	sink += rid + bal + nonce + uint64(bhash[0])
}

func BenchmarkDecode_JSON_stdlib(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		decodeJSON(rec.CodecStdlib)
	}
}

func BenchmarkDecode_JSON_goccy(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		decodeJSON(rec.CodecGoccy)
	}
}

func BenchmarkDecode_JSON_sonic(b *testing.B) {
	if !rec.SonicAvailable {
		b.Skip("sonic asm backend unavailable on this arch/build")
	}
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		decodeJSON(rec.CodecSonic)
	}
}

func BenchmarkDecode_ZAP(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		decodeZAP()
	}
}

// ---------- Encode only ----------
// v1.3.0's SetText/SetBytes defer the tail payload via a copy (append) + an
// offsets slice, and StartObject heap-allocates the ObjectBuilder, so ZAP's
// fresh-per-call encode allocates comparably to the fastest JSON libs here —
// reported honestly. The decode side is where the zero-copy win lives.

func encodeJSON(c rec.JSONCodec) {
	rq, _ := c.Marshal(newJSONReq())
	rs, _ := c.Marshal(&rec.JSONResp{ID: rec.SampleID, Balance: rec.RespBalance, Nonce: rec.RespNonce, BlockHash: rec.SampleBlockHashHex})
	sink += uint64(len(rq)) + uint64(len(rs))
}

func encodeZAP() {
	rq := rec.ZapEncodeReq(rec.SampleID, rec.SampleBlock, rec.SampleMethod, rec.SampleAccount[:])
	rs := rec.ZapEncodeResp(rec.SampleID, rec.RespBalance, rec.RespNonce, rec.SampleBlockHash[:])
	sink += uint64(len(rq)) + uint64(len(rs))
}

func BenchmarkEncode_JSON_stdlib(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		encodeJSON(rec.CodecStdlib)
	}
}

func BenchmarkEncode_JSON_goccy(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		encodeJSON(rec.CodecGoccy)
	}
}

func BenchmarkEncode_JSON_sonic(b *testing.B) {
	if !rec.SonicAvailable {
		b.Skip("sonic asm backend unavailable on this arch/build")
	}
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		encodeJSON(rec.CodecSonic)
	}
}

func BenchmarkEncode_ZAP(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		encodeZAP()
	}
}

// ---------- Round trip: encode req + decode req + encode resp + decode resp ----------

func serdeRoundTripJSON(c rec.JSONCodec) {
	reqBuf, _ := c.Marshal(newJSONReq())
	var rq rec.JSONReq
	_ = c.Unmarshal(reqBuf, &rq)
	sink += rq.ID + rq.Block + uint64(len(rq.Method)) + uint64(rq.Account[0])

	respBuf, _ := c.Marshal(&rec.JSONResp{ID: rq.ID, Balance: rec.RespBalance, Nonce: rec.RespNonce, BlockHash: rec.SampleBlockHashHex})
	var rs rec.JSONResp
	_ = c.Unmarshal(respBuf, &rs)
	sink += rs.ID + rs.Balance + rs.Nonce + uint64(rs.BlockHash[0])
}

func serdeRoundTripZAP() {
	reqBuf := rec.ZapEncodeReq(rec.SampleID, rec.SampleBlock, rec.SampleMethod, rec.SampleAccount[:])
	id, block, method, account, _ := rec.ZapDecodeReq(reqBuf)
	sink += id + block + uint64(len(method)) + uint64(account[0])

	respBuf := rec.ZapEncodeResp(id, rec.RespBalance, rec.RespNonce, rec.SampleBlockHash[:])
	rid, bal, nonce, bhash, _ := rec.ZapDecodeResp(respBuf)
	sink += rid + bal + nonce + uint64(bhash[0])
}

func BenchmarkSerde_JSON_stdlib(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		serdeRoundTripJSON(rec.CodecStdlib)
	}
}

func BenchmarkSerde_JSON_goccy(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		serdeRoundTripJSON(rec.CodecGoccy)
	}
}

func BenchmarkSerde_JSON_sonic(b *testing.B) {
	if !rec.SonicAvailable {
		b.Skip("sonic asm backend unavailable on this arch/build")
	}
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		serdeRoundTripJSON(rec.CodecSonic)
	}
}

func BenchmarkSerde_ZAP(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		serdeRoundTripZAP()
	}
}

// ---------- Server-only handler cost (decode request + compute + encode response) ----------
// Pairs allocs/req with the live req/sec numbers from the /rpc load test.

func BenchmarkHandler_JSON_stdlib(b *testing.B) { benchHandlerJSON(b, rec.CodecStdlib) }
func BenchmarkHandler_JSON_goccy(b *testing.B)  { benchHandlerJSON(b, rec.CodecGoccy) }

func BenchmarkHandler_JSON_sonic(b *testing.B) {
	if !rec.SonicAvailable {
		b.Skip("sonic asm backend unavailable on this arch/build")
	}
	benchHandlerJSON(b, rec.CodecSonic)
}

func benchHandlerJSON(b *testing.B, c rec.JSONCodec) {
	reqBuf := mustMarshal(c, newJSONReq())
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		out, err := rec.ServerComputeJSON(c, reqBuf)
		if err != nil {
			b.Fatal(err)
		}
		sink += uint64(len(out))
	}
}

func BenchmarkHandler_ZAP(b *testing.B) {
	reqBuf := rec.ZapEncodeReq(rec.SampleID, rec.SampleBlock, rec.SampleMethod, rec.SampleAccount[:])
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		out, err := rec.ServerComputeZAP(reqBuf)
		if err != nil {
			b.Fatal(err)
		}
		sink += uint64(len(out))
	}
}

// ---------- On-wire size (bytes) ----------

func TestWireSizes(t *testing.T) {
	jr := mustMarshal(rec.CodecStdlib, newJSONReq())
	js := mustMarshal(rec.CodecStdlib, &rec.JSONResp{ID: rec.SampleID, Balance: rec.RespBalance, Nonce: rec.RespNonce, BlockHash: rec.SampleBlockHashHex})
	zr := rec.ZapEncodeReq(rec.SampleID, rec.SampleBlock, rec.SampleMethod, rec.SampleAccount[:])
	zs := rec.ZapEncodeResp(rec.SampleID, rec.RespBalance, rec.RespNonce, rec.SampleBlockHash[:])

	t.Logf("request  wire bytes: JSON=%3d  ZAP=%3d", len(jr), len(zr))
	t.Logf("response wire bytes: JSON=%3d  ZAP=%3d", len(js), len(zs))
	t.Logf("round-trip total   : JSON=%3d  ZAP=%3d", len(jr)+len(js), len(zr)+len(zs))
	t.Logf("req  JSON: %s", jr)
	t.Logf("resp JSON: %s", js)
	t.Logf("req  ZAP  (hex): %s", hex.EncodeToString(zr))
	t.Logf("resp ZAP  (hex): %s", hex.EncodeToString(zs))
}

// ---------- Correctness: both codecs preserve all four fields round-trip ----------
// Proves the benchmark measures real, equivalent work — not a broken codec that
// looks fast because it drops a field.

func TestRoundTripEquivalence(t *testing.T) {
	// ZAP request round-trips every field byte-exact.
	reqBuf := rec.ZapEncodeReq(rec.SampleID, rec.SampleBlock, rec.SampleMethod, rec.SampleAccount[:])
	id, block, method, account, err := rec.ZapDecodeReq(reqBuf)
	if err != nil {
		t.Fatalf("zap decode req: %v", err)
	}
	if id != rec.SampleID || block != rec.SampleBlock || method != rec.SampleMethod || !bytes.Equal(account, rec.SampleAccount[:]) {
		t.Fatalf("zap req mismatch: id=%d block=%d method=%q account=%x", id, block, method, account)
	}

	// ZAP response round-trips every field byte-exact.
	respBuf := rec.ZapEncodeResp(rec.SampleID, rec.RespBalance, rec.RespNonce, rec.SampleBlockHash[:])
	rid, bal, nonce, bhash, err := rec.ZapDecodeResp(respBuf)
	if err != nil {
		t.Fatalf("zap decode resp: %v", err)
	}
	if rid != rec.SampleID || bal != rec.RespBalance || nonce != rec.RespNonce || !bytes.Equal(bhash, rec.SampleBlockHash[:]) {
		t.Fatalf("zap resp mismatch: id=%d bal=%d nonce=%d hash=%x", rid, bal, nonce, bhash)
	}

	// Every JSON codec round-trips the same record identically.
	for _, c := range []rec.JSONCodec{rec.CodecStdlib, rec.CodecGoccy} {
		checkJSONCodec(t, c)
	}
	if rec.SonicAvailable {
		checkJSONCodec(t, rec.CodecSonic)
	}

	// Both server compute paths echo id and emit all four response fields
	// (fairness: same fields in, same fields out). The folded balance depends
	// on the codec's native account representation (ZAP 20 raw bytes vs JSON
	// 42-char hex), so the two balances legitimately DIFFER — we assert only
	// that the fold actually ran on each side (balance != the raw constant),
	// which proves every request field was decoded and nothing was elided.
	zOut, err := rec.ServerComputeZAP(reqBuf)
	if err != nil {
		t.Fatalf("ServerComputeZAP: %v", err)
	}
	zid, zbal, znonce, zhash, err := rec.ZapDecodeResp(zOut)
	if err != nil || zid != rec.SampleID || znonce != rec.RespNonce || !bytes.Equal(zhash, rec.SampleBlockHash[:]) {
		t.Fatalf("ServerComputeZAP resp bad: id=%d nonce=%d hashlen=%d err=%v", zid, znonce, len(zhash), err)
	}
	if zbal == rec.RespBalance {
		t.Fatal("ServerComputeZAP fold did not run — request fields may be dead-code eliminated")
	}

	jReqBuf := mustMarshal(rec.CodecStdlib, newJSONReq())
	jOut, err := rec.ServerComputeJSON(rec.CodecStdlib, jReqBuf)
	if err != nil {
		t.Fatalf("ServerComputeJSON: %v", err)
	}
	var jResp rec.JSONResp
	if err := rec.CodecStdlib.Unmarshal(jOut, &jResp); err != nil {
		t.Fatalf("ServerComputeJSON decode: %v", err)
	}
	if jResp.ID != rec.SampleID || jResp.Nonce != rec.RespNonce || jResp.BlockHash != rec.SampleBlockHashHex {
		t.Fatalf("ServerComputeJSON resp bad: %+v", jResp)
	}
	if jResp.Balance == rec.RespBalance {
		t.Fatal("ServerComputeJSON fold did not run — request fields may be dead-code eliminated")
	}
}

func checkJSONCodec(t *testing.T, c rec.JSONCodec) {
	t.Helper()
	reqBuf := mustMarshal(c, newJSONReq())
	var rq rec.JSONReq
	if err := c.Unmarshal(reqBuf, &rq); err != nil {
		t.Fatalf("%s unmarshal req: %v", c.Name, err)
	}
	if rq.ID != rec.SampleID || rq.Block != rec.SampleBlock || rq.Method != rec.SampleMethod || rq.Account != rec.SampleAccountHex {
		t.Fatalf("%s req mismatch: %+v", c.Name, rq)
	}
}
