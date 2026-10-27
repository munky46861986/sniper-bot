#!/usr/bin/env python3
"""V188: only static relationship between live 10eLotto component and video service."""
import csv,io,json,re,urllib.request,zipfile
from pathlib import Path
out=Path("v188_risultati");out.mkdir(exist_ok=True)
url="https://mylotteries.it/mobile/download/android/MyLotteries.apk"
terms=["DieciELottoVideoService","estrazione5minuti","wrapperVideo","videoPlayerConfig","dieciElottoStreamingActive","listExtrations","numeriEstratti"]
rows=[];report={"version":"188","service_endpoint_verified":False,"ordered_draw_verified":False}
try:
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
 with urllib.request.urlopen(req,timeout=90) as r:data=r.read(95*1024*1024+1)
 if len(data)>95*1024*1024:raise ValueError("APK too large")
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  files=[n for n in z.namelist() if n.startswith("assets/www/") and n.endswith(".js") and z.getinfo(n).file_size<8_000_000]
  report["js_scanned"]=len(files)
  for file in files:
   src=z.read(file).decode("utf8","replace")
   for term in terms:
    for m in list(re.finditer(re.escape(term),src,re.I))[:45]:
     context=src[max(0,m.start()-1000):min(len(src),m.end()+1500)]
     context=re.sub(r"(?i)(bearer\s+[\w.-]+|(?:token|password|secret|authorization)\s*[:=]\s*['\"]?[\w.-]{10,})","[REDACTED]",context)
     rows.append(dict(file=file,term=term,offset=m.start(),context=re.sub(r"\s+"," ",context)[:2500]))
 report["matches"]=len(rows)
 report["by_term"]={t:sum(r["term"]==t for r in rows) for t in terms}
except Exception as ex:report["error"]=str(ex)[:250]
with (out/"service_context_v188.csv").open("w",encoding="utf-8-sig",newline="") as f:
 w=csv.DictWriter(f,fieldnames=["file","term","offset","context"]);w.writeheader();w.writerows(rows)
(out/"report_v188.json").write_text(json.dumps(report,indent=2),encoding="utf8")
print(json.dumps(report,indent=2))
