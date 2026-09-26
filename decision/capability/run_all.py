"""Every capability result and the 62-suite comparison for one Kai checkpoint, in one command.

    ./py run_all.py --kai hanzoai/kai@<revision> --bench BENCH   # or a checkpoint directory
    ./py run_all.py --kai DIR --bench BENCH --who kai,laya,jev    # rerun the baselines too (Jev is billed)

BENCH is hanzoai/decision's `bench` built with Metal on this machine (from a decision worktree:
`rx cargo build --release -p bench --features metal`, which leaves it in ra's
~/scratch/decision/target-<mirror>/release/bench).

A Hugging Face id is resolved to its local snapshot first. Each suite merges its keys into
results/<suite>.json, so the baselines' kept runs stay beside Kai's; results/cap.json is every
key (cap/<suite>/<who>/<metric>) with the checkpoint, the runtime, the Jev ledger and every
pending reason. The paper's scripts/results.py reads cap.json's "keys".
"""
import argparse
import os
import time
import traceback

import cap

SUITES = ["orig", "cardinality", "questions", "joint", "sensors", "invariance", "refresh", "deploy", "calibration"]


def resolve(model):
    if not model or os.path.isdir(model):
        return model
    from huggingface_hub import snapshot_download
    repo, _, rev = model.partition("@")
    return snapshot_download(repo, revision=rev or None)


def collect(started, kai, pending):
    keys, meta = {}, {}
    for s in SUITES:
        f = os.path.join(cap.RESULTS, s + ".json")
        if os.path.exists(f):
            d = cap.load(f)
            keys.update(d["keys"])
            for run in d["meta"].values():
                if isinstance(run, dict) and run.get("pending"):
                    pending.setdefault(s, {}).update(run["pending"])
    meta.update(started=started, finished=time.strftime("%Y-%m-%d %H:%M:%S %z"), checkpoint=kai,
                jev=cap.load(cap.LEDGER) if os.path.exists(cap.LEDGER) else None, pending=pending)
    out = {"meta": meta, "keys": dict(sorted(keys.items()))}
    cap.dump(out, os.path.join(cap.RESULTS, "cap.json"))
    print("wrote results/cap.json: %d keys; pending: %s" % (len(keys), sorted(pending)), flush=True)
    return out


def main(kai, who, only):
    started = time.strftime("%Y-%m-%d %H:%M:%S %z")
    local = resolve(kai)
    pending = {}
    for s in only:
        print("== %s" % s, flush=True)
        try:
            m = __import__(s)
            if s == "orig":
                m.main(local)
            elif s == "calibration":
                m.main()
            else:
                m.main(who, local)
        except Exception as e:  # a suite that fails is recorded, and the rest still run
            traceback.print_exc()
            pending.setdefault(s, {})["error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    return collect(started, kai, pending)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--kai", help="a Kai checkpoint: a directory or owner/name[@revision]")
    a.add_argument("--bench", help="hanzoai/decision's bench binary (else $KAI_BENCH)")
    a.add_argument("--who", default="kai", help="backends to run; the others' kept results stay")
    a.add_argument("--suites", default=",".join(SUITES))
    x = a.parse_args()
    if x.bench:
        os.environ["KAI_BENCH"] = os.path.abspath(os.path.expanduser(x.bench))
    main(x.kai, x.who.split(","), x.suites.split(","))
