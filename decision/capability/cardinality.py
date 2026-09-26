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
    bi.     the same with the dedicated bi-encoder Laya's README recommends in its place:
            sentence-transformers/all-MiniLM-L6-v2 @1110a243 (Apache-2.0), normalized.
Jev refuses more than 255 choices (HTTP 400 "Too many choices"); at K >= 10,000 it is sent 10
cases, and once all 10 are refused alike the rest are recorded as refused by the same rule, unsent.

Each run is kept as results/cardinality/<who>.<variant><k>.sums.json.gz: per question its top
option and probability, gold's probability and rank, and the sum of squares (cap.summary), with
the run's fit, cost and latency; keys are computed from every such file (cap.measure), so a run of
one backend rescored leaves the others as kept. Full vectors are kept too up to K = 150
(<who>.<variant><k>.preds.json.gz). recall@k counts a tie with gold against it (cap.rank).

    python cardinality.py [--who laya,jev,kai] [--kai CHECKPOINT] [--k 4,16,...] [--variants ,sl.,bi.]
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
WORDNET = "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59"  # nltk's wordnet.zip, WordNet 3.0
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
    d = os.path.join(cap.SCRATCH, "nltk")
    z = os.path.join(d, "corpora", "wordnet.zip")
    if not os.path.exists(z):
        nltk.download("wordnet", download_dir=d, quiet=True)
    assert cap.sha(z) == WORDNET, "wordnet.zip differs from the pinned corpus"
    nltk.data.path.insert(0, d)
    from nltk.corpus import wordnet as wn
    assert wn.get_version() == "3.0"
    syn = sorted(wn.all_synsets(), key=lambda s: s.name())  # all_synsets' order follows the string hash
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
BI = ("sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41")


def encoder(L, how):
    """The embed_fn a shortlist ranks by: Laya's English encoder (sl.) or the bi-encoder (bi.)."""
    if how == "sl.":
        from laya.shortlist import embed_fn_from_agent
        return embed_fn_from_agent(L.agent("english"), batch_size=128)
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(BI[0], revision=BI[1], device="cpu")
    return lambda texts: m.encode(list(texts), batch_size=256, normalize_embeddings=True)


def shortlists(L, S, how):
    """Per suite, per case: the top-SL labels by laya.shortlist over `how`'s encoder, the seconds
    to embed the label list once (cached by text) and each case's own seconds. Kept in cases/."""
    from laya.shortlist import shortlist_choice
    memo, raw = {}, []

    def embed(texts):
        raw or raw.append(encoder(L, how))
        miss = [t for t in dict.fromkeys(texts) if t not in memo]
        for i in range(0, len(miss), 4096):
            memo.update(zip(miss[i:i + 4096], raw[0](miss[i:i + 4096])))
        return np.stack([memo[t] for t in texts])

    path = os.path.join(cap.CASES, "cardinality.%sshortlists.json.gz" % how)
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


KEEP = ("fit", "dropped", "n_errors", "error_kinds", "errors", "served", "cost_usd", "input_tokens", "unsent",
        "note", "latency_ms", "seconds")


def sums(rows, p):
    """cap.summary per question of `rows` under preds `p`, None where unanswered."""
    return [None if p.get("%d/%s" % (ci, qid)) is None else cap.summary(p["%d/%s" % (ci, qid)], g[qid]["idx"])
            for ci, (_, qs, g) in enumerate(rows) for qid in qs]


def keep(w, v, n, rows, r):
    """Write one run: its summaries with what else it measured, and up to K = 150 its vectors."""
    d = os.path.join(cap.RESULTS, "cardinality")
    cap.dump(dict({x: r[x] for x in KEEP if x in r}, sums=sums(rows, r["p"])),
             os.path.join(d, "%s.%s%s.sums.json.gz" % (w, v, n)))
    if int(n[1:]) <= 150:
        cap.dump(r["p"], os.path.join(d, "%s.%s%s.preds.json.gz" % (w, v, n)))


def keys_from_disk(keys):
    """Every kept run's keys, from its summaries."""
    d = os.path.join(cap.RESULTS, "cardinality")
    detail = {}
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not f.endswith(".sums.json.gz"):
            continue
        w, rest = f[:-len(".sums.json.gz")].split(".", 1)
        v, n = (rest.rsplit(".", 1) + [""])[:2] if "." in rest else ("", rest)
        v = v + "." if v else ""
        r = cap.load(os.path.join(d, f))
        m = r.get("metrics") or cap.measure(r["sums"], len(r["sums"]))
        keys.metrics(w, n + "." + v, m, ("accuracy", "accall", "ece", "brier", "nll", "unanswered", "recall1",
                                         "recall5", "recall20"))
        nq = m["questions"]
        if r.get("seconds") and m.get("n"):
            keys.put(w, n + "." + v + "msperq", 1e3 * r["seconds"] / m["n"])
        if "fit" in r:
            keys.put(w, n + "." + v + "rejected", r["fit"]["rejected"] / nq)
            keys.put(w, n + "." + v + "optionscut", r["fit"]["options_cut"] / nq)
            keys.put(w, n + "." + v + "statecut", r["fit"]["state_cut"] / nq)
        if w == "jev":
            keys.put(w, n + "." + v + "rejected", r.get("n_errors", 0) / nq)
            keys.put(w, n + "." + v + "p50ms", cap.pct(r.get("latency_ms") or [], 50))
            keys.put(w, n + "." + v + "p95ms", cap.pct(r.get("latency_ms") or [], 95))
            keys.put(w, n + "." + v + "usd", r.get("cost_usd"))
        detail.setdefault(n, {})[w + ("." + v.rstrip(".") if v else "")] = dict(
            {x: r[x] for x in KEEP if x in r and x != "latency_ms"}, metrics=m)
    return detail


def main(who, kai, ks, variants=("", "wide.", "sl.", "bi.")):
    S = cap.trim(cases(ks))
    for name, rows in S.items():
        if name != "k77" and int(name[1:]) <= 1000:
            cap.dump(S[name], os.path.join(cap.CASES, "cardinality.%s.json.gz" % name))
    B = cap.backends(who, kai)
    keys, pending = cap.Keys("cardinality"), {}
    L = B.get("laya") or (cap.Laya() if any(v in ("sl.", "bi.") for v in variants) else None)
    R = {}
    for how in [v for v in variants if v in ("sl.", "bi.")]:
        sl = shortlists(L, S, how)
        for n in sl:
            R[(how, n)] = reduce(S[n], sl[n]["picks"])
            keys.put("all", n + "." + how + "hit", float(np.mean([g[next(iter(g))]["in"] for _, _, g in R[(how, n)][0]])))
            keys.put("all", n + "." + how + "indexs", sl[n]["index_s"])
            keys.put("all", n + "." + how + "casems", float(np.median(sl[n]["case_ms"])))
    for w, b in B.items():
        for n, rows in S.items():
            k = int(n[1:])
            for v in variants:
                if v == "wide." and (w != "laya" or not 77 <= k <= 1000):
                    continue
                if v in ("sl.", "bi.") and (v, n) not in R:
                    continue
                sub, maps = R[(v, n)] if v in ("sl.", "bi.") else (rows, None)
                try:
                    r = answer(w, b, v, n, sub)
                except cap.Pending as e:
                    pending[w] = str(e)
                    break
                if maps:
                    r["p"] = expand(r["p"], maps, rows)
                keep(w, v, n, rows, r)
    detail = keys_from_disk(keys)
    meta = {w: b.meta for w, b in B.items()}
    meta.update(pending=pending, bi=BI, cases={n: {"n": len(r), "k": len(next(iter(r[0][1].values()))["criteria"])}
                                               for n, r in S.items()})
    return cap.save("cardinality", keys, detail, meta)


def answer(w, b, v, n, rows):
    """One backend's run of one variant: preds, and what else it measured."""
    if w == "laya":
        if v == "wide.":
            ag = b.agent("english")
            was = dict(ag.cfg)
            ag.cfg.update(max_len=8192, head_max_len=7680)
            try:
                r = b.preds(rows, model="english", tag="laya wide " + n)
                r["fit"] = b.fit(rows, model="english")
            finally:
                ag.cfg.clear()
                ag.cfg.update(was)
            return r
        r = b.preds(rows, tag="laya %s%s" % (v, n))
        if not v:
            r["fit"] = b.fit(rows)
        return r
    if w == "jev":
        return jev_run(b, rows, "cardinality.%s%s" % (v, n))
    path = os.path.join(cap.SCRATCH, "cardinality.%s%s.json.gz" % (v, n))
    cap.dump({n: rows}, path)
    return b.preds(path, path + ".kai.json.gz")[n]


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    a.add_argument("--k", default=",".join(map(str, KS)))
    a.add_argument("--variants", default=",wide.,sl.,bi.")
    x = a.parse_args()
    main(x.who.split(","), x.kai, [int(k) for k in x.k.split(",")], x.variants.split(","))
