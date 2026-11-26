"""Synthetic fixed-window and time-safety tests for AMBATA GUIDA V1."""
import unittest
from datetime import timedelta

from twin90_advance import next_concorso
from twin90_ambata_guida import (choose, prepare, confirm, reconcile, root,
                                LOOKBACK, SLOT_EVERY_DRAWS)


def fixture():
    last = {"day": "2026-11-26", "draw": 107, "time": "08:45",
            "base": list(range(1, 21))}
    key, due = next_concorso(last)
    history = [{"day": "2026-11-26", "draw": x,
                "time": "08:45", "base": list(range(1, 21))}
               for x in range(48, 107)] + [last]
    prior = "2026-11-26#107"
    r = list(range(1, 21))
    d = list(range(1, 11)) + list(range(41, 51))
    h = list(range(11, 31))
    state = {
        "latest": prior, "history": history,
        "pending_notifications": [{
            "type": "PREVIEW", "key": key,
            "source_key": prior, "due_at": due.isoformat(),
        }],
        "advance_forecasts": {key: {
            "status": "QUEUED", "source_key": prior,
            "simulations": {"HYBRID": {"base": h}},
        }},
        "specialist_lab": {"forecasts": {key: {
            "status": "QUEUED", "source_key": prior,
            "base": {"DECINE": d, "RITARDATARI": r},
        }}},
    }
    return state, key, due


def draw(n, base):
    return {"day": "2026-11-26", "draw": n, "base": list(base)}


class AmbataGuidaTests(unittest.TestCase):
    def test_frozen_prep_and_single_hour_slot(self):
        s, key, due = fixture()
        self.assertEqual(len(s["history"]), LOOKBACK)
        self.assertEqual(int(key[-3:]) % SLOT_EVERY_DRAWS, 0)
        self.assertEqual(root(s)["published"], 0)
        prepare(s, due - timedelta(minutes=2))
        a = root(s)["active"][key]
        self.assertEqual(a["anchor"], 1)
        self.assertEqual(a["half_appearances"], [30, 30])
        self.assertEqual(a["pair"], [1, 2])
        self.assertEqual(a["control"], [1, 2])
        self.assertEqual(root(s)["screened"], 1)
        prepare(s, due - timedelta(minutes=2))
        self.assertEqual(root(s)["screened"], 1)
        self.assertEqual(root(s)["published"], 0)

    def test_stops_and_full_five_payout(self):
        s, key, due = fixture()
        prepare(s, due - timedelta(minutes=2))
        self.assertTrue(confirm(s, key, due - timedelta(minutes=1)))
        reconcile(s, draw(108, range(1, 21)))
        reconcile(s, draw(108, range(1, 21)))
        for n in range(109, 113):
            reconcile(s, draw(n, range(21, 41)))
        lab = root(s)
        self.assertEqual(lab["published"], 1)
        self.assertEqual(lab["completed"], 1)
        self.assertEqual(lab["stats"]["anchor_h1"], 1)
        self.assertEqual(lab["stats"]["pair_h1"], 1)
        self.assertEqual(lab["stats"]["pair_h5"], 1)
        self.assertEqual(lab["stats"]["FULL5"]["net_eur"], 9)
        self.assertEqual(lab["stats"]["STOP1"]["net_eur"], 13)
        self.assertEqual(lab["daily"]["2026-11-26"]["STOP1"]["net_eur"], 13)
        self.assertEqual(lab["weekly"]["2026-W48"]["FULL5"]["net_eur"], 9)
        self.assertFalse(lab["active"])

    def test_no_delivery_no_scoring(self):
        s, key, due = fixture()
        prepare(s, due - timedelta(minutes=2))
        reconcile(s, draw(108, range(1, 21)))
        self.assertEqual(root(s)["missed"], 1)
        self.assertEqual(root(s)["stats"]["n"], 0)
        self.assertEqual(root(s)["stats"]["FULL5"]["spent_eur"], 0)

    def test_late_delivery_and_missing_draw(self):
        s, key, due = fixture()
        prepare(s, due - timedelta(minutes=2))
        self.assertFalse(confirm(s, key, due))
        reconcile(s, draw(108, range(1, 21)))
        self.assertEqual(root(s)["missed"], 1)
        t, key, due = fixture()
        prepare(t, due - timedelta(minutes=2))
        self.assertTrue(confirm(t, key, due - timedelta(minutes=1)))
        reconcile(t, draw(108, range(1, 21)))
        reconcile(t, draw(110, range(1, 21)))
        self.assertEqual(root(t)["missed"], 1)
        self.assertEqual(root(t)["completed"], 0)

    def test_missing_forecasts_or_lookback(self):
        s, key, due = fixture()
        s["specialist_lab"]["forecasts"].clear()
        prepare(s, due - timedelta(minutes=2))
        self.assertEqual(root(s)["screened"], 0)
        t, key, due = fixture()
        t["history"] = t["history"][-10:]
        self.assertIsNone(choose(t["history"], {"DECINE": [], "RITARDATARI": []}, []))
        prepare(t, due - timedelta(minutes=2))
        self.assertEqual(root(t)["skipped"], 1)

    def test_future_data_never_in_lookback(self):
        s, key, due = fixture()
        before = choose(s["history"], s["specialist_lab"]["forecasts"][key]["base"],
                        s["advance_forecasts"][key]["simulations"]["HYBRID"]["base"])
        self.assertEqual(before["anchor"], 1)
        new_history = list(s["history"])
        new_history.append(draw(108, range(21, 41)))
        after = choose(new_history, s["specialist_lab"]["forecasts"][key]["base"],
                       s["advance_forecasts"][key]["simulations"]["HYBRID"]["base"])
        self.assertNotEqual(before["frequency_60"], after["frequency_60"])


if __name__ == "__main__":
    unittest.main()
