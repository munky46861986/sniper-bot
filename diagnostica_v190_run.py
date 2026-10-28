#!/usr/bin/env python3
"""Download the public My Lotteries APK and run the isolated V190 static audit."""
import urllib.request, pathlib, hashlib, subprocess, sys
url="https://mylotteries.it/mobile/download/android/MyLotteries.apk"
target=pathlib.Path("MyLotteries_V190.apk")
req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (public source audit)"})
with urllib.request.urlopen(req,timeout=90) as response, target.open("wb") as out:
    while True:
        part=response.read(1024*1024)
        if not part: break
        out.write(part)
        if out.tell()>95*1024*1024: raise RuntimeError("APK over 95 MiB")
sha=hashlib.sha256(target.read_bytes()).hexdigest()
print("APK downloaded",target.stat().st_size,"bytes; SHA-256",sha,flush=True)
subprocess.run([sys.executable,"diagnostica_v190_offline.py",str(target)],check=True)
