"""Joint coherence: five dependent typed questions on one state, with known structure.

programs.py generates 200 states of each family (maintenance: fault -> severity -> readiness ->
action -> review; trade: option -> evidence, risk -> readiness -> review), seed 13. The
baselines answer every question independently of the others: Jev one call per state with all
five questions, Laya each question its own sequence. Per backend, as answered (argmax) and
projected (proj.: the assignment of greatest joint probability under the backend's own
marginals that breaks no rule, programs.project, the same for every backend):

    acc      per-variable accuracy, mean over the five (acc.<variable> each; <family>.acc per family)
    exact    share of states with all five right
    violate  share of states whose answers break at least one of the family's rules
    unanswered  questions without an answer (the state then counts as not exact)

Laya runs its typed-decisions checkpoint (the one it ships for these workflows) and, as en., the
English one its router would pick. Kai runs bench refine (hanzoai/decision) at tau 0.9 over 1, 2
and 3 passes, each pass re-asking the unfrozen answers with their parents' answers as facts, then
Kai's own selection and projection onto the rules: pass<k>.acc (argmax), pass<k>.proj.acc and
pass<k>.proj.exact (Kai's selection and projection, not programs.project), pass<k>.violate (states
whose argmax answers break a rule), and the third pass also under acc, proj.acc, proj.exact and
violate. A checkpoint with a joint decoder reports it as is and one question at a time as alone.

    python joint.py [--who laya,jev,kai] [--kai CHECKPOINT]
"""
import argparse
import json
import os

import numpy as np

import cap
import programs

CASES = os.path.join(cap.CASES, "joint.json.gz")
GRAPHS = os.path.join(cap.CASES, "joint.graphs.json")


def measure(rows, p):
    """Answered and projected metrics from {"ci/qid": vector}."""
    out = {}
    for mode in ("", "proj."):
        right, exact, bad, full, un = {}, 0, 0, 0, 0
        for ci, (_, qs, g) in enumerate(rows):
            fam = g["_wf"]
            v = {q: p.get("%d/%s" % (ci, q)) for q in qs}
            un += sum(x is None for x in v.values())
            if any(x is None for x in v.values()):
                for q in qs:
                    right.setdefault(q, []).append(v[q] is not None and int(np.argmax(v[q])) == g[q]["idx"])
                continue
            full += 1
            pick = programs.project(fam, v) if mode else {q: int(np.argmax(v[q])) for q in qs}
            a = {q: programs.order(qs[q])[pick[q]] for q in qs}
            ok = [pick[q] == g[q]["idx"] for q in qs]
            for q, o in zip(qs, ok):
                right.setdefault(q, []).append(o)
            exact += all(ok)
            bad += bool(programs.broken(fam, a))
        n = len(rows)
        out[mode + "acc"] = float(np.mean([x for v in right.values() for x in v]))
        out.update({mode + "acc." + q: float(np.mean(v)) for q, v in right.items()})
        out[mode + "exact"] = exact / n
        out[mode + "violate"] = bad / full if full else None
        out["unanswered"] = un
    return out


def kai(K, passes="1,2,3", tau="0.9"):
    """bench refine's report: per pass, by program, the argmax and joint (Kai's own selection
    and projection) accuracy, the share of states wholly right after it (exact) and of states
    whose argmax answers break a rule (broken)."""
    r = K.run("refine", "--states", CASES, "--suite", "joint", "--graphs", GRAPHS, "--model", K.model,
              "--passes", passes, "--tau", tau)
    return json.loads(r.stdout)[tau]


def kai_keys(keys, rep):
    """Keys from a refine report; the deepest pass also under the baselines' names."""
    for mode, runs in rep.items():
        pre = "" if mode in ("facts", "joint") else mode + "."
        for r in runs:
            for fam, m in r["by"].items():
                at = "pass%d.%s%s" % (r["passes"], pre, "" if fam == "all" else fam + ".")
                keys.put("kai", at + "acc", m["argmax"])
                keys.put("kai", at + "proj.acc", m["joint"])
                keys.put("kai", at + "proj.exact", m["exact"])
                keys.put("kai", at + "violate", m["broken"])
                keys.put("kai", at + "frozen", m["frozen"])
            keys.put("kai", "pass%d.%sasked" % (r["passes"], pre), r["asked"])
            keys.put("kai", "pass%d.%sseconds" % (r["passes"], pre), r["seconds"])
        last = max(runs, key=lambda r: r["passes"])
        for fam, m in last["by"].items():
            at = pre + ("" if fam == "all" else fam + ".")
            keys.put("kai", at + "acc", m["argmax"])
            keys.put("kai", at + "proj.acc", m["joint"])
            keys.put("kai", at + "proj.exact", m["exact"])
            keys.put("kai", at + "violate", m["broken"])


def main(who, kai_model):
    rows = programs.cases(int(os.environ.get("CAP_N") or 200))
    cap.dump({"joint": rows}, CASES)
    cap.dump(programs.GRAPHS, GRAPHS)
    B = cap.backends(who, kai_model)
    keys, detail, pending = cap.Keys("joint"), {}, {}
    for w, b in B.items():
        runs = {}
        if w == "laya":
            runs[""] = b.preds(rows, model="typed-decisions", tag="laya joint")
            runs["en."] = b.preds(rows, model="english", tag="laya en joint")
        elif w == "jev":
            runs[""] = b.preds(rows, "joint")
        else:
            try:
                rep = kai(b)
            except cap.Pending as e:
                pending[w] = str(e)
                continue
            detail["kai"] = rep
            kai_keys(keys, rep)
            continue
        for v, r in runs.items():
            m = measure(rows, r["p"])
            for fam in programs.GRAPHS:
                sub = [x for x in rows if x[2]["_wf"] == fam]
                idx = [ci for ci, x in enumerate(rows) if x[2]["_wf"] == fam]
                pf = {"%d/%s" % (j, q): r["p"].get("%d/%s" % (ci, q)) for j, ci in enumerate(idx) for q in sub[0][1]}
                m.update({fam + "." + k: x for k, x in measure(sub, pf).items() if k in ("acc", "exact", "violate",
                                                                                   "proj.acc", "proj.exact")})
            detail[v + w] = {"metrics": m, **{x: r[x] for x in ("seconds", "dropped", "n_errors", "error_kinds",
                                                                 "cost_usd", "latency_ms") if x in r}}
            for k, x in m.items():
                keys.put(w, v + k, x)
            cap.dump(r["p"], os.path.join(cap.RESULTS, "joint", "%s%s.preds.json.gz" % (v, w)))
    meta = {w: b.meta for w, b in B.items()}
    meta.update(pending=pending, cases={"n": len(rows), "families": list(programs.GRAPHS), "seed": 13})
    return cap.save("joint", keys, detail, meta)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    x = a.parse_args()
    main(x.who.split(","), x.kai)
