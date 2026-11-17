"""Causal, pre-draw TWIN90 predictions. Read-only, no wagering.

A prediction counts in advance_stats only after Telegram confirms delivery
BEFORE the draw. Retrospective or undelivered forecasts are not scored as advance.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
MIN_LEAD_SECONDS = 30
MAX_FORECASTS = 400

def ts(value):
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=ROME) if dt.tzinfo is None else dt.astimezone(ROME)

def next_concorso(last):
    current = datetime.strptime(last["day"]+" "+last["time"].replace(".",":"),"%Y-%m-%d %H:%M").replace(tzinfo=ROME)
    n = int(last["draw"])
    if current.hour == 0 and current.minute == 0 and n > 1:
        current += timedelta(days=1)
    upcoming = current+timedelta(minutes=5)
    target = (upcoming.date().isoformat() if n==288 else last["day"])
    num = 1 if n==288 else n+1
    return f"{target}#{num:03d}",upcoming

def ensure(state):
    state.setdefault("advance_forecasts",{})
    state.setdefault("advance_checked",0)
    state.setdefault("advance_no_preview",0)
    state.setdefault("advance_stats",{
        x:{"n":0,"base_sum":0,"extra_sum":0,
           "gold1_hits":0,"gold2_hits":0,"both_gold_hits":0}
        for x in ("UNIFORM","HYBRID")
    })
    return state

def expire_undelivered(state,now=None):
    now=now or datetime.now(ROME)
    ensure(state)
    saved=[]
    for msg in state.setdefault("pending_notifications",[]):
        if msg.get("type") != "PREVIEW":
            saved.append(msg)
            continue
        target=msg["key"]
        info=state["advance_forecasts"].get(target)
        if info and not info.get("sent_at") and now >= ts(info["due_at"])-timedelta(seconds=MIN_LEAD_SECONDS):
            info["status"]="EXPIRED_UNDELIVERED"
            continue
        saved.append(msg)
    state["pending_notifications"]=saved

def make_preview(state,model,generate_fn,now=None):
    """Register a forecast only if there is still time to send it beforehand."""
    ensure(state)
    now=now or datetime.now(ROME)
    if not state.get("history") or not state.get("latest"):
        return None
    key,due=next_concorso(state["history"][-1])
    if now>=due-timedelta(seconds=MIN_LEAD_SECONDS):
        return None
    if key in state["advance_forecasts"]:
        return None
    history=state["history"]
    sims={m:generate_fn(history,model,key,m) for m in ("HYBRID","UNIFORM")}
    record={"key":key,"source_key":state["latest"],"created_at":now.isoformat(),
            "due_at":due.isoformat(),"sent_at":None,"status":"QUEUED",
            "simulations":sims}
    state["advance_forecasts"][key]=record
    state.setdefault("pending_notifications",[]).append({
        "type":"PREVIEW","key":key,"source_key":state["latest"],
        "due_at":record["due_at"],"simulations":sims
    })
    if len(state["advance_forecasts"])>MAX_FORECASTS:
        keys=sorted(state["advance_forecasts"])
        for stale in keys[:-MAX_FORECASTS]:
            state["advance_forecasts"].pop(stale,None)
    return key

def confirm_sent(state,key,when=None):
    """Call ONLY after Telegram API acknowledges sending a PREVIEW."""
    ensure(state)
    when=when or datetime.now(ROME)
    record=state["advance_forecasts"].get(key)
    if record is None:
        return False
    record["sent_at"]=when.isoformat()
    sent_early=when < ts(record["due_at"])-timedelta(seconds=MIN_LEAD_SECONDS)
    record["status"]="SENT_BEFORE_DRAW" if sent_early else "SENT_TOO_LATE"
    return sent_early

def reconcile(state,actual,key,compare_fn):
    """Compare only a previously delivered PREVIEW, never recompute the target."""
    ensure(state)
    record=state["advance_forecasts"].get(key)
    state["pending_notifications"]=[
        m for m in state.setdefault("pending_notifications",[])
        if m.get("type")!="PREVIEW" or m.get("key")!=key
    ]
    sent=record.get("sent_at") if record else None
    early=bool(record and sent and ts(sent)<ts(record["due_at"])-timedelta(seconds=MIN_LEAD_SECONDS)
               and ts(record["created_at"])<ts(sent)
               and record.get("source_key") and record["source_key"]<key)
    if not early:
        state["advance_no_preview"]+=1
        if record:
            record["status"]="MISSED_PRE_DRAW"
        return {"type":"DRAW_NOT_PREVIEWED","key":key,"actual":actual}
    scores={}
    for mode in ("HYBRID","UNIFORM"):
        delta=compare_fn(actual,record["simulations"][mode])
        score=state["advance_stats"][mode]
        score["n"]+=1
        score["base_sum"]+=delta["base"]
        score["extra_sum"]+=delta["extra"]
        score["gold1_hits"]+=delta["gold1"]
        score["gold2_hits"]+=delta["gold2"]
        score["both_gold_hits"]+=delta["both"]
        scores[mode]=delta
    state["advance_checked"]+=1
    record["status"]="SCORED_PRE_PUBLISHED"
    return {"type":"DRAW","key":key,"actual":actual,
            "pre_issued":True,"issued_at":sent,
            "simulations":record["simulations"],"comparison":scores}
