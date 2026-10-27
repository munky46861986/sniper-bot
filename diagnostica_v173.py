#!/usr/bin/env python3
"""V173 — browser read-only reconnaissance of publicly accessible lottery webpages.
No login, anti-bot evasion, direct app interception, betting, or polling APIs.
An array of twenty integers is NOT proof of the animation order.
"""
import argparse, asyncio, csv, hashlib, json, re, shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright

SOURCES = {
    'MYLOTTERIES_INFO': 'https://mylotteries.it/10elotto-estrazioni-e-archivio.html',
    'LOTTO_ITALIA_APP': 'https://www.lotto-italia.it/app',
    'LOTTO_ITALIA_ESTRAZIONI': 'https://www.lotto-italia.it/10-e-lotto/estratti.html',
    'TOTOFORTUNA': 'https://www.totofortuna.it/estrazioni-10elotto-ogni-5-minuti.php',
}
# Avoid retaining user identifiers, cookie data, tokens or full URLs with query strings.
TERMS = ('10elotto','10-e-lotto','10_e_lotto','estrazion','drawing','draw','results','numeri','numeri-estratti','oro','lottery')
MAX_BODY = 750_000
MAX_RESOURCES = 260
URL_HINT = re.compile(r'(?:https?://[^\s"\'<>\\]{10,180}|/[\w.\-/]{5,130}(?:\.json|/estrazion[\w/-]*|/results[\w/-]*))', re.I)

def extract_candidates(node, path='$', depth=0):
    if depth>9: return []
    results=[]
    if isinstance(node, list):
        if len(node)==20 and all(type(x) in (str,int) and re.fullmatch(r'\d{1,2}', str(x)) for x in node):
            nums=[int(x) for x in node]
            if len(set(nums))==20 and min(nums)>=1 and max(nums)<=90:
                results.append((path,nums))
        for i, v in enumerate(node[:30]):
            if isinstance(v,(dict,list)): results.extend(extract_candidates(v,f'{path}[{i}]',depth+1))
    elif isinstance(node,dict):
        for k,v in list(node.items())[:70]:
            if isinstance(v,(dict,list)):
                results.extend(extract_candidates(v, f'{path}.{str(k)[:45]}', depth+1))
    return results[:30]

def compact_url(url):
    p=urlsplit(url)
    return (p.hostname or '').lower(), p.path[:160]

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    resource_rows=[]; clues=[]; candidates=[]; visits=[]; events=[]; counts=Counter()
    seen=set()
    def log(s):
        line=datetime.now(timezone.utc).isoformat()+' | '+s
        print(line,flush=True);events.append(line)
    async with async_playwright() as play:
        browser_path=next((shutil.which(c) for c in ('google-chrome','google-chrome-stable','chromium','chromium-browser') if shutil.which(c)),None)
        opts={'headless':True,'args':['--no-sandbox']}
        if browser_path: opts['executable_path']=browser_path
        else: log('Browser di sistema non presente; richiesta installazione fallback')
        browser=await play.chromium.launch(**opts)
        log('Avviato '+(browser_path or 'Chromium Playwright'))
        for source, start in SOURCES.items():
            context=await browser.new_context(locale='it-IT',service_workers='block',accept_downloads=False)
            page=await context.new_page(); tasks=set(); per_source=Counter()
            async def inspect(response, source=source):
                try:
                    host,path=compact_url(response.url)
                    kind=response.request.resource_type
                    ctype=response.headers.get('content-type','').lower()
                    # Only public site resources, not advertisement or third-party analytics.
                    is_lottery_host=host.endswith(('lotto-italia.it','mylotteries.it','totofortuna.it'))
                    if not is_lottery_host: return
                    if len(resource_rows)>=MAX_RESOURCES: return
                    status=response.status
                    resource_rows.append(dict(source=source,host=host,path=path,status=status,type=kind,content_type=ctype[:65]))
                    per_source['responses']+=1;counts['responses']+=1
                    if status!=200 or not (kind in ('script','xhr','fetch') or 'json' in ctype): return
                    length=response.headers.get('content-length','')
                    if length.isdigit() and int(length)>MAX_BODY: return
                    body=await asyncio.wait_for(response.body(),timeout=7)
                    if len(body)>MAX_BODY: return
                    raw=body.decode('utf-8',errors='replace')
                    digest=hashlib.sha256(body).hexdigest()[:12]
                    if kind=='script' or 'javascript' in ctype:
                        matches=[]
                        for m in URL_HINT.findall(raw):
                            if any(x in m.lower() for x in TERMS) and '?' not in m and '#' not in m:
                                if m not in matches:matches.append(m)
                        for hint in matches[:15]:
                            key=(source,host,path,hint)
                            if key not in seen:
                                seen.add(key);clues.append(dict(source=source,host=host,script_path=path,sha256_short=digest,public_literal=hint[:180],status='UNVERIFIED_LITERAL'))
                        per_source['scripts_inspected']+=1
                    if 'json' in ctype or (kind in ('xhr','fetch') and raw.lstrip().startswith(('{','['))):
                        try: data=json.loads(raw)
                        except (ValueError,TypeError):return
                        per_source['json_inspected']+=1
                        for p,nums in extract_candidates(data):
                            candidates.append(dict(source=source,host=host,path=path,json_path=p,sorted_ascending=nums==sorted(nums),numbers=' '.join(map(str,nums)),validation='NOT_VALIDATED'))
                except Exception as exc:
                    per_source['inspect_errors']+=1
            def on_response(resp):
                task=asyncio.create_task(inspect(resp));tasks.add(task);task.add_done_callback(tasks.discard)
            page.on('response',on_response)
            try:
                res=await page.goto(start,timeout=24000,wait_until='domcontentloaded')
                visits.append(dict(source=source,page_url=start,status=res.status if res else '',final_host=compact_url(page.url)[0],final_path=compact_url(page.url)[1],error=''))
                log(f'{source}: status {res.status if res else "none"} final host {compact_url(page.url)[0]}')
                await page.wait_for_timeout(args.observe_seconds*1000)
            except Exception as e:
                visits.append(dict(source=source,page_url=start,status='',final_host='',final_path='',error=type(e).__name__))
                log(f'{source}: {type(e).__name__}')
            if tasks: await asyncio.wait(tasks,timeout=10)
            log(f'{source}: inspected {dict(per_source)}')
            await context.close()
        await browser.close()
    def csv_out(file,headers,rows):
        with (out/file).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=headers,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    csv_out('pagine_v173.csv',['source','page_url','status','final_host','final_path','error'],visits)
    csv_out('risorse_v173.csv',['source','host','path','status','type','content_type'],resource_rows)
    csv_out('indizi_js_v173.csv',['source','host','script_path','sha256_short','public_literal','status'],clues)
    csv_out('sequenze_candidate_v173.csv',['source','host','path','json_path','sorted_ascending','numbers','validation'],candidates)
    summary={'generated_utc':datetime.now(timezone.utc).isoformat(),'sites_tested':len(visits),'resources':len(resource_rows),'javascript_public_literals':len(clues),'candidate_arrays_unverified':len(candidates),'my_lotteries_animation_order_verified':False,'bot_modified':False,'notes':['V173 is limited to browser-accessible public web pages. It does not intercept the native app.','An observed 20-number list, even unsorted, is NOT evidence of animation sequence.','Source may contain dynamic data not loaded without user interactions; absence is not proof of impossibility.']}
    (out/'riepilogo_v173.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'eventi_v173.txt').write_text('\n'.join(events)+'\n',encoding='utf-8')
    log('Summary '+json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='risultati_v173')
    parser.add_argument('--observe-seconds',type=int,default=8)
    args=parser.parse_args();args.observe_seconds=max(3,min(30,args.observe_seconds))
    asyncio.run(main(args))
