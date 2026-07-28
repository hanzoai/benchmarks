#!/bin/bash
set -u
LB=/home/z/llama.cpp/build/bin/llama-bench
BIN=/home/z/work/hanzo/engine-dtype/hanzo-baseline
MDIR=/home/z/models; MF=Qwen_Qwen3-8B-Q4_K_M.gguf
echo "=== GPU util pre-check ==="; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
echo "=== ComfyUI queue ==="; curl -s http://localhost:8188/queue 2>/dev/null | head -c 120; echo
echo "===== LLAMA.CPP fa=1 ====="
$LB -m $MDIR/$MF -fa 1 -p 512,1024,2048 -n 0 -r 5 2>/dev/null | grep -iE "pp512|pp1024|pp2048|model"
echo "===== HANZO BASELINE bf16 (auto) ====="
BENCH_OUT=/tmp/base_bf16.out $BIN bench --format gguf -m $MDIR -f $MF --pa-context-len 4096 --prompt-len 512,1024,2048 --gen-len 0 --depth 1 --iterations 5 --warmup 2 2>/dev/null | grep -E "Prefill|Model"
echo "--- durable bf16 ---"; cat /tmp/base_bf16.out 2>/dev/null
echo "===== HANZO BASELINE f16 ====="
BENCH_OUT=/tmp/base_f16.out $BIN bench --format gguf -m $MDIR -f $MF --dtype f16 --pa-context-len 4096 --prompt-len 512,1024,2048 --gen-len 0 --depth 1 --iterations 5 --warmup 2 2>/dev/null | grep -E "Prefill|Model"
echo "--- durable f16 ---"; cat /tmp/base_f16.out 2>/dev/null
echo BASELINE_BENCH_DONE
