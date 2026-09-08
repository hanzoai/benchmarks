package blockchain

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"testing"
)

// Warp Message structures for cross-chain communication
// Based on Lux Network's AWM (Avalanche Warp Messaging) patterns

// JSONWarpMessage - traditional JSON encoding
type JSONWarpMessage struct {
	SourceChainID      string   `json:"source_chain_id"`
	DestinationChainID string   `json:"destination_chain_id"`
	Nonce              uint64   `json:"nonce"`
	Timestamp          int64    `json:"timestamp"`
	Payload            []byte   `json:"payload"`
	Signatures         []string `json:"signatures"`
}

// JSONValidatorSet - for consensus updates
type JSONValidatorSet struct {
	Epoch      uint64            `json:"epoch"`
	Validators []JSONValidator   `json:"validators"`
	TotalStake uint64            `json:"total_stake"`
}

type JSONValidator struct {
	NodeID    string `json:"node_id"`
	PublicKey string `json:"public_key"`
	Stake     uint64 `json:"stake"`
	StartTime int64  `json:"start_time"`
	EndTime   int64  `json:"end_time"`
}

// JSONConsensusVote
type JSONConsensusVote struct {
	BlockHash   string `json:"block_hash"`
	Height      uint64 `json:"height"`
	Round       uint32 `json:"round"`
	ValidatorID string `json:"validator_id"`
	Signature   string `json:"signature"`
	Timestamp   int64  `json:"timestamp"`
}

// ZAP versions - zero-copy binary format

// ZAPWarpMessage header (48 bytes fixed)
type ZAPWarpMessage struct {
	SourceChainID      [32]byte // Fixed chain ID
	DestinationChainID [32]byte
	Nonce              uint64
	Timestamp          int64
	PayloadPtr         uint32 // offset to payload
	PayloadLen         uint32
	SigsPtr            uint32 // offset to signatures
	SigsCount          uint32
	// Variable data follows
}

const warpHeaderSize = 32 + 32 + 8 + 8 + 4 + 4 + 4 + 4 // 96 bytes

func zapEncodeWarpMessage(buf []byte, srcChain, dstChain [32]byte, nonce uint64, ts int64, payload []byte, sigs [][]byte) int {
	offset := 0

	// Fixed header
	copy(buf[offset:], srcChain[:])
	offset += 32
	copy(buf[offset:], dstChain[:])
	offset += 32
	binary.LittleEndian.PutUint64(buf[offset:], nonce)
	offset += 8
	binary.LittleEndian.PutUint64(buf[offset:], uint64(ts))
	offset += 8

	// Payload pointer/length
	payloadOffset := warpHeaderSize
	binary.LittleEndian.PutUint32(buf[offset:], uint32(payloadOffset))
	offset += 4
	binary.LittleEndian.PutUint32(buf[offset:], uint32(len(payload)))
	offset += 4

	// Signatures pointer/count
	sigsOffset := payloadOffset + len(payload)
	binary.LittleEndian.PutUint32(buf[offset:], uint32(sigsOffset))
	offset += 4
	binary.LittleEndian.PutUint32(buf[offset:], uint32(len(sigs)))
	offset += 4

	// Write payload
	copy(buf[payloadOffset:], payload)

	// Write signatures (fixed 64 bytes each for Ed25519)
	sigOffset := sigsOffset
	for _, sig := range sigs {
		copy(buf[sigOffset:], sig)
		sigOffset += 64
	}

	return sigOffset
}

func zapDecodeWarpMessage(buf []byte) (srcChain, dstChain [32]byte, nonce uint64, ts int64, payload []byte, sigs [][]byte) {
	copy(srcChain[:], buf[0:32])
	copy(dstChain[:], buf[32:64])
	nonce = binary.LittleEndian.Uint64(buf[64:])
	ts = int64(binary.LittleEndian.Uint64(buf[72:]))

	payloadPtr := binary.LittleEndian.Uint32(buf[80:])
	payloadLen := binary.LittleEndian.Uint32(buf[84:])
	sigsPtr := binary.LittleEndian.Uint32(buf[88:])
	sigsCount := binary.LittleEndian.Uint32(buf[92:])

	payload = buf[payloadPtr : payloadPtr+payloadLen]

	sigs = make([][]byte, sigsCount)
	for i := uint32(0); i < sigsCount; i++ {
		sigs[i] = buf[sigsPtr+i*64 : sigsPtr+(i+1)*64]
	}

	return
}

// Test data generators
func generateWarpPayload(size int) []byte {
	payload := make([]byte, size)
	for i := range payload {
		payload[i] = byte(i % 256)
	}
	return payload
}

func generateSignatures(count int) [][]byte {
	sigs := make([][]byte, count)
	for i := range sigs {
		sigs[i] = make([]byte, 64)
		for j := range sigs[i] {
			sigs[i][j] = byte((i + j) % 256)
		}
	}
	return sigs
}

func generateSignatureStrings(count int) []string {
	sigs := make([]string, count)
	for i := range sigs {
		sig := make([]byte, 64)
		for j := range sig {
			sig[j] = byte((i + j) % 256)
		}
		sigs[i] = string(sig)
	}
	return sigs
}

// Warp message encoding benchmarks
func BenchmarkZAPWarpMessage(b *testing.B) {
	srcChain := sha256.Sum256([]byte("source-chain"))
	dstChain := sha256.Sum256([]byte("dest-chain"))
	payload := generateWarpPayload(1024)
	sigs := generateSignatures(10) // 10 validator signatures

	buf := make([]byte, 8192)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		zapEncodeWarpMessage(buf, srcChain, dstChain, uint64(i), 1706000000000, payload, sigs)
	}
}

func BenchmarkJSONWarpMessage(b *testing.B) {
	msg := JSONWarpMessage{
		SourceChainID:      "2JVSBoinj9C2J33VntvzYtVJNZdN2NKiwwKjcumHUWEb5DbBrm",
		DestinationChainID: "yH8D7ThNJkxmtkuv2jgBa4P1Rn3Qpr4pPr7QYNfcdoS6k6HWp",
		Nonce:              12345,
		Timestamp:          1706000000000,
		Payload:            generateWarpPayload(1024),
		Signatures:         generateSignatureStrings(10),
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		json.Marshal(msg)
	}
}

func BenchmarkZAPWarpDecode(b *testing.B) {
	srcChain := sha256.Sum256([]byte("source-chain"))
	dstChain := sha256.Sum256([]byte("dest-chain"))
	payload := generateWarpPayload(1024)
	sigs := generateSignatures(10)

	buf := make([]byte, 8192)
	zapEncodeWarpMessage(buf, srcChain, dstChain, 12345, 1706000000000, payload, sigs)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		zapDecodeWarpMessage(buf)
	}
}

func BenchmarkJSONWarpDecode(b *testing.B) {
	msg := JSONWarpMessage{
		SourceChainID:      "2JVSBoinj9C2J33VntvzYtVJNZdN2NKiwwKjcumHUWEb5DbBrm",
		DestinationChainID: "yH8D7ThNJkxmtkuv2jgBa4P1Rn3Qpr4pPr7QYNfcdoS6k6HWp",
		Nonce:              12345,
		Timestamp:          1706000000000,
		Payload:            generateWarpPayload(1024),
		Signatures:         generateSignatureStrings(10),
	}
	data, _ := json.Marshal(msg)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		var decoded JSONWarpMessage
		json.Unmarshal(data, &decoded)
	}
}

// Validator set update benchmarks (consensus critical path)
func BenchmarkZAPValidatorSet100(b *testing.B) {
	// 100 validators, typical network size
	buf := make([]byte, 100*1024) // 100KB

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		offset := 0
		// Header: epoch + count + total_stake
		binary.LittleEndian.PutUint64(buf[offset:], 12345) // epoch
		offset += 8
		binary.LittleEndian.PutUint32(buf[offset:], 100) // count
		offset += 4
		binary.LittleEndian.PutUint64(buf[offset:], 10000000) // total stake
		offset += 8

		// Each validator: 32-byte nodeID + 48-byte pubkey + 8-byte stake + 8+8 times
		for j := 0; j < 100; j++ {
			// NodeID (32 bytes)
			binary.LittleEndian.PutUint64(buf[offset:], uint64(j))
			offset += 32
			// PubKey (48 bytes BLS)
			offset += 48
			// Stake
			binary.LittleEndian.PutUint64(buf[offset:], 100000)
			offset += 8
			// Start/End times
			binary.LittleEndian.PutUint64(buf[offset:], 1706000000000)
			offset += 8
			binary.LittleEndian.PutUint64(buf[offset:], 1706000000000+86400*365)
			offset += 8
		}
	}
}

func BenchmarkJSONValidatorSet100(b *testing.B) {
	validators := make([]JSONValidator, 100)
	for i := range validators {
		validators[i] = JSONValidator{
			NodeID:    "NodeID-7Xhw2mDxuDS44j42TCB6U5579esbSt3Lg",
			PublicKey: "0x8a2fc8c01c7a2f8b6c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b",
			Stake:     100000,
			StartTime: 1706000000000,
			EndTime:   1706000000000 + 86400*365,
		}
	}

	set := JSONValidatorSet{
		Epoch:      12345,
		Validators: validators,
		TotalStake: 10000000,
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		json.Marshal(set)
	}
}

// Consensus vote benchmarks (latency critical)
func BenchmarkZAPConsensusVote(b *testing.B) {
	buf := make([]byte, 256)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		offset := 0
		// BlockHash (32 bytes)
		offset += 32
		// Height
		binary.LittleEndian.PutUint64(buf[offset:], 1000000)
		offset += 8
		// Round
		binary.LittleEndian.PutUint32(buf[offset:], 1)
		offset += 4
		// ValidatorID (32 bytes)
		offset += 32
		// Signature (64 bytes)
		offset += 64
		// Timestamp
		binary.LittleEndian.PutUint64(buf[offset:], 1706000000000)
	}
}

func BenchmarkJSONConsensusVote(b *testing.B) {
	vote := JSONConsensusVote{
		BlockHash:   "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
		Height:      1000000,
		Round:       1,
		ValidatorID: "NodeID-7Xhw2mDxuDS44j42TCB6U5579esbSt3Lg",
		Signature:   "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef12345678",
		Timestamp:   1706000000000,
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		json.Marshal(vote)
	}
}

// Batch consensus votes (1000 votes, typical block attestation)
func BenchmarkZAPConsensusVoteBatch1000(b *testing.B) {
	buf := make([]byte, 256*1000)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		for j := 0; j < 1000; j++ {
			offset := j * 144 // Fixed vote size
			// BlockHash (32 bytes)
			binary.LittleEndian.PutUint64(buf[offset:], uint64(j))
			offset += 32
			// Height
			binary.LittleEndian.PutUint64(buf[offset:], 1000000)
			offset += 8
			// Round
			binary.LittleEndian.PutUint32(buf[offset:], 1)
			offset += 4
			// ValidatorID (32 bytes)
			offset += 32
			// Signature (64 bytes)
			offset += 64
			// Timestamp
			binary.LittleEndian.PutUint64(buf[offset:], 1706000000000)
		}
	}
}

func BenchmarkJSONConsensusVoteBatch1000(b *testing.B) {
	votes := make([]JSONConsensusVote, 1000)
	for i := range votes {
		votes[i] = JSONConsensusVote{
			BlockHash:   "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
			Height:      1000000,
			Round:       1,
			ValidatorID: "NodeID-7Xhw2mDxuDS44j42TCB6U5579esbSt3Lg",
			Signature:   "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef12345678",
			Timestamp:   1706000000000,
		}
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		json.Marshal(votes)
	}
}

// State sync benchmark (memory-mapped access simulation)
func BenchmarkZAPStateAccess(b *testing.B) {
	// Simulate accessing random state in a 1MB buffer
	state := make([]byte, 1024*1024)
	for i := range state {
		state[i] = byte(i % 256)
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		// Direct access to specific offset (simulating mmap)
		offset := (i * 1024) % (1024 * 1024)
		_ = binary.LittleEndian.Uint64(state[offset:])
	}
}

func BenchmarkJSONStateAccess(b *testing.B) {
	// Must parse entire state to access any field
	state := map[string]interface{}{
		"accounts": make([]map[string]interface{}, 1000),
	}
	for i := 0; i < 1000; i++ {
		state["accounts"].([]map[string]interface{})[i] = map[string]interface{}{
			"address": "0x1234567890abcdef",
			"balance": 100000,
			"nonce":   i,
		}
	}
	data, _ := json.Marshal(state)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		var parsed map[string]interface{}
		json.Unmarshal(data, &parsed)
		// Access one account
		_ = parsed["accounts"].([]interface{})[i%1000]
	}
}
