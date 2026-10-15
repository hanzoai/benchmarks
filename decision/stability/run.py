"""Every request of requests.jsonl.gz, three times, through POST /v1/decisions.

The body is the request's own with `model` set. Repeat 1 runs over every request before repeat 2
starts. With several URLs (replicas of one server) request i's repeat r goes to URL (i + r) mod
their number, so with three or more each repeat of a request is answered by another replica, as
the recorded Kai run was. Each answer is one line of OUT: id, rep, status, the answer, its digest
(score.py), the routing it names and the latency; a run resumes where it stopped. A refusal to
queue, a 5xx or a transport error is retried 6 times with backoff; one still failing is written
with its status.

    export HANZO_API_KEY=...
    python stability/run.py --url https://api.hanzo.ai --out runs/kai.jsonl [--limit 50]
    python stability/run.py --url http://127.0.0.1:8081,http://127.0.0.1:8082,http://127.0.0.1:8083 --out runs/kai.jsonl
    python stability/score.py runs/kai.jsonl

Standard library only.
"""
import argparse
import concurrent.futures as cf
import gzip
import json
import os
import time
import urllib.error
import urllib.request

from score import digest

HERE = os.path.dirname(os.path.abspath(__file__))
REPEATS = 3
RETRY = {429, 500, 502, 503, 504, 529}


def post(url, key, body):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read()), r.headers
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(text), e.headers
        except ValueError:
            return e.code, {"error": text[:500]}, e.headers


def ask(url, key, model, r, rep):
    body = dict(r["body"], model=model)
    (qk,) = r["body"]["questions"]
    start = time.time()
    status, d, headers = 0, {}, {}
    for attempt in range(6):
        try:
            status, d, headers = post(url, key, body)
        except Exception as e:  # transport: retried like a 5xx
            status, d, headers = -1, {"error": repr(e)[:500]}, {}
        if status == 200 or (status not in RETRY and status != -1):
            break
        try:
            wait = max(2 ** attempt, float(headers.get("retry-after", 0) or 0))
        except (TypeError, ValueError):
            wait = 2 ** attempt
        time.sleep(min(wait, 60))
    out = {"id": r["id"], "rep": rep, "status": status, "latency_ms": round((time.time() - start) * 1000)}
    if status == 200:
        out["answer"] = d["answers"][qk]
        out["digest"] = digest(out["answer"])
        out["routing"] = {k: v for k, v in (d.get("routing") or {}).items() if k in ("backend", "checkpoint", "sha256", "device")}
    else:
        out["error"] = d.get("error", d)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="https://api.hanzo.ai", help="one server, or several replicas comma-separated")
    ap.add_argument("--model", default="kai")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="the first N requests (a sample)")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    urls = [u.rstrip("/") + "/v1/decisions" for u in a.url.split(",")]
    key = os.environ.get("HANZO_API_KEY")
    reqs = [json.loads(l) for l in gzip.open(os.path.join(HERE, "requests.jsonl.gz"), "rt")]
    reqs = reqs[:a.limit] if a.limit else reqs
    index = {r["id"]: n for n, r in enumerate(reqs)}
    done = set()
    if os.path.exists(a.out):
        for l in open(a.out):
            x = json.loads(l)
            if x["status"] == 200:
                done.add((x["id"], x["rep"]))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "a") as f:
        for rep in range(1, REPEATS + 1):
            todo = [r for r in reqs if (r["id"], rep) not in done]
            print("%s rep %d: %d requests" % (a.model, rep, len(todo)), flush=True)
            with cf.ThreadPoolExecutor(a.workers) as ex:
                for x in ex.map(lambda r: ask(urls[(index[r["id"]] + rep) % len(urls)], key, a.model, r, rep), todo):
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
                    f.flush()
                    if x["status"] != 200:
                        print("  fail %s rep %d: %s %s" % (x["id"], rep, x["status"], str(x.get("error"))[:200]), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
