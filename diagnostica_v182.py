#!/usr/bin/env python3
"""V182: browser availability diagnostic, not an extraction of the Android app."""
import argparse, hashlib, json, os, pathlib, re, shutil, time
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen

def utc(): return datetime.now(timezone.utc).isoformat()
def sha(data): return hashlib.sha256(data).hexdigest()

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--url',default='https://mylotteries.it/10elotto-estrazioni-e-archivio.html')
 p.add_argument('--delay',type=int,default=65)
 p.add_argument('--output',default='v182_output')
 a=p.parse_args()
 host=urlparse(a.url)
 if host.scheme!='https' or host.hostname not in {'mylotteries.it','www.mylotteries.it','www.sisal.it','sisal.it','www.giocodellotto.it','giocodellotto.it'}:
  raise SystemExit('URL must be https and on the allowlist of public sites')
 out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True)
 report={'started_utc':utc(),'url':a.url,'purpose':'Test reachability and visual evolution of a PUBLIC WEBPAGE (not mobile app)', 'http':{},'browser':{}, 'live_sequence_verified':False,'app_access_verified':False}
 try:
  req=Request(a.url,headers={'User-Agent':'Mozilla/5.0 (compatible; V182ReadOnlyDiagnostic/1.0)'})
  with urlopen(req,timeout=25) as r:
   content=r.read(2000000)
   report['http']={'status':r.status,'final_url':r.url,'content_type':r.headers.get('Content-Type'),'sha256_first_2mb':sha(content),'bytes_sampled':len(content)}
 except Exception as e: report['http']={'error':str(e)}
 try:
  from playwright.sync_api import sync_playwright
  chrome=next((x for x in [os.getenv('CHROME_PATH'),'/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'] if x and os.path.isfile(x)),None)
  if not chrome: raise RuntimeError('No system Chromium/Chrome executable found')
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True,executable_path=chrome,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1280,'height':900},locale='it-IT')
   nav_error=None
   try: page.goto(a.url,wait_until='domcontentloaded',timeout=30000)
   except Exception as e: nav_error=str(e)
   frames=[]
   for i in range(2):
    if i: time.sleep(max(0,min(a.delay,120)))
    name=f'screenshot_{i}.png'; path=out/name
    page.screenshot(path=str(path),full_page=False,timeout=20000)
    text=page.locator('body').inner_text(timeout=10000)[:12000]
    (out/f'text_{i}.txt').write_text(text,encoding='utf-8')
    frames.append({'when':utc(),'url':page.url,'title':page.title(),'screenshot':name,'screenshot_sha256':sha(path.read_bytes()),'text_sha256':sha(text.encode()), 'visible_text_length':len(text)})
   report['browser']={'launched':True,'navigation_error':nav_error,'samples':frames,'screenshot_changed':frames[0]['screenshot_sha256'] != frames[1]['screenshot_sha256'],'text_changed':frames[0]['text_sha256']!=frames[1]['text_sha256']}
   browser.close()
 except Exception as e: report['browser']={'launched':False,'error':repr(e)}
 report['finished_utc']=utc()
 report['interpretation']='Changes in page screenshot/text do NOT establish that an app live draw feed is accessible, or provide 20 original-number positions.'
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
