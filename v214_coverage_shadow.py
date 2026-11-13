"""V214 diversified AMBO coverage. SHADOW ONLY -- NO REAL BETS.

Goal: raise P(at least one winning pair in a portfolio), NOT P(winning one ticket).
Profiles: 3,5,10,15 number-disjoint pairs. A 15-pair profile uses 20 numbers
from the latest BASE draw + 10 non-drawn numbers ranked by past frequency.
Pairs are frozen at origin; H1 and H4 ledgers are independent. H4 stops the
ENTIRE portfolio on first draw that contains at least one winning pair.
One simulated EUR per pair/draw, hypothetical payout EUR14 per winning pair.
No progressive wagering and no side effects outside v214_shadow state.
"""
from collections import Counter
from math import comb

V214_SIZES=(3,5,10,15)
V214_RETURN=14.0
V214_VERSION='V214_DIVERSIFIED_SHADOW_2026_11'


def theoretical_any(size):
    """Exact P(any complete pair) for size disjoint pairs, 20 of 90."""
    no_hit=sum(comb(size,k)*2**k*comb(90-2*size,20-k)
               for k in range(size+1) if 0<=20-k<=90-2*size)
    return 1-no_hit/comb(90,20)


def choose_pairs(history):
    """Current and historical draws only. Nested profiles; no data leakage.

    Accepts >= 80 20-number BASE draws (chronological), newest last.
    Every selected number appears in at most one pair.
    """
    if len(history)<80:
        return []
    win=history[-80:]
    newest=sorted(int(n) for n in win[-1])
    if len(newest)!=20 or len(set(newest))!=20 or not 1<=newest[0]<=newest[-1]<=90:
        return []
    if any(len(row)!=20 or len(set(row))!=20 for row in win):
        return []
    f5=Counter(n for row in win[-5:] for n in row)
    f15=Counter(n for row in win[-15:] for n in row)
    f80=Counter(n for row in win for n in row)
    def score(n):
        return (f80[n], f15[n], f5[n], -n)
    ordered=sorted(newest,key=score,reverse=True)
    pairs=[]
    for i in range(10):
        pairs.append(tuple(sorted((ordered[i],ordered[19-i]))))
    extra=sorted(set(range(1,91))-set(newest),key=score,reverse=True)[:10]
    for i in range(5):
        pairs.append(tuple(sorted((extra[i],extra[9-i]))))
    assert len(set(n for pair in pairs for n in pair))==30
    return pairs


def _counts():
    return dict(signals=0,h1_checked=0,h1_cycles_hit=0,h1_tickets_hit=0,
        h1_cost=0.0,h1_return=0.0,h4_checked=0,h4_cycles_hit=0,
        h4_tickets_hit=0,h4_cost=0.0,h4_return=0.0,interrupted=0)


def v214_ensure(tracker):
    st=tracker.data.get('v214_shadow')
    if not isinstance(st,dict):
        st=dict(schema=1,version=V214_VERSION,last_key=None,processed=0,
          warmup=0,gap_count=0,totals={str(k):_counts() for k in V214_SIZES},
          days={},active={},finished=[],recent=[],latest=None)
        tracker.data['v214_shadow']=st
        tracker.dirty=True
    return st


def _add(st,size,day,name,amount=1):
    for dest in (st['totals'][size],st['days'].setdefault(day,{}).setdefault(size,_counts())):
        dest[name]+=amount


def _consecutive(a,b):
    try:
        if str(a['day'])==str(b['day']):
            return int(b['draw_id'])==int(a['draw_id'])+1
        return int(b['draw_id'])==1 and int(a['draw_id']) in (228,288) and str(a['day'])<str(b['day'])
    except (KeyError,ValueError,TypeError):
        return False


def _window(tracker,row):
    hist=(tracker.data.get('lab_strutture') or {}).get('history') or []
    last=hist[-80:]
    if len(last)!=80 or str(last[-1].get('key'))!=str(row['key']):
        return []
    if any(not _consecutive(a,b) for a,b in zip(last,last[1:])):
        return []
    return [tuple(int(v) for v in h['nums']) for h in last]


def v214_process(tracker,row,gap=False):
    st=v214_ensure(tracker)
    key=str(row.get('key') or f"{row['day']}#{int(row['draw_id']):03d}")
    if st['last_key'] and key<=st['last_key']:
        return dict(signals=[],results=[],digest=False)
    st['last_key']=key
    st['processed']+=1
    signals=[];results=[]
    if gap:
        st['gap_count']+=1
        for sid,sig in list(st['active'].items()):
            _add(st,sig['profile'],sig['day'],'interrupted')
            sig['status']='INTERRUPTED'
            st['finished'].append(dict(sig))
            del st['active'][sid]
    else:
        found=set(int(v) for v in row['nums'])
        for sid,sig in list(st['active'].items()):
            size=sig['profile'];day=sig['day'];sig['step']+=1
            hits=sum(a in found and b in found for a,b in sig['pairs'])
            if sig['step']==1:
                _add(st,size,day,'h1_checked')
                _add(st,size,day,'h1_cost',int(size))
                if hits:
                    _add(st,size,day,'h1_cycles_hit')
                    _add(st,size,day,'h1_tickets_hit',hits)
                    _add(st,size,day,'h1_return',V214_RETURN*hits)
            _add(st,size,day,'h4_cost',int(size))
            if hits or sig['step']==4:
                sig['status']='CLOSED';sig['first_hit']=sig['step'] if hits else None
                _add(st,size,day,'h4_checked')
                if hits:
                    _add(st,size,day,'h4_cycles_hit')
                    _add(st,size,day,'h4_tickets_hit',hits)
                    _add(st,size,day,'h4_return',V214_RETURN*hits)
                st['finished'].append(dict(sig));del st['active'][sid]
                results.append(f"{size} AMBI: "+(f"HIT almeno uno H{sig['step']}" if hits else 'MISS H4'))
    history=_window(tracker,dict(row,key=key))
    st['warmup']=len(history)
    if history:
        pairs=choose_pairs(history)
        if pairs:
            for size in V214_SIZES:
                id_=f"{key}:V214:{size}"
                sig=dict(id=id_,origin_key=key,day=str(row['day']),profile=str(size),
                    pairs=[list(p) for p in pairs[:size]],step=0,first_hit=None,status='OPEN')
                st['active'][id_]=sig
                _add(st,str(size),str(row['day']),'signals')
            st['latest']=dict(key=key,pairs=[list(p) for p in pairs])
            signals.append(f"Coperture {','.join(map(str,V214_SIZES))} ambi disgiunti | H1/H4 virtuali")
    st['finished']=st['finished'][-2400:]
    st['recent']=(st['recent'] +
        [dict(key=key,event='result',text=s) for s in results] +
        [dict(key=key,event='signal',text=s) for s in signals])[-50:]
    tracker.dirty=True
    return dict(signals=signals,results=results,digest=st['processed']%48==0)


def v214_report(tracker,day=None,recent=False):
    st=v214_ensure(tracker)
    pct=lambda a,b:f"{100*a/b:.2f}%" if b else 'n.d.'
    lines=['V214 — COPERTURA AMBI DIVERSIFICATA | SOLO SHADOW',
        'Piu coppie SENZA numeri condivisi; non aumenta la probabilita del singolo ambo.',
        f"Ultimo concorso: {st['last_key'] or '-'} | periodo: {day or 'totale'}",
        f"Concorso elaborati: {st['processed']} | gap: {st['gap_count']}"]
    for size in V214_SIZES:
        c=(st['days'].get(day,{}) if day else st['totals']).get(str(size),_counts())
        n=c['h1_checked'];n4=c['h4_checked']
        lines += [f"{size} ambi distinti: H1 almeno uno {c['h1_cycles_hit']}/{n} "
                   f"({pct(c['h1_cycles_hit'],n)}) | virtuale {c['h1_return']-c['h1_cost']:+.0f} EUR",
                  f"  H4 almeno uno {c['h4_cycles_hit']}/{n4} ({pct(c['h4_cycles_hit'],n4)}) "
                   f"| virtuale {c['h4_return']-c['h4_cost']:+.0f} EUR | "
                   f"riferimento teorico H1 {theoretical_any(size)*100:.2f}%"]
    if recent:
        lines+=['','Ultimi eventi:']+[f"{v['key']} {v['text']}" for v in st['recent'][-10:]]
        if st.get('latest'):
            lines+=['Ultime coppie (max 15): '+', '.join(f"{a:02d}-{b:02d}" for a,b in st['latest']['pairs'])]
    lines+=['I saldi usano €1 per coppia/colpo, ritorno ipotetico 14x.',
            'Nessuna puntata reale; nessuna progressione; rischio di perdita elevato.']
    return '\n'.join(lines)
