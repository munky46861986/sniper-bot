#!/usr/bin/env python3
"""Read-only V121 positional backtest, H1 vs fixed nine-draw horizon.
Uses official frozen V121 model and the repository's past-only history.
No requests, logins, bets, telegram commands or state writes.
"""
import csv,json,math,os,sys
from pathlib import Path
from collections import Counter
OUT=Path("v121_positional_results");OUT.mkdir(exist_ok=True)
import sniper as bot

STATE=Path("10elotto_engine_only_state.json")
MODEL=Path("V121_MODELLO_NONLINEARE_2025.txt")
if not STATE.is_file() or not MODEL.is_file():raise SystemExit("State or frozen model missing")
state=json.loads(STATE.read_text(encoding="utf8"))
multi=state.get("multichannel_bd12_ed12_o2f12_v1") or {}
rows=multi.get("history") or []
rows=sorted(rows,key=lambda r:bot.order_key(str(r.get("key",""))) or (-1,-1))
print("START",json.dumps({"history":len(rows),"first":rows[0].get("key") if rows else None,
                         "last":rows[-1].get("key") if rows else None,
                         "live_v121_total":(state.get(bot.V121_KEY) or {}).get("tests")}),flush=True)
if len(rows)<310:raise SystemExit("Insufficient read-only history for nine draws")
POSITION=[("inizio",slice(0,7)),("centro",slice(7,14)),("fine",slice(14,20))]
NUMERIC=[("bassi",lambda n:n<=30),("medi",lambda n:31<=n<=60),("alti",lambda n:n>=61)]
def blank():return dict(candidates=0,h1_hits=0,nine_occurrences=0,nine_seen_once=0,seven_win_hits=0,
                        seven_win_candidates=0)
stats={"posizione":{name:blank() for name,_ in POSITION},
       "fascia_valore":{name:blank() for name,_ in NUMERIC}}
cases=[];bad=Counter();first_seven=Counter()
for oi in range(287,len(rows)-9):
    past=rows[:oi+1];future=rows[oi+1:oi+10]
    if not all(bot.V52LiveTracker._consecutive(a,b)
               for a,b in zip(rows[oi-2:oi+9],rows[oi-1:oi+10])):
        bad["gaps_or_missing"]+=1;continue
    try:
        forecast=bot.v121_predict(past)
    except Exception as ex:
        bad["predict_"+type(ex).__name__]+=1
        if sum(bad.values())<=3:print("ERROR",type(ex).__name__,str(ex)[:140],flush=True)
        continue
    if len(forecast)!=20 or len(set(forecast))!=20:
        bad["bad_forecast"]+=1;continue
    observed=[set(int(x) for x in row.get("nums",[])) for row in future]
    if any(len(x)!=20 or min(x)<1 or max(x)>90 for x in observed):
        bad["bad_actual"]+=1;continue
    h1=sum(n in observed[0] for n in forecast)
    first=next((j+1 for j,draw in enumerate(observed) if len(set(forecast)&draw)>=7),None)
    first_seven[str(first or "none")]+=1
    was_seven=h1>=7
    n_seen=set().union(*observed)
    one=dict(origin=rows[oi]["key"],target=rows[oi+1]["key"],predicted=" ".join(f"{n:02d}" for n in forecast),
             h1=h1,first_7plus_in_nine=first or "",seven_in_h1=int(was_seven))
    for dimension in stats:
        if dimension=="posizione":
            groups=[(name,forecast[sl]) for name,sl in POSITION]
        else:
            groups=[(name,[n for n in forecast if filt(n)]) for name,filt in NUMERIC]
        for name,numbers in groups:
            st=stats[dimension][name];k=len(numbers)
            total=sum(n in actual for actual in observed for n in numbers)
            hits=sum(n in observed[0] for n in numbers)
            once=sum(n in n_seen for n in numbers)
            st["candidates"]+=k;st["h1_hits"]+=hits
            st["nine_occurrences"]+=total;st["nine_seen_once"]+=once
            if was_seven:
                st["seven_win_hits"]+=hits;st["seven_win_candidates"]+=k
            one[dimension+"_"+name+"_h1"]=hits
            one[dimension+"_"+name+"_n"]=k
            one[dimension+"_"+name+"_nine_occurrences"]=total
    cases.append(one)
    if len(cases)%150==0:print("PROGRESS",len(cases),flush=True)
if not cases:raise SystemExit("No validated causal nine-draw windows")
outstats={}
for dimension,groups in stats.items():
    outstats[dimension]={}
    for name,st in groups.items():
        c=st["candidates"]
        outstats[dimension][name]={**st,"h1_rate":st["h1_hits"]/c if c else None,
                                  "nine_per_draw_rate":st["nine_occurrences"]/(c*9) if c else None,
                                  "nine_at_least_once_rate":st["nine_seen_once"]/c if c else None,
                                  "h1_seven_rate":st["seven_win_hits"]/st["seven_win_candidates"] if st["seven_win_candidates"] else None}
summary=dict(model="V121 LGBM frozen 2025",source="read-only repository 900 draw history",
             note="Reconstructed model forecasts are NOT the original 1398 live H1 records",
             history=len(rows),start=rows[0]["key"],end=rows[-1]["key"],
             valid_windows=len(cases),skipped=dict(bad),h1_seven_count=sum(int(c["seven_in_h1"]) for c in cases),
             nine_any_seven=sum(c["first_7plus_in_nine"]!="" for c in cases),
             first_seven_step=dict(first_seven),
             statistics=outstats)
(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
with (OUT/"cases.csv").open("w",newline="",encoding="utf8") as f:
    w=csv.DictWriter(f,fieldnames=list(cases[0]));w.writeheader();w.writerows(cases)
def fmt_rate(v):
    return "-" if v is None else f"{100*v:.2f}%"
md=["# V121 — Studio posizioni e fasce numeriche, orizzonte H1 e 9 estrazioni","",
    f"Modello congelato 2025; storico letto senza modifiche: {summary['history']} concorsi, da {summary['start']} a {summary['end']}.",
    f"Finestre causali complete di 9 estrazioni: **{len(cases)}**; escluse: {dict(bad)}.",
    "Questi sono backtest RICOSTRUITI sullo storico presente, non gli stessi 1.398 test live:","non confondere statistiche e generalizzabilità.",
    f"Risultati 7+ immediati H1: **{summary['h1_seven_count']}/{len(cases)}**.",
    f"Almeno un 7+ nei nove concorsi per la STESSA ventina: **{summary['nine_any_seven']}/{len(cases)}**.",
    "",
    "Le fasce per POSIZIONE si riferiscono alla lista V121 ordinata crescente: 1-7 / 8-14 / 15-20.",
    "Le fasce per VALORE numerico sono 01-30 / 31-60 / 61-90.",
    "I tassi sono normalizzati per quantità di numeri previsti in ciascuna fascia.",
    ""]
for dimension in ("posizione","fascia_valore"):
    md+=["## "+dimension,"","| Gruppo | Candidati | HIT H1 / candidato | Presenze nei nove / concorso | Comparsi ≥1 volta in nove | HIT H1 nei concorsi 7+ / candidato |",
         "|---|---:|---:|---:|---:|---:|"]
    for name,st in outstats[dimension].items():
        md.append(f"| {name} | {st['candidates']} | {fmt_rate(st['h1_rate'])} | {fmt_rate(st['nine_per_draw_rate'])} | {fmt_rate(st['nine_at_least_once_rate'])} | {fmt_rate(st['h1_seven_rate'])} |")
    md.append("")
md+=["## Limiti e interpretazione","",
     "- La probabilità teorica per un singolo numero in un'estrazione 20/90 è 22.22%. Nei nove concorsi il dato 'almeno una presenza' tende a essere alto per TUTTE le fasce, senza vantaggio predittivo.",
     "- Le finestre da nove concorsi si sovrappongono e non sono osservazioni statisticamente indipendenti.",
     "- Filtrare soltanto i concorsi con 7+ crea una selezione a posteriori: va distinta dall'analisi predittiva preventiva.",
     "- Le differenze piccole non dimostrano una legge sfruttabile; nessuna giocata automatica o modifica del modello.",
     "- Per replicare esattamente gli storici 1.398 LIVE H1 servono previsioni ed esiti per ogni concorso, che il tracker V121 attualmente non salva.",
     ""]
(OUT/"report.md").write_text("\n".join(md),encoding="utf8")
print("SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
