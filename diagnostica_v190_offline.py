#!/usr/bin/env python3
"""V190: verifica statica locale dell'APK My Lotteries; sola lettura.
Uso: python diagnostica_v190_offline.py /percorso/MyLotteries.apk
Non installa/esegue l'app, non interroga servizi di gioco.
"""
import csv,hashlib,json,re,sys,zipfile
from pathlib import Path
TARGETS={
'748.d52aa2da.js':{
 'assegnazione_array':r'(?:this\.)?numberToExtract\s*=(?!=)',
 'uso_array':r'(?:this\.)?numberToExtract\s*\.shift\s*\(',
 'input_originale':r'numeriDaEstrarre',
 'riordinamento':r'\.sort\s*\(|\.reverse\s*\(|shuffle\s*\(',
 'inizializzazione':r'\binit\s*\('},
'6065.a703ff3b.js':{
 'input_originale':r'numeriDaEstrarre',
 'evento_risposta':r'SERVICE-MODULE-getCurrentExtraction',
 'stato_estrazione':r'currentExtration',
 'riordinamento':r'\.sort\s*\(|\.reverse\s*\(|shuffle\s*\('},
'main.79046245.js':{
 'servizio_corrente':r'getCurrentExtraction',
 'definizione_servizio':r'RACCOLTE_FREQUENTI|ESTRAZIONEFREQUENTE'}}
def clean(s):
 s=re.sub(r'(?i)(bearer\s+[A-Za-z0-9._-]+|(?:token|password|secret|authorization|api[_-]?key)\s*[:=]\s*["\x27]?\S{12,})','[REDACTED]',s)
 return re.sub(r'\s+',' ',s)
def main(apk):
 p=Path(apk)
 if not p.is_file():raise SystemExit('ERRORE: APK non trovato: '+str(p))
 out=Path('v190_risultati');out.mkdir(exist_ok=True)
 result={'version':'190','apk_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'feed_live_identificato':False,'ordine_originale_verificato':False,'note':'Le occorrenze statiche non provano un feed pubblico o l’ordine fisico.'}
 contexts=[]
 with zipfile.ZipFile(p) as z:
  names=z.namelist()
  for target,patterns in TARGETS.items():
   matches=[n for n in names if n.endswith('/'+target)]
   if len(matches)!=1:
    result[target]={'presente':False,'corrispondenze_per_nome':len(matches)};continue
   src=z.read(matches[0]).decode('utf-8','replace');counts={}
   for label,pat in patterns.items():
    hits=list(re.finditer(pat,src,re.I));counts[label]=len(hits)
    for m in hits[:40]:
     contexts.append({'file':target,'tipo':label,'offset':m.start(),'contesto':clean(src[max(0,m.start()-750):min(len(src),m.end()+1100)])[:1900]})
   result[target]={'presente':True,'bytes':len(src),'occorrenze':counts}
 with (out/'contesti_v190.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['file','tipo','offset','contesto']);w.writeheader();w.writerows(contexts)
 (out/'riepilogo_v190.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
 if len(sys.argv)!=2:raise SystemExit('Uso: python diagnostica_v190_offline.py MyLotteries.apk')
 main(sys.argv[1])
