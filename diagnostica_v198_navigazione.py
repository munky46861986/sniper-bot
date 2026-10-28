#!/usr/bin/env python3
"""V198: UI-only navigation from privacy banner to 10eLotto follow-draw.
Only standard user clicks on: "Continue without accepting", "Fine", "10eLotto",
"Segui l'estrazione". Never click gambling, payment, login or consent-accept UI.
"""
import json, re, subprocess, time, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
OUT=Path("v198_risultati");OUT.mkdir(exist_ok=True)
APK="MyLotteries-v194.apk";PKG="it.lottomatica.lotto"
events=[]
def run(args,t=35,binary=False):
 try:
  p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=t)
  return p.returncode,(p.stdout if binary else p.stdout.decode("utf8","replace")),p.stderr.decode("utf8","replace")
 except Exception as e:return 99,(b"" if binary else ""),str(e)[:140]
def adb(*x,t=35):return run(["adb",*x],t)
def record(kind,**k):
 e={"event":kind,"utc":datetime.now(timezone.utc).isoformat(),**k}
 events.append(e);print(json.dumps(e,ensure_ascii=False),flush=True)
def snap(name):
 n=OUT/("s_"+name+".png")
 ret,png,err=run(["adb","exec-out","screencap","-p"],t=20,binary=True)
 if ret==0:n.write_bytes(png)
 adb("shell","uiautomator","dump","/sdcard/v198_ui.xml",t=40)
 adb("pull","/sdcard/v198_ui.xml",str(OUT/("ui_"+name+".xml")),t=40)
 _,a,_=adb("shell","dumpsys","activity","activities")
 active=re.findall(r"(?m)^\s*(?:mResumedActivity|ResumedActivity):?\s*(.{0,165})",a)
 nodes=[]
 try:
  for node in ET.parse(OUT/("ui_"+name+".xml")).iter("node"):
   text=node.get("text","").strip()
   bounds=node.get("bounds","")
   if text and bounds and bounds!="[0,0][0,0]":
    nodes.append({"text":text[:65],"bounds":bounds,"clickable":node.get("clickable","")})
 except Exception as e:record("ui_error",reason=str(e)[:120])
 record("snapshot",name=name,active=active[:1],visible_nodes=nodes[:40],node_count=len(nodes))
 return nodes
def center(bounds):
 vals=[int(x) for x in re.findall(r"\d+",bounds)]
 if len(vals)!=4:return None
 x1,y1,x2,y2=vals
 if x2-x1<5 or y2-y1<5 or x1<0 or y1<0 or x2>320 or y2>640:return None
 return [(x1+x2)//2,(y1+y2)//2]
def tap_node(nodes,text,contains=False,preferred_top=640):
 matches=[n for n in nodes if (text in n["text"] if contains else n["text"]==text) and center(n["bounds"])]
 matches=[n for n in matches if center(n["bounds"])[1]<preferred_top]
 if not matches:return False
 matches.sort(key=lambda n:center(n["bounds"])[1])
 x,y=center(matches[0]["bounds"])
 adb("shell","input","tap",str(x),str(y))
 record("tap",text=text,xy=[x,y])
 return True

code,out,err=adb("install","-r",APK,t=130)
record("install",returncode=code,message=out.strip()[-90:])
if code==0:
 adb("shell","monkey","-p",PKG,"-c","android.intent.category.LAUNCHER","1")
 time.sleep(14)
 nodes=snap("initial")
 if tap_node(nodes,"Continua senza accettare"):
  time.sleep(16); nodes=snap("after_decline")
  finished=tap_node(nodes,"Fine")
  if not finished:
   # The V198 screenshot showed the tutorial and its visible "Fine" at [211,456][240,471],
   # while Android WebView's accessibility tree was temporarily empty.
   adb("shell","input","tap","225","463")
   record("tap_screen_verified_fine",xy=[225,463])
   finished=True
  if finished:
   time.sleep(12); nodes=snap("after_intro")
   if not any(n["text"]=="10eLotto" for n in nodes):
    time.sleep(8);nodes=snap("after_intro_retry")
   if tap_node(nodes,"10eLotto",preferred_top=580):
    time.sleep(8);nodes=snap("10elotto_tab")
    for attempt in range(3):
     if tap_node(nodes,"Segui l'estrazione",contains=True):
      time.sleep(6);nodes=snap("draw_open")
      time.sleep(20);nodes=snap("draw_20s")
      break
     # One ordinary vertical scroll to find the follow-draw button; no playing buttons.
     adb("shell","input","swipe","168","555","168","238","500")
     record("scroll",attempt=attempt)
     time.sleep(3);nodes=snap("10elotto_scroll_"+str(attempt))
   else:record("no_category_tab")
  else:record("no_intro_finish")
 else:record("no_decline_button")
(OUT/"report.json").write_text(json.dumps({"version":198,"events":events,"extraction_order_verified":False},ensure_ascii=False,indent=2),encoding="utf8")
