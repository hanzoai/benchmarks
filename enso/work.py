"""Workloads: tasks with a checkable answer, as data.

    python work.py build <dir> [--n synthetic=200,gsm8k=200,mbpp=100,bfcl=100,trace=200] [--traces <path>...]

A task is a dict: id, family, system, request, chunks (context candidates, rendered as numbered
documents), tools (rendered into the system turn), steps (prior agent steps), check (how an
answer is scored) and optimum (the known best action, where one is known by construction).
`messages(task, chunks, tools)` renders it as OpenAI messages, keeping only the chunk and tool
indices given; `score(task, text)` is success.

Families: arith and logic (graded-depth chains, exact answers, optimum = depth), needle (one
relevant chunk among N, optimum = its index), tool (one needed tool among N, optimum = its
name), gsm8k, mbpp (tests run in a sandbox: temp dir, rlimits, no network), bfcl (BFCL v3
"multiple": one gold call among 2-4 functions) and trace (the next action of a recorded agent
session, scrubbed; success is agreement with the recorded action: a proxy).
"""
import glob
import json
import os
import random
import re
import subprocess
import sys
import tempfile

from scrub import deep, scrub

SEED = 13
GSM8K = ("openai/gsm8k", "a05f38c23a0e9ab0b71de8a2b4947e20f74f68f7", "main/test/0000.parquet")
MBPP = ("google-research-datasets/mbpp", "f7f18be5a72d664e3884261303eb5b7f01dd10c2", "sanitized/test/0000.parquet")
BFCL = ("gorilla-llm/Berkeley-Function-Calling-Leaderboard", "61fc0608cfd831fcfbbaa676ebdfef0ed963eeda",
        "BFCL_v3_multiple.json", "possible_answer/BFCL_v3_multiple.json")
ZEN = ("zenlm/zen-agentic-dataset-private", "3753d88b97e3e56263b0ed25a5c045642a602606",
       "data/hanzo-dev/training/conversations_001.jsonl")
CALL = ('To use a tool, reply with only one JSON object: {"tool": "<name>", "arguments": {...}}.')
PLAIN = "You are a helpful assistant. Answer the request."


# ---- synthetic -------------------------------------------------------------------------------

def arith(rng, depth, i):
    x = rng.randint(2, 9)
    lines = [f"Let x0 = {x}."]
    for k in range(1, depth + 1):
        a, b = rng.randint(2, 9), rng.randint(1, 20)
        op = rng.choice("+-*")
        x = x * a + b if op == "*" else (x + a * b if op == "+" else x - b)
        lines.append({"*": f"x{k} = x{k-1} * {a} + {b}.", "+": f"x{k} = x{k-1} + {a} * {b}.",
                      "-": f"x{k} = x{k-1} - {b}."}[op])
    req = " ".join(lines) + f" What is x{depth}? End with 'ANSWER: <integer>'."
    return task(f"arith/d{depth}/{i}", "arith", req, check={"type": "int", "answer": x},
                optimum={"depth": depth})


NAMES = ["Ada", "Bo", "Cy", "Dee", "Eli", "Fay", "Gus", "Hal", "Ivy", "Jo", "Kit", "Lu", "Mo",
         "Ned", "Oz", "Pia", "Quin", "Rex", "Sy", "Tam"]


def logic(rng, depth, i):
    people = rng.sample(NAMES, depth + 1)  # people[0] is tallest
    facts = [f"{people[k]} is taller than {people[k + 1]}." for k in range(depth)]
    rng.shuffle(facts)
    req = " ".join(facts) + " Who is the tallest? End with 'ANSWER: <name>'."
    return task(f"logic/d{depth}/{i}", "logic", req, check={"type": "exact", "answer": people[0]},
                optimum={"depth": depth})


WORDS = ("system report budget quarter vendor module sensor latency region cluster review policy "
         "schedule migration audit ledger backlog release metric incident storage network design "
         "contract pipeline forecast inventory license").split()


def filler(rng, n):
    out = []
    for _ in range(n):
        w = rng.sample(WORDS, 8)
        out.append(f"The {w[0]} {w[1]} for the {w[2]} {w[3]} was {w[4]} after the {w[5]} {w[6]} {w[7]}.")
    return " ".join(out)


def needle(rng, n, i):
    projects = [f"{rng.choice(NAMES)}-{rng.randint(100, 999)}" for _ in range(n)]
    codes = [f"{rng.choice('BCDFGHJKLMNPRSTVWXZ')}{rng.randint(1000, 9999)}" for _ in range(n)]
    chunks = [{"text": f"Project {p}. {filler(rng, 6)} The access code of project {p} is {c}. {filler(rng, 6)}",
               "source": "document"} for p, c in zip(projects, codes)]
    k = rng.randrange(n)
    req = f"What is the access code of project {projects[k]}? End with 'ANSWER: <code>'."
    return task(f"needle/n{n}/{i}", "needle", req, chunks=chunks,
                check={"type": "exact", "answer": codes[k]}, optimum={"chunk": k})


TOOLS = [
    ("get_weather", "Current weather or forecast for a city.", "city", "What will the weather be in {x} tomorrow?", ["Paris", "Lagos", "Osaka", "Lima"]),
    ("get_stock_price", "Latest trading price of a stock ticker.", "ticker", "What is {x} trading at right now?", ["NVDA", "AAPL", "TSM", "ASML"]),
    ("send_email", "Send an email to an address.", "to", "Email {x} that the meeting moved to 3pm.", ["ops@example.com", "hr@example.com"]),
    ("create_event", "Add an event to the calendar.", "title", "Put '{x}' on my calendar for Friday at 10.", ["Design review", "1:1 with Jo"]),
    ("search_web", "Search the web for pages.", "query", "Find recent articles about {x}.", ["solid-state batteries", "RISC-V servers"]),
    ("convert_currency", "Convert an amount between currencies.", "amount", "How much is {x} US dollars in euros?", ["250", "1200"]),
    ("translate_text", "Translate text into another language.", "text", "Translate '{x}' into Japanese.", ["good morning", "thank you"]),
    ("get_directions", "Route between two places.", "destination", "How do I drive to {x} from here?", ["the airport", "Union Station"]),
    ("set_timer", "Start a countdown timer.", "minutes", "Set a timer for {x} minutes.", ["12", "45"]),
    ("lookup_order", "Status of a customer order by id.", "order_id", "Where is my order {x}?", ["A-1042", "Z-77"]),
    ("run_sql", "Run a read-only SQL query on the analytics database.", "query", "How many users signed up last week? Query the {x} table.", ["users", "signups"]),
    ("read_file", "Read a file from the workspace.", "path", "Show me what is in {x}.", ["config.yaml", "src/main.rs"]),
    ("list_directory", "List a directory in the workspace.", "path", "What files are in {x}?", ["src/", "docs/"]),
    ("resize_image", "Resize an image file.", "width", "Make logo.png {x} pixels wide.", ["512", "128"]),
    ("book_flight", "Book a flight.", "destination", "Book me a flight to {x} next Monday.", ["Berlin", "Denver"]),
    ("get_news", "Top headlines for a topic.", "topic", "Any headlines about {x} today?", ["elections", "the Fed"]),
]


def tool(rng, n, i):
    picked = rng.sample(TOOLS, n)
    k = rng.randrange(n)
    name, _, arg, q, xs = picked[k]
    x = rng.choice(xs)
    tools = [{"name": t[0], "description": t[1],
              "parameters": {"type": "object", "properties": {t[2]: {"type": "string"}}, "required": [t[2]]}}
             for t in picked]
    return task(f"tool/n{n}/{i}", "tool", q.format(x=x), tools=tools,
                check={"type": "call", "name": name, "contains": x}, optimum={"tool": name})


def synthetic(n, rng):
    """n tasks: 30% arith, 20% logic, 25% needle, 25% tool, depths and sizes graded."""
    out = []
    plan = [(arith, [1, 2, 4, 8, 16], 0.30), (logic, [2, 4, 8, 16], 0.20),
            (needle, [4, 8, 16], 0.25), (tool, [4, 8, 16], 0.25)]
    for f, grades, share in plan:
        m = max(1, round(n * share))
        for i in range(m):
            out.append(f(rng, grades[i % len(grades)], i))
    return out


# ---- public ----------------------------------------------------------------------------------

def hub(repo, rev, path):
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo, path, repo_type="dataset", revision=rev)


def parquet(repo, rev, path):
    import pyarrow.parquet as pq
    return pq.read_table(hub(repo, rev, path)).to_pylist()


def gsm8k(n, rng):
    rows = parquet(*GSM8K)
    rng.shuffle(rows)
    return [task(f"gsm8k/{i}", "gsm8k", r["question"] + " End with 'ANSWER: <number>'.",
                 check={"type": "int", "answer": int(r["answer"].split("####")[-1].strip().replace(",", ""))})
            for i, r in enumerate(rows[:n])]


def mbpp(n, rng):
    rows = parquet(*MBPP)
    rng.shuffle(rows)
    out = []
    for r in rows[:n]:
        tests = "\n".join(r["test_list"])
        req = (f"{r['prompt']}\nYour code should pass these tests:\n{tests}\n"
               "Reply with only the Python code in one ```python block.")
        out.append(task(f"mbpp/{r['task_id']}", "mbpp", req,
                        check={"type": "code", "tests": list(r["test_list"]), "imports": list(r["test_imports"])}))
    return out


def bfcl(n, rng):
    repo, rev, qpath, apath = BFCL
    qs = [json.loads(l) for l in open(hub(repo, rev, qpath))]
    ans = {a["id"]: a["ground_truth"] for a in map(json.loads, open(hub(repo, rev, apath)))}
    rng.shuffle(qs)
    out = []
    for q in qs[:n]:
        (gold,) = ans[q["id"]]
        (name, args), = gold.items()
        user = " ".join(m["content"] for m in q["question"][0] if m["role"] == "user")
        tools = [{"name": f["name"], "description": f.get("description", ""), "parameters": f.get("parameters", {})}
                 for f in q["function"]]
        out.append(task(f"bfcl/{q['id']}", "bfcl", user, tools=tools,
                        check={"type": "call", "name": name, "arguments": args}, optimum={"tool": name}))
    return out


# ---- traces ----------------------------------------------------------------------------------

AGENT = {  # the coding agent's standing tools, offered on every trace task beside the session's own
    "Read": "Read a file.", "Write": "Write a file.", "Edit": "Replace text in a file.",
    "Bash": "Run a shell command.", "Grep": "Search file contents with a regex.", "Glob": "Find files by pattern.",
    "Agent": "Start a subagent on a task.", "WebFetch": "Fetch a URL.", "WebSearch": "Search the web.",
    "TodoWrite": "Update the task list.",
}
KEYARG = ("file_path", "path", "command", "pattern", "url", "query", "description", "prompt", "skill")


def blocks(content):
    return content if isinstance(content, list) else [{"type": "text", "text": content or ""}]


def sessions(path):
    """Claude Code events of a JSONL file, grouped by session and agent: [(role, blocks)] per
    transcript. A subagent (sidechain) is its own transcript, keyed by its agentId; values may
    arrive stringified ("True")."""
    out = {}
    for line in open(path, errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message")
        if e.get("type") in ("user", "assistant") and isinstance(m, dict):
            side = e.get("isSidechain") in (True, "True")
            key = (e.get("sessionId"), e.get("agentId") if side else None, side)
            out.setdefault(key, []).append((m.get("role"), blocks(m.get("content"))))
    return list(out.values())


def pairs(events, limit):
    """(request, steps, chunks, next action) from one session's events, and the tool names used."""
    out, request, steps, results, names = [], None, [], [], set()
    for role, bs in events:
        bs = [b for b in bs if isinstance(b, dict)]
        if role == "user":
            text = " ".join(b.get("text", "") for b in bs if b.get("type") == "text").strip()
            if text and not text.startswith("<"):
                request, steps, results = text, [], []
            for b in bs:
                if b.get("type") == "tool_result" and steps:
                    c = b.get("content")
                    c = c if isinstance(c, str) else " ".join(x.get("text", "") for x in blocks(c) if isinstance(x, dict))
                    steps[-1]["result"] = c[:300]
                    results.append({"text": c[:2000], "source": f"tool_result:{steps[-1]['tool']}"})
        else:
            for b in bs:
                if b.get("type") == "tool_use":
                    names.add(b["name"])
                if b.get("type") != "tool_use" or not request:
                    continue
                if steps:  # at least one prior step: an action in context
                    args = b.get("input") if isinstance(b.get("input"), dict) else {}
                    key = next((k for k in KEYARG if k in args), None)
                    out.append({"request": request, "steps": [dict(s) for s in steps[-8:]], "chunks": list(results[-12:]),
                                "action": {"tool": b["name"], "key": key, "value": str(args[key])[:200] if key else ""}})
                steps.append({"tool": b["name"], "result": ""})
    return out[:limit], names


def traces(n, rng, paths):
    """n trace tasks from Claude Code session files: directories, files, or "zen" (the Hanzo
    sessions of zenlm/zen-agentic-dataset-private at a pinned revision)."""
    files = []
    for p in paths:
        if p == "zen":
            files.append(hub(*ZEN))
        elif os.path.isdir(os.path.expanduser(p)):
            files += glob.glob(os.path.join(os.path.expanduser(p), "**", "*.jsonl"), recursive=True)
        else:
            files.append(p)
    rng.shuffle(files)
    out = []
    for f in files:
        if len(out) >= n:
            break
        try:
            found = [pairs(e, 4) for e in sessions(f)]
        except OSError:
            continue
        found = [(p, names) for p, names in found if p]
        if not found:
            continue
        ps, names = rng.choice(found)
        pair = rng.choice(ps)
        tools = [{"name": x, "description": AGENT.get(x, f"The {x} tool of the recorded agent."), "parameters": {"type": "object"}}
                 for x in sorted(set(AGENT) | names)]
        a = pair["action"]
        out.append(deep(task(f"trace/{len(out)}", "trace", pair["request"][:4000], chunks=pair["chunks"],
                             tools=tools, steps=pair["steps"],
                             check={"type": "action", "tool": a["tool"], "key": a["key"], "value": a["value"]},
                             optimum={"tool": a["tool"]})))
    return out


# ---- tasks -----------------------------------------------------------------------------------

def task(id, family, request, chunks=(), tools=(), steps=(), check=None, optimum=None, system=PLAIN):
    return {"id": id, "family": family, "system": system, "request": request, "chunks": list(chunks),
            "tools": list(tools), "steps": list(steps), "check": check or {}, "optimum": optimum or {}}


def messages(t, chunks=None, tools=None):
    """t as OpenAI messages; chunks/tools are the indices kept (None keeps all)."""
    cs = [c for i, c in enumerate(t["chunks"]) if chunks is None or i in chunks]
    ts = [x for i, x in enumerate(t["tools"]) if tools is None or i in tools]
    system = t["system"]
    if t["tools"]:
        system += "\n\nTools:\n" + json.dumps(ts, ensure_ascii=False) + "\n" + CALL
    user = []
    if cs:
        user.append("Documents:\n" + "\n\n".join(f"[{i + 1}] ({c['source']}) {c['text']}" for i, c in enumerate(cs)))
    if t["steps"]:
        user.append("Steps so far:\n" + "\n".join(f"- {s['tool']}: {s['result']}" for s in t["steps"]))
    user.append(t["request"])
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(user)}]


def final(text):
    m = re.findall(r"ANSWER:\s*([^\n]+)", text or "")
    return m[-1].strip().strip("*`. ") if m else None


def integer(text):
    f = final(text)
    for s in ([f] if f else []) + [text or ""]:
        xs = re.findall(r"-?\d[\d,]*(?:\.\d+)?", s)
        if xs:
            try:
                return float(xs[-1].replace(",", ""))
            except ValueError:
                pass
    return None


def call(text):
    """The first JSON object in text with a "tool" (or "name") key, as (name, arguments)."""
    s = text or ""
    for m in re.finditer(r"\{", s):
        depth = 0
        for j in range(m.start(), len(s)):
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            if depth == 0:
                try:
                    o = json.loads(s[m.start():j + 1])
                except ValueError:
                    break
                if isinstance(o, dict) and ("tool" in o or "name" in o):
                    args = o.get("arguments", o.get("parameters", {}))
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {}
                    return o.get("tool", o.get("name")), args if isinstance(args, dict) else {}
                break
    return None, {}


def same(v, allowed):
    """v matches one of BFCL's allowed values (strings case-folded, numbers by value)."""
    for a in allowed:
        if a == "" and v in (None, ""):
            return True
        if isinstance(a, (int, float)) and not isinstance(a, bool):
            try:
                if float(v) == float(a):
                    return True
            except (TypeError, ValueError):
                pass
        elif isinstance(a, str) and isinstance(v, str) and a.strip().lower() == v.strip().lower():
            return True
        elif a == v:
            return True
    return False


def sandbox(code, tests, imports, timeout=10):
    """True when code plus the asserts exit 0: temp dir, rlimits, no network."""
    body = "\n".join(list(imports) + [code] + list(tests)) + "\n"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.py")
        open(p, "w").write(body)
        limit = ("import resource as r; r.setrlimit(r.RLIMIT_AS, (2 << 30, 2 << 30)); "
                 "r.setrlimit(r.RLIMIT_CPU, (10, 10)); r.setrlimit(r.RLIMIT_FSIZE, (1 << 24, 1 << 24)); ")
        run = [sys.executable, "-I", "-c", limit + f"exec(compile(open({p!r}).read(), 't.py', 'exec'))"]
        if sys.platform == "linux":
            run = ["unshare", "-rn"] + run
        elif sys.platform == "darwin":
            run = ["sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"] + run
        else:
            return False
        try:
            return subprocess.run(run, cwd=d, capture_output=True, timeout=timeout, env={"PATH": "/usr/bin:/bin"}).returncode == 0
        except subprocess.TimeoutExpired:
            return False


def code(text):
    m = re.findall(r"```(?:python|py)?\n(.*?)```", text or "", re.S)
    return m[-1] if m else (text or "")


def score(t, text):
    c = t["check"]
    kind = c.get("type")
    if kind == "int":
        v = integer(text)
        return v is not None and abs(v - c["answer"]) < 1e-6
    if kind == "exact":
        f = final(text) or ""
        return c["answer"].lower() in f.lower()
    if kind == "code":
        return sandbox(code(text), c["tests"], c["imports"])
    if kind == "call":
        name, args = call(text)
        if name != c["name"]:
            return False
        if "contains" in c:  # synthetic: the asked value appears somewhere in the arguments
            return c["contains"].lower() in json.dumps(args, ensure_ascii=False).lower()
        for k, allowed in c["arguments"].items():
            allowed = allowed if isinstance(allowed, list) else [allowed]
            if "" in allowed and k not in args:
                continue
            if not same(args.get(k), allowed):
                return False
        return True
    if kind == "action":
        name, args = call(text)
        return name == c["tool"]
    raise ValueError(f"unknown check {kind!r}")


def build(n, rng, paths=()):
    out = []
    if n.get("synthetic"):
        out += synthetic(n["synthetic"], rng)
    if n.get("gsm8k"):
        out += gsm8k(n["gsm8k"], rng)
    if n.get("mbpp"):
        out += mbpp(n["mbpp"], rng)
    if n.get("bfcl"):
        out += bfcl(n["bfcl"], rng)
    if n.get("trace") and paths:
        out += traces(n["trace"], rng, paths)
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("dir")
    ap.add_argument("--n", default="synthetic=200,gsm8k=200,mbpp=100,bfcl=100,trace=200")
    ap.add_argument("--traces", nargs="*", default=[])
    a = ap.parse_args(argv)
    n = {k: int(v) for k, v in (x.split("=") for x in a.n.split(","))}
    tasks = build(n, random.Random(SEED), a.traces)
    os.makedirs(a.dir, exist_ok=True)
    with open(os.path.join(a.dir, "tasks.jsonl"), "w") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"{len(tasks)} tasks -> {a.dir}/tasks.jsonl")


if __name__ == "__main__":
    main(sys.argv[1:])
