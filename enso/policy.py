"""The study's conditions: what each one picks for a task.

B0  Zen-only: the primary tier at the default budget, full context and tools (today).
B1  static router: zen-svc's own request-shape rules (escalate.go isHardTask, classifyTask,
    wantsShortAnswer) as a tier and budget: hard -> large/deep, code -> medium/medium,
    short answer -> small/none, else medium/short.
R1  Zen-as-router: the smallest served tier is asked for {"tier", "budget"} as JSON; its own
    request is charged to the task.
K1  Kai router.model picks the tier.            K2  + reasoning.budget picks the level.
K3  + context.select keeps the top-k chunks.     K4  + tools.select keeps the top-k tools.
K5  + agent.complete / agent.progress: after an answer, stop when `done` holds, else retry one
    level deeper, or one tier up when progress is stalled or looping (at most 3 attempts).

B0, B1, R1, K1 and K2 change only (tier, level): their cells are looked up in the grid. K3, K4
and K5 change the prompt or the loop, so they run online. A tier label maps to the primary
served tier of that label, else the cheapest served tier at or above it, else the largest.
Every Kai call runs mode "enforced"; a result that comes back shadow (its calibration is not
the program's pin) is not applied, and the condition falls back to B0's choice for that op.
"""
import json
import re

import kai as K
from work import messages

CODE = re.compile(r"(?i)\b(write|implement|fix|debug|refactor|rewrite|optimi[sz]e)\b[^.?!\n]{0,60}\b"
                  r"(function|method|code|program|script|algorithm|class|module|endpoint|api|query|bug|regex|compiler?)\b")
MCQ = re.compile(r"(?m)(?:^|[\s(\[])\(?([A-Ea-e])[).]\s")
HARD = 4000
ROUTER = ("You route requests to models. Tiers: small (lookup, formatting, short answers), medium "
          "(ordinary code, summaries, one-step reasoning), large (multi-step reasoning, non-trivial "
          "code, long context), frontier (the hardest problems). Budgets: none, short, medium, deep. "
          "Pick the cheapest tier and the smallest budget that will answer correctly. Reply with only "
          'JSON: {"tier": "...", "budget": "..."}.')


def tokens(msgs):
    """zen-svc's estimate: each message's JSON bytes / 4."""
    return sum(len(json.dumps(m, separators=(",", ":"), ensure_ascii=False).encode()) // 4 for m in msgs)


class Tiers:
    def __init__(self, spec, primary=None):
        self.labels, self.levels, self.default = spec["labels"], spec["levels"], spec["default"]
        self.served = [t for t in spec["tiers"] if t.get("served")]
        self.by = {t["id"]: t for t in spec["tiers"]}
        prim = primary or next((t["id"] for t in self.served if t.get("primary")), None)
        self.primary = self.by[prim] if prim else max(self.served, key=self.rank)

    def rank(self, t):
        return self.labels.index(t["label"])

    def pick(self, label):
        r = self.labels.index(label)
        if self.primary["label"] == label:
            return self.primary
        up = [t for t in self.served if self.rank(t) >= r]
        if up:
            return min(up, key=lambda t: (self.rank(t), t.get("usd_per_gpu_hour", 0)))
        top = max(map(self.rank, self.served))
        if self.rank(self.primary) == top:
            return self.primary
        return min((t for t in self.served if self.rank(t) == top), key=lambda t: t.get("usd_per_gpu_hour", 0))

    def smallest(self):
        return min(self.served, key=lambda t: (self.rank(t), t.get("usd_per_gpu_hour", 0)))

    def up(self, t):
        """The next served tier above t's label, or t."""
        higher = [x for x in self.served if self.rank(x) > self.rank(t)]
        return min(higher, key=lambda x: (self.rank(x), x.get("usd_per_gpu_hour", 0))) if higher else t


def b0(t, tiers):
    return tiers.primary["id"], tiers.default


def b1(t, tiers):
    msgs = messages(t)
    req = t["request"]
    if tokens(msgs) >= HARD:
        label, level = "large", "deep"
    elif "```" in req or CODE.search(req):
        label, level = "medium", "medium"
    elif len({m.lower() for m in MCQ.findall(req)}) >= 2 or (0 < len(req.strip()) <= 400 and "?" in req):
        label, level = "small", "none"
    else:
        label, level = "medium", "short"
    return tiers.pick(label)["id"], level


def r1(t, tiers, cap, run):
    """(pick, router row): the smallest tier routes. `run(task, tier, level, cap)` is grid.run."""
    router = {"id": t["id"] + "/router", "family": "router", "system": ROUTER, "request": t["request"][:4000],
              "chunks": [], "tools": [], "steps": [], "check": {"type": "exact", "answer": ""}, "optimum": {}}
    row = run(router, tiers.smallest(), "none", cap, variant="router")
    text = row.pop("_content", "")
    m = re.search(r"\{.*?\}", text, re.S)
    label, level = "medium", "short"
    if m:
        try:
            o = json.loads(m.group(0))
            label = o.get("tier") if o.get("tier") in tiers.labels else label
            level = o.get("budget") if o.get("budget") in tiers.levels else level
        except ValueError:
            pass
    row["success"] = True
    return (tiers.pick(label)["id"], level), row


def route(t):
    msgs = messages(t)
    return K.route(msgs, t["tools"], tokens(msgs))


def k1(t, tiers, kai):
    r = kai.decide("router.model@1", [route(t)], mode="enforced")
    label = K.act(r["results"][0], "tier")
    return (tiers.pick(label)["id"] if label else tiers.primary["id"]), r


def k2(t, tiers, kai):
    r = kai.decide("reasoning.budget@1", [route(t)], mode="enforced")
    a = K.act(r["results"][0], "budget")
    return (K.LEVELS[int(a)] if a is not None else tiers.default), r


def select(kai, program, states, k):
    """Kept indices, or None (keep all) unless every result is enforced."""
    if not states:
        return None, None
    r = kai.decide(program, states, mode="enforced", k=k)
    if any(x.get("error") or x.get("mode") != "enforced" for x in r["results"]):
        return None, r
    return sorted(r.get("selected") or []), r


def k3(t, kai, k):
    return select(kai, "context.select@1", [K.chunk(t["request"], c["text"], c["source"]) for c in t["chunks"]], k)


def k4(t, kai, k):
    return select(kai, "tools.select@1", [K.tool(t["request"], x) for x in t["tools"]], k)


def done(t, answer, kai):
    r = kai.decide("agent.complete@1", [K.complete(t["request"], answer)], mode="enforced")
    return K.act(r["results"][0], "done") == "true", r


def stuck(t, steps, kai):
    r = kai.decide("agent.progress@1", [K.progress(t["request"], steps)], mode="enforced")
    return K.act(r["results"][0], "status") in ("stalled", "looping"), r
