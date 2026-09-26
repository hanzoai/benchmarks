"""Refresh: a program re-run after one evidence change.

Ten fleet programs (seed 13), each 20 vehicles from programs.readiness: per vehicle six
evidence items (five subsystem readings with their trouble codes, the operator note) and five
Kai nodes (fault, severity, readiness, action, review, each reading its parents and the
evidence it needs), plus one fleet node over every vehicle's readiness: 101 nodes, 121
evidence items and the policy. The change is one new reading on one vehicle.

    kai   bench refresh (hanzoai/decision): the program executor runs cold, then refreshes the
          change on its cache, then recomputes it cold; nodes run and wall time of each, and
          whether the refresh's outputs equal the recompute's node for node.
    laya, jev  no program model, so no refresh: after any change every question is asked
          again. Recorded as unsupported, with what that full re-ask costs them: each vehicle's
          five questions over its evidence (Laya each question its own sequence on its
          typed-decisions checkpoint; Jev one call per vehicle, 8 in flight).

    python refresh.py [--who laya,jev,kai] [--kai CHECKPOINT]
"""
import argparse
import json
import os
import random
import time

import numpy as np

import cap
import programs

FLEETS, VEHICLES, SEED = 10, 20, 13
ITEMS = os.path.join(cap.CASES, "refresh.json")


def fleet(f):
    rng = random.Random("%d/refresh/%d" % (SEED, f))
    ev, snaps, nodes, flat = [{"id": "policy", "uri": "doc:maintenance-policy"}], {"policy": programs.POLICY_R}, [], []
    q = programs.QUESTIONS["maintenance"]
    for v in range(VEHICLES):
        st, _ = programs.readiness(rng, f * VEHICLES + v)
        flat.append(st)
        p = "v%02d" % v
        subs = []
        for s in st["sensors"]:
            sub = next(k for k, x in programs.SUBSYSTEMS.items() if x[0] == s["sensor"])
            i = "%s_%s" % (p, sub)
            ev.append({"id": i, "uri": "sensor:%s/%s" % (p, sub)})
            snaps[i] = dict(s, trouble_codes=[c for c in st["trouble_codes"] if c in programs.SUBSYSTEMS[sub][6]])
            subs.append(i)
        ev.append({"id": p + "_note", "uri": "report:%s/operator" % p})
        snaps[p + "_note"] = st["operator_note"]

        def kai(n, inputs):
            nodes.append({"id": "%s_%s" % (p, n), "kind": "kai", "model": "kai", "inputs": inputs, "question": q[n]})

        kai("fault", subs + [p + "_note", "policy"])
        kai("severity", [p + "_fault"] + subs + ["policy"])
        kai("readiness", [p + "_fault", p + "_severity", "policy"])
        kai("action", [p + "_severity", p + "_readiness", "policy"])
        kai("review", [p + "_fault", p + "_action", p + "_note", "policy"])
    nodes.append({"id": "fleet", "kind": "kai", "model": "kai", "inputs": ["v%02d_readiness" % v for v in range(VEHICLES)],
                  "question": {"type": "score", "instructions": "How much of the fleet is mission capable?",
                               "criteria": ["under a quarter", "a quarter to a half", "a half to three quarters",
                                            "three quarters or more"]}})
    # the change: a new reading on one vehicle's one subsystem
    v, sub = rng.randrange(VEHICLES), rng.choice(list(programs.SUBSYSTEMS))
    i = "v%02d_%s" % (v, sub)
    new = dict(snaps[i], reading=round(snaps[i]["reading"] * rng.choice([0.85, 1.15]), 1))
    prog = {"id": "fleet.readiness.%d" % f, "version": 1, "description": "Readiness of a %d-vehicle fleet." % VEHICLES,
            "evidence": ev, "nodes": nodes}
    return {"program": prog, "snapshots": snaps, "change": {"evidence": i, "content": new}}, flat


def reask(b, w, flat):
    """One full re-ask of a fleet: seconds, and Jev's cost."""
    rows = [[st, programs.QUESTIONS["maintenance"], {}] for st in flat]
    t = time.perf_counter()
    if w == "laya":
        b.preds(rows, model="typed-decisions")
        return time.perf_counter() - t, 0.0
    r = b.preds(rows, "refresh.reask")
    return time.perf_counter() - t, r["cost_usd"]


def main(who, kai_model):
    items, flats = zip(*[fleet(f) for f in range(FLEETS)])
    cap.dump(list(items), ITEMS)
    B = cap.backends(who, kai_model)
    keys, detail, pending = cap.Keys("refresh"), {}, {}
    nodes = len(items[0]["program"]["nodes"])
    for w, b in B.items():
        if w == "kai":
            try:
                r = json.loads(b.run("refresh", "--model", b.model, "--programs", ITEMS).stdout)
            except cap.Pending as e:
                pending[w] = str(e)
                continue
            detail[w] = r
            keys.put(w, "nodes", float(np.mean([x["nodes"] for x in r])))
            keys.put(w, "ran", float(np.mean([x["ran"] for x in r])))
            for f in ("cold_ms", "refresh_ms", "recompute_ms"):
                keys.put(w, f.replace("_", ""), float(np.median([x[f] for x in r])))
            keys.put(w, "speedup", float(np.median([x["recompute_ms"] / x["refresh_ms"] for x in r])))
            keys.put(w, "same", sum(x["same"] for x in r))
            keys.put(w, "support", "yes")
            continue
        secs, usd = zip(*[reask(b, w, flat) for flat in flats])
        detail[w] = {"reask_s": secs, "reask_usd": usd}
        keys.put(w, "support", "none")
        keys.put(w, "reask.questions", VEHICLES * 5)
        keys.put(w, "reask.ms", 1e3 * float(np.median(secs)))
        if w == "jev":
            keys.put(w, "reask.usd", float(np.mean(usd)))
    meta = {w: b.meta for w, b in B.items()}
    meta.update(pending=pending, fleets=FLEETS, vehicles=VEHICLES, nodes=nodes)
    return cap.save("refresh", keys, detail, meta)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    x = a.parse_args()
    main(x.who.split(","), x.kai)
