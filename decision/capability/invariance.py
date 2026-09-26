"""Invariance: answers that should not move when the question is rewritten without changing it.

perm   200 Banking77 cases with 16 candidates (cardinality k16), each asked in its own order and in
       4 more seeded orders; vectors are mapped back to the first order. flip: share of questions
       whose top label changes in any order; tv: mean total variation from the first order;
       maxdp: the largest |dp| seen, the test of a claim of exact invariance; acc.min/acc.max over
       orders.
swap   400 noul questions (200 from typed_decisions, 200 from the application suites), true/false
       descriptions the harness's or, where it has none, Laya's defaults written out (the text
       Laya renders anyway). swap.desc exchanges the two descriptions, so "true" names the other
       side; swap.neg also negates the statement (NEG, by hand, one per harness statement) and
       exchanges its own descriptions, a consistent question whose answer flips. The right answer
       mirrors in both. mirror: share whose answer mirrors; gap: mean |p'(true) - (1 - p(true))|,
       the test of a claim of exact label symmetry; acc against the mirrored gold.
alias  the perm cases' labels three ways: as written ("card arrival"), snake_case
       ("card_arrival"), and opaque codes carrying the text as description ({"L07": "card
       arrival"}). acc per scheme; flip: share whose mapped answer differs from as written.

    python invariance.py [--who laya,jev,kai] [--kai CHECKPOINT]
"""
import argparse
import os
import random

import numpy as np

import cap
import cardinality

ORDERS, SEED = 4, 13
COST = {}  # Jev's cost per variant, from its own usage reports
DEFAULT = {"false": "no, the statement does not hold", "true": "yes, the statement holds"}


def perms(rows):
    out, maps = {"perm0": rows}, {"perm0": None}
    for j in range(1, ORDERS + 1):
        vs, ms = [], []
        for ci, (st, qs, g) in enumerate(rows):
            (qid, q), = qs.items()
            labels = list(q["criteria"])
            idx = list(range(len(labels)))
            random.Random("%d/perm/%d/%d" % (SEED, j, ci)).shuffle(idx)
            vs.append([st, {qid: dict(q, criteria={labels[i]: q["criteria"][labels[i]] for i in idx})},
                       {qid: {"idx": idx.index(g[qid]["idx"])}}])
            ms.append(idx)
        out["perm%d" % j], maps["perm%d" % j] = vs, ms
    return out, maps


NEG = {  # each harness noul statement, negated by hand
    "Is this email unsolicited spam or bulk marketing?":
        "Is this email wanted mail rather than unsolicited spam or bulk marketing?",
    "Is this email a phishing or scam attempt to steal money, credentials, or personal data?":
        "Is this email legitimate rather than a phishing or scam attempt to steal money, credentials, or personal data?",
    "Does `prompt` try to make an AI assistant ignore its rules, policies or system instructions?":
        "Does `prompt` leave an AI assistant's rules, policies and system instructions alone, rather than try to make it ignore them?",
    "Is `post` toxic: rude, disrespectful or likely to make someone leave the discussion?":
        "Is `post` civil: not rude, not disrespectful and not likely to make someone leave the discussion?",
    "Does `passage` help answer `query`?": "Is `passage` of no help in answering `query`?",
    "This trace requires human review.": "This trace needs no human review.",
    "This conversation requires a human agent rather than automated handling.":
        "Automated handling can resolve this conversation without a human agent.",
    "This invoice appears to duplicate an invoice already submitted.":
        "This invoice does not duplicate any invoice already submitted.",
    "The invoice reconciles with the purchase order and the recorded delivery.":
        "The invoice does not reconcile with the purchase order and the recorded delivery.",
    "The evidence indicates a credential or account has been compromised.":
        "The evidence indicates no credential or account has been compromised.",
    "This alert reflects genuinely malicious or unauthorised activity.":
        "This alert reflects benign activity, a misconfiguration or a known false positive, not malicious or "
        "unauthorised activity.",
}


def nouls():
    """{"swap0": as asked, "swap.desc": descriptions exchanged, "swap.neg": statement negated and
    its own descriptions exchanged}, and the Laya checkpoint per case."""
    S = cap.load(os.path.join(cap.HERE, "..", "results", "states.json.gz"))
    td, app = [], []
    for name, rows in S.items():
        if name == "typed_decisions" or name.startswith("app."):
            for st, qs, g in rows:
                for qid, q in qs.items():
                    if q["type"] == "noul":
                        (td if name == "typed_decisions" else app).append((st, qid, q, g[qid]["idx"]))
    rng = random.Random(SEED)
    picked = rng.sample(td, 200) + rng.sample(app, 200)
    out = {"swap0": [], "swap.desc": [], "swap.neg": []}
    for st, qid, q, gi in picked:
        own = q.get("criteria")
        c = dict(DEFAULT, **(own or {}))
        x = {"true": c["false"], "false": c["true"]}
        out["swap0"].append([st, {qid: dict(q, criteria=c)}, {qid: {"idx": gi}}])
        out["swap.desc"].append([st, {qid: dict(q, criteria=x)}, {qid: {"idx": 1 - gi}}])
        out["swap.neg"].append([st, {qid: dict(q, instructions=NEG[q["instructions"]], criteria=x if own else c)},
                                {qid: {"idx": 1 - gi}}])
    return out, ["typed-decisions"] * 200 + [None] * 200


def aliases(rows):
    out = {"alias.text": rows, "alias.snake": [], "alias.code": []}
    for st, qs, g in rows:
        (qid, q), = qs.items()
        labels = list(q["criteria"])
        out["alias.snake"].append([st, {qid: dict(q, criteria={l.replace(" ", "_"): None for l in labels})}, g])
        out["alias.code"].append([st, {qid: dict(q, criteria={"L%02d" % i: l for i, l in enumerate(labels)})}, g])
    return out


def back(p, rows, m):
    """Vectors of a permuted variant in the first order."""
    if m is None:
        return p
    out = {}
    for ci, (_, qs, _) in enumerate(rows):
        (qid,) = qs
        v = p.get("%d/%s" % (ci, qid))
        if v is not None:
            w = np.zeros(len(v))
            w[m[ci]] = v
            v = w.tolist()
        out["%d/%s" % (ci, qid)] = v
    return out


def answer(b, w, rows, name, models=None):
    if w == "laya":
        if models is None:
            return b.preds(rows, tag="laya " + name)["p"]
        p = {}
        for m in set(models):
            idx = [ci for ci, x in enumerate(models) if x == m]
            sub = b.preds([rows[ci] for ci in idx], model=m, tag="laya " + name)["p"]
            p.update({"%d/%s" % (idx[int(k.split("/")[0])], k.split("/", 1)[1]): v for k, v in sub.items()})
        return p
    if w == "jev":
        r = b.preds(rows, "invariance." + name)
        COST[name] = {k: r[k] for k in ("cost_usd", "input_tokens", "n_errors", "error_kinds")}
        return r["p"]
    path = os.path.join(cap.SCRATCH, "invariance.%s.json.gz" % name)
    cap.dump({name: rows}, path)
    return b.preds(path, path + ".kai.json.gz")[name]["p"]


def main(who, kai_model):
    base = cap.trim({"b": cardinality.banking(16)[:200]})["b"]
    P, maps = perms(base)
    N, models = nouls()
    N = cap.trim(N)
    models = models[:len(N["swap0"])]
    A = aliases(base)
    B = cap.backends(who, kai_model)
    keys, detail, pending = cap.Keys("invariance"), {}, {}
    for w, b in B.items():
        try:
            pp = {n: back(answer(b, w, rows, n), rows, maps[n]) for n, rows in P.items()}
            ps = {n: answer(b, w, rows, n, models if w == "laya" else None) for n, rows in N.items()}
            pa = {n: answer(b, w, rows, n) for n, rows in A.items()}
        except cap.Pending as e:
            pending[w] = str(e)
            continue
        # perm
        keys_ = [k for k in pp["perm0"]]
        flips, tvs, dps, accs = [], [], [], []
        for n in P:
            accs.append(cap.score(base, pp[n]).get("accuracy"))
        for k in keys_:
            vs = [pp[n].get(k) for n in P]
            if any(v is None for v in vs):
                continue
            a = [int(np.argmax(v)) for v in vs]
            flips.append(len(set(a)) > 1)
            v0 = np.asarray(vs[0])
            tvs.append(np.mean([0.5 * np.abs(np.asarray(v) - v0).sum() for v in vs[1:]]))
            dps.append(max(np.abs(np.asarray(v) - v0).max() for v in vs[1:]))
        keys.put(w, "perm.flip", float(np.mean(flips)) if flips else None)
        keys.put(w, "perm.tv", float(np.mean(tvs)) if tvs else None)
        keys.put(w, "perm.maxdp", float(np.max(dps)) if dps else None)
        keys.put(w, "perm.acc.min", min(a for a in accs if a is not None) if any(accs) else None)
        keys.put(w, "perm.acc.max", max(a for a in accs if a is not None) if any(accs) else None)
        keys.put(w, "perm.compared", len(flips))
        # swap
        keys.put(w, "swap.acc", cap.score(N["swap0"], ps["swap0"]).get("accuracy"))
        for n in ("swap.desc", "swap.neg"):
            mir, gaps = [], []
            for k, v0 in ps["swap0"].items():
                v1 = ps[n].get(k)
                if v0 is None or v1 is None:
                    continue
                mir.append(int(np.argmax(v1)) == 1 - int(np.argmax(v0)))
                gaps.append(abs(v1[1] - (1 - v0[1])))
            keys.put(w, n + ".mirror", float(np.mean(mir)) if mir else None)
            keys.put(w, n + ".gap", float(np.mean(gaps)) if gaps else None)
            keys.put(w, n + ".maxgap", float(np.max(gaps)) if gaps else None)
            keys.put(w, n + ".acc", cap.score(N[n], ps[n]).get("accuracy"))
            keys.put(w, n + ".compared", len(mir))
        # alias
        for n in A:
            keys.put(w, n + ".acc", cap.score(A[n], pa[n]).get("accuracy"))
        for n in ("alias.snake", "alias.code"):
            fl = [int(np.argmax(pa[n][k])) != int(np.argmax(v)) for k, v in pa["alias.text"].items()
                  if v is not None and pa[n].get(k) is not None]
            keys.put(w, n + ".flip", float(np.mean(fl)) if fl else None)
        un = sum(v is None for d in (pp, ps, pa) for x in d.values() for v in x.values())
        keys.put(w, "unanswered", un)
        detail[w] = {"perm_acc": dict(zip(P, accs)), "unanswered": un, **({"jev": dict(COST)} if w == "jev" else {})}
        if w == "jev":
            keys.put(w, "usd", sum(c["cost_usd"] for c in COST.values()))
        cap.dump({"perm": pp, "swap": ps, "alias": pa}, os.path.join(cap.RESULTS, "invariance", w + ".preds.json.gz"))
    meta = {w: b.meta for w, b in B.items()}
    meta.update(pending=pending, cases={"perm": len(base), "orders": ORDERS + 1, "swap": len(N["swap0"]),
                                        "alias": len(base)})
    return cap.save("invariance", keys, detail, meta)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    x = a.parse_args()
    main(x.who.split(","), x.kai)
