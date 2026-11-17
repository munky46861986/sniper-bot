#!/usr/bin/env python3
"""TWIN90 LIVE: solo monitor e confronti virtuali. Nessuna giocata."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import requests
from bs4 import BeautifulSoup
from lotto_twin90 import CANDIDATES, dynamic_score, load_model, pick_weighted
from twin90_advance import expire_undelivered, make_preview, reconcile, ensure as advance_ensure

ROME = ZoneInfo("Europe/Rome")
ROOT = "https://lottologia.com/10elotto5minuti"
MONTHS = dict(zip(("gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre").split(),range(1,13)))
MONTHS.update({"gen":1,"feb":2,"mar":3,"apr":4,"mag":5,"giu":6,"lug":7,"ago":8,"set":9,"sett":9,"ott":10,"nov":11,"dic":12})
HEAD = re.compile(r"#\s*(\d{1,3})\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\.?\s+(\d{4})\s+(\d{1,2}:\d{2})",re.I)
SECT = re.compile(r"\bNumeri\b(.*?)\bOro\b(.*?)\bDoppio\s+Oro\b(.*?)\bExtra\b(.*)$",re.I|re.S)
NUMS = re.compile(r"(?<!\d)(\d{1,2})(?!\d)")
HEADERS={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36","Accept-Language":"it-IT,it;q=0.9"}


def marker(r):
    return f"{r['day']}#{r['draw']:03d}"


def mark_order(k):
    day,num=k.rsplit("#",1)
    return day,int(num)


def check(r):
    b,e=r["base"],r["extra"]
    g1,g2=r["oro1"],r["oro2"]
    alln=b+e+[g1,g2]
    if (len(b)!=20 or len(set(b))!=20 or len(e)!=15 or len(set(e))!=15
        or set(b)&set(e) or g1==g2 or g1 not in b or g2 not in b
        or any(not isinstance(n,int) or isinstance(n,bool) or not 1<=n<=90 for n in alln)
        or not 1<=r["draw"]<=288):
        raise ValueError("Invalid Base/Oro/Extra")
    datetime.fromisoformat(r["day"])
    return r


def parse_page(html,expected_day):
    txt=BeautifulSoup(html,"html.parser").get_text(" ",strip=True).replace("\xa0"," ")
    txt=re.sub(r"\s+"," ",txt)
    headers=list(HEAD.finditer(txt))
    out={}
    for i,m in enumerate(headers):
        try:
            month=MONTHS[m.group(3).lower().strip().rstrip(".")]
            day=datetime(int(m.group(4)),month,int(m.group(2))).date().isoformat()
            if day!=expected_day:continue
            sec=SECT.search(txt[m.end():headers[i+1].start() if i+1<len(headers) else len(txt)])
            if not sec:continue
            b=[int(v) for v in NUMS.findall(sec.group(1))][:20]
            o1=[int(v) for v in NUMS.findall(sec.group(2))]
            o2=[int(v) for v in NUMS.findall(sec.group(3))]
            e=[int(v) for v in NUMS.findall(sec.group(4))][:15]
            if not o1 or not o2:continue
            gold2=next((v for v in o2 if v!=o1[0]),None)
            if gold2 is None:continue
            r=check({"day":day,"draw":int(m.group(1)),"time":m.group(5),
                     "base":sorted(b),"oro1":o1[0],"oro2":gold2,"extra":sorted(e)})
            if marker(r) in out and out[marker(r)]!=r:
                raise ValueError("Source conflict "+marker(r))
            out[marker(r)]=r
        except (KeyError,ValueError,TypeError):
            continue
    return sorted(out.values(),key=lambda r:mark_order(marker(r)))


def fetch_real():
    today=datetime.now(ROME).date()
    targets=[(ROOT+"/tutte-le-estrazioni",str(today)),
             (ROOT+"/estrazioni/",str(today)),
             (ROOT+"/estrazioni-ieri",str(today-timedelta(days=1)))]
    found={};errors=[]
    for url,day in targets:
        try:
            res=requests.get(url,headers=HEADERS,timeout=22)
            res.raise_for_status()
            rows=parse_page(res.text,day)
            if not rows:errors.append("Nessun dato valido: "+url)
            for r in rows:
                k=marker(r)
                if k in found and (found[k]["base"],found[k]["oro1"],found[k]["oro2"],found[k]["extra"])!=(r["base"],r["oro1"],r["oro2"],r["extra"]):
                    raise RuntimeError("Fonti discordanti: "+k)
                found[k]=r
        except (requests.RequestException,RuntimeError) as exc:
            errors.append(str(exc)[:160])
    rows=sorted(found.values(),key=lambda r:mark_order(marker(r)))
    if not rows:raise RuntimeError("Fonte reale non disponibile: "+"; ".join(errors))
    return rows,errors


def empty():
    return {"schema":1,"latest":None,"history":[],"checked_at":None,
            "source_latest":None,"evaluated":0,"source_gaps":0,
            "stats":{k:{"n":0,"base_sum":0,"extra_sum":0,"gold1_hits":0,"gold2_hits":0,"both_gold_hits":0} for k in ("UNIFORM","HYBRID")},
            "recent":[]}


def generate_virtual(history,model,target_key,mode):
    # Only previous *real* draws are available here. No target result is read.
    prior=history[-1]
    day,n=mark_order(target_key)
    coeff=CANDIDATES[mode]
    scores=np.asarray(dynamic_score([r["base"] for r in history],model,n,coeff,
                                    (prior["oro1"],prior["oro2"]),prior["extra"]),dtype=float)
    scores=scores-scores.max()
    weights=np.exp(np.clip(scores,-10,10))
    seed=int.from_bytes(hashlib.sha256((target_key+"|"+mode+"|TWIN90").encode()).digest()[:8],"big")
    rng=np.random.default_rng(seed)
    ids=pick_weighted(rng,np.arange(90),weights,20)
    oro1=int(pick_weighted(rng,ids,model["oro1"],1)[0])
    oro2=int(pick_weighted(rng,ids[ids!=oro1],model["oro2"],1)[0])
    available=np.setdiff1d(np.arange(90),ids,assume_unique=True)
    ext=pick_weighted(rng,available,model["extra"],15)
    return check({"day":day,"draw":n,"base":sorted((ids+1).tolist()),
                  "oro1":oro1+1,"oro2":oro2+1,"extra":sorted((ext+1).tolist())})


def compare(a,b):
    return {"base":len(set(a["base"])&set(b["base"])),
            "extra":len(set(a["extra"])&set(b["extra"])),
            "gold1":int(a["oro1"]==b["oro1"]),
            "gold2":int(a["oro2"]==b["oro2"]),
            "both":int(a["oro1"]==b["oro1"] and a["oro2"]==b["oro2"])}


def ingest(state,rows,model,stamp=None):
    stamp=stamp or datetime.now(ROME).isoformat(timespec="seconds")
    now=datetime.fromisoformat(stamp)
    if now.tzinfo is None:
        now=now.replace(tzinfo=ROME)
    if state.get("schema")!=1 or not isinstance(state.get("history"),list):
        raise ValueError("Stato TWIN90 non compatibile; scrittura bloccata")
    advance_ensure(state)
    rows=sorted(rows,key=lambda r:mark_order(marker(r)))
    if not rows:raise ValueError("Nessun dato")
    for row in rows:check(row)
    expire_undelivered(state,now)
    state["checked_at"]=stamp
    state["source_latest"]=marker(rows[-1])
    if state["latest"] is None:
        state["history"]=rows[-288:]
        state["latest"]=marker(rows[-1])
        state["initialized_at"]=stamp
        preview=make_preview(state,model,generate_virtual,now=now)
        return {"status":"BOOTSTRAP","latest":state["latest"],"new_draws":0,
                "advance_checked":0,"next_preview":preview,"history_count":len(state["history"])}
    unseen=[r for r in rows if mark_order(marker(r))>mark_order(state["latest"])]
    previous=state["history"][-1] if state["history"] else None
    for actual in unseen:
        target_key=marker(actual)
        if previous:
            d0=datetime.fromisoformat(previous["day"])
            d1=datetime.fromisoformat(actual["day"])
            if (d0==d1 and actual["draw"]>previous["draw"]+1) or (d1-d0).days>1:
                state["source_gaps"]+=1
        # Do NOT regenerate a virtual draw after its actual result is known.
        # Score only the pre-announced simulation stored in our persistent
        # state and acknowledged by Telegram before the scheduled draw.
        notification=reconcile(state,actual,target_key,compare)
        state.setdefault("pending_notifications",[]).append(notification)
        state["recent"].append({"key":target_key,
                                "advance_verified":notification["type"]=="DRAW",
                                "comparison":notification.get("comparison",{})})
        state["recent"]=state["recent"][-30:]
        state["history"].append(actual)
        state["history"]=state["history"][-288:]
        state["latest"]=target_key
        previous=actual
    expire_undelivered(state,now)
    preview=make_preview(state,model,generate_virtual,now=now)
    # Digest old messages after long outages. Keep the newest preview intact.
    pending=state.get("pending_notifications",[])
    if len(pending)>12:
        older=pending[:-3]
        count=sum(int(item.get("count",1)) for item in older)
        start=older[0].get("first_key",older[0].get("key"))
        end=older[-1].get("last_key",older[-1].get("key"))
        state["pending_notifications"]=[
            {"type":"SUMMARY","count":count,"first_key":start,"last_key":end}
        ]+pending[-3:]
    return {"status":"LIVE" if unseen else "NO_NEW_DATA",
            "latest":state["latest"],"source_latest":state["source_latest"],
            "new_draws":len(unseen),"advance_checked":state["advance_checked"],
            "advance_no_preview":state["advance_no_preview"],
            "next_preview":preview,
            "source_gaps":state["source_gaps"],
            "advance_models":{k:{"draws":v["n"],
                                "avg_base_overlap":round(v["base_sum"]/v["n"],3) if v["n"] else None,
                                "avg_extra_overlap":round(v["extra_sum"]/v["n"],3) if v["n"] else None}
                              for k,v in state["advance_stats"].items()}}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",required=True);p.add_argument("--state",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    model,_=load_model(a.model)
    sp=Path(a.state)
    state=json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else empty()
    real,warnings=fetch_real()
    result=ingest(state,real,model)
    result["source_warnings"]=warnings
    sp.parent.mkdir(parents=True,exist_ok=True)
    sp.write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
