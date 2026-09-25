"""The harness on hand-made cases: scrubbing, the oracle and regret, the state builders'
truncation, the metric integrals, and the answer checks.

    uv run python -m unittest discover -s enso
"""
import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kai as K  # noqa: E402
import oracle as O  # noqa: E402
import policy as P  # noqa: E402
import serve as S  # noqa: E402
import target as T  # noqa: E402
import work as W  # noqa: E402
from scrub import deep, scrub  # noqa: E402


class Scrub(unittest.TestCase):
    def test_secrets(self):
        cases = {
            "key sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv here": "sk-ant",
            "export OPENAI_API_KEY=sk-proj-abcdefghijklmnop1234": "sk-proj",
            "token ghp_0123456789abcdefghijABCDEFGHIJ": "ghp_",
            "aws AKIAABCDEFGHIJKLMNOP": "AKIAABCD",
            "hf_ABCDEFGHIJKLMNOPQRSTUVWXYZ12 is mine": "hf_ABCD",
            "curl -H 'Authorization: Bearer abc.def.ghi-123456'": "abc.def.ghi",
            "postgres://admin:hunter2@db.example.com/x": "hunter2",
            "password = 'correct horse'": "correct",
            "DB_PASSWORD=s3cr3tvalue\nOTHER=1": "s3cr3tvalue",
            "mail z@example.com please": "z@example.com",
            "ssh 10.0.0.19:18300": "10.0.0.19",
            "host ra.local up": "ra.local",
            "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk\n-----END OPENSSH PRIVATE KEY-----": "b3BlbnNzaC1rZXk",
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U": "eyJhbGci",
        }
        for text, leaked in cases.items():
            self.assertNotIn(leaked, scrub(text), text)

    def test_keeps_code(self):
        s = "def add(a, b):\n    return a + b  # adds two numbers"
        self.assertEqual(scrub(s), s)
        self.assertEqual(deep({"a": ["x z@example.com"]}), {"a": ["x [EMAIL]"]})


def row(task, tier, level, ok, usd, gpu=1.0, dec=10):
    return {"task": task, "tier": tier, "level": level, "success": ok, "usd": usd, "gpu_s": gpu, "decode_tokens": dec}


class Oracle(unittest.TestCase):
    def setUp(self):
        self.g = O.cells([
            row("a", "big", "deep", True, 5.0), row("a", "big", "none", True, 1.0),
            row("a", "small", "none", False, 0.2), row("a", "small", "deep", True, 1.0, gpu=0.5),
            row("b", "big", "deep", False, 5.0), row("b", "small", "none", False, 0.1),
        ])

    def test_cheapest_not_largest(self):
        best = O.oracle(self.g)
        self.assertEqual(best, {"a": ("small", "deep")})  # $1.0 ties big/none; fewer GPU-s wins

    def test_regret(self):
        best = O.oracle(self.g)
        r = O.regret(self.g, best, {"a": ("big", "deep"), "b": ("big", "deep")})
        self.assertAlmostEqual(r["a"]["regret_usd"], 4.0)
        self.assertFalse(r["a"]["lost"])
        self.assertEqual((r["b"]["lost"], r["b"]["regret_usd"], r["b"]["oracle"]), (False, None, False))
        r = O.regret(self.g, best, {"a": ("small", "none"), "c": ("x", "y")})
        self.assertTrue(r["a"]["lost"])
        self.assertEqual(r["c"], {"missing": True})

    def test_summary(self):
        s = O.summary([{"success": True, "latency_s": 1.0, "usd": 1.0}, {"success": True, "latency_s": 3.0, "usd": 3.0},
                       {"success": False, "latency_s": 9.0, "usd": 9.0}], 4)
        self.assertEqual((s["success_rate"], s["latency_p50"], s["usd"], s["usd_total"]), (0.5, 2.0, 2.0, 13.0))


class States(unittest.TestCase):
    def test_truncation(self):
        long = "x" * 9000
        msgs = [{"role": "system", "content": "s" * 900}, {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "yo"}, {"role": "user", "content": long}]
        r = K.route(msgs, [{"name": "a"}, {"name": "b"}], 812)
        self.assertEqual((len(r["request"]), len(r["system"]), r["turns"], r["tools"], r["prompt_tokens"], r["images"]),
                         (4000, 500, 3, ["a", "b"], 812, False))
        self.assertEqual(list(r), ["request", "system", "turns", "tools", "prompt_tokens", "images"])
        c = K.chunk(long, long, "doc")
        self.assertEqual((len(c["request"]), len(c["chunk"])), (2000, 2000))
        t = K.tool(long, {"name": "n", "description": long})
        self.assertEqual(len(t["tool"]["description"]), 500)
        p = K.progress(long, [{"tool": str(i), "result": long} for i in range(12)])
        self.assertEqual([s["tool"] for s in p["steps"]], [str(i) for i in range(4, 12)])
        self.assertEqual(len(p["steps"][0]["result"]), 300)
        self.assertEqual(len(K.complete(long, long)["answer"]), 3000)
        big = {"cmd": long}
        self.assertEqual(K.risk("bash", {"cmd": "ls"})["arguments"], {"cmd": "ls"})
        self.assertEqual(len(K.risk("bash", big)["arguments"]), 2000)

    def test_parts_and_images(self):
        msgs = [{"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "image_url", "image_url": {}},
                                             {"type": "text", "text": "b"}]}]
        r = K.route(msgs, [], 1)
        self.assertEqual((r["request"], r["images"]), ("a\nb\n", True))

    def test_act(self):
        res = {"mode": "enforced", "signals": {"tier": {"answer": "small", "certainty": 0.4, "accepted": False},
                                               "done": {"answer": "false", "certainty": 0.6, "holds": False},
                                               "ok": {"answer": "true", "certainty": 0.9, "holds": True}}}
        self.assertIsNone(K.act(res, "tier"))
        self.assertEqual((K.act(res, "done"), K.act(res, "ok")), ("false", "true"))
        self.assertIsNone(K.act(dict(res, mode="shadow"), "ok"))


class Integrals(unittest.TestCase):
    def test_timeline(self):
        r = {"t0": 0.0, "ttft": 2.0, "end": 6.0, "times": [(2.0, 10), (4.0, 20), (6.0, 40)]}
        pts = S.timeline(r, 100, 40)
        # prefill ramp 0->100 over 2s: 100; first chunk jumps to 110; 110->120 over 2s: 230; 120->140: 260
        self.assertAlmostEqual(S.area(pts), 100 + 230 + 260)
        samples = [(0.0, 1, 0, 0.5), (3.0, 2, 0, 0.25)]
        self.assertAlmostEqual(S.steps(samples, 0.0, 6.0, lambda s: 1 / max(1, s[1])), 3 * 1 + 3 * 0.5)

    def test_measure(self):
        tier = {"state_bytes": 1e9, "kv_bytes_per_token": 1e6, "gpus": 1, "usd_per_gpu_hour": 3.6, "kv_capacity_bytes": 2e9}
        r = {"t0": 0.0, "ttft": 1.0, "end": 3.0, "times": [(1.0, 5), (3.0, 10)], "content": "abcde", "reasoning": "fghij",
             "usage": {"prompt_tokens": 100, "completion_tokens": 20}, "finish": "stop", "error": None,
             "samples": [(0.0, 2, 0, 0.5)], "waiting": 0}
        m = S.measure(r, tier)
        self.assertEqual((m["prompt_tokens"], m["decode_tokens"], m["reasoning_tokens"], m["reasoning_estimated"]), (100, 20, 10, True))
        self.assertAlmostEqual(m["gpu_s"], 1.5)
        self.assertAlmostEqual(m["usd"], 1.5 * 3.6 / 3600)
        self.assertAlmostEqual(m["kv_gb_s"], (1e9 * 3 + 1e6 * S.area(S.timeline(r, 100, 20))) / 1e9)
        self.assertAlmostEqual(m["kv_server_gb_s"], 0.5 * 2e9 * 3 / 1e9)


class Work(unittest.TestCase):
    def test_synthetic_checks(self):
        rng = random.Random(13)
        t = W.arith(rng, 4, 0)
        self.assertTrue(W.score(t, f"... so ANSWER: {t['check']['answer']}"))
        self.assertFalse(W.score(t, "ANSWER: 1234567"))
        n = W.needle(rng, 8, 0)
        k = n["optimum"]["chunk"]
        self.assertIn(n["check"]["answer"], n["chunks"][k]["text"])
        self.assertTrue(W.score(n, f"ANSWER: {n['check']['answer']}"))
        tl = W.tool(rng, 4, 0)
        name, x = tl["check"]["name"], tl["check"]["contains"]
        self.assertTrue(W.score(tl, json.dumps({"tool": name, "arguments": {"q": f"about {x} today"}})))
        self.assertFalse(W.score(tl, json.dumps({"tool": name, "arguments": {"q": "elsewhere"}})))
        self.assertFalse(W.score(tl, json.dumps({"tool": "nope", "arguments": {}})))
        lg = W.logic(rng, 4, 0)
        self.assertTrue(W.score(lg, f"ANSWER: {lg['check']['answer']}"))

    def test_messages_keep(self):
        rng = random.Random(1)
        t = W.needle(rng, 4, 0)
        t["tools"] = [{"name": "a"}, {"name": "b"}]
        full = W.messages(t)
        kept = W.messages(t, chunks=[1], tools=[0])
        self.assertIn("[4]", full[1]["content"])
        self.assertNotIn("[2]", kept[1]["content"])
        self.assertIn('"a"', kept[0]["content"])
        self.assertNotIn('"b"', kept[0]["content"])

    def test_bfcl_args(self):
        t = W.task("x", "bfcl", "?", check={"type": "call", "name": "f", "arguments": {"n": [3], "unit": ["", "km"]}})
        self.assertTrue(W.score(t, '{"name": "f", "arguments": {"n": 3}}'))
        self.assertTrue(W.score(t, '{"tool": "f", "arguments": {"n": "3.0", "unit": "KM"}}'))
        self.assertFalse(W.score(t, '{"tool": "f", "arguments": {"n": 4}}'))

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "sandbox needs unshare or sandbox-exec")
    def test_sandbox(self):
        self.assertTrue(W.sandbox("def f(x):\n    return x + 1", ["assert f(1) == 2"], []))
        self.assertFalse(W.sandbox("def f(x):\n    return x", ["assert f(1) == 2"], []))
        net = "import socket\nsocket.create_connection(('1.1.1.1', 80), timeout=2)"
        self.assertFalse(W.sandbox(net, [], []))

    def test_trace_pairs(self):
        events = [("user", [{"type": "text", "text": "fix the bug in a.py"}]),
                  ("assistant", [{"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}]),
                  ("user", [{"type": "tool_result", "content": "def f(): pass"}]),
                  ("assistant", [{"type": "tool_use", "name": "Edit", "input": {"file_path": "a.py", "old": "x"}}])]
        ps, names = W.pairs(events, 4)
        self.assertEqual(names, {"Read", "Edit"})
        self.assertEqual(ps[0]["action"], {"tool": "Edit", "key": "file_path", "value": "a.py"})
        self.assertEqual(ps[0]["steps"], [{"tool": "Read", "result": "def f(): pass"}])
        self.assertEqual(ps[0]["chunks"][0]["source"], "tool_result:Read")


class Rules(unittest.TestCase):
    def test_b1_and_tiers(self):
        spec = {"labels": ["small", "medium", "large", "frontier"], "levels": ["none", "short", "medium", "deep"],
                "default": "deep", "tiers": [
                    {"id": "big", "label": "large", "served": True, "usd_per_gpu_hour": 1.0, "primary": True},
                    {"id": "cheap", "label": "large", "served": True, "usd_per_gpu_hour": 0.5},
                    {"id": "tiny", "label": "small", "served": True, "usd_per_gpu_hour": 0.1},
                    {"id": "gone", "label": "medium", "served": False}]}
        tiers = P.Tiers(spec)
        self.assertEqual((tiers.pick("small")["id"], tiers.pick("medium")["id"], tiers.pick("large")["id"],
                          tiers.pick("frontier")["id"]), ("tiny", "cheap", "big", "big"))
        self.assertEqual(tiers.up(tiers.by["tiny"])["id"], "cheap")
        short = W.task("s", "x", "What is 2+2?")
        code = W.task("c", "x", "Please write a function that parses dates.")
        hard = W.task("h", "x", "summarize " + "word " * 5000)
        self.assertEqual(P.b1(short, tiers), ("tiny", "none"))
        self.assertEqual(P.b1(code, tiers), ("cheap", "medium"))
        self.assertEqual(P.b1(hard, tiers), ("big", "deep"))
        self.assertEqual(P.b0(short, tiers), ("big", "deep"))


class Target(unittest.TestCase):
    def test_units_are_stable(self):
        a = T.units({"x": "Oil  prices\nrise"})
        b = T.units({"y": "Oil prices rise"})
        self.assertEqual(a, b)
        self.assertEqual(len(T.units({"d": "a" * 250})), 2)
        self.assertIsInstance(T.is_val({"x": "y"}, 100), bool)


if __name__ == "__main__":
    unittest.main()


class Fake:
    """Kai stand-in: tier small, budget 1, chunk/tool 0 selected, done on the second try."""

    def __init__(self, mode="enforced"):
        self.mode, self.calls = mode, {}

    def decide(self, program, states, mode=None, thresholds=None, k=None, base=None):
        key = (program, json.dumps(states[0].get("request")))
        self.calls[key] = self.calls.get(key, 0) + 1
        sig = {"router.model@1": {"tier": {"answer": "small", "certainty": 0.9, "accepted": True}},
               "reasoning.budget@1": {"budget": {"answer": "1", "certainty": 0.9, "accepted": True}},
               "agent.complete@1": {"done": {"answer": "true", "certainty": 0.9, "holds": self.calls[key] > 1}},
               "agent.progress@1": {"status": {"answer": "looping", "certainty": 0.9, "accepted": True}}}.get(program, {})
        out = {"program": program, "hash": "sha256:x", "ms": 1.0,
               "results": [{"state": f"sha256:{i}", "mode": self.mode, "signals": sig} for i, _ in enumerate(states)]}
        if k is not None:
            out["selected"] = [0]
        return out


class Study(unittest.TestCase):
    def test_conditions_end_to_end(self):
        import tempfile
        import grid as G
        import study as ST
        spec = {"labels": ["small", "medium", "large", "frontier"], "levels": ["none", "short", "medium", "deep"],
                "default": "deep", "tiers": [
                    {"id": "big", "label": "large", "served": True, "usd_per_gpu_hour": 1.0, "primary": True},
                    {"id": "tiny", "label": "small", "served": True, "usd_per_gpu_hour": 0.1}]}
        tiers = P.Tiers(spec)
        rng = random.Random(3)
        ts = [W.needle(rng, 4, 0), W.tool(rng, 4, 0), W.arith(rng, 2, 0)]
        sent = []

        def run(t, tier, level, cap, variant="full", chunks=None, tools=None):
            sent.append((t["id"], tier["id"], level, variant, chunks, tools))
            ok = tier["id"] == "big" or level == "deep"
            usd = {"none": 1, "short": 2, "medium": 3, "deep": 4}[level] * tier["usd_per_gpu_hour"]
            return {"task": t["id"], "family": t["family"], "tier": tier["id"], "label": tier["label"], "level": level,
                    "variant": variant, "success": ok, "gpu_s": usd, "kv_gb_s": usd, "prompt_tokens": 10,
                    "decode_tokens": 10 * usd, "reasoning_tokens": 0, "prefill_s": 1, "decode_s": 1, "latency_s": 2,
                    "usd": usd, "_content": "an answer"}

        real = G.run
        G.run = run
        try:
            rows = []
            for t in ts:
                for tier in tiers.served:
                    for lv in tiers.levels:
                        r = run(t, tier, lv, None)
                        r["content"] = r.pop("_content")
                        rows.append(r)
            sent.clear()
            g = O.cells(rows)
            best = O.oracle(g)
            self.assertEqual(best[ts[0]["id"]], ("tiny", "deep"))  # $0.4 beats big/none $1
            cfg = dict(ST.STUDIES["smoke"], k=1, attempts=3)
            with tempfile.TemporaryDirectory() as d:
                picks, _ = ST.offline(ts, tiers, g, d, S.Cap(99), Fake())
                self.assertEqual(picks["K1"][ts[0]["id"]][0], ("tiny", "deep"))
                self.assertEqual(picks["K2"][ts[0]["id"]][0], ("tiny", "short"))
                self.assertEqual(picks["R1"][ts[0]["id"]][0][0] in ("tiny", "big"), True)
                out = ST.online(ts, tiers, cfg, d, S.Cap(99), Fake(), picks, g)
            # K3 prunes the needle's chunks to one; K4 the tool list to one; K5 retries once, a tier up.
            self.assertIn((ts[0]["id"], "tiny", "short", "K3", [0], None), sent)
            self.assertIn((ts[1]["id"], "tiny", "short", "K4", None, [0]), sent)
            self.assertEqual(out["K5"][ts[2]["id"]]["attempts"], 2)
            self.assertIn((ts[2]["id"], "big", "medium", "K5", None, None), sent)
            self.assertTrue(out["K5"][ts[2]["id"]]["success"])
            self.assertEqual(set(out["K3"]), {t["id"] for t in ts})
        finally:
            G.run = real

    def test_shadow_is_not_applied(self):
        spec = {"labels": ["small", "medium", "large", "frontier"], "levels": ["none", "short", "medium", "deep"],
                "default": "deep", "tiers": [{"id": "big", "label": "large", "served": True, "primary": True}]}
        tiers = P.Tiers(spec)
        t = W.needle(random.Random(1), 4, 0)
        k = Fake(mode="shadow")
        self.assertEqual(P.k1(t, tiers, k)[0], "big")
        self.assertEqual(P.k2(t, tiers, k)[0], "deep")
        self.assertIsNone(P.k3(t, k, 1)[0])
