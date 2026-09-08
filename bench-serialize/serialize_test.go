package serialize

import (
	"encoding/binary"
	"encoding/json"
	"testing"
	"unsafe"
)

// Message structures for benchmarking

// JSONMessage represents a typical agent tool call
type JSONMessage struct {
	ID        uint64   `json:"id"`
	Type      string   `json:"type"`
	Timestamp int64    `json:"timestamp"`
	Payload   string   `json:"payload"`
	Tags      []string `json:"tags"`
}

// ZAPMessage is a zero-copy representation
// The wire format IS the memory format
type ZAPMessage struct {
	ID           uint64
	Type         uint32
	_padding     uint32
	Timestamp    int64
	PayloadPtr   uint32 // offset to payload
	PayloadLen   uint32
	TagsPtr      uint32 // offset to tags array
	TagsCount    uint32
	// Variable data follows in same buffer
}

// Pre-allocated buffer for ZAP (simulating arena allocation)
var zapArena = make([]byte, 64*1024) // 64KB arena

func BenchmarkJSONEncode(b *testing.B) {
	msg := JSONMessage{
		ID:        12345,
		Type:      "tool_call",
		Timestamp: 1706000000000,
		Payload:   "Execute function get_weather with args: {\"location\": \"San Francisco\"}",
		Tags:      []string{"weather", "api", "external"},
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		_, err := json.Marshal(msg)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkJSONDecode(b *testing.B) {
	msg := JSONMessage{
		ID:        12345,
		Type:      "tool_call",
		Timestamp: 1706000000000,
		Payload:   "Execute function get_weather with args: {\"location\": \"San Francisco\"}",
		Tags:      []string{"weather", "api", "external"},
	}
	data, _ := json.Marshal(msg)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		var decoded JSONMessage
		err := json.Unmarshal(data, &decoded)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkJSONRoundTrip(b *testing.B) {
	msg := JSONMessage{
		ID:        12345,
		Type:      "tool_call",
		Timestamp: 1706000000000,
		Payload:   "Execute function get_weather with args: {\"location\": \"San Francisco\"}",
		Tags:      []string{"weather", "api", "external"},
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		data, _ := json.Marshal(msg)
		var decoded JSONMessage
		json.Unmarshal(data, &decoded)
	}
}

// ZAP encoding: write directly to buffer (zero-copy)
func zapEncode(buf []byte, id uint64, msgType uint32, timestamp int64, payload string, tags []string) int {
	offset := 0

	// Write fixed header (32 bytes)
	binary.LittleEndian.PutUint64(buf[offset:], id)
	offset += 8
	binary.LittleEndian.PutUint32(buf[offset:], msgType)
	offset += 4
	offset += 4 // padding
	binary.LittleEndian.PutUint64(buf[offset:], uint64(timestamp))
	offset += 8

	// Payload pointer and length
	payloadOffset := 40 // starts after header (8+4+4+8+4+4+4+4 = 40 bytes)
	binary.LittleEndian.PutUint32(buf[offset:], uint32(payloadOffset))
	offset += 4
	binary.LittleEndian.PutUint32(buf[offset:], uint32(len(payload)))
	offset += 4

	// Tags pointer and count
	tagsOffset := payloadOffset + len(payload)
	binary.LittleEndian.PutUint32(buf[offset:], uint32(tagsOffset))
	offset += 4
	binary.LittleEndian.PutUint32(buf[offset:], uint32(len(tags)))
	offset += 4

	// Write payload (variable data)
	copy(buf[payloadOffset:], payload)

	// Write tags (as length-prefixed strings)
	tagOffset := tagsOffset
	for _, tag := range tags {
		binary.LittleEndian.PutUint16(buf[tagOffset:], uint16(len(tag)))
		tagOffset += 2
		copy(buf[tagOffset:], tag)
		tagOffset += len(tag)
	}

	return tagOffset
}

// ZAP decoding: just cast and read (zero-copy)
func zapDecode(buf []byte) (id uint64, msgType uint32, timestamp int64, payload string, tags []string) {
	id = binary.LittleEndian.Uint64(buf[0:])
	msgType = binary.LittleEndian.Uint32(buf[8:])
	timestamp = int64(binary.LittleEndian.Uint64(buf[16:]))

	payloadPtr := binary.LittleEndian.Uint32(buf[24:])
	payloadLen := binary.LittleEndian.Uint32(buf[28:])
	tagsPtr := binary.LittleEndian.Uint32(buf[32:])
	tagsCount := binary.LittleEndian.Uint32(buf[36:])

	// Zero-copy string access (unsafe but fast)
	payload = unsafe.String(&buf[payloadPtr], payloadLen)

	// Read tags
	tags = make([]string, tagsCount)
	offset := int(tagsPtr)
	for i := uint32(0); i < tagsCount; i++ {
		tagLen := binary.LittleEndian.Uint16(buf[offset:])
		offset += 2
		tags[i] = unsafe.String(&buf[offset], int(tagLen))
		offset += int(tagLen)
	}

	return
}

func BenchmarkZAPEncode(b *testing.B) {
	buf := make([]byte, 1024)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		zapEncode(buf, 12345, 1, 1706000000000,
			"Execute function get_weather with args: {\"location\": \"San Francisco\"}",
			[]string{"weather", "api", "external"})
	}
}

func BenchmarkZAPDecode(b *testing.B) {
	buf := make([]byte, 1024)
	zapEncode(buf, 12345, 1, 1706000000000,
		"Execute function get_weather with args: {\"location\": \"San Francisco\"}",
		[]string{"weather", "api", "external"})

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		zapDecode(buf)
	}
}

func BenchmarkZAPRoundTrip(b *testing.B) {
	buf := make([]byte, 1024)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		zapEncode(buf, 12345, 1, 1706000000000,
			"Execute function get_weather with args: {\"location\": \"San Francisco\"}",
			[]string{"weather", "api", "external"})
		zapDecode(buf)
	}
}

// Zero-copy pass-through: ZAP's real advantage
// When you just need to forward a message, no encode/decode needed
func BenchmarkZAPPassthrough(b *testing.B) {
	buf := make([]byte, 1024)
	size := zapEncode(buf, 12345, 1, 1706000000000,
		"Execute function get_weather with args: {\"location\": \"San Francisco\"}",
		[]string{"weather", "api", "external"})

	destBuf := make([]byte, 1024)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		// Just copy the bytes - no encode/decode!
		copy(destBuf, buf[:size])
	}
}

func BenchmarkJSONPassthrough(b *testing.B) {
	msg := JSONMessage{
		ID:        12345,
		Type:      "tool_call",
		Timestamp: 1706000000000,
		Payload:   "Execute function get_weather with args: {\"location\": \"San Francisco\"}",
		Tags:      []string{"weather", "api", "external"},
	}
	data, _ := json.Marshal(msg)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		// Must decode to inspect/route, then re-encode
		var decoded JSONMessage
		json.Unmarshal(data, &decoded)
		json.Marshal(decoded)
	}
}

// Batch operations
func BenchmarkZAPBatch100(b *testing.B) {
	buf := make([]byte, 100*1024) // 100KB for 100 messages

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		offset := 0
		for j := 0; j < 100; j++ {
			size := zapEncode(buf[offset:], uint64(j), 1, 1706000000000,
				"Execute function get_weather with args: {\"location\": \"San Francisco\"}",
				[]string{"weather", "api", "external"})
			offset += size
		}
	}
}

func BenchmarkJSONBatch100(b *testing.B) {
	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		for j := 0; j < 100; j++ {
			msg := JSONMessage{
				ID:        uint64(j),
				Type:      "tool_call",
				Timestamp: 1706000000000,
				Payload:   "Execute function get_weather with args: {\"location\": \"San Francisco\"}",
				Tags:      []string{"weather", "api", "external"},
			}
			json.Marshal(msg)
		}
	}
}

// Large message benchmark (32KB context window update)
func BenchmarkZAPLargeMessage(b *testing.B) {
	payload := make([]byte, 32*1024)
	for i := range payload {
		payload[i] = byte('A' + (i % 26))
	}

	buf := make([]byte, 64*1024)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		zapEncode(buf, 12345, 1, 1706000000000, string(payload), nil)
	}
}

func BenchmarkJSONLargeMessage(b *testing.B) {
	payload := make([]byte, 32*1024)
	for i := range payload {
		payload[i] = byte('A' + (i % 26))
	}

	msg := JSONMessage{
		ID:        12345,
		Type:      "context_update",
		Timestamp: 1706000000000,
		Payload:   string(payload),
		Tags:      nil,
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		json.Marshal(msg)
	}
}
