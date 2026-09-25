"""One request to one tier, measured: a streaming OpenAI chat client and a /metrics sampler.

    from serve import Cap, chat, measure
    r = chat(tier, messages, tier["budgets"]["none"], Cap(50))   # raw timeline
    m = measure(r, tier)                                          # tokens, seconds, KV, GPU, $

The sampler reads the server's /metrics at ~10 Hz while the request runs: vLLM
(num_requests_running, num_requests_waiting, kv_cache_usage_perc) or halogen's llama.cpp
dialect (requests_processing, requests_deferred, kv_cache_usage_ratio). KV is integrated two
ways: analytic, this request's own bytes (state_bytes + kv_bytes_per_token x live tokens) over
its streamed timeline, and sampled, the whole server's KV (usage x capacity) for validation.
"""
import http.client
import json
import threading
import time
import urllib.parse
import urllib.request

SAMPLING = {"temperature": 0.6, "top_p": 0.95, "seed": 13}
DIALECT = {
    "vllm": {"running": "vllm:num_requests_running", "waiting": "vllm:num_requests_waiting", "kv": "vllm:kv_cache_usage_perc"},
    "halogen": {"running": "llamacpp:requests_processing", "waiting": "llamacpp:requests_deferred", "kv": "llamacpp:kv_cache_usage_ratio"},
}


class Spent(Exception):
    """The study's request cap is reached."""


class Cap:
    """At most n requests in this process, shared by every thread."""

    def __init__(self, n):
        self.n, self.used, self.lock = n, 0, threading.Lock()

    def take(self):
        with self.lock:
            if self.used >= self.n:
                raise Spent(f"request cap {self.n} reached")
            self.used += 1


def metrics(tier, timeout=2.0):
    """(running, waiting, kv fraction) from the tier's /metrics, or None."""
    names = DIALECT[tier["kind"]]
    try:
        with urllib.request.urlopen(tier["endpoint"] + "/metrics", timeout=timeout) as r:
            text = r.read().decode(errors="replace")
    except OSError:
        return None
    got = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        for k, name in names.items():
            if line.startswith(name + "{") or line.startswith(name + " "):
                try:
                    got[k] = got.get(k, 0.0) + float(line.rsplit(" ", 1)[1])
                except ValueError:
                    pass
    return (got.get("running", 0.0), got.get("waiting", 0.0), got.get("kv", 0.0)) if got else None


class Sampler(threading.Thread):
    def __init__(self, tier, hz=10.0):
        super().__init__(daemon=True)
        self.tier, self.dt, self.samples, self.halt = tier, 1.0 / hz, [], threading.Event()

    def run(self):
        while not self.halt.is_set():
            t = time.time()
            m = metrics(self.tier)
            if m:
                self.samples.append((t,) + m)
            self.halt.wait(max(0.0, self.dt - (time.time() - t)))

    def stop(self):
        self.halt.set()
        self.join(timeout=3)
        return self.samples


BUSY = {}


def wait(tier, most=2, patience=300, poll=10):
    """For a live tier, hold until at most `most` requests wait in its queue; False when the
    queue stays longer than that for `patience` seconds, and then at once for the next
    `patience` seconds, so a busy server is skipped rather than waited on cell by cell."""
    if not tier.get("live"):
        return True
    now = time.time()
    if BUSY.get(tier["id"], 0) > now:
        return False
    end = now + patience
    while True:
        m = metrics(tier)
        if m is None or m[1] <= most:
            return True
        if time.time() > end:
            BUSY[tier["id"]] = time.time() + patience
            return False
        time.sleep(poll)


def body(tier, messages, budget):
    b = {"model": tier["model"], "messages": messages, "stream": True,
         "stream_options": {"include_usage": True}, **SAMPLING}
    b.update(budget)
    return b


def chat(tier, messages, budget, cap, timeout=900):
    """Stream one completion. Returns t0, ttft, end, chunk times with cumulative characters,
    content, reasoning, usage, finish reason, the server's samples and any error."""
    if not wait(tier):
        return {"t0": time.time(), "ttft": None, "end": time.time(), "times": [], "content": "", "reasoning": "",
                "usage": {}, "finish": None, "error": "busy: the live queue stayed long", "waiting": None, "samples": []}
    cap.take()
    before = metrics(tier)
    sampler = Sampler(tier)
    sampler.start()
    u = urllib.parse.urlsplit(tier["endpoint"])
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
    out = {"t0": time.time(), "ttft": None, "end": None, "times": [], "content": "", "reasoning": "",
           "usage": {}, "finish": None, "error": None, "waiting": before[1] if before else None}
    chars = 0
    content, reasoning = [], []
    try:
        conn.request("POST", "/v1/chat/completions", json.dumps(body(tier, messages, budget)),
                     {"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 200:
            out["error"] = f"http {resp.status}: {resp.read()[:300].decode(errors='replace')}"
        else:
            for raw in resp:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ev = json.loads(data)
                except ValueError:
                    continue
                if ev.get("usage"):
                    out["usage"] = ev["usage"]
                for ch in ev.get("choices") or []:
                    d = ch.get("delta") or {}
                    piece = (d.get("content") or "")
                    think = (d.get("reasoning_content") or d.get("reasoning") or "")
                    if piece or think:
                        now = time.time()
                        if out["ttft"] is None:
                            out["ttft"] = now
                        chars += len(piece) + len(think)
                        out["times"].append((now, chars))
                        content.append(piece)
                        reasoning.append(think)
                    if ch.get("finish_reason"):
                        out["finish"] = ch["finish_reason"]
    except (OSError, http.client.HTTPException) as e:
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        conn.close()
        out["end"] = time.time()
        out["samples"] = sampler.stop()
    out["content"], out["reasoning"] = "".join(content), "".join(reasoning)
    return out


def timeline(r, prompt, completion):
    """[(t, live tokens)]: prompt tokens ramp over prefill, then decode grows with the streamed
    characters (completion tokens spread over them in proportion)."""
    t0, t1, end = r["t0"], r["ttft"] or r["end"], r["end"]
    pts = [(t0, 0.0), (t1, float(prompt))]
    total = r["times"][-1][1] if r["times"] else 0
    for t, c in r["times"]:
        pts.append((t, prompt + completion * (c / total if total else 0)))
    pts.append((end, float(prompt + completion)))
    return pts


def area(pts):
    """Trapezoid integral of a piecewise-linear [(t, y)]."""
    return sum((b[0] - a[0]) * (a[1] + b[1]) / 2 for a, b in zip(pts, pts[1:]))


def steps(samples, t0, end, f):
    """Integral over [t0, end] of f(sample) held from each sample to the next."""
    s = [x for x in samples if t0 <= x[0] <= end]
    if not s:
        return 0.0
    s = [(t0,) + s[0][1:]] + s + [(end,) + s[-1][1:]]
    return sum((b[0] - a[0]) * f(a) for a, b in zip(s, s[1:]))


def measure(r, tier):
    """The metrics of one request (a chat() result) on tier."""
    u = r["usage"] or {}
    prompt = int(u.get("prompt_tokens") or 0)
    completion = int(u.get("completion_tokens") or 0)
    details = u.get("completion_tokens_details") or {}
    rc, cc = len(r["reasoning"]), len(r["content"])
    reasoning = details.get("reasoning_tokens")
    estimated = reasoning is None
    if estimated:
        reasoning = round(completion * rc / (rc + cc)) if rc + cc else 0
    t0, end = r["t0"], r["end"]
    ttft = r["ttft"] or end
    wall = end - t0
    live = area(timeline(r, prompt, completion))
    kv = tier.get("state_bytes", 0) * wall + tier.get("kv_bytes_per_token", 0) * live
    peak = tier.get("state_bytes", 0) + tier.get("kv_bytes_per_token", 0) * (prompt + completion)
    samples = r.get("samples") or []
    gpu = steps(samples, t0, end, lambda s: 1.0 / max(1.0, s[1])) if samples else wall
    gpu *= tier.get("gpus", 1)
    cap = tier.get("kv_capacity_bytes") or tier.get("kv_bytes_per_token", 0) * tier.get("kv_capacity_tokens", 0)
    return {
        "prompt_tokens": prompt, "decode_tokens": completion, "reasoning_tokens": int(reasoning),
        "reasoning_estimated": estimated, "prefill_s": ttft - t0, "decode_s": end - ttft, "latency_s": wall,
        "gpu_s": gpu, "kv_gb_s": kv / 1e9, "kv_peak_gb": peak / 1e9,
        "kv_server_gb_s": steps(samples, t0, end, lambda s: s[3] * cap) / 1e9 if samples else None,
        "kv_server_peak": max((s[3] for s in samples), default=None),
        "running_peak": max((s[1] for s in samples), default=None),
        "waiting": r.get("waiting"), "samples": len(samples),
        "usd": gpu * tier.get("usd_per_gpu_hour", 0.0) / 3600.0,
        "finish": r["finish"], "error": r["error"],
    }
