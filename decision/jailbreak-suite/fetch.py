"""fetch.py DATA: every file build.py reads, at its pinned revision, checked against files.json.

Each line of files.json is a path under DATA, the URL of that file at the revision prereg.json
pins (a Hugging Face dataset commit or a GitHub commit), and its SHA-256. A file already present
with the right SHA-256 is kept; a download that does not match is refused and removed.
allenai/wildjailbreak is gated: accept its terms on Hugging Face and set HF_TOKEN (or log in with
`hf auth login`, whose token file is read). Standard library only.

    python jailbreak-suite/fetch.py data
"""
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def token():
    t = os.environ.get("HF_TOKEN")
    path = os.path.join(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "token")
    if not t and os.path.exists(path):
        t = open(path).read().strip()
    return t


def main():
    data = sys.argv[1]
    hf = token()
    bad = []
    for f in json.load(open(os.path.join(HERE, "files.json"))):
        dest = os.path.join(data, f["path"])
        if os.path.exists(dest) and sha(dest) == f["sha256"]:
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        headers = {"User-Agent": "hanzoai-benchmarks"}
        if hf and f["url"].startswith("https://huggingface.co/"):
            headers["Authorization"] = "Bearer " + hf
        try:
            with urllib.request.urlopen(urllib.request.Request(f["url"], headers=headers), timeout=300) as r, \
                    open(dest + ".part", "wb") as w:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    w.write(b)
        except Exception as e:  # network, 401/403 on a gated set
            bad.append("%s: %s" % (f["path"], e))
            continue
        if sha(dest + ".part") != f["sha256"]:
            os.remove(dest + ".part")
            bad.append("%s: SHA-256 differs from files.json" % f["path"])
            continue
        os.replace(dest + ".part", dest)
        print("fetched", f["path"], flush=True)
    if bad:
        sys.exit("not fetched:\n  " + "\n  ".join(bad))
    print("every file present and checked", flush=True)


if __name__ == "__main__":
    main()
