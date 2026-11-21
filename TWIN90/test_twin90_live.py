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
        self.assertEqual(s["evaluated"],0)
        self.assertEqual(s["advance_checked"],0)
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



class DnaMasterTests(unittest.TestCase):
    def test_frozen_rules_and_warmup(self):
        from twin90_dna_master import fresh, signals, PAIRS, _observe, index
        from datetime import date, timedelta
        lab=fresh()
        origin=date(2026,11,14)
        for i in range(575):
            row={"day":str(origin+timedelta(days=i//288)),"draw":i%288+1,
                 "base":list(range(1,21))}
            _observe(lab,row)
        self.assertEqual(signals(lab,"2026-11-16#001"),{})
        _observe(lab,{"day":"2026-11-15","draw":288,"base":list(range(1,21))})
        self.assertEqual(len(lab["history"]),576)
        self.assertEqual(len(PAIRS),100)
        self.assertEqual(len(lab["occ"][0]),6)
        self.assertEqual(signals(lab,"2026-11-16#001"),signals(lab,"2026-11-16#001"))

    def test_ack_outcomes_and_gap(self):
        from twin90_dna_master import fresh, confirm, _observe, index, MODES
        from datetime import timedelta
        target="2026-11-17#002"
        lab=fresh(); state={"dna_master":lab}
        lab["last_index"]=index("2026-11-17#001")
        base={"created_at":"2026-11-17T10:00:00+01:00","due_at":"2026-11-17T10:05:00+01:00",
              "sent_at":None,"candidates":{"15":{"modes":list(MODES)}},"seen":[]}
        lab["active"][target]=base
        self.assertTrue(confirm(state,target,datetime(2026,11,17,10,1,tzinfo=ROME)))
        for i in range(2,12):
            _observe(lab,{"day":"2026-11-17","draw":i,"base":list(range(1,21))})
        for mode in MODES:
            self.assertEqual(lab["stats"][mode]["published"],1)
            for h in (1,2,5,10):
                self.assertEqual(lab["stats"][mode][str(h)],{"n":1,"hit":1})
        self.assertFalse(lab["active"])
        self.assertEqual(_observe(lab,{"day":"2026-11-17","draw":11,"base":list(range(1,21))}),[])
        _observe(lab,{"day":"2026-11-17","draw":13,"base":list(range(1,21))})
        self.assertEqual(len(lab["history"]),1)
        self.assertEqual(lab["gaps"],1)

    def test_undelivered_never_scores(self):
        from twin90_dna_master import fresh, _observe, index, MODES
        lab=fresh(); lab["last_index"]=index("2026-11-17#001")
        lab["active"]["2026-11-17#002"]={"created_at":"2026-11-17T10:00:00+01:00",
            "due_at":"2026-11-17T10:05:00+01:00","sent_at":None,
            "candidates":{"15":{"modes":list(MODES)}},"seen":[]}
        _observe(lab,{"day":"2026-11-17","draw":2,"base":list(range(1,21))})
        self.assertEqual(lab["stats"][MODES[0]]["1"]["n"],0)
        self.assertFalse(lab["active"])


    def test_dna_bootstrap_extends_backwards_without_scoring(self):
        from twin90_dna_master import fresh, tick, _observe, MODES
        from datetime import date, timedelta
        start=date(2026,11,19)
        rows=[{"day":str(start+timedelta(days=i//288)),
               "draw":i%288+1,"time":"00:05","base":list(range(1,21))}
              for i in range(576)]
        lab=fresh()
        for row in rows[-6:]: _observe(lab,row)
        state={"dna_master":lab,"history":rows[-1:],"pending_notifications":[]}
        result=tick(state,rows,now=datetime(2026,11,22,0,5,tzinfo=ROME))
        self.assertEqual(result["warmup"],576)
        for m in MODES:
            self.assertEqual(result["stats"][m]["published"],0)
            self.assertEqual(result["stats"][m]["1"]["n"],0)

    def test_dna_bootstrap_does_not_fill_missing_draw(self):
        from twin90_dna_master import fresh, tick, _observe
        from datetime import date, timedelta
        start=date(2026,11,19)
        rows=[{"day":str(start+timedelta(days=i//288)),
               "draw":i%288+1,"time":"00:05","base":list(range(1,21))}
              for i in range(576)]
        lab=fresh()
        for row in rows[-6:]: _observe(lab,row)
        state={"dna_master":lab,"history":rows[-1:],"pending_notifications":[]}
        result=tick(state,rows[:500]+rows[501:],now=datetime(2026,11,22,0,5,tzinfo=ROME))
        self.assertEqual(result["warmup"],75)


if __name__=="__main__":unittest.main()
