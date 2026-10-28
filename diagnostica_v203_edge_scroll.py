#!/usr/bin/env python3
"""V203 - Inspect the My Lotteries home at taller Android screen sizes.

Only system display resizing and normal UI interactions. No auth, payments,
remote endpoint calls, reverse proxies, or permission circumvention.
"""
import json, re, subprocess, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUT=Path("v203_risultati");OUT.mkdir(exist_ok=True)
events=[]
def run(*args,timeout=40):
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        return p.returncode,p.stdout,p.stderr.decode(errors="replace")[:180]
    except Exception as ex:
        return -1,b"",type(ex).__name__+":"+str(ex)[:110]
def adb(*args,timeout=40):return run("adb",*args,timeout=timeout)
def event(kind,**kw):
    obj={"event":kind,"utc":datetime.now(timezone.utc).isoformat(),**kw}
    events.append(obj);print(json.dumps(obj,ensure_ascii=False),flush=True)
def ss(label):
    _,dims,_=adb("shell","wm","size")
    c,img,_=adb("exec-out","screencap","-p",timeout=25)
    if c==0:(OUT/(label+".png")).write_bytes(img)
    adb("shell","uiautomator","dump","/sdcard/v203_ui.xml")
    adb("pull","/sdcard/v203_ui.xml",str(OUT/(label+".xml")))
    nodes=[];interesting=[]
    path=OUT/(label+".xml")
    if path.exists():
        try:
            for el in ET.parse(path).iter("node"):
                text=el.attrib.get("text","").strip()
                bounds=el.attrib.get("bounds","")
                if text and bounds!="[0,0][0,0]":
                    nodes.append({"text":text[:95],"bounds":bounds})
                if text and any(s in text.lower() for s in ("segui l'estrazione","estrazione in corso","10elotto","risultati")):
                    interesting.append({"text":text[:90],"bounds":bounds})
        except Exception as ex:event("parse_error",name=label,reason=str(ex)[:100])
    event("screenshot",name=label,wm=dims.decode(errors="replace").strip(),png_bytes=len(img),interesting=interesting[:15],visible_nodes=len(nodes))
    return nodes
def click(nodes,text):
    for n in nodes:
        if text.lower() in n["text"].lower():
            a=[int(v) for v in re.findall(r"\d+",n["bounds"])]
            if len(a)==4 and a[2]-a[0]>5 and a[3]-a[1]>5:
                x=(a[0]+a[2])//2;y=(a[1]+a[3])//2
                adb("shell","input","tap",str(x),str(y))
                event("clicked",text=text,xy=[x,y])
                return True
    return False

c,out,err=adb("install","-r","MyLotteries-v194.apk",timeout=130)
event("install",code=c,message=out.decode(errors="replace").strip()[-90:])
if c==0:
    adb("shell","monkey","-p","it.lottomatica.lotto","-c","android.intent.category.LAUNCHER","1")
    time.sleep(15)
    nodes=ss("privacy")
    if click(nodes,"Continua senza accettare"):
        time.sleep(16)
        nodes=ss("introduction")
        if not click(nodes,"Fine"):
            # This location was verified visually in the previous V197 run.
            adb("shell","input","tap","225","463")
            event("intro_finish_screenshot_coordinates",xy=[225,463])
        time.sleep(12)
        ss("home_320x640")
        # Use taller screen and swipe from narrow margins, not over embedded web promotions.
        adb("shell","wm","size","600x1180")
        time.sleep(15)
        ss("wide_before")
        gestures=[(589,965,589,155,850,"right_edge"),
                  (12,930,12,120,850,"left_edge"),
                  (300,855,300,130,950,"center_background")]
        clicked=False
        for x1,y1,x2,y2,dur,name in gestures:
            adb("shell","input","swipe",str(x1),str(y1),str(x2),str(y2),str(dur))
            event("swipe",name=name,xy=[x1,y1,x2,y2],duration_ms=dur)
            time.sleep(7)
            nodes=ss("after_"+name)
            if click(nodes,"Segui l'estrazione"):
                clicked=True
                time.sleep(17)
                ss("after_live_click")
                break
        if not clicked:event("follow_draw_still_hidden_after_edge_swipes")
    else:event("privacy_decline_not_found")
(OUT/"report.json").write_text(json.dumps({"version":203,"events":events,
   "sequence_verified":False,"notes":"A visible draw button does not alone prove original order."},ensure_ascii=False,indent=2),encoding="utf-8")
