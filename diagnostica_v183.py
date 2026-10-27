#!/usr/bin/env python3
"""V183 - analisi statica e delimitata di asset JS pubblici dell'APK My Lotteries.
Solo download APK ufficiale + analisi locale: non esegue l'app e non chiama endpoint dell'app.
"""
import csv, hashlib, json, re, sys, zipfile
from pathlib import Path
from urllib.request import Request, urlopen

APK_URL = 'https://mylotteries.it/mobile/download/android/MyLotteries.apk'
OUT = Path('v183_risultati'); OUT.mkdir(exist_ok=True)
APK = OUT/'MyLotteries.apk'
MAX_APK = 90 * 1024 * 1024
MAX_JS = 18 * 1024 * 1024
TARGET = re.compile(r'10elotto|estrazion|diretta|websocket|socket|sorteggio|frequenti|numeriEstratti|listaNumeri|ordine|sequenz|draw', re.I)
PATH = re.compile(r'(/(?:del/)?[\w\-/.%@]{6,150}\.(?:json|do|xml)|https?://[^\s"\x27<>]{8,180})', re.I)
REDACT = re.compile(r'(?i)(bearer\s+\S+|(?:access_?token|refresh_?token|authorization|api[_-]?key|password)["\x27]?\s*[:=]\s*["\x27]?[^\s"\x27,}]{5,})')

def scrub(s):
    s = REDACT.sub('[REDACTED]', s)
    return ''.join(c if c.isprintable() else ' ' for c in s)[:350]

status={'apk_source':APK_URL,'apk_downloaded':False,'entries_scanned':0,'js_scanned':0,'contexts_recorded':0,'candidate_paths':0,'live_sequence_verified':False,'limitations':'Lettura statica soltanto: non dimostra dove passa la diretta, né certifica ordine dei 20 numeri.'}
rows=[]; paths={}
try:
    req=Request(APK_URL,headers={'User-Agent':'Mozilla/5.0 (compatible; static-study/1.0)'})
    with urlopen(req,timeout=40) as resp, APK.open('wb') as f:
        status['http_status']=resp.status
        total=0
        while True:
            block=resp.read(1024*1024)
            if not block: break
            total += len(block)
            if total>MAX_APK: raise ValueError('APK supera il limite di 90 MiB')
            f.write(block)
    status.update(apk_downloaded=True,apk_bytes=total,apk_sha256=hashlib.sha256(APK.read_bytes()).hexdigest())
    with zipfile.ZipFile(APK) as z:
        members=[m for m in z.infolist() if m.filename.startswith('assets/www/') and m.filename.endswith('.js') and m.file_size<=MAX_JS]
        status['entries_scanned']=len(members)
        for m in members:
            try: source=z.read(m).decode('utf-8','replace')
            except Exception: continue
            status['js_scanned']+=1
            matches=list(TARGET.finditer(source))
            # Priority: lines near extraction/draw keywords, bounded output
            for hit in matches[:75]:
                a=max(0,hit.start()-170);b=min(len(source),hit.end()+180)
                around=source[a:b]
                rows.append({'file':m.filename,'keyword':hit.group(0),'offset':hit.start(),'context_redacted':scrub(around)})
            for hit in PATH.finditer(source):
                raw=hit.group(1)
                if re.search('10elotto|estraz|frequen|sortegg|risultat|draw|live',raw,re.I):
                    paths[(m.filename,raw)]='possible reference; not tested'
    with (OUT/'contesti_v183.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['file','keyword','offset','context_redacted']);w.writeheader();w.writerows(rows[:2500])
    with (OUT/'percorsi_candidati_v183.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['file','path_found_in_app','status']);
        for (filename,p),label in list(paths.items())[:500]:w.writerow([filename,scrub(p),label])
    status['contexts_recorded']=min(len(rows),2500);status['candidate_paths']=min(len(paths),500)
except Exception as e:
    status['error']=f'{type(e).__name__}: {str(e)[:250]}'
finally:
    if APK.exists(): APK.unlink() # Non distribuire codice APK nell'artifact
    (OUT/'riepilogo_v183.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False,indent=2))
