import tempfile
import unittest
from pathlib import Path
import numpy as np
from lotto_twin90 import (DECADES, CANDIDATES, load_csv, load_model, generate,
                          parse_set, build_features, fit, score, probabilities, BASE_P)

HERE = Path(__file__).parent

class Twin90Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m,cls.desc=load_model(HERE/'twin90_model_2025_2026.json')

    def test_nine_decades_partition(self):
        self.assertEqual(len(DECADES),9)
        self.assertTrue(all(len(v)==10 for v in DECADES))
        self.assertEqual(set(sum((list(v) for v in DECADES), [])),set(range(1,91)))
        self.assertEqual(DECADES[0],(90,1,2,3,4,5,6,7,8,9))

    def test_every_draw_has_valid_base_gold_and_extra(self):
        rows=generate(self.m,300,"2026-11-18",42,CANDIDATES['UNIFORM'])
        self.assertEqual(rows[287]['date'],'2026-11-18')
        self.assertEqual(rows[287]['draw'],288)
        self.assertEqual(rows[288]['date'],'2026-11-19')
        self.assertEqual(rows[288]['draw'],1)
        for row in rows:
            base=set(parse_set(row['base'],20))
            extra=set(parse_set(row['extra'],15))
            self.assertEqual(len(base),20)
            self.assertEqual(len(extra),15)
            self.assertFalse(base&extra)
            self.assertIn(int(row['oro1']),base)
            self.assertIn(int(row['oro2']),base)
            self.assertNotEqual(row['oro1'],row['oro2'])

    def test_seed_reproducibility_and_independent_seeds(self):
        a=generate(self.m,8,"2026-11-18",322,CANDIDATES['HYBRID'])
        b=generate(self.m,8,"2026-11-18",322,CANDIDATES['HYBRID'])
        c=generate(self.m,8,"2026-11-18",323,CANDIDATES['HYBRID'])
        self.assertEqual(a,b)
        self.assertNotEqual(a,c)

    def test_no_look_ahead_in_features(self):
        # synthetic small historical series with known valid metadata
        n=330
        x=np.zeros((n,90),dtype=np.uint8)
        for i in range(n): x[i,np.arange(i, i+20)%90]=1
        from lotto_twin90 import Draws
        day=np.asarray(['2025-01-01']*n)
        draw=np.arange(n)%288+1
        gold1=np.arange(n)%90
        gold2=(np.arange(n)+1)%90
        extra=np.zeros_like(x)
        for i in range(n):extra[i,np.arange(i+20,i+35)%90]=1
        dataset=Draws(day,draw,x,gold1,gold2,extra,np.ones(n,dtype=bool),[])
        m=fit(dataset,200)
        f1=build_features(dataset,m,299,300)
        clone=Draws(day,draw,x.copy(),gold1.copy(),gold2.copy(),extra.copy(),np.ones(n,dtype=bool),[])
        clone.base[300:]=0
        clone.oro1[300:]=0
        clone.oro2[300:]=0
        clone.extra[300:]=0
        f2=build_features(clone,m,299,300)
        self.assertTrue(np.array_equal(f1,f2))

    def test_uniform_model_is_correct_reference(self):
        p=probabilities(np.zeros((10,90,10),dtype=np.float32),CANDIDATES['UNIFORM'])
        self.assertTrue(np.allclose(p,BASE_P))
        self.assertTrue(np.isfinite(score(np.zeros_like(p),p)['logloss']))

if __name__=='__main__':unittest.main(verbosity=2)