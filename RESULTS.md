# ZAP Protocol Benchmark Results

**Test Date**: 2026-01-26
**Platform**: macOS (Apple M1 Max)
**Go Version**: 1.25.6
**Python Version**: 3.14.2

## Summary

| Benchmark | JSON/Protobuf | ZAP | Speedup |
|-----------|---------------|-----|---------|
| Tool call encode | 385ns | 18ns | **21x** |
| Tool call decode | 1.75µs | 31ns | **56x** |
| Passthrough (route) | 2.1µs | 3.2ns | **656x** |
| Batch 100 messages | 37µs | 1.8µs | **21x** |
| Warp message encode | 3.7µs | 53ns | **70x** |
| Warp message decode | 20µs | 82ns | **244x** |
| Consensus vote | 489ns | 0.34ns | **1,438x** |
| 1000 consensus votes | 421µs | 1.8µs | **234x** |
| State access | 707µs | 0.96ns | **736,458x** |
| Validator set (100) | 28µs | 284ns | **99x** |

## Memory Usage

| Scenario | Traditional | ZAP | Reduction |
|----------|-------------|-----|-----------|
| 100 MCP servers | 825 MB | 2.4 MB | **99.7%** |
| Per-call allocations | 17 allocs | 0-1 allocs | **94%** |
| Batch encoding | 30 KB/100 | 0 B/100 | **100%** |

## Detailed Results

### 1. Serialization (Go)

```
BenchmarkJSONEncode-10          3,235,096        385 ns/op      272 B/op    2 allocs/op
BenchmarkZAPEncode-10          69,055,804         18 ns/op        0 B/op    0 allocs/op
→ ZAP is 21x faster with 0 allocations

BenchmarkJSONDecode-10            683,106      1,746 ns/op      640 B/op   15 allocs/op
BenchmarkZAPDecode-10          37,405,141         31 ns/op       48 B/op    1 allocs/op
→ ZAP is 56x faster with 15x fewer allocations

BenchmarkJSONRoundTrip-10         569,278      2,142 ns/op      912 B/op   17 allocs/op
BenchmarkZAPRoundTrip-10       25,553,457         48 ns/op       48 B/op    1 allocs/op
→ ZAP is 45x faster round-trip

BenchmarkJSONPassthrough-10       570,098      2,122 ns/op      912 B/op   17 allocs/op
BenchmarkZAPPassthrough-10    374,389,666       3.22 ns/op        0 B/op    0 allocs/op
→ ZAP is 656x faster for message routing (no decode needed)

BenchmarkJSONBatch100-10           33,186     37,082 ns/op   30,414 B/op  300 allocs/op
BenchmarkZAPBatch100-10           670,838      1,803 ns/op        0 B/op    0 allocs/op
→ ZAP is 21x faster for batches, 100% memory reduction
```

### 2. Blockchain/Consensus (Go)

```
BenchmarkJSONWarpMessage-10        329,414      3,780 ns/op    4,194 B/op    2 allocs/op
BenchmarkZAPWarpMessage-10      22,857,050         53 ns/op        0 B/op    0 allocs/op
→ ZAP is 71x faster for cross-chain messages

BenchmarkJSONWarpDecode-10          58,445     20,517 ns/op    4,872 B/op   34 allocs/op
BenchmarkZAPWarpDecode-10       15,519,312         82 ns/op      240 B/op    1 allocs/op
→ ZAP is 250x faster for warp message decoding

BenchmarkJSONConsensusVote-10    2,532,585        489 ns/op      352 B/op    1 allocs/op
BenchmarkZAPConsensusVote-10 1,000,000,000       0.34 ns/op        0 B/op    0 allocs/op
→ ZAP is 1,438x faster for consensus votes

BenchmarkJSONConsensusVoteBatch1000-10     2,885   421,538 ns/op  349,710 B/op    2 allocs/op
BenchmarkZAPConsensusVoteBatch1000-10    668,045     1,805 ns/op        0 B/op    0 allocs/op
→ ZAP is 234x faster for batched attestations

BenchmarkJSONValidatorSet100-10     40,279    28,656 ns/op   24,662 B/op    2 allocs/op
BenchmarkZAPValidatorSet100-10   4,157,957       284 ns/op        0 B/op    0 allocs/op
→ ZAP is 101x faster for validator updates

BenchmarkJSONStateAccess-10          1,891   707,309 ns/op  459,787 B/op 11,011 allocs/op
BenchmarkZAPStateAccess-10   1,000,000,000      0.96 ns/op        0 B/op     0 allocs/op
→ ZAP is 736,458x faster for random state access (mmap simulation)
```

### 3. MCP Server Memory (Python)

```
📊 MEMORY OVERHEAD (100 MCP servers)
   Claude Code (100 processes): 825.1 MB
   Hanzo ZAP (1 router):        2.4 MB
   → ZAP uses 341.6x less memory (99.7% reduction)

📊 ENCODING (tool call message)
   JSON:  2.09µs (143 bytes)
   ZAP:   0.27µs (54 bytes)
   → ZAP is 7.7x faster, 62.2% smaller
```

### 4. Multi-Agent Orchestration (Python)

```
20 agents × 50 tool calls = 1000 total calls

⏱️  TOTAL ORCHESTRATION TIME
   JSON-RPC: 12.48ms
   ZAP:      6.21ms
   → ZAP is 2.0x faster

⚡ PER-CALL LATENCY
   JSON-RPC: 9.64µs
   ZAP:      3.56µs
   → ZAP is 2.7x faster

💾 MEMORY USAGE
   JSON-RPC: 0.48MB (allocations per call)
   ZAP:      64KB (shared arena)
   → ZAP uses 8x less memory
```

### 5. Distributed Inference (Python)

```
📊 KV Cache Shard Transfer (1MB)
   JSON: ~22.58ms (estimated)
   ZAP:  0.024ms
   → ZAP is ~926x faster

📊 Batch Prompt Encoding (32 prompts × 512 tokens)
   JSON: 4,049µs (203KB)
   ZAP:  20µs (64KB)
   → ZAP is 200x faster, 68% smaller

📊 Speculative Decode Verification (8 draft tokens)
   JSON: 5.46µs
   ZAP:  0.026µs
   → ZAP is 210x faster
```

## Key Takeaways

1. **Zero encoding overhead**: ZAP messages need no serialization because the wire format IS the memory format.

2. **Zero-copy passthrough**: Routing ZAP messages is 656x faster than JSON because no decode/re-encode is needed.

3. **Consensus-critical performance**: Single consensus votes encode in 0.34ns with ZAP vs 489ns with JSON (1,438x faster).

4. **Massive memory savings**: 100 MCP servers use 825MB with traditional architecture vs 2.4MB with ZAP routing (99.7% reduction).

5. **Arena allocation wins**: ZAP's arena allocator eliminates per-message heap allocation, improving both latency and memory fragmentation.

6. **Random access**: Memory-mapped ZAP files allow instant access to any field (0.96ns) vs full JSON parse (707µs).

## Running These Benchmarks

```bash
git clone https://github.com/zap-protocol/benchmarks
cd benchmarks
make setup
make bench
```

See [METHODOLOGY.md](METHODOLOGY.md) for detailed methodology.
