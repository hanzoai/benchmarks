"""How many of each headline suite's harness rows are in the data Laya trained on: trained/overlap.json.

Each suite's rows (results/states.json.gz) are compared with the training split of every dataset they
were drawn from that a Laya checkpoint trained on, at a pinned revision, by held/build.py's rules: a row
is found when its text equals a training row's after lowercasing and collapsing whitespace (exact), or
when at least half of its word 5-grams occur in one training row (contained, counted only where exact did
not fire). A training row's text is built the way Laya's builder builds the state from it, untruncated.

RAG relevance is compared as whole states, since MS MARCO passages repeat across splits: a row is found
only in a training pair with the same query whose passage is equal (exact) or holds half of the row's
passage 5-grams (contained). A dataset no Laya checkpoint trained on is not compared, and the suite says
which source reports it held out.

    uv run --python 3.11 --with huggingface_hub --with pyarrow python trained/measure.py
"""
import gzip
import json
import os
import sys

import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "held"))
sys.dont_write_bytecode = True
from build import NEAR, Near, fetch, grams, norm, rows_csv  # noqa: E402

STATES = os.path.join(HERE, "..", "results", "states.json.gz")
OUT = os.path.join(HERE, "overlap.json")
LAYA = "github.com/hanzoai/laya@970dc8c5f63d7b886a68409493f37d569424f933"

# The Laya checkpoints that trained on a dataset: hanzo-inc/kai train/src/data/laya.rs CLAIMS, from the
# sources cited there. laya-typed-decisions is fine-tuned from laya, so it holds laya's data too.
ENGLISH = ["laya", "laya-typed-decisions"]
TYPED = ["laya-typed-decisions"]

AG = ("fancyzhx/ag_news", "eb185aade064a813bc0b7f42de02595523103ca4")
ENRON = ("SetFit/enron_spam", "1916f66c89d52221ae33eb57d44498b4f3a5df22")
ZEFANG = ("zefang-liu/phishing-email-dataset", "34085a032c123ca237f314a01a67909cdea35e34")
TOBI = ("Tobi-Bueck/customer-support-tickets", "ddf1c81a5475992c4fa6752bf1e8b4e31f07bbeb")
MARCO = ("microsoft/ms_marco", "a47ee7aae8d7d466ba15f9f0bfac3b3681087b3a")
DECISIONS = ("LocalLLaMA/typed-decisions", "c76749ec58bd8c3d2ea706b31c333a9059c38f90")


def leaves(v):
    """A state's text: its leaf values in order, keys left out."""
    if isinstance(v, dict):
        return [x for u in v.values() for x in leaves(u)]
    if isinstance(v, list):
        return [x for u in v for x in leaves(u)]
    return [str(v)]


def text(state):
    return " ".join(leaves(state))


def parquet(repo, name, columns):
    for batch in pq.ParquetFile(fetch(repo, name)).iter_batches(batch_size=4096, columns=columns):
        yield from batch.to_pylist()


# ------------------------------------------------------------------ training rows, as Laya's builders make states
def ag_news():
    return (r["text"] for r in parquet(AG, "data/train-00000-of-00001.parquet", ["text"]))


def enron():
    for line in open(fetch(ENRON, "train.jsonl")):
        r = json.loads(line)
        yield "%s %s" % (r.get("subject") or "", r.get("message") or "")


def phishing():
    return (r["Email Text"] or "" for r in rows_csv(fetch(ZEFANG, "Phishing_Email.csv")))


TOBI_FILES = ("aa_dataset-tickets-multi-lang-5-2-50-version.csv", "dataset-tickets-german_normalized_50_5_2.csv",
              "dataset-tickets-multi-lang-4-20k.csv")


def tickets():
    for name in TOBI_FILES:
        for r in rows_csv(fetch(TOBI, name)):
            yield "%s %s" % (r.get("subject") or "", (r.get("body") or "").replace("\\n", "\n"))


def decisions():
    for r in parquet(DECISIONS, "all/train-00000-of-00001.parquet", ["state"]):
        s = r["state"]
        try:
            s = json.loads(s)
        except (TypeError, ValueError):
            pass
        yield text(s)


def marco():
    """(query, passage) for every passage of every v1.1 training query."""
    for r in parquet(MARCO, "v1.1/train-00000-of-00001.parquet", ["query", "passages"]):
        for p in r["passages"]["passage_text"]:
            yield r["query"], p


SOURCES = {
    "ag_news": (AG, "data/train-00000-of-00001.parquet", ag_news, ENGLISH),
    "enron": (ENRON, "train.jsonl", enron, ENGLISH),
    "phishing": (ZEFANG, "Phishing_Email.csv (the train split)", phishing, ENGLISH),
    "tickets": (TOBI, ", ".join(TOBI_FILES) + " (the train split)", tickets, ENGLISH),
    "decisions": (DECISIONS, "all/train-00000-of-00001.parquet", decisions, TYPED),
}

# Each suite: where its rows are drawn, the datasets among them a Laya checkpoint trained
# on, and those upstream reports held out (a path in LAYA).
B, L = LAYA + " research/scripts/bench_apps.py", LAYA + " research/scripts/bench_local.py"
SUITES = {
    "jev.ag_news": (B + ":88, fancyzhx/ag_news test", ["ag_news"], []),
    "jev.emotion": (B + ":103, dair-ai/emotion test", [], ["dair-ai/emotion (README.md:872)"]),
    "jev.banking77_full": (B + ":118, mteb/banking77 test", [],
                           ["mteb/banking77 (research/scripts/build_benchmark_nb.py:759)"]),
    "app.support_triage": (B + ":149, Tobi-Bueck/customer-support-tickets train", ["tickets"], []),
    "app.email_spam": (B + ":162, SetFit/enron_spam test", ["enron"], []),
    "app.phishing": (B + ":179, zefang-liu/phishing-email-dataset train", ["phishing"], []),
    "app.guardrails_jailbreak": (B + ":197, lmsys/toxic-chat toxicchat0124 test", [],
                                 ["lmsys/toxic-chat (BENCHMARKS.md:131)"]),
    "app.moderation_toxicity": (B + ":210, lmsys/toxic-chat toxicchat0124 test", [],
                                ["lmsys/toxic-chat (BENCHMARKS.md:132)"]),
    "app.rag_relevance": (B + ":233, microsoft/ms_marco v1.1 validation", ["marco"], []),
    "app.model_routing_domain": (B + ":261, openai/gsm8k, google-research-datasets/mbpp and fancyzhx/ag_news test",
                                 ["ag_news"], ["openai/gsm8k, google-research-datasets/mbpp (BENCHMARKS.md:135)"]),
    "typed_decisions": (L + ":221, LocalLLaMA/typed-decisions all test", ["decisions"],
                        ["LocalLLaMA/typed-decisions, by laya and laya-multilingual "
                         "(research/scripts/build_benchmark_nb.py:760)"]),
    "massive": (L + ":160, mteb/amazon_massive_intent test, 51 languages", [],
                ["mteb/amazon_massive_intent (research/scripts/build_benchmark_nb.py:760); laya-multilingual's "
                 "card names no training sources"]),
}


def contained(texts, refs):
    """For each text: 'exact', 'contained' or None against one stream of reference texts."""
    near, hit = Near(texts), [None] * len(texts)
    for t in refs:
        for i in near.exact.get(norm(t), ()):
            hit[i] = "exact"
        n, shared = near.overlap(t)
        for i, k in shared.items():
            if hit[i] is None and k / near.size[i] >= NEAR:
                hit[i] = "contained"
    return hit


def whole(states):
    """RAG relevance by whole state: the same query, and its passage equal to or contained in the pair's."""
    passages = Near([s["passage"] for s in states])
    queries = {}
    for i, s in enumerate(states):
        queries.setdefault(norm(s["query"]), []).append(i)
    hit, alone, asked, pairs = [None] * len(states), set(), set(), 0
    for q, p in marco():
        pairs += 1
        alone.update(passages.exact.get(norm(p), ()))
        rows = queries.get(norm(q))
        if not rows:
            continue
        asked.update(rows)
        for i in passages.exact.get(norm(p), ()):
            if i in rows:
                hit[i] = "exact"
        n, shared = passages.overlap(p)
        for i, k in shared.items():
            if i in rows and hit[i] is None and k / passages.size[i] >= NEAR:
                hit[i] = "contained"
    return hit, pairs, len(asked), len(alone)


def found(hit):
    """A source's matches, without the suite's row count."""
    c = count(hit)
    return {"exact": c["exact"], "contained": c["contained"], "share": c["share"]}


def count(hit):
    rows = len(hit)
    exact = sum(h == "exact" for h in hit)
    con = sum(h == "contained" for h in hit)
    return {"rows": rows, "exact": exact, "contained": con, "share": round((exact + con) / rows, 4) if rows else 0.0}


def main():
    S = json.load(gzip.open(STATES))
    out = {}
    for suite, (drawn, names, held) in SUITES.items():
        if suite == "massive":
            langs = sorted(n for n in S if n.startswith("massive."))
            rows = sum(len(S[n]) for n in langs)
            out[suite] = dict(count([None] * rows), drawn=drawn, compared=[], checkpoints=[], held=held,
                              languages={n.split(".", 1)[1]: count([None] * len(S[n])) for n in langs})
            continue
        states = [st for st, _, _ in S[suite]]
        hit, compared, checkpoints = [None] * len(states), [], []
        for name in names:
            if name == "marco":
                got, pairs, asked, alone = whole(states)
                compared.append({"dataset": MARCO[0], "revision": MARCO[1], "split": "train",
                                 "files": "v1.1/train-00000-of-00001.parquet", "rows": pairs,
                                 "basis": "whole state: the same query, its passage exact or contained",
                                 "same query": asked, "same passage": alone, **found(got)})
                checkpoints += ENGLISH
            else:
                repo, files, rows, ckpts = SOURCES[name]
                refs = list(rows())
                got = contained([text(s) for s in states], refs)
                compared.append({"dataset": repo[0], "revision": repo[1], "split": "train", "files": files,
                                 "rows": len(refs), **found(got)})
                checkpoints += ckpts
            hit = [h or g for h, g in zip(hit, got)]
            print(suite, compared[-1], flush=True)
        out[suite] = dict(count(hit), drawn=drawn, compared=compared,
                          checkpoints=sorted(set(checkpoints)), held=held)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    for suite, r in out.items():
        print("%-26s %5d rows  exact %4d  contained %4d  share %.4f" % (suite, r["rows"], r["exact"], r["contained"], r["share"]))


if __name__ == "__main__":
    main()
