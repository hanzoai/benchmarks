#!/usr/bin/env bash
set -u
BIN="$1"; LABEL="$2"; EXTRA="${3:-}"
cd ~/work/hanzo/engine
export CUDA_ROOT=/usr/local/cuda CUDA_COMPUTE_CAP=121 PATH=/usr/local/cuda/bin:$PATH
OUT=~/bench_out/${LABEL}.log
echo "=== $LABEL BIN=$BIN EXTRA=[$EXTRA] $(date) ===" > "$OUT"
env $EXTRA "$BIN" bench \
  --prompt-len 512 --gen-len 128 --iterations 3 --warmup 1 \
  auto -m ~/models/Qwen3.6-35B-A3B-GGUF -f Qwen3.6-35B-A3B-UD-Q4_K_M.gguf --format gguf \
  >> "$OUT" 2>&1
echo "=== EXIT $? $(date) ===" >> "$OUT"
