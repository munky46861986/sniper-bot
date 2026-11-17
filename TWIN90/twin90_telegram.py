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


def as_nums(vals):
    return " ".join(f"{int(x):02d}" for x in vals)


def format_draw(item):
    real=item["actual"]
    simulations=item["simulations"]
    stats=item["comparison"]
    lines=[
        f"📊 TWIN90 LIVE — 10eLotto #{real['draw']:03d}",
        f"📅 {real['day']} | 🕒 {real.get('time','')}",
        "",
        "✅ ESTRAZIONE REALE",
        "BASE: "+as_nums(real["base"]),
        f"ORO: {real['oro1']:02d} | DOPPIO ORO: {real['oro2']:02d}",
        "EXTRA: "+as_nums(real["extra"]),
        "",
        "🧪 CONFRONTO SIMULAZIONI (nessuna giocata)",
    ]
    for mode in ("HYBRID","UNIFORM"):
        if mode not in simulations or mode not in stats:
            continue
        generated=simulations[mode]
        comparison=stats[mode]
        lines.append(f"{mode}: Base {comparison['base']}/20 | Extra {comparison['extra']}/15")
        lines.append("  Simulati Base: "+as_nums(generated["base"]))
        lines.append(f"  Simulati Oro: {generated['oro1']:02d}-{generated['oro2']:02d}")
        lines.append("  Simulati Extra: "+as_nums(generated["extra"]))
    lines.append("Confronto statistico, non previsione certa.")
    return "\n".join(lines)


def format_summary(item):
    return (f"📊 TWIN90 LIVE — recupero automatico\n"
            f"Altri {item['count']} concorsi letti e analizzati: "
            f"{item['first_key']} → {item['last_key']}.\n"
            "Per non riempire Telegram, trovi gli ultimi risultati nei messaggi successivi.\n"
            "Nessuna puntata automatica.")


def format_message(item):
    if item["type"]=="DRAW":
        return format_draw(item)
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


def publish(state,send_fn):
    """Persistenza gestita dal chiamante, anche se un invio successivo fallisce."""
    count=0
    if not state.get("telegram_welcome_sent"):
        send_fn("✅ TWIN90 LIVE collegato a Superambo3.\n"
                "Da ora invio automaticamente le estrazioni REALI nuove "
                "con Base, Oro, Doppio Oro, Extra e confronto HYBRID/UNIFORM.\n"
                "Il controllo GitHub è programmato ogni 5 minuti. "
                "Nessuna giocata automatica.")
        state["telegram_welcome_sent"]=True
        count+=1
    pending=state.setdefault("pending_notifications",[])
    while pending:
        item=pending[0]
        send_fn(format_message(item))
        pending.pop(0)
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
    def _send(msg):
        nonlocal calls
        send_message(token,chat_id,msg)
        calls+=1
        # Salva l'avanzamento solo dopo conferma. In caso di fallimento
        # successivo, il workflow potrà conservare i messaggi rimanenti.
        state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    try:
        publish(state,_send)
    finally:
        # Anche su errore, conservare il progresso degli invii già confermati.
        state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"TWIN90 Telegram: {calls} messaggi confermati, "
          f"coda {len(state.get('pending_notifications',[]))}")


if __name__=="__main__":
    main()
