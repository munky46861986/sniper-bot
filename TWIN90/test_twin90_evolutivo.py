"""RITARDATARI EVOLUTIVO V1: causality and scoring tests."""
import unittest
from datetime import datetime
from twin90_advance import ROME
from twin90_evolutivo import ages, filters, prepare, confirm, reconcile, describe, draw_index, format_extra


def fixture(accept=True):
    hist = [
        {"day":"2026-11-21","draw":i,"time":"00:00" if i==288 else "23:55",
         "base":list(range(1,21))}
        for i in range(2,289)
    ]+[{"day":"2026-11-22","draw":1,"time":"00:05","base":list(range(1,21))}]
    chosen=list(range(1,10))+list(range(21,32)) if accept else list(range(1,21))
    return {
        "schema":1,"history":hist,"latest":"2026-11-22#001",
        "pending_notifications":[{
            "type":"PREVIEW","key":"2026-11-22#002","source_key":"2026-11-22#001",
            "due_at":"2026-11-22T00:10:00+01:00","simulations":{}
        }],
        "specialist_lab":{"forecasts":{
            "2026-11-22#002":{
                "status":"QUEUED","source_key":"2026-11-22#001",
                "sent_at":None,
                "base":{"RITARDATARI":chosen,"CONTROLLO":list(range(41,61))}
            }
        }}
    }


def observed(n):
    return {"day":"2026-11-22","draw":n,"base":list(range(1,21))}


class EvolutivoTests(unittest.TestCase):
    def test_frozen_filters(self):
        s=fixture()
        h=s["history"]
        self.assertEqual(len(h),288)
        self.assertEqual(ages(h)[1],0)
        self.assertEqual(ages(h)[90],288)
        self.assertTrue(filters(h,list(range(1,10))+list(range(21,32)))["pass"])
        self.assertFalse(filters(h,list(range(1,21)))["pass"])
        self.assertEqual(filters(h,list(range(1,10))+list(range(21,32)))["missing_transitions"],0)
        self.assertEqual(draw_index("2026-11-21#288")+1,draw_index("2026-11-22#001"))

    def test_rejected_and_no_extra_message(self):
        s=fixture(False)
        now=datetime(2026,11,22,0,6,tzinfo=ROME)
        self.assertIsNone(prepare(s,now))
        self.assertEqual(describe(s)["rejected"],1)
        self.assertEqual(describe(s)["published"],0)
        self.assertEqual(len(s["pending_notifications"]),1)
        self.assertEqual(format_extra(s["pending_notifications"][0]),"")

    def test_preview_must_preexist_and_have_lead(self):
        s=fixture()
        self.assertIsNone(prepare(s,datetime(2026,11,22,0,9,45,tzinfo=ROME)))
        s["pending_notifications"]=[]
        self.assertIsNone(prepare(s,datetime(2026,11,22,0,6,tzinfo=ROME)))
        self.assertEqual(describe(s)["screened"],0)

    def test_ack_h1_h2_h5_and_duplicate(self):
        s=fixture()
        start=datetime(2026,11,22,0,6,tzinfo=ROME)
        self.assertEqual(prepare(s,start),"2026-11-22#002")
        self.assertIsNone(prepare(s,start))
        original=s["specialist_lab"]["forecasts"]["2026-11-22#002"]["base"]["RITARDATARI"]
        self.assertEqual(s["ritardatari_evolutivo"]["active"]["2026-11-22#002"]["base"],original)
        self.assertIn("EVOLUTIVO",format_extra(s["pending_notifications"][0]))
        self.assertTrue(confirm(s,"2026-11-22#002",datetime(2026,11,22,0,7,tzinfo=ROME)))
        self.assertEqual(describe(s)["published"],1)
        self.assertEqual(reconcile(s,observed(2))[0]["hits"],9)
        self.assertEqual(reconcile(s,observed(2)),[])
        for n in range(3,7):reconcile(s,observed(n))
        for h in (1,2,5):
            stat=describe(s)["stats"][str(h)]
            self.assertEqual((stat["n"],stat["hits"],stat["control_hits"]),(1,9,0))
        self.assertEqual(describe(s)["active"],0)

    def test_undelivered_and_late_never_scored(self):
        s=fixture()
        prepare(s,datetime(2026,11,22,0,6,tzinfo=ROME))
        self.assertEqual(reconcile(s,observed(2)),[])
        self.assertEqual(describe(s)["stats"]["1"]["n"],0)
        s=fixture()
        prepare(s,datetime(2026,11,22,0,6,tzinfo=ROME))
        self.assertFalse(confirm(s,"2026-11-22#002",datetime(2026,11,22,0,9,45,tzinfo=ROME)))
        self.assertEqual(reconcile(s,observed(2)),[])
        self.assertEqual(describe(s)["published"],0)

    def test_missing_draw_cannot_count_h2_h5(self):
        s=fixture()
        prepare(s,datetime(2026,11,22,0,6,tzinfo=ROME))
        confirm(s,"2026-11-22#002",datetime(2026,11,22,0,7,tzinfo=ROME))
        self.assertEqual(len(reconcile(s,observed(2))),1)
        self.assertEqual(reconcile(s,observed(4)),[])
        self.assertEqual(describe(s)["stats"]["2"]["n"],0)
        self.assertEqual(describe(s)["missed"],1)


if __name__=="__main__":unittest.main()
