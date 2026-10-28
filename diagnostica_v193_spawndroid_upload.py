#!/usr/bin/env python3
"""V193: authenticated upload of public APK to own SpawnDroid account.

GitHub secret SPAWNDROID_UPLOAD_KEY_V193 required, with only "upload" scope.
Does not run Android, attempt unavailable API endpoints, or touch sniper-bot.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.request
import urllib.error

EXPECTED_SHA256="857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a"
APK_URL="https://mylotteries.it/mobile/download/android/MyLotteries.apk"
UPLOAD_URL="https://app.spawndroid.io/api/apps"
key=os.environ.get("SPAWNDROID_UPLOAD_KEY_V193","").strip()
if not key:
    print("NO_UPLOAD: configure the upload-scoped SPAWNDROID_UPLOAD_KEY_V193 repository Actions secret first.")
    sys.exit(0)
apk=pathlib.Path("MyLotteries-v193.apk")
req=urllib.request.Request(APK_URL,headers={"User-Agent":"Mozilla/5.0 (APK provenance test)"})
with urllib.request.urlopen(req,timeout=90) as r, apk.open("wb") as f:
    while True:
        b=r.read(1048576)
        if not b:break
        f.write(b)
        if f.tell()>95*1048576:
            raise RuntimeError("Unexpected APK size; stopping.")
digest=hashlib.sha256(apk.read_bytes()).hexdigest()
if digest!=EXPECTED_SHA256:
    raise RuntimeError("APK SHA-256 mismatch; abort upload. Actual="+digest)
print("APK verified by SHA-256, size:",apk.stat().st_size)
response=pathlib.Path("v193_upload_result.json")
cmd=["curl","--silent","--show-error","--fail-with-body",
     "--max-time","150","--retry","0",
     "--request","POST",UPLOAD_URL,
     "--header","Authorization: Bearer "+key,
     "--form","file=@"+str(apk),
     "--output",str(response),
     "--write-out","%{http_code}"]
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
print("SpawnDroid upload HTTP status:",p.stdout[-3:] if p.stdout else "unknown")
if p.returncode!=0:
    print("Upload failed; no credentials or response body logged.")
    sys.exit(1)
try:
    obj=json.loads(response.read_text(encoding="utf8"))
except Exception:
    print("Upload HTTP 2xx, but response JSON unavailable; check own SpawnDroid Artifacts.")
else:
    print("Upload accepted; returned fields:",[k for k in obj if k in ("id","slug","name","status")] if isinstance(obj,dict) else "array")
    if isinstance(obj,dict):
        print("Artifact id:",str(obj.get("id","not returned"))[:100])
print("No session started. Open SpawnDroid Artifacts to check the uploaded APK.")
