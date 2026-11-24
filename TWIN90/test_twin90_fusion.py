"""Only synthetic fixtures; verifies no retrospective or unacknowledged scoring."""
import unittest
from datetime import datetime, timedelta
from twin90_advance import ROME, next_concorso
from twin90_fusion import prepare, confirm, reconcile, root, MODES, VERSION


def fixture():
    last = {"day": "2026-11-24", "draw": 100, "time": "08:10"}
    key, due = next_concorso(last)
    prior = "2026-11-24#100"
    R = list(range(1, 21))
    D = list(range(1, 11)) + list(range(41, 51))
    H = [1, 2] + list(range(11, 19)) + list(range(51, 61))
    C = list(range(21, 41))
    state = {
        "latest": prior, "history": [last],
        "pending_notifications": [{"type": "PREVIEW", "key": key, "due_at": due.isoformat()}],
        "advance_forecasts": {key: {"status": "QUEUED", "source_key": prior,
                                    "simulations": {"HYBRID": {"base": H}}}},
        "specialist_lab": {"forecasts": {key: {"status": "QUEUED", "source_key": prior,
                                "base": {"RITARDATARI": R, "DECINE": D, "CONTROLLO": C}}}},
        "ritardatari_evolutivo": {"active": {key: {
            "status": "QUEUED", "source_key": prior, "base": R}}},
    }
    return state, key, due


def actual(draw, base=None):
    return {"day": "2026-11-24", "draw": draw,
            "base": list(base or range(1, 21))}


class FusionTests(unittest.TestCase):
    def test_requires_evolutivo_pass_and_preview(self):
        state, key, due = fixture()
        state["ritardatari_evolutivo"]["active"].clear()
        prepare(state, due - timedelta(minutes=2))
        self.assertEqual(root(state)["published"], 0)
        self.assertFalse(root(state)["active"])
        self.assertNotIn("superambo_fusion", state["pending_notifications"][0])

    def test_prepared_pairs_and_dna_bonus(self):
        state, key, due = fixture()
        state["pending_notifications"][0]["dna_master"] = {"3": {"families": 4}}
        prepare(state, due - timedelta(minutes=2))
        a = root(state)["active"][key]["modes"]
        self.assertEqual(a[MODES[0]]["pair"], [1, 3])
        self.assertEqual(a[MODES[1]]["pair"], [1, 2])
        self.assertEqual(a[MODES[0]]["control"], [21, 22])
        self.assertTrue(a[MODES[0]]["dna_confirmed"])
        self.assertFalse(prepare(state, due - timedelta(minutes=2))["screened"] > 1)

    def test_unacknowledged_does_not_score(self):
        state, key, due = fixture()
        prepare(state, due - timedelta(minutes=2))
        reconcile(state, actual(101))
        self.assertEqual(root(state)["missed"], 1)
        self.assertEqual(root(state)["stats"][MODES[0]]["by_h"]["1"]["n"], 0)

    def test_h1_to_h5_and_duplicate_are_idempotent(self):
        state, key, due = fixture()
        prepare(state, due - timedelta(minutes=2))
        self.assertTrue(confirm(state, key, due - timedelta(minutes=1)))
        reconcile(state, actual(101))
        reconcile(state, actual(101))
        for draw in range(102, 106):
            reconcile(state, actual(draw, range(3, 23)))
        lab = root(state)
        self.assertEqual(lab["published"], 1)
        self.assertEqual(lab["stats"][MODES[0]]["by_h"]["1"]["n"], 1)
        self.assertEqual(lab["stats"][MODES[0]]["by_h"]["1"]["wins"], 1)
        self.assertEqual(lab["stats"][MODES[0]]["by_h"]["2"]["wins"], 0)
        self.assertEqual(lab["stats"][MODES[0]]["within5"]["wins"], 1)
        self.assertEqual(lab["stats"][MODES[0]]["within5"]["n"], 1)
        self.assertEqual(len(lab["recent"]), 1)
        self.assertFalse(lab["active"])

    def test_missing_concorso_fails_closed(self):
        state, key, due = fixture()
        prepare(state, due - timedelta(minutes=2))
        confirm(state, key, due - timedelta(minutes=1))
        reconcile(state, actual(101))
        reconcile(state, actual(103))
        lab = root(state)
        self.assertEqual(lab["missed"], 1)
        self.assertEqual(lab["stats"][MODES[0]]["by_h"]["2"]["n"], 0)

    def test_late_ack_does_not_count(self):
        state, key, due = fixture()
        prepare(state, due - timedelta(minutes=2))
        self.assertFalse(confirm(state, key, due))
        reconcile(state, actual(101))
        self.assertEqual(root(state)["stats"][MODES[0]]["published"], 0)
        self.assertEqual(root(state)["stats"][MODES[0]]["by_h"]["1"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
