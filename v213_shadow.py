"""V213 experimental 10eLotto ABC challenger, SHADOW ONLY.
One virtual pair per draw, H1 and H4 independent ledgers. Frozen model trained
Jan-Apr 2025, cutoff selected May-Jun 2025. External 2026 check: 106/1908
H1 hits (5.56%), net -424 EUR at simulated 14x. NOT verified profitable.
No real bets, no automatic stakes, no modifications of ABC/V212 histories.
"""
from collections import Counter
from datetime import date
import math
from v212_shadow import V212_RULES, _consecutive

VERSION='V213_CHALLENGER_SHADOW_2026_11'
CUTOFF=0.06025597605949512
MEAN=(0.21954895032217833,0.13604240282685512,23.40443774683018,
26.918883807940137,50.32332155477032,77.24220536271045,
1.4427353980461441,3.2524423196840573,16.467054666389522,
20.67085844938682,4.758989815007275,20.593223861982956,
3.514446061109956,3.4918416129702763,11.404022032841405,
1.880222406983995,1.884535439617543,0.28294533361047597)
SCALE=(0.4139410691566332,0.3428335856650432,17.605133409208694,
12.616182941085137,18.905680918930727,26.893214082121922,
0.5813518606655651,1.1924909522160145,2.9648403240102064,
3.160528897674132,1.9068708535153727,18.65731753575494,
3.9646705742294333,3.9630629263120825,6.888561730986284,
0.8260375349528555,0.822586912226455,0.450430096461759)
COEF=(-0.09109565569841768,0.06778083417052767,
0.05354135846617108,-0.0036251157926966383,0.04743902666231494,
0.03164841914651538,-0.10120837054337622,-0.02553103561819465,
0.007091281546084267,0.01878647795837961,0.03754382175204814,
0.02499283472669652,0.0050161357338470115,-0.05850293306973793,
0.009951311220522958,0.021087399387873906,0.008472691404227737,
0.007636103047090628)
INTERCEPT=-2.9233415322625484

def _empty():
    return dict(signals=0,eligible=0,skipped=0,h1_checked=0,h1_hits=0,
                h1_cost=0.0,h1_return=0.0,h4_closed=0,h4_hits=0,
                h4_cost=0.0,h4_return=0.0,interrupted=0)

def v213_ensure(tracker):
    if not isinstance(tracker.data.get('v213_shadow'),dict):
        tracker.data['v213_shadow']=dict(schema=1,version=VERSION,last_key=None,
          processed=0,gap_count=0,warmup=0,totals=_empty(),days={},
          active={},finished=[],recent=[],latest=None)
        tracker.dirty=True
    return tracker.data['v213_shadow']

def _add(st,day,field,amount=1):
    for obj in (st['totals'],st['days'].setdefault(day,_empty())):
        obj[field]=obj.get(field,0)+amount

def _history(tracker,row):
    hist=(tracker.data.get('lab_strutture') or {}).get('history') or []
    recent=hist[-81:]
    if len(recent)!=81 or str(recent[-1].get('key'))!=str(row['key']):
        return []
    if any(not _consecutive(a,b) for a,b in zip(recent,recent[1:])):
        return []
    try:
        values=[tuple(sorted(int(n) for n in x['nums'])) for x in recent]
    except (TypeError,KeyError,ValueError):
        return []
    if any(len(x)!=20 or len(set(x))!=20 or x[0]<1 or x[-1]>90 for x in values):
        return []
    return values

def v213_candidates(window,day,draw_id):
    if len(window)!=81: return []
    previous,nums=window[:-1],window[-1]
    last80=window[-80:]
    freq={k:Counter(n for row in last80[-k:] for n in row) for k in (5,15,80)}
    sets=list(map(set,last80))
    prior_sets=list(map(set,previous))
    weekend=int(date.fromisoformat(str(day)).weekday()>=5)
    out=[]
    for code,(p,q,maximum) in V212_RULES.items():
        a,b=nums[p-1],nums[q-1]
        distance=b-a
        if distance>maximum: continue
        pair_occ=[i for i,s in enumerate(prior_sets) if a in s and b in s]
        pair_age=80-pair_occ[-1] if pair_occ else 80
        delay_a=next((i for i,s in enumerate(reversed(prior_sets)) if a in s),80)
        delay_b=next((i for i,s in enumerate(reversed(prior_sets)) if b in s),80)
        cooc=sum(a in s and b in s for s in sets)
        fa,fb=freq[80][a],freq[80][b]
        feat=(int(code=='A'),int(code=='C'),distance,a,b,a+b,
          min(freq[5][a],freq[5][b]),min(freq[15][a],freq[15][b]),
          min(fa,fb),max(fa,fb),cooc,pair_age,delay_a,delay_b,
          (int(draw_id)-1)//12,freq[5][a],freq[5][b],weekend)
        z=INTERCEPT+sum(w*(v-mean)/scale
                        for w,v,mean,scale in zip(COEF,feat,MEAN,SCALE))
        score=1/(1+math.exp(-max(-40,min(40,z))))
        out.append(dict(method=code,pair=[a,b],distance=distance,
                        score=round(score,9)))
    return sorted(out,key=lambda r:(-r['score'],r['method']))

def v213_process(tracker,row,gap=False):
    st=v213_ensure(tracker)
    key=str(row.get('key') or f"{row['day']}#{int(row['draw_id']):03d}")
    if st['last_key'] and key<=st['last_key']:
        return dict(signals=[],results=[],digest=False)
    st['last_key']=key; st['processed']+=1
    signals=[];results=[]
    if gap:
        st['gap_count']+=1
        for sid,sig in list(st['active'].items()):
            sig['status']='INTERRUPTED'
            _add(st,sig['day'],'interrupted')
            st['finished'].append(dict(sig))
            results.append(f"{sig['pair'][0]:02d}-{sig['pair'][1]:02d} INTERROTTO (gap)")
            del st['active'][sid]
    else:
        drawn=set(int(n) for n in row['nums'])
        for sid,sig in list(st['active'].items()):
            sig['step']+=1
            hit=all(n in drawn for n in sig['pair'])
            if sig['step']==1:
                sig['h1']=int(hit)
                _add(st,sig['day'],'h1_checked')
                _add(st,sig['day'],'h1_cost',1.0)
                if hit:
                    _add(st,sig['day'],'h1_hits')
                    _add(st,sig['day'],'h1_return',14.0)
            _add(st,sig['day'],'h4_cost',1.0)
            if hit or sig['step']==4:
                sig['status']='CLOSED';sig['h4']=int(hit)
                sig['first_hit']=sig['step'] if hit else None
                _add(st,sig['day'],'h4_closed')
                if hit:
                    _add(st,sig['day'],'h4_hits')
                    _add(st,sig['day'],'h4_return',14.0)
                st['finished'].append(dict(sig))
                results.append(f"{sig['pair'][0]:02d}-{sig['pair'][1]:02d} "+
                               (f"HIT H{sig['step']}" if hit else 'MISS H4'))
                del st['active'][sid]
    window=_history(tracker,dict(row,key=key))
    st['warmup']=len(window)
    if window:
        candidates=v213_candidates(window,row['day'],row['draw_id'])
        if candidates:
            day=str(row['day']);_add(st,day,'eligible')
            best=candidates[0]
            if best['score']>=CUTOFF:
                sig=dict(id=f'{key}:V213',origin_key=key,day=day,
                         method=best['method'],pair=best['pair'],
                         distance=best['distance'],score=best['score'],
                         step=0,h1=None,h4=None,first_hit=None,status='OPEN')
                st['active'][sig['id']]=sig
                st['latest']=dict(sig)
                _add(st,day,'signals')
                signals.append(f"{best['method']} {best['pair'][0]:02d}-{best['pair'][1]:02d} "
                               f"score={best['score']:.4f} | H1/H4 SHADOW")
            else: _add(st,day,'skipped')
    st['finished']=st['finished'][-2400:]
    st['recent']=(st['recent']+
       [dict(origin=key,type='result',message=x) for x in results]+
       [dict(origin=key,type='signal',message=x) for x in signals])[-60:]
    tracker.dirty=True
    return dict(signals=signals,results=results,digest=st['processed']%24==0)

def v213_report(tracker,day=None,recent=False):
    st=v213_ensure(tracker)
    c=st['days'].get(day,_empty()) if day else st['totals']
    pct=lambda a,b:f"{100*a/b:.2f}%" if b else 'n.d.'
    out=['V213 — SELETTORE AMBI SFIDANTE | SOLO SHADOW',
         'Modello congelato 2025; 1 ambo massimo per origine, nessuna puntata reale.',
         f"Periodo: {day or 'cumulativo'} | ultimo concorso: {st['last_key'] or '-'}",
         f"Segnali: {c['signals']} | idonei: {c['eligible']} | scartati: {c['skipped']}",
         f"H1: {c['h1_hits']}/{c['h1_checked']} ({pct(c['h1_hits'],c['h1_checked'])}) | "
         f"virtuale {c['h1_return']-c['h1_cost']:+.2f} EUR",
         f"H4: {c['h4_hits']}/{c['h4_closed']} ({pct(c['h4_hits'],c['h4_closed'])}) | "
         f"virtuale {c['h4_return']-c['h4_cost']:+.2f} EUR",
         f"Interrotti: {c['interrupted']} | attivi: {len(st['active'])} | gap: {st['gap_count']}",
         'Backtest 2026: H1 106/1908 (5.56%), saldo simulato -424 EUR. '
         'Nessun vantaggio profittevole dimostrato.']
    if recent:
        out+=['','Ultimi eventi:']
        out += [f"{x['origin']} {x['message']}" for x in st['recent'][-10:]]
    return '\n'.join(out)
