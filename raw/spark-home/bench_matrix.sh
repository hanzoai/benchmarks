#!/bin/bash
set -u
MDIR=/home/z/models; MF=Qwen_Qwen3-8B-Q4_K_M.gguf
BASE=/home/z/work/hanzo/engine-dtype/hanzo-baseline
FIX=/home/z/work/hanzo/engine-dtype/target/release/hanzo
LB=/home/z/llama.cpp/build/bin/llama-bench
ITER=10; WARM=3
idle() { local u; for i in $(seq 1 30); do u=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits); q=$(curl -s http://localhost:8188/queue 2>/dev/null); if [ "${u:-99}" -lt 15 ] && echo "$q" | grep -q "queue_running.: \[\]"; then return 0; fi; sleep 3; done; echo "WARN: gpu not idle (u=$u)"; }
runh() { local bin=$1 dt=$2 g=$3 tag=$4; idle; echo "===== HANZO $tag (dtype=$dt prefill_graph=$g) ====="; CUDA_GRAPHS=1 CUDA_PREFILL_GRAPHS=$g BENCH_OUT=/tmp/m_$tag.out $bin bench --format gguf -m $MDIR -f $MF --dtype $dt --pa-context-len 4096 --prompt-len 512,1024,2048 --gen-len 0 --depth 1 --iterations $ITER --warmup $WARM 2>/dev/null | grep -E "Prefill"; cat /tmp/m_$tag.out 2>/dev/null | grep Prefill; }
echo "#### MATRIX START $(date +%H:%M:%S) ####"
idle; echo "===== LLAMA.CPP fa=1 ====="; $LB -m $MDIR/$MF -fa 1 -p 512,1024,2048 -n 0 -r 8 2>/dev/null | grep -iE "pp512|pp1024|pp2048"
runh $BASE bf16 0 base_bf16_eager
runh $FIX  bf16 0 fix_bf16_eager
runh $BASE f16  0 base_f16_eager
runh $FIX  f16  0 fix_f16_eager
runh $BASE bf16 1 base_bf16_graph
runh $FIX  bf16 1 fix_bf16_graph
runh $BASE f16  1 base_f16_graph
runh $FIX  f16  1 fix_f16_graph
echo "#### MATRIX DONE $(date +%H:%M:%S) ####"
