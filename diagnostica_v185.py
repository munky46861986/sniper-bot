#!/usr/bin/env python3
"""V185: mappatura statica di eventi My Lotteries, sola lettura e senza chiamate API interne."""
import csv, hashlib, io, json, re, sys, zipfile
from pathlib import Path
from urllib.request import urlopen, Request

APK_URL='https://mylotteries.it/mobile/download/android/MyLotteries.apk'
OUT=Path('v185_risultati'); OUT.mkdir(exist_ok=True)
TERMS={
 'progressive_event':r'viewEmit_get10eLOTTONumbersProgressiveExtrations',
 'day_event':r'viewEmit_get10eLOTTODaysExtraction',
 'live_ui':r'Guarda la diretta',
 'drawn_numbers':r'numeriEstratti',
 'progressive_variants':r'get10eLOTTONumbersProgressiveExtrations|get10eLOTTODaysExtraction',
}
CALL_HINT=re.compile(r'\b(fetch|axios|XMLHttpRequest|WebSocket|subscribe|dispatch|emit|onMounted|watch|\.get|\.post)\s*\(',re.I)
SECRET=re.compile(r'(?i)(bearer\s+[a-z0-9._-]+|(?:api[_-]?key|token|authorization|password|secret)\s*[:=]\s*[\'\"]?[^\s,;\'\"]{10,})')

def context(s):
 s=SECRET.sub('[REDACTED]',s)
 return re.sub(r'\s+',' ',s)[:1000]

def csv_write(name, fields, rows):
 with (OUT/name).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

report={'version':'185','source':APK_URL,'apk_downloaded':False,'js_files_scanned':0,'exact_event_occurrences':0,'events_with_multiple_files':[], 'network_endpoint_identified':False,'live_sequence_verified':False,'notes':'Analisi statica. Eventi, frammenti e vicinanze non dimostrano un collegamento alla rete.'}
hits=[]; adjacent=[]; filemap={}; download_bytes=0
try:
 req=Request(APK_URL,headers={'User-Agent':'Mozilla/5.0 (static source audit)'})
 with urlopen(req,timeout=45) as r:
  data=bytearray()
  while True:
   block=r.read(1024*1024)
   if not block:break
   data.extend(block)
   if len(data)>95*1024*1024:raise ValueError('APK exceeds 95 MiB limit')
 report['apk_downloaded']=True;report['apk_bytes']=len(data);report['apk_sha256']=hashlib.sha256(data).hexdigest()
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  for info in z.infolist():
   if not (info.filename.startswith('assets/www/') and info.filename.endswith('.js')):continue
   if info.file_size>8*1024*1024:continue
   report['js_files_scanned']+=1
   src=z.read(info).decode('utf-8','replace')
   filemap[info.filename]=src
   for term,pattern in TERMS.items():
    for m in list(re.finditer(pattern,src,re.I))[:150]:
     before=src[max(0,m.start()-320):m.start()]
     after=src[m.end():min(len(src),m.end()+480)]
     hits.append({'file':info.filename,'type':term,'match':m.group(0),'offset':m.start(), 'before':context(before),'after':context(after),'interpretation':'static text occurrence; handler not proven'})
   # check whether event string appears near obvious registration/call patterns, not asserting true linkage
   relevant=[m for term in ('progressive_event','day_event','live_ui','drawn_numbers') for m in re.finditer(TERMS[term],src,re.I)]
   calls=list(CALL_HINT.finditer(src))
   for ev in relevant[:40]:
    best=min(calls,key=lambda c:abs(c.start()-ev.start()),default=None)
    if best:
     adjacent.append({'file':info.filename,'event':ev.group(0),'event_offset':ev.start(),'nearby_call':best.group(0),'call_offset':best.start(),'distance_chars':abs(best.start()-ev.start()),'call_context':context(src[max(0,best.start()-100):best.end()+180]),'confidence':'PROXIMITY_ONLY'})
 report['exact_event_occurrences']=sum(h['type'] in ('progressive_event','day_event') for h in hits)
 report['events_with_multiple_files']=[{'event':key,'files':sorted(set(h['file'] for h in hits if h['type']==key))} for key in ('progressive_event','day_event','live_ui','drawn_numbers')]
 csv_write('occorrenze_v185.csv',['file','type','match','offset','before','after','interpretation'],hits)
 csv_write('vicinanze_chiamate_v185.csv',['file','event','event_offset','nearby_call','call_offset','distance_chars','call_context','confidence'],sorted(adjacent,key=lambda r:r['distance_chars']))
 report['occurrences_written']=len(hits);report['proximities_written']=len(adjacent)
except Exception as e:
 report['error']=type(e).__name__+': '+str(e)[:250]
finally:
 (OUT/'riepilogo_v185.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))
