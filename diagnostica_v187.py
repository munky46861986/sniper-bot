#!/usr/bin/env python3
"""V187: trace statico MIRATO alla navigazione della diretta My Lotteries.
Non esegue app, non chiama API di gioco, non modifica bot o archivi.
"""
import csv, hashlib, io, json, re, urllib.request, zipfile
from pathlib import Path

APK_URL="https://mylotteries.it/mobile/download/android/MyLotteries.apk"
OUT=Path("v187_risultati"); OUT.mkdir(exist_ok=True)
TERMS={
 "live_button":r"Guarda la diretta",
 "daily_progressive":r"progressivoGiornaliero",
 "route_prog":r"(?:prog=|[?&]prog|progressivoGiornaliero)",
 "drawn_numbers":r"numeriEstratti",
 "live_component":r"(?:diretta|live|estrazione10eLotto)",
 "event_progressive":r"viewEmit_get10eLOTTONumbersProgressiveExtrations",
}
# Piccole finestre per limitare esposizione e falsi positivi
def redact(s):
 s=re.sub(r'(?i)(bearer\s+[\w.-]+|(?:token|password|secret|authorization|api_key)\s*[:=]\s*["\x27]?[\w./-]{10,})','[REDACTED]',s)
 return re.sub(r"\s+"," ",s)
report={"version":"187","apk_downloaded":False,"source":APK_URL,"network_feed_verified":False,"order_of_20_verified":False}
rows=[]; ranked=[]
try:
 req=urllib.request.Request(APK_URL,headers={"User-Agent":"Mozilla/5.0 (static research; read only)"})
 with urllib.request.urlopen(req,timeout=75) as f: data=f.read(95*1024*1024+1)
 if len(data)>95*1024*1024:raise RuntimeError("File over limit")
 report.update(apk_downloaded=True,apk_sha256=hashlib.sha256(data).hexdigest(),apk_bytes=len(data))
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  js=[n for n in z.namelist() if n.startswith("assets/www/") and n.endswith(".js") and z.getinfo(n).file_size<=8*1024*1024]
  report["js_count"]=len(js)
  for name in js:
   source=z.read(name).decode("utf-8","replace")
   matches={key:list(re.finditer(regex,source,re.I))[:150] for key,regex in TERMS.items()}
   score=sum(bool(matches[k]) for k in ("live_button","daily_progressive","drawn_numbers","event_progressive"))
   if not score:continue
   ranked.append({"file":name,"score":score,**{k:len(v) for k,v in matches.items()}})
   if not (matches["live_button"] or (matches["daily_progressive"] and matches["live_component"])):
    continue
   anchors=(matches["live_button"]+matches["daily_progressive"])[:60]
   for m in anchors:
    start=max(0,m.start()-1800);end=min(len(source),m.end()+2300)
    context=redact(source[start:end])[:4100]
    candidates=re.findall(r'(?:(?:https?:)?//[\w./?&=%:-]+|["\x27]/[\w./?&=%:-]+["\x27])',context)
    rows.append({"file":name,"anchor":m.group(0),"offset":m.start(),"context":context,"url_like":' | '.join(candidates[:12]),"proof":"STATIC_CONTEXT_ONLY"})
  report["selected_contexts"]=len(rows)
  report["files_with_hits"]=len(ranked)
 with (OUT/"tracce_v187.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["file","anchor","offset","context","url_like","proof"]);w.writeheader();w.writerows(rows)
 with (OUT/"files_v187.csv").open("w",encoding="utf-8-sig",newline="") as f:
  fields=["file","score",*TERMS.keys()]
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(sorted(ranked,key=lambda x:-x["score"]))
except Exception as ex:report["error"]=type(ex).__name__+": "+str(ex)[:250]
(OUT/"report_v187.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
