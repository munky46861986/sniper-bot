#!/usr/bin/env python3
"""V197: Analyze standard Android Onetrust CMP taps on the user's own app.
Produces sanitized diagnostics; never accepts analytics, modifies network routes, or bypasses auth.
"""
import pathlib,re,subprocess,hashlib,json,time,xml.etree.ElementTree as ET
from datetime import datetime,timezone

OUT=pathlib.Path("v197_risultati"); OUT.mkdir(exist_ok=True)
ID="it.lottomatica.lotto"; SCREEN="it.lottomatica.lotto:id/close_banner_text"
report={"version":"197","purpose":"Diagnose consent-decline UI; do not grant marketing consent","events":[]}
def sh(*args, timeout=40):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 return p.returncode,p.stdout.decode(errors="replace"),p.stderr.decode(errors="replace")
def adb(*args, timeout=40):
 return sh("adb",*args,timeout=timeout)
def now():return datetime.now(timezone.utc).isoformat()
def capture(label):
 try:
  code,png,err=sh("adb","exec-out","screencap","-p",timeout=20)
  if code==0:
   (OUT/("screen_"+label+".png")).write_bytes(png.encode("latin-1")) # unused, see binary capture below
 except Exception:pass
 # Binary-safe screenshot (do not decode PNG as text).
 try:
  p=subprocess.run(["adb","exec-out","screencap","-p"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
  if p.returncode==0:(OUT/("screen_"+label+".png")).write_bytes(p.stdout)
 except Exception as e:report["events"].append({"event":"screenshot_error","at":now(),"error":type(e).__name__})
 adb("shell","uiautomator","dump","/sdcard/v197_ui.xml",timeout=30)
 adb("pull","/sdcard/v197_ui.xml",str(OUT/("ui_"+label+".xml")),timeout=30)
 ui=(OUT/("ui_"+label+".xml"))
 strings=[];close=None
 if ui.exists():
  try:
   for el in ET.parse(ui).iter():
    t=el.attrib.get("text","")
    if t: strings.append(t[:80])
    if el.attrib.get("resource-id")==SCREEN: close=dict(el.attrib)
  except Exception:pass
 _,activity,_=adb("shell","dumpsys","activity","activities",timeout=15)
 resumed=re.findall(r"(?m)^\s*(?:mResumedActivity|ResumedActivity):?\s*(.{0,200})",activity)
 info={"event":"snapshot","name":label,"at":now(),"resumed":resumed[:2],"visible_text":strings[:14],
       "close_button_present":close is not None,"close_button_clickable":close.get("clickable") if close else None,
       "close_button_bounds":close.get("bounds") if close else None}
 report["events"].append(info)
 print(json.dumps(info,ensure_ascii=False),flush=True)
def safe_log():
 p=subprocess.run(["adb","logcat","-d","-v","brief","-t","1200"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
 lines=p.stdout.decode(errors="replace").splitlines()
 chosen=[]
 for line in lines:
  if not re.search(r"(?i)(onetrust|cmpactivity|consent|cordova|chromium|webview|androidruntime|cookie|privacy)",line): continue
  if re.search(r"(?i)(bearer|authorization|api.?key|cookie:|set-cookie|password|secret|token)",line):continue
  # Output only signature and selected diagnostic terms: avoid publishing full PII, network URLs or cookies.
  line=re.sub(r"https?://\S+","[URL]",line)
  line=re.sub(r"[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}","[EMAIL]",line)
  line=re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b","[IP]",line)
  chosen.append(line[:230])
 (OUT/"cmp_log_excerpt.txt").write_text("\n".join(chosen[-180:]),encoding="utf8")
 report["selected_log_lines"]=len(chosen[-180:])
 # Do not interpret filtered logcat as definitive evidence of missing events.

apk=pathlib.Path("MyLotteries-v194.apk")
if not apk.exists():
 report["error"]="APK missing"; (OUT/"report.json").write_text(json.dumps(report,indent=2));raise SystemExit(0)
code,out,err=adb("install","-r",str(apk),timeout=120)
report["install_status"]=code
report["install_message"]=out.strip()[-70:]
if code==0:
 adb("logcat","-c")
 adb("shell","monkey","-p",ID,"-c","android.intent.category.LAUNCHER","1")
 time.sleep(13);capture("before")
 # Locate the actual "Continue without accepting" bounds, validated from UI hierarchy.
 xmlfile=OUT/"ui_before.xml"
 bounds=None
 if xmlfile.exists():
  try:
   for element in ET.parse(xmlfile).iter():
    if element.attrib.get("resource-id")==SCREEN and element.attrib.get("text")=="Continua senza accettare":
     bounds=element.attrib.get("bounds");break
  except Exception:pass
 if bounds:
  n=[int(x) for x in re.findall(r"\d+",bounds)]
  if len(n)==4:
   x=(n[0]+n[2])//2; y=(n[1]+n[3])//2
   adb("shell","input","tap",str(x),str(y))
   report["events"].append({"event":"tap_decline","at":now(),"coords":[x,y]})
   time.sleep(3);capture("after_3s")
   time.sleep(12);capture("after_15s")
   # Normal tap again is a diagnostic; never click Accept/Customize automatically.
   adb("shell","input","tap",str(x),str(y))
   report["events"].append({"event":"tap_decline_again","at":now(),"coords":[x,y]})
   time.sleep(10);capture("after_second")
 else:
  report["events"].append({"event":"decline_not_found","at":now()})
 safe_log()
report["finished_at"]=now()
(OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps({"summary":"V197 completed", "install":report["install_message"],"events":report["events"],"selected_log_lines":report.get("selected_log_lines",0)},ensure_ascii=False),flush=True)
