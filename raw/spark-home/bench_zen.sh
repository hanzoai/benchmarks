#!/usr/bin/env bash
# Streaming decode benchmark for zen-nano on a test port.
# Usage: bench_zen.sh <PORT> <MAXTOK> [PROMPT]
set -u
PORT="${1:?port}"
MAXTOK="${2:-256}"
PROMPT="${3:-Write a detailed essay about the history of computing, covering the abacus, mechanical calculators, vacuum tubes, transistors, integrated circuits, microprocessors, and modern GPUs. Be thorough and verbose.}"

URL="http://127.0.0.1:${PORT}/v1/completions"

python3 - "$URL" "$MAXTOK" "$PROMPT" <<'PY'
import sys, json, time, urllib.request
url, maxtok, prompt = sys.argv[1], int(sys.argv[2]), sys.argv[3]
body = json.dumps({
    "model":"default","prompt":prompt,"max_tokens":maxtok,
    "temperature":0.0,"stream":True,"stream_options":{"include_usage":True},
}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
t0=time.perf_counter(); ttft=None; n_after=0; first_tok_time=None; last=t0
usage=None
with urllib.request.urlopen(req, timeout=300) as r:
    for raw in r:
        line=raw.decode("utf-8","replace").strip()
        if not line.startswith("data:"): continue
        data=line[5:].strip()
        if data=="[DONE]": break
        try: obj=json.loads(data)
        except: continue
        ch=obj.get("choices",[])
        if ch and ch[0].get("text"):
            now=time.perf_counter()
            if ttft is None:
                ttft=now-t0; first_tok_time=now
            else:
                n_after+=1
            last=now
        if obj.get("usage"): usage=obj["usage"]
t_end=time.perf_counter()
comp = usage.get("completion_tokens", n_after+1) if usage else n_after+1
decode_span = (last - first_tok_time) if first_tok_time is not None else 0.0
dec_toks = comp-1
dec_rate = dec_toks/decode_span if decode_span>0 else 0
e2e = t_end - t0
e2e_rate = comp/e2e if e2e>0 else 0
print(f"TTFT={ttft*1000:.0f}ms  completion_tokens={comp}  decode_span={decode_span:.3f}s  "
      f"DECODE={dec_rate:.1f} tok/s  e2e={e2e:.3f}s  e2e_rate={e2e_rate:.1f} tok/s")
PY
