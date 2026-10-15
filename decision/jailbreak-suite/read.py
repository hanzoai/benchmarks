#!/usr/bin/env python3
"""read.py ITEMS VARIANT OUT: the suite's items through POST /v1/decisions.

ITEMS is build.py's items.jsonl. VARIANT is H (the harness's jailbreak question) or P (the
paper's detector for the item's task); prereg.json holds both, word for word. Kai's recorded
reads took only items clean for Kai (--clean); --same FILE reads exactly the items a recorded
answer file holds (results/kai-H.jsonl.gz is the recorded Kai read under H). Each answer is
appended to OUT by item id, so a run resumes; a refusal (400, 422) is final and scored as an
error, any other failure is asked again on the next run. Workers: two a URL.

    export HANZO_API_KEY=...
    python3 -I jailbreak-suite/read.py items/items.jsonl H runs/kai-H.jsonl --clean --same jailbreak-suite/results/kai-H.jsonl.gz
    python3 -I jailbreak-suite/read.py items/items.jsonl H runs/kai-H.jsonl --clean --datasets wild --limit 200
    python3 jailbreak-suite/score.py --kai runs                     # Jev from its recorded answers

Standard library only.
"""
import argparse
import concurrent.futures as cf
import gzip
import json
import os
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
Q = json.load(open(os.path.join(HERE, "prereg.json")))["questions"]


def body(it, variant, model):
    if variant == "H":
        if it["task"] not in ("injection", "jailbreak"):
            return None
        q = Q["H"]
        return {"model": model, "state": {"prompt": it["text"]}, "questions": {q["key"]: q["question"]}}
    q = Q["P"][it["task"]]
    (k,) = q["state"]
    return {"model": model, "state": {k: it["text"]}, "questions": {q["key"]: q["question"]}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("items")
    ap.add_argument("variant", choices=["H", "P"])
    ap.add_argument("out")
    ap.add_argument("--url", default="https://api.hanzo.ai", help="one server, or several comma-separated")
    ap.add_argument("--model", default="kai")
    ap.add_argument("--clean", action="store_true", help="only items clean for Kai")
    ap.add_argument("--same", help="only the items this recorded answer file holds")
    ap.add_argument("--datasets", help="only these datasets, comma-separated (wild, gandalf, ...)")
    ap.add_argument("--limit", type=int, default=0, help="the first N items to read (a sample)")
    a = ap.parse_args()
    urls = [u.rstrip("/") + "/v1/decisions" for u in a.url.split(",")]
    key = os.environ.get("HANZO_API_KEY")
    workers = int(os.environ.get("WORKERS", 2 * len(urls)))
    only = {json.loads(l)["id"] for l in gzip.open(a.same, "rt")} if a.same else None
    items = [json.loads(l) for l in open(a.items)]
    keep = set(a.datasets.split(",")) if a.datasets else None
    items = [it for it in items if (it["clean"] or not a.clean) and (only is None or it["id"] in only)
             and (keep is None or it["dataset"] in keep) and body(it, a.variant, a.model) is not None]
    items = items[:a.limit] if a.limit else items
    done = {json.loads(l)["id"] for l in open(a.out)} if os.path.exists(a.out) else set()
    todo = [it for it in items if it["id"] not in done]
    print("%d of %d to read (%s, %s)" % (len(todo), len(items), a.variant, a.model), flush=True)
    local, lock = threading.local(), threading.Lock()
    counter = iter(range(10**9))

    def url():
        if not hasattr(local, "u"):
            local.u = urls[next(counter) % len(urls)]
        return local.u

    def ask(it):
        b = body(it, a.variant, a.model)
        raw = json.dumps(b, ensure_ascii=False, sort_keys=True).encode()
        (qk,) = b["questions"]
        headers = {"content-type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        err, p, ms, cost = None, None, None, None
        for attempt in range(5):
            t0 = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(url(), data=raw, headers=headers), timeout=900) as r:
                    d = json.loads(r.read())
                p, err, ms = d["answers"][qk]["noul"], None, round((time.time() - t0) * 1000)
                cost = (d.get("usage") or {}).get("cost")
                break
            except urllib.error.HTTPError as e:
                err = "%d %s" % (e.code, e.read().decode("utf-8", "replace")[:300])
                if e.code in (400, 422):
                    break  # the model's refusal (reach, schema): final
                try:
                    wait = float(e.headers.get("retry-after") or 2 * (attempt + 1))
                except ValueError:
                    wait = 2 * (attempt + 1)
                time.sleep(min(wait, 60))
            except Exception as e:  # transport
                err = ("transport %s: %s" % (type(e).__name__, e))[:300]
                time.sleep(2 * (attempt + 1))
        return {"id": it["id"], "variant": a.variant, "model": a.model, "p": p, "error": err, "ms": ms, "cost": cost}

    n = 0
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "a") as f, cf.ThreadPoolExecutor(workers) as ex:
        for r in ex.map(ask, todo):
            n += 1
            if r["p"] is None and (r["error"] or "")[:3] not in ("400", "422"):
                print("  unanswered %s: %s" % (r["id"], r["error"]), flush=True)
                continue
            with lock:
                f.write(json.dumps(r) + "\n")
                f.flush()
            if n % 250 == 0:
                print("  %d/%d" % (n, len(todo)), flush=True)
    print("done %d" % n, flush=True)


if __name__ == "__main__":
    main()
