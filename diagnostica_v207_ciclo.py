#!/usr/bin/env python3
"""V207: observe one full 5-minute draw cycle on publicly available app UI.

No betting, authentication, network workarounds, advertising consent,
direct API calls or attempts to access hidden UI elements. Capture screenshots
and visible accessibility labels for ~6m20s, then summarize differences.
"""
import hashlib,json,re,subprocess,time,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path

OUT=Path("v207_risultati");OUT.mkdir(exist_ok=True)
REPORT={"version":207,"purpose":"Observe normal 10eLotto draw-cycle UI only",
        "original_order_verified":False,"opened_live":False,"samples":[],
        "events":[],"started_utc":datetime.now(timezone.utc).isoformat()}
T0=time.monotonic()
def utc():return datetime.now(timezone.utc).isoformat()
def event(name,**data):
    info={"event":name,"at":utc(),"t_elapsed_s":round(time.monotonic()-T0,1),**data}
    REPORT["events"].append(info)
    print(json.dumps(info,ensure_ascii=False),flush=True)
def call(cmd,timeout=35):
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        return p.returncode,p.stdout,p.stderr.decode("utf8","replace")[:180]
    except Exception as ex:return 99,b"",type(ex).__name__+": "+str(ex)[:100]
def adb(*args,timeout=35):return call(["adb",*args],timeout=timeout)
def snapshot(tag,ui=True):
    code,png,err=adb("exec-out","screencap","-p",timeout=22)
    item={"tag":tag,"utc":utc(),"elapsed_s":round(time.monotonic()-T0,1),
          "image_bytes":len(png),"image_sha256":hashlib.sha256(png).hexdigest() if code==0 else None,
          "interesting":[]}
    if code==0:(OUT/(tag+".png")).write_bytes(png)
    if ui:
        # Standard Android accessibility tree. Hidden nodes are explicitly excluded.
        dump,_,derr=adb("shell","uiautomator","dump","/sdcard/v207.xml",timeout=28)
        if dump==0:
            adb("pull","/sdcard/v207.xml",str(OUT/(tag+".xml")),timeout=28)
            try:
                root=ET.fromstring((OUT/(tag+".xml")).read_bytes())
                for node in root.iter("node"):
                    txt=node.attrib.get("text","").strip()
                    b=node.attrib.get("bounds","")
                    if not txt:continue
                    match=any(w in txt.lower() for w in
                       ("estrazione","diretta","10elotto","10e lotto","secondi","numero","countdown"))
                    if match:
                        item["interesting"].append({"text":txt[:100],"bounds":b,
                                                  "visible":b not in ("","[0,0][0,0]")})
            except Exception as e:item["ui_error"]=type(e).__name__
        else:item["ui_error"]="dump_failed"
    REPORT["samples"].append(item)
    event("screenshot",tag=tag,image_sha256=item["image_sha256"],
          interesting=item["interesting"][:8],ui_error=item.get("ui_error"))
    return item
def ui_nodes(item):
    path=OUT/(item["tag"]+".xml")
    if not path.is_file():return []
    try:return list(ET.fromstring(path.read_bytes()).iter("node"))
    except Exception:return []
def click_visible(item,fragments):
    for node in ui_nodes(item):
        t=node.attrib.get("text","").strip().lower()
        if not any(f.lower() in t for f in fragments):continue
        nums=[int(x) for x in re.findall(r"\d+",node.attrib.get("bounds",""))]
        if len(nums)!=4:continue
        x1,y1,x2,y2=nums
        # Emulator in portrait 320x640 initially, later 600x1180.
        _,wraw,_=adb("shell","wm","size")
        m=re.search(r"Override size:\s*(\d+)x(\d+)",wraw.decode(errors="replace"))
        if not m:m=re.search(r"Physical size:\s*(\d+)x(\d+)",wraw.decode(errors="replace"))
        width,height=(int(m.group(1)),int(m.group(2))) if m else (600,1180)
        if x1<0 or y1<0 or x2>width or y2>height or x2-x1<8 or y2-y1<8:continue
        x=(x1+x2)//2;y=(y1+y2)//2
        adb("shell","input","tap",str(x),str(y))
        event("click_public_ui",text=t[:70],xy=[x,y])
        return True
    return False
try:
    status,msg,_=adb("install","-r","MyLotteries-v194.apk",timeout=130)
    event("install",status=status,result=msg.decode(errors="replace").strip()[-80:])
    if status!=0:raise RuntimeError("apk_install_failed")
    adb("shell","monkey","-p","it.lottomatica.lotto","-c",
        "android.intent.category.LAUNCHER","1")
    time.sleep(14)
    first=snapshot("privacy_start")
    if not click_visible(first,["continua senza accettare"]):
        raise RuntimeError("privacy_decline_not_accessible")
    time.sleep(18)
    intro=snapshot("after_decline")
    if not click_visible(intro,["fine"]):
        # Previously screenshot-confirmed on the same emulator profile (320x640).
        adb("shell","input","tap","225","463")
        event("click_previously_verified_intro_finish",xy=[225,463])
    time.sleep(10)
    adb("shell","wm","size","600x1180")
    time.sleep(10)
    snapshot("home_before_cycle")
    # Need a full 5-minute cycle irrespective of when the runner begins.
    # 16 frames spaced 25 seconds = 375 seconds.
    period=25
    observed_start=time.monotonic()
    last_image=None
    for i in range(16):
        target=observed_start+i*period
        delay=target-time.monotonic()
        if delay>0:time.sleep(delay)
        item=snapshot("cycle_%02d"%i,ui=(i%2==0 or i==15))
        if last_image is not None:
            item["changed_from_previous"]=item["image_sha256"]!=last_image
        last_image=item["image_sha256"]
        if i==0:REPORT["observation_started_utc"]=item["utc"]
        REPORT["observation_ended_utc"]=item["utc"]
        # Click only a visibly accessible, explicitly read-only live-draw button.
        if not REPORT["opened_live"] and i%2==0 and click_visible(item,["segui l'estrazione","guarda la diretta"]):
            REPORT["opened_live"]=True
            event("opened_public_live_screen")
            time.sleep(8)
            snapshot("live_after_open")
    images=[x.get("image_sha256") for x in REPORT["samples"] if x["tag"].startswith("cycle_")]
    REPORT["distinct_cycle_screenshots"]=len(set(images))
    REPORT["observed_cycle_frames"]=len(images)
except Exception as e:
    REPORT["error"]=type(e).__name__+": "+str(e)[:180]
    event("diagnostic_error",description=REPORT["error"])
finally:
    REPORT["finished_utc"]=utc()
    (OUT/"report.json").write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"final":"V207","frames":REPORT.get("observed_cycle_frames",0),
      "distinct_screens":REPORT.get("distinct_cycle_screenshots"),
      "opened_live":REPORT["opened_live"],"error":REPORT.get("error"),
      "observation_started":REPORT.get("observation_started_utc"),
      "observation_ended":REPORT.get("observation_ended_utc")},ensure_ascii=False),flush=True)
