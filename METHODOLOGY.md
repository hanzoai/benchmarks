# Benchmark Methodology

## Overview

All ZAP Protocol benchmarks follow rigorous methodology to ensure reproducible, fair, and meaningful results.

## Test Environment

### Hardware
- **Reference**: AMD EPYC 7763 (64 cores), 512GB DDR4-3200
- **Acceptable**: Any modern x86-64 or ARM64 system
- **Memory**: Minimum 16GB RAM for full benchmark suite

### Software
- **OS**: Linux (Ubuntu 22.04 LTS recommended), macOS 13+, Windows 11
- **Go**: 1.21+
- **Python**: 3.11+
- **Compiler flags**: `-O3 -march=native` for Go benchmarks

## Measurement Methodology

### Time Measurements

1. **Warm-up**: 1000 iterations discarded before measurement
2. **Iterations**: Minimum 10,000 for µs-scale operations
3. **Timing**: `time.perf_counter_ns()` (Python), `testing.B` (Go)
4. **Statistics**: Report median, p95, p99 for latency-sensitive benchmarks

### Memory Measurements

1. **Heap allocations**: Counted via `runtime.MemStats` (Go) or `tracemalloc` (Python)
2. **Peak RSS**: Measured via `/proc/self/status` or `psutil`
3. **Allocation count**: Number of `malloc` calls per operation

### What We Measure

| Metric | Description | ZAP Expectation |
|--------|-------------|-----------------|
| Encoding time | Time to convert memory → wire format | ~0 (no conversion) |
| Decoding time | Time to parse wire → accessible data | ~0 (direct access) |
| Round-trip time | Encode + transmit + decode | Only transmit time |
| Memory allocations | Heap allocations per message | 0-1 (arena) |
| Memory footprint | Total memory used | Minimal overhead |

## Fairness Principles

### What ZAP Does Differently

Traditional formats:
1. **Serialize**: Convert in-memory structures to bytes
2. **Transmit**: Send bytes over network/IPC
3. **Deserialize**: Parse bytes back to memory structures

ZAP:
1. ~~Serialize~~: Wire format IS memory format
2. **Transmit**: Send bytes
3. ~~Deserialize~~: Direct pointer access

This is not "cheating" — it's the fundamental design difference. ZAP eliminates steps 1 and 3.

### Fair Comparison Rules

1. **Same data**: Identical logical content in all formats
2. **Same operations**: Both encode AND decode measured
3. **Same conditions**: Warm JIT, stable CPU frequency
4. **Real implementations**: Use production-quality libraries

### What We Don't Do

- Cherry-pick favorable scenarios
- Compare debug vs release builds
- Use artificial microbenchmarks unrelated to real usage
- Ignore memory or allocation costs

## Benchmark Categories

### 1. Serialization (`bench-serialize/`)

Core encode/decode performance for:
- Small messages (tool calls, 100-500 bytes)
- Medium messages (context updates, 1-32KB)
- Large messages (state snapshots, 1MB+)
- Batch operations (100+ messages)

### 2. Agent Communication (`bench-agents/`)

Real-world MCP patterns:
- Connection overhead (memory per server)
- Message latency (tool call round-trip)
- Multi-agent orchestration (20 agents, 50 calls each)
- Memory pressure under load

### 3. Blockchain Operations (`bench-blockchain/`)

Consensus-critical paths:
- Warp message encoding (cross-chain)
- Validator set updates (100 validators)
- Consensus votes (latency-critical)
- State access (random field reads)

### 4. Inference Infrastructure (`bench-inference/`)

Distributed AI patterns:
- KV cache shard transfer (1MB shards)
- Batch prompt encoding (32 × 512 tokens)
- Speculative decoding verification
- Model weight distribution

## Reproducing Results

```bash
# Clone and setup
git clone https://github.com/zap-protocol/benchmarks
cd benchmarks
make setup

# Run all benchmarks
make bench

# Run specific suite
make bench-serialize   # Go serialization benchmarks
make bench-agents      # Python MCP/agent benchmarks
make bench-blockchain  # Go consensus benchmarks
make bench-inference   # Python AI infrastructure benchmarks

# Generate report
make report
```

## Reporting Issues

If you find:
- Methodology problems
- Unfair comparisons
- Reproducibility issues
- Missing context

Please open an issue at https://github.com/zap-protocol/benchmarks/issues

## Statistical Rigor

### Variance Handling

- Multiple runs (default: 10 iterations per benchmark)
- Report standard deviation when > 5% of mean
- Discard outliers beyond 3σ

### Significance

- Only report speedups > 10% as "faster"
- Note when differences are within noise
- Provide confidence intervals for critical claims

## Limitations

### Known Limitations

1. **Simulated ZAP**: Benchmarks use ZAP-like binary encoding, not full ZAP implementation
2. **Network excluded**: Benchmarks measure encoding/decoding, not network I/O
3. **Single-threaded focus**: Most benchmarks are single-threaded unless noted

### When JSON/Protobuf Might Win

- Schema-less dynamic data (JSON's strength)
- Human readability requirements
- Existing ecosystem integration
- Debugging and logging scenarios

ZAP is not universally better — it's better for performance-critical paths where the schema is known at compile time.
