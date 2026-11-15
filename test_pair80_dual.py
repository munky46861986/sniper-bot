"""Test sintetici di regressione: PAIR80 SINGOLO e DOPPIO, no rete."""
import unittest
from types import SimpleNamespace
from pair80_dual import ensure, seed, process, report, _select_pair

DAY = "2026-11-15"
REST = [1,2,3,11,12,13,21,22,23,31,32,33,41,42,43,61,62,71,72,81]
SOURCE = list(range(51, 61))

def row(draw, source):
    nums = sorted(set(source) | set(REST[:20-len(source)]))
    assert len(nums) == 20
    return {"day":DAY, "draw_id":draw, "nums":nums}

class DualTests(unittest.TestCase):
    def triggered(self):
        tr = SimpleNamespace(data={"legacy": {"keep": True}}, dirty=False)
        old = [row(i, SOURCE[:5] if i == 78 else SOURCE[:2])
               for i in range(1,80)]
        self.assertIn("79/80", seed(tr, old))
        self.assertEqual(ensure(tr)["totals"]["SINGOLO"]["signals"], 0)
        result = process(tr, row(80, SOURCE[5:10]))
        self.assertEqual(len(result["signals"]), 2)
        self.assertIn("SINGOLO", result["signals"][0])
        self.assertIn("DOPPIO", result["signals"][1])
        self.assertEqual(tr.data["legacy"], {"keep": True})
        return tr

    def test_live_both_and_hit_h1(self):
        tr = self.triggered()
        result = process(tr, row(81, SOURCE[:2]))
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(all("H1: AMBO HIT" in x for x in result["results"]))
        st = ensure(tr)
        for mode in ("SINGOLO", "DOPPIO"):
            self.assertEqual(st["totals"][mode]["closed_h2"], 1)
            self.assertEqual(st["totals"][mode]["hits_h2"], 1)
            self.assertEqual(st["totals"][mode]["stakes_virtual"], 1.0)
            self.assertEqual(st["totals"][mode]["returns_virtual"], 14.0)
        self.assertFalse(process(tr, row(81,SOURCE[:2]))["new"])
        self.assertIn("DOPPIO", report(tr))

    def test_h1_miss_h2_hit_and_gap(self):
        tr = self.triggered()
        out = process(tr, row(81, SOURCE[2:4]))
        self.assertEqual(len(out["results"]), 2)
        self.assertTrue(all("H1: MISS" in x for x in out["results"]))
        out = process(tr, row(82, SOURCE[:2]))
        self.assertEqual(len(out["results"]), 2)
        self.assertTrue(all("H2: AMBO HIT" in x for x in out["results"]))
        for mode in ("SINGOLO", "DOPPIO"):
            self.assertEqual(ensure(tr)["totals"][mode]["stakes_virtual"], 2.0)
        out = process(tr, row(83, SOURCE[:5]))
        self.assertEqual(len(out["signals"]), 1)
        out = process(tr, row(86, SOURCE[:2]))
        self.assertTrue(out["gap"])
        self.assertEqual(len(ensure(tr)["history"]), 1)
        self.assertEqual(ensure(tr)["totals"]["SINGOLO"]["interrupted"], 1)

    def test_seed_no_backfill_tiebreak(self):
        tr = SimpleNamespace(data={}, dirty=False)
        self.assertIn("80/80", seed(tr, [row(i, []) for i in range(1,81)]))
        self.assertEqual(ensure(tr)["totals"]["SINGOLO"]["signals"],0)
        pair,count = _select_pair([{"nums":list(range(1,21))}]*80, 0)
        self.assertEqual(pair, (1,2))
        self.assertEqual(count, 80)

if __name__ == "__main__":
    unittest.main(verbosity=2)
