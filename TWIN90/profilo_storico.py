#!/usr/bin/env python3
"""Research diagnostics by 90 numbers and the nine user-specified decades."""
import argparse, csv, json
from pathlib import Path
import numpy as np
from lotto_twin90 import load_csv, DECADES, K, N


def age_last(x):
    i = np.flatnonzero(x)
    return len(x)-1-int(i[-1]) if len(i) else len(x)


def dec_label(n):
    return '90-09' if n == 90 or 1 <= n <= 9 else f'{n//10*10:02d}-{n//10*10+9:02d}'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--archive-2025',required=True)
    p.add_argument('--archive-2026',required=True)
    p.add_argument('--output',default='.')
    a=p.parse_args()
    out=Path(a.output);out.mkdir(exist_ok=True,parents=True)
    all_numbers=[];all_decades=[];reports={}
    for period, path in [('2025',a.archive_2025),('2026',a.archive_2026)]:
        d=load_csv(path); rows=len(d.day)
        valid_ex=d.extra[d.extra_valid]
        oro_counts1=np.bincount(d.oro1,minlength=N)
        oro_counts2=np.bincount(d.oro2,minlength=N)
        oro_comb=oro_counts1+oro_counts2
        ex_counts=valid_ex.sum(axis=0)
        for v in range(1,N+1):
            j=v-1;hist=d.base[:,j]; gold=(d.oro1==j)|(d.oro2==j)
            extra=d.extra[:,j]&d.extra_valid
            all_numbers.append({
                'period':period,'numero':v,'decina':dec_label(v),
                'base_presenze':int(hist.sum()),'base_freq_pct':round(float(hist.mean()*100),5),
                'base_ritardo_finale':age_last(hist),
                'base_ultime20':int(hist[-20:].sum()),
                'base_ultime80':int(hist[-80:].sum()),
                'base_ultime288':int(hist[-288:].sum()),
                'oro1_presenze':int(oro_counts1[j]),
                'oro2_presenze':int(oro_counts2[j]),
                'oro_complessivo':int(oro_comb[j]),
                'oro_ritardo_finale':age_last(gold),
                'extra_presenze':int(ex_counts[j]),
                'extra_ritardo_finale':age_last(extra),
                'extra_freq_su_concorsi_validi_pct':round(float(ex_counts[j]/len(valid_ex)*100),5)
            })
        decall=[]
        for nums in DECADES:
            numcols=np.asarray(nums,dtype=int)-1
            cnt=d.base[:,numcols].sum(axis=1)
            row={'period':period,'decina':dec_label(nums[0]),
                 'media_base_per_concorso':round(float(cnt.mean()),5),
                 'almeno5_eventi':int((cnt>=5).sum()),
                 'almeno5_pct':round(float((cnt>=5).mean()*100),5),
                 'almeno6_eventi':int((cnt>=6).sum()),
                 'almeno6_pct':round(float((cnt>=6).mean()*100),5),
                 'zero_eventi':int((cnt==0).sum()),
                 'zero_pct':round(float((cnt==0).mean()*100),5)}
            all_decades.append(row);decall.append(row)
        indexes=[t for t,x in enumerate(all_numbers) if x['period']==period]
        rr=[all_numbers[t] for t in indexes]
        reports[period]={
            'rows':rows,'start':str(d.day[0]),'end':str(d.day[-1]),
            'extra_not_usable':d.bad,
            'top10_base':[{k:el[k] for k in ('numero','base_presenze','base_freq_pct')} for el in sorted(rr,key=lambda t:-t['base_presenze'])[:10]],
            'top10_ritardatari_base_finali':[{k:el[k] for k in ('numero','base_ritardo_finale')} for el in sorted(rr,key=lambda t:-t['base_ritardo_finale'])[:10]],
            'top10_oro1':[{k:el[k] for k in ('numero','oro1_presenze')} for el in sorted(rr,key=lambda t:-t['oro1_presenze'])[:10]],
            'top10_oro2':[{k:el[k] for k in ('numero','oro2_presenze')} for el in sorted(rr,key=lambda t:-t['oro2_presenze'])[:10]],
            'top10_extra':[{k:el[k] for k in ('numero','extra_presenze')} for el in sorted(rr,key=lambda t:-t['extra_presenze'])[:10]],
        }
    for filename,records in [('statistiche_90_numeri.csv',all_numbers),('statistiche_9_decine.csv',all_decades)]:
        with (out/filename).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    with (out/'profilo_storico.json').open('w',encoding='utf-8') as f:json.dump(reports,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:{'rows':v['rows'],'top10_base':[z['numero'] for z in v['top10_base']],
                         'extra_issues':len(v['extra_not_usable'])} for k,v in reports.items()},indent=2))
if __name__=='__main__':main()