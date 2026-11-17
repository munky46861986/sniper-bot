"""TWIN90 LIVE: integrity, no retrospective evaluation, idempotency and causality."""
import unittest
import numpy as np
from twin90_live import empty,check,parse_page,ingest,generate_virtual,compare

def example(i):
    base=sorted(((i+j-1)%90)+1 for j in range(20))
    extra=[n for n in range(1,91) if n not in base][:15]
    return {"day":"2026-11-17","draw":i,"time":"10:00",
            "base":base,"oro1":base[0],"oro2":base[1],"extra":extra}

def model():
    return {"bias":np.zeros(90),"trans":np.zeros((90,90)),
            "slot":np.zeros((6,90)),"oro1":np.ones(90),
            "oro2":np.ones(90),"extra":np.ones(90)}

class LiveTests(unittest.TestCase):
    def test_validation(self):
        check(example(1))
        wrong=example(1);wrong["extra"][0]=wrong["base"][0]
        with self.assertRaises(ValueError):check(wrong)
    def test_feed_parser(self):
        x=example(100)
        html="# 100 17 Novembre 2026 08:20 Numeri "+" ".join(map(str,x["base"]))+" Oro "+str(x["oro1"])+" Doppio Oro "+str(x["oro2"])+" Extra "+" ".join(map(str,x["extra"]))
        parsed=parse_page("<html><body>"+html+"</body></html>","2026-11-17")
        self.assertEqual(len(parsed),1)
        self.assertEqual(parsed[0]["base"],x["base"])
        self.assertEqual(parsed[0]["extra"],x["extra"])
    def test_bootstrap_does_not_retroactively_win(self):
        s=empty();r=ingest(s,[example(1),example(2)],model())
        self.assertEqual(r["status"],"BOOTSTRAP")
        self.assertEqual(s["evaluated"],0)
    def test_idempotency(self):
        s=empty();ingest(s,[example(1),example(2)],model())
        self.assertEqual(ingest(s,[example(1),example(2)],model())["new_draws"],0)
        self.assertEqual(s["evaluated"],0)
    def test_causal_progress(self):
        s=empty();ingest(s,[example(1)],model())
        r=ingest(s,[example(1),example(2)],model())
        self.assertEqual(r["new_draws"],1)
        self.assertEqual(s["evaluated"],1)
        self.assertEqual(s["stats"]["HYBRID"]["n"],1)
        self.assertEqual(ingest(s,[example(1),example(2)],model())["new_draws"],0)
        self.assertEqual(s["evaluated"],1)
    def test_deterministic_and_legal_virtual(self):
        a=generate_virtual([example(1)],model(),"2026-11-17#002","HYBRID")
        b=generate_virtual([example(1)],model(),"2026-11-17#002","HYBRID")
        self.assertEqual(a,b)
        check(a)
        self.assertEqual(compare(a,b)["base"],20)

if __name__=="__main__":unittest.main()
