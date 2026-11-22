"""Recover verified BASE history exclusively for DNA MASTER (SHADOW)."""
import json
import re
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from twin90_dna_master import WARMUP,index,rowkey

MONTHS="gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre".split()
SEED=Path(__file__).with_name("dna_master_bootstrap.json")
HEADERS={"User-Agent":"Mozilla/5.0", "Accept-Language":"it-IT,it;q=0.9"}

def parse_day(html,day):
    d=date.fromisoformat(day)
    soup=BeautifulSoup(html,"html.parser")
    title=" ".join(t.get_text(" ",strip=True) for t in soup.find_all(["title","h1","h2","caption"])).casefold()
    if not (re.search(rf"(?<!\d)0?{d.day}\s+{MONTHS[d.month-1]}\s+{d.year}(?!\d)",title) or re.search(rf"(?<!\d)0?{d.day}[/.-]0?{d.month}[/.-]{d.year}(?!\d)",title)):
        return []
    found={}
    for tr in soup.find_all("tr"):
        cells=tr.find_all("td",recursive=False)
        if len(cells)<2: continue
        m=re.fullmatch(r"\s*(\d{1,3})\s*[-–]\s*(\d{1,2}):(\d{2})\s*",cells[0].get_text(" ",strip=True))
        if not m: continue
        n,h,minute=map(int,m.groups())
        if not (1<=n<=288 and 0<=minute<60 and 0<=h<=24 and h*60+minute in ((n*5)%1440,n*5)): continue
        nums=sorted(map(int,re.findall(r"(?<!\d)\d{1,2}(?!\d)",cells[1].get_text(" ",strip=True))))
        if len(nums)!=20 or len(set(nums))!=20 or not all(1<=v<=90 for v in nums): continue
        if n in found and found[n]["base"]!=nums: raise ValueError("Conflicting archive draw")
        found[n]={"day":day,"draw":n,"base":nums}
    return list(found.values())

def collect(state,real,fetch=None,seed_rows=None):
    end=index(rowkey(state["history"][-1]))
    start=end-WARMUP+1
    known={}
    def add(r):
        pos=index(rowkey(r))
        if not start<=pos<=end: return
        base=sorted(r["base"])
        if len(base)!=20 or len(set(base))!=20 or not all(isinstance(v,int) and 1<=v<=90 for v in base): raise ValueError("Invalid BASE archive")
        if pos in known and known[pos]["base"]!=base: raise ValueError("Conflicting BASE archive")
        known[pos]={"day":r["day"],"draw":int(r["draw"]),"base":base}
    def key_at(pos):
        ordinal,n=divmod(pos-1,288)
        return date.fromordinal(ordinal).isoformat(),n+1
    lab=state.get("dna_master",{})
    last=lab.get("last_index")
    if last is not None:
        for offset,base in enumerate(reversed(lab.get("history",[]))):
            day,n=key_at(last-offset)
            add({"day":day,"draw":n,"base":base})
    for r in state["history"]+real: add(r)
    if seed_rows is None:
        seed_rows=json.loads(SEED.read_text(encoding="utf-8"))["rows"] if SEED.exists() else []
    for r in seed_rows: add(r)
    days=sorted({key_at(pos)[0] for pos in range(start,end+1) if pos not in known})
    checks=[]
    for day in days[-3:]:
        d=date.fromisoformat(day)
        url=f"https://www.10elotto5minuti.it/estrazioni-10elotto-5-minuti-{d.day}-{MONTHS[d.month-1]}-{d.year}.php"
        try:
            if fetch is None:
                res=requests.get(url,headers=HEADERS,timeout=12)
                res.raise_for_status()
                html=res.text
            else: html=fetch(url)
            rows=parse_day(html,day)
            overlaps=[r for r in rows if index(rowkey(r)) in known]
            if len(overlaps)<10 or any(known[index(rowkey(r))]["base"]!=r["base"] for r in overlaps):
                checks.append({"day":day,"status":"UNVERIFIED","overlap":len(overlaps)})
                continue
            before=len(known)
            for r in rows: add(r)
            checks.append({"day":day,"status":"VERIFIED","overlap":len(overlaps),"added":len(known)-before})
        except (requests.RequestException,ValueError) as exc:
            checks.append({"day":day,"status":type(exc).__name__})
    missing=[f"{d}#{n:03d}" for d,n in (key_at(pos) for pos in range(start,end+1) if pos not in known)]
    # Retain all current feed rows, including outcomes for already active research records.
    merged={rowkey(r):r for r in real}
    for pos in known: merged[rowkey(known[pos])]=known[pos]
    return sorted(merged.values(),key=lambda r:index(rowkey(r))),{"verified_rows":len(known),"missing":missing,"checks":checks}
