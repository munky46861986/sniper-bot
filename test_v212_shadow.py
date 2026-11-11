"""Deterministic offline smoke tests for V212; no Telegram or betting."""
from types import SimpleNamespace
from v212_shadow import v212_process, v212_ensure, v212_report, v212_candidates

def make(n,nums):
    return {'day':'2026-11-03','draw_id':n,'key':f'2026-11-03#{n:03d}','nums':sorted(nums)}

def main():
    tr=SimpleNamespace(data={'lab_strutture':{'history':[]}},dirty=False)
    for k in range(1,110):
        row=make(k,range(1,21))
        h=tr.data['lab_strutture']['history']
        h.append(row)
        h[:]=h[-240:]
        ans=v212_process(tr,row)
        assert ans['signals']==[] or len(ans['signals'])==1
        assert not v212_process(tr,row)['signals'], 'idempotency'
    st=v212_ensure(tr)
    assert st['processed']==109 and st['gap_count']==0
    assert st['totals']['h1_checked']<=st['totals']['signals']
    assert st['totals']['h4_closed']<=st['totals']['h1_checked']
    assert len(v212_candidates([tuple(range(1,21))]*80))>0
    assert 'SOLO SHADOW' in v212_report(tr)
    # Forced H1 success: one winning pair in the next draw.
    tr2=SimpleNamespace(data={'lab_strutture':{'history':[]}},dirty=False)
    st2=v212_ensure(tr2)
    st2['active']={'x':{'id':'x','origin_key':'2026-11-03#100','day':'2026-11-03','method':'A','pair':[23,55],'step':0,'h1':None,'h4':None,'first_hit':None,'status':'OPEN'}}
    st2['totals']['signals']=1
    row=make(101,[23,55]+list(range(1,19)))
    tr2.data['lab_strutture']['history']=[row]
    v212_process(tr2,row)
    assert st2['totals']['h1_hits']==1 and st2['totals']['h4_hits']==1
    assert st2['totals']['h1_return']==14 and st2['totals']['h4_cost']==1
    assert not st2['active']
    # Gap must interrupt, not record a MISS.
    st2['active']={'y':{'id':'y','origin_key':'2026-11-03#101','day':'2026-11-03','method':'B','pair':[23,55],'step':0,'status':'OPEN'}}
    before=st2['totals']['h1_checked']
    v212_process(tr2,make(104,range(1,21)),gap=True)
    assert st2['totals']['interrupted']==1 and st2['totals']['h1_checked']==before
    print('V212_SELFTEST_OK: forward only, dedup, H1/H4, gap')

if __name__=='__main__':
    main()
