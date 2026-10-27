#!/usr/bin/env python3
"""V176: analisi statica locale dell'APK ufficiale, senza esecuzione né chiamate agli endpoint trovati."""
import csv, hashlib, io, json, re, urllib.request, zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

APK_URL='https://mylotteries.it/mobile/download/android/MyLotteries.apk'
OUT=Path('risultati_v176'); OUT.mkdir(exist_ok=True)
FOCUS=['main.79046245.js','9961.e60531af.js','3743.b31ac562.js','4256.0a81cc64.js']
TERMS=['10elotto','estrazioni','risultati','result','websocket','socket.io','ordine','sequenza','extraction','draw']
INTERESTING=re.compile(r'10elotto|estraz|risultat|websocket|socket\.io|draw|sequence|ordine|lotto',re.I)
report={'version':'V176','timestamp_utc':datetime.now(timezone.utc).isoformat(), 'apk_source':APK_URL,'focused_files':FOCUS,'sequence_order_validated':False,'note':'Static hints are NOT validated APIs or original extraction sequences. No endpoint probes.'}

def write_csv(filename,fields,rows):
    with (OUT/filename).open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def clean_context(s):
    # Do not export tokens, credentials, full query strings, or large code fragments.
    s=re.sub(r'https?://[^\s"\'`\\<>]+',lambda m:'[URL host: '+(urlsplit(m.group(0)).hostname or 'unknown')+']',s)
    s=re.sub(r'(?i)(api[_-]?key|authorization|bearer|token|password|secret)[^,;}]{0,80}', '[REDACTED]', s)
    return re.sub(r'[^\x20-\x7E]', ' ', s)[:155]

try:
    req=urllib.request.Request(APK_URL,headers={'User-Agent':'Mozilla/5.0 V176 static research'})
    with urllib.request.urlopen(req,timeout=90) as r:
        chunks=[];total=0
        while True:
            b=r.read(1024*1024)
            if not b: break
            total+=len(b)
            if total>95*1024*1024:raise ValueError('APK exceeds 95 MiB safety cap')
            chunks.append(b)
    blob=b''.join(chunks)
    report['apk_bytes']=len(blob);report['sha256']=hashlib.sha256(blob).hexdigest()
    matches=[]; contexts=[]; urls=[]; files_found=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            if not any(name.endswith('/'+f) for f in FOCUS):continue
            file_size=z.getinfo(name).file_size
            if file_size>25*1024*1024:
                files_found.append({'file':name,'size':file_size,'status':'skipped_oversized'});continue
            s=z.read(name).decode('utf-8','replace')
            files_found.append({'file':name,'size':file_size,'status':'analyzed'})
            for t in TERMS:
                occurrences=len(list(re.finditer(re.escape(t),s,re.I)))
                matches.append({'file':name,'term':t,'count':occurrences})
                if not occurrences:continue
                for m in list(re.finditer(re.escape(t),s,re.I))[:8]:
                    contexts.append({'file':name,'keyword':t,'offset':m.start(),'context_redacted':clean_context(s[max(0,m.start()-60):m.end()+95])})
            for m in re.finditer(r'https?://[^\s"\'`\\<>]{5,240}',s):
                raw=m.group(0).rstrip('.,;)>}')
                host=urlsplit(raw).hostname
                if not host or '.' not in host:continue
                path=urlsplit(raw).path[:90]
                # Store sanitized path only when strongly relevant; no queries, fragments, keys or userinfo.
                if INTERESTING.search(raw):
                    urls.append({'file':name,'host':host.lower(),'path_if_relevant':path if INTERESTING.search(path) else '', 'nearby_keyword':next((t for t in TERMS if t in raw.lower()),'site-reference')})
    report['files_found']=files_found
    report['keyword_matches']=sum(x['count'] for x in matches)
    report['candidate_reference_count']=len(urls)
    report['conclusion']='Referential evidence only: no proof of 20-number presentation order.'
    write_csv('parole_chiave_v176.csv',['file','term','count'],matches)
    write_csv('contesti_redatti_v176.csv',['file','keyword','offset','context_redacted'],contexts)
    write_csv('riferimenti_url_v176.csv',['file','host','path_if_relevant','nearby_keyword'],sorted({tuple(x.values()) for x in urls}) and [dict(zip(['file','host','path_if_relevant','nearby_keyword'],x)) for x in sorted({tuple(x.values()) for x in urls})] or [])
except Exception as exc:
    report['error']=type(exc).__name__+': '+str(exc)[:250]
(OUT/'riepilogo_v176.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
