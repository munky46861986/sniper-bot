#!/usr/bin/env python3
"""V186: tracing statico della navigazione diretta My Lotteries, solo lettura."""
import csv, io, json, re, zipfile, urllib.request
from pathlib import Path
OUT=Path("v186_risultati"); OUT.mkdir(exist_ok=True)
URL="https://mylotteries.it/mobile/download/android/MyLotteries.apk"
TERMS={"live":"Guarda la diretta","prog":"progressivoGiornaliero","parameter":r"\?prog=","numbers":"numeriEstratti","archive":"viewEmit_get10eLOTTONumbersProgressiveExtrations","navigation":r"router\.push|router\.replace|location\.href"}
rows=[]; report={"version":"186","source":URL,"live_endpoint_verified":False,"original_order_verified":False}
try:
 req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0 (static source review)"})
 with urllib.request.urlopen(req,timeout=60) as response: data=response.read(95*1024*1024+1)
 if len(data)>95*1024*1024: raise ValueError("APK beyond limit")
 report["apk_bytes"]=len(data)
 with zipfile.ZipFile(io.BytesIO(data)) as apk:
  files=[n for n in apk.namelist() if n.startswith("assets/www/") and n.endswith(".js")]
  report["js_files"]=len(files)
  for filename in files:
   if apk.getinfo(filename).file_size>8*1024*1024: continue
   source=apk.read(filename).decode("utf-8","replace")
   for label,pattern in TERMS.items():
    for hit in list(re.finditer(pattern,source,re.IGNORECASE))[:80]:
     excerpt=source[max(0,hit.start()-450):min(len(source),hit.end()+750)]
     excerpt=re.sub(r"(?i)(bearer\s+[\w.-]+|(?:token|password|secret|authorization)\s*[:=]\s*['\"]?[^\s,;'\"]+)", "[REDACTED]",excerpt)
     rows.append({"file":filename,"label":label,"offset":hit.start(),"context":re.sub(r"\s+"," ",excerpt)[:1200]})
 report["hits"]=len(rows)
 report["labels"]={label:sum(row["label"]==label for row in rows) for label in TERMS}
except Exception as error:
 report["error"]=str(error)[:300]
with (OUT/"contesti_v186.csv").open("w",encoding="utf-8-sig",newline="") as f:
 w=csv.DictWriter(f,fieldnames=["file","label","offset","context"]);w.writeheader();w.writerows(rows)
(OUT/"riepilogo_v186.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
