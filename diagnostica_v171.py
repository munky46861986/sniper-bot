#!/usr/bin/env python3
"""V171, sola lettura: verifica fonti pubbliche e salva SOLO array espliciti.
Non aggira 403/500; non prova che l'array sia ordine animato My Lotteries.
"""
import argparse, csv, json, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

SOURCES = [
 ('UFFICIALE', 'https://www.lotto-italia.it/10-e-lotto/estratti'),
 ('LOTTOMATICA', 'https://www.lottomatica.it/lotterie/info/estrazioni'),
 ('TOTOFORTUNA', 'https://www.totofortuna.it/estrazioni-10elotto-ogni-5-minuti.php'),
 ('EUROBET_PAGINA', 'https://www.eurobet.it/it/lotterie/10elotto'),
 ('EUROBET_FEED_NOTO', 'https://www.eurobet.it/del/serviziFE/jsonrest/10elotto/raccolteFrequentiV2.json'),
]
COLUMNS = ['fonte','concorso','timestamp_ms','utc','stato','quinto_feed','quinto_crescente',*[f'p{i:02d}' for i in range(1,21)]]

def validate(entry):
 if not isinstance(entry, dict): return None
 values = entry.get('numeri')
 if not isinstance(values,list) or len(values)!=20: return None
 try:
  if any(isinstance(v,bool) or not isinstance(v,(str,int)) for v in values): return None
  nums=[int(v) for v in values]
  draw=int(entry['progressivoGiornaliero'])
  stamp=int(entry['timestampProssimaEstrazione'])
  if len(set(nums))!=20 or not all(1<=n<=90 for n in nums) or not 1<=draw<=288 or stamp<1500000000000: return None
  return dict(concorso=draw,timestamp_ms=stamp,utc=datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat(),stato=str(entry.get('statoRaccolta',''))[:24],quinto_feed=nums[4],quinto_crescente=sorted(nums)[4],nums=nums)
 except (ValueError, KeyError, TypeError, OverflowError): return None

def run(out, timeout):
 out.mkdir(parents=True,exist_ok=True)
 statuses=[]; candidates={}; session=requests.Session()
 session.headers.update({'User-Agent':'V171-public-readonly-diagnostic/1.0'})
 for name,url in SOURCES:
  row=dict(fonte=name,host=urlparse(url).hostname,http=None,content_type='',bytes=0,indicazione='')
  try:
   resp=session.get(url,timeout=timeout,allow_redirects=True)
   row.update(http=resp.status_code,content_type=resp.headers.get('Content-Type','').split(';')[0],bytes=len(resp.content))
   if resp.status_code!=200:
    row['indicazione']='HTTP_NON_DISPONIBILE_NON_RITENTARE_FORZATAMENTE'
   elif name=='EUROBET_FEED_NOTO':
    try:
     payload=resp.json(); items=payload.get('raccolteFrequenti') if isinstance(payload,dict) else None
     if not isinstance(items,list): row['indicazione']='SCHEMA_NON_RICONOSCIUTO'
     else:
      for item in items:
       d=validate(item)
       if d: candidates[(name,d['timestamp_ms'],d['concorso'])]=dict(fonte=name,**d)
      row['indicazione']=f'ARRAY_VALIDI_{sum(k[0]==name for k in candidates)}_DA_VERIFICARE'
    except (ValueError,TypeError): row['indicazione']='RISPOSTA_NON_JSON'
   else:
    row['indicazione']='PAGINA_ACCESSIBILE_MA_ORDINE_NON_DIMOSTRATO'
  except requests.RequestException as exc:
   row['indicazione']='ERRORE_RETE_'+type(exc).__name__
  statuses.append(row)
  print(f"{name}: HTTP {row['http']} | {row['indicazione']}",flush=True)
  time.sleep(0.6)
 with (out/'fonti_v171.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=['fonte','host','http','content_type','bytes','indicazione']);writer.writeheader();writer.writerows(statuses)
 with (out/'sequenze_candidate_v171.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.writer(f);writer.writerow(COLUMNS)
  for d in sorted(candidates.values(),key=lambda r:r['timestamp_ms']): writer.writerow([d[x] for x in COLUMNS[:7]]+d['nums'])
 summary={'ora_utc':datetime.now(timezone.utc).isoformat(),'fonti_esaminate':len(statuses),'sequenze_candidate_non_convalidate':len(candidates),'ordine_mylotteries_convalidato':False,'nessuna_modifica_al_bot':True,'stati_http':{r['fonte']:r['http'] for r in statuses}}
 (out/'riepilogo_v171.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',default='risultati_v171');p.add_argument('--timeout',type=int,default=15);a=p.parse_args();run(Path(a.output),a.timeout)
