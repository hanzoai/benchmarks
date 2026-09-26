"""Choice over K candidates, K = 4 ... 100,000: accuracy, recall@k, time, rejection, truncation.

K = 4, 16, 77  the frozen jev.banking77_full cases (Banking77 test, 400, harness seed 13). At 4
               and 16 the candidates are the gold label and its K-1 nearest labels by word overlap
               (hard negatives; ties by seed), in seeded order; at 77 the case is the frozen one.
K = 150        CLINC150 test (clinc/clinc_oos plus @155b9c71, in scope), 400 by seed 13.
K = 1,000 ...  WordNet 3.0 (nltk corpus, sha256 cbda5ea6): a definition; which concept does it
100,000        define? One label list per K, nested across K, holding each target's co-hyponyms
               (semantic hard negatives), then seeded fill. A label is a synset's lemmas, with its
               hypernym (or adjective/adverb) in parentheses where the lemmas alone repeat; a label
               that still repeats is left out (111,726 of 117,659 remain). 200 targets at 1K and
               10K, the first 50 at 100K.

Variants, each scored against all K:
    (none)  the case as is.
    wide.   Laya with head_max_len 7680 and max_len 8192, its README's recipe for 50+ options.
    sl.     every backend answers the top 20 of laya.shortlist over the English checkpoint's own
            mean-pooled encoder (embed_fn_from_agent), its README's other recipe; the answer maps
            back to all K and a gold label outside the shortlist is a miss.
Jev takes at most 255 options (Laya's README); at K >= 10,000 it is sent 10 cases, and once all 10
are refused alike the rest are recorded as refused by the same rule, unsent.

    python cardinality.py [--who laya,jev,kai] [--kai CHECKPOINT] [--k 4,16,...]
"""
import argparse
import os
import random
import re
import time

import numpy as np

import cap

KS = [4, 16, 77, 150, 1000, 10000, 100000]
SL, SEED = 20, 13
INS = {"banking": "Which banking intent does `message` express?",
       "clinc": "Which intent does `message` express?",
       "wordnet": "Which concept does `definition` define?"}


def words(s):
    return set(re.findall(r"[a-z]+", s.lower()))


def banking(k):
    rows = cap.load(os.path.join(cap.HERE, "..", "results", "states.json.gz"))["jev.banking77_full"]
    if k == 77:
        return rows
    out = []
    for ci, (st, qs, g) in enumerate(rows):
        labels = list(qs["intent"]["criteria"])
        gl = labels[g["intent"]["idx"]]
        rng = random.Random("%d/%d/%d" % (SEED, k, ci))
        w = words(gl)
        rest = sorted((l for l in labels if l != gl),
                      key=lambda l: (-len(w & words(l)) / len(w | words(l)), rng.random()))
        opts = [gl] + rest[:k - 1]
        rng.shuffle(opts)
        q = dict(qs["intent"], criteria={l: None for l in opts})
        out.append([st, {"intent": q}, {"intent": {"idx": opts.index(gl)}}])
    return out


def clinc():
    from datasets import load_dataset
    ds = load_dataset("clinc/clinc_oos", "plus", split="test", revision="155b9c710419136e17307b80d0a13e68cd46b4ec")
    names = ds.features["intent"].names
    keep = [i for i, n in enumerate(names) if n != "oos"]
    labels = [names[i].replace("_", " ") for i in keep]
    rows = [r for r in ds if names[r["intent"]] != "oos"]
    random.Random(SEED).shuffle(rows)
    q = {"type": "choice", "instructions": INS["clinc"], "criteria": {l: None for l in labels}}
    return [[{"message": r["text"]}, {"intent": q}, {"intent": {"idx": keep.index(r["intent"])}}] for r in rows[:400]]


def wordnet():
    """(label list of 100,000, targets): the label list's first K entries are the space at K."""
    import nltk
    nltk.data.path.insert(0, os.path.join(cap.SCRATCH, "nltk"))
    from nltk.corpus import wordnet as wn
    assert wn.get_version() == "3.0"
    syn = list(wn.all_synsets())
    base = {s: ", ".join(l.replace("_", " ") for l in s.lemma_names()) for s in syn}
    once = tally(base.values())

    def tag(s):
        h = s.hypernyms() or s.instance_hypernyms() or s.similar_tos()
        return h[0].lemma_names()[0].replace("_", " ") if h else \
            {"adj": "adjective", "adv": "adverb"}.get(s.lexname().split(".")[0], s.lexname())

    label = {s: base[s] if once[base[s]] == 1 else "%s (%s)" % (base[s], tag(s)) for s in syn}
    count = tally(label.values())
    uni = [s for s in syn if count[label[s]] == 1]
    ok = set(uni)
    rng = random.Random(SEED)
    pool = [s for s in uni if s.pos() == "n" and once[base[s]] == 1 and len(s.definition().split()) >= 6 and s.hypernyms()
            and sum(h in ok and h != s for p in s.hypernyms() for h in p.hyponyms()) >= 3]
    targets = rng.sample(pool, 200)
    order, seen = [], set()

    def add(s):
        if s not in seen:
            seen.add(s)
            order.append(s)

    for s in targets:
        add(s)
    for s in targets:
        sib = sorted({h for p in s.hypernyms() for h in p.hyponyms() if h in ok and h != s}, key=lambda x: x.name())
        for h in rng.sample(sib, min(3, len(sib))):
            add(h)
    rest = [s for s in uni if s not in seen]
    rng.shuffle(rest)
    for s in rest:
        if len(order) == 100000:
            break
        add(s)
    return [label[s] for s in order], [(label[s], s.definition()) for s in targets]


def tally(xs):
    out = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def words_rows(k, space, targets):
    labels = space[:k]
    random.Random("%d/%d" % (SEED, k)).shuffle(labels)
    pos = {l: i for i, l in enumerate(labels)}
    q = {"type": "choice", "instructions": INS["wordnet"], "criteria": {l: None for l in labels}}
    return [[{"definition": d}, {"concept": q}, {"concept": {"idx": pos[l]}}] for l, d in targets[:200 if k < 100000 else 50]]


def cases(ks):
    out, space = {}, None
    for k in ks:
        if k <= 77:
            out["k%d" % k] = banking(k)
        elif k == 150:
            out["k150"] = clinc()
        else:
            space = space or wordnet()
            out["k%d" % k] = words_rows(k, *space)
    return out


# ------------------------------------------------------------------ shortlist
def shortlists(L, S):
    """Per suite, per case: the top-SL labels by laya.shortlist over the English encoder, the
    seconds to embed the label list once (cached by text) and each case's own seconds."""
    from laya.shortlist import embed_fn_from_agent, shortlist_choice
    memo, raw = {}, []

    def embed(texts):
        raw or raw.append(embed_fn_from_agent(L.agent("english"), batch_size=128))
        miss = [t for t in dict.fromkeys(texts) if t not in memo]
        for i in range(0, len(miss), 4096):
            memo.update(zip(miss[i:i + 4096], raw[0](miss[i:i + 4096])))
        return np.stack([memo[t] for t in texts])

    path = os.path.join(cap.CASES, "cardinality.shortlists.json.gz")
    kept = cap.load(path) if os.path.exists(path) else {}
    out = {}
    for name, rows in S.items():
        if len(next(iter(rows[0][1].values()))["criteria"]) <= SL:
            continue
        if name in kept and len(kept[name]["picks"]) == len(rows):
            out[name] = kept[name]
            continue
        crit = next(iter(rows[0][1].values()))["criteria"]
        t = time.perf_counter()
        embed([str(k) for k in crit])  # the label list, once
        index_s = time.perf_counter() - t
        picks, secs = [], []
        for st, qs, _ in rows:
            (q,) = qs.values()
            t = time.perf_counter()
            picks.append(shortlist_choice(st, q["criteria"], embed, k=SL, instructions=q["instructions"]))
            secs.append(time.perf_counter() - t)
        out[name] = {"picks": picks, "index_s": round(index_s, 3), "case_ms": [round(1e3 * s, 2) for s in secs]}
        if not os.environ.get("CAP_N"):
            cap.dump(dict(kept, **out), path)
    return out


def reduce(rows, picks):
    """The shortlisted cases (gold -1 when outside) and each case's map back to all K."""
    out, maps = [], []
    for (st, qs, g), pick in zip(rows, picks):
        (qid, q), = qs.items()
        full = list(q["criteria"])
        idx = [full.index(l) for l in pick]
        gi = g[qid]["idx"]
        out.append([st, {qid: dict(q, criteria={l: q["criteria"][l] for l in pick})},
                    {qid: {"idx": idx.index(gi) if gi in idx else 0, "in": gi in idx}}])
        maps.append(idx)
    return out, maps


def expand(p, maps, rows):
    """Shortlist answers as vectors over all K, zero outside the shortlist."""
    out = {}
    for ci, (_, qs, _) in enumerate(rows):
        (qid, q), = qs.items()
        v = p.get("%d/%s" % (ci, qid))
        if v is None:
            out["%d/%s" % (ci, qid)] = None
            continue
        full = np.zeros(len(q["criteria"]))
        full[maps[ci]] = v
        out["%d/%s" % (ci, qid)] = full.tolist()
    return out


# ------------------------------------------------------------------ run
def jev_run(J, rows, suite):
    """All cases, except at K >= 10,000: 10 first, and the rest only if any of those is answered."""
    k = len(next(iter(rows[0][1].values()))["criteria"])
    if k < 10000:
        return J.preds(rows, suite)
    head = J.preds(rows[:10], suite)
    if head["n_errors"] < 10 or len(head["error_kinds"]) != 1:
        return J.preds(rows, suite)
    why = next(iter(head["error_kinds"]))
    for ci in range(10, len(rows)):
        head["p"].update({"%d/%s" % (ci, qid): None for qid in rows[ci][1]})
    head.update(n_errors=len(rows), unsent=len(rows) - 10,
                error_kinds={why: len(rows)}, note="10 sent, all refused (%s); the rest unsent" % why)
    return head


def main(who, kai, ks):
    S = cap.trim(cases(ks))
    for name, rows in S.items():
        if name != "k77" and int(name[1:]) <= 1000:
            cap.dump(S[name], os.path.join(cap.CASES, "cardinality.%s.json.gz" % name))
    B = cap.backends(who, kai)
    keys, detail, pending = cap.Keys("cardinality"), {}, {}
    L = B.get("laya") or cap.Laya()
    sl = shortlists(L, S) if L else {}  # kept in cases/, so a Kai-only run reuses the baselines' shortlists
    R = {n: reduce(S[n], sl[n]["picks"]) for n in sl}
    for n in sl if "laya" in B else ():
        keys.put("laya", n + ".sl.hit", float(np.mean([g[next(iter(g))]["in"] for _, _, g in R[n][0]])))
        keys.put("laya", n + ".sl.indexs", sl[n]["index_s"])
        keys.put("laya", n + ".sl.casems", float(np.median(sl[n]["case_ms"])))
    runs = {}
    for w, b in B.items():
        for n, rows in S.items():
            nq = len(rows)
            if w == "laya":
                runs[(w, n, "")] = r = b.preds(rows, tag="laya " + n)
                d = r["fit"] = b.fit(rows)
                keys.put(w, n + ".rejected", d["rejected"] / nq)
                keys.put(w, n + ".optionscut", d["options_cut"] / nq)
                keys.put(w, n + ".statecut", d["state_cut"] / nq)
                if int(n[1:]) >= 77 and int(n[1:]) <= 1000:
                    ag = b.agent("english")
                    was = dict(ag.cfg)
                    ag.cfg.update(max_len=8192, head_max_len=7680)
                    runs[(w, n, "wide.")] = r = b.preds(rows, model="english", tag="laya wide " + n)
                    d = r["fit"] = b.fit(rows, model="english")
                    ag.cfg.clear()
                    ag.cfg.update(was)
                    keys.put(w, n + ".wide.rejected", d["rejected"] / nq)
                    keys.put(w, n + ".wide.optionscut", d["options_cut"] / nq)
            elif w == "jev":
                runs[(w, n, "")] = r = jev_run(b, rows, "cardinality." + n)
                keys.put(w, n + ".rejected", r["n_errors"] / nq)
                keys.put(w, n + ".p50ms", cap.pct(r["latency_ms"], 50))
                keys.put(w, n + ".p95ms", cap.pct(r["latency_ms"], 95))
                keys.put(w, n + ".usd", r["cost_usd"])
            else:
                path = os.path.join(cap.SCRATCH, "cardinality.%s.json.gz" % n)
                cap.dump({n: rows}, path)
                try:
                    runs[(w, n, "")] = b.preds(path, path + ".kai.json.gz")[n]
                except cap.Pending as e:
                    pending[w] = str(e)
                    break
            if n in R:
                sub, maps = R[n]
                if w == "laya":
                    r = b.preds(sub, tag="laya sl " + n)
                elif w == "jev":
                    r = b.preds(sub, "cardinality.sl." + n)
                else:
                    path = os.path.join(cap.SCRATCH, "cardinality.sl.%s.json.gz" % n)
                    cap.dump({n: sub}, path)
                    try:
                        r = b.preds(path, path + ".kai.json.gz")[n]
                    except cap.Pending:
                        continue
                r["p"] = expand(r["p"], maps, rows)
                runs[(w, n, "sl.")] = r
    for (w, n, v), r in runs.items():
        rows = S[n]
        m = cap.score(rows, r["p"])
        m.update(cap.ranks(rows, r["p"]))
        right = sum(1 for ci, (_, qs, g) in enumerate(rows) for qid in qs
                    if r["p"].get("%d/%s" % (ci, qid)) is not None
                    and int(np.argmax(r["p"]["%d/%s" % (ci, qid)])) == g[qid]["idx"])
        m["accall"] = round(right / len(rows), 4)
        keys.metrics(w, n + "." + v, m, ("accuracy", "accall", "ece", "brier", "unanswered", "recall1", "recall5", "recall20"))
        secs = r.get("seconds")
        if secs and m.get("n"):
            keys.put(w, n + "." + v + "msperq", 1e3 * secs / m["n"])
        detail.setdefault(n, {})[w + ("." + v.rstrip(".") if v else "")] = {
            "metrics": m, **{x: r[x] for x in ("fit", "dropped", "n_errors", "error_kinds", "errors", "served",
                                                "cost_usd", "input_tokens", "unsent", "note", "latency_ms") if x in r}}
    meta = {w: b.meta for w, b in B.items()}
    meta["pending"] = pending
    meta["cases"] = {n: {"n": len(r), "k": len(next(iter(r[0][1].values()))["criteria"])} for n, r in S.items()}
    for (w, n, v), r in runs.items():
        if "p" in r and int(n[1:]) <= 150:
            cap.dump(r["p"], os.path.join(cap.RESULTS, "cardinality", "%s.%s%s.preds.json.gz" % (w, v, n)))
    return cap.save("cardinality", keys, detail, meta)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    a.add_argument("--k", default=",".join(map(str, KS)))
    x = a.parse_args()
    main(x.who.split(","), x.kai, [int(k) for k in x.k.split(",")])
