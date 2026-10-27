#!/usr/bin/env python3
"""V172: osservazione passiva di risposte JSON pubbliche tramite Playwright.
NON autentica, NON aggira blocchi, NON interagisce con estrazioni/giocate.
Un vettore di 20 interi e' solo un candidato NON convalidato (non ordine animato).
"""
import argparse
import asyncio
import csv
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright

SOURCES = {
    'UFFICIALE': 'https://www.lotto-italia.it/10-e-lotto/estratti',
    'TOTOFORTUNA': 'https://www.totofortuna.it/estrazioni-10elotto-ogni-5-minuti.php',
    'EUROBET': 'https://www.eurobet.it/it/lotterie/10elotto',
}
KEYWORDS = ('10elotto','10-e-lotto','10_e_lotto','estraz','lotto','raccolte','draw','numeri','results')
LIMIT_BYTES = 700_000
MAX_RECORDS = 300


def normalize_20(values):
    if not isinstance(values, list) or len(values) != 20:
        return None
    if any(isinstance(x, bool) or not isinstance(x, (int,str)) or not re.fullmatch(r'\d{1,2}', str(x)) for x in values):
        return None
    nums = [int(x) for x in values]
    if len(set(nums)) != 20 or any(not 1 <= n <= 90 for n in nums):
        return None
    return nums


def find_candidates(data, path='$', depth=0, limit=35):
    if depth > 12 or limit <= 0:
        return []
    found = []
    if isinstance(data, dict):
        for k,v in list(data.items())[:65]:
            if not isinstance(k,str):
                continue
            child = f'{path}.{k[:48]}'
            nums = normalize_20(v)
            if nums:
                found.append((child,nums))
            elif isinstance(v,(dict,list)):
                found.extend(find_candidates(v, child, depth+1, limit-len(found)))
            if len(found)>=limit: break
    elif isinstance(data,list):
        for i,v in enumerate(data[:65]):
            if isinstance(v,(dict,list)):
                found.extend(find_candidates(v, f'{path}[{i}]', depth+1, limit-len(found)))
            if len(found)>=limit: break
    return found[:limit]

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    events=[]; inventory=[]; candidates=[]; counts=Counter(); seen=set(); pending=set()
    def log(message):
        msg=f'{datetime.now(timezone.utc).isoformat()} | {message}'
        print(msg,flush=True);events.append(msg)

    async with async_playwright() as p:
        # Use the Chrome/Chromium executable already on GitHub runners if present.
        # Fallback to the Playwright-managed Chromium installed by the workflow.
        system_browser = next((shutil.which(cmd) for cmd in
            ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser')
            if shutil.which(cmd)), None)
        launch_options = {'headless': True, 'args': ['--no-sandbox']}
        if system_browser:
            launch_options['executable_path'] = system_browser
            log(f'Browser sistema trovato: {system_browser}')
        else:
            log('Browser di sistema non trovato: uso Chromium Playwright')
        browser=await p.chromium.launch(**launch_options)
        for name,url in SOURCES.items():
            context=await browser.new_context(locale='it-IT', service_workers='block')
            page=await context.new_page()
            counts['pages_attempted']+=1
            async def handle(response, source=name):
                try:
                    parsed=urlsplit(response.url)
                    host=parsed.hostname or ''
                    path=parsed.path[:180]
                    ctype=response.headers.get('content-type','').lower()
                    # Avoid collecting cross-site advertising/tracking requests.
                    if not any(k in (host+path).lower() for k in KEYWORDS):
                        return
                    status=response.status
                    json_like=('json' in ctype or path.lower().endswith('.json'))
                    if len(inventory)<MAX_RECORDS:
                        inventory.append(dict(fonte=source, host=host, path=path, http=status, content_type=ctype[:80], json_possibile=json_like))
                    counts['relevant_responses']+=1
                    if status != 200 or not json_like:
                        return
                    length=response.headers.get('content-length','')
                    if length.isdigit() and int(length)>LIMIT_BYTES:
                        counts['too_large']+=1;return
                    try:
                        body=await asyncio.wait_for(response.body(),timeout=6)
                        if len(body)>LIMIT_BYTES:
                            counts['too_large']+=1;return
                        payload=json.loads(body)
                    except (Exception,) as e:
                        counts['json_unreadable']+=1
                        return
                    counts['json_read']+=1
                    for jsonpath,nums in find_candidates(payload):
                        sig=(source,host,path,jsonpath,tuple(nums))
                        if sig in seen:continue
                        seen.add(sig)
                        candidates.append(dict(fonte=source,host=host,path=path,json_path=jsonpath,
                          ordine_crescente=nums==sorted(nums),quinto_feed=nums[4],quinto_crescente=sorted(nums)[4],numeri=nums))
                        counts['candidates']+=1
                except Exception as e:
                    counts['handler_errors']+=1
                    log(f'{source}: errore risposta {type(e).__name__}')
            def on_response(resp):
                task=asyncio.create_task(handle(resp))
                pending.add(task)
                task.add_done_callback(pending.discard)
            page.on('response',on_response)
            try:
                response=await page.goto(url,wait_until='domcontentloaded',timeout=25000)
                status=response.status if response else 'nessuna_risposta'
                log(f'{name}: apertura status={status}')
                # Passive observation only: no clicks, refresh loops or scroll scraping.
                await page.wait_for_timeout(args.observe_seconds*1000)
            except Exception as e:
                log(f'{name}: navigazione {type(e).__name__} {str(e)[:120]}')
            await page.close()
            if pending:
                await asyncio.wait(pending,timeout=9)
            await context.close()
        await browser.close()

    with (out/'richieste_v172.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['fonte','host','path','http','content_type','json_possibile']);w.writeheader();w.writerows(inventory)
    with (out/'sequenze_candidate_v172.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['fonte','host','path','json_path','ordine_crescente','quinto_feed','quinto_crescente']+[f'p{i:02d}' for i in range(1,21)])
        for c in candidates:w.writerow([c[k] for k in ('fonte','host','path','json_path','ordine_crescente','quinto_feed','quinto_crescente')]+c['numeri'])
    (out/'eventi_v172.txt').write_text('\n'.join(events)+'\n',encoding='utf-8')
    summary={'ora_utc':datetime.now(timezone.utc).isoformat(),'contatori':dict(counts),'fonti':list(SOURCES),
      'candidate_20_numeri_non_convalidate':len(candidates),'ordine_animazione_mylotteries_convalidato':False,
      'nessuna_modifica_al_bot':True,
      'nota':'Il 20-element array, anche non crescente, NON prova la sequenza animata. Confronto esterno necessario.'}
    (out/'riepilogo_v172.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    log(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='risultati_v172');ap.add_argument('--observe-seconds',type=int,default=18)
    args=ap.parse_args();args.observe_seconds=max(3,min(60,args.observe_seconds));asyncio.run(main(args))
