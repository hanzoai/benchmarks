"""The held-out suites: held.phishing and held.support_triage, 400 cases each.

Laya trained on the rows behind the frozen harness's app.phishing and app.support_triage, so those
suites cannot compare it with Kai or Jev. These ask the same questions, verbatim from the Laya 0.3.20
builders (research/scripts/bench_apps.py), of rows no backend trained on, in the frozen harness's
format: states.json.gz {suite: [[state, questions, gold]]}, questions.json.gz {suite: [[gold, questions]]}.

    HANZO_TOKEN=$(hanzo auth token) uv run --python 3.11 python held/build.py generate   # until it exits 0
    HANZO_TOKEN=$(hanzo auth token) uv run --python 3.11 python held/build.py check      # until it exits 0
    uv run --python 3.11 --with huggingface_hub python held/build.py build

generate and check call api.hanzo.ai and append to support/. build reads only those files, the frozen
harness and pinned dataset revisions, so it is deterministic. A token lives about 11 minutes, so
generate and check stop after BUDGET seconds and exit 3 while work remains.
"""
import collections
import concurrent.futures as cf
import copy
import csv
import gzip
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "..", "harness")
FROZEN = os.path.join(HERE, "..", "results", "states.json.gz")
GENERATED = os.path.join(HERE, "support", "generate.jsonl")
CHECKED = os.path.join(HERE, "support", "check.jsonl")
SEED, CAP, NEAR = 13, 3000, 0.5
csv.field_size_limit(sys.maxsize)

AURA = ("kudzaiprichard/aura-phishing-email-corpus", "539567cee21d03c83bd2fb1b142c18a80904eb72")
ZEFANG = ("zefang-liu/phishing-email-dataset", "34085a032c123ca237f314a01a67909cdea35e34")
ENRON = ("SetFit/enron_spam", "1916f66c89d52221ae33eb57d44498b4f3a5df22")
TOBI = ("Tobi-Bueck/customer-support-tickets", "ddf1c81a5475992c4fa6752bf1e8b4e31f07bbeb")
TOBI_FILES = ("aa_dataset-tickets-multi-lang-5-2-50-version.csv", "dataset-tickets-german_normalized_50_5_2.csv",
              "dataset-tickets-multi-lang-4-20k.csv")

# The questions, verbatim from bench_apps.py.
PHISHING = {"is_phishing": {"type": "noul",
                            "instructions": "Is this email a phishing or scam attempt to steal money, credentials, or personal data?",
                            "criteria": {"true": "phishing, scam, or fraud",
                                         "false": "a legitimate email (even if promotional)"}}}
QUEUES = {"Technical Support": "technical problems, bugs, outages, integrations",
          "Product Support": "help using a product or feature",
          "Customer Service": "general account or service questions",
          "IT Support": "internal IT, devices, access, networks",
          "Billing and Payments": "invoices, charges, refunds, payment methods",
          "Returns and Exchanges": "returning or exchanging an item",
          "Service Outages and Maintenance": "downtime, outages, scheduled maintenance",
          "Sales and Pre-Sales": "pricing, quotes, buying",
          "Human Resources": "employment, payroll, leave, hiring",
          "General Inquiry": "anything else"}
SUPPORT = {"queue": {"type": "choice", "instructions": "Which support queue should handle this ticket?",
                     "criteria": dict(QUEUES)}}

# held.phishing: {file: (label kept, cases)}. Phishing is Nazario's phishing corpus and the Nigerian
# advance-fee fraud corpus; legitimate is the ham of CEAS 2008 and TREC 2007. Spam is left out, since
# bench_apps.py's criteria call a promotional email legitimate, and so is SpamAssassin's ham: 93% of a
# 1,500-row sample matches a zefang-liu/phishing-email-dataset row.
STRATA = {"Nazario.csv": (1, 100), "Nigerian_Fraud.csv": (1, 100), "CEAS_08.csv": (0, 100), "TREC_07.csv": (0, 100)}
EXAMINE = 400  # candidates per stratum: the head of its seeded shuffle

# held.support_triage generation.
API = "https://api.hanzo.ai/v1/chat/completions"
GEN_MODEL, CHECK_MODEL = "zen6", "zen5"
PER_QUEUE, BATCH, KEEP = 50, 2, 40
BUDGET = 480  # seconds; a token lives about 11 minutes
INDUSTRIES = ["online retail", "software as a service", "hospital and clinics", "retail banking",
              "telecommunications", "logistics and shipping", "university", "law firm", "manufacturing",
              "hotel chain", "airline", "insurance", "city government", "nonprofit", "video game studio",
              "marketing agency", "restaurant chain", "real estate", "electric utility", "consumer electronics",
              "accounting firm", "gyms and fitness", "pharmacy", "car dealership", "school district",
              "media streaming", "travel agency", "construction", "biotech lab", "e-learning"]
PRODUCTS = ["CRM platform", "business laptop", "smart thermostat", "accounting software", "VPN client",
            "mobile banking app", "project management tool", "wireless headphones", "cloud file storage",
            "payroll system", "online storefront builder", "video conferencing service", "point-of-sale terminal",
            "analytics dashboard", "office printers", "fitness tracker", "web hosting plan", "email marketing tool",
            "ERP system", "smartphone", "meal-kit subscription", "electric scooter", "office chair",
            "video streaming subscription", "password manager", "Wi-Fi router", "e-signature service",
            "shipping label API", "security cameras", "tax filing software", "online course platform",
            "espresso machine", "help-desk software", "domain and DNS service", "HR information system"]
LENGTHS = ["short: 1 to 3 sentences", "medium: 60 to 120 words", "long: 150 to 250 words"]
TONES = ["polite and formal", "neutral and matter-of-fact", "frustrated", "urgent", "angry", "apologetic",
         "confused", "curt"]
WRITERS = ["fluent professional", "non-native English speaker with small grammar mistakes",
           "in a hurry: lowercase, typos, little punctuation", "non-technical person",
           "technical expert who uses jargon", "manager writing for a team", "older person unused to technology",
           "student"]
NEIGHBORS = {"Technical Support": ["Product Support", "IT Support", "Service Outages and Maintenance"],
             "Product Support": ["Technical Support", "Customer Service", "Returns and Exchanges"],
             "Customer Service": ["General Inquiry", "Billing and Payments", "Product Support"],
             "IT Support": ["Technical Support", "Human Resources", "Service Outages and Maintenance"],
             "Billing and Payments": ["Customer Service", "Returns and Exchanges", "Sales and Pre-Sales"],
             "Returns and Exchanges": ["Billing and Payments", "Product Support", "Customer Service"],
             "Service Outages and Maintenance": ["Technical Support", "IT Support"],
             "Sales and Pre-Sales": ["Billing and Payments", "General Inquiry", "Product Support"],
             "Human Resources": ["IT Support", "Billing and Payments", "General Inquiry"],
             "General Inquiry": ["Customer Service", "Sales and Pre-Sales", "Human Resources"]}
GEN_SYSTEM = ("You write realistic help-desk tickets for a routing benchmark. A ticket is an email to a support "
              "address: a subject line and a body, written the way that person would really write it. "
              "You answer with JSON only.")
CHECK_SYSTEM = "You answer a typed decision question about a JSON state."


# ------------------------------------------------------------------ near duplicates
def grams(text):
    w = re.findall(r"\w+", text.lower())
    return {" ".join(w[i:i + 5]) for i in range(len(w) - 4)}


def norm(text):
    return " ".join(text.lower().split())


class Near:
    """Candidate texts indexed by word 5-gram."""

    def __init__(self, texts):
        self.size, self.index, self.exact = [], collections.defaultdict(list), collections.defaultdict(list)
        for i, t in enumerate(texts):
            g = grams(t)
            self.size.append(len(g))
            for s in g:
                self.index[s].append(i)
            self.exact[norm(t)].append(i)

    def overlap(self, text):
        """(the number of 5-grams in text, {candidate: 5-grams it shares with text})."""
        g = grams(text)
        return len(g), collections.Counter(i for s in g for i in self.index.get(s, ()))


def dedup(texts, refs):
    """Which candidates survive, and how many each rule removed.

    Against every reference text, a candidate goes when it is equal after lowercasing and collapsing
    whitespace (exact), when the two share at least NEAR of the union of their word 5-grams
    (jaccard), or when at least NEAR of the candidate's 5-grams occur in it (contained, counted only
    where jaccard did not fire). A surviving candidate then goes when at least NEAR of its 5-grams or
    of an earlier survivor's are shared between the two (within suite). Rules overlap, so "removed"
    counts each candidate once.
    """
    near, hit = Near(texts), {}
    for name, rows in refs.items():
        e, j, c = set(), set(), set()
        for t in rows:
            e.update(near.exact.get(norm(t), ()))
            n, shared = near.overlap(t)
            for i, k in shared.items():
                if k / (near.size[i] + n - k) >= NEAR:
                    j.add(i)
                elif k / near.size[i] >= NEAR:
                    c.add(i)
        hit[name + ", exact"], hit[name + ", jaccard"], hit[name + ", contained"] = e, j, c
    gone, kept, within = set().union(*hit.values()), set(), set()
    for i, t in enumerate(texts):
        if i in gone:
            continue
        n, shared = near.overlap(t)
        dup = any(k / min(n, near.size[x]) >= NEAR for x, k in shared.items() if x in kept)
        (within if dup else kept).add(i)
    counts = {k: len(v) for k, v in hit.items()}
    counts.update({"within suite": len(within), "removed": len(gone | within), "kept": len(kept)})
    return [i in kept for i in range(len(texts))], counts


def fetch(repo, name):
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo[0], name, repo_type="dataset", revision=repo[1])


def rows_csv(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def frozen(*suites):
    S = json.load(gzip.open(FROZEN))
    return [st for n in suites for st, _, _ in S[n]]


# ------------------------------------------------------------------ held.phishing
def phishing():
    rng = random.Random(SEED)
    cand, strata, short = [], [], 0
    for name, (label, _) in STRATA.items():
        pool = [r["body"] for r in rows_csv(fetch(AURA, name)) if int(r["label"]) == label]
        rng.shuffle(pool)
        for body in pool[:EXAMINE]:
            if len(re.findall(r"\w+", body)) < 5:
                short += 1
                continue
            cand.append(body)
            strata.append(name)
    enron = [json.loads(line)["message"] for s in ("train.jsonl", "test.jsonl") for line in open(fetch(ENRON, s))]
    refs = {ZEFANG[0]: [r["Email Text"] for r in rows_csv(fetch(ZEFANG, "Phishing_Email.csv"))],
            ENRON[0]: enron,
            "frozen app.phishing, app.email_spam": [st.get("email") or st["body"]
                                                    for st in frozen("app.phishing", "app.email_spam")]}
    keep, counts = dedup(cand, refs)
    counts = dict({"examined": len(STRATA) * EXAMINE, "under 5 words": short}, **counts)
    rows, per = [], {}
    for name, (label, n) in STRATA.items():
        got = [c for c, s, k in zip(cand, strata, keep) if s == name and k][:n]
        if len(got) < n:
            raise SystemExit("%s: %d of %d survive; raise EXAMINE" % (name, len(got), n))
        per[name] = sum(1 for s, k in zip(strata, keep) if s == name and k)
        rows += [[{"email": c[:CAP]}, copy.deepcopy(PHISHING), {"is_phishing": {"idx": label}}] for c in got]
    rng.shuffle(rows)
    return rows, dict(counts, survivors=per)


# ------------------------------------------------------------------ held.support_triage
def spec(queue, i):
    r = random.Random("%d/%s/%d" % (SEED, queue, i))
    s = {"industry": r.choice(INDUSTRIES), "product": r.choice(PRODUCTS), "length": r.choices(LENGTHS, (3, 5, 2))[0],
         "tone": r.choice(TONES), "writer": r.choice(WRITERS), "subject": r.random() >= 0.1}
    if r.random() < 0.3:
        s["near"] = r.choice(NEIGHBORS[queue])
    return s


def gen_prompt(queue, specs):
    out = ['Write %d tickets that belong in the queue "%s" (%s).' % (len(specs), queue, QUEUES[queue]), "",
           "The help desk routes every ticket to exactly one of these queues:"]
    out += ["- %s: %s" % kv for kv in QUEUES.items()]
    out += ["", "Rules:",
            '- Someone who sees only the ticket and these ten queues must route it to "%s" and to no other queue.' % queue,
            "- Never name the queue or team the ticket is for.",
            "- Every ticket is distinct: a different sender, organisation, product and problem.",
            "- Invent names, companies and order or account numbers; no real people, e-mail addresses or phone numbers.",
            "", "One specification per ticket, in order:"]
    for k, s in enumerate(specs, 1):
        t = "%d. industry: %s; product or service: %s (replace it if it does not fit this queue); length: %s; " \
            "tone: %s; writer: %s; %s." % (k, s["industry"], s["product"], s["length"], s["tone"], s["writer"],
                                           "with a subject line" if s["subject"] else 'no subject line (subject "")')
        if "near" in s:
            t += ' Boundary case: it also touches on something that belongs to "%s" (%s), but what the writer ' \
                 'needs is clearly "%s".' % (s["near"], QUEUES[s["near"]], queue)
        out.append(t)
    out += ["", 'Answer with a JSON array of %d objects {"subject": ..., "body": ...}, in specification order.'
            % len(specs)]
    return "\n".join(out)


def check_prompt(t):
    q = SUPPORT["queue"]
    return "State: %s\n\nQuestion: %s\nOptions:\n%s\n\nAnswer with one option name, exactly as written, and nothing else." % (
        json.dumps({"subject": t["subject"], "body": t["body"][:CAP]}, ensure_ascii=False), q["instructions"],
        "\n".join("- %s: %s" % kv for kv in q["criteria"].items()))


def pick(answer):
    """The queue an answer names: an exact option name, else the one option name it contains."""
    a = answer.strip().strip("`*\"'. \n").lower()
    exact = [k for k in QUEUES if k.lower() == a]
    named = [k for k in QUEUES if k.lower() in a]
    return exact[0] if exact else named[0] if len(named) == 1 else None


class Expired(Exception):
    pass


def chat(model, messages, temperature, max_tokens):
    """(content, the model that served it) from api.hanzo.ai, streamed: a reasoning model's answer can
    take longer than the edge's 100 s wait for a first byte."""
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens, "stream": True}).encode()
    err = "no attempt"
    for attempt in range(10):  # the upstream answers 429 when busy
        req = urllib.request.Request(API, data=body, headers={
            "Authorization": "Bearer " + os.environ["HANZO_TOKEN"], "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                parts, finished = [], False
                for line in r:
                    data = line.decode("utf-8").strip()[5:].strip() if line.startswith(b"data:") else ""
                    if data and data != "[DONE]":
                        for c in json.loads(data).get("choices", []):
                            parts.append((c.get("delta") or {}).get("content") or "")
                            finished = finished or bool(c.get("finish_reason"))
                if finished:
                    return "".join(parts), r.headers.get("x-hanzo-served")
            err = "stream ended before a finish_reason"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise Expired()
            if e.code not in (429, 500, 502, 503, 504, 520, 522, 524):
                raise
            err = "HTTP %d" % e.code
        except (urllib.error.URLError, OSError, ValueError) as e:
            err = str(e)[:100]
        print("retry", model, err, file=sys.stderr, flush=True)
        time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(err)


def drain(todo, work, path):
    """Run work over todo on 16 threads, appending each result to path, until done or BUDGET runs out."""
    t0, left, expired = time.time(), 0, []

    def one(item):
        if expired or time.time() - t0 > BUDGET:
            return None
        try:
            return work(item)
        except Expired:
            expired.append(item)
        except Exception as e:  # one failed item is retried on the next run; the others still land
            print("failed", item, repr(e)[:200], file=sys.stderr, flush=True)
        return None

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f, cf.ThreadPoolExecutor(16) as ex:
        for fu in cf.as_completed([ex.submit(one, x) for x in todo]):
            rec = fu.result()
            if rec is None:
                left += 1
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
    print("%d done, %d left%s" % (len(todo) - left, left, ", token expired" if expired else ""), flush=True)
    sys.exit(3 if left else 0)


def load(path):
    return [json.loads(line) for line in open(path)] if os.path.exists(path) else []


def generate():
    have = {(r["queue"], r["first"] + k) for r in load(GENERATED) for k in range(len(r["tickets"]))}
    todo = []  # (queue, first, count): runs of missing tickets, at most BATCH per call
    for q in QUEUES:
        for i in range(PER_QUEUE):
            if (q, i) in have:
                continue
            if todo and todo[-1][0] == q and todo[-1][1] + todo[-1][2] == i and todo[-1][2] < BATCH:
                todo[-1] = (q, todo[-1][1], todo[-1][2] + 1)
            else:
                todo.append((q, i, 1))

    def work(item):
        q, i, n = item
        specs = [spec(q, j) for j in range(i, i + n)]
        msgs = [{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": gen_prompt(q, specs)}]
        for _ in range(3):
            content, served = chat(GEN_MODEL, msgs, 1.0, 32000)
            a, b = content.find("["), content.rfind("]")
            try:
                ts = json.loads(content[a:b + 1])
            except ValueError:
                continue
            if len(ts) == n and all(isinstance(t, dict) and isinstance(t.get("subject"), str)
                                        and isinstance(t.get("body"), str) and t["body"].strip() for t in ts):
                tickets = [{"subject": t["subject"].strip() if s["subject"] else "", "body": t["body"].strip()}
                           for t, s in zip(ts, specs)]
                return {"queue": q, "first": i, "specs": specs, "model": GEN_MODEL, "served": served,
                        "temperature": 1.0, "messages": msgs, "content": content, "tickets": tickets}
        raise ValueError("no parseable batch")

    drain(todo, work, GENERATED)


def tickets():
    """Every generated ticket: (id, queue, spec, ticket), by queue then index."""
    return [("%s/%d" % (r["queue"], r["first"] + k), r["queue"], s, t)
            for r in sorted(load(GENERATED), key=lambda r: (list(QUEUES).index(r["queue"]), r["first"]))
            for k, (s, t) in enumerate(zip(r["specs"], r["tickets"]))]


def check():
    done = {r["id"] for r in load(CHECKED)}
    todo = [x for x in tickets() if x[0] not in done]

    def work(item):
        tid, _, _, t = item
        answer, served = chat(CHECK_MODEL, [{"role": "system", "content": CHECK_SYSTEM},
                                            {"role": "user", "content": check_prompt(t)}], 0.0, 4000)
        return {"id": tid, "model": CHECK_MODEL, "served": served, "answer": answer, "pick": pick(answer)}

    drain(todo, work, CHECKED)


def support():
    rng = random.Random(SEED)
    picks = {r["id"]: r["pick"] for r in load(CHECKED)}
    all_ = tickets()
    missing = [x[0] for x in all_ if x[0] not in picks]
    if missing:
        raise SystemExit("%d tickets unchecked; run check" % len(missing))
    agree = [x for x in all_ if picks[x[0]] == x[1]]
    hard = [x for x in all_ if "near" in x[2]]
    label = {"generated": len(all_), "agreed": len(agree), "rate": round(len(agree) / len(all_), 4),
             "boundary cases": len(hard), "boundary agreed": sum(1 for x in hard if picks[x[0]] == x[1]),
             "per queue": {q: "%d/%d" % (sum(1 for x in agree if x[1] == q), sum(1 for x in all_ if x[1] == q))
                           for q in QUEUES}}
    tobi = [r["subject"] + "\n" + r["body"].replace("\\n", "\n") for f in TOBI_FILES for r in rows_csv(fetch(TOBI, f))]
    refs = {TOBI[0]: tobi,
            "frozen app.support_triage": [st["subject"] + "\n" + st["body"] for st in frozen("app.support_triage")]}
    keep, counts = dedup([t["subject"] + "\n" + t["body"] for _, _, _, t in agree], refs)
    rows = []
    for q in QUEUES:
        got = [t for (_, qq, _, t), k in zip(agree, keep) if qq == q and k]
        rng.shuffle(got)
        if len(got) < KEEP:
            raise SystemExit("%s: %d of %d survive; raise PER_QUEUE and generate" % (q, len(got), KEEP))
        rows += [[{"subject": t["subject"], "body": t["body"][:CAP]}, copy.deepcopy(SUPPORT),
                  {"queue": {"idx": list(QUEUES).index(q)}}] for t in got[:KEEP]]
    rng.shuffle(rows)
    return rows, {"label check": label, "dedup": counts}


def build():
    ph, ph_report = phishing()
    su, su_report = support()
    out = {"held.phishing": ph, "held.support_triage": su}
    for name, data in (("states.json.gz", out),
                       ("questions.json.gz", {n: [[g, qs] for _, qs, g in rows] for n, rows in out.items()})):
        with open(os.path.join(HERE, name), "wb") as f:  # mtime 0: the same suites give the same bytes
            f.write(gzip.compress(json.dumps(data, ensure_ascii=False).encode("utf-8"), mtime=0))
    report = {"held.phishing": dict(ph_report, balance=dict(collections.Counter(
                  "phishing" if g["is_phishing"]["idx"] else "legitimate" for _, _, g in ph))),
              "held.support_triage": su_report}
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    {"generate": generate, "check": check, "build": build}[sys.argv[1]]()
