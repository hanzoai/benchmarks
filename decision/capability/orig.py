"""The 62 frozen suites for a Kai checkpoint, beside Laya and Jev, as cap/orig keys.

The harness does the work: `bench preds` answers results/states.json.gz into
results/kai/preds.json.gz, and harness/merge.py scores Kai, Laya and Jev from the committed
results into results/scores.json and table.md. This reads scores.json. Laya is the router's
checkpoint per case, except typed_decisions on laya:typed-decisions, the checkpoint Laya ships
for it (merge.OWN).

    python orig.py [--kai CHECKPOINT]
"""
import argparse
import os

import cap

FROZEN = os.path.join(cap.HERE, "..", "results")
STATES = os.path.join(FROZEN, "states.json.gz")
FIELDS = ("accuracy", "macro_f1", "ece", "brier", "nll", "aurc", "unanswered", "zero_prob")


def short(s):
    return s.replace("jev.", "").replace("app.", "").replace("massive.", "m").replace("_", "")


def main(kai=None):
    meta, pending = {}, {}
    if kai:
        k = cap.Kai(kai)
        try:
            k.run("preds", "--model", kai, "--states", STATES, "--out", os.path.join(FROZEN, "kai", "preds.json.gz"))
        except cap.Pending as e:
            pending["kai"] = str(e)
        meta["kai"] = k.meta
    cap.merge.main()
    sc = cap.load(os.path.join(FROZEN, "scores.json"))
    keys = cap.Keys("orig")
    wins = {}
    for name, row in sc["suites"].items():
        best = {"kai": row.get("kai"), "laya": row.get(cap.merge.OWN.get(name, "laya")), "jev": row.get("jev")}
        for who, m in best.items():
            if m and m.get("n") and not name.startswith("massive."):
                keys.metrics(who, short(name) + ".", m, FIELDS)
        acc = {w: m["accuracy"] for w, m in best.items() if m and m.get("n")}
        for a in acc:
            wins.setdefault(a, {})
            for b in acc:
                wins[a][b] = wins[a].get(b, 0) + (acc[a] > acc[b])
    for a, row in wins.items():
        for b, n in row.items():
            if a != b:
                keys.put(a, "beats." + b, n)
    for who, m in sc["massive_summary"].items():
        if who in ("kai", "laya", "jev"):
            for f in ("macro_accuracy", "macro_ece", "non_english_macro", "above_3x_random", "languages"):
                keys.put(who, "massive." + f.replace("_", ""), m.get(f))
    return cap.save("orig", keys, {"sources": sc["sources"]}, {"pending": pending, **meta})


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--kai")
    main(a.parse_args().kai)
