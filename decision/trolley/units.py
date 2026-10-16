"""units.py CELLS OUT: the states `bench units` turns into train/fixtures/trolley-units.txt.gz.

    python3 -I bench/trolley/units.py CELLS states.json.gz
    bench units --states states.json.gz --out train/fixtures/trolley-units.txt.gz

CELLS is scenarios/v2/cells-v2.json at the pin (prereg.json). Every cell gives five states: its scene (prose or an
object, both orders being cells of their own), the request trolley-bench sends it ({state, questions} with all three
forms), and that request with each form alone (headline, criteria, inverse). `bench units` keeps each one's content units
(train::data::units: its leaves whitespace-squashed and joined, and the opening of each leaf of 200 characters or more),
so a record holding a scene, or any logged request of any form, under any key or spacing, is caught exactly; the stage
barrier's `trolley` set adds the near-duplicate and span checks over the scenes read at the pin.
"""
import gzip
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = json.load(open(os.path.join(HERE, "prereg.json")))


def main():
    path, out = sys.argv[1:3]
    raw = open(path, "rb").read()
    if hashlib.sha256(raw).hexdigest() != PREREG["source"]["cells_sha256"]:
        sys.exit(f"{path}: not the pinned cells")
    rows = []
    for c in json.loads(raw)["cells"]:
        q = c["questions"]
        rows.append([c["state"], {}, {"id": c["id"], "what": "scene"}])
        rows.append([{"state": c["state"], "questions": q}, {}, {"id": c["id"], "what": "request"}])
        for form in ("pull", "pull_criteria", "stay"):
            rows.append([{"state": c["state"], "questions": {form: q[form]}}, {}, {"id": c["id"], "what": form}])
    with gzip.open(out, "wt") as f:
        json.dump({"trolley": rows}, f)
    print(f"{len(rows)} states from {len(rows) // 5} cells -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
