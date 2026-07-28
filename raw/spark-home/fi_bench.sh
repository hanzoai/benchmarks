#!/bin/bash
# fi_bench.sh — flashinfer_prefill A/B on zen-eco-4b (CUDA). Prefill+decode T/s, OFF vs ON.
set -u
BIN=~/work/engine-cuda-wt/target/release/hanzo-engine
MDIR=~/work/zen-eco-4b; MF=zen-eco-4b.gguf
ITER="${1:-6}"; WARM="${2:-2}"
run() { # <label> <fi>
  echo "----- prefill/decode  FLASHINFER_PREFILL=$2  ($1) -----"
  FLASHINFER_PREFILL="$2" CUDA_GRAPHS=1 "$BIN" bench --format gguf -m "$MDIR" -f "$MF" \
    --prompt-len 512 --gen-len 128 --depth 1 --iterations "$ITER" --warmup "$WARM" 2>/dev/null \
    | grep -E "Prefill|Decode"
}
echo "===== ZEN-ECO-4B flashinfer_prefill A/B (iter=$ITER warm=$WARM) ====="
run OFF 0
run ON  1
echo "----- LLAMA-CUDA ref (same window) -----"
~/work/llama.cpp/build/bin/llama-bench -m "$MDIR/$MF" -p 512 -n 128 -ngl 999 2>/dev/null | grep -iE "pp512|tg128"
