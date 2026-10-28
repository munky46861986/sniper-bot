#!/usr/bin/env python3
"""Verifica offline della V121 dinamica: nessun token, rete o giocata."""
import importlib.util
from datetime import datetime, timedelta

spec=importlib.util.spec_from_file_location("bot_study","sniper_V121_DINAMICO_H7_COMPLETO.py")
bot=importlib.util.module_from_spec(spec);spec.loader.exec_module(bot)
Z=bot.V121LiveShadow
b=Z()

def make_row(draw, nums=None):
    from datetime import datetime,timedelta
    dt=datetime(2026,10,28,0,0)+timedelta(minutes=5*draw)
    return dict(day="2026-10-28",key=f"2026-10-28#{draw:03d}",
                draw_id=draw,time=dt.strftime("%H:%M"),nums=nums or list(range(1,21)))
row=make_row(100)
b.initialize([row])
seen=[]
for i in range(1,11):
    # Ogni H1 aggiorna la propria ventina. Non viene mai riutilizzata una ventina vecchia.
    forecast=(list(range(1,21)) if i%3==1 else
              list(range(31,51)) if i%3==2 else list(range(61,81)))
    h=7 if i in (3,9) else 5
    actual=forecast[:h]+[n for n in range(1,91) if n not in forecast][:20-h]
    future=make_row(100+i,actual)
    b.pending=dict(origin_key=row["key"],target_key=future["key"],
                   base_numbers=list(forecast),v114_numbers=list(range(1,21)))
    outcome=b.observe(future,row)
    assert outcome and outcome["status"]=="VERIFICATO",(i,outcome)
    expected=(outcome["zone"]["kind"])
    if i<7:assert expected=="PRE_GATE",(i,outcome["zone"])
    if i in (7,8):assert expected=="CHECK",(i,outcome["zone"])
    if i==9:
        assert expected=="HIT7" and outcome["zone"]["h"]==9
        assert b.zone_successes==1 and b.zone_run["step"]==0
        assert outcome["zone"]["forecast"]==forecast
        assert sum(outcome["zone"]["values"].values())==7
        assert b.zone_numbers.get("65",{}).get("hits",0)>=1 # new forecast at H9
        assert b.zone_closed[-1]["h"]==9
    if i==10:
        assert expected=="PRE_GATE" and outcome["zone"]["h"]==1
    seen.append((i,forecast[0],expected))
    row=future
assert b.tests==10 and b.zone_checks==3 and b.zone_successes==1,(b.tests,b.zone_checks,b.zone_successes)
assert b.n7==2  # One seven was BEFORE gate; old H1 stats retained.
assert b.zone_values["ALTA_61_90"]["exposed"]==20 # H9 only
assert b.zone_values["ALTA_61_90"]["hits"]==7
assert b.zone_positions["PRIMI_7"]["exposed"]==21
assert b.zone_positions["CENTRO_7"]["exposed"]==21
assert b.zone_positions["ULTIMI_6"]["exposed"]==18
assert b.zone_values["MEDIA_31_60"]["hits"]==5 # H8
assert b.zone_values["BASSA_01_30"]["hits"]==5 # H7
assert "numeri" in b.report([]).lower() or "Numeri" in b.report([])
saved=b.dump()
restored=Z(saved)
assert restored.zone_checks==3 and restored.zone_successes==1
assert restored.zone_run["step"]==1
assert restored.zone_numbers==b.zone_numbers
print("PASS H7 dynamic forecasts, H9 seven-hit, zone learning, state persistence")
print("DYNAMIC PER DRAW:",seen)

# Gate H8 configurable, verify persistence across restarts and check H7 ignored.
import os
os.environ["V121_ZONE_START_H"]="8"
b2=Z();r=make_row(101)
b2.initialize([r])
for h in range(1,10):
    pred=list(range(1+h,21+h))
    nums=pred[:7]+[n for n in range(50,91) if n not in pred][:13]
    nextrow=make_row(101+h,nums)
    b2.pending=dict(origin_key=r["key"],target_key=nextrow["key"],
                    base_numbers=pred,v114_numbers=list(range(1,21)))
    result=b2.observe(nextrow,r)
    if h==7:assert result["zone"]["kind"]=="PRE_GATE"
    if h==8:assert result["zone"]["kind"]=="HIT7" and b2.zone_successes==1
    if h==9:assert result["zone"]["h"]==1
    r=nextrow
assert b2.zone_checks==1 and b2.zone_successes==1
print("PASS configurable H8 with fresh H1 each time")

# H1 gap must reset active count, not create an invented win.
os.environ["V121_ZONE_START_H"]="7"
b3=Z();r=make_row(101);b3.initialize([r])
for h in range(1,5):
    future=make_row(101+h)
    b3.pending=dict(origin_key=r["key"],target_key=future["key"],
                    base_numbers=list(range(1,21)),v114_numbers=list(range(1,21)))
    b3.observe(future,r);r=future
assert b3.zone_run["step"]==4
future=make_row(109)
b3.pending=dict(origin_key=r["key"],target_key=future["key"],
                base_numbers=list(range(1,21)),v114_numbers=list(range(1,21)))
x=b3.observe(future,r)
assert x["status"]=="NON_VERIFICABILE" and b3.zone_run["step"]==0 and b3.zone_aborted==1
print("PASS missing draw resets gate")

# H1 original counters and the new ranking survive the normal V121 merge.
p=bot._merge_v121_state(saved,saved)
assert p["tests"]==10 and p["zone_monitor"]["checks"]==3
print("ALL TESTS PASS")


# Verify the *real V121.arm()* calls the predictor again for every new draw.
# Replace the costly ML predictor only in this isolated synthetic test.
old_predict=bot.v121_predict
old_other=bot.V114GeneratorLive._forecast_base
try:
    forecast_calls=[]
    def artificial_prediction(history):
        draw_id=int(history[-1]["draw_id"])
        forecast_calls.append(draw_id)
        return list(range(draw_id%40+1, draw_id%40+21))
    bot.v121_predict=artificial_prediction
    bot.V114GeneratorLive._forecast_base=staticmethod(lambda numbers: list(range(1,21)))
    eng=Z()
    prev=make_row(80)
    eng.initialize([prev])
    first=eng.arm([prev],check_freshness=False)
    assert first and first["origin_key"]==prev["key"]
    actual=make_row(81)
    one=eng.observe(actual,prev)
    assert one["status"]=="VERIFICATO"
    second=eng.arm([prev,actual],check_freshness=False)
    assert second and second["origin_key"]==actual["key"]
    assert forecast_calls==[80,81],forecast_calls
    assert first["base_numbers"]!=second["base_numbers"],(first,second)
finally:
    bot.v121_predict=old_predict
    bot.V114GeneratorLive._forecast_base=old_other
print("PASS actual V121.arm recalculates using the immediately previous draw")


# If a draw arrives without an H1 forecast, the H7/H8 streak must be reset.
no_prediction=Z()
prior=make_row(120)
no_prediction.initialize([prior])
for d in range(121,125):
    curr=make_row(d)
    no_prediction.pending=dict(origin_key=prior["key"],target_key=curr["key"],
                               base_numbers=list(range(1,21)),
                               v114_numbers=list(range(1,21)))
    no_prediction.observe(curr,prior)
    prior=curr
assert no_prediction.zone_run["step"]==4
skip=make_row(125)
assert no_prediction.observe(skip,prior) is None
assert no_prediction.zone_run["step"]==0 and no_prediction.zone_aborted==1
print("PASS missing forecast resets the consecutive H counter")

# Old V121 snapshot with same H1 progress cannot overwrite newer learned-zone data.
old_snapshot=dict(saved)
old_snapshot.pop("zone_monitor",None)
merged=bot._merge_v121_state(old_snapshot,saved)
assert merged.get("zone_monitor",{}).get("checks")==3,merged.get("zone_monitor")
print("PASS V121 state merge preserves latest learned statistics")
