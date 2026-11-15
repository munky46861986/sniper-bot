"""PAIR80 runtime: PAIR80-only, historical strategies remain untouched/paused.

This file runs only when launched by sniper.py in SUPERAMBO3_MODE=PAIR80_ONLY.
It never places stakes, purchases or lottery tickets; all accounting virtual.
"""
import asyncio
import os
import time
from datetime import datetime
from telegram import BotCommand, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from pair80_shadow import ensure, seed, process, report, recent

MODE = "PAIR80_ONLY"
PAUSED = ("ABC A/B/C, ORARI, R2/F3, LAB, V212/V214, V27/V28/V38, "
          "V52/V55/V56/V67/V70/V72/V114/V121, MULTI/legacy")


async def _send(s, app, message):
    await s.abc_send(app, message)


async def _command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["legacy"]
    tracker = context.application.bot_data["pair80_tracker"]
    name = update.effective_message.text.split()[0].split("@")[0].lstrip("/").lower()
    if name in ("pair80", "status", "oggi", "pair80oggi"):
        day = s.now_dt().strftime("%Y-%m-%d") if name in ("oggi", "pair80oggi") else None
        output = report(tracker, day=day)
    elif name in ("pair80segnali", "pair80recenti"):
        output = recent(tracker)
    elif name in ("menu", "start", "help"):
        output = ("SUPERAMBO3 PAIR80_SOURCE SHADOW\n"
                  "/pair80 - stato totale\n/pair80oggi - giornata corrente\n"
                  "/pair80segnali - ultimi segnali\n/pausestato - strategie in pausa\n"
                  "Warmup 80 estrazioni consecutive della stessa giornata.\n"
                  "Solo simulazione H1/H2; nessuna giocata reale.")
    elif name == "pausestato":
        output = ("ALTRI METODI IN PAUSA (codice e stato conservati):\n" +
                  PAUSED + "\nPAIR80_SOURCE SHADOW attivo. Nessuna giocata reale.")
    else:
        output = ("Metodo legacy in pausa in modalita PAIR80_ONLY. "
                  "Codice e storico conservati; usa /pair80 per il nuovo metodo.")
    if update.effective_message:
        await update.effective_message.reply_text(output)


async def _poll_loop(s, tracker, app):
    launched = time.monotonic()
    last_error = ""
    while True:
        if time.monotonic() - launched >= s.BOT_MAX_RUNTIME_SECONDS:
            saved = tracker.save(git=True, force=True)
            s.console_log("PAIR80 ROTAZIONE: " + saved)
            if "ERRORE" in saved:
                await _send(s, app, "PAIR80: rotazione non confermata; " + saved)
                raise RuntimeError("PAIR80 non puo ruotare: stato non confermato")
            if s.BOT_ROTATION_NOTIFY:
                await _send(s, app, "PAIR80 SHADOW: rotazione, stato salvato.")
            return
        try:
            live_rows = s.fetch_multichannel_recent(days=2)
            if not live_rows:
                raise RuntimeError("Nessuna estrazione recente dalla fonte LIVE")
            # Archivio completo: necessario se /estrazioni/ mostra solo pochi concorsi.
            # Restituisce anche le nuove righe LIVE con controllo anti-conflitto.
            try:
                rows = s.lab_fetch_complete_history(live_rows=live_rows)
            except Exception as exc:
                s.console_log(f"PAIR80 archivio completo indisponibile: {exc}")
                rows = live_rows
            rows = sorted(rows, key=lambda r: s.order_key(s.abc_key(r)))
            state = ensure(tracker)
            if state["last_key"] is None:
                note = seed(tracker, rows)
                saved = tracker.save(git=True, force=True)
                s.console_log(f"PAIR80 STARTUP: {note} | {saved}")
                await _send(s, app, "PAIR80 SHADOW AVVIATO.\n"
                            "Tutti gli altri metodi in pausa.\n"
                            + note + "\n" + report(tracker))
            else:
                unseen = [r for r in rows if s.order_key(s.abc_key(r)) >
                          s.order_key(state["last_key"])]
                if unseen:
                    outputs, alerts, gaps = [], [], 0
                    for raw in unseen:
                        result = process(tracker, raw)
                        outputs.extend(result["results"])
                        alerts.extend(result["signals"])
                        gaps += int(result["gap"])
                    saved = tracker.save(git=True)
                    s.console_log(f"PAIR80 {state['last_key']} | nuovi={len(unseen)} "
                                  f"segnali={len(alerts)} gap={gaps} | {saved}")
                    if len(unseen) > 3:
                        # No retrospective trading-like advice, just reconciliation.
                        await _send(s, app,
                                    f"PAIR80: recuperate {len(unseen)} estrazioni. "
                                    f"Nuovi segnali storici: {len(alerts)}; gap: {gaps}.\n"
                                    + report(tracker))
                    else:
                        parts = []
                        if outputs:
                            parts.append("PAIR80 ESITI:\n" + "\n".join(outputs[-12:]))
                        if alerts:
                            parts.append("PAIR80 NUOVI SEGNALI SHADOW:\n" + "\n".join(alerts[-9:]))
                        if gaps:
                            parts.append("GAP FONTE: warmup azzerato; nessun MISS inventato.")
                        if parts:
                            await _send(s, app, "\n\n".join(parts))
            last_error = ""
        except Exception as exc:
            msg = f"{type(exc).__name__}: {str(exc)[:250]}"
            s.console_log("PAIR80 ERRORE: " + msg)
            if msg != last_error:
                try:
                    await _send(s, app, "PAIR80 sospeso per errore fonte/stato: " + msg)
                except Exception:
                    pass
                last_error = msg
        await asyncio.sleep(max(25, s.LOOP_SEC))


async def main(s):
    s.acquire_single_instance_lock()
    if not s.TOKEN or s.CHAT_ID is None:
        raise RuntimeError("Configura BOT_TOKEN e CHAT_ID (non nel codice)")
    app = (ApplicationBuilder().token(s.TOKEN)
           .connect_timeout(25).read_timeout(35).write_timeout(35)
           .pool_timeout(35).build())
    tracker = s.DistanceABCTracker()  # state legacy untouched; only new substate is updated
    ensure(tracker)
    app.bot_data["pair80_tracker"] = tracker
    app.bot_data["legacy"] = s
    commands = ["start","help","menu","status","oggi","pausestato",
                "pair80","pair80oggi","pair80segnali","pair80recenti",
                "abc","a","b","c","orari","orarioggi","ritardi","r2f3",
                "lab","labwarmup","v212","v214","multi","v27","v28",
                "v38","v52","v55","v56","v67","v70","v72","v114","v121"]
    for command in commands:
        app.add_handler(CommandHandler(command, _command))
    await s.abc_initialize_telegram_with_retry(app)
    try:
        await app.start()
        try:
            await app.bot.set_my_commands([
                BotCommand("pair80", "PAIR80 - stato completo"),
                BotCommand("pair80oggi", "PAIR80 - risultati di oggi"),
                BotCommand("pair80segnali", "PAIR80 - ultimi segnali"),
                BotCommand("pausestato", "Metodi precedenti in pausa"),
                BotCommand("menu", "Menu nuovo motore"),
            ])
        except Exception as exc:
            s.console_log("PAIR80 SET_COMMANDS errore: " + str(exc)[:180])
        await app.updater.start_polling(drop_pending_updates=True)
        await _poll_loop(s, tracker, app)
    finally:
        saved = tracker.save(git=True, force=True)
        s.console_log("PAIR80 CHIUSURA: " + saved)
        if app.updater and app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()
