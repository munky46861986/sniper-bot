#!/usr/bin/env python3
"""V202: Diagnose publicly visible News&info and Home navigation in My Lotteries.
Uses only normal touch/back/page-down controls. Does not play, buy, log in or bypass access.
"""
import json,re,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
OUT=Path("v202_risultati");OUT.mkdir(exist_ok=True)
events=[]
def event(what,**fields):
 obj={"event":what,"time_utc":datetime.now(timezone.utc).isoformat(),**fields}
 events.append(obj);print(json.dumps(obj,ensure_ascii=False),flush=True)
def call(args,timeout=35):
 try:
  p=subprocess.run(args,timeout=timeout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  return p.returncode,p.stdout,p.stderr.decode("utf-8","replace")[:300]
 except Exception as e:return -1,b"",type(e).__name__+":"+str(e)[:200]
def adb(*args,timeout=35):return call(["adb",*args],timeout)
def tap(x,y,label):
 code,_,_=adb("shell","input","tap",str(x),str(y));event("tap",name=label,xy=[x,y],code=code)
def swipe(x,y,x2,y2,ms,label):
 code,_,_=adb("shell","input","swipe",*[str(n) for n in (x,y,x2,y2,ms)]);event("swipe",name=label,code=code)
def key(k,label):
 code,_,_=adb("shell","input","keyevent",str(k));event("key",name=label,code=code)
def snap(label):
 code,img,_=adb("exec-out","screencap","-p",timeout=25)
 if code==0:(OUT/f"{label}.png").write_bytes(img)
 adb("shell","uiautomator","dump","/sdcard/v202_ui.xml",timeout=35)
 adb("pull","/sdcard/v202_ui.xml",str(OUT/f"{label}.xml"),timeout=35)
 info={"name":label,"png_bytes":len(img) if code==0 else 0,"visible":[],"hidden_interesting":[],"scrollables":[]}
 p=OUT/f"{label}.xml"
 if p.exists():
  try:
   root=ET.fromstring(p.read_bytes())
   for n in root.iter():
    a=n.attrib
    t=a.get("text","").strip()
    bounds=a.get("bounds","")
    if t:
     d={"text":t[:90],"bounds":bounds,"clickable":a.get("clickable")}
     if bounds=="[0,0][0,0]":
      if any(x in t.lower() for x in ("estrazione","10elotto","news","risultat")):info["hidden_interesting"].append(d)
     elif bounds:
      info["visible"].append(d)
    if a.get("scrollable")=="true":
     info["scrollables"].append({"class":a.get("class"),"bounds":bounds})
  except Exception as e:info["ui_error"]=str(e)[:150]
 event("snapshot",**{k:v if not isinstance(v,list) else v[:36] for k,v in info.items()})
 return info
c,o,e=adb("install","-r","MyLotteries-v194.apk",timeout=140)
event("install",status=c,message=o.decode("utf-8","replace").strip()[-90:])
if c==0:
 adb("shell","monkey","-p","it.lottomatica.lotto","-c","android.intent.category.LAUNCHER","1")
 time.sleep(14); before=snap("initial")
 # Decline optional consent only if identified in current UI.
 target=next((d for d in before["visible"] if d["text"]=="Continua senza accettare"),None)
 if target:
  n=[int(x) for x in re.findall(r"\d+",target["bounds"])]
  if len(n)==4:tap((n[0]+n[2])//2,(n[1]+n[3])//2,"decline_optional_privacy")
  time.sleep(15);intro=snap("after_decline")
  fin=next((d for d in intro["visible"] if d["text"]=="Fine"),None)
  if fin:
   a=[int(x) for x in re.findall(r"\d+",fin["bounds"])]
   if len(a)==4:tap((a[0]+a[2])//2,(a[1]+a[3])//2,"intro_finished")
  else:
   # UI V197 visual proof confirms "Fine" at [211,456][240,471]
   tap(225,463,"intro_finish_screenshot_verified")
  time.sleep(10);home=snap("home")
  # Inspect read-only result tools. Do not open a scanner camera or take a bet.
  tap(160,586,"bottom_verifica_vincite")
  time.sleep(10);first=snap("verify_wins")
  # Only inspect the page; do not press buttons that could enter a purchase flow.
  time.sleep(8);snap("verify_wins_18s")
  # Navigate back to home using ordinary app bottom navigation.
  tap(38,588,"bottom_home")
  time.sleep(10);snap("home_return")
 else:event("notice","no_decline_button_found")
(OUT/"report.json").write_text(json.dumps({"version":202,"events":events,"sequence_verified":False},ensure_ascii=False,indent=2),encoding="utf-8")
