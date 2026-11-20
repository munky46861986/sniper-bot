"""Offline causality and independence tests for SPECIALIST LAB LIVE."""
import unittest
from datetime import datetime, timedelta

from twin90_advance import ROME
from twin90_specialists import (
    MODES, _weights, confirm_sent, decine_counts, describe, generate,
    prepare, reconcile, score
)
from twin90_telegram import format_preview, format_draw, publish


def draw(i):
    base=sorted({((i+j-2)%90)+1 for j in range(1,21)})
    rest=[n for n in range(1,91) if n not in base]
    return {"day":"2026-11-20","draw":i,"time":"10:00",
            "base":base,"oro1":base[0],"oro2":base[1],"extra":rest[:15]}


def fixture():
    from twin90_live import generate_virtual
    # TWIN90's primary preview exists and is queued for #002, after #001.
    source=draw(1)
    pending={"type":"PREVIEW","key":"2026-11-20#002",
             "source_key":"2026-11-20#001",
             "due_at":"2026-11-20T10:05:00+01:00",
             "simulations":{}}
    state={"schema":1,"latest":"2026-11-20#001","history":[source],
           "telegram_welcome_sent":True,"pending_notifications":[pending],
           "advance_forecasts":{"2026-11-20#002":{
               "due_at":pending["due_at"],"created_at":"2026-11-20T10:01:00+01:00",
               "source_key":pending["source_key"],"sent_at":None}}}
    return state


class SpecialistTests(unittest.TestCase):
    def test_four_independent_base_selections(self):
        hist=[draw(i) for i in range(1,101)]
        for mode in MODES:
            out=generate(hist,"2026-11-20#101",mode)
            self.assertEqual(len(out),20)
            self.assertEqual(len(set(out)),20)
            self.assertTrue(all(1<=n<=90 for n in out))
            self.assertEqual(out,generate(hist,"2026-11-20#101",mode))
    def test_ritardatari_depend_only_on_gaps(self):
        history=[draw(1)]*25
        weights=_weights(history,"RITARDATARI")
        self.assertGreater(weights[89],weights[0])
        self.assertEqual(len(weights),90)
    def test_frequenti_depend_only_on_counts(self):
        history=[draw(1)]*40
        weights=_weights(history,"FREQUENTI")
        self.assertGreater(weights[0],weights[89])
    def test_decine_group_only(self):
        history=[draw(i) for i in range(1,81)]
        weights=_weights(history,"DECINE")
        for group in range(9):
            self.assertEqual(len(set(weights[group*10:(group+1)*10])),1)
        self.assertEqual(decine_counts(list(range(1,21))),[10,10,0,0,0,0,0,0,0])
    def test_prepare_attaches_to_existing_preview(self):
        s=fixture()
        k=prepare(s,now=datetime(2026,11,20,10,1,tzinfo=ROME))
        self.assertEqual(k,"2026-11-20#002")
        self.assertIn("specialists",s["pending_notifications"][0])
        self.assertEqual(set(s["pending_notifications"][0]["specialists"]),set(MODES))
        self.assertEqual(prepare(s,now=datetime(2026,11,20,10,2,tzinfo=ROME)),None)
        self.assertEqual(len(s["pending_notifications"]),1)
        text=format_preview(s["pending_notifications"][0])
        for mode in MODES:self.assertIn(mode,text)
    def test_no_preview_no_specialist_prediction(self):
        s=fixture();s["pending_notifications"]=[]
        self.assertIsNone(prepare(s,now=datetime(2026,11,20,10,1,tzinfo=ROME)))
    def test_pre_sent_and_scored_once(self):
        s=fixture()
        prepare(s,now=datetime(2026,11,20,10,1,tzinfo=ROME))
        k="2026-11-20#002"
        self.assertTrue(confirm_sent(s,k,when=datetime(2026,11,20,10,2,tzinfo=ROME)))
        item=reconcile(s,draw(2),k)
        self.assertEqual(item["total"],1)
        self.assertEqual(set(item["results"]),set(MODES))
        self.assertIsNone(reconcile(s,draw(2),k))
        for mode in MODES:self.assertEqual(s["specialist_lab"]["stats"][mode]["n"],1)
        self.assertEqual(describe(s)["checked"],1)
    def test_missing_telegram_ack_not_scored(self):
        s=fixture()
        prepare(s,now=datetime(2026,11,20,10,1,tzinfo=ROME))
        self.assertIsNone(reconcile(s,draw(2),"2026-11-20#002"))
        self.assertEqual(describe(s)["checked"],0)
        self.assertEqual(describe(s)["without_preview"],1)
    def test_expired_previews_cannot_count(self):
        s=fixture()
        self.assertIsNone(prepare(s,now=datetime(2026,11,20,10,5,tzinfo=ROME)))
        self.assertEqual(len(s["pending_notifications"]),1)
    def test_existing_telegram_ack_triggers_specialist_ack(self):
        s=fixture()
        prepare(s,now=datetime(2026,11,20,10,1,tzinfo=ROME))
        sent=[]
        publish(s,sent.append,now_fn=lambda:datetime(2026,11,20,10,2,tzinfo=ROME))
        self.assertEqual(len(sent),1)
        self.assertIn("SPECIALIST LAB",sent[0])
        self.assertEqual(s["specialist_lab"]["forecasts"]["2026-11-20#002"]["status"],"SENT_BEFORE_DRAW")
        self.assertEqual(publish(s,sent.append,now_fn=lambda:datetime(2026,11,20,10,2,tzinfo=ROME)),0)
    def test_post_draw_message_has_specialist_scores(self):
        s=fixture();prepare(s,now=datetime(2026,11,20,10,1,tzinfo=ROME))
        confirm_sent(s,"2026-11-20#002",when=datetime(2026,11,20,10,2,tzinfo=ROME))
        result=reconcile(s,draw(2),"2026-11-20#002")
        item={"type":"DRAW","actual":draw(2),"pre_issued":True,"issued_at":"2026-11-20T10:02:00+01:00",
              "simulations":{"HYBRID":{"base":draw(2)["base"],"oro1":1,"oro2":2,"extra":draw(2)["extra"]},
                             "UNIFORM":{"base":draw(2)["base"],"oro1":1,"oro2":2,"extra":draw(2)["extra"]}},
              "comparison":{"HYBRID":{"base":20,"extra":15,"gold1":0,"gold2":0},
                            "UNIFORM":{"base":20,"extra":15,"gold1":0,"gold2":0}},
              "specialist_report":result}
        msg=format_draw(item)
        self.assertIn("SPECIALIST LAB",msg)
        for mode in MODES:self.assertIn(mode+":",msg)
    def test_score_meaning(self):
        x=score(list(range(1,21)),list(range(1,21)))
        self.assertEqual(x["hits"],20)
        self.assertEqual(x["decine_abs_error"],0)
        self.assertEqual(score(list(range(1,21)),list(range(71,91)))["hits"],0)


if __name__=="__main__":unittest.main()
