"""TWIN90 Telegram: format e anti-duplicati verificati senza inviare messaggi."""
import unittest
from twin90_telegram import format_draw, format_summary, publish


def example():
    real={"day":"2026-11-17","draw":164,"time":"13:40",
          "base":list(range(1,21)),"oro1":1,"oro2":2,"extra":list(range(21,36))}
    v={"HYBRID":{"base":list(range(1,21)),"oro1":1,"oro2":2,
                 "extra":list(range(21,36))},
       "UNIFORM":{"base":list(range(1,21)),"oro1":1,"oro2":2,
                  "extra":list(range(21,36))}}
    scores={k:{"base":20,"extra":15,"gold1":1,"gold2":1,"both":1} for k in v}
    return {"type":"DRAW","key":"2026-11-17#164","actual":real,
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
    def test_summary(self):
        msg=format_summary({"type":"SUMMARY","count":14,"first_key":"2026-11-17#100","last_key":"2026-11-17#113"})
        self.assertIn("14 concorsi",msg)


if __name__=="__main__":unittest.main()
