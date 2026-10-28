#!/usr/bin/env python3
"""V203 targeted static route analysis of official MyLotteries APK.
No network traffic except public APK download, no authentication or game actions.
"""
import csv, hashlib, io, json, pathlib, re, urllib.request, zipfile
URL="https://mylotteries.it/mobile/download/android/MyLotteries.apk"
SHA="857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a"
OUT=pathlib.Path("v203_risultati");OUT.mkdir(exist_ok=True)
apk=pathlib.Path("V203MyLotteries.apk")
req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0 (Public static app audit)"})
with urllib.request.urlopen(req,timeout=90) as response,apk.open("wb") as f:
 while True:
  b=response.read(1<<20)
  if not b:break
  f.write(b)
  if f.tell()>95*(1<<20):raise RuntimeError("APK unexpectedly large")
digest=hashlib.sha256(apk.read_bytes()).hexdigest()
if digest!=SHA:raise RuntimeError("APK hash changed, refuse analysis on unverified version")
needles=[
 ("open_direct",re.compile(r"estrazione5minuti",re.I)),
 ("follow_button",re.compile(r"Segui l.est(razione)?",re.I)),
 ("home_open",re.compile(r"homeComponent\.open",re.I)),
 ("nav_store",re.compile(r"(?:currentExtration|countDownModel)",re.I)),
 ("listener",re.compile(r"ESTRAZIONEFREQUENTE-GET-CURRENT-EXTRACTION",re.I)),
 ("route_map",re.compile(r"(?:(?:open|navigate|router|page|component)\s*:\s*function|push\s*\()",re.I)),
]
matches=[]; perfile={}; total_js=0
with zipfile.ZipFile(apk) as z:
 for name in z.namelist():
  if not name.startswith("assets/www/") or not name.endswith(".js"):continue
  b=z.read(name);total_js+=1
  s=b.decode("utf8","replace")
  cs={}
  for label,pat in needles:
   hits=list(pat.finditer(s))
   cs[label]=len(hits)
   if label in ("nav_store","route_map") and not any(x in name for x in ("main.790","6065.","748.")):
    continue
   for hit in hits[:35 if label!="nav_store" else 12]:
    pre=1200;post=1800
    context=re.sub(r"\s+"," ",s[max(0,hit.start()-pre):min(len(s),hit.end()+post)])
    context=re.sub(r"(?i)(?:bearer|authorization)\s+\S{12,}","[REDACTED]",context)
    matches.append({"file":name,"match_type":label,"offset":hit.start(),"excerpt":context[:3200]})
  if cs["open_direct"] or cs["home_open"] or cs["listener"]:
   perfile[name]={"bytes":len(b),"counts":cs}
with (OUT/"routes.csv").open("w",newline="",encoding="utf-8-sig") as f:
 w=csv.DictWriter(f,fieldnames=["file","match_type","offset","excerpt"]);w.writeheader();w.writerows(matches)
summary={"version":203,"apk_sha256":digest,"js_count":total_js,"relevant_files":perfile,
 "excerpt_count":len(matches),"original_order_verified":False,
 "purpose":"Find internal navigation to estrazione5minuti using static APK code only"}
(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps({"version":203,"js_count":total_js,"relevant_files":perfile,
"excerpt_count":len(matches),"extraction_verified":False},ensure_ascii=False,indent=2))
