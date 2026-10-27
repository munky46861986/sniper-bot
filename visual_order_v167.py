"""V169: acquisizione ordine API 10eLotto e due backtest SHADOW.

Isolato dai predittori V114/V121, non effettua giocate e non ha token.
ATTENZIONE: l'ordine API non è ancora stato validato contro l'animazione My Lotteries.
Il feed deriva dal servizio di pagina Eurobet; può negare le richieste dirette.
V169 prova una sessione HTTP e una diagnostica limitata quando si verifica HTTP 500.
"""
from __future__ import annotations

import csv
import io
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

ROME = ZoneInfo('Europe/Rome')
API_URL = 'https://showcase.giocodellotto.it/del/serviziFE/jsonrest/10elotto/raccolteFrequentiV2.json'
SITE_URL = 'https://www.eurobet.it/it/lotterie/10elotto'
STATE_KEY = 'v167_visual_api_shadow'
MAX_RECORDS = 3000
AMBO_PRIZE = 14.0   # premio nominale riferito alla simulazione, senza Oro/Extra
# V169: i GET browser normalmente NON inviano un Origin cross-site artificiale.
# Prima della richiesta API, se necessario, inizializziamo una sessione HTTP.
# Non imitiamo un login e non inviamo credenziali né richieste di gioco.
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.6',
    'Cache-Control': 'no-cache',
}
SHOWCASE_ORIGIN = 'https://showcase.giocodellotto.it'
SHOWCASE_BOOTSTRAP = SHOWCASE_ORIGIN + '/del/serviziFE/jsonrest/10elotto/get10eLottoHH.json'

# Mantiene eventuali cookie di sola navigazione tra i vari cicli dello stesso runner.
_HTTP_SESSION = None
_RETRY_NOT_BEFORE = 0.0
_CACHED_API_ERROR = ''


def _session():
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = requests.Session()
        _HTTP_SESSION.headers.update(HEADERS)
    return _HTTP_SESSION


def _get_response(sess, url, timeout, referer):
    return sess.get(url, headers={'Referer': referer}, timeout=timeout, allow_redirects=True)


def _parse_result_response(response):
    try:
        payload = response.json()
    except (ValueError, TypeError) as exc:
        raise RuntimeError('API HTTP 200 senza JSON valido') from exc
    entries = payload.get('raccolteFrequenti') if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError('JSON API privo della lista raccolteFrequenti')
    return [r for x in entries if (r := normalize_entry(x)) is not None]


def _int(v):
    if isinstance(v, bool):
        raise ValueError('Boolean al posto di intero')
    return int(v)


def normalize_entry(entry):
    """Escludere payload parziali e falsi DOM; nessun valore calcolato inventato."""
    if not isinstance(entry, dict):
        return None
    nums = entry.get('numeri')
    if not isinstance(nums, list) or len(nums) != 20:
        return None
    try:
        nums = [_int(n) for n in nums]
        if len(set(nums)) != 20 or any(not 1 <= n <= 90 for n in nums):
            return None
        n = _int(entry['progressivoGiornaliero'])
        if not 1 <= n <= 288:
            return None
        anchor_ms = _int(entry['dataRaccolta'])
        stamp_ms = _int(entry['timestampProssimaEstrazione'])
        day = datetime.fromtimestamp(anchor_ms / 1000, ROME).date().isoformat()
        dt = datetime.fromtimestamp(stamp_ms / 1000, ROME)
        # Per il concorso 288 possono esistere transizioni a mezzanotte.
        delta_days = (dt.date() - datetime.fromisoformat(day).date()).days
        if delta_days < 0 or delta_days > 1:
            return None
        status = str(entry.get('statoRaccolta') or '').upper()
        if status not in ('ESTRATTA', 'CALCOLATA'):
            return None
        oro = entry.get('numeroSpecialeEstratto')
        oro2 = entry.get('doppioOroEstratto')
        if oro is not None and (not 1 <= _int(oro) <= 90 or _int(oro) not in nums):
            return None
        if oro2 is not None and (not 1 <= _int(oro2) <= 90 or _int(oro2) not in nums):
            return None
        return {
            'day': day, 'draw': n, 'ts_ms': stamp_ms, 'time': dt.strftime('%H:%M'),
            'nums': nums, 'five_api': nums[4], 'five_sorted': sorted(nums)[4],
            'oro': _int(oro) if oro is not None else None,
            'oro2': _int(oro2) if oro2 is not None else None,
            'status': status,
            'source': 'EUROBET_10ELOTTO_RACCOLTEFREQUENTIV2',
        }
    except (ValueError, TypeError, KeyError, OverflowError, OSError):
        return None


def fetch_recent_draws(timeout=16):
    """V169. Prova GET read-only e inizializzazione sessione se l'API risponde 500.

    L'HTTP 500 non dimostra che manchino cookie: può essere un problema di
    backend, metodo, rete o di limitazioni dell'hosting. Non aggira blocchi.
    Retry al massimo ogni V169_API_BACKOFF_SECONDS quando fallisce.
    Nessuna eccezione di questa funzione può arrestare il bot principale,
    perché l'invocazione è isolata nel task v167_poll_loop di sniper.py.
    """
    global _RETRY_NOT_BEFORE, _CACHED_API_ERROR
    now=time.monotonic()
    if now < _RETRY_NOT_BEFORE:
        raise RuntimeError((_CACHED_API_ERROR or 'Sorgente API non disponibile')+
                           ' | prossimo tentativo tra '+str(int(_RETRY_NOT_BEFORE-now)+1)+'s')
    sess=_session()
    sec=max(4.0,min(12.0,float(timeout)))
    statuses=[]
    attempts=(
        ('GET diretto', SITE_URL),
        ('GET dopo bootstrap Eurobet', SHOWCASE_ORIGIN+'/'),
        ('GET dopo bootstrap showcase', SITE_URL),
    )
    for idx,(label,referer) in enumerate(attempts):
        if idx==1:
            # GET di navigazione: solo cookies pubblici, non login.
            try:
                landing=sess.get(SITE_URL,timeout=sec,allow_redirects=True)
                statuses.append('landing='+str(landing.status_code))
            except requests.RequestException as exc:
                statuses.append('landing='+type(exc).__name__)
        if idx==2:
            try:
                boot=_get_response(sess,SHOWCASE_BOOTSTRAP,sec,SHOWCASE_ORIGIN+'/')
                statuses.append('bootstrap='+str(boot.status_code))
            except requests.RequestException as exc:
                statuses.append('bootstrap='+type(exc).__name__)
        try:
            response=_get_response(sess,API_URL,sec,referer)
        except requests.RequestException as exc:
            statuses.append(label+'='+type(exc).__name__)
            continue
        statuses.append(label+'='+str(response.status_code))
        if response.status_code==200:
            try:
                results=_parse_result_response(response)
            except RuntimeError as exc:
                statuses.append('JSON='+str(exc)[:70])
                continue
            _RETRY_NOT_BEFORE=0.0
            _CACHED_API_ERROR=''
            return results  # [] è normale quando l'estrazione è in corso.
        # Se il server applica un divieto esplicito, evitiamo altri tentativi.
        if response.status_code in (401,403,429):
            break
    detail='; '.join(statuses)[-420:]
    error='Sorgente ordine API non disponibile: '+detail
    _CACHED_API_ERROR=error
    try:
        backoff=int(os.getenv('V169_API_BACKOFF_SECONDS','300'))
    except (ValueError,TypeError):
        backoff=300
    _RETRY_NOT_BEFORE=time.monotonic()+max(120,min(3600,backoff))
    raise RuntimeError(error)


def _valid_row(r):
    if not isinstance(r, dict): return False
    try:
        nums=r['nums']
        return (isinstance(nums,list) and len(nums)==20 and len(set(nums))==20 and
                all(isinstance(x,int) and 1<=x<=90 for x in nums) and
                isinstance(r['day'],str) and 1<=int(r['draw'])<=288 and
                isinstance(r['ts_ms'],int) and int(r['ts_ms'])>0 and
                r['five_api']==nums[4] and r['five_sorted']==sorted(nums)[4])
    except (TypeError,KeyError,ValueError): return False


def merge_visual_states(a,b):
    """Unione conservativa per Git/HARD LOCK, mai sostituisce una sequenza discordante."""
    left = a if isinstance(a,dict) else {}
    right = b if isinstance(b,dict) else {}
    stored={}
    discrepancies=set()
    for src in (left,right):
        for row in src.get('records',[]):
            if not _valid_row(row): continue
            key=(row['day'],int(row['draw']))
            if key in stored and stored[key]['nums'] != row['nums']:
                discrepancies.add(f'{key[0]}#{key[1]}')
                continue
            if key not in stored or row.get('status')=='CALCOLATA':
                stored[key]=dict(row)
        for conflict in src.get('conflicts',[]):
            if isinstance(conflict,str):discrepancies.add(conflict)
    rows=sorted(stored.values(),key=lambda r:(r['day'],int(r['draw'])))[-MAX_RECORDS:]
    last_err=right.get('last_error') or left.get('last_error') or ''
    return {'records':rows,'conflicts':sorted(discrepancies)[-100:],
            'last_error':str(last_err)[:260],
            'last_success':max(str(left.get('last_success') or ''),str(right.get('last_success') or '')),
            'order_validated':False, # NON promuovere automaticamente alla provenienza certificata
            'schema':1}


class VisualOrderShadow:
    def __init__(self, data=None):
        self._data = merge_visual_states({},data)
        self.last_error = str(self._data.get('last_error') or '')

    def load(self,data):
        self._data=merge_visual_states(self._data,data)
        self.last_error=str(self._data.get('last_error') or '')

    def dump(self):
        return merge_visual_states({},self._data)

    @property
    def records(self):
        return self._data['records']

    def ingest(self,entries):
        before=len(self.records)
        self._data=merge_visual_states(self._data,{'records':entries})
        # Le discordie non devono diventare statistiche valide.
        self._data['last_success']=datetime.now(ROME).isoformat(timespec='seconds')
        self._data['last_error']=''
        self.last_error=''
        return max(0,len(self.records)-before)

    def error(self,what):
        self.last_error=f'{type(what).__name__}: {what}'[:250]
        self._data['last_error']=self.last_error

    def _timeline(self):
        byts={}
        conflicting=set(self._data.get('conflicts',[]))
        for r in self.records:
            key=f"{r['day']}#{r['draw']}"
            if key not in conflicting:
                byts[int(r['ts_ms'])] = r
        return byts

    def _outcomes(self):
        byts=self._timeline()
        # Per M1 si considerano due origini consecutive t-1,t e il target t+1.
        # Per M2 si usa solo la ventina t e la corrispondente t+3.
        results={'M1':[], 'M2':[]}
        for t, row in sorted(byts.items()):
            prev=byts.get(t-300000)
            nxt=byts.get(t+300000)
            after3=byts.get(t+900000)
            if prev and nxt:
                pair=tuple(sorted((prev['five_api'],row['five_api'])))
                if len(set(pair))==2:
                    hit=set(pair).issubset(nxt['nums'])
                    results['M1'].append((hit,pair,row,nxt))
            if after3:
                pair=tuple(sorted((row['five_api'],row['five_sorted'])))
                if len(set(pair))==2:
                    hit=set(pair).issubset(after3['nums'])
                    results['M2'].append((hit,pair,row,after3))
        return results

    def report(self):
        rows=sorted(self.records,key=lambda r:int(r['ts_ms']))
        latest=rows[-1] if rows else None
        lines=['🔬 V169 — ORDINE API, MODALITA\' SHADOW',
               '⚠️ Ordine NON ancora confrontato con My Lotteries',
               f'Estr. salvate: {len(rows)} | discordie: {len(self._data["conflicts"])}']
        if latest:
            lines.extend([f"Ultima: {latest['day']} #{latest['draw']} ore {latest['time']}",
                          '20 API: '+' '.join(f'{x:02d}' for x in latest['nums']),
                          f"Quinto API: {latest['five_api']} | quinto crescente: {latest['five_sorted']}"])
        if self.last_error: lines.append('⚠️ Ultimo errore: '+self.last_error[:160])
        else: lines.append('Ultimo recupero OK: '+str(self._data.get('last_success') or '-'))
        return '\n'.join(lines)

    def stats_report(self):
        r=self._outcomes()
        lines=['📊 V169 — CONFRONTO AMBI VIRTUALI',
               '⚠️ Ordine API NON validato; nessuna giocata automatica',
               'H1: prima estrazione dopo la seconda quinta.',
               'H3 = terzo concorso dopo il quinto API di origine.']
        for name,desc in (('M1','M1 ultime 2 quinte API → H1'),('M2','M2 quinta API + quinta crescente → H3')):
            vals=r[name]; count=len(vals);wins=sum(int(x[0]) for x in vals)
            lines.append(f'{desc}: {wins}/{count} HIT | saldo €{14*wins-count:+d} (1€/segnale)')
        # Segnali per il prossimo concorso temporale, solo se consecutivi.
        byts=self._timeline()
        if byts:
            t=max(byts); now=datetime.now(ROME)
            if abs(t/1000-now.timestamp()) < 18*60:
                last=byts[t]; prior=byts.get(t-300000); h3orig=byts.get(t-600000)
                lines.append(f"PROSSIMO dopo #{last['draw']}:")
                if prior and last['five_api']!=prior['five_api']:
                    lines.append(f"M1 H1: {prior['five_api']}-{last['five_api']}")
                else:lines.append('M1 H1: nessuno (dati mancanti/duplicati)')
                if h3orig and h3orig['five_api']!=h3orig['five_sorted']:
                    lines.append(f"M2 H3 da #{h3orig['draw']}: {h3orig['five_api']}-{h3orig['five_sorted']}")
                else:lines.append('M2 H3: nessuno (dati mancanti/identici)')
            else:lines.append('Previsioni attuali non mostrate: dati troppo vecchi.')
        return '\n'.join(lines)

    def export_csv(self):
        stream=io.StringIO();w=csv.writer(stream)
        w.writerow(['data','concorso','orario','stato','quinto_API','quinto_crescente', *[f'p{i:02d}' for i in range(1,21)]])
        for r in sorted(self.records,key=lambda x:int(x['ts_ms'])):
            w.writerow([r['day'],r['draw'],r['time'],r['status'],r['five_api'],r['five_sorted'],*r['nums']])
        return stream.getvalue()
