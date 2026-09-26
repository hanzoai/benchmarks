"""The capability suites' case format, backends, scoring and result keys.

A case file is the harness's states format, {suite: [[state, questions, gold], ...]}, gold
{qid: {"idx": i}}: what `bench preds` reads. A backend answers it with preds
{suite: {"p": {"ci/qid": [p, ...] | None}, ...}}, one probability vector per question in the
harness's option order (three_way.order); None is a question the backend did not answer, counted
by merge.score as unanswered, never dropped. Results are flat keys cap/<suite>/<who>/<metric>.

    laya  Laya 0.3.20 on hanzoai/kai-1@b50502c2 (= convaiinnovations/laya@55cf4c4e), each case
          answered by the checkpoint laya's Router picks: the frozen harness's Laya.
    jev   typesafe/jev-1.13 through OpenRouter's Decisions API; spend is ledgered and capped.
    kai   a Kai checkpoint through Kai's native runtime (`bench`, hanzoai/decision).
"""
import concurrent.futures as cf
import gzip
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "..", "harness")
CASES = os.path.join(HERE, "cases")
RESULTS = os.environ.get("CAP_RESULTS") or os.path.join(HERE, "results")  # a smoke run writes elsewhere
LEDGER = os.path.join(HERE, "results", "jev_spend.json")  # every Jev call, smoke runs included
DATA = os.path.join(HERE, "data")
SCRATCH = os.path.expanduser(os.environ.get("CAP_SCRATCH", "~/scratch/capability"))
os.environ.setdefault("LAYA_SRC", os.path.join(SCRATCH, "laya"))
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, HARNESS)
sys.dont_write_bytecode = True
import merge  # noqa: E402  frozen: the harness's metric code

BUNDLE, REV = "hanzoai/kai-1", "b50502c28537df49a3621f6fa543f9e8521e8a9c"


def order(qdef):
    """three_way.order: the harness's option order, what a probability vector is indexed by."""
    t, c = qdef["type"], qdef.get("criteria")
    if t == "noul":
        return ["false", "true"]
    if t == "score":
        return [str(i) for i in range(len(c))]
    return list(c.keys()) if isinstance(c, dict) else list(c)


# ------------------------------------------------------------------ files
def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "wt") as f:
        json.dump(obj, f, ensure_ascii=False)


def load(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt") as f:
        return json.load(f)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def host():
    return {"host": platform.node(), "machine": platform.machine(), "python": platform.python_version(),
            "load": [round(x, 1) for x in os.getloadavg()], "at": time.strftime("%Y-%m-%d %H:%M:%S %z")}


def trim(S):
    """The first CAP_N cases of each suite, for a smoke run (with CAP_RESULTS set elsewhere)."""
    n = int(os.environ.get("CAP_N") or 0)
    return {k: v[:n] for k, v in S.items()} if n else S


def pct(v, q):
    """Nearest-rank percentile, as bench speed computes it."""
    v = sorted(v)
    return float(v[min(len(v), max(1, int(np.ceil(q / 100 * len(v))))) - 1]) if v else None


# ------------------------------------------------------------------ scoring
def score(rows, p):
    """merge.score over a suite's rows and a backend's {"ci/qid": vector}."""
    return merge.score([[g, qs] for _, qs, g in rows], p, typed=False)


def ranks(rows, p, ks=(1, 5, 20)):
    """recall@k of the gold option in each answered vector's ranking, over all questions."""
    hit, n = {k: 0 for k in ks}, 0
    for ci, (_, qs, g) in enumerate(rows):
        for qid in qs:
            n += 1
            v = p.get("%d/%s" % (ci, qid))
            if v is None:
                continue
            v = np.asarray(v, float)
            r = int((v > v[g[qid]["idx"]]).sum())  # options strictly above gold; ties favour gold
            for k in ks:
                hit[k] += r < k
    return {"recall%d" % k: round(hit[k] / n, 4) for k in ks} if n else {}


class Keys(dict):
    """cap/<suite>/<who>/<metric> -> value. A value no run produced is never written."""

    def __init__(self, suite):
        super().__init__()
        self.suite = suite

    def put(self, who, metric, v):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return
        self["cap/%s/%s/%s" % (self.suite, who, metric)] = round(float(v), 4) \
            if isinstance(v, (float, np.floating)) else v

    def metrics(self, who, prefix, m, fields=("accuracy", "macro_f1", "ece", "brier", "nll", "unanswered",
                                             "questions", "zero_prob", "recall1", "recall5", "recall20")):
        for f in fields:
            if f in m:
                self.put(who, prefix + f.replace("_", ""), m[f])


def save(suite, keys, detail, meta=None):
    """Merge a run into results/<suite>.json: its keys replace every earlier key of the same
    backend and condition (cap/<suite>/<who>/<condition>.), so a run of one backend or one
    condition leaves the others' results in place; detail and meta merge at the top level."""
    path = os.path.join(RESULTS, suite + ".json")
    old = load(path) if os.path.exists(path) else {"keys": {}, "detail": {}, "meta": {}}
    owned = {k.rsplit("/", 1)[0] + "/" + k.rsplit("/", 1)[1].split(".")[0] for k in keys}
    kept = {k: v for k, v in old["keys"].items()
            if k.rsplit("/", 1)[0] + "/" + k.rsplit("/", 1)[1].split(".")[0] not in owned}
    run = dict(host(), **(meta or {}))
    out = {"meta": dict(old["meta"], **{"run " + run["at"]: run}), "keys": dict(sorted({**kept, **keys}.items())),
           "detail": merged(old["detail"], detail)}
    dump(out, path)
    print("wrote %s  %d keys (%d new)" % (path, len(out["keys"]), len(keys)), flush=True)
    return out


def merged(a, b):
    """b over a, recursively for dicts."""
    out = dict(a)
    for k, v in b.items():
        out[k] = merged(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return out


# ------------------------------------------------------------------ laya
class Laya:
    """The kai-1 checkpoints under the Laya 0.3.20 reference runtime, routed per case."""

    SUB = {"english": None, "multilingual": "multilingual", "typed-decisions": "typed-decisions"}

    def __init__(self, device=None):
        import importlib.util

        import laya
        import torch
        from huggingface_hub import snapshot_download
        from laya.router import Router

        spec = importlib.util.spec_from_file_location(
            "bl", os.path.join(os.environ["LAYA_SRC"], "research/scripts/bench_local.py"))
        self.bl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bl)
        self.laya, self.torch = laya, torch
        self.device = device or os.environ.get("LAYA_DEVICE") or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.local = snapshot_download(BUNDLE, revision=REV)
        self.router, self.agents = Router(), {}
        self.meta = {"runtime": "laya " + laya.__version__, "bundle": BUNDLE, "revision": REV,
                     "device": self.device, "dtype": "f32", "torch": torch.__version__}

    def agent(self, m):
        if m not in self.agents:
            ag = self.laya.load(self.local, device=self.device, subfolder=self.SUB[m])
            ag.model.eval()
            self.agents[m] = ag
        return self.agents[m]

    def route(self, state, qs):
        return self.router.route(state, qs).model

    def preds(self, rows, model=None, tag=""):
        """Every question of `rows`, each case on its routed checkpoint (or `model`), through the
        harness's engine (bench_local.score_cases: one sequence per question, batched)."""
        by = {}
        for ci, (st, qs, _) in enumerate(rows):
            by.setdefault(model or self.route(st, qs), []).append(ci)
        p, secs, dropped, route = {}, 0.0, 0, {}
        for m, cis in by.items():
            ag = self.agent(m)
            lgs, idx, s, d = self.bl.score_cases(ag, [(rows[ci][0], rows[ci][1]) for ci in cis], tag=tag)
            secs, dropped = secs + s, dropped + d
            for (j, qid, qt, k), z in zip(idx, lgs):
                p["%d/%s" % (cis[j], qid)] = None if z is None else \
                    [float(x) for x in self.bl.softmax_t(z, self.bl.temp_for(ag, qt, k))]
            for ci in cis:
                route[ci] = m
        return {"p": p, "seconds": round(secs, 3), "dropped": dropped,
                "route": [route[ci] for ci in range(len(rows))]}

    def fit(self, rows, model=None):
        """How each question fits the checkpoint's layout (common.build_sequence): rejected (an
        option marker fell past max_len, so the harness drops the question), options cut (the
        head_max_len budget or the 48-token cap shortened an option), state cut (the state lost
        tokens to max_len). Counts over all questions."""
        from laya.common import serialize_state
        n = rej = ocut = scut = 0
        seen = {}
        for st, qs, _ in rows:
            ag = self.agent(model or self.route(st, qs))
            tok, L, H = ag.tok, ag.cfg.get("max_len", 512), ag.cfg.get("head_max_len", 192)
            s_len = len(tok(serialize_state(st), add_special_tokens=False)["input_ids"])
            for qdef in qs.values():
                n += 1
                q = self.bl.to_internal(qdef)
                opts = self.bl.render_options(q)
                miss = [o for o in opts if o not in seen]
                if miss:
                    enc = tok([" " + o for o in miss], add_special_tokens=False)["input_ids"]
                    seen.update({o: 1 + len(e) for o, e in zip(miss, enc)})
                full = [seen[o] for o in opts]
                cap = [min(f, 49) for f in full]
                per = max(4, (H - 16) // max(1, len(cap))) if H - sum(cap) < 16 else 49
                kept = [min(c, per) for c in cap]
                head = len(tok("%s question: %s" % (q["t"], q["ins"]), add_special_tokens=False)["input_ids"])
                head = min(head, max(8, H - sum(kept)))
                used = 1 + head + 1 + sum(kept) + 1
                marks = [1 + head + 1 + sum(kept[:i]) for i in range(len(kept))]
                if any(m >= L for m in marks):
                    rej += 1
                    continue
                ocut += any(k < f for k, f in zip(kept, full))
                scut += s_len > max(0, L - used - 1)
        return {"questions": n, "rejected": rej, "options_cut": ocut, "state_cut": scut}

    def call(self, state, qs, model=None):
        """One product call (Agent.system_one) timed end to end: ms, answers."""
        ag = self.agent(model or self.route(state, qs))
        t = time.perf_counter()
        r = ag.system_one(state, qs)
        return 1e3 * (time.perf_counter() - t), r


# ------------------------------------------------------------------ jev
class Jev:
    """typesafe/jev-1.13 through OpenRouter's Decisions API, as three_way.jev_call sends it, with
    every call's cost added to a ledger and refused once the cap would be passed."""

    MODEL, URL = "typesafe/jev-1.13", "https://openrouter.ai/api/alpha/decisions"
    PRICE = 0.042e-6  # USD per input token, OpenRouter's listing for typesafe/jev-1.13
    CAP = float(os.environ.get("JEV_CAP_USD", "5"))
    LEDGER = LEDGER

    def __init__(self):
        path = os.path.expanduser(os.environ.get("OR_KEY_FILE", os.path.join(SCRATCH, ".or_key")))
        self.key = open(path).read().strip() if os.path.exists(path) else None
        self.lock = threading.Lock()
        self.held = 0.0
        self.meta = {"model": self.MODEL, "url": self.URL, "price_per_input_token": self.PRICE}

    @staticmethod
    def body(state, qs):
        qs = json.loads(json.dumps(qs))
        for q in qs.values():  # the harness allows a bare label; the wire wants a description
            c = q.get("criteria")
            if isinstance(c, dict):
                q["criteria"] = {k: (v if isinstance(v, str) and v else k) for k, v in c.items()}
        return json.dumps({"model": Jev.MODEL, "state": state, "questions": qs}).encode()

    def book(self, f):
        """Apply f to the ledger on disk under an exclusive file lock, so every process that
        calls Jev adds to one ledger; returns f's result."""
        import fcntl
        os.makedirs(os.path.dirname(self.LEDGER), exist_ok=True)
        with self.lock, open(self.LEDGER + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            led = load(self.LEDGER) if os.path.exists(self.LEDGER) else \
                {"cap_usd": self.CAP, "spent_usd": 0.0, "calls": 0, "refused": 0, "by_suite": {}}
            out = f(led)
            with open(self.LEDGER + ".tmp", "w") as w:
                json.dump(led, w)
            os.replace(self.LEDGER + ".tmp", self.LEDGER)
            return out

    def spend(self, suite, usd, n=1):
        def add(led):
            led["spent_usd"] = round(led["spent_usd"] + usd, 6)
            led["calls"] += n
            s = led["by_suite"].setdefault(suite, {"usd": 0.0, "calls": 0})
            s["usd"], s["calls"] = round(s["usd"] + usd, 6), s["calls"] + n
        self.book(add)

    def call(self, state, qs, suite, timeout=120, tries=8):
        """(response, ms, error). The error names why a question has no answer."""
        if not self.key:
            return None, 0.0, "no key"
        body = self.body(state, qs)
        est = len(body) / 3 * self.PRICE  # tokens <= bytes / 3 on this wire, so a ceiling

        def room(led):
            if led["spent_usd"] + self.held + est > self.CAP:
                led["refused"] += 1
                return False
            return True

        if not self.book(room):
            return None, 0.0, "spend cap"
        with self.lock:
            self.held += est
        err = "retries exhausted"
        try:
            for attempt in range(tries):
                req = urllib.request.Request(self.URL, data=body, headers={
                    "Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
                t = time.perf_counter()
                try:
                    d = json.load(urllib.request.urlopen(req, timeout=timeout))
                    ms = 1e3 * (time.perf_counter() - t)
                    self.spend(suite, float((d.get("usage") or {}).get("cost") or 0))
                    return d, ms, None
                except urllib.error.HTTPError as e:
                    msg = e.read()[:300].decode("utf-8", "replace")
                    if e.code in (429, 500, 502, 503, 504):
                        err = "HTTP %d %s" % (e.code, msg)
                        time.sleep(min(60, 2 ** attempt))
                        continue
                    return None, 1e3 * (time.perf_counter() - t), "HTTP %d %s" % (e.code, msg)
                except Exception as e:  # network, timeout
                    err = type(e).__name__ + ": " + str(e)[:200]
                    time.sleep(min(60, 2 ** attempt))
            return None, 0.0, "gave up: " + err
        finally:
            with self.lock:
                self.held -= est

    @staticmethod
    def vector(qdef, a):
        """three_way.vector: an answer as a probability vector in harness order."""
        keys, t = order(qdef), qdef["type"]
        if not a:
            return None
        if t == "noul":
            p = float(a.get("noul", 0.5))
            return [1 - p, p]
        probs = a.get("probabilities") or {}
        v = [float(probs.get(k, 0.0)) for k in keys]
        if sum(v) <= 0:
            pick = a.get("choice") if t == "choice" else None
            if pick in keys:
                v = [1.0 if k == pick else 0.0 for k in keys]
            elif t == "score" and a.get("score") is not None:
                i = min(len(keys) - 1, max(0, int(round(float(a["score"])))))
                v = [1.0 if j == i else 0.0 for j in range(len(keys))]
            else:
                return None
        s = sum(v)
        return [x / s for x in v]

    def preds(self, rows, suite, workers=8):
        """Every case of `rows` as one call, `workers` at a time."""
        p, ms, errors, served, cost, tin = {}, [], [], {}, 0.0, 0

        def one(ci):
            st, qs, _ = rows[ci]
            return ci, self.call(st, qs, suite)

        with cf.ThreadPoolExecutor(workers) as ex:
            for ci, (d, t, err) in ex.map(one, range(len(rows))):
                qs = rows[ci][1]
                if err:
                    errors.append("%d: %s" % (ci, err))
                    p.update({"%d/%s" % (ci, qid): None for qid in qs})
                    continue
                ms.append(t)
                served[d.get("model")] = served.get(d.get("model"), 0) + 1
                u = d.get("usage") or {}
                cost += float(u.get("cost") or 0)
                tin += int(u.get("input_tokens") or 0)
                for qid, q in qs.items():
                    p["%d/%s" % (ci, qid)] = self.vector(q, (d.get("answers") or {}).get(qid))
        return {"p": p, "latency_ms": sorted(ms), "errors": errors[:50], "n_errors": len(errors),
                "error_kinds": kinds(errors), "served": served, "cost_usd": round(cost, 6), "input_tokens": tin}


def kinds(errors):
    """Errors grouped by their first words: 'HTTP 400', 'spend cap', 'gave up', ..."""
    out = {}
    for e in errors:
        k = " ".join(e.split(": ", 1)[1].split()[:2])
        out[k] = out.get(k, 0) + 1
    return out


# ------------------------------------------------------------------ kai
class Pending(Exception):
    """A result that needs something not yet built; the reason is recorded, never a number."""


class Kai:
    """A Kai checkpoint (a directory or owner/name[@rev]) through Kai's native runtime, the
    `bench` binary of hanzoai/decision: `bench preds` answers a case file."""

    def __init__(self, model):
        self.model = model
        self.bin = os.path.expanduser(os.environ.get("KAI_BENCH", "bench"))
        self.meta = {"checkpoint": model, "bench": self.bin}
        if os.path.exists(self.bin):
            self.meta["bench_sha256"] = sha(self.bin)

    def run(self, *args, timeout=None):
        if not os.path.exists(self.bin):
            raise Pending("no Kai runtime at %s (KAI_BENCH; rx cargo build --release -p bench --features metal)"
                          % self.bin)
        r = subprocess.run([self.bin, *args], capture_output=True, text=True, timeout=timeout)
        self.meta.setdefault("calls", []).append({"args": list(args), "stderr": r.stderr[-2000:]})
        if r.returncode:
            err = (r.stderr or r.stdout).strip().splitlines()
            raise Pending("bench %s: %s" % (args[0], err[-1] if err else "exit %d" % r.returncode))
        return r

    def preds(self, cases_path, out):
        """{suite: {"p": ..., "seconds": ...}} for every suite of the case file."""
        self.run("preds", "--model", self.model, "--states", cases_path, "--out", out)
        d = load(out)
        self.meta.update({k: d[k] for k in ("weights", "device", "dtype") if k in d})
        return d["suites"]


def backends(which, kai=None):
    """{who: backend} for the requested backends; Kai only with a checkpoint."""
    make = {"laya": Laya, "jev": Jev, "kai": lambda: Kai(kai)}
    return {w: make[w]() for w in which if w != "kai" or kai}
