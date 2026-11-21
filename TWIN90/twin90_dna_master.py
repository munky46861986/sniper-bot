"""DNA MASTER V1: frozen experimental shadow, no betting or orders.
Matches the historical 14 indicators / 6 family thresholds. No backfill of forecasts.
"""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta
from twin90_advance import ROME, MIN_LEAD_SECONDS, next_concorso, ts

VERSION = "DNA_MASTER_V1_FROZEN"
WARMUP = 576
HORIZONS = (1, 2, 5, 10)
MODES = ("MASTER_4_FAMIGLIE", "MASTER_5_INDICATORI")
NAMES = ("DNA_ABBDA", "25_R15", "L15_C01_L15", "C01_L20_C01", "R20",
         "06_to_41", "DNA_ADDAA", "03_R10_to_67", "05_R10_to_79",
         "19_lunedi", "momentum576", "top100_ambi_2025", "presente_un_vicino", "shift28")
GROUPS = ((0,1,2,3,4,6),(5,7,8),(9,),(10,),(11,),(12,13))
# Frozen from top100_ambi.csv, historical 2025. Never re-estimate LIVE.
PAIRS = tuple(tuple(map(int,p.split("-"))) for p in (
    "23-37 8-41 53-55 71-78 59-79 4-56 37-41 7-55 38-78 55-78 "
    "1-68 16-41 3-46 17-58 46-59 8-68 33-37 43-59 55-73 41-52 "
    "57-82 23-59 41-73 8-80 1-63 1-82 1-15 55-57 15-73 56-57 "
    "14-41 8-55 37-68 14-79 37-89 16-55 34-82 41-58 46-76 26-78 "
    "1-9 8-38 17-21 23-64 29-79 56-59 58-78 64-79 9-14 41-43 "
    "68-82 1-3 8-15 37-55 21-56 29-61 72-74 41-45 54-59 59-83 "
    "1-33 6-41 34-55 34-57 8-20 56-78 16-38 40-57 4-12 12-55 "
    "33-83 46-54 51-59 12-35 17-83 38-53 43-70 8-89 12-39 15-82 "
    "66-79 8-14 59-77 23-90 37-57 6-8 14-35 25-59 55-70 57-79 "
    "1-29 1-77 8-57 17-70 68-69 81-82 22-82 29-43 33-38 33-57"
).split())
assert len(PAIRS) == 100 and len(set(PAIRS)) == 100

def index(key):
    day, n = key.rsplit("#", 1)
    n = int(n)
    if not 1 <= n <= 288:
        raise ValueError("Invalid draw")
    return date.fromisoformat(day).toordinal() * 288 + n

def rowkey(row):
    return f"{row['day']}#{int(row['draw']):03d}"

def fresh():
    return {"version":VERSION,"last_index":None,"history":[],"occ":[[] for _ in range(90)],
            "active":{},"recent":[],"gaps":0,"missed":0,
            "stats":{m:{"published":0, **{str(h):{"n":0,"hit":0} for h in HORIZONS}} for m in MODES}}

def _cat(g):
    return 0 if g == 0 else 1 if g <= 2 else 2 if g <= 5 else 3

def signals(lab, target):
    if len(lab["history"]) < WARMUP:
        return {}
    present = set(lab["history"][-1])
    votes = [set() for _ in range(90)]
    t = lab["last_index"]
    gap = {}
    for n in present:
        ix = lab["occ"][n-1]
        if len(ix) >= 2:
            g = [b-a-1 for a,b in zip(ix,ix[1:])]
            gap[n] = g[-1]
            if len(g) >= 5:
                c = list(map(_cat,g[-5:]))
                if c == [0,1,1,3,0]: votes[n-1].add(0)
                if c == [0,3,3,0,0]: votes[n-1].add(6)
            if len(g) >= 3:
                a,b,c = g[-3:]
                if a >= 15 and b <= 1 and c >= 15: votes[n-1].add(2)
                if a <= 1 and b >= 20 and c <= 1: votes[n-1].add(3)
            if g[-1] >= 20: votes[n-1].add(4)
    if gap.get(25,-1) >= 15: votes[24].add(1)
    if 6 in present: votes[40].add(5)
    if gap.get(3,-1) >= 10: votes[66].add(7)
    if gap.get(5,-1) >= 10: votes[78].add(8)
    if date.fromisoformat(target.split("#")[0]).weekday() == 0: votes[18].add(9)
    old = Counter(n for draw in lab["history"][-576:-288] for n in draw)
    new = Counter(n for draw in lab["history"][-288:] for n in draw)
    for n in sorted(range(1,91), key=lambda n: (old[n]-new[n], n))[:20]:
        votes[n-1].add(10)
    for a,b in PAIRS:
        if a in present and b in present:
            votes[a-1].add(11); votes[b-1].add(11)
    for n in present:
        r,c=divmod(n-1,10)
        near=[n-1 if c else 0, n+1 if c<9 else 0, n-10 if r else 0, n+10 if r<8 else 0]
        if sum(x in present for x in near)==1: votes[n-1].add(12)
        votes[(n-1+28)%90].add(13)
    out={}
    for n,v in enumerate(votes,1):
        families=sum(bool(v.intersection(g)) for g in GROUPS)
        modes=[m for m,ok in zip(MODES,(families>=4,len(v)>=5)) if ok]
        if modes:
            out[str(n)]={"families":families,"indicators":[NAMES[i] for i in sorted(v)],"modes":modes}
    return out

def describe(lab):
    return {"version":VERSION,"warmup":len(lab["history"]),"required":WARMUP,
            "gaps":lab["gaps"],"missed":lab["missed"],"active":len(lab["active"]),
            "stats":deepcopy(lab["stats"])}

def _early(rec):
    return bool(rec.get("sent_at")) and ts(rec["created_at"]) <= ts(rec["sent_at"]) < ts(rec["due_at"])-timedelta(seconds=MIN_LEAD_SECONDS)

def confirm(state,key,when):
    lab=state.get("dna_master")
    if not lab: return False
    rec=lab["active"].get(key)
    if not rec: return False
    if rec.get("sent_at"): return _early(rec)
    rec["sent_at"]=when.isoformat()
    if not _early(rec):
        lab["missed"] += len(rec["candidates"])
        lab["active"].pop(key,None)
        return False
    for n, item in rec["candidates"].items():
        for m in item["modes"]: lab["stats"][m]["published"] += 1
    return True

def _observe(lab,row):
    t=index(rowkey(row)); previous=lab["last_index"]
    if previous is not None and t <= previous: return []
    present=set(row["base"])
    if len(present)!=20 or not present <= set(range(1,91)): raise ValueError("Invalid BASE")
    notes=[]
    if previous is not None and t != previous+1:
        lab["gaps"]+=1
        lab["history"]=[]
        lab["occ"]=[[] for _ in range(90)]
        lab["missed"]+=sum(len(x["candidates"]) for x in lab["active"].values())
        lab["active"]={}
    for key,rec in list(lab["active"].items()):
        h=t-index(key)+1
        if h<1: continue
        if h>10 or not _early(rec):
            lab["missed"]+=len(rec["candidates"])
            lab["active"].pop(key,None); continue
        rec["seen"]=sorted(set(rec["seen"])|present)
        if h in HORIZONS:
            for m in MODES:
                candidates={int(n) for n,item in rec["candidates"].items() if m in item["modes"]}
                if not candidates: continue
                hits=sorted(candidates & set(rec["seen"]))
                s=lab["stats"][m][str(h)]
                s["n"]+=len(candidates); s["hit"]+=len(hits)
                notes.append(f"{m} {key} H{h}: {len(hits)}/{len(candidates)} (totale {s['hit']}/{s['n']})")
            if h==10:
                lab["recent"].append({"key":key,"candidates":rec["candidates"],"seen":rec["seen"],"sent_at":rec["sent_at"]})
                lab["recent"]=lab["recent"][-100:]
                lab["active"].pop(key,None)
    lab["history"].append(sorted(present))
    lab["history"]=lab["history"][-WARMUP:]
    for n in present:
        lab["occ"][n-1].append(t); lab["occ"][n-1]=lab["occ"][n-1][-6:]
    lab["last_index"]=t
    return notes

def tick(state, rows, now=None):
    """Receives only already verified source rows. No alteration to TWIN90 counters."""
    now=now or datetime.now(ROME)
    lab=deepcopy(state.get("dna_master") or fresh())
    if lab["version"] != VERSION: raise ValueError("DNA MASTER state version mismatch")
    pending=state.setdefault("pending_notifications",[])
    historical={rowkey(r):r for r in state.get("history",[])}
    historical.update({rowkey(r):r for r in rows})
    # Keep already validated BASE draws while extending the window backwards.
    # During normal operation this reconstruction does not touch live scores.
    saved={index(k):r["base"] for k,r in historical.items()}
    old_end=lab["last_index"]
    if old_end is not None:
        for offset,base in enumerate(reversed(lab["history"])):
            pos=old_end-offset
            if pos in saved and sorted(saved[pos])!=sorted(base):
                raise ValueError("Conflicting historic BASE")
            saved[pos]=base
    notes=[]
    for key,row in sorted(historical.items(), key=lambda x:index(x[0])):
        notes.extend(_observe(lab,row))
    # _observe ignores older draws already passed by the live cursor.
    # Rebuild only the unscored warmup from a contiguous, validated suffix.
    # Never clear counters, and never reconstruct forecasts in the past.
    end=lab["last_index"]
    if end is not None and len(lab["history"])<WARMUP and not lab["active"]:
        suffix=[]
        for pos in range(end,end-WARMUP,-1):
            if pos not in saved: break
            suffix.append((pos,saved[pos]))
        if len(suffix)>len(lab["history"]):
            lab["history"]=[]
            lab["occ"]=[[] for _ in range(90)]
            lab["last_index"]=None
            for pos,base in reversed(suffix):
                # Inverse of index(); valid concorsi 1..288.
                ordinal,number=divmod(pos-1,288)
                _observe(lab,{"day":date.fromordinal(ordinal).isoformat(),
                              "draw":number+1,"base":base})
    preview=None
    if state.get("history") and len(lab["history"])>=WARMUP:
        last=state["history"][-1]
        key,due=next_concorso(last)
        if lab["last_index"]==index(rowkey(last)) and index(key)==lab["last_index"]+1:
            preview=next((r for r in pending if r.get("type")=="PREVIEW" and r.get("key")==key),None)
            if preview is not None and now<due-timedelta(seconds=MIN_LEAD_SECONDS) and key not in lab["active"]:
                chosen=signals(lab,key)
                if chosen:
                    lab["active"][key]={"created_at":now.isoformat(),"due_at":due.isoformat(),
                        "sent_at":None,"candidates":chosen,"seen":[]}
    state["dna_master"]=lab
    if preview is not None and preview["key"] in lab["active"]:
        preview["dna_master"]=deepcopy(lab["active"][preview["key"]]["candidates"])
    if notes and pending:
        # Reports attach to an existing message, not a new Telegram queue.
        msg=next((r for r in reversed(pending) if r.get("type") in ("DRAW","DRAW_NOT_PREVIEWED","SUMMARY")), pending[-1])
        msg["dna_master_results"]=notes[-12:]
    return describe(lab)

def format_extra(item):
    lines=[]
    results=item.get("dna_master_results",[])
    if results:
        lines.extend(["","DNA MASTER — VERIFICA SHADOW",*results])
    candidates=item.get("dna_master",{})
    if candidates:
        lines.extend(["","DNA MASTER V1 — SHADOW / NESSUNA GIOCATA"])
        for n,data in candidates.items():
            modes=", ".join("MASTER 4" if m==MODES[0] else "MASTER 5" for m in data["modes"])
            lines.append(f"{int(n):02d}: {modes} | famiglie {data['families']}/6 | indicatori {len(data['indicators'])}/14")
        lines.append("Osservazione H1/H2/H5/H10, non suggerimenti di gioco.")
    return "\n".join(lines)
