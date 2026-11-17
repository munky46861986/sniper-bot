"""TWIN90 LIVE: integrity, no retrospective evaluation, idempotency and causality."""
import unittest
from datetime import datetime
import numpy as np
from twin90_live import empty,check,parse_page,ingest,generate_virtual,compare
from twin90_advance import next_concorso, make_preview, confirm_sent, ROME

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
        self.assertEqual(s["advance_checked"],0)
        self.assertEqual(s["advance_no_preview"],1)
        self.assertEqual(s["stats"]["HYBRID"]["n"],0)
        self.assertEqual(ingest(s,[example(1),example(2)],model())["new_draws"],0)
        self.assertEqual(s["evaluated"],1)
    def test_forecast_published_before_draw_counts(self):
        s=empty()
        ing=ingest(s,[example(1)],model(),stamp="2026-11-17T10:01:00+01:00")
        self.assertEqual(ing["next_preview"],"2026-11-17#002")
        forecast=s["advance_forecasts"]["2026-11-17#002"]
        self.assertIsNone(forecast["sent_at"])
        confirm_sent(s,"2026-11-17#002",when=datetime(2026,11,17,10,2,tzinfo=ROME))
        result=ingest(s,[example(1),example(2)],model(),stamp="2026-11-17T10:06:00+01:00")
        self.assertEqual(result["advance_checked"],1)
        self.assertEqual(s["advance_stats"]["HYBRID"]["n"],1)
        self.assertTrue(any(r["type"]=="DRAW" and r["pre_issued"]
                            for r in s["pending_notifications"]))
        self.assertEqual(s["evaluated"],0)
    def test_forecast_not_delivered_never_scores(self):
        s=empty()
        ingest(s,[example(1)],model(),stamp="2026-11-17T10:01:00+01:00")
        ingest(s,[example(1),example(2)],model(),stamp="2026-11-17T10:06:00+01:00")
        self.assertEqual(s["advance_checked"],0)
        self.assertEqual(s["advance_no_preview"],1)
        self.assertFalse(any(x["type"]=="PREVIEW" for x in s["pending_notifications"]))
        self.assertTrue(any(x["type"]=="DRAW_NOT_PREVIEWED" for x in s["pending_notifications"]))
    def test_late_creation_is_blocked(self):
        s=empty()
        ingest(s,[example(1)],model(),stamp="2026-11-17T10:05:01+01:00")
        self.assertNotIn("2026-11-17#002",s["advance_forecasts"])
    def test_rollover_at_midnight(self):
        row=example(288)
        row["time"]="00:00"
        k,due=next_concorso(row)
        self.assertEqual(k,"2026-11-18#001")
        self.assertEqual(due.strftime("%Y-%m-%d %H:%M"),"2026-11-18 00:05")
    def test_forecast_deterministic_and_saved(self):
        s=empty()
        ingest(s,[example(1)],model(),stamp="2026-11-17T10:01:00+01:00")
        f=s["advance_forecasts"]["2026-11-17#002"]
        for mode in ("HYBRID","UNIFORM"):
            self.assertEqual(f["simulations"][mode],
                             generate_virtual([example(1)],model(),"2026-11-17#002",mode))

    def test_deterministic_and_legal_virtual(self):
        a=generate_virtual([example(1)],model(),"2026-11-17#002","HYBRID")
        b=generate_virtual([example(1)],model(),"2026-11-17#002","HYBRID")
        self.assertEqual(a,b)
        check(a)
        self.assertEqual(compare(a,b)["base"],20)

if __name__=="__main__":unittest.main()
