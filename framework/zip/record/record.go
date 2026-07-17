// Package record defines ONE realistic eth-style RPC record and its two
// serialization strategies — HTTP+JSON vs native ZAP-typed — so the in-process
// microbench, the live /rpc server, and the ZAP load generator all exercise the
// exact same record, the exact same compute, and the exact same field set. One
// definition, three consumers: DRY across the whole benchmark.
//
// This is the JSON-SKIP axis: native ZAP carries typed binary fields and reads
// them zero-copy (no scan, no reflect, no per-field alloc); HTTP+JSON must
// serialize to / scan from text every call. It is a SEPARATE axis from the
// zaphttp framing-CPU test — that one carries the body opaque and never touches
// JSON, so it cannot show this. This package makes the JSON-skip explicit.
//
// FAIRNESS CONTRACT (enforced by record's tests):
//   - Same logical record both sides: request {method, account[20], block, id},
//     response {id, balance, nonce, blockHash[32]}.
//   - The server decodes all four request fields and emits all four response
//     fields on BOTH codecs. ComputeBalance folds every decoded request field
//     into the emitted balance, so no field read is dead-code-eliminated and
//     neither codec can silently skip a field the other parses.
//   - JSON is held to its FASTEST general libraries (goccy, sonic), not just
//     stdlib. The account/hash travel as 0x-hex strings — exactly how real eth
//     JSON-RPC represents binary — and we do NOT charge JSON for hex→binary
//     decoding, i.e. the most charitable framing for JSON.
package record

import (
	"encoding/hex"
	"encoding/json"

	goccy "github.com/goccy/go-json"
	zap "github.com/zap-proto/go"
)

// ---- The record: fixed sample values shared by every path ----

const (
	SampleMethod        = "eth_getBalance"
	SampleBlock  uint64 = 0x10d4f // 68943
	SampleID     uint64 = 1
	RespBalance  uint64 = 1_000_000_000_000_000_000 // 1 ETH in wei
	RespNonce    uint64 = 42
)

// SampleAccount (20 bytes) and SampleBlockHash (32 bytes) are the binary fields
// ZAP carries natively and JSON must render as hex text.
var (
	SampleAccount   = [20]byte{0xde, 0xad, 0xbe, 0xef, 0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff}
	SampleBlockHash = [32]byte{0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef, 0xfe, 0xdc, 0xba, 0x98, 0x76, 0x54, 0x32, 0x10, 0x0f, 0x1e, 0x2d, 0x3c, 0x4b, 0x5a, 0x69, 0x78, 0x87, 0x96, 0xa5, 0xb4, 0xc3, 0xd2, 0xe1, 0xf0}

	SampleAccountHex   = "0x" + hex.EncodeToString(SampleAccount[:])   // 42 chars
	SampleBlockHashHex = "0x" + hex.EncodeToString(SampleBlockHash[:]) // 66 chars
)

// ---- JSON representation ----

type JSONReq struct {
	Method  string `json:"method"`
	Account string `json:"account"` // 0x + 40 hex nibbles
	Block   uint64 `json:"block"`
	ID      uint64 `json:"id"`
}

type JSONResp struct {
	ID        uint64 `json:"id"`
	Balance   uint64 `json:"balance"`
	Nonce     uint64 `json:"nonce"`
	BlockHash string `json:"blockHash"` // 0x + 64 hex nibbles
}

// ---- ZAP representation ----
//
// Schemas are the single layout authority: field byte-offsets are read back
// from the compiled Struct, never hardcoded. account/blockHash are declared as
// Bytes (out-of-line 4-byte offset + 4-byte length in the fixed section; the
// 20/32 raw bytes live in the tail). Reading them back is zero-copy — the
// returned slice aliases the wire, no allocation. v1.3.0's published API has no
// inline fixed-bytes setter (SetBytesFixed is luxfi/zap-only), so this is the
// honest tag-reproducible path.

var reqSchema = zap.NewStructBuilder("EthCallReq").
	Uint64("id").     // @0
	Uint64("block").  // @8
	Text("method").   // @16 (off+len)
	Bytes("account"). // @24 (off+len)
	Build()

var respSchema = zap.NewStructBuilder("EthCallResp").
	Uint64("id").       // @0
	Uint64("balance").  // @8
	Uint64("nonce").    // @16
	Bytes("blockHash"). // @24 (off+len)
	Build()

// Field offsets pulled from the compiled schemas (DRY: one layout authority).
var (
	roID      = reqSchema.Fields[0].Offset
	roBlock   = reqSchema.Fields[1].Offset
	roMethod  = reqSchema.Fields[2].Offset
	roAccount = reqSchema.Fields[3].Offset

	soID        = respSchema.Fields[0].Offset
	soBalance   = respSchema.Fields[1].Offset
	soNonce     = respSchema.Fields[2].Offset
	soBlockHash = respSchema.Fields[3].Offset
)

// ReqWireSize / RespWireSize expose the fixed-section sizes for callers sizing
// buffers.
var (
	ReqWireSize  = reqSchema.Size
	RespWireSize = respSchema.Size
)

func ZapEncodeReq(id, block uint64, method string, account []byte) []byte {
	b := zap.NewBuilder(128)
	ob := b.StartObject(reqSchema.Size)
	ob.SetUint64(roID, id)
	ob.SetUint64(roBlock, block)
	ob.SetText(roMethod, method)
	ob.SetBytes(roAccount, account)
	ob.FinishAsRoot()
	return b.Finish()
}

func ZapEncodeResp(id, balance, nonce uint64, blockHash []byte) []byte {
	b := zap.NewBuilder(128)
	ob := b.StartObject(respSchema.Size)
	ob.SetUint64(soID, id)
	ob.SetUint64(soBalance, balance)
	ob.SetUint64(soNonce, nonce)
	ob.SetBytes(soBlockHash, blockHash)
	ob.FinishAsRoot()
	return b.Finish()
}

// ZapDecodeReq returns the four request fields zero-copy (method string and
// account slice alias the wire buffer).
func ZapDecodeReq(buf []byte) (id, block uint64, method string, account []byte, err error) {
	msg, e := zap.Parse(buf)
	if e != nil {
		return 0, 0, "", nil, e
	}
	o := msg.Root()
	return o.Uint64(roID), o.Uint64(roBlock), o.Text(roMethod), o.Bytes(roAccount), nil
}

func ZapDecodeResp(buf []byte) (id, balance, nonce uint64, blockHash []byte, err error) {
	msg, e := zap.Parse(buf)
	if e != nil {
		return 0, 0, 0, nil, e
	}
	o := msg.Root()
	return o.Uint64(soID), o.Uint64(soBalance), o.Uint64(soNonce), o.Bytes(soBlockHash), nil
}

// ---- The compute: identical trivial O(1) work on both codecs ----
//
// Echo id; balance is the fixed constant XOR a cheap fold of block, the method
// length, the account length and account[0]. The fold exists ONLY so that every
// decoded request field is provably consumed and emitted — parity with JSON's
// unavoidable full unmarshal — and nothing is dead-code eliminated. It is O(1),
// not O(len): ZAP legitimately does not re-scan payload bytes JSON must scan,
// which is the structural advantage under test.
func ComputeBalance(block uint64, methodLen, accountLen int, accountFirst byte) uint64 {
	fold := block ^ uint64(methodLen) ^ uint64(accountLen) ^ uint64(accountFirst)
	return RespBalance ^ fold
}

// ServerComputeZAP: decode ZAP request → compute → encode ZAP response.
func ServerComputeZAP(reqBuf []byte) ([]byte, error) {
	id, block, method, account, err := ZapDecodeReq(reqBuf)
	if err != nil {
		return nil, err
	}
	var first byte
	if len(account) > 0 {
		first = account[0]
	}
	bal := ComputeBalance(block, len(method), len(account), first)
	return ZapEncodeResp(id, bal, RespNonce, SampleBlockHash[:]), nil
}

// ---- Pluggable JSON codec (stdlib / goccy / sonic) ----

type JSONCodec struct {
	Name      string
	Marshal   func(any) ([]byte, error)
	Unmarshal func([]byte, any) error
}

var (
	CodecStdlib = JSONCodec{"stdlib", json.Marshal, json.Unmarshal}
	CodecGoccy  = JSONCodec{"goccy", goccy.Marshal, goccy.Unmarshal}
	// CodecSonic is defined in sonic.go / nosonic.go (build-guarded).
)

// ServerComputeJSON: decode JSON request → compute → encode JSON response.
func ServerComputeJSON(c JSONCodec, reqBuf []byte) ([]byte, error) {
	var req JSONReq
	if err := c.Unmarshal(reqBuf, &req); err != nil {
		return nil, err
	}
	var first byte
	if len(req.Account) > 0 {
		first = req.Account[0]
	}
	bal := ComputeBalance(req.Block, len(req.Method), len(req.Account), first)
	return c.Marshal(&JSONResp{ID: req.ID, Balance: bal, Nonce: RespNonce, BlockHash: SampleBlockHashHex})
}

func LookupJSONCodec(name string) (JSONCodec, bool) {
	switch name {
	case "stdlib":
		return CodecStdlib, true
	case "goccy":
		return CodecGoccy, true
	case "sonic":
		if SonicAvailable {
			return CodecSonic, true
		}
	}
	return JSONCodec{}, false
}
