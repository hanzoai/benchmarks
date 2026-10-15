#!/usr/bin/env python3
"""build.py DATA OUT: the suite's items from the pinned public datasets, with each item's text.

DATA holds the files fetch.py downloads (files.json pins each by revision and SHA-256). The items
are drawn as prereg.json fixes them: a dataset's rows ordered by sha256("jailbreak-suite" NUL
"<dataset>/<row key>") and the first n kept, a within-dataset repeat dropped. Which items are clean
for Kai (no Kai training source could hold them) was decided against Kai's training registry, which
is not public; manifest.jsonl.gz records that decision and its reason per item, and this file
takes the manifest's items and flags as they are, after checking that every manifest item is built
here with the same SHA-256 of its text. Writes OUT/items.jsonl (with text: never committed; the
datasets' terms are theirs) for read.py.

Read with `python3 -I`; every input is untrusted data and is only parsed. Needs pyarrow.

    python3 -I jailbreak-suite/fetch.py data
    uv run --with pyarrow python3 -I jailbreak-suite/build.py data items
"""
import ast
import csv
import gzip
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict

import pyarrow.parquet as pq

csv.field_size_limit(10**9)
DATA, OUT = sys.argv[1:3]
HERE = os.path.dirname(os.path.abspath(__file__))
PRE = json.load(open(os.path.join(HERE, "prereg.json")))
WORD = re.compile(r"\w+")


def draw(*parts):
    """A stable order: sha256 of the parts, the suite's seed first."""
    return hashlib.sha256("\0".join(("jailbreak-suite",) + parts).encode()).hexdigest()


def sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


def norm(t):
    return " ".join(WORD.findall(t.lower()))


def pick(rows, n, key):
    """The first n rows by draw order of key(row)."""
    return sorted(rows, key=lambda r: draw(key(r)))[:n]


def parquet(path):
    return pq.read_table(path).to_pylist()


def csvrows(path, sep=","):
    return list(csv.DictReader(open(path, newline="", encoding="utf-8"), delimiter=sep))


def jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]



# --- the scored datasets ---

items = []


def add(dataset, key, label, text, task, pool, **meta):
    items.append({"id": f"{dataset}/{key}", "dataset": dataset, "label": int(label), "task": task,
                  "pool": pool, "text": text, **meta})


def D(*p):
    return os.path.join(DATA, *p)


# deepset/prompt-injections, test split, every row
for i, r in enumerate(parquet(D("deepset/data/test-00000-of-00001-701d16158af87368.parquet"))):
    add("deepset", f"test/{i}", r["label"], r["text"], "injection", "curated")

# jackhhao/jailbreak-classification, default test split, every row
for i, r in enumerate(csvrows(D("jackhhao/default/jailbreak_dataset_test.csv"))):
    add("jackhhao", f"test/{i}", r["type"] == "jailbreak", r["prompt"], "jailbreak", "curated")

# leolee99/NotInject, its three subsets (every row benign)
for part in ("one", "two", "three"):
    for i, r in enumerate(parquet(D(f"notinject/data/NotInject_{part}-00000-of-00001.parquet"))):
        add("notinject", f"{part}/{i}", 0, r["prompt"], "injection", "curated", category=r["category"])

# Lakera/gandalf_ignore_instructions: every split's rows are attacks; a sample
g = []
for split, f in (("train", "train-00000-of-00001-ded53be747ff55cd"), ("validation", "validation-00000-of-00001-94481a2a09ff2fff"),
                 ("test", "test-00000-of-00001-bc92128b9288a6d1")):
    g += [(split, i, r["text"]) for i, r in enumerate(parquet(D("gandalf/data", f + ".parquet")))]
for split, i, t in pick(g, PRE["datasets"]["gandalf"]["n"], lambda x: f"gandalf/{x[0]}/{x[1]}"):
    add("gandalf", f"{split}/{i}", 1, t, "injection", "real")

# qxcv/tensor-trust hijacking robustness: the human attack is positive, the access code benign
tt = jsonl(D("tensortrust/benchmarks/hijacking-robustness/v1/hijacking_robustness_dataset.jsonl"))
n = PRE["datasets"]["tensortrust"]["n"]
for r in pick(tt, n, lambda r: f"tt/attack/{r['sample_id']}"):
    add("tensortrust", f"attack/{r['sample_id']}", 1, r["attack"], "injection", "real")
codes = {}
for r in tt:
    codes.setdefault(norm(r["access_code"]), r)
for r in pick(list(codes.values()), n, lambda r: f"tt/code/{r['sample_id']}"):
    add("tensortrust", f"code/{r['sample_id']}", 0, r["access_code"], "injection", "real")

# BIPIA (geodesic-research/bipia, microsoft/BIPIA's test contexts with attacks inserted): the
# injected external content is positive; a base context as microsoft/BIPIA a004b69 holds it
# (benchmark/<task>/test.jsonl, a code context's lines joined by newlines, as geodesic joins
# them) is benign
bip = parquet(D("bipia/bipia/train-00000-of-00001.parquet"))
n = PRE["datasets"]["bipia"]["n"]
for r in pick(bip, n, lambda r: f"bipia/inj/{r['id']}"):
    add("bipia", f"inj/{r['id']}", 1, r["context"], "injection", "curated", category=r["attack_category"], task_name=r["task_name"])
clean = {}
for task in ("email", "table", "code"):
    for i, r in enumerate(jsonl(D("bipia-raw", task + ".jsonl"))):
        c = r["context"]
        clean[f"{task}-{i}"] = ("\n".join(c) if isinstance(c, list) else c, task)
for base, (c, tn) in pick(list(clean.items()), n, lambda x: f"bipia/clean/{x[0]}"):
    add("bipia", f"clean/{base}", 0, c, "injection", "curated", task_name=tn)

# TrustAIRLab/in-the-wild-jailbreak-prompts, the 2023-12-25 tables Kai's builder reads
wj = [(i, r) for i, r in enumerate(parquet(D("wild/jailbreak_2023_12_25/train-00000-of-00001.parquet")))]
wr = [(i, r) for i, r in enumerate(parquet(D("wild/regular_2023_12_25/train-00000-of-00001.parquet")))]
for i, r in wj:
    add("wild", f"jailbreak/{i}", 1, r["prompt"], "jailbreak", "real", platform=r["platform"])
regular = pick([x for x in wr if x[1]["prompt"].strip()], PRE["datasets"]["wild"]["regular_pool"], lambda x: f"wild/regular/{x[0]}")
for i, r in regular:
    add("wild", f"regular/{i}", 0, r["prompt"], "jailbreak", "real", platform=r["platform"])

# allenai/wildjailbreak eval: adversarial harmful positive, adversarial benign negative
we = csvrows(D("wildjailbreak/eval/eval.tsv"), "\t")
harm = [(i, r) for i, r in enumerate(we) if r["data_type"] == "adversarial_harmful"]
ben = [(i, r) for i, r in enumerate(we) if r["data_type"] == "adversarial_benign"]
for i, r in pick(harm, PRE["datasets"]["wildjailbreak"]["harmful"], lambda x: f"wjb/{x[0]}"):
    add("wildjailbreak", f"eval/{i}", 1, r["adversarial"], "jailbreak", "curated")
for i, r in ben:
    add("wildjailbreak", f"eval/{i}", 0, r["adversarial"], "jailbreak", "curated")

# JailbreakBench: released attack artifacts (positive whether or not they succeeded) and the
# benign behaviors (negative)
art = []
for root, _, files in os.walk(D("jbbart")):
    for f in sorted(files):
        if not f.endswith(".json") or f == "attack-info.json":
            continue
        d = json.load(open(os.path.join(root, f)))
        m = d["parameters"]
        for j in d["jailbreaks"]:
            if j.get("prompt"):
                art.append((f"{m['method']}/{m['model']}/{j['index']}", j["prompt"]))
seen = set()
art = [a for a in sorted(art) if not (norm(a[1]) in seen or seen.add(norm(a[1])))]
for k, t in pick(art, PRE["datasets"]["jbb"]["n"], lambda x: f"jbb/{x[0]}"):
    add("jbb", f"artifact/{k}", 1, t, "jailbreak", "curated")
for i, r in enumerate(csvrows(D("jbb/data/benign-behaviors.csv"))):
    add("jbb", f"benign/{i}", 0, r["Goal"], "jailbreak", "curated")

# harmful content: JailbreakBench's judged responses and HarmBench's classifier validation set
jc = csvrows(D("jbb/data/judge-comparison.csv"))
votes = lambda r, ks: sum(int(r[k]) for k in ks)
H3 = ("human1", "human2", "human3")
pos = [r for r in jc if votes(r, H3) >= 2]
neg = [r for r in jc if votes(r, H3) == 0]
n = PRE["datasets"]["jbbresp"]["n"]
for r in pick(pos, n, lambda r: f"jbbresp/{r['Index']}") + pick(neg, n, lambda r: f"jbbresp/{r['Index']}"):
    add("jbbresp", r["Index"], votes(r, H3) >= 2, r["target_response"], "harm", "harm")
hb = json.load(open(D("harmbenchval/text_behaviors_val_set.json")))
hrows = [(b, k, x) for b, v in sorted(hb.items()) for k, x in enumerate(v)]
H3 = ("human_0", "human_1", "human_2")
pos = [x for x in hrows if votes(x[2], H3) >= 2]
neg = [x for x in hrows if votes(x[2], H3) == 0]
n = PRE["datasets"]["harmbench"]["n"]
for b, k, x in pick(pos, n, lambda x: f"hb/{x[0]}/{x[1]}") + pick(neg, n, lambda x: f"hb/{x[0]}/{x[1]}"):
    add("harmbench", f"{b}/{k}", votes(x, H3) >= 2, x["generation"], "harm", "harm")

# AI-generated text: HC3 (a question's human or ChatGPT answer, never both) and M4
hc = [r for r in jsonl(D("hc3/all.jsonl")) if r["human_answers"] and r["chatgpt_answers"]]
hc = pick(list(enumerate(hc)), 2 * PRE["datasets"]["hc3"]["n"], lambda x: f"hc3/{x[0]}")
n = PRE["datasets"]["hc3"]["n"]
for j, (i, r) in enumerate(hc):
    human = j < n
    add("hc3", f"{i}/{'human' if human else 'chatgpt'}", not human,
        (r["human_answers"] if human else r["chatgpt_answers"])[0], "aitext", "aitext", source=r["source"])
def first(v):
    return (v[0] if v else "") if isinstance(v, list) else (v or "")


m4 = []
for f in PRE["datasets"]["m4"]["files"]:
    for i, r in enumerate(jsonl(D("m4", f + ".jsonl"))):
        r = {"human_text": first(r.get("human_text", r.get("text"))), "machine_text": first(r.get("machine_text"))}
        if r["human_text"].strip() and r["machine_text"].strip():
            m4.append((f, i, r))
m4 = pick(m4, 2 * PRE["datasets"]["m4"]["n"], lambda x: f"m4/{x[0]}/{x[1]}")
n = PRE["datasets"]["m4"]["n"]
for j, (f, i, r) in enumerate(m4):
    human = j < n
    add("m4", f"{f}/{i}/{'human' if human else 'machine'}", not human,
        r["human_text"] if human else r["machine_text"], "aitext", "aitext", source=f)

# multi-turn: tom-gibbs' harmful conversations, its completely- and semi-benign twins, and
# ultrachat's test conversations, each read as the conversation so far after every user turn


def render(turns):
    lines = []
    for t in turns:
        c = t["content"] if isinstance(t["content"], str) else ""
        if t["role"] == "assistant" and c.strip() in ("", "None"):
            continue
        lines.append(f"{t['role']}: {c.strip()}")
    return "\n".join(lines)


def conversation(dataset, key, label, turns, **meta):
    for k, t in enumerate(turns):
        if t["role"] == "user":
            add(dataset, f"{key}/turn{k}", label, render(turns[: k + 1]), "jailbreak", "multiturn", conv=f"{dataset}/{key}", **meta)


for name, f, label in (("mt-harmful", "Harmful Dataset.csv", 1), ("mt-benign", "Completely-Benign Dataset.csv", 0),
                       ("mt-semibenign", "Semi-Benign Dataset.csv", 0)):
    rows = list(enumerate(csvrows(D("multiturn", f))))
    for i, r in pick(rows, PRE["datasets"][name]["n"], lambda x: f"{name}/{x[0]}"):
        conversation(name, str(i), label, ast.literal_eval(r["Multi-turn conversation"]),
                     cipher=f"{r['Input-cipher']}/{r['Output-cipher']}")
uc = list(enumerate(parquet(D("ultrachat/data/test_sft-00000-of-00001-f7dfac4afe5b93f4.parquet"))))
for i, r in pick(uc, PRE["datasets"]["ultrachat"]["n"], lambda x: f"ultrachat/{x[0]}"):
    conversation("ultrachat", r["prompt_id"][:16], 0, r["messages"])

# within a dataset an exact repeat (normalized) keeps its first row; a text carrying both labels
# is dropped whole
by = defaultdict(list)
for it in items:
    if "conv" not in it:
        by[(it["dataset"], norm(it["text"]))].append(it)
drop = set()
dupes = Counter()
for (ds, _), group in by.items():
    if len({x["label"] for x in group}) > 1:
        drop.update(x["id"] for x in group)
        dupes[(ds, "conflict")] += len(group)
    else:
        drop.update(x["id"] for x in group[1:])
        dupes[(ds, "repeat")] += len(group) - 1
items = [it for it in items if it["id"] not in drop]

# --- the manifest: the committed item list, labels and Kai's contamination flags ---

manifest = [json.loads(l) for l in gzip.open(os.path.join(HERE, "manifest.jsonl.gz"), "rt")]
built = {it["id"]: it for it in items}
missing = [m["id"] for m in manifest if m["id"] not in built]
differ = [m["id"] for m in manifest if m["id"] in built and sha(built[m["id"]]["text"]) != m["sha256"]]
if missing or differ:
    sys.exit("manifest items not built: %d (first %s); built with another text: %d (first %s)"
             % (len(missing), missing[:3], len(differ), differ[:3]))
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "items.jsonl"), "w") as f:
    for m in manifest:
        it = built[m["id"]]
        assert it["label"] == m["label"] and it["task"] == m["task"] and it["pool"] == m["pool"], m["id"]
        f.write(json.dumps(dict(it, clean=m["clean"], why=m["why"]), ensure_ascii=False) + "\n")
n = Counter((m["dataset"], m["clean"]) for m in manifest)
print("%d items, every text matching the manifest; %d clean for Kai" % (len(manifest), sum(m["clean"] for m in manifest)))
