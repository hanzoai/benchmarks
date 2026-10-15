"""Each suite's digest of a preds file, as a research run's notes record it (`preds sha256:...`).

A run filed at api.hanzo.ai/v1/research names the predictions it was scored from by one SHA-256
per suite: the suite's slice of the preds file ({"suites": {name: ...}}, or {"route", "models"}
for a routed file; MASSIVE's 51 languages together) written as compact JSON in the file's own key
order, numbers in their shortest round-trip form. This prints those digests, so a reader can
check that a committed file is the one a published number came from.

    python harness/digest.py results/kai-1/preds.json.gz
    python harness/digest.py results/jev/preds.json.gz jev.ag_news massive
"""
import gzip
import hashlib
import json
import sys

MASSIVE = "massive"


def number(x):
    """A float as serde_json writes it: Python's shortest digits, laid out as ryu lays them out."""
    r = repr(x)
    sign = "-" if r.startswith("-") else ""
    m, _, e = r.lstrip("-").partition("e")
    a, _, b = m.partition(".")
    b = "" if b == "0" else b
    digits, k = (a + b).lstrip("0"), int(e or 0) - len(b)
    if not digits:
        return sign + "0.0"
    k += len(digits) - len(digits.rstrip("0"))
    digits = digits.rstrip("0")
    n = len(digits)
    kk = n + k
    if 0 <= k and kk <= 16:
        s = digits + "0" * k + ".0"
    elif 0 < kk <= 16:
        s = digits[:kk] + "." + digits[kk:]
    elif -5 < kk <= 0:
        s = "0." + "0" * -kk + digits
    elif n == 1:
        s = digits + "e" + str(kk - 1)
    else:
        s = digits[0] + "." + digits[1:] + "e" + str(kk - 1)
    return sign + s


def compact(v):
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + compact(x) for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(compact(x) for x in v) + "]"
    if isinstance(v, float):
        return number(v)
    return json.dumps(v, ensure_ascii=False)


def digest(preds, suite):
    def part(m):
        return {k: x for k, x in (m or {}).items() if k == suite or (suite == MASSIVE and k.startswith("massive."))}

    if isinstance(preds.get("models"), dict):
        body = {"route": part(preds.get("route")), "models": {c: part(s) for c, s in preds["models"].items()}}
    else:
        body = {"suites": part(preds.get("suites"))}
    return hashlib.sha256(compact(body).encode()).hexdigest()


def main():
    preds = json.load(gzip.open(sys.argv[1]))
    names = sys.argv[2:] or sorted({MASSIVE if n.startswith("massive.") else n for n in preds.get("suites") or preds["route"]})
    for name in names:
        print(name, digest(preds, name))


if __name__ == "__main__":
    main()
