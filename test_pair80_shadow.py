import unittest
from types import SimpleNamespace
from pair80_shadow import ensure, seed, process, report, _select_pair

DAY = "2026-11-15"
BASE = list(range(1, 51))
SOURCE = list(range(51, 61))

def row(draw, source):
    nums = sorted(set(source) | set(BASE[:20-len(source)]))
    return {"day": DAY, "draw_id": draw, "nums": nums}

class Pair80Tests(unittest.TestCase):
    def test_warmup_trigger_win_and_gap(self):
        tr = SimpleNamespace(data={}, dirty=False)
        old = [row(i, SOURCE[:5] if i == 78 else SOURCE[:2])
               for i in range(1, 80)]
        self.assertIn("79/80", seed(tr, old))
        self.assertEqual(ensure(tr)["totals"]["signals"], 0)
        trig = process(tr, row(80, SOURCE[5:10]))
        self.assertEqual(len(trig["signals"]), 1)
        sig = list(ensure(tr)["active"].values())[0]
        self.assertEqual(sig["decina"], "51-60")
        hit = process(tr, row(81, SOURCE))
        self.assertIn("H1 HIT", hit["results"][0])
        totals = ensure(tr)["totals"]
        self.assertEqual(totals["closed_h2"], 1)
        self.assertEqual(totals["hits_h2"], 1)
        self.assertEqual(totals["stakes_virtual"], 1.0)
        self.assertEqual(totals["returns_virtual"], 14.0)
        gap = process(tr, row(84, SOURCE[:2]))
        self.assertTrue(gap["gap"])
        self.assertEqual(len(ensure(tr)["history"]), 1)
        self.assertFalse(process(tr, row(84, SOURCE[:2]))["new"])

    def test_seed_is_non_retroactive_and_tie_break(self):
        tr = SimpleNamespace(data={}, dirty=False)
        rows = [row(i, []) for i in range(1, 81)]
        self.assertIn("80/80", seed(tr, rows))
        self.assertEqual(ensure(tr)["totals"]["signals"], 0)
        pick, count = _select_pair(rows, 0)
        self.assertEqual(pick, (1, 2))
        self.assertEqual(count, 80)

if __name__ == "__main__":
    unittest.main(verbosity=2)
