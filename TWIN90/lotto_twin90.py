#!/usr/bin/env python3
"""LOTTO TWIN90 v1: statistical digital twin of 10eLotto 5-minute draws.

Not the operator's algorithm and NOT a reliable way to predict winning numbers.
Training: 2025. Independent evaluation: 2026.
Draw constraints: 20 Base from 1..90; distinct Oro1/Oro2 from Base;
15 Extra from Base complement (70 eligible), 1..90 unique in each set.

Dependencies: numpy; Python 3.10+.
Usage: see README_TWIN90.md.
"""
import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

N = 90
K = 20
E = 15
BASE_P = K/N
DECADES = [tuple([90] + list(range(1,10)))] + [tuple(range(x, x+10)) for x in range(10,90,10)]
FEATURE_NAMES = ("bias", "hot80", "hot288", "delay", "prev", "transition", "dec_prev", "oro_prev", "extra_prev", "slot")
# Candidate models are frozen BEFORE looking at the 2026 holdout.
CANDIDATES = {
    "UNIFORM": (0,0,0,0,0,0,0,0,0,0),
    "BAYES_GLOBAL": (0.7,0,0,0,0,0,0,0,0,0),
    "HOT80": (0.5,0.18,0,0,0,0,0,0,0,0),
    "COLD80": (0.5,-0.18,0,0,0,0,0,0,0,0),
    "HOT288": (0.5,0,0.18,0,0,0,0,0,0,0),
    "COLD288": (0.5,0,-0.18,0,0,0,0,0,0,0),
    "DELAY_LONG": (0.5,0,0,0.16,0,0,0,0,0,0),
    "DELAY_SHORT": (0.5,0,0,-0.16,0,0,0,0,0,0),
    "REPEAT": (0.5,0,0,0,0.14,0,0,0,0,0),
    "AVOID_REPEAT": (0.5,0,0,0,-0.14,0,0,0,0,0),
    "TRANSITION": (0.5,0,0,0,0,0.6,0,0,0,0),
    "DECADE": (0.5,0,0,0,0,0,0.10,0,0,0),
    "ORO_LAST": (0.5,0,0,0,0,0,0,0.16,0,0),
    "EXTRA_LAST": (0.5,0,0,0,0,0,0,0,0.12,0),
    "CLOCK": (0.5,0,0,0,0,0,0,0,0,0.6),
    "HYBRID": (0.5,0.06,0.06,0.06,0.06,0.2,0.04,0.06,0.06,0.2),
}


@dataclass
class Draws:
    day: np.ndarray
    draw: np.ndarray
    base: np.ndarray
    oro1: np.ndarray
    oro2: np.ndarray
    extra: np.ndarray
    extra_valid: np.ndarray
    bad: list


def parse_set(raw, expected):
    if raw is None or str(raw).strip() == "":
        return None
    try:
        vals = [int(v) for v in str(raw).strip().split(".")]
    except ValueError:
        return None
    if len(vals) != expected or len(set(vals)) != expected or min(vals) < 1 or max(vals) > 90:
        return None
    return vals


def load_csv(path):
    dates, draws, base, o1, o2, extra, ev, bad = [], [], [], [], [], [], [], []
    keys = set()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for i, rec in enumerate(csv.DictReader(fh), start=2):
            dt = rec.get("date", "")
            num = int(rec["draw"])
            if not 1 <= num <= 288: raise ValueError(f"{path}:{i} invalid draw number {num}")
            key = (dt, num)
            if key in keys: raise ValueError(f"{path}:{i} duplicate draw {key}")
            keys.add(key)
            b = parse_set(rec.get("base"), K)
            if b is None: raise ValueError(f"{path}:{i} invalid Base")
            g1, g2 = int(rec["oro1"]), int(rec["oro2"])
            if g1 == g2 or g1 not in b or g2 not in b:
                raise ValueError(f"{path}:{i} invalid Gold: ({g1},{g2})")
            ex = parse_set(rec.get("extra"), E)
            is_valid = ex is not None and not (set(ex) & set(b))
            if not is_valid:
                bad.append({"date": dt, "draw": num, "reason": "missing/invalid/overlap Extra"})
            dates.append(dt); draws.append(num)
            base.append([v-1 for v in b]); o1.append(g1-1); o2.append(g2-1)
            extra.append([v-1 for v in ex] if is_valid else [-1]*E)
            ev.append(is_valid)
    order = np.lexsort((np.asarray(draws), np.asarray(dates)))
    dates = np.asarray(dates)[order]
    draws = np.asarray(draws,dtype=np.int16)[order]
    bmat = np.zeros((len(order),N),dtype=np.uint8)
    emat = np.zeros_like(bmat)
    for r, idx in enumerate(order):
        bmat[r,np.asarray(base[idx],dtype=np.int16)] = 1
        if ev[idx]: emat[r,np.asarray(extra[idx],dtype=np.int16)] = 1
    return Draws(dates,draws,bmat,np.asarray(o1,dtype=np.int16)[order],
                 np.asarray(o2,dtype=np.int16)[order],emat,np.asarray(ev)[order],bad)


def fit(draws, cutoff=None):
    if cutoff is None: cutoff = len(draws.day)
    x = draws.base[:cutoff].astype(np.float64)
    bcount = x.sum(axis=0)
    # high-prior shrinkage: best default for a nominally unbiased RNG.
    base_prob = (bcount+2000*BASE_P)/(cutoff+2000)
    bias = np.log(base_prob/BASE_P)
    g1count = np.bincount(draws.oro1[:cutoff],minlength=N)
    g2count = np.bincount(draws.oro2[:cutoff],minlength=N)
    # Conditional on a number being among the 20 Base.
    oro1_weight = (g1count+300/20)/(bcount+300)
    oro2_weight = (g2count+300/20)/(bcount+300)
    mask = draws.extra_valid[:cutoff]
    eligible = mask.sum()-x[mask].sum(axis=0)
    extras = draws.extra[:cutoff][mask].sum(axis=0)
    extra_weight = (extras+500*(E/70))/(eligible+500)
    # train-only conditional next-number tendency, shrink each conditional by 5000.
    prior = x[:-1]; nxt = x[1:]
    trans_counts = prior.T @ nxt
    prev_n = prior.sum(axis=0)
    trans_p = (trans_counts + 5000*BASE_P)/(prev_n[:,None]+5000)
    trans = np.log(np.maximum(trans_p,1e-8)/BASE_P)
    # time-of-day pattern; slot indexes are *draw numbers*, never raw time strings
    buckets = np.minimum((draws.draw[:cutoff]-1)//48,5)
    slots = []
    for slot in range(6):
        rows = x[buckets==slot]
        slots.append(np.log((rows.sum(axis=0)+500*BASE_P)/(len(rows)+500)/BASE_P))
    return {"bias":bias,"oro1":oro1_weight,"oro2":oro2_weight,"extra":extra_weight,
            "trans":trans,"slot":np.stack(slots),"train_rows":cutoff,
            "trained_to":str(draws.day[cutoff-1])}


def build_features(draws, model, begins, ends):
    """Construct causal features: every row depends ONLY on earlier rows."""
    x = draws.base
    cum = np.vstack((np.zeros((1,N),dtype=np.int32),np.cumsum(x,axis=0,dtype=np.int32)))
    i = np.arange(begins,ends)
    w80 = (cum[i]-cum[np.maximum(i-80,0)])/np.maximum(1,np.minimum(i,80))[:,None]
    w288 = (cum[i]-cum[np.maximum(i-288,0)])/np.maximum(1,np.minimum(i,288))[:,None]
    scale80 = math.sqrt(BASE_P*(1-BASE_P)/80)
    scale288 = math.sqrt(BASE_P*(1-BASE_P)/288)
    recent = np.zeros((len(i),N),dtype=np.float32)
    last_seen = np.full(N,-1,dtype=np.int32)
    # scan prefix to avoid look-ahead in the delay feature
    for t in range(ends):
        if t >= begins:
            age = t-last_seen-1
            recent[t-begins] = np.minimum(age,80)
        last_seen[np.flatnonzero(x[t])] = t
    delay = (recent-3.5)/7.0
    lag = x[i-1].astype(np.float32)
    trans = lag@model["trans"] / K
    # traditional 90,1..9;10..19 etc decade order, same as user specified
    mapping = np.zeros(N,dtype=np.int16)
    for d,nums in enumerate(DECADES): mapping[np.asarray(nums)-1] = d
    dec_cnt = np.empty_like(lag)
    for j,t in enumerate(i):
        counts = np.bincount(mapping,weights=x[t-1],minlength=9)
        dec_cnt[j] = counts[mapping]
    oro = np.zeros_like(lag)
    oro[np.arange(len(i)),draws.oro1[i-1]] = 1
    oro[np.arange(len(i)),draws.oro2[i-1]] = 1
    ex = draws.extra[i-1].astype(np.float32)
    ex[~draws.extra_valid[i-1]] = 0
    slot = model["slot"][np.minimum((draws.draw[i]-1)//48,5)]
    out = np.stack((np.broadcast_to(model["bias"],lag.shape),
                    (w80-BASE_P)/scale80,(w288-BASE_P)/scale288,delay,
                    lag,trans,(dec_cnt-(K/9))/1.4,oro,ex,slot),axis=2).astype(np.float32)
    return out


def probabilities(features, coeff):
    logits = np.tensordot(features,np.asarray(coeff,dtype=np.float32),axes=([-1],[0]))
    logits -= logits.max(axis=1,keepdims=True)
    weight = np.exp(logits)
    p = K * weight/weight.sum(axis=1,keepdims=True)
    return np.clip(p,1e-5,1-1e-5)


def score(x, p):
    p = np.clip(p,1e-8,1-1e-8)
    brier = float(np.mean((x-p)**2))
    logloss = float(np.mean(-(x*np.log(p)+(1-x)*np.log(1-p))))
    idx = np.argpartition(-p,K-1,axis=1)[:,:K]
    hits = float(x[np.arange(len(x))[:,None],idx].sum(axis=1).mean())
    best2 = np.argpartition(-p,1,axis=1)[:,:2]
    pair_hits = float(np.all(x[np.arange(len(x))[:,None],best2]==1,axis=1).mean())
    return {"draws":len(x),"brier":round(brier,9),"logloss":round(logloss,9),
            "top20_mean_hits":round(hits,5),"top2_ambo_H1_pct":round(100*pair_hits,5)}


def validate_candidates(train, val_begin, val_end):
    features = build_features(train, fit(train,val_begin),val_begin,val_end)
    x = train.base[val_begin:val_end]
    report={}
    for name,coeff in CANDIDATES.items():
        report[name]=score(x,probabilities(features,coeff))
    baseline=report["UNIFORM"]["logloss"]
    best=min(report,key=lambda k: report[k]["logloss"])
    # conservative: only select nonuniform when it materially beats baseline
    # on pre-2026 validation; otherwise physical RNG is the default.
    picked = best if baseline-report[best]["logloss"] > 0.00010 else "UNIFORM"
    return report,picked,best


def transition_from_recent(history, model):
    if len(history)==0: return np.zeros(N)
    return np.mean(model["trans"][np.asarray(history[-1],dtype=int)-1],axis=0)


def dynamic_score(history, model, day_draw, coeff, oro_last=None, extra_last=None):
    # simulate using only earlier simulated draws; historical data not replayed.
    score=np.asarray(model["bias"],dtype=float)*coeff[0]
    if not history:
        return score
    h=np.asarray(history[-288:],dtype=np.int16)-1
    last80 = h[-80:]
    last288 = h[-288:]
    freq80=np.bincount(last80.ravel(),minlength=N)/len(last80)
    freq288=np.bincount(last288.ravel(),minlength=N)/len(last288)
    score=score + coeff[1]*(freq80-BASE_P)/math.sqrt(BASE_P*(1-BASE_P)/80)
    score=score + coeff[2]*(freq288-BASE_P)/math.sqrt(BASE_P*(1-BASE_P)/288)
    age=np.full(N,80)
    for j,row in enumerate(history[-80:][::-1]):
        pos=np.asarray(row,dtype=np.int16)-1
        age[pos]=np.minimum(age[pos],j)
    score=score + coeff[3]*(age-3.5)/7
    lag=np.zeros(N);lag[h[-1]]=1
    score=score + coeff[4]*lag + coeff[5]*transition_from_recent(history,model)
    mapping=np.zeros(N,dtype=np.int16)
    for d,nums in enumerate(DECADES): mapping[np.asarray(nums)-1]=d
    cnt=np.bincount(mapping,weights=lag,minlength=9)
    score=score+coeff[6]*(cnt[mapping]-K/9)/1.4
    if oro_last:
        score[np.asarray(oro_last)-1]+=coeff[7]
    if extra_last:
        score[np.asarray(extra_last)-1]+=coeff[8]
    score=score+coeff[9]*model["slot"][min((day_draw-1)//48,5)]
    return score


def pick_weighted(rng, allowed, weights, k):
    w=np.maximum(np.asarray(weights,dtype=float)[allowed],1e-8)
    if not np.isfinite(w).all():raise ValueError("Invalid sampling weights")
    return rng.choice(allowed,size=k,replace=False,p=w/w.sum())


def generate(model, count, start, seed, coeff, warmup_history=None):
    rng=np.random.default_rng(seed)
    today=date.fromisoformat(start)
    history=[] if warmup_history is None else [list(v) for v in warmup_history[-288:]]
    oro_last=None; extra_last=None
    rows=[]
    for ix in range(count):
        draw=ix%288+1
        if ix and draw==1:today+=timedelta(days=1)
        logits=dynamic_score(history,model,draw,coeff,oro_last,extra_last)
        logits=logits-np.max(logits)
        weights=np.exp(np.clip(logits,-10,10))
        base_idx=pick_weighted(rng,np.arange(N),weights,K)
        base=sorted((base_idx+1).tolist())
        gold_idx=pick_weighted(rng,base_idx,model["oro1"],1)[0]
        remaining=base_idx[base_idx!=gold_idx]
        gold2_idx=pick_weighted(rng,remaining,model["oro2"],1)[0]
        complement=np.setdiff1d(np.arange(N),base_idx,assume_unique=True)
        extra_idx=pick_weighted(rng,complement,model["extra"],E)
        extra=sorted((extra_idx+1).tolist())
        oro_last=(int(gold_idx)+1,int(gold2_idx)+1)
        extra_last=extra
        history.append(base)
        if len(history)>288:history.pop(0)
        mins=(draw*5)%(24*60)
        tm=f'{mins//60:02d}.{mins%60:02d}'
        rows.append({"date":today.isoformat(),"draw":draw,"time":tm,
                     "base":".".join(f'{n:02d}' for n in base),
                     "oro1":oro_last[0],"oro2":oro_last[1],
                     "extra":".".join(f'{n:02d}' for n in extra)})
    return rows


def save_rows(rows,path):
    with open(path,"w",newline="",encoding="utf-8") as fh:
        writer=csv.DictWriter(fh,fieldnames=["date","draw","time","base","oro1","oro2","extra"])
        writer.writeheader(); writer.writerows(rows)


def distribution_metrics(draws):
    x=draws.base
    cov=np.logical_and(x[1:],x[:-1]).sum(axis=1)
    even=x[:,1::2].sum(axis=1)
    decmap=np.zeros(N,dtype=np.int8)
    for d,nums in enumerate(DECADES):decmap[np.asarray(nums)-1]=d
    dec=np.column_stack([x[:,decmap==z].sum(axis=1) for z in range(9)])
    f=x.mean(axis=0)
    o1=np.bincount(draws.oro1,minlength=N)/len(x)
    o2=np.bincount(draws.oro2,minlength=N)/len(x)
    fm=draws.extra[draws.extra_valid].mean(axis=0)
    sums=x@np.arange(1,91)
    return {"base_frequency_mean":float(np.mean(f)),
            "base_frequency_std":float(np.std(f)),
            "base_frequency_range":float(np.max(f)-np.min(f)),
            "mean_overlap_next":float(np.mean(cov)),
            "overlap_next_std":float(np.std(cov)),
            "mean_even":float(np.mean(even)),
            "mean_sum20":float(np.mean(sums)),
            "mean_decade_count":float(np.mean(dec)),
            "decade_5plus_rate":float((dec>=5).mean()),
            "oro1_frequency_std":float(np.std(o1)),
            "oro2_frequency_std":float(np.std(o2)),
            "extra_frequency_mean_valid_only":float(np.mean(fm)),
            "extra_frequency_std_valid_only":float(np.std(fm))}


def evaluate_similarity(real, sim):
    # similarity of a declared set of distributional summaries, not exact draw overlap.
    a=distribution_metrics(real);b=distribution_metrics(sim)
    # dimensionless relative abs errors; caution: small means can distort
    rows=[]
    for key in a:
        reference=a[key]
        rel=abs(b[key]-reference)/max(abs(reference),1e-8)
        rows.append({"metric":key,"real":round(reference,7),"synthetic":round(b[key],7),
                     "relative_error_pct":round(100*rel,3),
                     "similarity_pct":round(100*max(0,1-rel),3)})
    return {"metrics":rows,"mean_relative_similarity_pct":round(float(np.mean([r["similarity_pct"] for r in rows])),3),
            "warning":"Statistic similarity is NOT percentage of actual numbers predicted."}


def save_model(path,model,chosen,validation,metrics):
    obj={"name":"LOTTO_TWIN90_V1","chosen":chosen,"coeff":CANDIDATES[chosen],
         "trained_to":model["trained_to"],"train_rows":model["train_rows"],
         "validation":validation,"out_of_sample":metrics,
         "weights":{k:model[k].tolist() for k in ("bias","oro1","oro2","extra","trans","slot")}}
    with open(path,"w",encoding="utf-8") as fh:json.dump(obj,fh,indent=2,ensure_ascii=False)


def load_model(path):
    with open(path,encoding="utf-8") as fh:d=json.load(fh)
    m={k:np.asarray(v,dtype=np.float64) for k,v in d["weights"].items()}
    return m,d


def cli_train(args):
    base=load_csv(args.archive_2025)
    test=load_csv(args.archive_2026)
    cut=int(np.searchsorted(base.day,"2025-07-01",side="left"))
    if not (1000<cut<len(base.day)-1000):raise ValueError("2025 training/validation split invalid")
    validation,chosen,best=validate_candidates(base,cut,len(base.day))
    model=fit(base)
    # Testing uses 2026 draw history only and train-2025 fixed parameters.
    test_start=min(288,len(test.day)//10)
    feats=build_features(test,model,test_start,len(test.day))
    holdout_x=test.base[test_start:]
    holdout={}
    for key in ("UNIFORM",chosen,"HYBRID","TRANSITION","HOT80","COLD80"):
        if key not in holdout:
            holdout[key]=score(holdout_x,probabilities(feats,CANDIDATES[key]))
    validation_result={"training_count":cut,"validation_count":len(base.day)-cut,
                       "selected_model":chosen,"validation_winner_unpenalized":best,
                       "validation_scores":validation}
    save_model(args.model,model,chosen,validation_result,holdout)
    # 95% benchmark is based on explicitly listed distribution metrics only.
    simrows=generate(model,args.sample_size,"2026-11-18",args.seed,CANDIDATES[chosen])
    save_rows(simrows,args.simulations)
    synthetic=load_csv(args.simulations)
    ix=min(len(test.day),len(synthetic.day))
    similarity=evaluate_similarity(Draws(test.day[-ix:],test.draw[-ix:],test.base[-ix:],
                      test.oro1[-ix:],test.oro2[-ix:],test.extra[-ix:],test.extra_valid[-ix:],test.bad),synthetic)
    similarity["sample_size"] = ix
    similarity["holdout_2026"] =holdout
    similarity["selection_2025"] = {"selected":chosen,"best_unpenalized":best,
                                    "validation_loss_uniform":validation["UNIFORM"]["logloss"],
                                    "validation_loss_best":validation[best]["logloss"]}
    similarity["quality"]={"archive_2025_rows":len(base.day),"archive_2026_rows":len(test.day),
                           "2025_bad_extra":base.bad,"2026_bad_extra":test.bad}
    with open(args.report,"w",encoding="utf-8") as fh:json.dump(similarity,fh,indent=2,ensure_ascii=False)
    print(json.dumps({"selected":chosen,"holdout":holdout,"similarity":similarity["mean_relative_similarity_pct"],
                      "training":len(base.day),"testing":len(test.day),"bad_extra":(len(base.bad),len(test.bad))},indent=2))


def cli_refit(args):
    """Post-validation fit using both years for future-only simulation."""
    _, previous=load_model(args.model)
    a=load_csv(args.archive_2025)
    b=load_csv(args.archive_2026)
    joint=Draws(np.concatenate((a.day,b.day)),np.concatenate((a.draw,b.draw)),
                np.concatenate((a.base,b.base),axis=0),
                np.concatenate((a.oro1,b.oro1)),np.concatenate((a.oro2,b.oro2)),
                np.concatenate((a.extra,b.extra),axis=0),
                np.concatenate((a.extra_valid,b.extra_valid)),a.bad+b.bad)
    fitted=fit(joint)
    save_model(args.output,fitted,previous["chosen"],previous["validation"],previous["out_of_sample"])
    print(json.dumps({"two_year_model":args.output,"trained_on":fitted["train_rows"],
                      "last_training_day":fitted["trained_to"],
                      "prediction_model_selected_before_2026_test":previous["chosen"]},indent=2))


def cli_simulate(args):
    model,desc=load_model(args.model)
    chosen=desc["chosen"] if not args.mode else args.mode
    rows=generate(model,args.count,args.start,args.seed,CANDIDATES[chosen])
    save_rows(rows,args.output)
    print(f"Synthetic draws {len(rows)} saved to {args.output} | mode={chosen}")


def cli_predict(args):
    """Return an honest, explicitly experimental ranking for the next draw."""
    model,desc=load_model(args.model)
    data=load_csv(args.history)
    chosen=desc["chosen"]
    if chosen=="UNIFORM":
        print(json.dumps({"after":f'{data.day[-1]}#{int(data.draw[-1]):03d}',
                          "model":chosen,"all_90_numbers_equal":True,
                          "inclusion_probability_each":round(BASE_P,8),
                          "top20_ranked":None,
                          "note":"Il modello non identifica un vantaggio predittivo; una classifica sarebbe arbitraria."},indent=2))
        return
    history=[(np.flatnonzero(row)+1).tolist() for row in data.base[-288:]]
    day_draw=int(data.draw[-1])+1
    if day_draw>288:day_draw=1
    oro_last=(int(data.oro1[-1]+1),int(data.oro2[-1]+1))
    extra_last=(np.flatnonzero(data.extra[-1])+1).tolist() if data.extra_valid[-1] else []
    logits=dynamic_score(history,model,day_draw,CANDIDATES[chosen],oro_last,extra_last)
    order=(np.argsort(-logits)+1).tolist()
    print(json.dumps({"after":f'{data.day[-1]}#{int(data.draw[-1]):03d}',
                      "next_draw_number":day_draw,"top20_ranked":order[:20],
                      "top10":order[:10],"model":chosen,
                      "warning":"Ranking sperimentale, senza vantaggio fuori campione dimostrato"},indent=2))


def main():
    p=argparse.ArgumentParser(description="10eLotto statistical twin, NOT its secret algorithm")
    sub=p.add_subparsers(dest="command",required=True)
    tr=sub.add_parser("train"); tr.add_argument("--archive-2025",required=True);tr.add_argument("--archive-2026",required=True)
    tr.add_argument("--model",default="twin90_model.json");tr.add_argument("--report",default="twin90_evaluation.json")
    tr.add_argument("--simulations",default="twin90_synthetic.csv");tr.add_argument("--sample-size",type=int,default=10000)
    tr.add_argument("--seed",type=int,default=20261117);tr.set_defaults(func=cli_train)
    rf=sub.add_parser("refit");rf.add_argument("--model",required=True)
    rf.add_argument("--archive-2025",required=True);rf.add_argument("--archive-2026",required=True)
    rf.add_argument("--output",default="twin90_model_2025_2026.json")
    rf.set_defaults(func=cli_refit)
    sim=sub.add_parser("simulate");sim.add_argument("--model",required=True);sim.add_argument("--output",default="twin90_generated.csv")
    sim.add_argument("--count",type=int,default=288);sim.add_argument("--start",default="2026-11-18");sim.add_argument("--seed",type=int,default=20261117)
    sim.add_argument("--mode",choices=tuple(CANDIDATES),default=None);sim.set_defaults(func=cli_simulate)
    pred=sub.add_parser("predict");pred.add_argument("--model",required=True);pred.add_argument("--history",required=True)
    pred.set_defaults(func=cli_predict)
    args=p.parse_args();args.func(args)


if __name__=="__main__":main()