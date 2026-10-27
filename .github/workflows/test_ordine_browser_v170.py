#!/usr/bin/env python3
"""Diagnostica V170: osserva una pagina pubblica senza credenziali.

Usa il Chrome installato nel runner GitHub. Non fa login, non piazza giocate,
non modifica il bot, non stampa/salva cookie, intestazioni, token o payload
estranei all'endpoint di estrazione. I dati mostrati sono da convalidare contro
My Lotteries: il fatto che una risposta contenga 20 numeri non prova che sia
l'ordine della visualizzazione.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

SITE_URL = "https://www.eurobet.it/it/lotterie/10elotto"
TARGET_PATH = "/del/serviziFE/jsonrest/10elotto/raccolteFrequentiV2.json"


def valid_draw(row: object) -> dict | None:
    if not isinstance(row, dict):
        return None
    nums = row.get("numeri")
    if not isinstance(nums, list) or len(nums) != 20:
        return None
    if any(isinstance(x, bool) or not isinstance(x, (int, str)) for x in nums):
        return None
    try:
        nums = [int(x) for x in nums]
        draw = int(row["progressivoGiornaliero"])
        stamp = int(row["timestampProssimaEstrazione"])
    except (ValueError, TypeError, KeyError):
        return None
    if len(set(nums)) != 20 or any(not 1 <= x <= 90 for x in nums):
        return None
    if not 1 <= draw <= 288 or stamp <= 0:
        return None
    return {
        "draw": draw,
        "utc": datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).isoformat(),
        "timestamp_ms": stamp,
        "status": str(row.get("statoRaccolta", ""))[:24],
        "five_api": nums[4],
        "five_sorted": sorted(nums)[4],
        "nums": nums,
    }


async def inspect(minutes: float, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    events: list[str] = []
    rows: dict[tuple[int, int], dict] = {}
    counters = {"http200": 0, "http_errors": 0, "matched_responses": 0, "json_errors": 0}
    tasks: set[asyncio.Task] = set()

    def log(message: str):
        line = datetime.now(timezone.utc).strftime("%H:%M:%S UTC") + " | " + message
        print(line, flush=True)
        events.append(line)

    async def inspect_response(resp):
        try:
            url = urlparse(resp.url)
            if url.path.lower() != TARGET_PATH.lower():
                return
            counters["matched_responses"] += 1
            log(f"Risposta endpoint: HTTP {resp.status} host={url.hostname} path={url.path}")
            if resp.status != 200:
                counters["http_errors"] += 1
                return
            counters["http200"] += 1
            try:
                payload = await asyncio.wait_for(resp.json(), timeout=15)
            except Exception as exc:
                counters["json_errors"] += 1
                log(f"Errore conversione JSON: {type(exc).__name__}")
                return
            entries = payload.get("raccolteFrequenti") if isinstance(payload, dict) else None
            if not isinstance(entries, list):
                log("HTTP 200 ma 'raccolteFrequenti' non presente")
                return
            log(f"Raccolte nell'ultima risposta: {len(entries)}")
            for entry in entries:
                valid = valid_draw(entry)
                if valid is None:
                    continue
                key = (valid["timestamp_ms"], valid["draw"])
                if key not in rows:
                    rows[key] = valid
                    log(f"CONCORSO ACQUISITO: #{valid['draw']} utc={valid['utc']} 5API={valid['five_api']} 5CRESC={valid['five_sorted']}")
        except Exception as exc:
            log(f"Errore di diagnosi nel browser: {type(exc).__name__}: {str(exc)[:120]}")

    def on_response(resp):
        t = asyncio.create_task(inspect_response(resp))
        tasks.add(t)
        t.add_done_callback(tasks.discard)

    log("V170 — sola lettura; nessun login, nessuna giocata, nessun token Telegram")
    async with async_playwright() as playwright:
        browser = None
        for channel in ["chrome", "msedge"]:
            try:
                browser = await playwright.chromium.launch(channel=channel, headless=True, args=["--no-first-run"])
                log(f"Avviato browser presente sul runner: {channel}")
                break
            except Exception as exc:
                log(f"Browser {channel} non avviato: {type(exc).__name__} {str(exc)[:170]}")
        if browser is None:
            log("ESITO: browser non disponibile sul runner")
        else:
            context = await browser.new_context(locale="it-IT", viewport={"width": 1280, "height": 950})
            page = await context.new_page()
            page.on("response", on_response)
            try:
                response = await page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60000)
                log(f"Apertura Eurobet: HTTP {response.status if response else 'senza risposta'}")
            except Exception as exc:
                log(f"Pagina non completamente aperta: {type(exc).__name__}: {str(exc)[:170]}")
            start = time.monotonic()
            next_reload = start + 60
            deadline = start + max(0.5, minutes) * 60
            while time.monotonic() < deadline:
                if time.monotonic() >= next_reload:
                    log("Ricarico la pagina per verificare gli aggiornamenti del concorso")
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=45000)
                    except Exception as exc:
                        log(f"Ricaricamento parziale: {type(exc).__name__}: {str(exc)[:140]}")
                    next_reload += 60
                await asyncio.sleep(2)
            if tasks:
                await asyncio.wait(tasks, timeout=20)
            await context.close()
            await browser.close()

    with (output_dir / "eventi_v170.txt").open("w", encoding="utf-8") as f:
        f.write("\n".join(events) + "\n")
    with (output_dir / "sequenze_v170.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ms", "concorso", "utc", "stato", "5_API", "5_crescente", *[f"p{i:02d}" for i in range(1, 21)]])
        for r in sorted(rows.values(), key=lambda v: v["timestamp_ms"]):
            writer.writerow([r["timestamp_ms"], r["draw"], r["utc"], r["status"], r["five_api"], r["five_sorted"], *r["nums"]])
    result = {"endpoint_responses": counters["matched_responses"], "endpoint_http200": counters["http200"],
              "endpoint_http_errors": counters["http_errors"], "concorsi_distinti": len(rows),
              "risultato": "DATI_RECUPERATI_DA_VERIFICARE" if rows else "NESSUN_DATO_ORDINATO_RECUPERATO"}
    (output_dir / "riepilogo_v170.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log("RISULTATO: " + json.dumps(result, ensure_ascii=False))
    # append summary after saving events
    with (output_dir / "eventi_v170.txt").open("a", encoding="utf-8") as f:
        f.write(events[-1] + "\n")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--minuti", type=float, default=3)
    p.add_argument("--output", default="risultati_v170")
    args = p.parse_args()
    asyncio.run(inspect(args.minuti, Path(args.output)))


if __name__ == "__main__":
    main()
