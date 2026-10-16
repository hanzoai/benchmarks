"""read.py: every trolley-bench v2 cell to a `kai serve`, one POST /v1/decisions a cell, resumable, sharded.

    python3 -I bench/trolley/read.py CELLS URL OUT SHARD RELEASE      (SHARD: k/n, e.g. 0/3)

CELLS is scenarios/v2/cells-v2.json at the pin, held to prereg.json's SHA-256. The body is the one trolley-bench's Jev
runner sends, {state, questions} as the cell holds them, with model `kai`: the state (prose or an object) as written
and the three noul questions (pull, pull_criteria, stay) in one request. With SHARD k/n only the cells whose index in the
file is k mod n are sent, so n servers read the set; a cell already in OUT is not sent again. One line a cell: the
cell's coordinates, `answers` (P(yes) a form, as the repository's raw rows hold them), the decision's routing, usage,
the server's latency, the wall time and the load before the request; OUT.models.json keeps the server's GET /v1/models. A 429 or 529 waits its Retry-After and asks
again; any other refusal is written as an error row, which score.py refuses to score.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = json.load(open(os.path.join(HERE, "prereg.json")))
FORMS = ("pull", "pull_criteria", "stay")


def post(url, body):
    while True:
        req = urllib.request.Request(url + "/v1/decisions", body, {"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3600) as resp:
                return 200, json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 529):
                time.sleep(float(e.headers.get("retry-after") or 5))
                continue
            return e.code, json.loads(e.read() or b"{}")


def main():
    path, url, out, shard, release = sys.argv[1:6]
    k, n = (int(x) for x in shard.split("/"))
    raw = open(path, "rb").read()
    if hashlib.sha256(raw).hexdigest() != PREREG["source"]["cells_sha256"]:
        sys.exit(f"{path}: not the pinned cells")
    cells = json.loads(raw)["cells"]
    done = set()
    if os.path.exists(out):
        done = {json.loads(l)["id"] for l in open(out) if l.strip()}
    with urllib.request.urlopen(url + "/v1/models", timeout=60) as resp:
        served = json.load(resp)
    with open(out + ".models.json", "w") as f:
        json.dump(served, f, indent=1)
    with open(out, "a") as f:
        for i, c in enumerate(cells):
            if i % n != k or c["id"] in done:
                continue
            body = json.dumps({"model": "kai", "state": c["state"], "questions": c["questions"]}).encode()
            load = float(open("/proc/loadavg").read().split()[0])
            t = time.monotonic()
            code, ans = post(url, body)
            wall = time.monotonic() - t
            where = {x: c[x] for x in ("id", "scenario", "wording", "order", "n", "k")}
            row = {"prompt_version": PREREG["source"]["prompt_version"], "model_id": release, "pass": "a", **where}
            if code != 200:
                row["error"] = {"status": code, "body": ans}
            else:
                got = ans["answers"]
                if any(got[q].get("type") != "noul" for q in FORMS):
                    sys.exit(f"{c['id']}: an answer is not a noul: {got}")
                r = ans.get("routing", {})
                row.update({"answers": {q: got[q]["noul"] for q in FORMS},
                            "routing": {x: r.get(x) for x in ("checkpoint", "sha256", "representation", "calibration", "primitive", "capability", "device", "extrapolated")},
                            "input_tokens": ans.get("usage", {}).get("input_tokens"), "latency_ms": ans.get("latency_ms")})
            row.update({"wall_s": round(wall, 4), "load": load, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            f.write(json.dumps(row) + "\n")
            f.flush()


if __name__ == "__main__":
    main()
