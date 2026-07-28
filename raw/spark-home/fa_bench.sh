FA=~/fa-build/release/hanzo; BASE=~/cuda-build/release/hanzo
LB=~/llama.cpp/build/bin/llama-bench
M=~/models; M2=~/evo-staging/wsl-home/models
f8=Qwen_Qwen3-8B-Q4_K_M.gguf; f06=Qwen_Qwen3-0.6B-Q8_0.gguf
echo "## 8B prefill: hanzo+FLASH-ATTN"; [ -f $M/$f8 ] && $FA bench --prompt-len 1024 --gen-len 32 text -m $M --format gguf -f $f8 2>/dev/null | grep Prefill || echo "(no 8B model)"
echo "## 8B prefill: hanzo NO-FA (cuda-build)"; [ -f $M/$f8 ] && $BASE bench --prompt-len 1024 --gen-len 32 text -m $M --format gguf -f $f8 2>/dev/null | grep Prefill
echo "## 8B prefill: llama-CUDA"; [ -f $M/$f8 ] && $LB -m $M/$f8 -p 1024 -n 0 -ngl 99 2>/dev/null | grep -iE pp1024
echo "## 0.6B prefill: hanzo+FA vs llama"; $FA bench --prompt-len 1024 --gen-len 32 text -m $M2 --format gguf -f $f06 2>/dev/null | grep Prefill; $LB -m $M2/$f06 -p 1024 -n 0 -ngl 99 2>/dev/null | grep -iE pp1024
echo FA_BENCH_DONE
