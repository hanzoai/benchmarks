#!/usr/bin/env bash
# run_bench.sh <label> <hanzo-binary-path>
# Runs the in-process `hanzo bench` decode benchmark twice (CUDA graph on/off)
# against Qwen3-30B-A3B-Instruct-2507-Q4_K_M, matching the tg128/d1 methodology
# (gen-len 128, depth 1) used for the task's reference numbers.
set -uo pipefail
LABEL="$1"; BIN="$2"
MODEL_DIR=/data/Qwen3-30B-GGUF
MODEL_FILE=Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf
OUT_DIR=/home/z/cx-bench-results
mkdir -p "$OUT_DIR"

[[ -x "$BIN" ]] || { echo "no binary at $BIN" >&2; exit 2; }

for mode in graph eager; do
  if [[ "$mode" == "graph" ]]; then ENV=(env CUDA_GRAPHS=1); else ENV=(env CUDA_GRAPHS=0); fi
  LOG="$OUT_DIR/${LABEL}.${mode}.log"
  echo ">>> $LABEL / $mode -> $LOG" >&2
  "${ENV[@]}" BENCH_OUT="$OUT_DIR/${LABEL}.${mode}.out" "$BIN" bench \
    -m "$MODEL_DIR" -f "$MODEL_FILE" --format gguf \
    --paged-attn on --pa-context-len 8192 \
    --prompt-len 512 --gen-len 128 --depth 1 \
    --iterations 5 --warmup 1 \
    > "$LOG" 2>&1
  rc=$?
  echo "    exit=$rc" >&2
  grep -E "Decode|Prefill" "$LOG" | grep -v "INFO\|DEBUG" || tail -20 "$LOG"
done
