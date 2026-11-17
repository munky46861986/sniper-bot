#!/usr/bin/env python3
"""Invia risultati REALI TWIN90 su Telegram usando i secret di Superambo3.

Nessuna puntata: gli estratti sono confermati dalla fonte, i numeri TWIN90
sono esclusivamente simulazioni SHADOW. Anti-duplicati: la coda di notifiche
viene rimossa solo dopo la conferma HTTP dell'API Telegram.
"""
import argparse
import json
import os
from pathlib import Path

import requests
from datetime import datetime, timedelta
from twin90_advance import MIN_LEAD_SECONDS, ROME, confirm_sent, ts


def as_nums(vals):
    return " ".join(f"{int(x):02d}" for x in vals)


def format_preview(item):
    forecasts=item["simulations"]
    expected=ts(item["due_at"])
    lines=[
        f"🔭 TWIN90 — SIMULAZIONE PREVENTIVA #{int(item['key'].split('#')[-1]):03d}",
        f"📅 {expected:%Y-%m-%d} | concorso previsto alle {expected:%H:%M} (Italia)",
        f"Basata sull'ultimo concorso reale: {item['source_key']}",
        "⚠️ NUMERI SIMULATI, NON ESTRAZIONI REALI E NON CONSIGLI DI GIOCO",
    ]
    for mode in ("HYBRID","UNIFORM"):
        r=forecasts[mode]
        lines.extend([
            "",
            f"🧪 {mode} — estrazione virtuale",
            "BASE: "+as_nums(r["base"]),
            f"ORO: {r['oro1']:02d} | DOPPIO ORO: {r['oro2']:02d}",
            "EXTRA: "+as_nums(r["extra"]),
        ])
    lines.append("")
    lines.append("Dopo il concorso confronterò SOLO questi numeri già comunicati.")
    return "\n".join(lines)


def format_draw(item):
    real=item["actual"]
    advance=bool(item.get("pre_issued"))
    lines=[
        f"📊 TWIN90 LIVE — 10eLotto #{real['draw']:03d}",
        f"📅 {real['day']} | 🕒 {real.get('time','')}",
        "",
        "✅ ESTRAZIONE REALE",
        "BASE: "+as_nums(real["base"]),
        f"ORO: {real['oro1']:02d} | DOPPIO ORO: {real['oro2']:02d}",
        "EXTRA: "+as_nums(real["extra"]),
    ]
    if not advance:
        lines+=["", "⚠️ Nessuna simulazione preventiva verificata per questo concorso.",
                "Non ricostruisco una previsione dopo aver visto il risultato."]
        return "\n".join(lines)
    simulations=item["simulations"]
    stats=item["comparison"]
    lines.extend(["", "🎯 RISULTATO DELLE SIMULAZIONI INVIATE PRIMA DEL CONCORSO",
                  "Inviate su Telegram: "+str(item.get("issued_at",""))])
    for mode in ("HYBRID","UNIFORM"):
        generated=simulations[mode]
        comparison=stats[mode]
        matches=sorted(set(generated["base"]) & set(real["base"]))
        lines.append(f"{mode}: Base {comparison['base']}/20 | Extra {comparison['extra']}/15")
        lines.append("  Base coincidenti: "+(as_nums(matches) if matches else "nessuno"))
        lines.append(f"  Oro 1 esatto: {'SI' if comparison['gold1'] else 'NO'} | "
                     f"Oro 2 esatto: {'SI' if comparison['gold2'] else 'NO'}")
    lines.append("Test statistico virtuale. Nessuna giocata automatica.")
    return "\n".join(lines)


def format_summary(item):
    return (f"📊 TWIN90 LIVE — recupero automatico\n"
            f"Altri {item['count']} concorsi letti e analizzati: "
            f"{item['first_key']} → {item['last_key']}.\n"
            "Per non riempire Telegram, trovi gli ultimi risultati nei messaggi successivi.\n"
            "Nessuna puntata automatica.")


def format_message(item):
    if item["type"] in ("DRAW","DRAW_NOT_PREVIEWED"):
        return format_draw(item)
    if item["type"]=="PREVIEW":
        return format_preview(item)
    if item["type"]=="SUMMARY":
        return format_summary(item)
    raise ValueError("Notifica sconosciuta: invio bloccato")


def send_message(token,chat_id,message):
    # Non stampare URL, response.request, token o dettagli di requests che
    # potrebbero includere le credenziali nella URL.
    try:
        response=requests.post(
            "https://api.telegram.org/bot"+token+"/sendMessage",
            data={"chat_id":chat_id,"text":message,
                  "disable_web_page_preview":"true"},
            timeout=25,
        )
    except requests.RequestException:
        raise RuntimeError("Telegram non raggiungibile; notifica conservata in coda") from None
    if response.status_code!=200:
        raise RuntimeError(f"Telegram HTTP {response.status_code}; notifica conservata in coda")
    try:
        result=response.json()
    except ValueError:
        raise RuntimeError("Telegram ha restituito JSON non valido") from None
    if not result.get("ok"):
        raise RuntimeError("Telegram non ha confermato la notifica")
    return True


def publish(state,send_fn,now_fn=None,persist_fn=None):
    """Send queued reports, confirming preview before the draw and checkpointing."""
    now_fn=now_fn or (lambda:datetime.now(ROME))
    checkpoint=persist_fn or (lambda:None)
    count=0
    if not state.get("telegram_welcome_sent"):
        send_fn("✅ TWIN90 LIVE collegato a Superambo3.\n"
                "Le nuove simulazioni vengono inviate PRIMA del concorso, "
                "quando la fonte e l'orario lo permettono.\n"
                "Dopo il concorso mostro solo confronti già registrati. "
                "Nessuna giocata.")
        state["telegram_welcome_sent"]=True
        checkpoint()
        count+=1
    pending=state.setdefault("pending_notifications",[])
    while pending:
        item=pending[0]
        if item["type"]=="PREVIEW" and (
            now_fn()>=ts(item["due_at"])-timedelta(seconds=MIN_LEAD_SECONDS)
        ):
            # Never send an expired preview as if it were a pre-draw signal.
            record=state.get("advance_forecasts",{}).get(item["key"])
            if record and not record.get("sent_at"):
                record["status"]="EXPIRED_UNDELIVERED"
            pending.pop(0)
            checkpoint()
            continue
        send_fn(format_message(item))
        if item["type"]=="PREVIEW":
            confirm_sent(state,item["key"],when=now_fn())
        pending.pop(0)
        checkpoint()
        count+=1
    return count


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--state",required=True)
    args=p.parse_args()
    state_path=Path(args.state)
    if not state_path.exists():
        raise RuntimeError("Stato TWIN90 mancante; invio bloccato")
    token=os.environ.get("BOT_TOKEN","").strip()
    chat_id=os.environ.get("CHAT_ID","").strip()
    if not token or not chat_id:
        raise RuntimeError("BOT_TOKEN e CHAT_ID non disponibili nei GitHub Secrets")
    state=json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schema")!=1:
        raise RuntimeError("Stato non riconosciuto; invio bloccato")
    calls=0
    def _save():
        state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    def _send(msg):
        nonlocal calls
        send_message(token,chat_id,msg)
        calls+=1
    try:
        publish(state,_send,persist_fn=_save)
    finally:
        # Keep every delivery acknowledgement and any remaining pending messages.
        _save()
    print(f"TWIN90 Telegram: {calls} messaggi confermati, "
          f"coda {len(state.get('pending_notifications',[]))}")


if __name__=="__main__":
    main()
