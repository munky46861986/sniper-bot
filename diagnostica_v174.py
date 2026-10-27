#!/usr/bin/env python3
"""V174: inspect public metadata and documented app links; no APK download or protected API access."""
import argparse, csv, datetime, html.parser, json, re, time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path

TARGETS = [
 ('MYLOTTERIES_UFFICIALE','https://mylotteries.it/'),
 ('LOTTO_ITALIA_APP','https://www.lotto-italia.it/app'),
 ('LOTTO_ITALIA_10ELOTTO','https://www.lotto-italia.it/10-e-lotto/dove-giocare/app'),
 ('PLAY_STORE_INFO','https://play.google.com/store/apps/details?id=it.mylotteries.verificavincite&hl=it'),
]
KEYS=('apk','android','download','scarica','lotter','estraz','api','appstore','play.google')
class Links(html.parser.HTMLParser):
 def __init__(self):
  super().__init__(); self.links=[]; self.title=''; self.in_title=False
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='title':self.in_title=True
  if tag in ('a','script','link'):
   x=a.get('href') or a.get('src')
   if x:self.links.append((tag,x,a.get('type',''),a.get('rel','')))
 def handle_endtag(self,tag):
  if tag=='title':self.in_title=False
 def handle_data(self,txt):
  if self.in_title:self.title+=txt

def fetch(url,method='GET',limit=1_000_000):
 req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; public-reference-audit/1.0)'},method=method)
 try:
  with urlopen(req,timeout=18) as r:
   data=r.read(limit) if method=='GET' else b''
   return {'status':r.status,'final_url':r.url,'type':r.headers.get('Content-Type',''),'size_header':r.headers.get('Content-Length',''),'body':data.decode('utf-8','replace')}
 except HTTPError as e:return {'status':e.code,'final_url':e.url,'type':e.headers.get('Content-Type',''),'size_header':e.headers.get('Content-Length',''),'body':'','error':str(e)}
 except (URLError,TimeoutError, OSError) as e:return {'status':None,'final_url':url,'type':'','size_header':'','body':'','error':str(e)}

def write_csv(path, cols, rows):
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='risultati_v174');args=p.parse_args()
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 pages=[];links=[];metadata=[]
 for name,url in TARGETS:
  print('GET',name,url,flush=True)
  res=fetch(url);page={'site':name,'requested_url':url,'http_status':res['status'],'final_url':res['final_url'],'content_type':res['type'],'title':'','error':res.get('error','')}
  parser=Links()
  if 'html' in res['type'].lower() or '<html' in res['body'][:500].lower():
   parser.feed(res['body']);page['title']=parser.title.strip()[:150]
  pages.append(page)
  for tag,link,typ,rel in parser.links:
   absolute=urljoin(res['final_url'],link)
   if any(k in absolute.lower() for k in KEYS):
    links.append({'source':name,'element':tag,'url':absolute[:700],'type':typ,'rel':str(rel),'apk_reference':'.apk' in absolute.lower()})
  # Only HEAD public APK links, no downloading, credentials, or reverse engineering
  for item in [x for x in links if x['source']==name and x['apk_reference']][:5]:
   dest=item['url']
   # Only explicit https links from the official MyLotteries domain
   host=urlparse(dest).hostname or ''
   if name=='MYLOTTERIES_UFFICIALE' and dest.startswith('https://') and (host=='mylotteries.it' or host.endswith('.mylotteries.it')):
    info=fetch(dest,'HEAD')
    metadata.append({'referrer':name,'url':dest,'http_status':info['status'],'content_type':info['type'],'content_length':info['size_header'],'final_url':info['final_url'],'error':info.get('error','')})
  time.sleep(.4)
 write_csv(out/'pagine_v174.csv',['site','requested_url','http_status','final_url','content_type','title','error'],pages)
 write_csv(out/'riferimenti_app_v174.csv',['source','element','url','type','rel','apk_reference'],links)
 write_csv(out/'apk_head_v174.csv',['referrer','url','http_status','content_type','content_length','final_url','error'],metadata)
 summary={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pages_checked':len(pages),'public_links_matched':len(links),'apk_head_checked':len(metadata),'original_draw_order_found':False,'my_lotteries_animation_order_verified':False,'notes':['Only public webpages and link metadata inspected.','No APK binary is downloaded or reverse engineered.','The app network traffic cannot be inferred from its public landing page.','HTTP 200 on a security/challenge page is not evidence that the target page loaded.','No bot code or live functionality was modified.']}
 (out/'riepilogo_v174.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
