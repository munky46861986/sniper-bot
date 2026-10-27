#!/usr/bin/env python3
"""Diagnostica statica di APK pubblico + verifica accesso Eurobet; nessun login, nessun bypass."""
import csv, hashlib, io, json, re, sys, urllib.request, urllib.error, zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

OUT=Path('risultati_v175'); OUT.mkdir(exist_ok=True)
APK='https://mylotteries.it/mobile/download/android/MyLotteries.apk'
EURO='https://www.eurobet.it/'
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; V175-public-diagnostic/1.0)'}
report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'version':'V175','apk_url':APK,'download_ok':False,'apk_zip_valid':False,'eurobet':{},'sequence_order_found':False,'notes':['Only static inspection of publicly provided APK; no app execution, interception, authentication or bypass.','Extracted URLs and hostnames are hints, not confirmed public APIs.','No 20-number extraction order can be confirmed from static strings alone.']}

def request(url, method='GET', timeout=25):
    req=urllib.request.Request(url, headers=HEADERS, method=method)
    return urllib.request.urlopen(req, timeout=timeout)

def csvout(name, fields, rows):
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

# Public website status only; do not attempt challenge evasion.
try:
    with request(EURO) as r:
        data=r.read(100000)
        report['eurobet']={'http':r.status,'final_host':urlsplit(r.url).hostname,'html_like':b'<html' in data.lower(),'bytes_previewed':len(data)}
except urllib.error.HTTPError as e:
    report['eurobet']={'http':e.code,'error':'HTTP response'}
except Exception as e:
    report['eurobet']={'error':type(e).__name__+': '+str(e)[:160]}

max_bytes=90*1024*1024
try:
    with request(APK,timeout=50) as r:
        total=bytearray()
        while True:
            b=r.read(1024*1024)
            if not b: break
            total.extend(b)
            if len(total)>max_bytes: raise ValueError('APK exceeds 90 MiB cap')
        apk=bytes(total)
        report['apk_http']=r.status
    report['apk_bytes']=len(apk)
    report['apk_sha256']=hashlib.sha256(apk).hexdigest()
    report['download_ok']=True
    hostcounts=Counter(); clues=[]; candidates=set(); entries=0; searched=0
    with zipfile.ZipFile(io.BytesIO(apk)) as z:
        report['apk_zip_valid']=True
        for entry in z.infolist():
            if entry.is_dir(): continue
            entries+=1
            # Don't decompress giant archives, native libraries or media assets.
            path=entry.filename
            if entry.file_size>12*1024*1024 or not (path.endswith(('.dex','.xml','.json','.js','.txt','.properties','.html')) or '/assets/' in path): continue
            try: blob=z.read(entry)
            except Exception: continue
            searched+=1
            # URL scanning on binary is only suggestive, not decompilation.
            s=blob.decode('latin1','ignore')
            for raw in re.findall(r'https?://[A-Za-z0-9._~:/?#\[\]@!$&\'()*+,;=%-]{5,220}',s):
                raw=raw.rstrip('.,;)>\\')
                host=urlsplit(raw).hostname
                if not host or '.' not in host: continue
                host=host.lower()
                hostcounts[host]+=1
                if re.search(r'lotto|extract|estraz|draw|risultat|api|ws',raw,re.I):
                    # redact the path, querystring, userinfo and tokens: only hostname + generic signal
                    candidates.add((host,'url_keyword',path))
            for term in ('websocket','10elotto','estrazioni','result','draw','api/v','socket.io'):
                n=len(re.findall(re.escape(term),s,re.I))
                if n: clues.append({'archive_file':path,'keyword':term,'occurrences':n})
    report['apk_entries']=entries; report['files_scanned']=searched
    csvout('domini_apk_v175.csv',['hostname','occurrences'],[{'hostname':h,'occurrences':n} for h,n in hostcounts.most_common(100)])
    csvout('indizi_apk_v175.csv',['archive_file','keyword','occurrences'],clues[:300])
    csvout('possibili_servizi_v175.csv',['hostname','kind','archive_file'],[dict(zip(('hostname','kind','archive_file'),v)) for v in sorted(candidates)][:200])
    report['domains_found']=len(hostcounts); report['keyword_clues']=len(clues); report['possible_services']=len(candidates)
except Exception as e:
    report['apk_error']=type(e).__name__+': '+str(e)[:200]

(OUT/'riepilogo_v175.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(report,indent=2,ensure_ascii=False))
