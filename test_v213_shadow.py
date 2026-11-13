"""Deterministic V213 offline tests, no Telegram, no wagering."""
from types import SimpleNamespace
from v213_shadow import v213_process, v213_ensure, v213_candidates, v213_report

def draw(i,nums):
    return dict(day='2026-11-03',draw_id=i,key=f'2026-11-03#{i:03d}',nums=sorted(nums))

def run():
    import random,json
    rng=random.Random(20261113)
    tr=SimpleNamespace(data={'lab_strutture':{'history':[]}},dirty=False)
    for i in range(1,240):
        r=draw(i,rng.sample(range(1,91),20))
        tr.data['lab_strutture']['history'].append(r)
        tr.data['lab_strutture']['history']=tr.data['lab_strutture']['history'][-240:]
        result=v213_process(tr,r)
        assert len(result['signals'])<=1
        assert not v213_process(tr,r)['signals']
    st=v213_ensure(tr)
    assert st['processed']==239 and st['gap_count']==0
    assert st['totals']['h1_hits']<=st['totals']['h1_checked']<=st['totals']['signals']
    assert st['totals']['h4_hits']<=st['totals']['h4_closed']<=st['totals']['signals']
    assert 'SOLO SHADOW' in v213_report(tr)
    assert json.loads(json.dumps(tr.data))['v213_shadow']['totals']==st['totals']

    tr2=SimpleNamespace(data={'lab_strutture':{'history':[]}},dirty=False)
    st2=v213_ensure(tr2)
    st2['active']={'x':dict(id='x',origin_key='2026-11-03#100',
        day='2026-11-03',method='B',pair=[23,55],step=0,h1=None,h4=None,status='OPEN')}
    st2['totals']['signals']=1
    r=draw(101,[23,55]+list(range(1,19)))
    tr2.data['lab_strutture']['history'].append(r)
    v213_process(tr2,r)
    assert st2['totals']['h1_hits']==1 and st2['totals']['h4_hits']==1
    assert st2['totals']['h1_return']==14.0 and st2['totals']['h4_cost']==1.0
    assert not st2['active']
    st2['active']={'y':dict(id='y',origin_key='2026-11-03#101',
        day='2026-11-03',method='A',pair=[1,30],step=0,h1=None,h4=None,status='OPEN')}
    n=st2['totals']['h1_checked']
    v213_process(tr2,draw(104,range(1,21)),gap=True)
    assert st2['totals']['interrupted']==1 and st2['totals']['h1_checked']==n
    assert not st2['active']
    print('V213_SMOKE_OK: one pair per draw, H1/H4, gap, idempotence, persistence')

if __name__=='__main__': run()
