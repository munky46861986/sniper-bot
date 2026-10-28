#!/usr/bin/env python3
"""Single read-only POST to the public results endpoint referenced in My Lotteries app.
No credentials, no retry, no bypass, no purchase calls.
"""
import json, urllib.request, urllib.error, pathlib
url="https://showcase.giocodellotto.it/del/serviziFE/jsonrest/10elotto/raccolteFrequentiV2.json"
body={"dataEstrazione":"2026-10-27","numeroRaccolte":1,"progressivoGiornaliero":226}
video=[25,38,53,83,8,80,34,40,84,26,5,18,44,90,15,51,69,11,66,49]
result={"version":191,"source":"APK official JS reference","draw":"2026-10-27 #226",
        "parameters":body,"access_verified":False,"same_numbers_order_verified":False,
        "limitations":"Only one request. No auth or retries; no HTTP error bypass."}
try:
 req=urllib.request.Request(url,data=json.dumps(body).encode("utf8"),headers={"Accept":"application/json","Content-Type":"application/json"},method="POST")
 with urllib.request.urlopen(req,timeout=20) as response:
  result["status"]=response.status
  raw=response.read(256*1024+1)
 if len(raw)>256*1024:raise ValueError("response too large")
 doc=json.loads(raw)
 result["json_parsed"]=True
 if isinstance(doc,dict):
  result["top_keys"]=list(doc)[:40]
  draws=doc.get("raccolteFrequenti",[])
  if isinstance(draws,list) and draws and isinstance(draws[0],dict):
   item=draws[0]; nums=item.get("numeri")
   result["draw_keys"]=list(item)[:40]
   result["response_progressive"]=item.get("progressivoGiornaliero")
   if isinstance(nums,list) and len(nums)==20 and all(type(n)==int and 1<=n<=90 for n in nums) and len(set(nums))==20:
    result["numbers"]=nums
    result["same_set_as_video"]=set(nums)==set(video)
    result["same_numbers_order_verified"]=nums==video and item.get("progressivoGiornaliero")==226
 result["access_verified"]=True
except urllib.error.HTTPError as exc:
 result["status"]=exc.code;result["error"]="HTTP non-success; no retry"
except Exception as exc:
 result["error"]=type(exc).__name__+": "+str(exc)[:120]
output=pathlib.Path("v191_risultati");output.mkdir(exist_ok=True)
(output/"report_v191.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps(result,ensure_ascii=False,indent=2))
