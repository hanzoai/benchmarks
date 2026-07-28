FA=~/fa-build/release/hanzo; BASE=~/cuda-build/release/hanzo; LB=~/llama.cpp/build/bin/llama-bench
M=~/models; f8=Qwen_Qwen3-8B-Q4_K_M.gguf
echo "## 8B coherence (FA correct?)"; $FA run --format gguf -m $M -f $f8 -i "Capital of France?" 2>&1 | grep -iE "Paris|error|flash|panic|illegal" | head -3
echo "## 8B prefill hanzo+FLASH-ATTN"; $FA bench --prompt-len 1024 --gen-len 32 text -m $M --format gguf -f $f8 2>/dev/null | grep Prefill
echo "## 8B prefill hanzo NO-FA"; $BASE bench --prompt-len 1024 --gen-len 32 text -m $M --format gguf -f $f8 2>/dev/null | grep Prefill
echo "## 8B prefill llama-CUDA"; $LB -m $M/$f8 -p 1024 -n 0 -ngl 99 2>/dev/null | grep -iE pp1024
echo "## 8B prefill@2048 FA vs llama (FA win grows w/ context)"; $FA bench --prompt-len 2048 --gen-len 16 text -m $M --format gguf -f $f8 2>/dev/null | grep Prefill; $LB -m $M/$f8 -p 2048 -n 0 -ngl 99 2>/dev/null | grep -iE pp2048
echo FA2_DONE
