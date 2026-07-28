#!/usr/bin/env bash
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
~/work/hanzo-evobuild/engine/target/release/hanzo bench --format gguf -m ~/models -f Qwen3-30B-A3B-Q4_K_M.gguf --prompt-len 64 --gen-len 64 --iterations 1
echo "BENCH_EXIT=$?"
