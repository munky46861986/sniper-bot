#!/usr/bin/env python3
"""V177: bounded, read-only diagnostic of selected paths evidenced by V176."""
import csv, json, re, time
from pathlib import Path
from urllib.parse import urlsplit
import requests

BASE = 'https://showcase.giocodellotto.it'
PATHS = [
 '/del/serviziInformativiFE/jsonrest/10elotto/frequenti.json',
 '/del/serviziInformativiFE/jsonrest/10elotto/frequentiGong.json',
 '/del/serviziInformativiFE/jsonrest/10elotto/frequentiTop10.json',
 '/del/serviziFE/jsonrest/10elotto/estrazioniMensile.json',
 '/del/serviziFE/jsonrest/10elotto/get10eLottoHH.json',
 '/del/serviziFE/jsonrest/10elotto/raccolteFrequentiGiornaliere.json',
 '/del/serviziFE/jsonrest/10elotto/raccolteFrequentiV2.json',
]
OUT = Path('risultati_v177'); OUT.mkdir(exist_ok=True)
KEYS = re.compile(r'estraz|numer|sequenz|ordin|concor|oro|data|result|draw|frequency|frequen', re.I)

# A JSON list of 20 unique integers, 1..90, is a candidate only, never proof of display order.
def candidates(node, path='$', depth=0, output=None):
    if output is None: output=[]
    if depth > 18 or len(output) >= 50: return output
    if isinstance(node,list):
        if len(node)==20 and all(type(n) is int and 1<=n<=90 for n in node) and len(set(node))==20:
            output.append({'json_path':path, 'numbers':' '.join(f'{n:02d}' for n in node), 'ascending':node==sorted(node)})
        else:
            for i,item in enumerate(node[:300]): candidates(item,f'{path}[{i}]',depth+1,output)
    elif isinstance(node,dict):
        for k,item in list(node.items())[:200]: candidates(item,f'{path}.{str(k)[:80]}',depth+1,output)
    return output

def structure(node,depth=0):
    if depth>=3:return type(node).__name__
    if isinstance(node,dict): return {str(k)[:80]:structure(v,depth+1) for k,v in list(node.items())[:25]}
    if isinstance(node,list):return {'type':'list','count':len(node),'first_item':structure(node[0],depth+1) if node else None}
    return type(node).__name__

session=requests.Session()
session.headers.update({'User-Agent':'Mozilla/5.0 (compatible; read-only-research/1.0)','Accept':'application/json, text/plain, */*'})
rows=[]; seq=[]; info=[]
for path in PATHS:
    entry={'path':path,'http_status':'','content_type':'','bytes_examined':0,'json_valid':False,'note':'','final_host':''}
    try:
        response=session.get(BASE+path,timeout=(7,12),allow_redirects=False,stream=True)
        entry['http_status']=response.status_code
        entry['content_type']=response.headers.get('content-type','')[:100]
        entry['final_host']=urlsplit(response.url).hostname
        if response.status_code in (301,302,303,307,308):
            entry['note']='redirect not followed: '+response.headers.get('location','')[:180]
        elif response.status_code==200:
            buffer=bytearray()
            for part in response.iter_content(16384):
                if part: buffer.extend(part)
                if len(buffer)>262144: break
            entry['bytes_examined']=len(buffer)
            if len(buffer)>262144:entry['note']='response truncated at 256 KiB'
            try:
                data=json.loads(buffer.decode('utf-8-sig'))
                entry['json_valid']=True
                info.append({'path':path,'structure':structure(data), 'relevant_top_keys':[str(k) for k in data if KEYS.search(str(k))][:30] if isinstance(data,dict) else []})
                for c in candidates(data):seq.append({'endpoint':path,**c,'validated_with_mylotteries':False})
            except (ValueError,UnicodeError):entry['note']+='; not parseable JSON (or truncated)'
        else:entry['note']='HTTP non-success; no retry or bypass'
        response.close()
    except requests.RequestException as exc: entry['note']=type(exc).__name__+': '+str(exc)[:150]
    rows.append(entry);print(entry['http_status'],path,entry['note'],flush=True)
    time.sleep(0.8)

with (OUT/'endpoint_v177.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (OUT/'sequenze_candidate_v177.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['endpoint','json_path','numbers','ascending','validated_with_mylotteries']);w.writeheader();w.writerows(seq)
(OUT/'strutture_json_v177.json').write_text(json.dumps(info,indent=2,ensure_ascii=False),encoding='utf8')
(OUT/'riepilogo_v177.json').write_text(json.dumps({'endpoints_tested':len(rows),'http_200':sum(r['http_status']==200 for r in rows),'json_parsed':sum(r['json_valid'] for r in rows),'unvalidated_candidate_sequences':len(seq),'original_order_validated':False,'bot_modified':False},indent=2),encoding='utf8')
print('Report created in',OUT)
