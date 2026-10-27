#!/usr/bin/env python3
"""V184: analisi statica mirata di due bundle JS nell'APK pubblico My Lotteries.
Non esegue app, non chiama API interne, non elude controlli.
"""
import csv, hashlib, json, re, zipfile
from pathlib import Path
from urllib.request import urlopen, Request

URL='https://mylotteries.it/mobile/download/android/MyLotteries.apk'
OUT=Path('v184_risultati');OUT.mkdir(exist_ok=True)
APK=OUT/'download_temporaneo.apk'
FILES=['archive10eLotto-index-js.a89fbbef.js','4256.0a81cc64.js']
TERMS=[r'Guarda la diretta',r'numeriEstratti',r'websocket',r'WebSocket',r'get10eLottoHH',r'estrazione',r'diretta',r'10elotto',r'http[s]?://',r'\.json',r'fetch\(',r'axios',r'XMLHttpRequest',r'\.subscribe\(',r'\.emit\(']
PATTERN=re.compile('|'.join('(?:'+x+')' for x in TERMS),re.I)
PATHS=re.compile(r'https?://[^\s\"\x27<>`]{8,180}|/[A-Za-z0-9_./-]{4,120}\.(?:json|do|xml)',re.I)
SECRET=re.compile(r'(?i)((?:bearer\s+)[A-Za-z0-9._-]+|(?:token|authorization|password|secret|api[_-]?key)\s*[:=]\s*[\"\x27]?[A-Za-z0-9._-]{12,})')

def clean(s):
    return SECRET.sub('[REDACTED]', ''.join(' ' if c in '\r\n\t' else c for c in s))[:900]

def write_csv(path,cols,rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)

report={'source':URL,'download_success':False,'sha256':None,'files_requested':FILES,'files_present':[],'contexts':0,'candidate_urls':0,'live_feed_identified':False,'original_order_verified':False,'note':'La presenza di stringhe non conferma una API live né l’ordine visualizzato.'}
contexts=[]; urls=[]; relations=[]
try:
    req=Request(URL,headers={'User-Agent':'Mozilla/5.0 (static analysis; public APK)'})
    with urlopen(req,timeout=35) as stream,APK.open('wb') as f:
        size=0
        while chunk:=stream.read(1024*1024):
            size+=len(chunk)
            if size>90*1024*1024:raise RuntimeError('APK supera 90 MiB')
            f.write(chunk)
    report.update(download_success=True,download_bytes=size,sha256=hashlib.sha256(APK.read_bytes()).hexdigest())
    with zipfile.ZipFile(APK) as z:
        allnames=z.namelist()
        for short in FILES:
            matches=[n for n in allnames if n.startswith('assets/www/') and n.endswith('/'+short) or n=='assets/www/'+short]
            if not matches:
                report.setdefault('missing_files',[]).append(short);continue
            filename=matches[0]
            info=z.getinfo(filename)
            if info.file_size>20*1024*1024:continue
            src=z.read(filename).decode('utf-8','replace')
            report['files_present'].append({'file':filename,'size':len(src),'sha256':hashlib.sha256(src.encode()).hexdigest()})
            hits=list(PATTERN.finditer(src))
            for i,m in enumerate(hits[:350]):
                left=max(0,m.start()-240);right=min(len(src),m.end()+360)
                contexts.append({'file':short,'term':m.group(0),'offset':m.start(),'context':clean(src[left:right])})
            for m in PATHS.finditer(src):
                item=m.group(0).rstrip('.,);')
                if re.search(r'lotto|estraz|live|sorteg|frequen|risultat|websocket|socket',item,re.I):
                    urls.append({'file':short,'value':clean(item),'offset':m.start(),'verification':'NOT TESTED'})
            # Analizza se i riferimenti coesistono nella stessa finestra di codice; NON prova collegamento runtime
            patterns={'diretta':r'Guarda la diretta|diretta','numbers':r'numeriEstratti','request':r'fetch\(|axios|\.json|\.get\(','socket':r'websocket|\.subscribe\('}
            pts={k:[m.start() for m in re.finditer(p,src,re.I)][:100] for k,p in patterns.items()}
            for a,b in [('diretta','request'),('numbers','request'),('numbers','socket')]:
                best=min(((abs(x-y),x,y) for x in pts[a] for y in pts[b]),default=None)
                if best:
                    relations.append({'file':short,'pair':a+' / '+b,'minimum_char_distance':best[0], 'first_offset':best[1], 'second_offset':best[2], 'meaning':'proximity only; not proven data flow'})
    write_csv(OUT/'contesti_mirati_v184.csv',['file','term','offset','context'],contexts)
    distinct=list({(x['file'],x['value']):x for x in urls}.values())
    write_csv(OUT/'riferimenti_v184.csv',['file','value','offset','verification'],distinct)
    write_csv(OUT/'vicinanze_v184.csv',['file','pair','minimum_char_distance','first_offset','second_offset','meaning'],relations)
    report.update(contexts=len(contexts),candidate_urls=len(distinct))
except Exception as e:
    report['error']=type(e).__name__+': '+str(e)[:250]
finally:
    if APK.exists():APK.unlink()
    (OUT/'riepilogo_v184.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))
