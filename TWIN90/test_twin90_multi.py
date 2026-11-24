"""Synthetic, prospective-only safety and scoring tests for Multi-2/3/5."""
import unittest
from datetime import timedelta
from test_twin90_fusion import fixture, actual
from twin90_fusion import prepare as fusion_prepare, confirm as fusion_confirm
from twin90_multi import prepare, confirm, reconcile, root, MODES


class MultiTests(unittest.TestCase):
    def setUp(self):
        self.state, self.key, self.due = fixture()
        fusion_prepare(self.state, self.due - timedelta(minutes=2))

    def test_preannounced_only_and_caps(self):
        prepare(self.state, self.due - timedelta(minutes=2))
        modes = root(self.state)["active"][self.key]["modes"]
        self.assertEqual(len(modes[MODES[0]]["2"]["pairs"]), 2)
        self.assertEqual(len(modes[MODES[0]]["3"]["pairs"]), 3)
        self.assertEqual(len(modes[MODES[0]]["5"]["pairs"]), 5)
        self.assertEqual(len(modes[MODES[1]]["5"]["pairs"]), 5)
        self.assertEqual(prepare(self.state)["published"], 0)
        self.assertEqual(len(root(self.state)["active"]), 1)

    def test_no_telegram_ack_no_scoring(self):
        prepare(self.state)
        reconcile(self.state, actual(101))
        self.assertEqual(root(self.state)["missed"], 1)
        self.assertEqual(root(self.state)["stats"][MODES[0]]["2"]["by_h"]["1"]["n"], 0)

    def test_prospective_h5_and_no_duplicates(self):
        prepare(self.state, self.due - timedelta(minutes=2))
        self.assertTrue(confirm(self.state, self.key, self.due - timedelta(minutes=1)))
        for draw in range(101, 106):
            reconcile(self.state, actual(draw))
            reconcile(self.state, actual(draw))
        lab = root(self.state)
        self.assertEqual(lab["published"], 1)
        self.assertEqual(lab["stats"][MODES[0]]["2"]["within5"]["n"], 1)
        self.assertEqual(lab["stats"][MODES[0]]["5"]["by_h"]["1"]["pair_exposures"], 5)
        self.assertEqual(lab["stats"][MODES[1]]["3"]["by_h"]["1"]["control_pair_exposures"], 3)
        self.assertFalse(lab["active"])

    def test_late_and_gap_rejected(self):
        prepare(self.state, self.due - timedelta(minutes=2))
        self.assertFalse(confirm(self.state, self.key, self.due))
        reconcile(self.state, actual(101))
        self.assertEqual(root(self.state)["missed"], 1)
        self.assertEqual(root(self.state)["stats"][MODES[0]]["2"]["published"], 0)

    def test_requires_original_fusion(self):
        state, key, due = fixture()
        prepare(state, due - timedelta(minutes=2))
        self.assertFalse(root(state)["active"])


if __name__ == "__main__":
    unittest.main()
