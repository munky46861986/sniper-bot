#!/usr/bin/env python3
"""V192: public Lotto Italia page, read-only browser diagnostic. No auth or 403 bypass."""
import csv, json, os, re, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

URL="https://www.lotto-italia.it/10-e-lotto"
OUT=Path("v192_risultati"); OUT.mkdir(exist_ok=True)
def now(): return datetime.now(timezone.utc).isoformat()
def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def scan(obj,path="root",depth=0):
    if depth>7: return []
    found=[]
    if isinstance(obj,list):
        if len(obj)==20 and all(type(x)==int and 1<=x<=90 for x in obj) and len(set(obj))==20:
            found.append({"json_path":path,"numbers":obj})
        for i,x in enumerate(obj[:60]):
            if isinstance(x,(list,dict)):found+=scan(x,path+f"[{i}]",depth+1)
    elif isinstance(obj,dict):
        for k,v in list(obj.items())[:80]:
            if isinstance(v,(list,dict)):found+=scan(v,path+"."+str(k)[:60],depth+1)
    return found[:25]
report={"version":"192","url":URL,"started_utc":now(),"browser_started":False,
        "live_order_verified":False,"official_video_matched":False}
requests=[]; candidates=[]; screenshots=[]
try:
    chrome=next((x for x in (os.environ.get("CHROME_PATH"),"/usr/bin/google-chrome","/usr/bin/chromium","/usr/bin/chromium-browser") if x and os.path.isfile(x)),None)
    if not chrome: raise RuntimeError("No system Chrome installed")
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=chrome,headless=True,args=["--no-sandbox"])
        ctx=browser.new_context(viewport={"width":1280,"height":900},locale="it-IT")
        page=ctx.new_page()
        report["browser_started"]=True
        def on_response(r):
            if len(requests)>=350: return
            parsed=urlsplit(r.url); host=parsed.hostname or ""
            if host not in ("www.lotto-italia.it","lotto-italia.it"):return
            # Log only safe path/status: no query strings, cookies, auth headers, or tokens.
            path=parsed.path[:180]
            ct=(r.headers.get("content-type") or "").lower()
            requests.append({"path":path,"status":r.status,"content_type":ct[:80],"method":r.request.method})
            if r.status!=200 or "json" not in ct or len(candidates)>=25:return
            try:
                body=r.body()
                if len(body)>220000: return
                obj=json.loads(body.decode("utf-8","replace"))
                for sample in scan(obj):
                    candidates.append({"path":path,"json_path":sample["json_path"],"numbers":sample["numbers"],"observed_utc":now(),"status":"UNVALIDATED"})
            except Exception:pass
        page.on("response",on_response)
        try:page.goto(URL,wait_until="domcontentloaded",timeout=35000)
        except Exception as e:report["navigation_error"]=str(e)[:150]
        for i in range(2):
            if i:time.sleep(65)
            try:
                filename=f"screen_{i}.png"
                page.screenshot(path=str(OUT/filename),full_page=False,timeout=15000)
                txt=page.locator("body").inner_text(timeout=15000)
                (OUT/f"text_{i}.txt").write_text(txt[:15000],encoding="utf-8")
                screenshots.append({"sample":i,"time_utc":now(),"url_path":urlsplit(page.url).path,"title":page.title()[:150],"text_sha256":sha(txt),"screenshot":filename,"text_length":len(txt)})
            except Exception as e:
                screenshots.append({"sample":i,"error":type(e).__name__+":"+str(e)[:120]})
        browser.close()
except Exception as e:report["error"]=type(e).__name__+": "+str(e)[:220]
with (OUT/"requests.csv").open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["path","status","content_type","method"]);w.writeheader();w.writerows(requests)
(OUT/"candidates.json").write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding="utf-8")
report.update(screenshots=screenshots,request_count=len(requests),candidate_count=len(candidates),ended_utc=now(),note="A candidate array or screenshot change does NOT prove original draw order; compare same competition with mobile video.")
(OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
