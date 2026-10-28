#!/usr/bin/env python3
"""V213: navigate Home using normal keyboard focus.

Legitimate intent: https://mylotteries.it/estrazioni (registered as https +
mylotteries.it + /estrazioni prefix in AndroidManifest.xml).
No blocked API requests, hidden-component invocation, gambling, authentication,
browser injection, or data collection. Only inspect what the official app shows.
"""
import json,re,subprocess,time,hashlib,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
OUT=Path("v213_risultati");OUT.mkdir(exist_ok=True)
URL="https://mylotteries.it/estrazioni"
events=[]
def log(name,**kw):
 obj={"event":name,"utc":datetime.now(timezone.utc).isoformat(),**kw}
 events.append(obj);print(json.dumps(obj,ensure_ascii=False),flush=True)
def shell(*args,timeout=40):
 try:
  p=subprocess.run(["adb",*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
  return p.returncode,p.stdout,p.stderr.decode(errors="replace")[:200]
 except Exception as e:return 99,b"",type(e).__name__+":"+str(e)[:150]
def snap(name):
 code,b,err=shell("exec-out","screencap","-p",timeout=25)
 if code==0:(OUT/(name+".png")).write_bytes(b)
 digest=hashlib.sha256(b).hexdigest() if code==0 else None
 shell("shell","uiautomator","dump","/sdcard/v213.xml",timeout=32)
 shell("pull","/sdcard/v213.xml",str(OUT/(name+".xml")),timeout=32)
 txt=[]
 try:
  for n in ET.parse(OUT/(name+".xml")).iter("node"):
   t=n.attrib.get("text","").strip()
   if t and n.attrib.get("bounds") not in ("","[0,0][0,0]"):txt.append(t[:70])
 except Exception:pass
 log("snapshot",step=name,bytes=len(b),sha256=digest,ui_texts=txt[:24])
 return txt
def click(label,path):
 try:
  for n in ET.parse(OUT/(path+".xml")).iter("node"):
   if label.lower() not in n.attrib.get("text","").lower():continue
   a=[int(x) for x in re.findall(r"\d+",n.attrib.get("bounds",""))]
   if len(a)==4 and a[2]-a[0]>5 and a[3]-a[1]>5:
    x=(a[0]+a[2])//2;y=(a[1]+a[3])//2
    shell("shell","input","tap",str(x),str(y))
    log("tap",label=label,point=[x,y]);return True
 except Exception:pass
 return False

code,out,err=shell("install","-r","MyLotteries-v194.apk",timeout=140)
log("install",code=code,message=out.decode(errors="replace").strip()[-100:])
if code==0:
 shell("shell","monkey","-p","it.lottomatica.lotto","-c","android.intent.category.LAUNCHER","1")
 time.sleep(16)
 snap("privacy")
 if click("Continua senza accettare","privacy"):
  time.sleep(17);snap("intro")
  if not click("Fine","intro"):
   shell("shell","input","tap","225","463")
   log("intro_finish_previous_verified_point")
  time.sleep(11);snap("home_before_link")
  # Normal TAB moved the Home in V211. Never activate purchase buttons.
  opened=False
  for i in range(1,71):
   code,_,err=shell("shell","input","keyevent","61")
   if code!=0:
    log("tab_failed",index=i,error=err);break
   time.sleep(0.35)
   if i%5==0:
    name="tabs_"+str(i).zfill(2)
    texts=snap(name)
    target=any("Segui l'estrazione" in x for x in texts)
    log("home_focus_checkpoint",tabs=i,visible_live_button=target)
    if target and click("Segui l'estrazione",name):
     log("live_button_click",tabs=i)
     time.sleep(4);snap("live_after_4s")
     time.sleep(15);snap("live_after_19s")
     opened=True
     break
  if not opened:
   for i in range(1,17):
    code,_,err=shell("shell","input","keyevent","20") # DPAD_DOWN, no ENTER
    if code!=0:break
    time.sleep(0.6)
    if i%4==0:
     name="dpad_"+str(i).zfill(2)
     texts=snap(name)
     target=any("Segui l'estrazione" in x for x in texts)
     log("dpad_checkpoint",index=i,visible_live_button=target)
     if target and click("Segui l'estrazione",name):
      log("live_button_click",dpad=i)
      time.sleep(4);snap("live_from_dpad_4s")
      opened=True
      break
  log("diagnostic_summary",button_clicked=opened,sequence_verified=False)
 else:log("stop",reason="privacy_decline_not_found")
(OUT/"report.json").write_text(json.dumps({
 "version":213,"verified_10elotto_original_order":False,
 "focus_navigation_tested":True,"events":events},ensure_ascii=False,indent=2),encoding="utf8")
