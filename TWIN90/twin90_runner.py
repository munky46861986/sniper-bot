#!/usr/bin/env python3
"""TWIN90 live GitHub Actions supervisor.

Runs a real-feed read / Telegram delivery / isolated state commit cycle
every 5 minutes. One GitHub runner rotates after roughly 5h25m, then the
workflow dispatches its successor. Independently deployed from PAIR80.

Only read-only lottery observations and Telegram reports; never buys tickets.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
BASE = Path(__file__).resolve().parent.parent
STATE_DIR = BASE / "_twin90_state"
STATE = STATE_DIR / "twin90_live_state.json"
REPORT = BASE / "TWIN90" / "output_live" / "last_run.json"
MODEL = BASE / "TWIN90" / "twin90_model_2025_2026.json"

def log(msg):
    print(f"[TWIN90 {datetime.now(ROME).isoformat(timespec='seconds')}] {msg}",flush=True)

def checked_run(args, cwd=BASE, timeout=150):
    cmd=[str(x) for x in args]
    p=subprocess.run(cmd,cwd=str(cwd),capture_output=True,text=True,timeout=timeout,check=False)
    if p.returncode!=0:
        # Avoid logging private POST URLs, environmental variables or bot tokens.
        tail=(p.stderr or p.stdout or "")[-600:]
        raise RuntimeError(f"Exit {p.returncode}: "+tail)
    return p.stdout.strip()

def save_state():
    """Commit and push only the dedicated data branch, never main."""
    if not STATE.exists():
        raise RuntimeError("No live state to persist")
    checked_run(["git","add","twin90_live_state.json"],cwd=STATE_DIR,timeout=25)
    status=subprocess.run(["git","diff","--cached","--quiet"],cwd=str(STATE_DIR),timeout=25,check=False)
    if status.returncode==0:
        return "unchanged"
    if status.returncode!=1:
        raise RuntimeError("git diff --cached could not check state")
    checked_run(["git","-c","user.name=github-actions[bot]",
                "-c","user.email=41898282+github-actions[bot]@users.noreply.github.com",
                "commit","-m","state: TWIN90 live observations + Telegram delivery"],cwd=STATE_DIR,timeout=35)
    checked_run(["git","push","origin","HEAD:twin90-live-state"],cwd=STATE_DIR,timeout=60)
    return "pushed"

def run_tick():
    """Always persist confirmed deliveries, even if a later Telegram send fails."""
    feed_ok=False
    delivery_error=None
    feed_error=None
    try:
        output=checked_run([sys.executable,BASE/"TWIN90"/"twin90_live.py",
                 "--model",MODEL,"--state",STATE,"--output",REPORT],timeout=145)
        feed_ok=True
        log("Acquisizione reale OK: "+output[-380:].replace("\n"," "))
    except Exception as exc:
        feed_error=str(exc)
        log("ERRORE fonte reale: "+feed_error[-400:])
    # Only publish when state exists; still retry pending delivery on feed failures.
    if STATE.exists():
        try:
            output=checked_run([sys.executable,BASE/"TWIN90"/"twin90_telegram.py",
                                "--state",STATE],timeout=145)
            log(output[-220:])
        except Exception as exc:
            delivery_error=str(exc)
            log("ERRORE Telegram (coda conservata): "+delivery_error[-400:])
        try:
            log("Persistenza: "+save_state())
        except Exception as exc:
            log("ERRORE CRITICO salvataggio stato: "+str(exc)[-400:])
            # Prevent further sending until persistence is restored.
            raise
    return bool(feed_ok and not delivery_error)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--seconds",type=int,default=int(os.getenv("TWIN90_RUNTIME_SECONDS","19500")))
    ap.add_argument("--interval",type=int,default=300)
    ap.add_argument("--once",action="store_true")
    opt=ap.parse_args()
    if opt.seconds<=0 or opt.interval<60:raise ValueError("Invalid cadence")
    if not STATE_DIR.exists():raise RuntimeError("TWIN90 state branch checkout missing")
    log("Avvio supervisor LIVE: controllo ogni "+str(opt.interval)+" s")
    launch=time.monotonic()
    n=0
    while True:
        began=time.monotonic()
        n+=1
        try:
            run_tick()
        except Exception:
            # Do not run another tick if state could not be persisted.
            raise
        if opt.once:
            return
        elapsed=time.monotonic()-launch
        if elapsed+opt.interval>=opt.seconds:
            log(f"Rotazione programmata dopo {n} controlli, {int(elapsed)} secondi")
            return
        until=began+opt.interval
        delay=max(0,until-time.monotonic())
        if delay:
            time.sleep(delay)

if __name__=="__main__":
    main()
