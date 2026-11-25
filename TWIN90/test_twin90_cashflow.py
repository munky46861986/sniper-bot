"""Accounting tests: costs, independent stops, idempotence, week crossover."""
import unittest
from twin90_cashflow import refresh, root, MODES


def item(pair_count, hits, controls):
    pairs = [[i, i + 1] for i in range(1, pair_count + 1)]
    return {"pairs": pairs, "hits": hits, "control_hits": controls}


def source(key="2026-11-24#287", pair_count=2):
    return {"key": key,
            "modes": {MODES[0]: {"2": item(pair_count, [0, 0, 2, 0, 0],
                                          [0, 1, 0, 0, 0])}}}


class CashflowTests(unittest.TestCase):
    def test_full5_vs_stop_and_independent_control(self):
        state = {"superambo_multi": {"recent": [source()]}}
        self.assertEqual(refresh(state), [])
        lab = root(state)
        a = lab["stats"][MODES[0]]["2"]["REPLAY"]["FULL5"]
        b = lab["stats"][MODES[0]]["2"]["REPLAY"]["STOP1"]
        self.assertEqual((a["spent_eur"], a["gross_eur"], a["net_eur"]),
                         (10, 28, 18))
        self.assertEqual((b["spent_eur"], b["gross_eur"], b["net_eur"]),
                         (6, 28, 22))
        self.assertEqual((b["control_spent_eur"], b["control_gross_eur"],
                          b["control_net_eur"]), (4, 14, 10))
        self.assertEqual(lab["replayed_signals"], 1)
        self.assertEqual(refresh(state), [])
        self.assertEqual(lab["replayed_signals"], 1)

    def test_forward_and_separate_days_and_weeks(self):
        state = {"superambo_multi": {"recent": []}}
        refresh(state)
        state["superambo_multi"]["recent"] = [source("2026-11-29#287")]
        notes = refresh(state)
        self.assertEqual(len(notes), 1)
        lab = root(state)
        self.assertEqual(lab["forward_signals"], 1)
        self.assertEqual(lab["replayed_signals"], 0)
        self.assertIn("2026-11-29", lab["daily"])
        self.assertIn("2026-11-30", lab["daily"])
        self.assertIn("2026-W48", lab["weekly"])
        self.assertIn("2026-W49", lab["weekly"])
        self.assertEqual(refresh(state), [])

    def test_ignore_incomplete_or_invalid(self):
        bad = source()
        bad["modes"][MODES[0]]["2"]["hits"] = [1]
        state = {"superambo_multi": {"recent": [bad]}}
        refresh(state)
        self.assertEqual(root(state)["replayed_signals"], 0)


if __name__ == "__main__":
    unittest.main()
