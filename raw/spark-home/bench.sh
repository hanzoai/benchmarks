#!/bin/bash
# bench.sh <model_dir> <gguf_file> <label> [gen_len] [depth]
# A/B decode throughput: CUDA_GRAPHS=0 (eager) vs =1 (decode graph). Reports prefill+decode T/s.
set -u
MDIR="$1"; MF="$2"; LABEL="$3"; GEN="${4:-128}"; DEPTH="${5:-4}"
BIN=/home/z/opfus-build/release/hanzo
bench() {
  local g="$1"
  echo "----- $LABEL  CUDA_GRAPHS=$g  (gen=$GEN depth=$DEPTH) -----"
  CUDA_GRAPHS="$g" "$BIN" bench --format gguf -m "$MDIR" -f "$MF" \
    --prompt-len 512 --gen-len "$GEN" --depth "$DEPTH" --iterations 3 --warmup 1 2>/dev/null \
    | grep -E "Prefill|Decode|T/s"
}
echo "===== BENCH: $LABEL ====="
bench 0
bench 1
echo
