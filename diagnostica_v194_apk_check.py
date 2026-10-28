#!/usr/bin/env python3
"""V194: official APK compatibility check for a standard Android emulator.
No service calls except downloading the public APK; no browser or auth bypass.
"""
import hashlib, json, os, pathlib, urllib.request, zipfile
from collections import Counter

URL = "https://mylotteries.it/mobile/download/android/MyLotteries.apk"
EXPECTED = "857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a"
APK = pathlib.Path("MyLotteries-v194.apk")
OUT = pathlib.Path("v194_risultati")
OUT.mkdir(exist_ok=True)
report={"version":194,"source":URL,"apkinstalled":False,
        "purpose":"Standard Android emulator compatibility test, not live feed bypass"}
try:
    with urllib.request.urlopen(urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0 (App compatibility test)"}),timeout=90) as r, APK.open("wb") as f:
        while True:
            chunk=r.read(1048576)
            if not chunk: break
            f.write(chunk)
            if f.tell()>95*1048576: raise RuntimeError("APK unexpectedly large")
    report["apk_bytes"]=APK.stat().st_size
    report["sha256"]=hashlib.sha256(APK.read_bytes()).hexdigest()
    if report["sha256"]!=EXPECTED: raise RuntimeError("APK SHA256 differs from previously analyzed build")
    with zipfile.ZipFile(APK) as z:
        libs=[n for n in z.namelist() if n.startswith("lib/") and n.endswith(".so") and len(n.split("/"))>=3]
    arch=sorted(set(n.split("/")[1] for n in libs))
    report["native_architectures"]=arch
    report["native_library_count"]=len(libs)
    can=(not arch or bool(set(arch)&{"x86","x86_64"}))
    report["can_test_x86_64_emulator"]=can
    if not can:
        report["reason"]="Native libraries only for non-x86 architectures; skip incompatible emulator"
    else:
        report["reason"]="No incompatible native ABI detected; emulator install test permitted"
except Exception as ex:
    report["error"]=type(ex).__name__+": "+str(ex)[:200]
    can=False
(OUT/"apk_compatibility.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps(report,indent=2,ensure_ascii=False))
if os.getenv("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as f:
        f.write(f"can_emulate={'true' if can else 'false'}\n")
