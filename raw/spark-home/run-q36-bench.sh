#!/usr/bin/env bash
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
~/work/hanzo-evobuild/engine/target/release/hanzo bench --format gguf -m ~/work/qwen36 -f qwen3.6.gguf --prompt-len 64 --gen-len 64 --iterations 1
echo "BENCH_EXIT=$?"
