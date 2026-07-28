#!/bin/bash
# fa_prefill_bench.sh <bin> <mdir> <mf> <label> <outfile>
# Pure prefill sweep (gen-len 0) + a decode check. flock-serialized, BENCH_OUT for durable results.
set -u
BIN="$1"; MDIR="$2"; MF="$3"; LABEL="$4"; OUT="$5"
echo "===== PREFILL SWEEP: $LABEL ($BIN) ====="
BENCH_OUT="${OUT}.prefill" "$BIN" bench --format gguf -m "$MDIR" -f "$MF" \
  --prompt-len 512,1024,2048,4096 --gen-len 0 --depth 1 --iterations 5 --warmup 2 2>/dev/null \
  | grep -E "Prefill|T/s|Model:"
echo "===== DECODE CHECK: $LABEL ====="
BENCH_OUT="${OUT}.decode" "$BIN" bench --format gguf -m "$MDIR" -f "$MF" \
  --prompt-len 0 --gen-len 128 --depth 4 --iterations 5 --warmup 2 2>/dev/null \
  | grep -E "Decode|T/s"
echo "--- durable results ---"; cat "${OUT}.prefill" "${OUT}.decode" 2>/dev/null
