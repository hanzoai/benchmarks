"""The 62 frozen suites for a Kai checkpoint, beside Laya and Jev, as cap/orig keys.

As results/kai-a was made: the harness and its committed results are copied to a scratch tree,
`bench preds` answers results/states.json.gz into its results/kai/preds.json.gz, and the frozen
harness/merge.py scores Kai, Laya and Jev there. The checkpoint's predictions and scores are kept
as results/orig/kai.{preds,scores}.json.gz. Laya is the router's checkpoint per case, except
typed_decisions on laya:typed-decisions, the checkpoint Laya ships for it (merge.OWN).

    python orig.py [--kai CHECKPOINT]
"""
import argparse
import importlib.util
import os
import shutil

import cap

FROZEN = os.path.join(cap.HERE, "..")
FIELDS = ("accuracy", "macro_f1", "ece", "brier", "nll", "aurc", "unanswered", "zero_prob")


def short(s):
    return s.replace("jev.", "").replace("app.", "").replace("massive.", "m").replace("_", "")


def tree():
    """A scratch copy of harness/ and the results merge.py reads."""
    t = os.path.join(cap.SCRATCH, "orig")
    shutil.rmtree(t, ignore_errors=True)
    shutil.copytree(os.path.join(FROZEN, "harness"), os.path.join(t, "harness"))
    for p in ("questions.json.gz", "states.json.gz", "laya/preds.json.gz", "jev/preds.json.gz"):
        os.makedirs(os.path.dirname(os.path.join(t, "results", p)), exist_ok=True)
        shutil.copy(os.path.join(FROZEN, "results", p), os.path.join(t, "results", p))
    return t


def main(kai=None):
    t, meta, pending = tree(), {}, {}
    if kai:
        k = cap.Kai(kai)
        out = os.path.join(t, "results", "kai", "preds.json.gz")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            k.run("preds", "--model", kai, "--states", os.path.join(t, "results", "states.json.gz"), "--out", out)
            os.makedirs(os.path.join(cap.RESULTS, "orig"), exist_ok=True)
            shutil.copy(out, os.path.join(cap.RESULTS, "orig", "kai.preds.json.gz"))
        except cap.Pending as e:
            pending["kai"] = str(e)
        meta["kai"] = k.meta
    spec = importlib.util.spec_from_file_location("frozen", os.path.join(t, "harness", "merge.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.main()
    sc = cap.load(os.path.join(t, "results", "scores.json"))
    if "kai" in sc["sources"]:
        cap.dump({"sources": sc["sources"], "suites": {n: r.get("kai") for n, r in sc["suites"].items()},
                  "massive": sc["massive_summary"].get("kai")}, os.path.join(cap.RESULTS, "orig", "kai.scores.json.gz"))
    keys = cap.Keys("orig")
    wins = {}
    for name, row in sc["suites"].items():
        best = {"kai": row.get("kai"), "laya": row.get(m.OWN.get(name, "laya")), "jev": row.get("jev")}
        for who, x in best.items():
            if x and x.get("n") and not name.startswith("massive."):
                keys.metrics(who, short(name) + ".", x, FIELDS)
        acc = {w: x["accuracy"] for w, x in best.items() if x and x.get("n")}
        for a in acc:
            wins.setdefault(a, {})
            for b in acc:
                wins[a][b] = wins[a].get(b, 0) + (acc[a] > acc[b])
    for a, row in wins.items():
        for b, n in row.items():
            if a != b:
                keys.put(a, "beats." + b, n)
    for who, x in sc["massive_summary"].items():
        if who in ("kai", "laya", "jev"):
            for f in ("macro_accuracy", "macro_ece", "non_english_macro", "above_3x_random", "languages"):
                keys.put(who, "massive." + f.replace("_", ""), x.get(f))
    return cap.save("orig", keys, {"sources": sc["sources"]}, {"pending": pending, **meta})


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--kai")
    main(a.parse_args().kai)
