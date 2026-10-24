"""Offline tests for the alert logic (no network). Run: python -m unittest discover -s tests"""
import unittest

from agentid_tracker import reputation
from agentid_tracker.tracker import Tracker


def row(i, fill, launched=False, creator="0xabc", venue="flap_agent_curve"):
    return {"venue": venue, "id": f"m{i}", "symbol": f"T{i}", "quote": "BNB", "fill_pct": fill, "raised": fill / 20,
            "cap": 5.0, "creator": creator, "launched": launched, "index": i, "link": "x"}


class FakeTracker(Tracker):
    def __init__(self, frames, **kw):
        super().__init__(venues=(), **kw)
        self.frames = list(frames)

    def collect(self):
        return self.frames.pop(0)


class TrackerTest(unittest.TestCase):
    def test_events(self):
        frames = [
            [row(1, 5.0)],                       # baseline: no alerts
            [row(1, 5.0), row(2, 1.0)],          # new market
            [row(1, 18.0), row(2, 1.0)],         # +13pp -> fast_fill
            [row(1, 85.0), row(2, 1.0)],         # crosses 80 -> near_full (+ fast_fill again)
            [row(1, 100.0, launched=True), row(2, 1.0)],
        ]
        t = FakeTracker(frames, fast_window=3600)
        got = [[e["event"] for e in t.step()[1]] for _ in range(len(frames))]
        self.assertEqual(got[0], [])
        self.assertEqual(got[1], ["new_launch"])
        self.assertEqual(got[2], ["fast_fill"])
        self.assertIn("near_full", got[3])
        self.assertEqual(got[4], ["launched"])

    def test_reputation(self):
        rows = [row(1, 100, True), row(2, 100, True), row(3, 4.0)]
        db = reputation.build(rows)
        s = reputation.score("0xabc", db, current=rows[2])
        self.assertEqual(s["score"], 3)  # +2 graduated launches, +1 grad rate 2/2
        spam = [row(i, 1.0, creator="0xspam") for i in range(6)]
        s2 = reputation.score("0xspam", reputation.build(spam), current=spam[-1])
        self.assertLessEqual(s2["score"], -3)


if __name__ == "__main__":
    unittest.main()
