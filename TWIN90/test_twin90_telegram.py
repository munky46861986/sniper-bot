"""TWIN90 Telegram: format e anti-duplicati verificati senza inviare messaggi."""
import unittest
from datetime import datetime
from twin90_telegram import format_draw, format_summary, format_preview, publish
from twin90_advance import ROME


def example():
    real={"day":"2026-11-17","draw":164,"time":"13:40",
          "base":list(range(1,21)),"oro1":1,"oro2":2,"extra":list(range(21,36))}
    v={"HYBRID":{"base":list(range(1,21)),"oro1":1,"oro2":2,
                 "extra":list(range(21,36))},
       "UNIFORM":{"base":list(range(1,21)),"oro1":1,"oro2":2,
                  "extra":list(range(21,36))}}
    scores={k:{"base":20,"extra":15,"gold1":1,"gold2":1,"both":1} for k in v}
    return {"type":"DRAW","key":"2026-11-17#164","actual":real,
            "pre_issued":True,"issued_at":"2026-11-17T13:36:00+01:00",
            "simulations":v,"comparison":scores}


class TelegramTests(unittest.TestCase):
    def test_format_real_and_virtual(self):
        msg=format_draw(example())
        self.assertIn("ESTRAZIONE REALE",msg)
        self.assertIn("DOPPIO ORO",msg)
        self.assertIn("EXTRA",msg)
        self.assertIn("HYBRID",msg)
        self.assertIn("UNIFORM",msg)
    def test_welcome_only_once(self):
        state={"telegram_welcome_sent":False,"pending_notifications":[]}
        sent=[]
        self.assertEqual(publish(state,sent.append),1)
        self.assertEqual(publish(state,sent.append),0)
        self.assertEqual(len(sent),1)
    def test_deliver_then_clear(self):
        state={"telegram_welcome_sent":True,"pending_notifications":[example()]}
        sent=[]
        self.assertEqual(publish(state,sent.append),1)
        self.assertEqual(len(state["pending_notifications"]),0)
        self.assertEqual(publish(state,sent.append),0)
    def test_failure_keeps_pending(self):
        state={"telegram_welcome_sent":True,"pending_notifications":[example()]}
        def fail(_):
            raise RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            publish(state,fail)
        self.assertEqual(len(state["pending_notifications"]),1)
    def test_no_advance_draw_label(self):
        v=example()
        v["type"]="DRAW_NOT_PREVIEWED"
        v.pop("pre_issued")
        msg=format_draw(v)
        self.assertIn("Nessuna simulazione preventiva",msg)
        self.assertNotIn("RISULTATO DELLE SIMULAZIONI INVIATE",msg)

    def test_preventive_message(self):
        v=example()
        pre={"type":"PREVIEW","key":v["key"],
             "source_key":"2026-11-17#163",
             "due_at":"2026-11-17T13:40:00+01:00",
             "simulations":v["simulations"]}
        msg=format_preview(pre)
        self.assertIn("SIMULAZIONE PREVENTIVA",msg)
        self.assertIn("13:40",msg)
        self.assertIn("HYBRID",msg)
        self.assertIn("UNIFORM",msg)
        self.assertIn("NON ESTRAZIONI REALI",msg)

    def test_preview_ack_and_idempotence(self):
        v=example()
        key=v["key"]
        pre={"type":"PREVIEW","key":key,"source_key":"2026-11-17#163",
             "due_at":"2026-11-17T13:40:00+01:00",
             "simulations":v["simulations"]}
        record={"due_at":pre["due_at"],"created_at":"2026-11-17T13:35:00+01:00",
                "source_key":"2026-11-17#163",
                "simulations":v["simulations"],"sent_at":None}
        s={"telegram_welcome_sent":True,"pending_notifications":[pre],
           "advance_forecasts":{key:record}}
        sent=[]
        clock=lambda:datetime(2026,11,17,13,36,tzinfo=ROME)
        self.assertEqual(publish(s,sent.append,now_fn=clock),1)
        self.assertTrue(record["sent_at"])
        self.assertEqual(record["status"],"SENT_BEFORE_DRAW")
        self.assertEqual(publish(s,sent.append,now_fn=clock),0)

    def test_expired_preview_not_delivered(self):
        v=example()
        key=v["key"]
        pre={"type":"PREVIEW","key":key,"source_key":"2026-11-17#163",
             "due_at":"2026-11-17T13:40:00+01:00",
             "simulations":v["simulations"]}
        record={"due_at":pre["due_at"],"sent_at":None}
        s={"telegram_welcome_sent":True,"pending_notifications":[pre],
           "advance_forecasts":{key:record}}
        sent=[]
        clock=lambda:datetime(2026,11,17,13,40,tzinfo=ROME)
        self.assertEqual(publish(s,sent.append,now_fn=clock),0)
        self.assertEqual(sent,[])
        self.assertEqual(record["status"],"EXPIRED_UNDELIVERED")

    def test_summary(self):
        msg=format_summary({"type":"SUMMARY","count":14,"first_key":"2026-11-17#100","last_key":"2026-11-17#113"})
        self.assertIn("14 concorsi",msg)


if __name__=="__main__":unittest.main()
