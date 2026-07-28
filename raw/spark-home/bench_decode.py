#!/usr/bin/env python3
"""Single-stream DECODE tok/s bench: streams /v1/completions, separates TTFT from decode rate.
Usage: bench_decode.py <port> <label> [n_predict] [n_runs] [prompt_tokens]
Decode rate = (tokens_after_first) / (time_from_first_token_to_last_token).
"""
import sys, time, json, urllib.request, statistics

port = int(sys.argv[1])
label = sys.argv[2]
n_predict = int(sys.argv[3]) if len(sys.argv) > 3 else 256
n_runs = int(sys.argv[4]) if len(sys.argv) > 4 else 5
# A fixed, deterministic-ish prompt. Short prompt so TTFT/prefill is minimal & decode dominates.
prompt = "Write a long detailed story about a robot exploring a distant planet. Begin now:"

url = f"http://127.0.0.1:{port}/v1/completions"

def one_run():
    body = json.dumps({
        "model": "default",
        "prompt": prompt,
        "max_tokens": n_predict,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    t_first = None
    t_last = None
    n_tok = 0
    usage = None
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if obj.get("usage"):
                usage = obj["usage"]
            choices = obj.get("choices") or []
            if not choices:
                continue
            txt = choices[0].get("text", "")
            if txt:
                now = time.perf_counter()
                if t_first is None:
                    t_first = now
                t_last = now
                n_tok += 1
    if t_first is None or t_last is None or n_tok < 2:
        return None
    ttft = t_first - t0
    decode_t = t_last - t_first
    decode_toks = n_tok - 1  # tokens emitted AFTER the first
    decode_rate = decode_toks / decode_t if decode_t > 0 else 0.0
    comp_tokens = usage.get("completion_tokens") if usage else None
    return ttft, decode_rate, n_tok, comp_tokens

rates = []
ttfts = []
detail = []
for i in range(n_runs):
    r = one_run()
    if r is None:
        detail.append("run failed")
        continue
    ttft, rate, n_tok, comp = r
    rates.append(rate)
    ttfts.append(ttft)
    detail.append(f"run{i}: decode={rate:.1f} tok/s ttft={ttft*1000:.0f}ms streamed_chunks={n_tok} usage_completion={comp}")

if not rates:
    print(json.dumps({"label": label, "port": port, "error": "all runs failed", "detail": detail}))
    sys.exit(1)

# Best (peak) decode rate + median for stability.
result = {
    "label": label,
    "port": port,
    "n_predict": n_predict,
    "n_runs": len(rates),
    "decode_best": round(max(rates), 1),
    "decode_median": round(statistics.median(rates), 1),
    "decode_mean": round(statistics.mean(rates), 1),
    "ttft_median_ms": round(statistics.median(ttfts) * 1000, 0),
    "detail": detail,
}
print(json.dumps(result, indent=2))
