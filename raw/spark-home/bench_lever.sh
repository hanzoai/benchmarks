#!/usr/bin/env bash
# Usage: bench_lever.sh <label> <gguf-file> <extra-env>
set -u
cd ~/work/hanzo/engine
LABEL="$1"; GGUF="$2"; EXTRA="${3:-}"
export CUDA_ROOT=/usr/local/cuda CUDA_COMPUTE_CAP=121 PATH=/usr/local/cuda/bin:$PATH
OUT=~/bench_out/${LABEL}.log
mkdir -p ~/bench_out
echo "=== $LABEL === GGUF=$GGUF EXTRA=[$EXTRA] $(date) ===" > "$OUT"
env $EXTRA ./target/release/hanzo bench \
  --prompt-len 512 --gen-len 128 --iterations 3 --warmup 1 \
  auto -m /home/z/models -f "$GGUF" --format gguf \
  >> "$OUT" 2>&1
echo "=== EXIT $? $(date) ===" >> "$OUT"
