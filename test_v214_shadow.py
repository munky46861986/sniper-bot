"""V214 deterministic offline checks; no Telegram and no real wagering."""
from types import SimpleNamespace
from v214_coverage_shadow import (v214_process,v214_report,v214_ensure,
                                  choose_pairs,theoretical_any,V214_SIZES)

def newtracker():
    return SimpleNamespace(data={'lab_strutture':{'history':[]}},dirty=False)

def draw(i,nums,day='2026-11-03'):
    return dict(day=day,draw_id=i,key=f'{day}#{i:03d}',nums=sorted(nums))

def main():
    x=choose_pairs([tuple(range(1,21))]*80)
    assert x[:3]==[(1,20),(2,19),(3,18)] and len(x)==15
    assert len(set(n for pair in x for n in pair))==30
    vals=[theoretical_any(s) for s in V214_SIZES]
    assert vals==sorted(vals) and .21<vals[1]<.23 and .53<vals[3]<.55
    tr=newtracker()
    for i in range(1,100):
        row=draw(i,range(1,21))
        hist=tr.data['lab_strutture']['history'];hist.append(row)
        ans=v214_process(tr,row)
        assert len(ans['signals'])<=1
        assert not v214_process(tr,row)['signals']
    st=v214_ensure(tr)
    assert st['processed']==99 and st['warmup']==80
    for s in V214_SIZES:
        d=st['totals'][str(s)]
        assert d['signals']>=10
        assert d['h1_cycles_hit']<=d['h1_checked']<=d['signals']
        assert d['h4_cycles_hit']<=d['h4_checked']<=d['signals']
    assert 'SOLO SHADOW' in v214_report(tr)
    assert 'Ultime coppie' in v214_report(tr,recent=True)

    tr2=newtracker(); st2=v214_ensure(tr2)
    st2['active']={'a':dict(id='a',origin_key='2026-11-03#100',
        day='2026-11-03',profile='3',pairs=[[1,20],[2,19],[3,18]],
        step=0,first_hit=None,status='OPEN')}
    st2['totals']['3']['signals']=1
    day=draw(101,[1,20]+list(range(30,48)))
    tr2.data['lab_strutture']['history'].append(day)
    v214_process(tr2,day)
    c=st2['totals']['3']
    assert (c['h1_checked'],c['h1_cycles_hit'],c['h1_tickets_hit'],c['h1_cost'],c['h1_return'])==(1,1,1,3,14)
    assert (c['h4_checked'],c['h4_cycles_hit'],c['h4_cost'],c['h4_return'])==(1,1,3,14)
    assert not st2['active']
    st2['active']={'b':dict(id='b',origin_key='2026-11-03#101',
        day='2026-11-03',profile='5',pairs=[[1,20],[2,19],[3,18],[4,17],[5,16]],
        step=0,status='OPEN')}
    st2['totals']['5']['signals']=1
    v214_process(tr2,draw(104,range(1,21)),gap=True)
    c=st2['totals']['5']
    assert c['interrupted']==1 and c['h1_checked']==0 and not st2['active']

    tr3=newtracker();s3=v214_ensure(tr3)
    s3['active']={'x':dict(id='x',origin_key='2026-11-03#100',
        day='2026-11-03',profile='3',pairs=[[1,20],[2,19],[3,18]],
        step=0,status='OPEN')}
    s3['totals']['3']['signals']=1
    v214_process(tr3,draw(101,range(30,50)))
    v214_process(tr3,draw(102,range(30,50)))
    v214_process(tr3,draw(103,[1,20]+list(range(30,48))))
    cc=s3['totals']['3']
    assert cc['h1_checked']==1 and cc['h1_cycles_hit']==0
    assert cc['h4_checked']==1 and cc['h4_cycles_hit']==1
    assert cc['h4_cost']==9 and cc['h4_return']==14
    print('V214_TEST_OK -- 3/5/10/15 disjoint, H1/H4, gap, persistence, duplicates')

if __name__=='__main__': main()
