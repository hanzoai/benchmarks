"""merge.py's metrics on cases computed by hand.

    uv run --with numpy python -m unittest discover -s harness
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import merge  # noqa: E402


class Upstream(unittest.TestCase):
    def test_two_answers(self):
        # gold 0 at [.75, .25]: right, confidence .75; gold 1 at [.55, .45]: wrong, confidence .55
        m = merge.metrics([(0, np.array([0.75, 0.25])), (1, np.array([0.55, 0.45]))])
        self.assertEqual(m["n"], 2)
        self.assertEqual(m["accuracy"], 0.5)
        # class 0: tp 1, fp 1, fn 0 -> 2/3; class 1: tp 0, fn 1 -> 0
        self.assertEqual(m["macro_f1"], round(1 / 3, 4))
        # one per bin: .5 * |.75 - 1| + .5 * |.55 - 0|
        self.assertEqual(m["ece"], 0.4)
        # (.25² + .25²) and (.55² + .55²), averaged
        self.assertEqual(m["brier"], 0.365)
        self.assertEqual(m["nll"], round((-math.log(0.75) - math.log(0.45)) / 2, 4))
        self.assertEqual(m["mean_confidence"], 0.65)
        self.assertEqual(m["acc_at_50_coverage"], 1.0)


class RiskCoverage(unittest.TestCase):
    def test_distinct_confidences(self):
        # errors by confidence: 0 1 0 1 -> risk 0, 1/2, 1/3, 1/2
        aurc, at = merge.risk_coverage([0.9, 0.8, 0.7, 0.6], [1, 0, 1, 0])
        self.assertEqual(aurc, round((0 + 1 / 2 + 1 / 3 + 1 / 2) / 4, 4))
        self.assertEqual(at, {"0.1": 0.0, "0.25": 0.0, "0.5": 0.5, "0.75": 0.3333, "0.9": 0.3333, "1.0": 0.5})

    def test_order_given_does_not_matter(self):
        self.assertEqual(merge.risk_coverage([0.6, 0.9, 0.7, 0.8], [0, 1, 1, 0]),
                         merge.risk_coverage([0.9, 0.8, 0.7, 0.6], [1, 0, 1, 0]))

    def test_ties_are_taken_together(self):
        # the two at 1.0 hold one error between them: 1/2 at either prefix, whatever their order
        for corr in ([1, 0, 1], [0, 1, 1]):
            aurc, at = merge.risk_coverage([1.0, 1.0, 0.5], corr)
            self.assertEqual(aurc, round((1 / 2 + 1 / 2 + 1 / 3) / 3, 4))
            self.assertEqual(at["0.5"], 0.5)
            self.assertEqual(at["1.0"], 0.3333)

    def test_empty(self):
        self.assertEqual(merge.risk_coverage([], []), (None, {}))


def gold(*idx, qtype="choice"):
    return [[{"q": {"idx": i}}, {"q": {"type": qtype}}] for i in idx]


class Score(unittest.TestCase):
    def test_unanswered_and_zero_probability_on_gold(self):
        m = merge.score(gold(0, 1, 1), {"0/q": [1.0, 0.0], "1/q": [1.0, 0.0], "2/q": None})
        self.assertEqual((m["n"], m["unanswered"], m["questions"]), (2, 1, 3))
        self.assertEqual(m["accuracy"], 0.5)
        # the second answer gives its gold option nothing
        self.assertEqual(m["zero_prob"], 0.5)
        self.assertEqual(m["nll"], round(-math.log(1e-12) / 2, 4))
        # both at confidence 1: one error between them at every coverage
        self.assertEqual(m["aurc"], 0.5)

    def test_score_mae_against_the_teachers_mean_level(self):
        g = [[{"r": {"idx": 1, "gold_score": 1.5, "soft": [0, 0.5, 0.5]}, "_wf": "w"}, {"r": {"type": "score"}}]]
        m = merge.score(g, {"0/r": [0.2, 0.3, 0.5]}, typed=True)
        # expected level .3 + 2 * .5 = 1.3
        self.assertEqual(m["score_mae"], 0.2)
        self.assertEqual(m["within_1_level"], 1.0)
        self.assertEqual(m["soft_accuracy"], 0.4)
        self.assertEqual(m["brier_vs_soft"], 0.08)
        self.assertEqual(m["by_question_type"], {"score": 0.0})


class Sides(unittest.TestCase):
    def test_routed_takes_the_routers_checkpoint_per_case(self):
        laya = {"route": {"s": ["english", "multilingual"]},
                "models": {"english": {"s": {"p": {"0/q": [1, 0], "1/q": [1, 0]}}},
                           "multilingual": {"s": {"p": {"0/q": [0, 1], "1/q": [0, 1]}}}}}
        self.assertEqual(merge.routed(laya, "s", gold(0, 1)), {"0/q": [1, 0], "1/q": [0, 1]})
        b = merge.backends("s", gold(0, 1), {"suites": {"s": {"p": {"0/q": [0.5, 0.5]}}}}, laya, None)
        self.assertEqual(list(b), ["kai", "laya", "laya:english", "laya:multilingual"])

    def test_massive_macro_over_languages(self):
        def lang(acc, ece):
            m = {k: 0.0 for k in merge.MACRO}
            m.update({"n": 100, "unanswered": 0, "questions": 100, "accuracy": acc, "ece": ece,
                      "risk_at_coverage": {str(k): 1 - acc for k in merge.COVERAGE}})
            return m
        suites = {"massive.en-US": {"jev": lang(0.9, 0.1)}, "massive.de-DE": {"jev": lang(0.5, 0.3), "laya": lang(0.1, 0.2)},
                  "jev.ag_news": {"jev": lang(0.0, 0.0)}}
        s = merge.massive(suites)
        self.assertEqual(s["jev"]["languages"], 2)
        self.assertEqual(s["jev"]["macro_accuracy"], 0.7)
        self.assertEqual(s["jev"]["macro_ece"], 0.2)
        self.assertEqual((s["jev"]["english"], s["jev"]["non_english_macro"]), (0.9, 0.5))
        self.assertEqual(s["jev"]["risk_at_coverage"]["0.5"], 0.3)
        self.assertEqual(s["laya"]["above_3x_random"], 0)
        self.assertEqual(s["jev"]["above_3x_random"], 2)


if __name__ == "__main__":
    unittest.main()
