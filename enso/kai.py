"""Kai in process: libcontrol (hanzoai/decision, crate `control`) through ctypes, and the
states its programs read, built exactly as Enso builds them.

    k = Kai("/path/libcontrol.dylib", ["kai-1-agent"], "metal")
    r = k.decide("router.model@1", [route(messages, tools, 812)], mode="enforced")
    r["results"][0]["signals"]["tier"]   # {"answer": "small", "certainty": 0.61, "accepted": true}

The C ABI (every string UTF-8 JSON; returned strings freed with kai_free):
kai_open(config) -> handle | NULL, kai_decide(handle, call) -> result | NULL, kai_error(),
kai_free(s), kai_close(handle). A caller acts on Kai only when a result's mode is "enforced":
a choice or score when accepted, a noul by whether it holds (`act(result, question)`).
"""
import ctypes
import json

LEVELS = ["none", "short", "medium", "deep"]


class Kai:
    def __init__(self, lib, models, device="cpu"):
        self.lib = ctypes.CDLL(lib)
        self.lib.kai_open.restype = ctypes.c_void_p
        self.lib.kai_open.argtypes = [ctypes.c_char_p]
        self.lib.kai_decide.restype = ctypes.c_void_p
        self.lib.kai_decide.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.kai_error.restype = ctypes.c_void_p
        self.lib.kai_error.argtypes = []
        self.lib.kai_free.argtypes = [ctypes.c_void_p]
        self.lib.kai_close.argtypes = [ctypes.c_void_p]
        self.h = self.lib.kai_open(json.dumps({"models": list(models), "device": device}).encode())
        if not self.h:
            raise RuntimeError(f"kai_open: {self.error()}")

    def error(self):
        p = self.lib.kai_error()
        if not p:
            return "unknown error"
        try:
            return ctypes.string_at(p).decode()
        finally:
            self.lib.kai_free(p)

    def decide(self, program, states, mode=None, thresholds=None, k=None, base=None):
        call = {"program": program, "states": list(states)}
        for key, v in (("mode", mode), ("thresholds", thresholds), ("k", k), ("base", base)):
            if v is not None:
                call[key] = v
        p = self.lib.kai_decide(self.h, json.dumps(call, ensure_ascii=False).encode())
        if not p:
            raise RuntimeError(f"kai_decide {program}: {self.error()}")
        try:
            return json.loads(ctypes.string_at(p).decode())
        finally:
            self.lib.kai_free(p)

    def close(self):
        if self.h:
            self.lib.kai_close(self.h)
            self.h = None


def act(result, question):
    """The answer Kai may act on, or None. Only in enforced mode: a choice or score when its
    certainty is accepted at the threshold; a noul always, as "true" when it holds at its
    threshold and "false" when it does not."""
    if not result or result.get("error") or result.get("mode") != "enforced":
        return None
    s = (result.get("signals") or {}).get(question)
    if not s:
        return None
    if "holds" in s and s["holds"] is not None:
        return "true" if s["holds"] else "false"
    return s["answer"] if s.get("accepted") else None


def text(content):
    """A message's text: a string, or the text parts of a content array."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("text")) + ("\n" if content else "")
    return ""


def last(messages, role="user"):
    for m in reversed(messages):
        if m.get("role") == role:
            return text(m.get("content"))
    return ""


def images(messages):
    return any(isinstance(m.get("content"), list) and any(isinstance(p, dict) and p.get("type") in ("image_url", "image")
                                                           for p in m["content"]) for m in messages)


# The states, one function per program (contract.txt). Truncation counts characters.

def route(messages, tools, prompt_tokens):
    """router.model@1 and reasoning.budget@1."""
    system = next((text(m.get("content")) for m in messages if m.get("role") == "system"), "")
    return {"request": last(messages)[:4000], "system": system[:500],
            "turns": sum(1 for m in messages if m.get("role") != "system"),
            "tools": [t["name"] for t in tools], "prompt_tokens": int(prompt_tokens), "images": images(messages)}


def chunk(request, body, source):
    """context.select@1, one per candidate."""
    return {"request": request[:2000], "chunk": body[:2000], "source": source}


def tool(request, spec):
    """tools.select@1, one per candidate."""
    return {"request": request[:2000], "tool": {"name": spec["name"], "description": (spec.get("description") or "")[:500]}}


def progress(request, steps):
    """agent.progress@1 over the last 8 steps."""
    return {"request": request[:2000], "steps": [{"tool": s["tool"], "result": (s.get("result") or "")[:300]} for s in steps[-8:]]}


def complete(request, answer):
    """agent.complete@1, and escalation over a probe answer."""
    return {"request": request[:2000], "answer": answer[:3000]}


def risk(name, arguments):
    """action.risk@1: arguments kept whole under 2000 serialized characters, else cut as text."""
    s = json.dumps(arguments, ensure_ascii=False)
    return {"tool": name, "arguments": arguments if len(s) <= 2000 else s[:2000]}
