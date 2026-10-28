#!/usr/bin/env python3
"""V208: static trace of authorized UI navigation to the 10eLotto draw card.

Reads only the official APK JavaScript bundle (no requests to restricted APIs).
Looks for the existing application's scroll-to-draw event and its emitter.
"""
import hashlib,json,re,zipfile
from pathlib import Path

APK=Path("MyLotteries-v194.apk")
OUT=Path("v208_risultati");OUT.mkdir(exist_ok=True)
needles=[
    "scrollToElementsNotification",
    "scrollTo(\".estrazione_diecielotto\")",
    "newAppContainer",
    "estrazione_diecielotto",
    "scrollToElements",
    "10elotto",
    "10ELOTTO",
    "SCROLL_TO",
    "SCROLL-TO",
    "scroll-to",
    "scrollToElement",
]
matchers={
 "direct_function":r"scrollToElementsNotification",
 "direct_draw_selector":r"estrazione_diecielotto",
 "app_scroller":r"newAppContainer",
 "event_subscription":r"(?:\$BUS\.\$on|\.on)\s*\(\s*['\x22][^'\x22]{0,100}(?:SCROLL|NAVIG|HOME|FOCUS)[^'\x22]{0,100}",
 "event_emission":r"(?:\$BUS\.\$emit|\.emit)\s*\(\s*['\x22][^'\x22]{0,100}(?:SCROLL|NAVIG|HOME|FOCUS)[^'\x22]{0,100}",
 "route_scroll_query":r"(?:\$route\.query|this\.\$route\.query|scrollToElements)[\w\W]{0,180}",
}
summary={"version":208,"APK_sha256":hashlib.sha256(APK.read_bytes()).hexdigest(),
 "file_scans":0,"matches":[],"full_original_order_verified":False,
 "goal":"Find app's ordinary navigation action to scroll 10eLotto draw into visible area"}
with zipfile.ZipFile(APK) as z:
 for name in z.namelist():
  if not (name.startswith("assets/www/") and name.endswith(".js")):continue
  summary["file_scans"]+=1
  s=z.read(name).decode("utf8","replace")
  if not any(n in s for n in needles):continue
  counts={};matches=[]
  for label,pattern in matchers.items():
   hitlist=list(re.finditer(pattern,s,flags=re.I))
   counts[label]=len(hitlist)
   for m in hitlist[:15 if label in ("direct_function","direct_draw_selector","app_scroller") else 4]:
    before=1300 if label=="direct_function" else 900
    after=1700 if label=="direct_function" else 1100
    ctx=s[max(0,m.start()-before):min(len(s),m.end()+after)]
    # No direct HTTP data access, no live tokens. Do not copy potential credential strings.
    ctx=re.sub(r"(?i)(authorization\s*[:=]\s*|bearer\s+|password\s*[:=]\s*)[^\s,;}]{12,}",r"\1[REDACTED]",ctx)
    matches.append({"label":label,"offset":m.start(),"context":ctx[:3400]})
  if any(counts.values()):
   summary["matches"].append({"file":name,"counts":counts,"contexts":matches})
summary["matches"].sort(key=lambda x:(-x["counts"].get("direct_function",0),-x["counts"].get("direct_draw_selector",0),-x["counts"].get("app_scroller",0)))
summary["matches"]=summary["matches"][:28]
(OUT/"trace_event_v208.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
compact={"version":208,"scanned_js":summary["file_scans"],
 "matched_files":len(summary["matches"]),
 "top":[{"file":f["file"],"counts":f["counts"]} for f in summary["matches"][:12]]}
(OUT/"report_v208.json").write_text(json.dumps(compact,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps(compact,ensure_ascii=False,indent=2),flush=True)
