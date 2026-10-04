# ============================================================
# 🎯 10eLOTTO FOCUS FAST + INCROCIO + CORE SYNC20 + MULTI BD12+ED12+O2F12 — v20.2 FEED FIX + BD12/ED12/O2F12
# ============================================================
#
# METODI ATTIVI:
#   • ritardo 13..18
#   • segnale solo con 3 o 4 candidati
#   • ranking candidati con TRANS80 H1 calcolato solo sul passato
#   • sceglie il TRANS80 piu' alto
#   • FOCUS: UN SOLO NUMERO, SOLO prossima H1
#   • INCROCIO: persistenza candidati, ambata + ambo H1-H5
#   • CORE SYNC20: solo FOCUS a 3 candidati, coppia al primo ×2, SYNC20 positivo, ambo H1-H5
#   • nessun backfill dei risultati INCROCIO/CORE/MULTI BD12+ED12+O2F12
#
# PAUSA v19:
#   • ENGINE predittivo, SOSIA, FORCED ONE, TRIPLETTE, HC, BURST,
#     POST-6, PLAY, AMBO, DUAL e gli altri tracker non vengono
#     aggiornati nel loop live e non inviano notifiche.
#   • il loro state storico viene comunque caricato e risalvato
#     senza cancellarlo, per poterli riattivare in futuro.
#
# INFRASTRUTTURA:
#   • polling sito ogni LOOP_SEC
#   • state persistente GitHub
#   • rotazione automatica GitHub runner prima del limite
# ============================================================

import asyncio
import hashlib
from collections import Counter
from itertools import combinations
import atexit
import json
import math
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from telegram import BotCommand, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

try:
    import fcntl
except ImportError:
    fcntl = None


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")
CHAT_ID = int(CHAT_ID_RAW) if CHAT_ID_RAW and str(CHAT_ID_RAW).lstrip("-").isdigit() else None

BOT_TZ_NAME = os.getenv("BOT_TZ", "Europe/Rome")
BOT_TZ = ZoneInfo(BOT_TZ_NAME)

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
URL_YESTERDAY = "https://10elotto5minuti.com/estrazioni-di-ieri"
URL_DAY_BEFORE_YESTERDAY = "https://10elotto5minuti.com/estrazioni-dellaltro-ieri"
URL_YEAR_ARCHIVE = "https://10elotto5minuti.com/estrazioni-ultimo-anno"
LOTTOLOGIA_BASE = "https://lottologia.com/10elotto5minuti"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "10elotto_engine_only_state.json")
LEGACY_STATE_FILE = os.path.join(BASE_DIR, "superambo_gap4_core_fast_h1_state.json")
LOCK_FILE = "/tmp/10elotto_engine_only.lock"
STATE_VERSION = 1

LOOP_SEC = int(os.getenv("LOOP_SEC", "60"))
BOT_MAX_RUNTIME_SECONDS = int(os.getenv("BOT_MAX_RUNTIME_SECONDS", "19800"))
BOT_ROTATION_NOTIFY = os.getenv("BOT_ROTATION_NOTIFY", "1") != "0"
WARMUP_RETRY_SEC = int(os.getenv("WARMUP_RETRY_SEC", "300"))
WARMUP_FAIL_TG_MIN_SECONDS = int(os.getenv("WARMUP_FAIL_TG_MIN_SECONDS", "900"))
WARMUP_DAYS = int(os.getenv("WARMUP_DAYS", "7"))
WARMUP_MIN_DRAWS = int(os.getenv("WARMUP_MIN_DRAWS", "120"))
WARMUP_FULL_DAY_DRAWS = int(os.getenv("WARMUP_FULL_DAY_DRAWS", "288"))
WARMUP_REQUIRE_COMPLETE_PAST_DAYS = os.getenv("WARMUP_REQUIRE_COMPLETE_PAST_DAYS", "1") != "0"
PROCESSED_MAX = int(os.getenv("PROCESSED_MAX", "12000"))

ENGINE_SHADOW_ENABLED = True
ENGINE_NOTIFY_SIGNALS = os.getenv("ENGINE_NOTIFY_SIGNALS", "1") != "0"
ENGINE_NOTIFY_H1_RESULT = os.getenv("ENGINE_NOTIFY_H1_RESULT", "1") != "0"
ENGINE_NOTIFY_H5_RESULT = os.getenv("ENGINE_NOTIFY_H5_RESULT", "1") != "0"
ENGINE_MODEL_VERSION = 1
ENGINE_HISTORY_MAX = int(os.getenv("ENGINE_HISTORY_MAX", "800"))
ENGINE_MIN_HISTORY = int(os.getenv("ENGINE_MIN_HISTORY", "120"))
ENGINE_TRANSITION_LOOKBACK = int(os.getenv("ENGINE_TRANSITION_LOOKBACK", "300"))
ENGINE_MARGIN_LOOKBACK = int(os.getenv("ENGINE_MARGIN_LOOKBACK", "300"))
ENGINE_MIN_MARGIN_SAMPLES = int(os.getenv("ENGINE_MIN_MARGIN_SAMPLES", "80"))
ENGINE_SELECT_RATE = float(os.getenv("ENGINE_SELECT_RATE", "0.15"))
ENGINE_RECENT_MAX = int(os.getenv("ENGINE_RECENT_MAX", "250"))

ENGINE_H5_MAX = 5
ENGINE_H5_RECORD_MAX = int(os.getenv("ENGINE_H5_RECORD_MAX", "5000"))
ENGINE_MULTI_DIAG_VERSION = 1

# PLAY SHADOW: prima uscita H1-H3 = conferma; dalla successiva si cerca la seconda entro H5.
ENGINE_PLAY_DIAG_VERSION = 1
ENGINE_PLAY_RECORD_MAX = int(os.getenv("ENGINE_PLAY_RECORD_MAX", "5000"))
ENGINE_NOTIFY_PLAY_CONFIRM = os.getenv("ENGINE_NOTIFY_PLAY_CONFIRM", "1") != "0"
ENGINE_NOTIFY_PLAY_RESULT = os.getenv("ENGINE_NOTIFY_PLAY_RESULT", "1") != "0"

# AMBO 2xHOT5 NO-LOCK: simulazione con notifiche Telegram.
# Prima uscita TOP1 entro H1-H3 = conferma. I DUE accompagnatori sono scelti fra
# i numeri PRESENTI nel draw di conferma: massimo conteggio nelle ultime 5
# estrazioni (inclusa la conferma), tie-break recency e poi numero piu' basso.
# Ogni HIGH CONFIDENCE apre una sessione indipendente; sono ammesse sovrapposizioni.
AMBO_SIM_ENABLED = os.getenv("AMBO_SIM_ENABLED", "1") != "0"
AMBO_SIM_STAKE_CENTS = max(1, int(os.getenv("AMBO_SIM_STAKE_CENTS", "100")))
AMBO_SIM_PAYOUT_MULTIPLIER = float(os.getenv("AMBO_SIM_PAYOUT_MULTIPLIER", "14"))
AMBO_SIM_NOTIFY = os.getenv("AMBO_SIM_NOTIFY", "1") != "0"
AMBO_SIM_RECORD_MAX = max(100, int(os.getenv("AMBO_SIM_RECORD_MAX", "5000")))
AMBO_SIM_BET_LOG_MAX = max(100, int(os.getenv("AMBO_SIM_BET_LOG_MAX", "15000")))
AMBO_SIM_DIAG_VERSION = 3

# SOSIA 20/90: campione uniforme indipendente, generato PRIMA del draw reale successivo.
# NON altera ENGINE, HIGH CONFIDENCE, MULTI-HIT, PLAY o AMBO.
SOSIA_ENABLED = os.getenv("SOSIA_ENABLED", "1") != "0"
SOSIA_RECORD_MAX = max(100, int(os.getenv("SOSIA_RECORD_MAX", "600")))
SOSIA_VERSION = 1
SOSIA_RANDOM = secrets.SystemRandom()
# SOSIA ADATTIVO: emette 20 numeri PRIMA del draw successivo, poi apprende
# soltanto dal risultato successivo. Il vecchio SOSIA uniforme resta un controllo.
SOSIA_PRED_ENABLED = os.getenv("SOSIA_PRED_ENABLED", "1") != "0"
SOSIA_PRED_VERSION = 1
SOSIA_PRED_RECORD_MAX = max(100, int(os.getenv("SOSIA_PRED_RECORD_MAX", "600")))
SOSIA_PRED_NAMES = ("hot5", "hot20", "hot100", "repeat", "transition", "engine4")
SOSIA_PRETRAIN_FILE = os.path.join(BASE_DIR, "sosia_backtest_training.json")
SOSIA_PRETRAIN_STRENGTH = 60.0  # peso massimo del passato rispetto ai risultati live

# SOSIA SNIPER: estrae la classifica interna del SOSIA adattivo e segue H1
# di TOP1 / TOP2 / ambo TOP1-TOP2. Nessuna puntata automatica.
SOSIA_SNIPER_VERSION = 1
SOSIA_SNIPER_RECORD_MAX = max(100, int(os.getenv("SOSIA_SNIPER_RECORD_MAX", "1500")))
SOSIA_SNIPER_NOTIFY = os.getenv("SOSIA_SNIPER_NOTIFY", "1") != "0"
# Soglia fissata PRIMA del forward: 90° percentile del gap TOP1-TOP2 nel
# blocco storico di verifica separato da 600 draw. Non viene riottimizzata live.
SOSIA_SNIPER_STRONG_GAP = float(os.getenv("SOSIA_SNIPER_STRONG_GAP", "0.07691307328092588"))
# Nuovi tracker SHADOW: non alterano il SOSIA adattivo. Le soglie ULTRA sono
# ipotesi congelate da validare in forward, non vengono riottimizzate live.
SOSIA_SNIPER_ULTRA_SCORE = float(os.getenv("SOSIA_SNIPER_ULTRA_SCORE", "0.95"))
SOSIA_SNIPER_ULTRA_GAP = float(os.getenv("SOSIA_SNIPER_ULTRA_GAP", "0.05"))
SOSIA_SNIPER_PAIR_LOOKBACK = max(30, int(os.getenv("SOSIA_SNIPER_PAIR_LOOKBACK", "200")))
# Pattern: nuovo tracker SOLO osservativo per posizione, numeri e co-HIT del SOSIA.
SOSIA_PATTERN_VERSION = 1

# PATTERN LAB: tre piste SHADOW aggiuntive, tutte congelate PRIMA del draw futuro.
# - POSITION CALIBRATED: corregge con shrink la resa storica delle posizioni #1..#20.
# - PATTERN TRANSITION: osserva il passaggio fra fasce A/B/C/D del ranking.
# - NUMBER WATCH: segue 5 numeri del TOP20 con miglior resa storica shrinkata.
# Nessuna di queste piste modifica SOSIA, ENGINE, pesi, soglie o giocate.
SOSIA_PATTERN_LAB_VERSION = 1
SOSIA_POS_PRIOR_DRAWS = max(20.0, float(os.getenv("SOSIA_POS_PRIOR_DRAWS", "120")))
SOSIA_POS_CAL_EXPONENT = max(0.0, min(2.0, float(os.getenv("SOSIA_POS_CAL_EXPONENT", "0.60"))))
SOSIA_NUMBER_WATCH_PRIOR = max(10.0, float(os.getenv("SOSIA_NUMBER_WATCH_PRIOR", "60")))
SOSIA_NUMBER_WATCH_SIZE = max(1, min(10, int(os.getenv("SOSIA_NUMBER_WATCH_SIZE", "5"))))
SOSIA_NUMBER_WATCH_MIN_SELECT = max(1, int(os.getenv("SOSIA_NUMBER_WATCH_MIN_SELECT", "15")))
SOSIA_TRANSITION_MIN_SUPPORT = max(3, int(os.getenv("SOSIA_TRANSITION_MIN_SUPPORT", "8")))

PERSIST_GIT_STATE = os.getenv("PERSIST_GIT_STATE", "1") != "0"
GIT_COMMIT_MIN_SECONDS = int(os.getenv("GIT_COMMIT_MIN_SECONDS", "300"))
_LAST_GIT_COMMIT_TS = 0.0

_ITALIAN_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def now_dt():
    return datetime.now(BOT_TZ)


def now_txt():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def day_key():
    return now_dt().strftime("%Y-%m-%d")


def console_log(message):
    print(f"[{now_txt()}] {message}", flush=True)


def draw_key(day, e):
    return f"{day}#{int(e):03d}"


def safe_pct(num, den):
    return (100.0 * float(num) / float(den)) if den else 0.0


def sim_euro(cents):
    return f"{int(cents) / 100.0:.2f} €"


def sim_draw_is_consecutive(previous_key, day, draw_id):
    """La simulazione non deve inventare colpi su estrazioni mancanti."""
    if not previous_key:
        return True
    try:
        previous_day, previous_id = str(previous_key).rsplit("#", 1)
        prev_date = datetime.fromisoformat(previous_day).date()
        new_date = datetime.fromisoformat(str(day)).date()
        prev_id = int(previous_id)
        current_id = int(draw_id)
        return (
            (new_date == prev_date and current_id == prev_id + 1)
            or (new_date == prev_date + timedelta(days=1) and prev_id == 288 and current_id == 1)
        )
    except (ValueError, TypeError):
        return False


def atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _http_get_text(url, retries=3, timeout=20):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            if not r.text or len(r.text) < 100:
                raise RuntimeError("risposta HTTP vuota/corta")
            return r.text
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1.2 * attempt)
    raise RuntimeError(f"download fallito: {url} | {last_exc}")


def _extract_day_from_header(line):
    m = re.search(
        r"Estrazione\s+(?:[^,]+,\s*)?(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4}),",
        str(line), re.IGNORECASE,
    )
    if not m:
        return None
    month = _ITALIAN_MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        return datetime(int(m.group(3)), month, int(m.group(1))).strftime("%Y-%m-%d")
    except Exception:
        return None


def parse_site_records(url=URL, expected_day=None):
    html = _http_get_text(url)
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    lines = [x.strip() for x in text.splitlines() if x.strip()]

    out = []
    i = 0
    while i < len(lines):
        row0 = lines[i]
        m = re.search(r"Estrazione\s+.*?\bn\.\s*(\d+)", row0, re.IGNORECASE)
        if not m:
            i += 1
            continue

        e = int(m.group(1))
        rec_day = _extract_day_from_header(row0) or expected_day
        nums = []
        i += 1
        while i < len(lines):
            row = lines[i]
            if re.search(r"Estrazione\s+.*?\bn\.\s*\d+", row, re.IGNORECASE):
                break
            if re.fullmatch(r"\d{1,2}", row):
                n = int(row)
                if 1 <= n <= 90:
                    nums.append(n)
            i += 1

        if len(nums) >= 20:
            clean = nums[:20]
            if len(set(clean)) == 20 and (not expected_day or rec_day == expected_day):
                out.append((rec_day or expected_day or day_key(), e, clean))

    dedup = {}
    for d, e, nums in out:
        dedup[(str(d), int(e))] = (str(d), int(e), list(map(int, nums)))
    return sorted(dedup.values(), key=lambda x: (x[0], x[1]))


def parse_site_today():
    return parse_site_records(URL, expected_day=day_key())


def _lottologia_url_for_offset(day_offset):
    day_offset = int(day_offset)
    if day_offset <= 0:
        return f"{LOTTOLOGIA_BASE}/estrazioni/"
    if day_offset == 1:
        return f"{LOTTOLOGIA_BASE}/estrazioni-ieri"
    return f"{LOTTOLOGIA_BASE}/estrazioni-{day_offset}gg-fa"


def _lottologia_month_number(token):
    aliases = {
        "gen": 1, "gennaio": 1, "feb": 2, "febbraio": 2, "mar": 3, "marzo": 3,
        "apr": 4, "aprile": 4, "mag": 5, "maggio": 5, "giu": 6, "giugno": 6,
        "lug": 7, "luglio": 7, "ago": 8, "agosto": 8, "set": 9, "sett": 9,
        "settembre": 9, "ott": 10, "ottobre": 10, "nov": 11, "novembre": 11,
        "dic": 12, "dicembre": 12,
    }
    return aliases.get(str(token).lower().strip().rstrip("."))


def parse_lottologia_records(url, expected_day=None):
    html = _http_get_text(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    header_re = re.compile(
        r"#\s*(\d{1,3})\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\.?\s+(\d{4})\s+(\d{1,2}:\d{2})",
        re.IGNORECASE,
    )
    headers = list(header_re.finditer(text))
    out = []

    for idx, m in enumerate(headers):
        e = int(m.group(1))
        mon = _lottologia_month_number(m.group(3))
        if not mon:
            continue
        try:
            rec_day = datetime(int(m.group(4)), mon, int(m.group(2))).strftime("%Y-%m-%d")
        except Exception:
            continue
        if expected_day and rec_day != expected_day:
            continue

        block_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        block = text[m.end():block_end]
        sec = re.search(
            r"\bNumeri\b(.*?)(?=\bOro\b|\bDoppio\s+Oro\b|\bExtra\b|$)",
            block, re.IGNORECASE | re.DOTALL,
        )
        if not sec:
            continue
        vals = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", sec.group(1))]
        nums = [n for n in vals if 1 <= n <= 90][:20]
        if len(nums) == 20 and len(set(nums)) == 20:
            out.append((rec_day, e, nums))

    if not out and headers:
        for idx, m in enumerate(headers):
            e = int(m.group(1))
            mon = _lottologia_month_number(m.group(3))
            if not mon:
                continue
            try:
                rec_day = datetime(int(m.group(4)), mon, int(m.group(2))).strftime("%Y-%m-%d")
            except Exception:
                continue
            if expected_day and rec_day != expected_day:
                continue
            block_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
            block = text[m.end():block_end]
            special = re.search(r"\b(?:Oro|Doppio\s+Oro|Extra)\b", block, re.IGNORECASE)
            if not special:
                continue
            vals = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", block[:special.start()])]
            nums = [n for n in vals if 1 <= n <= 90][:20]
            if len(nums) == 20 and len(set(nums)) == 20:
                out.append((rec_day, e, nums))

    dedup = {}
    for d, e, nums in out:
        dedup[(str(d), int(e))] = (str(d), int(e), list(map(int, nums)))
    return sorted(dedup.values(), key=lambda x: (x[0], x[1]))


# ============================================================
# MULTI-CHANNEL parser — Base + Oro + Doppio Oro + Extra
# ============================================================
def parse_lottologia_multichannel_records(url, expected_day=None):
    """Estrae record completi Lottologia senza modificare i parser Base legacy.

    Output: [{day, draw_id, key, nums[20], oro, doppio_oro, extra[15]}].
    Nel sito Lottologia la sezione "Doppio Oro" mostra Oro + secondo Oro;
    qui `doppio_oro` conserva il secondo numero distinto da `oro`.
    """
    html = _http_get_text(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    header_re = re.compile(
        r"#\s*(\d{1,3})\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\.?\s+(\d{4})\s+(\d{1,2}:\d{2})",
        re.IGNORECASE,
    )
    headers = list(header_re.finditer(text))
    out = []
    for idx, m in enumerate(headers):
        draw_id = int(m.group(1))
        mon = _lottologia_month_number(m.group(3))
        if not mon:
            continue
        try:
            rec_day = datetime(int(m.group(4)), mon, int(m.group(2))).strftime("%Y-%m-%d")
        except Exception:
            continue
        if expected_day and rec_day != expected_day:
            continue
        block_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        block = text[m.end():block_end]
        sec = re.search(
            r"\bNumeri\b(.*?)\bOro\b(.*?)\bDoppio\s+Oro\b(.*?)\bExtra\b(.*)$",
            block, re.IGNORECASE | re.DOTALL,
        )
        if not sec:
            continue
        base_vals = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", sec.group(1))]
        oro_vals = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", sec.group(2))]
        double_vals = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", sec.group(3))]
        extra_vals = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", sec.group(4))]
        nums = [n for n in base_vals if 1 <= n <= 90][:20]
        oro_list = [n for n in oro_vals if 1 <= n <= 90]
        dlist = [n for n in double_vals if 1 <= n <= 90]
        extra = [n for n in extra_vals if 1 <= n <= 90][:15]
        if len(nums) != 20 or len(set(nums)) != 20 or not oro_list:
            continue
        oro = int(oro_list[0])
        # Lottologia visualizza tipicamente: "Doppio Oro <oro> <secondo>".
        distinct = [n for n in dlist if n != oro]
        doppio = int(distinct[0] if distinct else (dlist[-1] if dlist else 0))
        if not (1 <= doppio <= 90):
            continue
        if oro not in nums or doppio not in nums:
            continue
        if len(extra) != 15 or len(set(extra)) != 15 or (set(extra) & set(nums)):
            continue
        out.append({
            "day": rec_day, "draw_id": draw_id, "key": draw_key(rec_day, draw_id),
            "nums": list(map(int, nums)), "oro": oro, "doppio_oro": doppio,
            "extra": list(map(int, extra)), "time": str(m.group(5)),
        })
    dedup = {str(r["key"]): r for r in out}
    return sorted(dedup.values(), key=lambda r: (r["day"], int(r["draw_id"])))


def fetch_multichannel_recent(days=3):
    """Scarica gli ultimi giorni necessari al warmup/live MULTI-CHANNEL."""
    days = max(1, min(5, int(days)))
    merged = {}
    today = now_dt().date()
    for offset in range(days):
        expected = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            rows = parse_lottologia_multichannel_records(
                _lottologia_url_for_offset(offset), expected_day=expected
            )
        except Exception as exc:
            console_log(f"MULTI parser offset={offset} fail | {type(exc).__name__}: {exc}")
            continue
        for row in rows:
            merged[str(row["key"])] = row
    return sorted(merged.values(), key=lambda r: (r["day"], int(r["draw_id"])))


# Live feed health. v20.2 mantiene il feed-fix Lottologia anche per i metodi Base legacy quando
# la vecchia fonte 10elotto5minuti.com e' indietro o non disponibile.
LIVE_FEED_LAST_SOURCE = "-"
LIVE_FEED_LAST_KEY = "-"
LIVE_FEED_LAST_PRIMARY_KEY = "-"
LIVE_FEED_LAST_LOTTOLOGIA_KEY = "-"

def _latest_base_key(rows):
    good=[]
    for row in rows or []:
        try:
            d,e,nums=row
            if len(nums)==20 and len(set(map(int,nums)))==20:
                good.append((str(d),int(e)))
        except Exception:
            pass
    if not good:
        return None
    d,e=max(good,key=lambda x:(x[0],x[1]))
    return draw_key(d,e)

def fetch_live_bundle_today():
    """Ritorna (base_rows, multi_rows, source).

    Preferisce la sorgente con il draw-id piu' recente. Lottologia e' la fonte
    completa Base/Oro/Doppio/Extra; la vecchia fonte resta come fallback.
    """
    global LIVE_FEED_LAST_SOURCE, LIVE_FEED_LAST_KEY
    global LIVE_FEED_LAST_PRIMARY_KEY, LIVE_FEED_LAST_LOTTOLOGIA_KEY

    multi_rows=[]
    try:
        multi_rows=fetch_multichannel_recent(days=1)
    except Exception as exc:
        console_log(f"LIVE Lottologia fail | {type(exc).__name__}: {exc}")
    lott_base=[(str(r["day"]),int(r["draw_id"]),list(map(int,r["nums"]))) for r in multi_rows]

    primary=[]
    try:
        primary=parse_site_today()
    except Exception as exc:
        console_log(f"LIVE primary fail | {type(exc).__name__}: {exc}")

    lk=_latest_base_key(lott_base)
    pk=_latest_base_key(primary)
    LIVE_FEED_LAST_LOTTOLOGIA_KEY=lk or "-"
    LIVE_FEED_LAST_PRIMARY_KEY=pk or "-"

    # Controllo di coerenza sulle estrazioni comuni piu' recenti.
    if lott_base and primary:
        lm={(d,int(e)):set(map(int,n)) for d,e,n in lott_base}
        pm={(d,int(e)):set(map(int,n)) for d,e,n in primary}
        common=sorted(set(lm).intersection(pm))[-5:]
        conflicts=[k for k in common if lm[k] != pm[k]]
        if conflicts:
            console_log(f"LIVE FEED WARNING | conflitti Base su {conflicts}")

    def ord_key(k):
        return _verifica_order(k) or (-1,-1)

    if lott_base and (not primary or ord_key(lk) >= ord_key(pk)):
        chosen=lott_base; source="Lottologia"
    elif primary:
        chosen=primary; source="10elotto5minuti.com"
    else:
        chosen=[]; source="NESSUNA"

    LIVE_FEED_LAST_SOURCE=source
    LIVE_FEED_LAST_KEY=_latest_base_key(chosen) or "-"
    return chosen, multi_rows, source


def _annual_archive_by_day(target_days):
    target_days = {str(x) for x in (target_days or [])}
    if not target_days:
        return {}
    try:
        rows = parse_site_records(URL_YEAR_ARCHIVE, expected_day=None)
    except Exception:
        return {}
    out = {}
    for d, e, nums in rows:
        if d in target_days:
            out.setdefault(d, []).append((d, e, nums))
    for d in out:
        out[d].sort(key=lambda x: x[1])
    return out


def _normalize_day_rows(rows, expected_day):
    """Normalizza una sorgente: un solo record per numero estrazione."""
    out = {}
    for row in rows or []:
        try:
            d, e, nums = row
            d = str(d)
            e = int(e)
            clean = list(map(int, nums))
        except Exception:
            continue
        if d != str(expected_day):
            continue
        if e < 1 or e > WARMUP_FULL_DAY_DRAWS:
            continue
        if len(clean) != 20 or len(set(clean)) != 20 or any(n < 1 or n > 90 for n in clean):
            continue
        out[e] = (d, e, clean)
    return out


def _merge_day_sources(expected_day, source_rows):
    """
    Unisce piu' fonti SENZA sovrascrivere in silenzio.

    - i record mancanti vengono integrati dalla fonte successiva;
    - se due fonti danno numeri diversi per lo stesso id, il conflitto viene
      segnalato e il giorno non puo' essere considerato affidabile;
    - l'ordine dei 20 numeri non conta: per il motore conta l'insieme estratto.
    """
    merged = {}
    owner = {}
    conflicts = []
    added_by_source = {}
    fetched_by_source = {}

    for source_name, rows in source_rows:
        clean_map = _normalize_day_rows(rows, expected_day)
        fetched_by_source[source_name] = len(clean_map)
        added = 0
        for e in sorted(clean_map):
            row = clean_map[e]
            if e not in merged:
                merged[e] = row
                owner[e] = source_name
                added += 1
                continue

            old_nums = tuple(sorted(merged[e][2]))
            new_nums = tuple(sorted(row[2]))
            if old_nums != new_nums:
                conflicts.append({
                    "draw": int(e),
                    "source_a": owner.get(e, "?"),
                    "source_b": source_name,
                })
        added_by_source[source_name] = added_by_source.get(source_name, 0) + added

    ordered = [merged[e] for e in sorted(merged)]
    return ordered, added_by_source, fetched_by_source, conflicts


def _day_continuity_info(rows, full_day=False):
    ids = sorted({int(e) for _, e, _ in (rows or [])})
    if not ids:
        return {
            "count": 0,
            "min_id": None,
            "max_id": None,
            "missing_ids": [],
            "continuous": True,
            "complete": False,
        }

    if full_day:
        expected = set(range(1, WARMUP_FULL_DAY_DRAWS + 1))
        missing = sorted(expected - set(ids))
        extra = sorted(set(ids) - expected)
        continuous = not missing and not extra and len(ids) == WARMUP_FULL_DAY_DRAWS
        complete = continuous
    else:
        # Per il giorno corrente non pretendiamo 288 perche' e' ancora in corso,
        # ma non accettiamo buchi interni tra #1 e l'ultimo id disponibile.
        expected = set(range(1, max(ids) + 1))
        missing = sorted(expected - set(ids))
        continuous = not missing and ids[0] == 1
        complete = continuous

    return {
        "count": len(ids),
        "min_id": ids[0],
        "max_id": ids[-1],
        "missing_ids": missing,
        "continuous": bool(continuous),
        "complete": bool(complete),
    }


def _source_label(added_by_source, fetched_by_source):
    parts = []
    for name in ("10elotto5minuti", "lottologia", "10elotto5minuti-year"):
        fetched = int((fetched_by_source or {}).get(name, 0) or 0)
        added = int((added_by_source or {}).get(name, 0) or 0)
        if fetched or added:
            if fetched == added:
                parts.append(f"{name}:{added}")
            else:
                parts.append(f"{name}:{added}aggiunte/{fetched}lette")
    for name in sorted(set(fetched_by_source or {}) - {"10elotto5minuti", "lottologia", "10elotto5minuti-year"}):
        fetched = int((fetched_by_source or {}).get(name, 0) or 0)
        added = int((added_by_source or {}).get(name, 0) or 0)
        if fetched or added:
            parts.append(f"{name}:{added}aggiunte/{fetched}lette")
    return "+".join(parts) if parts else "MISSING"


def _warmup_integrity_problems(summary, today_iso=None):
    today_iso = str(today_iso or now_dt().date().isoformat())
    problems = []
    for x in summary or []:
        day = str(x.get("day"))
        conflicts = int(x.get("conflicts", 0) or 0)
        if conflicts:
            problems.append(f"{day}: {conflicts} conflitti tra fonti")
            continue

        if day < today_iso and WARMUP_REQUIRE_COMPLETE_PAST_DAYS:
            if not bool(x.get("complete", False)):
                missing = list(x.get("missing_ids", []) or [])
                tail = ",".join(map(str, missing[:12]))
                more = "..." if len(missing) > 12 else ""
                problems.append(
                    f"{day}: giorno concluso incompleto "
                    f"({int(x.get('draws', 0) or 0)}/{WARMUP_FULL_DAY_DRAWS}; "
                    f"mancano [{tail}{more}])"
                )
        elif day == today_iso and int(x.get("draws", 0) or 0) > 0:
            if not bool(x.get("continuous", False)):
                missing = list(x.get("missing_ids", []) or [])
                tail = ",".join(map(str, missing[:12]))
                more = "..." if len(missing) > 12 else ""
                problems.append(f"{day}: buchi interni nel giorno corrente [{tail}{more}]")
    return problems


def _select_latest_contiguous_warmup(records, summary, today_iso=None):
    """
    Usa soltanto il segmento cronologico continuo piu' recente che arriva fino a oggi.

    Se un vecchio giorno concluso e' incompleto/conflittuale NON uniamo le estrazioni
    prima e dopo il buco: tutto cio' che precede (e include) l'ultimo giorno rotto
    viene scartato dal warmup. In questo modo il motore non inventa continuita'.

    Esempio:
      05 OK, 06 OK, 07 INCOMPLETO, 08 OK, 09 OK, 10 OK, 11 LIVE
      -> warmup effettivo = 08 + 09 + 10 + 11.
    """
    today_iso = str(today_iso or now_dt().date().isoformat())
    summary = [dict(x) for x in (summary or [])]

    bad_past_days = []
    for x in summary:
        day = str(x.get("day"))
        if day >= today_iso:
            continue
        conflicts = int(x.get("conflicts", 0) or 0)
        if conflicts or (WARMUP_REQUIRE_COMPLETE_PAST_DAYS and not bool(x.get("complete", False))):
            bad_past_days.append(day)

    cutoff_day = max(bad_past_days) if bad_past_days else None
    for x in summary:
        day = str(x.get("day"))
        x["used_for_warmup"] = not (cutoff_day is not None and day <= cutoff_day)

    used_summary = [x for x in summary if x.get("used_for_warmup", True)]
    used_days = {str(x.get("day")) for x in used_summary}
    selected = [(d, e, nums) for d, e, nums in (records or []) if str(d) in used_days]

    # Sul segmento che useremo l'integrita' resta obbligatoria. In particolare,
    # un buco interno nel giorno corrente non viene mai ignorato.
    problems = _warmup_integrity_problems(used_summary, today_iso=today_iso)

    note = None
    dropped_days = []
    if cutoff_day is not None:
        dropped_days = [str(x.get("day")) for x in summary if not x.get("used_for_warmup", True)]
        first_used = min(used_days) if used_days else None
        if first_used:
            note = (
                f"ultimo giorno storico non integro = {cutoff_day}; "
                f"warmup ricostruito senza attraversare il buco, da {first_used} in poi"
            )
        else:
            note = f"ultimo giorno storico non integro = {cutoff_day}; nessun segmento successivo disponibile"

    return selected, summary, {
        "problems": problems,
        "cutoff_day": cutoff_day,
        "dropped_days": dropped_days,
        "note": note,
    }


def format_warmup_sources(summary):
    parts = []
    for x in summary or []:
        day = x.get("day", "?")
        draws = int(x.get("draws", 0) or 0)
        src = x.get("source", "?")
        if x.get("used_for_warmup") is False:
            status = "SCARTATO"
        elif x.get("is_today"):
            if draws <= 0:
                status = "VUOTO"
            else:
                status = "LIVE" if x.get("continuous") else "INCOMPLETO"
        else:
            status = "OK" if x.get("complete") else "INCOMPLETO"
        parts.append(f"{day}={draws}[{src}|{status}]")
    return ", ".join(parts)


def fetch_warmup_records(days=WARMUP_DAYS):
    """
    Scarica gli ultimi N giorni in ordine cronologico.

    Regola di integrita' v4:
      • i giorni gia' conclusi devono coprire #1..#288 senza buchi;
      • se la prima fonte e' incompleta viene provata la fonte alternativa;
      • se ancora incompleto viene usato l'archivio annuale per integrare;
      • eventuali conflitti sullo stesso numero estrazione vengono segnalati;
      • oggi puo' essere parziale, ma non puo' avere buchi interni #1..#max.
    """
    today_date = now_dt().date()
    primary_by_offset = {0: URL, 1: URL_YESTERDAY, 2: URL_DAY_BEFORE_YESTERDAY}
    day_candidates = {}

    # Prima passata: fonte principale + Lottologia quando serve.
    for offset in range(max(1, int(days))):
        expected_day = (today_date - timedelta(days=offset)).isoformat()
        is_today = offset == 0
        candidates = []

        primary_rows = []
        if offset in primary_by_offset:
            try:
                primary_rows = parse_site_records(primary_by_offset[offset], expected_day=expected_day)
            except Exception:
                primary_rows = []
            candidates.append(("10elotto5minuti", primary_rows))

        primary_info = _day_continuity_info(primary_rows, full_day=not is_today)
        need_alt = (not primary_rows) or (not is_today and not primary_info["complete"]) or (is_today and not primary_info["continuous"])

        # Per gli offset >2 Lottologia e' la prima fonte storica disponibile.
        if offset > 2 or need_alt:
            try:
                lotto_rows = parse_lottologia_records(
                    _lottologia_url_for_offset(offset), expected_day=expected_day
                )
            except Exception:
                lotto_rows = []
            candidates.append(("lottologia", lotto_rows))

        day_candidates[expected_day] = {
            "offset": offset,
            "is_today": is_today,
            "candidates": candidates,
        }

    # Capisco quali giorni conclusi sono ancora incompleti dopo le prime fonti.
    need_annual = []
    for expected_day, info in day_candidates.items():
        rows, _, _, conflicts = _merge_day_sources(expected_day, info["candidates"])
        check = _day_continuity_info(rows, full_day=not info["is_today"])
        if (not info["is_today"]) and (not check["complete"] or conflicts):
            need_annual.append(expected_day)

    annual = _annual_archive_by_day(need_annual) if need_annual else {}

    records = []
    summary = []
    for expected_day, info in day_candidates.items():
        candidates = list(info["candidates"])
        if expected_day in need_annual:
            candidates.append(("10elotto5minuti-year", annual.get(expected_day, [])))

        merged, added_by, fetched_by, conflicts = _merge_day_sources(expected_day, candidates)
        check = _day_continuity_info(merged, full_day=not info["is_today"])
        records.extend(merged)

        summary.append({
            "day": expected_day,
            "draws": len(merged),
            "source": _source_label(added_by, fetched_by),
            "is_today": bool(info["is_today"]),
            "continuous": bool(check["continuous"]),
            "complete": bool(check["complete"]),
            "min_id": check["min_id"],
            "max_id": check["max_id"],
            "missing_ids": list(check["missing_ids"]),
            "conflicts": len(conflicts),
            "conflict_details": conflicts[:10],
        })

    dedup = {}
    for d, e, nums in records:
        if len(nums) == 20 and len(set(nums)) == 20:
            dedup[(str(d), int(e))] = (str(d), int(e), list(map(int, nums)))

    ordered = sorted(dedup.values(), key=lambda x: (x[0], x[1]))
    summary.sort(key=lambda x: x["day"])
    return ordered, summary


def _git_clean_text(text, limit=900):
    txt = str(text or "").strip()
    # Non mostrare mai eventuali credenziali presenti in un URL remoto.
    txt = re.sub(r"https://[^\s/@]+@github\.com", "https://***@github.com", txt, flags=re.I)
    txt = re.sub(r"gh[ps]_[A-Za-z0-9_]+", "***", txt)
    if len(txt) > limit:
        txt = txt[-limit:]
    return txt


def _git_run(args, cwd, timeout=45):
    try:
        r = subprocess.run(
            ["git", *args], cwd=cwd, text=True, capture_output=True,
            timeout=timeout, check=False,
        )
        return r.returncode, _git_clean_text(r.stdout), _git_clean_text(r.stderr)
    except Exception as exc:
        return 999, "", f"{type(exc).__name__}: {exc}"


def _git_status(ok, action, detail="", branch="", commit=""):
    return {
        "ok": bool(ok),
        "action": str(action),
        "detail": str(detail or ""),
        "branch": str(branch or ""),
        "commit": str(commit or ""),
        "at": now_txt(),
    }


def git_commit_state_if_needed(force=False):
    """Salva STATE_FILE nel repository e verifica che il commit sia sul remote.

    Importante: un commit locale NON viene considerato successo. Il risultato e' OK
    solo quando `origin/<branch>` punta allo stesso commit locale (o lo contiene).
    Se un push precedente era fallito, la funzione ritenta anche quando il file non
    ha nuove modifiche, perche' controlla gli eventuali commit locali non pushati.
    """
    global _LAST_GIT_COMMIT_TS

    if not PERSIST_GIT_STATE:
        st = _git_status(True, "disabled", "PERSIST_GIT_STATE=0")
        console_log("STATE GIT DISABILITATO")
        return st

    now = time.time()
    if not force and (now - _LAST_GIT_COMMIT_TS) < GIT_COMMIT_MIN_SECONDS:
        return _git_status(True, "throttled", f"prossimo controllo tra {int(GIT_COMMIT_MIN_SECONDS - (now - _LAST_GIT_COMMIT_TS))}s")

    if not os.path.exists(STATE_FILE):
        st = _git_status(False, "missing-state", f"file non trovato: {STATE_FILE}")
        console_log(f"STATE PUSH FAIL | {st['detail']}")
        return st

    rc, root_out, root_err = _git_run(["rev-parse", "--show-toplevel"], BASE_DIR)
    if rc != 0 or not root_out:
        st = _git_status(False, "no-repo", root_err or root_out or "repository Git non trovato")
        console_log(f"STATE PUSH FAIL | {st['detail']}")
        return st
    root = root_out.splitlines()[-1].strip()

    branch = os.getenv("GITHUB_REF_NAME", "").strip()
    if not branch or os.getenv("GITHUB_REF_TYPE", "branch") not in {"", "branch"}:
        rc, bout, _ = _git_run(["rev-parse", "--abbrev-ref", "HEAD"], root)
        branch = bout.strip() if rc == 0 else ""
    if not branch or branch == "HEAD":
        branch = os.getenv("STATE_GIT_BRANCH", "main").strip() or "main"

    # GitHub Actions non garantisce che user.name/email siano configurati.
    _git_run(["config", "user.name", "github-actions[bot]"], root)
    _git_run(["config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], root)

    rel = os.path.relpath(STATE_FILE, root)
    if rel.startswith(".."):
        st = _git_status(False, "outside-repo", f"state fuori dal repository: {STATE_FILE}", branch=branch)
        console_log(f"STATE PUSH FAIL | {st['detail']}")
        return st

    # -f rende persistibile lo state anche se per errore e' presente nel .gitignore.
    rc, _, err = _git_run(["add", "-f", "--", rel], root)
    if rc != 0:
        st = _git_status(False, "git-add-failed", err, branch=branch)
        console_log(f"STATE PUSH FAIL | git add | {err}")
        return st

    rc_diff, _, _ = _git_run(["diff", "--cached", "--quiet", "--", rel], root)
    committed_now = False
    if rc_diff == 1:
        rc, out, err = _git_run(["commit", "-m", "state: 10elotto engine only"], root)
        if rc != 0:
            st = _git_status(False, "commit-failed", err or out, branch=branch)
            console_log(f"STATE PUSH FAIL | git commit | {st['detail']}")
            return st
        committed_now = True
        console_log("STATE COMMIT OK")
    elif rc_diff not in {0, 1}:
        st = _git_status(False, "diff-failed", "git diff --cached fallito", branch=branch)
        console_log("STATE PUSH FAIL | git diff --cached")
        return st

    # Aggiorna la vista del remote. Se il branch remoto e' avanzato, rebase prima del push.
    rc_fetch, _, err_fetch = _git_run(["fetch", "origin", branch, "--prune"], root, timeout=60)
    if rc_fetch != 0:
        st = _git_status(False, "fetch-failed", err_fetch, branch=branch)
        console_log(f"STATE PUSH FAIL | git fetch origin {branch} | {err_fetch}")
        return st

    rc, counts, err = _git_run(["rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"], root)
    if rc != 0:
        st = _git_status(False, "rev-list-failed", err or counts, branch=branch)
        console_log(f"STATE PUSH FAIL | confronto remote | {st['detail']}")
        return st
    try:
        behind, ahead = [int(x) for x in counts.split()[:2]]
    except Exception:
        st = _git_status(False, "rev-list-parse", f"output inatteso: {counts}", branch=branch)
        console_log(f"STATE PUSH FAIL | {st['detail']}")
        return st

    if behind > 0:
        rc, out, err = _git_run(["rebase", f"origin/{branch}"], root, timeout=60)
        if rc != 0:
            _git_run(["rebase", "--abort"], root)
            st = _git_status(False, "rebase-failed", err or out, branch=branch)
            console_log(f"STATE PUSH FAIL | rebase | {st['detail']}")
            return st
        rc, counts, err = _git_run(["rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"], root)
        if rc != 0:
            st = _git_status(False, "post-rebase-check-failed", err or counts, branch=branch)
            console_log(f"STATE PUSH FAIL | post-rebase | {st['detail']}")
            return st
        behind, ahead = [int(x) for x in counts.split()[:2]]

    if ahead > 0:
        rc, out, err = _git_run(["push", "origin", f"HEAD:{branch}"], root, timeout=90)
        if rc != 0:
            st = _git_status(False, "push-failed", err or out, branch=branch)
            console_log(f"STATE PUSH FAIL | git push | {st['detail']}")
            return st

    # Verifica indipendente del commit remoto.
    rc, local_head, err = _git_run(["rev-parse", "HEAD"], root)
    if rc != 0:
        st = _git_status(False, "local-head-failed", err, branch=branch)
        console_log(f"STATE PUSH FAIL | {st['detail']}")
        return st
    local_head = local_head.strip().splitlines()[-1]

    rc, remote_line, err = _git_run(["ls-remote", "origin", f"refs/heads/{branch}"], root, timeout=60)
    remote_head = remote_line.split()[0] if rc == 0 and remote_line.split() else ""
    if rc != 0 or remote_head != local_head:
        st = _git_status(
            False, "remote-verify-failed",
            f"local={local_head[:10]} remote={(remote_head or '?')[:10]} | {err}",
            branch=branch, commit=local_head,
        )
        console_log(f"STATE PUSH FAIL | verifica remote | {st['detail']}")
        return st

    _LAST_GIT_COMMIT_TS = now
    action = "committed+pushed" if committed_now else ("pushed-pending" if ahead > 0 else "already-synced")
    st = _git_status(True, action, "remote verificato", branch=branch, commit=local_head)
    console_log(f"STATE PUSH OK | branch={branch} | commit={local_head[:10]} | action={action}")
    return st


def acquire_single_instance_lock():
    global _LOCK_HANDLE
    _LOCK_HANDLE = open(LOCK_FILE, "a+", encoding="utf-8")
    if fcntl is not None:
        try:
            fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("⚠️ Un'altra istanza di questo bot e' gia' attiva.")
            sys.exit(1)

    _LOCK_HANDLE.seek(0)
    _LOCK_HANDLE.truncate()
    _LOCK_HANDLE.write(str(os.getpid()))
    _LOCK_HANDLE.flush()

    def cleanup_lock():
        try:
            if fcntl is not None:
                fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_UN)
            _LOCK_HANDLE.close()
        except Exception:
            pass

    atexit.register(cleanup_lock)


# ============================================================
# ENGINE ONLY
# ============================================================

# ============================================================
# DUAL TARGET ENGINE v1 — LABORATORIO SHADOW H1, INDEPENDENTE
# Le features e la coppia sono congelate a t; settlement solo a t+1.
# L'indice di ordinamento non e' una probabilita' calibrata.
# ============================================================

DUAL_VERSION = 1
DUAL_PRETRAIN_FILE = os.path.join(BASE_DIR, "dual_target_pretrain.json")
DUAL_PRETRAIN_PRIOR_CAP = 400.0  # massimo 400 osservazioni per esperto; LIVE prevale nel tempo
DUAL_MIN_HISTORY = max(40, int(os.getenv("DUAL_MIN_HISTORY", "120")))
DUAL_RECORD_MAX = max(500, int(os.getenv("DUAL_RECORD_MAX", "5000")))
DUAL_NOTIFY = os.getenv("DUAL_NOTIFY", "0") == "1"  # default silenzioso: comando /dual
DUAL_P0 = 20.0 / 90.0
DUAL_PAIR_P0 = (20.0 * 19.0) / (90.0 * 89.0)
DUAL_AT_LEAST_ONE_P0 = 1.0 - (70.0 * 69.0) / (90.0 * 89.0)
DUAL_EXPERTS = ("hot8", "hot40", "hot160", "accel", "transition", "gap", "sosia", "engine")


class DualTargetLab:
    """Misuratore forward, non gestisce puntate e non interviene nei motori preesistenti."""

    def __init__(self):
        self.pending = None
        self.records = []
        self.totals = {"evaluated": 0, "skipped": 0, "any": 0, "both": 0,
                       "hits": 0, "random_any": 0, "random_both": 0,
                       "random_hits": 0, "paired_wins": 0, "paired_losses": 0,
                       "paired_ties": 0}
        self.experts = {name: {"n": 0, "hits": 0} for name in DUAL_EXPERTS}
        self.last_result = None
        self.pretrain = None  # training storico separato, MAI confluito nei contatori LIVE

    def load_pretrain(self, path=None):
        """Legge un prior storico versionato, senza cambiare pending o risultati live."""
        path = path or DUAL_PRETRAIN_FILE
        if not os.path.isfile(path):
            return False
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("schema") != "dual-target-pretrain-v1":
                return False
            exper = data.get("experts")
            if not isinstance(exper, dict) or not isinstance(data.get("source_sha256"), str):
                return False
            parsed = {}
            for name in ("hot8", "hot40", "hot160", "accel", "transition", "gap"):
                row = exper.get(name)
                if not isinstance(row, dict):
                    return False
                n, hits = int(row["n"]), int(row["hits"])
                if n <= 0 or hits < 0 or hits > n:
                    return False
                parsed[name] = {"n": n, "hits": hits}
            self.pretrain = {"experts": parsed, "source_sha256": data["source_sha256"],
                             "train_rows": int(data.get("train_rows", 0)),
                             "validation": data.get("validation", {}), "test": data.get("test", {})}
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    @staticmethod
    def _valid_pair(obj):
        return (isinstance(obj, (list, tuple)) and len(obj) == 2 and
                all(type(n) is int and 1 <= n <= 90 for n in obj) and obj[0] != obj[1])

    @staticmethod
    def _clip(x, low=-3.0, high=3.0):
        return max(low, min(high, float(x)))

    @staticmethod
    def _wilson(hits, trials, z=1.96):
        if trials <= 0:
            return (0.0, 1.0)
        p = hits / trials
        d = 1.0 + z * z / trials
        c = (p + z * z / (2.0 * trials)) / d
        r = z * math.sqrt(p * (1.0 - p) / trials + z*z / (4.0*trials*trials)) / d
        return max(0.0, c-r), min(1.0, c+r)

    @staticmethod
    def _hash_tie(key, name, value):
        h = hashlib.sha256(f"DUAL_V1|{key}|{name}|{value}".encode()).digest()
        return int.from_bytes(h[:8], "big")

    def load(self, raw):
        if not isinstance(raw, dict) or raw.get("version") != DUAL_VERSION:
            return
        totals = raw.get("totals", {})
        if isinstance(totals, dict):
            for k in self.totals:
                try:
                    self.totals[k] = max(0, int(totals.get(k, 0)))
                except (TypeError, ValueError, OverflowError):
                    pass
        expert_raw = raw.get("experts", {})
        if isinstance(expert_raw, dict):
            for name in DUAL_EXPERTS:
                row = expert_raw.get(name, {})
                if isinstance(row, dict):
                    try:
                        self.experts[name] = {"n": max(0, int(row.get("n", 0))),
                                              "hits": max(0, int(row.get("hits", 0)))}
                    except (TypeError, ValueError, OverflowError):
                        pass
        rows = raw.get("records", [])
        if isinstance(rows, list):
            self.records = [r for r in rows if isinstance(r, dict) and
                            isinstance(r.get("key"), str) and
                            self._valid_pair(r.get("pair"))][-DUAL_RECORD_MAX:]
        p = raw.get("pending")
        if (isinstance(p, dict) and isinstance(p.get("from_key"), str) and
                self._valid_pair(p.get("pair")) and self._valid_pair(p.get("random_pair"))):
            self.pending = p
        bootstrap = raw.get("history_bootstrap")
        if (isinstance(bootstrap, dict) and bootstrap.get("kind") == "state-history-bootstrap-v1"
                and isinstance(bootstrap.get("experts"), dict)):
            try:
                for name in ("hot8", "hot40", "hot160", "accel", "transition", "gap"):
                    row = bootstrap["experts"][name]
                    n, hits = int(row["n"]), int(row["hits"])
                    if n <= 0 or not 0 <= hits <= n:
                        raise ValueError(name)
                self.pretrain = bootstrap
            except (KeyError, ValueError, TypeError):
                pass

    def bootstrap_from_history(self, history):
        """Un solo warmstart da storico del vecchio state; nessun backfill nei contatori LIVE."""
        if self.pretrain is not None or not isinstance(history, list) or len(history) < 520:
            return False
        rows = []
        try:
            for r in history[-800:]:
                key, nums = str(r["key"]), list(map(int, r["nums"]))
                if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 90 for n in nums):
                    return False
                day, index = key.rsplit("#", 1)
                datetime.fromisoformat(day)
                int(index)
                rows.append({"key": key, "nums": nums})
        except (KeyError, ValueError, TypeError, AttributeError):
            return False
        # Guardia sui dati del vecchio state: scarta distribuzioni fortemente
        # anomale (es. il file esterno che contiene quasi zero occorrenze del 90).
        qc = rows[-min(500, len(rows)):]
        qc_counts = Counter(n for record in qc for n in record["nums"])
        if (min(qc_counts.get(n, 0) for n in range(1,91)) < len(qc)*0.08
                or max(qc_counts.get(n,0) for n in range(1,91)) > len(qc)*0.38):
            return False
        names = ("hot8", "hot40", "hot160", "accel", "transition", "gap")
        # Usiamo una copia indipendente, MAI engine_history originale o i vecchi pending.
        class Replay:
            engine_pending = None
            sosiapattern_pending = None
            engine_history = []
        replay = Replay()
        train = {name: {"n": 0, "hits": 0} for name in names}
        holdout = {"evaluated": 0, "any": 0, "random_any": 0}
        first_holdout = len(rows) - 80
        for i in range(321, first_holdout):
            key = rows[i-1]["key"]
            current_day, current_index = rows[i]["key"].rsplit("#",1)
            if not sim_draw_is_consecutive(key, current_day, int(current_index)):
                continue  # gap: nessun successo o insuccesso inventato
            replay.engine_history = rows[max(0,i-321):i]
            feats = self._features(replay, key)
            if not feats:
                continue
            actual = set(rows[i]["nums"])
            for name in names:
                vals = feats[name]
                pair = sorted(range(1,91), key=lambda n: (-vals[n], self._hash_tie(key,name,n)))[:2]
                train[name]["n"] += 2
                train[name]["hits"] += len(actual.intersection(pair))
        if min(x["n"] for x in train.values()) < 120:
            return False
        # Il blocco finale non ricalibra i pesi; serve solo come controllo separato.
        self.pretrain = {"kind": "state-history-bootstrap-v1", "experts": train,
            "train_rows": train[names[0]]["n"]//2, "test": holdout,
            "source_start": rows[0]["key"], "source_end": rows[-1]["key"]}
        old_pending = self.pending
        try:
            for i in range(first_holdout, len(rows)):
                key = rows[i-1]["key"]
                current_day, current_index = rows[i]["key"].rsplit("#",1)
                if not sim_draw_is_consecutive(key, current_day, int(current_index)):
                    continue
                replay.engine_history = rows[max(0,i-321):i]
                self.pending = None
                p = self.arm(replay,key)
                if not p:
                    continue
                actual = set(rows[i]["nums"])
                holdout["evaluated"] += 1
                holdout["any"] += bool(actual.intersection(p["pair"]))
                holdout["random_any"] += bool(actual.intersection(p["random_pair"]))
        finally:
            self.pending = old_pending
        return True

    def dump(self):
        return {"version": DUAL_VERSION, "pending": self.pending,
                "totals": self.totals, "experts": self.experts,
                "records": self.records[-DUAL_RECORD_MAX:],
                "history_bootstrap": self.pretrain if (self.pretrain or {}).get("kind") == "state-history-bootstrap-v1" else None}

    def _features(self, engine, current_key):
        """Richiede storia che termina in current_key. Nessuna estrazione futura."""
        hist = engine.engine_history
        if len(hist) < DUAL_MIN_HISTORY or str(hist[-1].get("key")) != str(current_key):
            return None
        rows = [set(map(int, r["nums"])) for r in hist]
        last = rows[-1]
        names = {}

        def recent_z(window):
            rr = rows[-window:]
            cnt = Counter(n for s in rr for n in s)
            sigma = math.sqrt(len(rr) * DUAL_P0 * (1.0-DUAL_P0))
            return {n: self._clip((cnt[n] - len(rr)*DUAL_P0)/max(1.0,sigma))
                    for n in range(1,91)}

        for w, name in ((8,"hot8"),(40,"hot40"),(160,"hot160")):
            names[name] = recent_z(w)
        names["accel"] = {n: self._clip((names["hot8"][n] - names["hot160"][n])*0.7)
                          for n in range(1,91)}

        # Transition ha un prior uniforme esplicito; usa coppie (stato_i, draw_i+1)
        # fino al SOLO draw corrente, senza usare il prossimo draw da prevedere.
        response = Counter()
        support = 0.0
        old = rows[-321:]
        for i in range(len(old)-1):
            overlap = len(old[i] & last)
            if overlap < 3:
                continue
            weight = overlap / 20.0
            support += weight
            for n in old[i+1]:
                response[n] += weight
        sigma = math.sqrt(max(1.0,support) * DUAL_P0 * (1-DUAL_P0))
        names["transition"] = {n: self._clip((response[n] - support*DUAL_P0) / sigma)
                                for n in range(1,91)}

        # Lag e ripetizioni sono features esplorative: l'apprendimento forward
        # puo' ridurne il peso, NON implicano che un ritardatario sia 'dovuto'.
        gap = {}
        for n in range(1,91):
            g = next((i for i, s in enumerate(reversed(rows[-75:])) if n in s), 75)
            gap[n] = self._clip((min(g, 18) - 3.5)/6.0)
        names["gap"] = gap
        sosia = engine.sosiapattern_pending
        if isinstance(sosia, dict) and str(sosia.get("from_key")) == str(current_key):
            ranked = sosia.get("rank20", [])
            if engine._sosia_valid20(ranked):
                positions = {int(n): i for i,n in enumerate(ranked)}
                names["sosia"] = {n: (1.7 - positions[n]/10.0) if n in positions else -0.38
                                  for n in range(1,91)}
        # Il vecchio ENGINE resta una fonte di evidenza, non viene riaddestrato.
        ep = engine.engine_pending
        if (isinstance(ep, dict) and ep.get("accepted") and
                str(ep.get("signal_from_key")) == str(current_key) and ep.get("top1")):
            top = int(ep["top1"])
            names["engine"] = {n: 2.5 if n == top else 0.0 for n in range(1,91)}
        return names

    def _weights(self, available):
        """Shrink forte dei rendimenti PRECEDENTI, senza ottimizzare sul futuro."""
        raw = {}
        for name in available:
            r = self.experts[name]
            n, hits = int(r["n"]), int(r["hits"])
            historic = (self.pretrain or {}).get("experts", {}).get(name, {})
            hist_n = max(0, int(historic.get("n", 0)))
            hist_hits = max(0, int(historic.get("hits", 0)))
            # Storico come prior leggero (n NON aggiunto alle statistiche LIVE).
            # SOSIA/ENGINE: senza replay dei loro segnali originali, nessun prior sintetico.
            hist_strength = min(DUAL_PRETRAIN_PRIOR_CAP, hist_n)
            hist_rate = hist_hits / hist_n if hist_n else DUAL_P0
            posterior = (hits + 200.0*DUAL_P0 + hist_strength*hist_rate) / (n+200.0+hist_strength)
            raw[name] = max(0.65, min(1.35, 1.0+3.0*(posterior-DUAL_P0)))
        scale = sum(raw.values()) or 1.0
        return {name: value/scale for name,value in raw.items()}

    def arm(self, engine, current_key):
        if self.pending is not None:
            # Non sovrascrivere mai una previsione precedente non ancora valutata.
            return self.pending if self.pending.get("from_key") == current_key else None
        feats = self._features(engine, current_key)
        if not feats:
            return None
        weights = self._weights(feats)
        combined = {n: sum(weights[name]*f[n] for name,f in feats.items())
                    for n in range(1,91)}
        # Baseline H1 esatta: p >=1 di due numeri distinti = 39.70%.
        # Scelta sulla totalita' delle 4005 coppie, con debole penalita' per
        # co-occorrenze storiche sopra il prior teorico. Non e' probabilita' reale.
        recent = [set(map(int,r["nums"])) for r in engine.engine_history[-250:]]
        co = Counter()
        for nums in recent:
            for pair in combinations(sorted(nums), 2):
                co[pair] += 1
        best = None
        best_score = -float("inf")
        for a in range(1,90):
            for b in range(a+1,91):
                joint = (co[(a,b)] + 160.0*DUAL_PAIR_P0) / (len(recent)+160.0)
                # Non interpretare come p stimata, e' SOLO indice ordinante.
                score = combined[a] + combined[b] - 5.0*(joint-DUAL_PAIR_P0)
                tie = self._hash_tie(current_key, "pair", f"{a}-{b}")
                if score > best_score + 1e-12 or (abs(score-best_score) <= 1e-12 and
                                                   (best is None or tie < best[2])):
                    best, best_score = (a,b,tie), score
        pair = [best[0], best[1]]
        # Il controllo casuale e' congelato allo stesso tempo, ma indipendente
        # da scores/risultati. Seed riproducibile per audit dopo il riavvio.
        rand = sorted(range(1,91), key=lambda n: self._hash_tie(current_key,"blind",n))[:2]
        expert_pairs = {}
        for name, vals in feats.items():
            expert_pairs[name] = sorted(range(1,91),
                key=lambda n: (-vals[n],self._hash_tie(current_key,name,n)))[:2]
        self.pending = {"from_key": str(current_key), "pair": pair,
                        "random_pair": rand, "experts": expert_pairs,
                        "weights": {k: round(v,6) for k,v in weights.items()},
                        "score_index": round(best_score,6),
                        "rank20_sosia": (list(engine.sosiapattern_pending.get("rank20",[]))
                            if isinstance(engine.sosiapattern_pending,dict) and
                            engine.sosiapattern_pending.get("from_key") == current_key else []),
                        "created_at": now_txt()}
        return self.pending

    def settle(self, day, e, nums):
        p = self.pending
        if not p:
            return None
        # Settlement prima di armare: il vecchio pending non puo' essere rimpiazzato.
        self.pending = None
        key = draw_key(day,e)
        if not sim_draw_is_consecutive(p["from_key"], day, e):
            self.totals["skipped"] += 1
            self.last_result = {"key":key,"skipped":True,"from_key":p["from_key"]}
            return self.last_result
        actual = set(map(int,nums))
        hit = sorted(actual.intersection(p["pair"]))
        blind_hit = sorted(actual.intersection(p["random_pair"]))
        rec = {"key":key, "from_key":p["from_key"], "pair":list(p["pair"]),
               "random_pair":list(p["random_pair"]), "hit":hit,
               "random_hit":blind_hit, "count":len(hit), "random_count":len(blind_hit),
               "expert_hits":{}, "score_index":p.get("score_index")}
        t = self.totals
        t["evaluated"] += 1
        t["hits"] += len(hit); t["any"] += bool(hit); t["both"] += (len(hit)==2)
        t["random_hits"] += len(blind_hit)
        t["random_any"] += bool(blind_hit); t["random_both"] += (len(blind_hit)==2)
        t["paired_wins"] += (bool(hit) and not bool(blind_hit))
        t["paired_losses"] += (not bool(hit) and bool(blind_hit))
        t["paired_ties"] += (bool(hit) == bool(blind_hit))
        for name, pair in p.get("experts", {}).items():
            if name in self.experts and self._valid_pair(pair):
                hits = len(actual.intersection(pair))
                self.experts[name]["n"] += 2
                self.experts[name]["hits"] += hits
                rec["expert_hits"][name] = hits
        self.records.append(rec)
        self.records = self.records[-DUAL_RECORD_MAX:]
        self.last_result = rec
        return rec

    def text(self):
        p, t = self.pending, self.totals
        n = t["evaluated"]
        lines = ["🧠 DUAL TARGET ENGINE v1 — H1 SHADOW",
                 "Obiettivo: >=1 HIT fra 2 numeri nella prossima estrazione.",
                 "No puntate automatiche. Indici NON sono probabilita' predittive."]
        if p:
            lines.extend([f"🎯 COPPIA CONGELATA da {p['from_key']}: "
                          f"{p['pair'][0]:02d} + {p['pair'][1]:02d}",
                          f"Indice comparativo: {p.get('score_index',0):+.4f}",
                          "🧪 CONTROLLO CASUALE congelato: " +
                          " + ".join(f"{x:02d}" for x in p["random_pair"]),
                          "Pesi esperti: " + " ".join(f"{k}={v:.2f}" for k,v in
                                                         p.get("weights",{}).items())])
        else:
            lines.append("Nessun pending H1: attendo il prossimo draw e lo storico minimo.")
        pre = self.pretrain
        if pre:
            va, te = pre.get("validation", {}), pre.get("test", {})
            source_txt = "storico STATE" if pre.get("kind") == "state-history-bootstrap-v1" else "file esterno"
            lines.append(f"📚 PRETRAIN {source_txt}: {pre.get('train_rows',0)} draw TRAIN | "+
                         f"validation {va.get('evaluated',0)} | test {te.get('evaluated',0)} (SEPARATI da LIVE)")
            if te.get("evaluated"):
                lines.append(f"• TEST storico DUAL >=1: {te.get('any',0)}/{te['evaluated']} | " +
                             f"random {te.get('random_any',0)}/{te['evaluated']}")
        else:
            lines.append("📚 PRETRAIN: non caricato (manca dual_target_pretrain.json)")
        lines.append(f"📊 FORWARD SOLO FUTURO: {n} confronti | salti {t['skipped']}")
        if n:
            low,high = self._wilson(t["any"],n)
            lines.extend([f"• DUAL >=1: {t['any']}/{n} ({safe_pct(t['any'],n):.2f}%)",
                          f"• IC Wilson 95% (descrittivo, non corretto per selezione): "
                          f"{100*low:.2f}–{100*high:.2f}%",
                          f"• DUAL 2/2: {t['both']}/{n} | HIT totali {t['hits']}/{2*n}",
                          f"• RANDOM >=1: {t['random_any']}/{n} "
                          f"({safe_pct(t['random_any'],n):.2f}%) | 2/2: {t['random_both']}/{n}",
                          f"• Confronto appaiato DUAL vince/perde/pareggia: "
                          f"{t['paired_wins']}/{t['paired_losses']}/{t['paired_ties']}",
                          f"• Teorico >=1 39.70% | 2/2 4.74% | singolo 22.22%"])
            for count in (100,300):
                subset = self.records[-count:]
                if len(subset) >= count:
                    lines.append(f"• Rolling {count}: DUAL "
                        f"{sum(bool(r['count']) for r in subset)}/{count} | RANDOM "
                        f"{sum(bool(r['random_count']) for r in subset)}/{count}")
            if self.last_result:
                r = self.last_result
                lines.append(f"Ultimo {r['key']}: " +
                    ("SALTO: non valutato" if r.get("skipped") else
                     f"DUAL {r['count']}/2, RANDOM {r['random_count']}/2"))
        lines.append("⚠️ Complessita' e overfitting non aumentano la probabilita' fisica di estrazione.")
        return "\n".join(lines)



# ============================================================
# DUAL TARGET — DECINA ENGINE v3 (isolato, solo SHADOW)
# Decine: 90/01..09, 10..19, ... 80..89; 405 coppie interne.
# Il DUAL originale rimane baseline e conserva TUTTO il suo stato.
# ============================================================
DECINA_VERSION = 1
DECINA_GROUPS = ((90, *range(1, 10)),) + tuple(tuple(range(s, s+10)) for s in range(10, 90, 10))
DECINA_LABELS = ("90–09",) + tuple(f"{s:02d}–{s+9:02d}" for s in range(10, 90, 10))
DECINA_BY_NUMBER = {n: i for i, group in enumerate(DECINA_GROUPS) for n in group}
DECINA_WITHIN_PAIRS = tuple(tuple(sorted(pair)) for group in DECINA_GROUPS
                            for pair in combinations(group, 2))
DECINA_RECORD_MAX = 5000
DECINA_NOTIFY = os.getenv("DECINA_NOTIFY", "0") == "1"


class DecinaEngine:
    """Analisi prospettica a decine; NON riscrive la scelta del DUAL originale.

    L'indice confronta tutte le coppie tramite: ranking numerico originale +
    densita' corrente e accelerazione delle decine + frequenza congiunta
    shrinkata. Una coppia della stessa decina e' monitorata separatamente.
    Nessuna stima di probabilita' predittiva e nessuna puntata automatica.
    """
    def __init__(self):
        self.pending = None
        self.records = []
        self.last_result = None
        self.totals = dict(evaluated=0, skipped=0, fusion_any=0, fusion_both=0,
                           within_any=0, within_both=0, original_any=0,
                           random_any=0, fusion_wins=0, fusion_losses=0,
                           fusion_ties=0, within_wins=0, within_losses=0,
                           within_ties=0)

    @staticmethod
    def _valid_pair(pair):
        return DualTargetLab._valid_pair(pair)

    @staticmethod
    def _scaled(count, n, expected, prior, clip=2.5):
        if n <= 0:
            return 0.0
        # Effetto della frequenza regolarizzato verso il valore uniforme.
        strength = n / (n + prior)
        z = (count - n * expected) / math.sqrt(max(1., n * expected * (1 - expected)))
        return max(-clip, min(clip, strength * z))

    def load(self, obj):
        if not isinstance(obj, dict) or obj.get("version") != DECINA_VERSION:
            return
        totals = obj.get("totals", {})
        if isinstance(totals, dict):
            for key in self.totals:
                value = totals.get(key)
                if type(value) is int and value >= 0:
                    self.totals[key] = value
        rows = obj.get("records", [])
        if isinstance(rows, list):
            self.records = [r for r in rows if isinstance(r, dict) and
                            isinstance(r.get("key"), str) and
                            self._valid_pair(r.get("fusion_pair")) and
                            self._valid_pair(r.get("within_pair"))][-DECINA_RECORD_MAX:]
        p = obj.get("pending")
        if isinstance(p, dict) and isinstance(p.get("from_key"), str) and all(
                self._valid_pair(p.get(k)) for k in
                ("fusion_pair", "within_pair", "original_pair", "random_pair")):
            self.pending = p

    def dump(self):
        return {"version": DECINA_VERSION, "pending": self.pending,
                "records": self.records[-DECINA_RECORD_MAX:], "totals": self.totals}

    def _signals(self, history, dual, engine, key):
        """Tutte le statistiche usano draw fino a key; nessun risultato futuro."""
        if len(history) < DUAL_MIN_HISTORY or history[-1].get("key") != key:
            return None
        last_rows = [set(int(n) for n in r["nums"]) for r in history[-320:]]
        if any(len(x) != 20 for x in last_rows):
            return None
        available = dual._features(engine, key)
        if not available:
            return None
        weights = dual._weights(available)
        base = {n: sum(weights[name] * signal[n] for name, signal in available.items())
                for n in range(1,91)}
        # Ogni decina ha 10 numeri: l'atteso per draw e' 2.2222.
        count_groups = [[len(s.intersection(group)) for group in DECINA_GROUPS]
                        for s in last_rows]
        current = count_groups[-1]
        group_index = []
        for j in range(9):
            n8 = len(count_groups[-8:]); n40 = len(count_groups[-40:]); n160 = len(count_groups[-160:])
            c8 = sum(x[j] for x in count_groups[-8:]); c40 = sum(x[j] for x in count_groups[-40:])
            c160 = sum(x[j] for x in count_groups[-160:])
            # Z per somme ipergeometriche: Var(X)=n*K/N*(1-K/N)*(N-n)/(N-1).
            variance = 20*(10/90)*(80/90)*(70/89)
            z8 = (c8 - n8*20/9) / math.sqrt(max(1., n8*variance))
            z40 = (c40 - n40*20/9) / math.sqrt(max(1., n40*variance))
            z160 = (c160 - n160*20/9) / math.sqrt(max(1., n160*variance))
            strength = 0.16*z8 + 0.35*z40 + 0.20*z160 + 0.08*(z8-z160)
            # Condizionale su decina affollata nell'ultimo draw: apprendimento
            # solo da transizioni gia' concluse e supporto Bayesiano elevato.
            label = min(4, current[j])
            prior_states = [i for i in range(len(count_groups)-1)
                            if min(4,count_groups[i][j]) == label]
            if len(prior_states) >= 10:
                next_avg = sum(count_groups[i+1][j] for i in prior_states)/len(prior_states)
                strength += 0.30 * (next_avg - 20/9) * len(prior_states)/(len(prior_states)+100)
            group_index.append(max(-2.0, min(2.0, strength)))
        recent = last_rows[-160:]
        pair_counts = Counter()
        for nums in recent:
            for pair in combinations(sorted(nums), 2):
                pair_counts[pair] += 1
        # Nessuna coppia e' considerata 'dovuta' per via del ritardo.
        # 160 draw => ~7.6 co-uscite casuali per coppia: prior forte.
        joint = {pair: (pair_counts[pair] + 240*DUAL_PAIR_P0)/(len(recent)+240)
                 for pair in combinations(range(1,91),2)}
        def pair_score(a, b):
            j = joint[(a,b)]
            # La penalita' di co-uscita e' coerente con obiettivo >=1/2;
            # la co-uscita rimane registrata anche come obiettivo alternativo 2/2.
            band = 0.20 * (group_index[DECINA_BY_NUMBER[a]] + group_index[DECINA_BY_NUMBER[b]])
            return base[a] + base[b] + band - 5.0*(j-DUAL_PAIR_P0)
        # Identica regola per la coppia 'mista' e quella nella medesima decina.
        all_pairs = combinations(range(1,91), 2)
        fusion = max(all_pairs, key=lambda p: (pair_score(*p),
                     -dual._hash_tie(key, "decina-fusion", f"{p[0]}-{p[1]}")))
        within = max(DECINA_WITHIN_PAIRS, key=lambda p: (pair_score(*p),
                     -dual._hash_tie(key, "decina-within", f"{p[0]}-{p[1]}")))
        # Diagnostica di OGNI fascia: coppia piu' frequente nelle ultime 160,
        # con co-uscite reali; non e' la stessa cosa di una previsione.
        overview = []
        for j, group in enumerate(DECINA_GROUPS):
            within_pairs = [tuple(sorted(p)) for p in combinations(group, 2)]
            top3 = sorted(within_pairs, key=lambda p: (-pair_counts[p], p[0], p[1]))[:3]
            fav = top3[0]
            overview.append({"label": DECINA_LABELS[j], "last8": sum(x[j] for x in count_groups[-8:]),
                             "last40": sum(x[j] for x in count_groups[-40:]),
                             "last160": sum(x[j] for x in count_groups[-160:]),
                             "band_index": round(group_index[j],4),
                             "common_pair": list(fav), "co160": pair_counts[fav],
                             "co_window": len(recent),
                             "top3_pairs": [{"pair": list(q), "co160": pair_counts[q]}
                                            for q in top3]})
        return fusion, within, overview, pair_score(*fusion), pair_score(*within)

    def arm(self, engine, key):
        if self.pending is not None:
            return self.pending if self.pending.get("from_key") == key else None
        original = engine.dual.pending
        if not (original and original.get("from_key") == key):
            return None
        # Usa esclusivamente lo storico e le previsioni originali gia' congelate;
        # non modifica alcun campo del DUAL.
        signals = self._signals(engine.engine_history, engine.dual, engine, key)
        if not signals:
            return None
        fusion, within, overview, fscore, wscore = signals
        self.pending = {"from_key": key, "fusion_pair": list(fusion),
                        "within_pair": list(within), "original_pair": list(original["pair"]),
                        "random_pair": list(original["random_pair"]),
                        "fusion_index": round(fscore,5), "within_index": round(wscore,5),
                        "overview": overview, "created_at": now_txt()}
        return self.pending

    def settle(self, day, draw_id, nums):
        p = self.pending
        if p is None:
            return None
        self.pending = None
        key = draw_key(day, draw_id)
        if not sim_draw_is_consecutive(p["from_key"], day, draw_id):
            self.totals["skipped"] += 1
            self.last_result = {"key": key, "skipped": True}
            return self.last_result
        actual = set(map(int, nums))
        outcomes = {name: len(actual.intersection(p[field])) for name, field in
                    (("fusion","fusion_pair"),( "within","within_pair"),
                     ("original","original_pair"),( "random","random_pair"))}
        rec = {"key":key, "from_key":p["from_key"], "fusion_pair":p["fusion_pair"],
               "within_pair":p["within_pair"], "original_pair":p["original_pair"],
               "random_pair":p["random_pair"], "counts":outcomes,
               "within_group":DECINA_LABELS[DECINA_BY_NUMBER[p["within_pair"][0]]]}
        t = self.totals
        t["evaluated"] += 1
        for name in ("fusion", "within", "original", "random"):
            t[f"{name}_any"] += int(outcomes[name]>0)
        t["fusion_both"] += int(outcomes["fusion"]==2)
        t["within_both"] += int(outcomes["within"]==2)
        for method in ("fusion", "within"):
            x, y = outcomes[method]>0, outcomes["original"]>0
            t[f"{method}_wins"] += int(x and not y)
            t[f"{method}_losses"] += int(y and not x)
            t[f"{method}_ties"] += int(x==y)
        self.records.append(rec)
        self.records = self.records[-DECINA_RECORD_MAX:]
        self.last_result = rec
        return rec

    def short_text(self):
        p, t = self.pending, self.totals
        if not p:
            return "🔟 DECINA ENGINE: nessuna nuova coppia congelata (attendo H1)."
        n = t["evaluated"]
        return (f"🔟 DUAL+DECINE PROSSIMA H1: {p['fusion_pair'][0]:02d}+{p['fusion_pair'][1]:02d} "
                f"| stessa decina {p['within_pair'][0]:02d}+{p['within_pair'][1]:02d} "
                f"({DECINA_LABELS[DECINA_BY_NUMBER[p['within_pair'][0]]]})\n"
                f"Forward DUAL+DECINE {t['fusion_any']}/{n} | coppia decina {t['within_any']}/{n} "
                f"| DUAL originario sugli stessi draw {t['original_any']}/{n} "
                f"| casuale {t['random_any']}/{n}.")

    def text(self):
        p, t = self.pending, self.totals
        lines = ["🔟 DUAL TARGET — DECINA ENGINE v3 SHADOW",
                 "Fasce: 90–09 (90+01..09), 10–19, …, 80–89. 9 fasce × 45 = 405 coppie interne.",
                 "Obiettivo principale: >=1 HIT fra 2 numeri alla prossima H1."]
        if p:
            lines.extend([f"🎯 DUAL+DECINE: {p['fusion_pair'][0]:02d} + {p['fusion_pair'][1]:02d}",
                          f"🔗 STESSA DECINA: {p['within_pair'][0]:02d} + {p['within_pair'][1]:02d} "
                          f"({DECINA_LABELS[DECINA_BY_NUMBER[p['within_pair'][0]]]})",
                          f"📎 DUAL ORIGINALE: {p['original_pair'][0]:02d} + {p['original_pair'][1]:02d}",
                          f"Origine del segnale: {p['from_key']} | indici {p['fusion_index']:+.3f}/{p['within_index']:+.3f}"])
            lines.append("📦 DECINE: conteggi numeri usciti nelle ultime 8/40/160 estrazioni disponibili; "
                         "TOP3 coppie co-uscite nelle ultime max 160:")
            for d in p["overview"]:
                a,b=d["common_pair"]
                strongest = ", ".join(
                    f"{q['pair'][0]:02d}+{q['pair'][1]:02d}:{q['co160']}"
                    for q in d.get("top3_pairs", [{"pair": [a,b], "co160":d["co160"]}]))
                lines.append(f"• {d['label']}: {d['last8']}/{d['last40']}/{d['last160']} "
                             f"| TOP3 co-uscite/{d.get('co_window',160)}: {strongest} "
                             f"| indice {d['band_index']:+.2f}")
        else:
            lines.append("Nessun pending valido: /decine mostrera' la nuova coppia dopo il prossimo draw live.")
        n=t["evaluated"]
        lines.extend([f"📊 FORWARD DECINA v3: {n} valutati | salti {t['skipped']}",
            f"• DUAL+DECINE >=1: {t['fusion_any']}/{n} ({safe_pct(t['fusion_any'],n):.2f}%) | 2/2 {t['fusion_both']}/{n}",
            f"• STESSA DECINA >=1: {t['within_any']}/{n} ({safe_pct(t['within_any'],n):.2f}%) | 2/2 {t['within_both']}/{n}",
            f"• DUAL ORIGINALE stessi draw >=1: {t['original_any']}/{n} ({safe_pct(t['original_any'],n):.2f}%)",
            f"• RANDOM stessi draw >=1: {t['random_any']}/{n} ({safe_pct(t['random_any'],n):.2f}%)",
            f"• Appaiato DECINE vs DUAL: +{t['fusion_wins']}/-{t['fusion_losses']}/={t['fusion_ties']}",
            f"• Appaiato STESSA DECINA vs DUAL: +{t['within_wins']}/-{t['within_losses']}/={t['within_ties']}"])
        if self.records:
            lines.append("📍 COPPIA STESSA DECINA: forward per fascia (solo segnali congelati):")
            for label in DECINA_LABELS:
                subset=[r for r in self.records if r.get("within_group")==label]
                if subset:
                    k=sum(r["counts"]["within"]>0 for r in subset)
                    z=sum(r["counts"]["within"]==2 for r in subset)
                    lines.append(f"• {label}: >=1 {k}/{len(subset)} ({safe_pct(k,len(subset)):.2f}%) | 2/2 {z}/{len(subset)}")
        for window in (100,300):
            if len(self.records)>=window:
                sub=self.records[-window:]
                lines.append(f"• Ultimi {window}: DUAL+DECINE "
                    f"{sum(r['counts']['fusion']>0 for r in sub)}/{window} | stessa decina "
                    f"{sum(r['counts']['within']>0 for r in sub)}/{window} | DUAL "
                    f"{sum(r['counts']['original']>0 for r in sub)}/{window}")
        lines.append("⚠️ Frequenze e co-uscite passate sono descrittive, non prove di previsione; nessuna puntata automatica.")
        return "\n".join(lines)


# ============================================================
# DECINA FLOW LAB v2 + FLOW REGIME + BURST EVENT DETECTOR v3 — SHADOW H1
# FLOW ricostruisce 288 draw × 9 decine e classifica COMPRESSION/NORMAL/DISPERSION.
# BURST v3 usa SOLO
# informazioni disponibili prima della H1 e puo' restituire NO SIGNAL.
# I risultati BURST v1 esistenti vengono migrati senza reset.
# ============================================================
FLOW_VERSION = 2
FLOW_WARMUP = max(288, int(os.getenv("FLOW_WARMUP", "288")))
FLOW_RECORD_MAX = max(300, int(os.getenv("FLOW_RECORD_MAX", "5000")))

BURST_VERSION = 3
BURST_WARMUP = max(288, int(os.getenv("BURST_WARMUP", "288")))
BURST_RECORD_MAX = max(300, int(os.getenv("BURST_RECORD_MAX", "5000")))
BURST_NOTIFY = os.getenv("BURST_NOTIFY", "0") == "1"
BURST_GATE_SCORE_Q = min(0.95, max(0.50, float(os.getenv("BURST_GATE_SCORE_Q", "0.80"))))
BURST_GATE_MARGIN_Q = min(0.95, max(0.25, float(os.getenv("BURST_GATE_MARGIN_Q", "0.55"))))
BURST_EXTREME_SCORE_Q = min(0.99, max(BURST_GATE_SCORE_Q, float(os.getenv("BURST_EXTREME_SCORE_Q", "0.93"))))
BURST_MIN_CALIBRATION = max(20, int(os.getenv("BURST_MIN_CALIBRATION", "30")))
BURST_GATE_AUDIT_VERSION = 1  # v9: salva soglie/delta per ogni nuova decisione

# Per una decina specifica: P(X>=5), P(X>=6) con X ipergeometrica(90,10,20)
BURST_BASE_5 = sum(math.comb(10,k)*math.comb(80,20-k)/math.comb(90,20)
                   for k in range(5, 11))
BURST_BASE_6 = sum(math.comb(10,k)*math.comb(80,20-k)/math.comb(90,20)
                   for k in range(6, 11))


def _decina_quantile(values, q):
    vals = sorted(float(x) for x in values if isinstance(x, (int, float)) and math.isfinite(float(x)))
    if not vals:
        return 0.0
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals)-1) * min(1.0, max(0.0, float(q)))
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    w = pos-lo
    return vals[lo]*(1.0-w) + vals[hi]*w


def _decina_history_rows(history, limit):
    """Ultimi `limit` draw validi, in ordine, senza inventare dati mancanti."""
    rows = []
    for row in history[-limit:]:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            return None
        raw = row.get("nums")
        if not isinstance(raw, (list, tuple)) or len(raw) != 20:
            return None
        try:
            nums = set(int(n) for n in raw)
        except (ValueError, TypeError):
            return None
        if len(nums) != 20 or min(nums) < 1 or max(nums) > 90:
            return None
        rows.append((row["key"], nums))
    if len(rows) < limit:
        return None
    keys = [x[0] for x in rows]
    if len(set(keys)) != len(keys):
        return None
    # Barriera minima anti-storico distorto. Su 288 draw l'atteso per numero
    # e' 64; i limiti 6%-40% sono volutamente larghi e servono solo a bloccare
    # archivi palesemente corrotti, non a selezionare risultati favorevoli.
    freq = Counter(n for _, nums in rows for n in nums)
    n = len(rows)
    if min(freq.get(i, 0) for i in range(1, 91)) < n*0.06 or max(freq.values()) > n*0.40:
        return None
    return rows


class DecinaFlowLab:
    """Tracker descrittivo draw-by-draw delle nove decine.

    Ricostruisce la matrice 288x9 dal normale ENGINE HISTORY e classifica ogni
    draw in COMPRESSION/NORMAL/DISPERSION. Non crea HIT retroattivi e non
    modifica ENGINE/SOSIA/DUAL. Le statistiche sono disponibili al BURST v3
    soltanto DOPO il draw che le ha generate.
    """
    def __init__(self):
        self.warmup = None
        self.last_snapshot = None
        self.live_rows = []

    def load(self, obj):
        if not isinstance(obj, dict) or obj.get("version") not in (1, FLOW_VERSION):
            return
        rows = obj.get("live_rows")
        if isinstance(rows, list):
            clean = []
            for r in rows[-FLOW_RECORD_MAX:]:
                if (isinstance(r, dict) and isinstance(r.get("key"), str) and
                    isinstance(r.get("counts"), list) and len(r["counts"]) == 9):
                    try:
                        counts = [max(0, min(10, int(x))) for x in r["counts"]]
                    except (TypeError, ValueError):
                        continue
                    clean.append({"key": r["key"], "counts": counts})
            self.live_rows = clean
        if isinstance(obj.get("warmup"), dict):
            self.warmup = obj.get("warmup")
        if isinstance(obj.get("last_snapshot"), dict):
            self.last_snapshot = obj.get("last_snapshot")

    def dump(self):
        return {"version": FLOW_VERSION, "warmup": self.warmup,
                "last_snapshot": self.last_snapshot,
                "live_rows": self.live_rows[-FLOW_RECORD_MAX:]}

    @staticmethod
    def _gap(counts, threshold):
        for back, value in enumerate(reversed(counts)):
            if value >= threshold:
                return back
        return len(counts)

    @staticmethod
    def _streak(counts, predicate):
        n = 0
        for value in reversed(counts):
            if predicate(value):
                n += 1
            else:
                break
        return n

    @staticmethod
    def _unique_dominant(row):
        m = max(row)
        ids = [i for i, x in enumerate(row) if x == m]
        return (ids[0], m) if len(ids) == 1 else (None, m)

    @staticmethod
    def _regime(row):
        """Regime globale delle nove decine nel draw gia' concluso.

        COMPRESSION: max-min <= 1
        NORMAL:      max-min == 2
        DISPERSION:  max-min >= 3
        La classificazione usa soltanto il draw corrente, quindi e' disponibile
        prima della H1 successiva.
        """
        lo=min(row); hi=max(row); spread=hi-lo
        mean=sum(row)/len(row)
        sd=math.sqrt(sum((x-mean)**2 for x in row)/len(row))
        if spread <= 1:
            name='COMPRESSION'
        elif spread == 2:
            name='NORMAL'
        else:
            name='DISPERSION'
        strength=('FORTE' if (name=='COMPRESSION' and spread<=1) or
                  (name=='DISPERSION' and (spread>=4 or hi>=6)) else 'STANDARD')
        return {"name":name, "strength":strength, "spread":spread,
                "min":lo, "max":hi, "sd":sd}

    @classmethod
    def build_snapshot_from_rows(cls, rows):
        matrix = [[len(nums.intersection(g)) for g in DECINA_GROUPS] for _, nums in rows]
        n = len(matrix)
        if not matrix:
            return None

        # Dominanti uniche + matrice delle transizioni dominante -> dominante.
        dom = [cls._unique_dominant(r) for r in matrix]
        regimes = [cls._regime(r) for r in matrix]
        regime_names = ("COMPRESSION", "NORMAL", "DISPERSION")
        regime_stats = {name:{"n":0, "next_sum_max":0, "next_any4":0,
                              "next_any5":0, "next_any6":0,
                              "next_group5":[0]*9, "next_group6":[0]*9,
                              "next_regime":{x:0 for x in regime_names}}
                        for name in regime_names}
        # Ogni record t usa il regime del draw t e misura SOLO il draw t+1.
        for i in range(n-1):
            nd, ne = rows[i+1][0].split('#')
            if not sim_draw_is_consecutive(rows[i][0], nd, int(ne)):
                continue
            rs = regime_stats[regimes[i]["name"]]
            nxt = matrix[i+1]
            rs["n"] += 1
            rs["next_sum_max"] += max(nxt)
            rs["next_any4"] += int(max(nxt) >= 4)
            rs["next_any5"] += int(max(nxt) >= 5)
            rs["next_any6"] += int(max(nxt) >= 6)
            for j, value in enumerate(nxt):
                rs["next_group5"][j] += int(value >= 5)
                rs["next_group6"][j] += int(value >= 6)
            rs["next_regime"][regimes[i+1]["name"]] += 1

        trans = [[0 for _ in range(9)] for _ in range(9)]
        dom_support = [0]*9
        dom_repeat = 0
        dom_repeat_den = 0
        ties = 0
        for i, (idx, _) in enumerate(dom):
            if idx is None:
                ties += 1
            if i >= n-1:
                continue
            nd, ne = rows[i+1][0].split('#')
            if not sim_draw_is_consecutive(rows[i][0], nd, int(ne)):
                continue
            a, b = dom[i][0], dom[i+1][0]
            if a is not None:
                dom_support[a] += 1
            if a is not None and b is not None:
                trans[a][b] += 1
                dom_repeat_den += 1
                dom_repeat += int(a == b)

        current_dom, current_dom_count = dom[-1]
        overview = []
        expected = 20.0/9.0
        for j, label in enumerate(DECINA_LABELS):
            counts = [r[j] for r in matrix]
            windows = {}
            for w in (8, 20, 40, 80, 160, 288):
                use = counts[-min(w, len(counts)):]
                windows[str(w)] = sum(use)
            avg8 = windows["8"] / min(8, len(counts))
            avg40 = windows["40"] / min(40, len(counts))
            avg160 = windows["160"] / min(160, len(counts))
            prev = counts[-2] if len(counts) >= 2 else counts[-1]

            # Stato della stessa decina -> comportamento della H1 successiva.
            state_trans = {str(k): {"n":0, "sum_next":0, "hit4":0, "hit5":0, "hit6":0}
                           for k in range(6)}
            for i in range(len(counts)-1):
                nd, ne = rows[i+1][0].split('#')
                if not sim_draw_is_consecutive(rows[i][0], nd, int(ne)):
                    continue
                cat = str(min(5, counts[i]))
                nxt = counts[i+1]
                d = state_trans[cat]
                d["n"] += 1; d["sum_next"] += nxt
                d["hit4"] += int(nxt >= 4); d["hit5"] += int(nxt >= 5); d["hit6"] += int(nxt >= 6)

            # Quante volte la decina e' risultata dominante unica nelle finestre recenti.
            dom40 = sum(1 for idx, _ in dom[-min(40, n):] if idx == j)
            dom160 = sum(1 for idx, _ in dom[-min(160, n):] if idx == j)

            if current_dom is not None and dom_support[current_dom] > 0:
                next_dom_raw = trans[current_dom][j] / dom_support[current_dom]
                # shrink verso 1/9, cosi pochi passaggi non dominano il punteggio.
                next_dom_shrink = (trans[current_dom][j] + 8*(1/9)) / (dom_support[current_dom] + 8)
            else:
                next_dom_raw = 1/9
                next_dom_shrink = 1/9

            overview.append({
                "label": label,
                "counts": counts[-16:],
                "recent": counts[-1], "prev": prev, "delta": counts[-1]-prev,
                "last8": windows["8"], "last20": windows["20"],
                "last40": windows["40"], "last80": windows["80"],
                "last160": windows["160"], "last288": windows["288"],
                "avg8": avg8, "avg40": avg40, "avg160": avg160,
                "accel8_40": avg8-avg40, "accel40_160": avg40-avg160,
                "gap4": cls._gap(counts, 4), "gap5": cls._gap(counts, 5),
                "gap6": cls._gap(counts, 6),
                "streak_high": cls._streak(counts, lambda x: x >= 3),
                "streak_low": cls._streak(counts, lambda x: x <= 1),
                "events4": sum(x >= 4 for x in counts),
                "events5": sum(x >= 5 for x in counts),
                "events6": sum(x >= 6 for x in counts),
                "dom40": dom40, "dom160": dom160,
                "state_transitions": state_trans,
                "next_dom_raw": next_dom_raw, "next_dom_shrink": next_dom_shrink,
                "expected": expected,
            })

        return {
            "ready": True, "required": FLOW_WARMUP, "available": n,
            "last_key": rows[-1][0], "matrix_tail": matrix[-12:],
            "keys_tail": [k for k, _ in rows[-12:]], "overview": overview,
            "current_dominant": current_dom,
            "current_dominant_label": DECINA_LABELS[current_dom] if current_dom is not None else None,
            "current_dominant_count": current_dom_count,
            "dominant_ties": ties,
            "dominant_repeat": dom_repeat, "dominant_repeat_den": dom_repeat_den,
            "dominant_transitions": trans, "dominant_support": dom_support,
            "current_regime": regimes[-1],
            "regime_stats": regime_stats,
            "regime_tail": [r["name"] for r in regimes[-12:]],
        }

    def bootstrap(self, history):
        rows = _decina_history_rows(history, FLOW_WARMUP)
        if rows is None:
            self.warmup = {"ready":False, "available":min(len(history), FLOW_WARMUP),
                           "required":FLOW_WARMUP, "reason":"storico insufficiente o anomalo"}
            self.last_snapshot = self.warmup
            return False
        snap = self.build_snapshot_from_rows(rows)
        self.warmup = snap
        self.last_snapshot = snap
        return True

    def observe_live(self, key, nums):
        try:
            s = set(int(x) for x in nums)
        except (TypeError, ValueError):
            return
        if len(s) != 20:
            return
        row = {"key": key, "counts": [len(s.intersection(g)) for g in DECINA_GROUPS]}
        if not self.live_rows or self.live_rows[-1].get("key") != key:
            self.live_rows.append(row)
            self.live_rows = self.live_rows[-FLOW_RECORD_MAX:]

    def group_feature(self, idx):
        w = self.last_snapshot or self.warmup or {}
        ov = w.get("overview") or []
        return ov[idx] if 0 <= idx < len(ov) else None

    def text(self):
        w = self.last_snapshot or self.warmup or {}
        lines = ["🌊 DECINA FLOW LAB v2 + FLOW REGIME — WARMUP 288",
                 "Conta ogni decina a OGNI estrazione e studia transizioni, ripetizioni e COMPRESSION/NORMAL/DISPERSION.",
                 f"📚 FLOW STATE: {w.get('available',0)}/{FLOW_WARMUP} | " +
                 ("READY" if w.get("ready") else "NON PRONTO: "+w.get("reason","storico assente"))]
        if not w.get("ready"):
            return "\n".join(lines)
        dom = w.get("current_dominant")
        domtxt = (f"{DECINA_LABELS[dom]} ({w.get('current_dominant_count',0)})"
                  if dom is not None else f"PARI ({w.get('current_dominant_count',0)})")
        den = int(w.get("dominant_repeat_den",0) or 0)
        rep = int(w.get("dominant_repeat",0) or 0)
        lines.extend([f"🎯 Dominante ultimo draw: {domtxt}",
                      f"🔁 Dominante unica ripetuta alla H1 nel warmup: {rep}/{den} ({safe_pct(rep,den):.2f}%)"])
        rg = w.get("current_regime") or {}
        rg_name = rg.get("name", "-")
        rg_stats = (w.get("regime_stats") or {}).get(rg_name, {})
        rn = int(rg_stats.get("n",0) or 0)
        rmean = (float(rg_stats.get("next_sum_max",0))/rn) if rn else 0.0
        lines.append(f"🧭 FLOW REGIME ultimo draw: {rg_name} {rg.get('strength','')} | "
                     f"spread {rg.get('spread','-')} (min {rg.get('min','-')} / max {rg.get('max','-')}) | σ {float(rg.get('sd',0)):.2f}")
        lines.append(f"↪ H1 dopo {rg_name} nel warmup n={rn}: max medio {rmean:.2f} | "
                     f"almeno una decina 4+ {safe_pct(rg_stats.get('next_any4',0),rn):.1f}% | "
                     f"5+ {safe_pct(rg_stats.get('next_any5',0),rn):.1f}% | "
                     f"6+ {safe_pct(rg_stats.get('next_any6',0),rn):.1f}%")
        if rn:
            g5 = rg_stats.get('next_group5') or [0]*9
            order5 = sorted(range(9), key=lambda j:(-g5[j],j))[:3]
            lines.append("🎯 Dopo questo regime, decine piu' spesso 5+ alla H1: " +
                         ", ".join(f"{DECINA_LABELS[j]} {g5[j]}/{rn} ({safe_pct(g5[j],rn):.1f}%)" for j in order5))
        lines.append("📦 STATO ATTUALE — ultimo/Δ1, media8/40, gap5, e comportamento H1 dopo lo stesso stato:")
        for row in w.get("overview", []):
            cat=str(min(5,int(row['recent'])))
            tr=row.get('state_transitions',{}).get(cat,{})
            tn=int(tr.get('n',0) or 0); tsum=int(tr.get('sum_next',0) or 0)
            next_mean=(tsum/tn) if tn else 0.0
            state=('SCARICA' if row['recent']<=1 else ('RICCA' if row['recent']>=4 else 'NORMALE'))
            lines.append(f"• {row['label']}: {row['recent']}/{row['delta']:+d} {state} | "
                         f"μ8 {row['avg8']:.2f} μ40 {row['avg40']:.2f} | gap5 {row['gap5']} | "
                         f"H1 stesso stato n={tn}: μ {next_mean:.2f}, 4+ {safe_pct(tr.get('hit4',0),tn):.1f}%, "
                         f"5+ {safe_pct(tr.get('hit5',0),tn):.1f}%")
        lines.append("🧩 ULTIMI 8 DRAW — vettore presenze per 9 decine:")
        keys = w.get("keys_tail", [])[-8:]
        matrix = w.get("matrix_tail", [])[-8:]
        regime_tail = w.get("regime_tail", [])[-8:]
        for pos, (key, row) in enumerate(zip(keys, matrix)):
            rname = regime_tail[pos] if pos < len(regime_tail) else self._regime(row)["name"]
            lines.append(f"• {key}: " + " ".join(str(x) for x in row) + f" | {rname}")
        if dom is not None:
            trans = w.get("dominant_transitions", [])
            support = w.get("dominant_support", [])
            if len(trans) == 9 and len(support) == 9 and support[dom] > 0:
                order = sorted(range(9), key=lambda j: (-trans[dom][j], j))[:3]
                lines.append(f"🔀 Dopo dominante {DECINA_LABELS[dom]} (supporto {support[dom]}): " +
                             ", ".join(f"{DECINA_LABELS[j]} {trans[dom][j]}" for j in order))
        lines.append("⚠️ FLOW e' descrittivo/shadow: usa solo draw gia' conclusi e non modifica ENGINE/SOSIA/DUAL.")
        return "\n".join(lines)



# ============================================================
# DECINA POST-BURST LAB v1 — analisi descrittiva H1/H2/H3
# Una coorte = una decina con 5 numeri esatti oppure 6+ in un draw.
# Le coorti dei draw con >=2 decine 5+ sono anche esposte separatamente.
# Lo storico 288 (rolling) NON incrementa i contatori LIVE.
# Nessuna feature POST-BURST modifica i gate BURST/DUAL esistenti.
# ============================================================
POSTBURST_VERSION = 1
POSTBURST_WARMUP = 288
POSTBURST_RECORD_MAX = max(100, int(os.getenv('POSTBURST_RECORD_MAX', '2000')))


class DecinaPostBurstLab:
    """Segue ciascuna decina 5/6+ fino a H3, senza attribuire colpi mancanti."""

    def __init__(self):
        self.warmup = None
        self.active = []
        self.live_records = []
        self.last_seen_key = None
        self.skipped = 0
        self.last_result = None

    @staticmethod
    def _counts(nums):
        values = set(int(x) for x in nums)
        if len(values) != 20 or min(values) < 1 or max(values) > 90:
            raise ValueError('estrazione non valida per POST-BURST')
        return [len(values.intersection(g)) for g in DECINA_GROUPS]

    @staticmethod
    def _origins(counts):
        multi = sum(x >= 5 for x in counts) >= 2
        return [{'group_index':j, 'origin_count':v, 'double':multi}
                for j,v in enumerate(counts) if v >= 5]

    @staticmethod
    def _category(origin):
        return '6+' if origin['origin_count'] >= 6 else '5 esatti'

    @staticmethod
    def _next_metrics(group_index, next_counts):
        same = next_counts[group_index]
        other = [j for j,x in enumerate(next_counts) if j != group_index and x >= 5]
        # La fascia 90-09 non e' adiacente numericamene a 80-89.
        nearby = [j for j in other if abs(j-group_index) == 1]
        return {'same_count':same, 'same_4':same >= 4,
                'same_5':same >= 5, 'same_6':same >= 6,
                'other_5':bool(other), 'other_count':len(other),
                'other_groups':other, 'adjacent_5':bool(nearby),
                'any_5':max(next_counts) >= 5}

    @classmethod
    def _hist_stats(cls, rows):
        matrix = [cls._counts(nums) for _,nums in rows]
        classes = ('TUTTE 5+', '5 esatti', '6+', 'DOPPIO 5+')
        stats = {c:{str(h):{'n':0, 'same_sum':0, 'same_4':0, 'same_5':0,
                              'same_6':0, 'other_5':0, 'adjacent_5':0,
                              'any_5':0, 'same_distribution':[0]*11}
                    for h in (1,2,3)} for c in classes}
        latest=[]
        for i,counts in enumerate(matrix):
            origins=cls._origins(counts)
            if i >= len(matrix)-8 and origins:
                latest.append({'key':rows[i][0], 'decine':[
                    {'label':DECINA_LABELS[o['group_index']], 'n':o['origin_count']}
                    for o in origins]})
            for origin in origins:
                categories=['TUTTE 5+', cls._category(origin)]
                if origin['double']:
                    categories.append('DOPPIO 5+')
                j=origin['group_index']
                for h in (1,2,3):
                    k=i+h
                    if k >= len(matrix):
                        continue
                    # Tutti i passaggi intermedi devono essere veri draw consecutivi.
                    valid=True
                    for step in range(i,k):
                        day, draw_id=rows[step+1][0].rsplit('#',1)
                        if not sim_draw_is_consecutive(rows[step][0], day, int(draw_id)):
                            valid=False; break
                    if not valid:
                        continue
                    m=cls._next_metrics(j,matrix[k])
                    for cat in categories:
                        st=stats[cat][str(h)]
                        st['n']+=1; st['same_sum']+=m['same_count']
                        st['same_distribution'][m['same_count']]+=1
                        for flag in ('same_4','same_5','same_6','other_5','adjacent_5','any_5'):
                            st[flag]+=int(m[flag])
        return {'stats':stats, 'recent_bursts':latest[-8:]}

    def bootstrap(self, history):
        rows=_decina_history_rows(history, POSTBURST_WARMUP)
        if rows is None:
            self.warmup={'ready':False, 'available':min(len(history),POSTBURST_WARMUP),
                         'reason':'storico insufficiente o anomalo'}
            return False
        snap=self._hist_stats(rows)
        self.warmup={'ready':True, 'available':len(rows), 'last_key':rows[-1][0], **snap}
        return True

    def load(self, obj):
        if not isinstance(obj,dict) or obj.get('version') != POSTBURST_VERSION:
            return
        self.warmup=obj.get('warmup') if isinstance(obj.get('warmup'),dict) else None
        self.last_seen_key=obj.get('last_seen_key') if isinstance(obj.get('last_seen_key'),str) else None
        self.skipped=max(0,int(obj.get('skipped',0) or 0))
        self.last_result=obj.get('last_result') if isinstance(obj.get('last_result'),dict) else None
        active=obj.get('active',[])
        if isinstance(active,list):
            for p in active[-40:]:
                if (isinstance(p,dict) and isinstance(p.get('origin_key'),str)
                    and isinstance(p.get('last_key'),str)
                    and isinstance(p.get('group_index'),int) and 0<=p['group_index']<9
                    and isinstance(p.get('age'),int) and 0<=p['age']<3
                    and isinstance(p.get('origin_count'),int) and 5<=p['origin_count']<=10):
                    self.active.append(dict(p))
        rec=obj.get('live_records',[])
        if isinstance(rec,list):
            self.live_records=[dict(r) for r in rec[-POSTBURST_RECORD_MAX:]
                               if isinstance(r,dict) and isinstance(r.get('origin_key'),str)
                               and r.get('horizon') in (1,2,3)]

    def dump(self):
        return {'version':POSTBURST_VERSION, 'warmup':self.warmup,
                'last_seen_key':self.last_seen_key, 'active':self.active[-40:],
                'live_records':self.live_records[-POSTBURST_RECORD_MAX:],
                'skipped':self.skipped, 'last_result':self.last_result}

    def observe_live(self, day, draw_id, nums, open_new=True):
        """Valuta coorti gia' aperte. Nuove coorti solo da nuovi draw notificabili."""
        key=draw_key(day,draw_id)
        if key==self.last_seen_key:
            return None
        counts=self._counts(nums)
        still=[]; closed=[]
        for p in self.active:
            if not sim_draw_is_consecutive(p['last_key'],day,draw_id):
                self.skipped += 3-p['age']
                continue
            horizon=p['age']+1
            metrics=self._next_metrics(p['group_index'],counts)
            result={'key':key,'origin_key':p['origin_key'],
                    'group_index':p['group_index'],'group':DECINA_LABELS[p['group_index']],
                    'origin_count':p['origin_count'],'double':p['double'],
                    'horizon':horizon, **metrics}
            self.live_records.append(result)
            self.last_result=result
            closed.append(result)
            if horizon<3:
                updated=dict(p); updated['age']=horizon; updated['last_key']=key
                still.append(updated)
        self.active=still
        for origin in (self._origins(counts) if open_new else []):
            self.active.append({'origin_key':key,'last_key':key,
                                'group_index':origin['group_index'],
                                'origin_count':origin['origin_count'],
                                'double':origin['double'],'age':0})
        self.live_records=self.live_records[-POSTBURST_RECORD_MAX:]
        self.last_seen_key=key
        return closed

    def text(self):
        w=self.warmup or {}
        lines=['🌋 DECINA POST-BURST LAB v1 — H1/H2/H3 SHADOW',
               'Segue la STESSA decina dopo 5 esatti o 6+, e controlla se un nuovo 5+ passa ad ALTRA decina.',
               f"📚 WARMUP: {w.get('available',0)}/{POSTBURST_WARMUP} | " +
               ('READY' if w.get('ready') else 'NON PRONTO: '+w.get('reason','storico assente'))]
        if w.get('ready'):
            lines.append('📦 STORICO WARMUP — una coorte per decina 5+; i casi DOPPIO si sovrappongono alle altre categorie:')
            for cat in ('TUTTE 5+', '5 esatti', '6+', 'DOPPIO 5+'):
                lines.append('• '+cat+':')
                for h in (1,2,3):
                    st=w['stats'][cat][str(h)]; n=st['n']
                    mean=st['same_sum']/n if n else 0.0
                    lines.append(f"  H{h} n={n} | stessa μ {mean:.2f}/10, 4+ {safe_pct(st['same_4'],n):.1f}%, "
                                 f"5+ {safe_pct(st['same_5'],n):.1f}%, 6+ {safe_pct(st['same_6'],n):.1f}% | "
                                 f"altra 5+ {safe_pct(st['other_5'],n):.1f}% "
                                 f"(adiacente {safe_pct(st['adjacent_5'],n):.1f}%) | "
                                 f"qualsiasi 5+ {safe_pct(st['any_5'],n):.1f}%")
                    if h==1 and n:
                        dist=st['same_distribution']
                        lines.append('    Distribuzione stessa H1: ' + ' | '.join(
                            f'{k}={dist[k]}' for k in range(5)) +
                            f" | 5={dist[5]} | 6+={sum(dist[6:])}")
            latest=w.get('recent_bursts') or []
            if latest:
                lines.append('🧩 EVENTI 5+ RECENTI nel warmup:')
                for event in latest[-5:]:
                    lines.append('• '+event['key']+': '+', '.join(f"{x['label']}={x['n']}" for x in event['decine']))
        lines.append(f'🧪 FORWARD LIVE SOLO NUOVI EVENTI: {len(self.live_records)} valutazioni di coorte | '
                     f'coorti ancora aperte {len(self.active)} | orizzonti saltati {self.skipped}')
        for cat in ('TUTTE 5+', '5 esatti', '6+', 'DOPPIO 5+'):
            chosen=[r for r in self.live_records if (cat=='TUTTE 5+' or
                    (cat=='5 esatti' and r['origin_count']==5) or
                    (cat=='6+' and r['origin_count']>=6) or
                    (cat=='DOPPIO 5+' and r['double']))]
            vals=[r for r in chosen if r['horizon']==1]
            if vals:
                n=len(vals)
                lines.append(f"• {cat} H1: stessa 5+ {sum(r['same_5'] for r in vals)}/{n} "
                             f"({safe_pct(sum(r['same_5'] for r in vals),n):.1f}%) | "
                             f"altra 5+ {sum(r['other_5'] for r in vals)}/{n} | "
                             f"media stessa {sum(r['same_count'] for r in vals)/n:.2f}/10")
        if self.last_result:
            r=self.last_result
            lines.append(f"🧾 Ultimo: {r['origin_key']} {r['group']} {r['origin_count']}/10 → "
                         f"H{r['horizon']} {r['key']}: stessa {r['same_count']}/10 | "
                         f"altre 5+ {', '.join(DECINA_LABELS[j] for j in r['other_groups']) or 'nessuna'}")
        lines.append('⚠️ Coorti per decina, non estrazioni indipendenti; warmup descrittivo, forward separato. '
                     'POST-BURST non altera BURST v3 o le altre previsioni.')
        return '\n'.join(lines)


# ============================================================
# POST-6 EXTREME SHADOW v1 — test prospettico pulito
# Regola congelata dalla v10: quando una decina CHIUDE con 6+ numeri,
# segue LA STESSA DECINA esclusivamente nella H1 successiva.
# Ogni evento ha un controllo casuale congelato nello stesso momento.
# I casi POST-BURST pre-v10 sono solo riferimento descrittivo, mai risultati v10.
# ============================================================
POST6_VERSION = 1
POST6_RECORD_MAX = max(200, int(os.getenv("POST6_RECORD_MAX", "2000")))


class Post6ExtremeShadow:
    def __init__(self):
        self.start_from_key = None
        self.started_at = None
        self.pre_reference = None
        self.pending = []
        self.records = []
        self.skipped = 0
        self.last_result = None
        self.last_seen_key = None

    @staticmethod
    def _counts(nums):
        values = set(int(x) for x in nums)
        if len(values) != 20 or min(values) < 1 or max(values) > 90:
            raise ValueError("estrazione non valida per POST-6")
        return [len(values.intersection(g)) for g in DECINA_GROUPS]

    def ensure_start(self, history, postburst=None):
        if self.start_from_key:
            return False
        if not history:
            return False
        self.start_from_key = str(history[-1].get("key") or "")
        if not self.start_from_key:
            return False
        self.started_at = datetime.now(BOT_TZ).isoformat(timespec="seconds")
        # Snapshot immutabile del riferimento gia' osservato PRIMA della v10.
        vals=[]
        if postburst is not None:
            vals=[r for r in getattr(postburst, "live_records", [])
                  if isinstance(r,dict) and r.get("horizon")==1
                  and int(r.get("origin_count",0) or 0)>=6]
        n=len(vals)
        self.pre_reference={
            "n":n,
            "same5":sum(int(bool(r.get("same_5"))) for r in vals),
            "same6":sum(int(bool(r.get("same_6"))) for r in vals),
            "same_sum":sum(int(r.get("same_count",0) or 0) for r in vals),
        }
        return True

    def load(self, obj):
        if not isinstance(obj,dict) or int(obj.get("version",0) or 0) != POST6_VERSION:
            return False
        self.start_from_key = obj.get("start_from_key") if isinstance(obj.get("start_from_key"),str) else None
        self.started_at = obj.get("started_at") if isinstance(obj.get("started_at"),str) else None
        self.pre_reference = obj.get("pre_reference") if isinstance(obj.get("pre_reference"),dict) else None
        self.skipped=max(0,int(obj.get("skipped",0) or 0))
        self.last_result=obj.get("last_result") if isinstance(obj.get("last_result"),dict) else None
        self.last_seen_key=obj.get("last_seen_key") if isinstance(obj.get("last_seen_key"),str) else None
        raw=obj.get("pending",[])
        if isinstance(raw,list):
            self.pending=[dict(x) for x in raw[-10:] if isinstance(x,dict)
                          and isinstance(x.get("origin_key"),str)
                          and isinstance(x.get("group_index"),int) and 0<=x["group_index"]<9
                          and isinstance(x.get("control_index"),int) and 0<=x["control_index"]<9
                          and x.get("group_index") != x.get("control_index")
                          and int(x.get("origin_count",0) or 0)>=6]
        rec=obj.get("records",[])
        if isinstance(rec,list):
            self.records=[dict(r) for r in rec[-POST6_RECORD_MAX:] if isinstance(r,dict)
                          and isinstance(r.get("origin_key"),str) and isinstance(r.get("key"),str)]
        return True

    def dump(self):
        return {
            "version":POST6_VERSION,
            "start_from_key":self.start_from_key,
            "started_at":self.started_at,
            "pre_reference":self.pre_reference,
            "pending":self.pending[-10:],
            "records":self.records[-POST6_RECORD_MAX:],
            "skipped":self.skipped,
            "last_result":self.last_result,
            "last_seen_key":self.last_seen_key,
        }

    def observe_live(self, day, draw_id, nums, open_new=True):
        key=draw_key(day,draw_id)
        if key == self.last_seen_key:
            return None
        counts=self._counts(nums)
        closed=[]
        # POST-6 dura ESATTAMENTE una H1.
        old=list(self.pending)
        self.pending=[]
        for p in old:
            if not sim_draw_is_consecutive(p["origin_key"],day,draw_id):
                self.skipped += 1
                self.last_result={"origin_key":p["origin_key"],"key":key,
                                  "group_index":p["group_index"],"skipped":True}
                continue
            gi=p["group_index"]; ci=p["control_index"]
            same=counts[gi]; control=counts[ci]
            r={
                "origin_key":p["origin_key"],"key":key,
                "group_index":gi,"group":DECINA_LABELS[gi],
                "origin_count":p["origin_count"],
                "control_index":ci,"control_group":DECINA_LABELS[ci],
                "same_count":same,"control_count":control,
                "same_5":same>=5,"same_6":same>=6,
                "control_5":control>=5,"control_6":control>=6,
                "skipped":False,
            }
            self.records.append(r); self.last_result=r; closed.append(r)
        if open_new and self.start_from_key:
            for gi,v in enumerate(counts):
                if v < 6:
                    continue
                choices=[j for j in range(9) if j != gi]
                ci=choices[secrets.randbelow(len(choices))]
                self.pending.append({
                    "origin_key":key,"group_index":gi,"group":DECINA_LABELS[gi],
                    "origin_count":v,"control_index":ci,"control_group":DECINA_LABELS[ci]
                })
        self.records=self.records[-POST6_RECORD_MAX:]
        self.last_seen_key=key
        return closed

    def text(self):
        n=len(self.records)
        s5=sum(int(bool(r.get("same_5"))) for r in self.records)
        s6=sum(int(bool(r.get("same_6"))) for r in self.records)
        c5=sum(int(bool(r.get("control_5"))) for r in self.records)
        c6=sum(int(bool(r.get("control_6"))) for r in self.records)
        sm=sum(int(r.get("same_count",0) or 0) for r in self.records)
        cm=sum(int(r.get("control_count",0) or 0) for r in self.records)
        wins=sum(int(bool(r.get("same_5")) and not bool(r.get("control_5"))) for r in self.records)
        losses=sum(int(bool(r.get("control_5")) and not bool(r.get("same_5"))) for r in self.records)
        ties=n-wins-losses
        lines=[
            "🔥 POST-6 EXTREME SHADOW v1 — STESSA DECINA ALLA H1",
            "Regola congelata: dopo un 6+ segue LA STESSA decina soltanto nella prossima estrazione.",
            f"🧊 Inizio test v10: dopo {self.start_from_key or '-'}" +
            (f" | {self.started_at}" if self.started_at else ""),
            "Vecchi casi POST-BURST non vengono sommati al nuovo test.",
        ]
        pr=self.pre_reference or {}
        pn=int(pr.get("n",0) or 0)
        if pn:
            lines.append(f"📚 RIFERIMENTO PRE-v10 congelato: stessa decina 5+ {pr.get('same5',0)}/{pn} "
                         f"({safe_pct(pr.get('same5',0),pn):.2f}%) | 6+ {pr.get('same6',0)}/{pn} "
                         f"({safe_pct(pr.get('same6',0),pn):.2f}%) | μ {pr.get('same_sum',0)/pn:.2f}/10")
        lines += [
            f"🧪 FORWARD v10+: {n} H1 valutate | pendenti {len(self.pending)} | salti {self.skipped}",
            f"• STESSA DECINA 5+: {s5}/{n} ({safe_pct(s5,n):.2f}%) | teorico 3.981%",
            f"• STESSA DECINA 6+: {s6}/{n} ({safe_pct(s6,n):.2f}%) | teorico 0.701%",
            f"• Media stessa decina: {(sm/n if n else 0):.3f}/10 | teorico 2.222/10",
            f"• CONTROLLO RANDOM 5+: {c5}/{n} ({safe_pct(c5,n):.2f}%) | 6+: {c6}/{n} ({safe_pct(c6,n):.2f}%) | μ {(cm/n if n else 0):.3f}/10",
            f"• Appaiato 5+ POST-6 vs random: +{wins}/-{losses}/={ties}",
        ]
        if n:
            dist=[0]*7
            for r in self.records:
                x=int(r.get("same_count",0) or 0); dist[min(6,max(0,x))]+=1
            lines.append("• Distribuzione stessa H1: " + " | ".join(f"{i}={dist[i]}" for i in range(6)) + f" | 6+={dist[6]}")
            by=[]
            for gi,label in enumerate(DECINA_LABELS):
                vals=[r for r in self.records if r.get("group_index")==gi]
                if vals:
                    by.append(f"{label} {sum(int(bool(r.get('same_5'))) for r in vals)}/{len(vals)}")
            if by:
                lines.append("📍 Per fascia 5+: " + " | ".join(by))
        if self.pending:
            lines.append("⏳ PENDENTI H1:")
            for p in self.pending:
                lines.append(f"• {p['origin_key']} {p['group']}={p['origin_count']}/10 → stessa decina H1 | random {p['control_group']}")
        if self.last_result:
            r=self.last_result
            if r.get("skipped"):
                lines.append(f"🧾 Ultimo: {r['origin_key']} → SALTO, H1 non consecutiva")
            else:
                lines.append(f"🧾 Ultimo: {r['origin_key']} {r['group']} {r['origin_count']}/10 → {r['key']}: "
                             f"stessa {r['same_count']}/10 | random {r['control_count']}/10")
        lines.append("⚠️ Shadow prospettico: non modifica POST-BURST, BURST v3, DUAL, ENGINE o altre previsioni.")
        return "\n".join(lines)


class DecinaBurstLab:
    """BURST v3: selettivo, FLOW REGIME, NO SIGNAL ed EXTREME-6 separato.

    Migra integralmente i risultati v1/v2. Il gate v3 e' calibrato sulla DISTRIBUZIONE
    degli score passati, non sugli esiti futuri: score e margin devono essere
    abbastanza anomali rispetto ai 288 draw di warmup.
    """
    def __init__(self):
        self.pending = None
        self.records = []
        self.last_result = None
        self.warmup = None
        self.totals = {
            "evaluated":0, "skipped":0, "pred5":0, "pred6":0,
            "random5":0, "random6":0, "pred_numbers":0, "random_numbers":0,
            "paired_wins":0, "paired_losses":0, "paired_ties":0,
            "abstained":0, "abstained_any5":0, "abstained_any6":0,
            "extreme_evaluated":0, "extreme_hits":0,
        }
        self.by_group = {label: {"n":0,"hit5":0,"hit6":0,"numbers":0}
                         for label in DECINA_LABELS}

    def load(self, obj):
        if not isinstance(obj, dict) or obj.get("version") not in (1, 2, BURST_VERSION):
            return
        old_version = int(obj.get("version", 1) or 1)
        for name in self.totals:
            x = (obj.get("totals") or {}).get(name)
            if type(x) is int and x >= 0:
                self.totals[name] = x
        old_groups = obj.get("by_group") or {}
        for label, stats in self.by_group.items():
            row = old_groups.get(label) if isinstance(old_groups, dict) else None
            if isinstance(row, dict):
                for name in stats:
                    val = row.get(name)
                    if type(val) is int and val >= 0:
                        stats[name] = val
        rows = obj.get("records")
        if isinstance(rows, list):
            self.records = [r for r in rows if isinstance(r, dict) and isinstance(r.get("key"), str)
                            and type(r.get("group_index")) is int and 0 <= r["group_index"] < 9][-BURST_RECORD_MAX:]
        p = obj.get("pending")
        if (isinstance(p, dict) and isinstance(p.get("from_key"), str) and
            type(p.get("group_index")) is int and 0 <= p["group_index"] < 9 and
            type(p.get("control_index")) is int and 0 <= p["control_index"] < 9):
            self.pending = dict(p)
            # Un pending v1 era sempre un vero segnale: non cambiamo la previsione gia' congelata.
            if old_version == 1:
                self.pending.setdefault("signal", True)
                self.pending.setdefault("model_version", 1)
                self.pending.setdefault("extreme6", False)
        self.warmup = obj.get("warmup") if isinstance(obj.get("warmup"), dict) else None

    def dump(self):
        return {"version":BURST_VERSION, "pending":self.pending, "warmup":self.warmup,
                "records":self.records[-BURST_RECORD_MAX:],
                "totals":self.totals, "by_group":self.by_group}

    @staticmethod
    def _score_snapshot(snapshot):
        ov = snapshot.get("overview") or []
        if len(ov) != 9:
            return []
        # cross-sectional z delle finestre recenti: in ogni draw le nove decine
        # dividono sempre gli stessi 20 numeri, quindi lo scarto relativo e' informativo.
        vals8 = [r["avg8"] for r in ov]
        vals40 = [r["avg40"] for r in ov]
        m8 = sum(vals8)/9; m40 = sum(vals40)/9
        sd8 = math.sqrt(sum((x-m8)**2 for x in vals8)/9) or 1.0
        sd40 = math.sqrt(sum((x-m40)**2 for x in vals40)/9) or 1.0
        scored = []
        for i, row in enumerate(ov):
            state = str(min(5, int(row["recent"])))
            cond = row["state_transitions"][state]
            # shrink robusto verso comportamento teorico: il warmup non puo' dare
            # un vantaggio enorme a una transizione vista poche volte.
            post5 = (cond["hit5"] + 120*BURST_BASE_5) / (cond["n"] + 120)
            cond_lift = (post5-BURST_BASE_5) / BURST_BASE_5
            cross8 = (row["avg8"]-m8)/sd8
            cross40 = (row["avg40"]-m40)/sd40
            accel = row["accel8_40"]
            trans_dom = (row["next_dom_shrink"] - 1/9) / (1/9)
            drought = min(1.5, row["gap5"]/40.0)
            streak = min(3, row["streak_high"])/3.0

            # FLOW REGIME globale: misura cosa e' successo alla STESSA fascia nella H1
            # successiva quando il sistema era nello stesso regime. Forte shrink per
            # evitare che pochi casi di warmup creino score eccessivi.
            rg = snapshot.get("current_regime") or {}
            rs = (snapshot.get("regime_stats") or {}).get(rg.get("name"), {})
            rn = int(rs.get("n",0) or 0)
            g5 = (rs.get("next_group5") or [0]*9)[i] if rn else 0
            post_rg5 = (g5 + 160*BURST_BASE_5) / (rn + 160)
            rg_group_lift = (post_rg5-BURST_BASE_5)/BURST_BASE_5
            # Intensita' globale del regime: puo' alzare/abbassare la propensione a
            # emettere SIGNAL, ma non sceglie da sola la fascia. Baseline any-5
            # ricavata empiricamente dal warmup totale per evitare assunzioni indebite.
            all_rs = snapshot.get("regime_stats") or {}
            base_num = sum(int(x.get("next_any5",0) or 0) for x in all_rs.values())
            base_den = sum(int(x.get("n",0) or 0) for x in all_rs.values())
            base_any5 = (base_num/base_den) if base_den else 0.335
            rg_any5 = (int(rs.get("next_any5",0) or 0)+40*base_any5)/(rn+40) if rn else base_any5
            rg_global_lift = (rg_any5-base_any5)/max(0.05,base_any5)

            # Punteggio complesso ma regolarizzato. Nessun termine usa la H1 futura.
            raw = (0.23*cross8 + 0.15*cross40 + 0.19*accel +
                   0.11*max(-1.5, min(1.5, cond_lift)) +
                   0.08*max(-1.5, min(1.5, trans_dom)) +
                   0.06*streak + 0.05*drought +
                   0.09*max(-1.5, min(1.5, rg_group_lift)) +
                   0.04*max(-1.5, min(1.5, rg_global_lift)))
            scored.append((max(-3.0, min(3.0, raw)), i))
        return sorted(scored, key=lambda x:(-x[0], x[1]))

    @classmethod
    def _calibrate_gate(cls, rows):
        top_scores = []
        margins = []
        # Replay puramente cronologico: score al tempo t usa solo draw <=t.
        # Campioniamo al massimo 48 punti del warmup: stessa logica, costo stabile.
        start = max(80, len(rows)-220)
        candidates = list(range(start, len(rows)-1))
        if len(candidates) > 48:
            step = int(math.ceil(len(candidates)/48.0))
            candidates = candidates[::step]
        for end in candidates:
            prefix = rows[max(0, end-FLOW_WARMUP+1):end+1]
            if len(prefix) < 80:
                continue
            snap = DecinaFlowLab.build_snapshot_from_rows(prefix)
            ranks = cls._score_snapshot(snap or {})
            if len(ranks) < 2:
                continue
            top_scores.append(ranks[0][0])
            margins.append(ranks[0][0]-ranks[1][0])
        score_thr = _decina_quantile(top_scores, BURST_GATE_SCORE_Q)
        margin_thr = _decina_quantile(margins, BURST_GATE_MARGIN_Q)
        extreme_thr = _decina_quantile(top_scores, BURST_EXTREME_SCORE_Q)
        return {"n":len(top_scores), "score_threshold":score_thr,
                "margin_threshold":margin_thr, "extreme_threshold":extreme_thr,
                "score_q":BURST_GATE_SCORE_Q, "margin_q":BURST_GATE_MARGIN_Q,
                "extreme_q":BURST_EXTREME_SCORE_Q}

    def bootstrap(self, history, flow=None):
        rows = _decina_history_rows(history, BURST_WARMUP)
        if rows is None:
            self.warmup = {"ready":False, "available":min(len(history), BURST_WARMUP),
                           "required":BURST_WARMUP, "reason":"storico insufficiente o anomalo"}
            return False
        if flow is not None:
            flow.bootstrap(history)
            snap = flow.last_snapshot
        else:
            snap = DecinaFlowLab.build_snapshot_from_rows(rows)
        if not snap or not snap.get("ready"):
            self.warmup = {"ready":False, "available":len(rows), "required":BURST_WARMUP,
                           "reason":"FLOW non disponibile"}
            return False
        gate = self._calibrate_gate(rows)
        overview = []
        for row in snap.get("overview", []):
            overview.append({
                "label":row["label"], "last8":row["last8"], "last40":row["last40"],
                "last160":row["last160"], "last288":row["last288"], "recent":row["recent"],
                "events5":row["events5"], "events6":row["events6"],
                "gap5":row["gap5"], "gap6":row["gap6"], "delta":row["delta"],
                "avg8":row["avg8"], "avg40":row["avg40"], "streak_high":row["streak_high"]
            })
        self.warmup = {"ready":True, "required":BURST_WARMUP, "available":len(rows),
                       "last_key":rows[-1][0], "overview":overview,
                       "gate":gate, "flow_snapshot":snap}
        return True

    def arm(self, history, key, flow=None):
        if self.pending is not None:
            return self.pending if self.pending.get("from_key") == key else None
        if not history or history[-1].get("key") != key or not self.bootstrap(history, flow=flow):
            return None
        snap = self.warmup.get("flow_snapshot") or {}
        ranks = self._score_snapshot(snap)
        if len(ranks) < 2:
            return None
        top_score, idx = ranks[0]
        second_score, second_idx = ranks[1]
        margin = top_score-second_score
        gate = self.warmup.get("gate") or {}
        calibrated = int(gate.get("n",0) or 0) >= BURST_MIN_CALIBRATION
        score_thr = float(gate.get("score_threshold", 0.0) or 0.0)
        margin_thr = float(gate.get("margin_threshold", 0.0) or 0.0)
        extreme_thr = float(gate.get("extreme_threshold", score_thr) or score_thr)
        signal = bool(calibrated and top_score >= score_thr and margin >= margin_thr and top_score > 0)
        extreme6 = bool(signal and top_score >= extreme_thr and margin >= margin_thr)
        if not calibrated:
            gate_reason = "UNCALIBRATED"
        elif top_score <= 0:
            gate_reason = "NONPOSITIVE"
        elif top_score < score_thr and margin < margin_thr:
            gate_reason = "BOTH_FAIL"
        elif top_score < score_thr:
            gate_reason = "SCORE_FAIL"
        elif margin < margin_thr:
            gate_reason = "MARGIN_FAIL"
        else:
            gate_reason = "PASS"
        ctrl = secrets.randbelow(len(DECINA_GROUPS))
        feat = (snap.get("overview") or [{}]*9)[idx]
        self.pending = {
            "from_key":key, "group_index":idx, "control_index":ctrl,
            "signal":signal, "extreme6":extreme6, "model_version":BURST_VERSION,
            "gate_audit_version":BURST_GATE_AUDIT_VERSION, "gate_reason":gate_reason,
            "index":round(top_score,4), "second_index":round(second_score,4),
            "second_group_index":second_idx, "margin":round(margin,4),
            "score_threshold":round(score_thr,4), "margin_threshold":round(margin_thr,4),
            "score_delta":round(top_score-score_thr,4),
            "margin_delta":round(margin-margin_thr,4),
            "extreme_threshold":round(extreme_thr,4), "calibration_n":int(gate.get("n",0) or 0),
            "warmup_draws":self.warmup["available"], "created_at":now_txt(),
            "flow": {"recent":feat.get("recent"), "delta":feat.get("delta"),
                     "avg8":feat.get("avg8"), "avg40":feat.get("avg40"),
                     "gap5":feat.get("gap5"), "gap6":feat.get("gap6"),
                     "streak_high":feat.get("streak_high")},
            "flow_regime": dict(snap.get("current_regime") or {}),
        }
        return self.pending

    def settle(self, day, draw_id, nums):
        p = self.pending
        if p is None:
            return None
        self.pending = None
        key = draw_key(day, draw_id)
        if not sim_draw_is_consecutive(p["from_key"], day, draw_id):
            self.totals["skipped"] += 1
            self.last_result = {"key":key, "skipped":True, "signal":bool(p.get("signal", True))}
            return self.last_result
        actual = set(int(n) for n in nums)
        idx = p["group_index"]
        count = len(actual.intersection(DECINA_GROUPS[idx]))
        rc = len(actual.intersection(DECINA_GROUPS[p["control_index"]]))
        all_counts = [len(actual.intersection(g)) for g in DECINA_GROUPS]
        signal = bool(p.get("signal", True))  # v1 pending migrato => vero segnale
        extreme6 = bool(p.get("extreme6", False))
        r = {"key":key, "from_key":p["from_key"], "group_index":idx,
             "group":DECINA_LABELS[idx], "control_index":p["control_index"],
             "count":count, "control_count":rc, "hit5":count>=5, "hit6":count>=6,
             "control5":rc>=5, "control6":rc>=6, "signal":signal,
             "extreme6":extreme6, "index":p.get("index"), "margin":p.get("margin"),
             "second_index":p.get("second_index"),
             "score_threshold":p.get("score_threshold"),
             "margin_threshold":p.get("margin_threshold"),
             "score_delta":p.get("score_delta"), "margin_delta":p.get("margin_delta"),
             "gate_reason":p.get("gate_reason"),
             "gate_audit_version":p.get("gate_audit_version"),
             "calibration_n":p.get("calibration_n"),
             "flow_regime":dict(p.get("flow_regime") or {}),
             "flow":dict(p.get("flow") or {}),
             "any5":max(all_counts)>=5, "any6":max(all_counts)>=6, "max_count":max(all_counts)}
        self.records.append(r)
        self.records = self.records[-BURST_RECORD_MAX:]
        t = self.totals
        if signal:
            t["evaluated"] += 1
            t["pred5"] += int(count>=5); t["pred6"] += int(count>=6)
            t["random5"] += int(rc>=5); t["random6"] += int(rc>=6)
            t["pred_numbers"] += count; t["random_numbers"] += rc
            t["paired_wins"] += int(count>=5 and rc<5)
            t["paired_losses"] += int(count<5 and rc>=5)
            t["paired_ties"] += int((count>=5)==(rc>=5))
            if extreme6:
                t["extreme_evaluated"] += 1
                t["extreme_hits"] += int(count>=6)
            g = self.by_group[DECINA_LABELS[idx]]
            g["n"] += 1; g["hit5"] += int(count>=5); g["hit6"] += int(count>=6); g["numbers"] += count
        else:
            t["abstained"] += 1
            t["abstained_any5"] += int(max(all_counts)>=5)
            t["abstained_any6"] += int(max(all_counts)>=6)
        self.last_result = r
        return r

    def text(self):
        w = self.warmup or {}
        t = self.totals
        n = t["evaluated"]
        abst = t.get("abstained", 0)
        decisions = n + abst
        lines = ["🔟 DECINA BURST EVENT DETECTOR v3 + FLOW REGIME — H1 SHADOW",
                 "Obiettivo: segnalare SOLO configurazioni selettive per 5+; EXTREME-6 separato.",
                 f"📚 WARMUP/FLOW: {w.get('available',0)}/{BURST_WARMUP} | " +
                 ("READY" if w.get("ready") else "NON PRONTO: "+w.get("reason","storico assente"))]
        p = self.pending
        if p:
            i = p["group_index"]; c = p["control_index"]
            status = "✅ SIGNAL" if p.get("signal", True) else "⏸ NO SIGNAL"
            lines.extend([f"{status} dopo {p['from_key']}: candidato {DECINA_LABELS[i]}",
                          "Numeri: "+" ".join(f"{x:02d}" for x in DECINA_GROUPS[i]),
                          f"Score {float(p.get('index',0)):+.3f} | #2 {float(p.get('second_index',0)):+.3f} | "
                          f"gap {float(p.get('margin',0)):+.3f}",
                          f"Gate: score≥{float(p.get('score_threshold',0)):+.3f} e gap≥{float(p.get('margin_threshold',0)):+.3f} "
                          f"(calibrazione {p.get('calibration_n',0)})",
                          f"🔥 EXTREME-6: {'ON' if p.get('extreme6') else 'OFF'} | soglia score≥{float(p.get('extreme_threshold',0)):+.3f}",
                          f"🧪 Controllo casuale congelato: {DECINA_LABELS[c]}"])
            f = p.get("flow") or {}
            lines.append(f"🌊 FLOW candidato: ultimo {f.get('recent','-')} | Δ1 {f.get('delta','-')} | "
                         f"media8 {float(f.get('avg8',0)):.2f} | media40 {float(f.get('avg40',0)):.2f} | "
                         f"gap5 {f.get('gap5','-')} | streak≥3 {f.get('streak_high','-')}")
            rg = p.get("flow_regime") or {}
            lines.append(f"🧭 FLOW REGIME congelato: {rg.get('name','-')} {rg.get('strength','')} | "
                         f"spread {rg.get('spread','-')} | min/max {rg.get('min','-')}/{rg.get('max','-')} | "
                         f"σ {float(rg.get('sd',0)):.2f}")
        elif w.get("ready"):
            lines.append("⏸ Nessuna decisione H1 congelata: attendo il prossimo draw live.")

        if w.get("ready"):
            lines.append("📦 WARMUP 288: presenze 8/40/160/288 | 5+/6+ | gap5:")
            for row in w.get("overview", []):
                lines.append(f"• {row['label']}: {row['last8']}/{row['last40']}/{row['last160']}/{row['last288']} "
                             f"| {row['events5']}/{row['events6']} | {row['gap5']}")
        coverage = safe_pct(n, decisions)
        lines.extend([f"📊 FORWARD LIVE: segnali valutati {n} | NO SIGNAL {abst} | copertura {coverage:.2f}% | salti {t['skipped']}",
                      f"• SIGNAL 5+: {t['pred5']}/{n} ({safe_pct(t['pred5'],n):.2f}%) | random {t['random5']}/{n} ({safe_pct(t['random5'],n):.2f}%)",
                      f"• SIGNAL 6+: {t['pred6']}/{n} ({safe_pct(t['pred6'],n):.2f}%) | random {t['random6']}/{n} ({safe_pct(t['random6'],n):.2f}%)",
                      f"• Media numeri nei SIGNAL: {t['pred_numbers']/n if n else 0:.3f}/10 | random {t['random_numbers']/n if n else 0:.3f}/10",
                      f"• EXTREME-6: {t.get('extreme_hits',0)}/{t.get('extreme_evaluated',0)}",
                      f"• NO SIGNAL con almeno una decina 5+/6+ nel draw: {t.get('abstained_any5',0)}/{t.get('abstained_any6',0)} su {abst}",
                      f"• Teorico decina preselezionata: 5+ {100*BURST_BASE_5:.3f}% | 6+ {100*BURST_BASE_6:.3f}% | media 2.222/10"])
        if self.last_result:
            r = self.last_result
            if r.get("skipped"):
                lines.append(f"🧾 Ultima H1 {r['key']}: salto, nessun HIT attribuito.")
            elif r.get("signal"):
                lines.append(f"🧾 Ultima H1 {r['key']}: SIGNAL {r['group']} {r['count']}/10 | random {r['control_count']}/10")
            else:
                lines.append(f"🧾 Ultima H1 {r['key']}: NO SIGNAL | candidato shadow {r['group']} {r['count']}/10 | max decina reale {r['max_count']}/10")
        if n:
            lines.append("📍 RISULTATI PER FASCIA — solo SIGNAL congelati:")
            for label, s in self.by_group.items():
                if s["n"]:
                    lines.append(f"• {label}: 5+ {s['hit5']}/{s['n']} | 6+ {s['hit6']}/{s['n']} | media {s['numbers']/s['n']:.2f}")
        lines.append("⚠️ Warmup/FLOW sono descrittivi; risultati v1 conservati, v2 resta shadow e non effettua puntate.")
        return "\n".join(lines)



# ============================================================
# BURST GATE LAB v4 — AUDIT PROSPETTICO DEL GATE, NON CAMBIA BURST v3
# Da v9 ogni NUOVA decisione BURST salva soglia e distanza dalla soglia.
# I record precedenti restano utilizzabili soltanto per una mappa descrittiva
# dello score assoluto: non ricostruiamo soglie storiche che non erano salvate.
# ============================================================
class BurstGateLab:
    REASON_ORDER = ("PASS", "SCORE_FAIL", "MARGIN_FAIL", "BOTH_FAIL", "NONPOSITIVE", "UNCALIBRATED")

    @staticmethod
    def _valid_num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))

    @staticmethod
    def _rate(k, n):
        return f"{k}/{n} ({safe_pct(k,n):.2f}%)" if n else "0/0"

    @classmethod
    def _summary(cls, rows):
        n = len(rows)
        h5 = sum(int(r.get("count", 0) >= 5) for r in rows)
        h6 = sum(int(r.get("count", 0) >= 6) for r in rows)
        c5 = sum(int(r.get("control_count", 0) >= 5) for r in rows)
        any5 = sum(int(bool(r.get("any5"))) for r in rows)
        mean = (sum(int(r.get("count", 0)) for r in rows)/n) if n else 0.0
        return n, h5, h6, c5, any5, mean

    @classmethod
    def _fmt(cls, rows):
        n,h5,h6,c5,any5,mean = cls._summary(rows)
        return (f"n={n} | 5+ {cls._rate(h5,n)} | 6+ {cls._rate(h6,n)} | "
                f"μ {mean:.2f}/10 | random5 {cls._rate(c5,n)} | any5 {cls._rate(any5,n)}")

    @classmethod
    def text(cls, engine):
        all_rows = [r for r in engine.burst.records if isinstance(r, dict) and not r.get("skipped")
                    and type(r.get("count")) is int and type(r.get("control_count")) is int
                    and type(r.get("signal")) is bool]
        exact = [r for r in all_rows if r.get("gate_audit_version") == BURST_GATE_AUDIT_VERSION
                 and cls._valid_num(r.get("score_delta")) and cls._valid_num(r.get("margin_delta"))]

        lines = [
            "🔬 BURST GATE LAB v4 — AUDIT PROSPETTICO",
            "Non modifica BURST v3: misura DOVE il gate sta scartando o accettando i candidati.",
            "Da v9 soglie e delta sono congelati insieme alla previsione; nessun backfill delle soglie vecchie.",
            "",
            f"📊 AUDIT ESATTO v9+: {len(exact)} decisioni valutate",
            "Riferimento una decina: 5+ 3.981% | 6+ 0.701% | media 2.222/10",
        ]
        if exact:
            lines += ["", "🚦 PER MOTIVO DEL GATE"]
            for reason in cls.REASON_ORDER:
                rows = [r for r in exact if str(r.get("gate_reason")) == reason]
                if rows:
                    lines.append(f"• {reason}: {cls._fmt(rows)}")

            lines += ["", "📏 DISTANZA SCORE DALLA SOGLIA (score − soglia)"]
            bands = [
                ("≤ -0.30", lambda x: x <= -0.30),
                ("-0.30…-0.15", lambda x: -0.30 < x <= -0.15),
                ("-0.15…-0.05", lambda x: -0.15 < x <= -0.05),
                ("-0.05…0", lambda x: -0.05 < x < 0),
                ("0…+0.10", lambda x: 0 <= x < 0.10),
                ("≥ +0.10", lambda x: x >= 0.10),
            ]
            for label, fn in bands:
                rows = [r for r in exact if fn(float(r["score_delta"]))]
                if rows:
                    lines.append(f"• {label}: {cls._fmt(rows)}")

            no = [r for r in exact if not r.get("signal")]
            near = [r for r in no if -0.10 <= float(r["score_delta"]) < 0]
            deep = [r for r in no if float(r["score_delta"]) < -0.10]
            margin_block = [r for r in no if float(r["score_delta"]) >= 0 and float(r["margin_delta"]) < 0]
            lines += ["", "🧪 NO SIGNAL — DOVE SONO I 5+?",
                      f"• quasi soglia score [-0.10,0): {cls._fmt(near)}",
                      f"• score più lontano (<-0.10): {cls._fmt(deep)}",
                      f"• score passa ma gap blocca: {cls._fmt(margin_block)}"]

            regimes = Counter(str((r.get("flow_regime") or {}).get("name") or "-") for r in exact if r.get("count",0) >= 5)
            if regimes:
                lines.append("• Regimi dei 5+ v9+: " + ", ".join(f"{k}={v}" for k,v in regimes.most_common()))
        else:
            lines += ["", "⏳ Nessun esito v9 ancora valutato: il primo dato arriverà dopo la prima H1 nata con questa versione."]

        legacy = [r for r in all_rows if cls._valid_num(r.get("index"))]
        lines += ["", f"🗺 SCORE ASSOLUTO — descrittivo su {len(legacy)} record conservati"]
        abs_bands = [
            ("<0", lambda x: x < 0),
            ("0…0.25", lambda x: 0 <= x < 0.25),
            ("0.25…0.50", lambda x: 0.25 <= x < 0.50),
            ("0.50…0.75", lambda x: 0.50 <= x < 0.75),
            ("≥0.75", lambda x: x >= 0.75),
        ]
        for label, fn in abs_bands:
            rows = [r for r in legacy if fn(float(r["index"]))]
            if rows:
                sig = sum(int(bool(r.get("signal"))) for r in rows)
                n,h5,h6,c5,any5,mean = cls._summary(rows)
                lines.append(f"• score {label}: n={n} | SIGNAL {sig} | 5+ {h5}/{n} | 6+ {h6}/{n} | μ {mean:.2f} | random5 {c5}/{n}")

        lines += ["", "⚠️ Il LAB osserva il gate; non inverte soglie e non apre puntate. Prima di cambiare regola servono nuovi risultati prospettici."]
        return "\n".join(lines)


# ============================================================
# VERIFICA v1 — SOLO AUDIT, senza previsioni o backfill di HIT.
# Marker permanente sulla storia nota al primo avvio: una previsione
# gia' congelata prima dell'installazione NON e' nel nuovo test.
# Usa i records originali DECINA/ENGINE H5/BURST, mai i totali aggregati
# del warmup; confronto sullo stesso draw per tutti i controlli.
# ============================================================
VERIFICA_VERSION = 1
VERIFICA_TEST_TARGET = 300


def _verifica_order(key):
    try:
        day, seq = str(key).rsplit('#', 1)
        datetime.fromisoformat(day)
        return day, int(seq)
    except (ValueError, TypeError, AttributeError):
        return None


class VerificationLab:
    def __init__(self):
        self.start_from_key = None
        self.started_at = None
        self.old_counts = {}

    def load(self, obj):
        if not isinstance(obj, dict) or obj.get('version') != VERIFICA_VERSION:
            return False
        key = obj.get('start_from_key')
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = str(obj.get('started_at') or '')
        raw = obj.get('old_counts') or {}
        self.old_counts = dict(raw) if isinstance(raw, dict) else {}
        return True

    def dump(self):
        return {'version': VERIFICA_VERSION, 'start_from_key': self.start_from_key,
                'started_at': self.started_at, 'old_counts': dict(self.old_counts)}

    def ensure_start(self, engine):
        if self.start_from_key is not None:
            return False
        history = engine.engine_history
        if not history or _verifica_order(history[-1].get('key')) is None:
            return False
        self.start_from_key = str(history[-1]['key'])
        self.started_at = now_txt()
        self.old_counts = {
            'decina': int(engine.decina.totals.get('evaluated', 0)),
            'dual': int(engine.dual.totals.get('evaluated', 0)),
            'burst_signal': int(engine.burst.totals.get('evaluated', 0)),
            'burst_nosignal': int(engine.burst.totals.get('abstained', 0)),
            'engine_h5': len(engine.engine_h5_records_live),
        }
        return True

    def _new(self, key):
        origin = _verifica_order(key)
        marker = _verifica_order(self.start_from_key)
        return origin is not None and marker is not None and origin > marker

    @staticmethod
    def _rate(n, total):
        return f'{n}/{total} ({safe_pct(n,total):.2f}%)' if total else '0/0 (in attesa)'

    @staticmethod
    def _pair_summary(records, name):
        n = len(records)
        a = sum(int((r.get('counts') or {}).get(name, 0) > 0) for r in records)
        d = sum(int((r.get('counts') or {}).get('original', 0) > 0) for r in records)
        c = sum(int((r.get('counts') or {}).get('random', 0) > 0) for r in records)
        wins = sum(int((r.get('counts') or {}).get(name,0) > 0 and
                       (r.get('counts') or {}).get('random',0) == 0) for r in records)
        losses = sum(int((r.get('counts') or {}).get(name,0) == 0 and
                         (r.get('counts') or {}).get('random',0) > 0) for r in records)
        return n, a, d, c, wins, losses

    def text(self, engine):
        if self.start_from_key is None:
            self.ensure_start(engine)
        if self.start_from_key is None:
            return ('🧪 VERIFICA v1 — IN ATTESA DEL PRIMO STORICO\n'
                    'Il test partira quando il bot avra una H1 di origine valida.\n'
                    'Nessun risultato precedente viene cancellato.')

        d_rows = [r for r in engine.decina.records if self._new(r.get('from_key')) and
                  isinstance(r.get('counts'), dict) and
                  all(k in r['counts'] and type(r['counts'][k]) is int
                      for k in ('fusion', 'within', 'original', 'random'))]
        h_rows = [r for r in engine.engine_h5_records_live if
                  r.get('origin_mode') == 'live' and self._new(r.get('signal_from_key')) and
                  isinstance(r.get('hits5'), int)]
        b_rows = [r for r in engine.burst.records if self._new(r.get('from_key')) and
                  not r.get('skipped') and type(r.get('count')) is int and
                  type(r.get('control_count')) is int and
                  type(r.get('signal')) is bool]
        signal = [r for r in b_rows if r['signal']]
        no = [r for r in b_rows if not r['signal']]

        lines = ['🧪 VERIFICA v1 — TEST PROSPETTICO, REGOLE INVARIATE',
                 f'Inizio congelato: dopo {self.start_from_key} | {self.started_at}',
                 'Solo previsioni ORIGINATE dopo il marker; warmup e vecchi pending esclusi.',
                 'Nessun reset: /dual /decine /engineh /burst mostrano anche lo storico vecchio.',
                 '', '🔟 DUAL STESSA DECINA — obiettivo >=1 fra 2 numeri H1']
        n,a,orig,ctrl,w,l = self._pair_summary(d_rows, 'within')
        lines += [f'Nuovo test: {n}/{VERIFICA_TEST_TARGET} confronti (completamento {safe_pct(min(n,VERIFICA_TEST_TARGET),VERIFICA_TEST_TARGET):.1f}%)',
                  f'STESSA DECINA {self._rate(a,n)} | DUAL originale {self._rate(orig,n)}',
                  f'RANDOM appaiato {self._rate(ctrl,n)} | teorico 39.70%',
                  f'STESSA DECINA vs RANDOM: +{w}/-{l}/={n-w-l} (esiti >=1).']
        for width in (50,100,300):
            recent=d_rows[-width:]
            rn, ra, ro, rc, rw, rl=self._pair_summary(recent, 'within')
            label='FINESTRA COMPLETA' if rn == width else 'PARZIALE'
            lines.append(f'Ultimi {width} ({label}, n={rn}): stessa {ra}/{rn}, original {ro}/{rn}, random {rc}/{rn}')
        if n:
            base=self._pair_summary(d_rows,'fusion')
            lines.append(f'DUAL+DECINE sullo stesso periodo: {base[1]}/{base[0]} (diagnostica).')
        if len(d_rows) < len([r for r in engine.decina.records if self._new(r.get('from_key'))]):
            lines.append('Avviso: alcuni record DECINA del nuovo periodo non sono confrontabili e sono esclusi.')
        lines += ['', '🎯 ENGINE HIGH CONFIDENCE H5 — nuove sessioni CHIUSE',
                  f'Completate {len(h_rows)} | attive create dopo marker: '+str(sum(
                   1 for x in engine.engine_h5_sessions if x.get('origin_mode')=='live' and
                   self._new(x.get('signal_from_key')))),
                  f'Almeno 1 uscita entro H5: {self._rate(sum(r["hits5"]>=1 for r in h_rows),len(h_rows))} | teorico 71.54%',
                  f'Almeno 2 uscite entro H5: {self._rate(sum(r["hits5"]>=2 for r in h_rows),len(h_rows))} | teorico 30.88%',
                  f'Esattamente 2 uscite: {self._rate(sum(r["hits5"]==2 for r in h_rows),len(h_rows))} | teorico 23.23%',
                  'H5: ogni sessione entra nel test solo se la sua previsione nasce DOPO il marker.']
        for width in (50,100,300):
            recent=h_rows[-width:]
            rn=len(recent)
            label='FINESTRA COMPLETA' if rn==width else 'PARZIALE'
            lines.append(f'H5 ultimi {width} ({label}, n={rn}): >=1 {sum(r["hits5"]>=1 for r in recent)}/{rn}, >=2 {sum(r["hits5"]>=2 for r in recent)}/{rn}.')
        lines += ['', '🌋 BURST — GATE: SIGNAL vs NO SIGNAL nella stessa H1',
                  f'SIGNAL {len(signal)} | NO SIGNAL {len(no)} | copertura {safe_pct(len(signal),len(b_rows)):.2f}%',
                  f'SIGNAL candidato 5+ {self._rate(sum(r["count"]>=5 for r in signal),len(signal))} | random {self._rate(sum(r["control_count"]>=5 for r in signal),len(signal))}',
                  f'NO SIGNAL candidato SHADOW 5+ {self._rate(sum(r["count"]>=5 for r in no),len(no))} | random {self._rate(sum(r["control_count"]>=5 for r in no),len(no))}',
                  f'SIGNAL candidato 6+ {self._rate(sum(r["count"]>=6 for r in signal),len(signal))} | random {self._rate(sum(r["control_count"]>=6 for r in signal),len(signal))}',
                  f'NO SIGNAL candidato SHADOW 6+ {self._rate(sum(r["count"]>=6 for r in no),len(no))} | random {self._rate(sum(r["control_count"]>=6 for r in no),len(no))}',
                  f'Almeno una delle NOVE decine 5+ nei NO SIGNAL: {self._rate(sum(bool(r.get("any5")) for r in no),len(no))} (evento globale, NON successo del candidato).',
                  'Riferimento per UNA decina preselezionata: 5+ 3.981% | 6+ 0.701%.',
                  'Versioni BURST pre-v8 conservate nei totali storici; questo periodo parte dal nuovo marker.',
                  'Approfondimento score/soglia e motivi del gate: /burstgate']
        lines += ['', '🗂 STORICO PRECEDENTE, NON SOMMATO AL NUOVO TEST',
                  f'Alla partenza: DUAL STESSA DECINA {self.old_counts.get("decina", "-")} draw; '
                  f'DUAL originale {self.old_counts.get("dual", "-")} draw; '
                  f'BURST signal {self.old_counts.get("burst_signal", "-")}, NO SIGNAL {self.old_counts.get("burst_nosignal", "-")}; '
                  f'ENGINE H5 {self.old_counts.get("engine_h5", "-")} completate.',
                  '⚠️ Campioni e finestre parziali mostrati esplicitamente. Risultati shadow: nessuna puntata automatica.']
        return '\n'.join(lines)


# ============================================================
# CONVERGENCE LAB v1 — solo SHADOW, prospettico dalla v11.
# Nasce SOLO quando POST-6 apre un nuovo evento 6+ dopo il marker v11.
# Fotografa, PRIMA della H1, se la stessa decina contiene/concorda con:
#   • ENGINE HIGH CONFIDENCE TOP1
#   • SOSIA rank #1
#   • BURST candidate (e relativo SIGNAL/NO SIGNAL)
#   • coppia STESSA DECINA del DECINA ENGINE
# FLOW viene salvato come contesto, non come "voto" predittivo.
# La H1 misura poi 5+/6+ della stessa decina e del controllo random POST-6.
# Nessun modulo esistente viene modificato.
# ============================================================
CONVERGENCE_VERSION = 1
CONVERGENCE_RECORD_MAX = max(200, int(os.getenv("CONVERGENCE_RECORD_MAX", "2000")))


class ConvergenceLab:
    def __init__(self):
        self.start_from_key = None
        self.started_at = None
        self.pending = []
        self.records = []
        self.skipped = 0
        self.last_result = None

    def ensure_start(self, engine):
        if self.start_from_key:
            return False
        if not engine.engine_history:
            return False
        key = str(engine.engine_history[-1].get("key") or "")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = datetime.now(BOT_TZ).isoformat(timespec="seconds")
        return True

    def load(self, obj):
        if not isinstance(obj, dict) or int(obj.get("version", 0) or 0) != CONVERGENCE_VERSION:
            return False
        key = obj.get("start_from_key")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = obj.get("started_at") if isinstance(obj.get("started_at"), str) else None
        self.skipped = max(0, int(obj.get("skipped", 0) or 0))
        self.last_result = obj.get("last_result") if isinstance(obj.get("last_result"), dict) else None
        raw = obj.get("pending", [])
        if isinstance(raw, list):
            self.pending = [dict(x) for x in raw[-20:] if isinstance(x, dict)
                            and isinstance(x.get("origin_key"), str)
                            and isinstance(x.get("group_index"), int)
                            and 0 <= x["group_index"] < 9
                            and isinstance(x.get("control_index"), int)
                            and 0 <= x["control_index"] < 9]
        rec = obj.get("records", [])
        if isinstance(rec, list):
            self.records = [dict(x) for x in rec[-CONVERGENCE_RECORD_MAX:]
                            if isinstance(x, dict) and isinstance(x.get("origin_key"), str)
                            and isinstance(x.get("key"), str)]
        return True

    def dump(self):
        return {
            "version": CONVERGENCE_VERSION,
            "start_from_key": self.start_from_key,
            "started_at": self.started_at,
            "pending": self.pending[-20:],
            "records": self.records[-CONVERGENCE_RECORD_MAX:],
            "skipped": self.skipped,
            "last_result": self.last_result,
        }

    def _is_after_marker(self, key):
        a = _verifica_order(key)
        b = _verifica_order(self.start_from_key)
        return a is not None and b is not None and a > b

    @staticmethod
    def _same_group(num, gi):
        try:
            return int(num) in DECINA_GROUPS[int(gi)]
        except (TypeError, ValueError, IndexError):
            return False

    def arm(self, current_key, engine):
        if not self.start_from_key:
            self.ensure_start(engine)
        if not self.start_from_key or not self._is_after_marker(current_key):
            return []
        # Solo eventi POST-6 nati ORA: nessun backfill di pending pre-v11.
        origins = [p for p in engine.post6.pending
                   if isinstance(p, dict) and str(p.get("origin_key")) == str(current_key)]
        if not origins:
            return []
        already = {(str(p.get("origin_key")), int(p.get("group_index", -1))) for p in self.pending}
        created = []
        for src in origins:
            gi = int(src["group_index"])
            token = (str(current_key), gi)
            if token in already:
                continue

            ep = engine.engine_pending if isinstance(engine.engine_pending, dict) else {}
            engine_hc = bool(ep.get("accepted") and str(ep.get("signal_from_key")) == str(current_key))
            engine_top1 = int(ep["top1"]) if engine_hc and ep.get("top1") else None
            engine_same = bool(engine_top1 is not None and self._same_group(engine_top1, gi))

            sp = engine.sosiasniper_pending if isinstance(engine.sosiasniper_pending, dict) else {}
            sosia_top1 = int(sp["top1"]) if str(sp.get("from_key")) == str(current_key) and sp.get("top1") else None
            sosia_same = bool(sosia_top1 is not None and self._same_group(sosia_top1, gi))
            fusion_top3 = bool(sp.get("engine_hc") and sp.get("engine_rank") is not None and
                               int(sp.get("engine_rank")) <= 3)

            bp = engine.burst.pending if isinstance(engine.burst.pending, dict) else {}
            burst_same = bool(str(bp.get("from_key")) == str(current_key) and
                              int(bp.get("group_index", -1)) == gi)
            burst_signal_same = bool(burst_same and bp.get("signal"))

            dp = engine.decina.pending if isinstance(engine.decina.pending, dict) else {}
            within_pair = list(dp.get("within_pair") or []) if str(dp.get("from_key")) == str(current_key) else []
            decina_same = bool(len(within_pair) == 2 and all(self._same_group(n, gi) for n in within_pair))

            flow_snap = engine.flow.last_snapshot or engine.flow.warmup or {}
            regime = dict(flow_snap.get("current_regime") or {})
            feat = engine.flow.group_feature(gi) or {}
            state = "SCARICA" if int(feat.get("recent", 0) or 0) <= 1 else (
                    "RICCA" if int(feat.get("recent", 0) or 0) >= 4 else "NORMALE")

            support = int(engine_same) + int(sosia_same) + int(burst_same) + int(decina_same)
            row = {
                "origin_key": str(current_key),
                "group_index": gi,
                "group": DECINA_LABELS[gi],
                "origin_count": int(src.get("origin_count", 0) or 0),
                "control_index": int(src["control_index"]),
                "control_group": DECINA_LABELS[int(src["control_index"])],
                "engine_hc": engine_hc,
                "engine_top1": engine_top1,
                "engine_same": engine_same,
                "sosia_top1": sosia_top1,
                "sosia_same": sosia_same,
                "fusion_top3": fusion_top3,
                "burst_same": burst_same,
                "burst_signal_same": burst_signal_same,
                "burst_score_delta": bp.get("score_delta") if burst_same else None,
                "decina_same": decina_same,
                "within_pair": within_pair if decina_same else None,
                "flow_regime": regime.get("name"),
                "flow_strength": regime.get("strength"),
                "flow_state": state,
                "support": support,
            }
            self.pending.append(row)
            created.append(row)
            already.add(token)
        self.pending = self.pending[-20:]
        return created

    def settle(self, day, draw_id, nums):
        if not self.pending:
            return []
        key = draw_key(day, draw_id)
        actual = set(map(int, nums))
        old = list(self.pending)
        self.pending = []
        closed = []
        for p in old:
            if not sim_draw_is_consecutive(p["origin_key"], day, draw_id):
                self.skipped += 1
                self.last_result = {"origin_key": p["origin_key"], "key": key,
                                    "group_index": p["group_index"], "skipped": True}
                continue
            gi = int(p["group_index"]); ci = int(p["control_index"])
            same = len(actual.intersection(DECINA_GROUPS[gi]))
            ctrl = len(actual.intersection(DECINA_GROUPS[ci]))
            r = dict(p)
            r.update({
                "key": key,
                "same_count": same,
                "same_5": same >= 5,
                "same_6": same >= 6,
                "control_count": ctrl,
                "control_5": ctrl >= 5,
                "control_6": ctrl >= 6,
                "skipped": False,
            })
            self.records.append(r)
            self.last_result = r
            closed.append(r)
        self.records = self.records[-CONVERGENCE_RECORD_MAX:]
        return closed

    @staticmethod
    def _fmt(rows):
        n = len(rows)
        h5 = sum(int(bool(r.get("same_5"))) for r in rows)
        h6 = sum(int(bool(r.get("same_6"))) for r in rows)
        c5 = sum(int(bool(r.get("control_5"))) for r in rows)
        mean = sum(int(r.get("same_count", 0) or 0) for r in rows) / n if n else 0.0
        return f"n={n} | 5+ {h5}/{n} ({safe_pct(h5,n):.2f}%) | 6+ {h6}/{n} ({safe_pct(h6,n):.2f}%) | μ {mean:.2f} | random5 {c5}/{n} ({safe_pct(c5,n):.2f}%)"

    def text(self):
        lines = [
            "🧲 CONVERGENCE LAB v1 — POST-6 + ALTRI MODULI",
            "Solo eventi POST-6 nati dalla v11; nessun backfill.",
            f"🧊 Inizio: dopo {self.start_from_key or '-'}" + (f" | {self.started_at}" if self.started_at else ""),
            f"Valutati {len(self.records)} | pendenti {len(self.pending)} | salti {self.skipped}",
            "Riferimento una decina: 5+ 3.981% | 6+ 0.701%.",
        ]
        if self.records:
            lines.append("📊 PER NUMERO DI CONVERGENZE sulla stessa decina (ENGINE/SOSIA/BURST/DECINA):")
            for k in range(5):
                rows = [r for r in self.records if int(r.get("support", 0) or 0) == k]
                if rows:
                    lines.append(f"• support {k}/4: {self._fmt(rows)}")
            for label, pred in (
                ("ENGINE HC nella decina", lambda r: r.get("engine_same")),
                ("SOSIA #1 nella decina", lambda r: r.get("sosia_same")),
                ("BURST candidato stessa decina", lambda r: r.get("burst_same")),
                ("BURST SIGNAL stessa decina", lambda r: r.get("burst_signal_same")),
                ("DECINA pair stessa fascia", lambda r: r.get("decina_same")),
                ("FUSION TOP3 + ENGINE", lambda r: r.get("fusion_top3") and r.get("engine_same")),
            ):
                rows = [r for r in self.records if pred(r)]
                if rows:
                    lines.append(f"• {label}: {self._fmt(rows)}")
        else:
            lines.append("⏳ Nessun evento POST-6 v11 ancora valutato.")
        if self.pending:
            lines.append("⏳ PENDENTI:")
            for r in self.pending[-5:]:
                flags=[]
                if r.get("engine_same"): flags.append("ENGINE")
                if r.get("sosia_same"): flags.append("SOSIA")
                if r.get("burst_same"): flags.append("BURST" + ("+SIGNAL" if r.get("burst_signal_same") else "+NO"))
                if r.get("decina_same"): flags.append("DECINA")
                lines.append(f"• {r['origin_key']} {r['group']} {r['origin_count']}/10 | support {r['support']}/4 | " + (", ".join(flags) or "nessuna convergenza"))
        lines.append("⚠️ Shadow: misura convergenze, non cambia POST-6, ENGINE, SOSIA, BURST o DECINA.")
        return "\n".join(lines)


# ============================================================
# METODO CONVERGENZA HC v1 — SHADOW PROSPETTICO dalla v13.
# MAIN nasce SOLO quando ENGINE e' HIGH CONFIDENCE e il suo TOP1
# coincide esattamente con SOSIA rank #1 per la medesima H1.
# SUPER e' un MAIN in cui anche BURST e' SIGNAL e la decina BURST
# contiene il numero MAIN. BURST non crea e non blocca MAIN.
# HC_DISAGREE registra il controllo: ENGINE HC ma SOSIA #1 diverso.
# Ogni record congela anche un numero random appaiato PRIMA della H1.
# Nessun backfill: i vecchi segnali restano fuori dal nuovo test.
# ============================================================
HC_METHOD_VERSION = 1
HC_METHOD_RECORD_MAX = max(300, int(os.getenv("HC_METHOD_RECORD_MAX", "3000")))
HC_METHOD_NOTIFY = os.getenv("HC_METHOD_NOTIFY", "1").strip().lower() not in {"0", "false", "no", "off"}


class HCConvergenceMethod:
    def __init__(self):
        self.start_from_key = None
        self.started_at = None
        self.pending = []
        self.records = []
        self.skipped = 0
        self.missing_context = 0
        self.last_result = None

    def ensure_start(self, engine):
        if self.start_from_key:
            return False
        if not engine.engine_history:
            return False
        key = str(engine.engine_history[-1].get("key") or "")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = datetime.now(BOT_TZ).isoformat(timespec="seconds")
        return True

    def load(self, obj):
        if not isinstance(obj, dict) or int(obj.get("version", 0) or 0) != HC_METHOD_VERSION:
            return False
        key = obj.get("start_from_key")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = obj.get("started_at") if isinstance(obj.get("started_at"), str) else None
        self.skipped = max(0, int(obj.get("skipped", 0) or 0))
        self.missing_context = max(0, int(obj.get("missing_context", 0) or 0))
        self.last_result = obj.get("last_result") if isinstance(obj.get("last_result"), dict) else None
        raw = obj.get("pending", [])
        if isinstance(raw, list):
            self.pending = [dict(x) for x in raw[-20:] if isinstance(x, dict)
                            and isinstance(x.get("origin_key"), str)
                            and x.get("engine_top1") and x.get("sosia_top1")
                            and x.get("control_num")]
        rec = obj.get("records", [])
        if isinstance(rec, list):
            self.records = [dict(x) for x in rec[-HC_METHOD_RECORD_MAX:]
                            if isinstance(x, dict) and isinstance(x.get("origin_key"), str)
                            and isinstance(x.get("key"), str)]
        return True

    def dump(self):
        return {
            "version": HC_METHOD_VERSION,
            "start_from_key": self.start_from_key,
            "started_at": self.started_at,
            "pending": self.pending[-20:],
            "records": self.records[-HC_METHOD_RECORD_MAX:],
            "skipped": self.skipped,
            "missing_context": self.missing_context,
            "last_result": self.last_result,
        }

    def _is_after_marker(self, key):
        a = _verifica_order(key)
        b = _verifica_order(self.start_from_key)
        return a is not None and b is not None and a > b

    @staticmethod
    def _burst_group_contains(bp, num):
        if not isinstance(bp, dict):
            return False
        try:
            gi = int(bp.get("group_index", -1))
            return 0 <= gi < len(DECINA_GROUPS) and int(num) in DECINA_GROUPS[gi]
        except (TypeError, ValueError, IndexError):
            return False

    def arm(self, current_key, engine):
        if not self.start_from_key:
            self.ensure_start(engine)
        if not self.start_from_key or not self._is_after_marker(current_key):
            return None

        # Un record per origine al massimo, anche dopo restart.
        if any(str(x.get("origin_key")) == str(current_key) for x in self.pending):
            return None
        if any(str(x.get("origin_key")) == str(current_key) for x in self.records[-20:]):
            return None

        ep = engine.engine_pending if isinstance(engine.engine_pending, dict) else {}
        if not (ep.get("accepted") and str(ep.get("signal_from_key")) == str(current_key)):
            return None
        try:
            engine_top1 = int(ep.get("top1"))
        except (TypeError, ValueError):
            self.missing_context += 1
            return None

        sp = engine.sosiasniper_pending if isinstance(engine.sosiasniper_pending, dict) else {}
        if str(sp.get("from_key")) != str(current_key) or not sp.get("top1"):
            self.missing_context += 1
            return None
        try:
            sosia_top1 = int(sp.get("top1"))
        except (TypeError, ValueError):
            self.missing_context += 1
            return None

        agreement = engine_top1 == sosia_top1
        bp = engine.burst.pending if isinstance(engine.burst.pending, dict) else {}
        burst_same_origin = str(bp.get("from_key")) == str(current_key)
        burst_signal = bool(burst_same_origin and bp.get("signal"))
        burst_contains = bool(burst_same_origin and self._burst_group_contains(bp, engine_top1))
        super_signal = bool(agreement and burst_signal and burst_contains)
        signal_type = "SUPER" if super_signal else ("MAIN" if agreement else "HC_DISAGREE")

        pool = [n for n in range(1, 91) if n != engine_top1]
        control_num = int(SOSIA_RANDOM.choice(pool))
        gi = None
        if burst_same_origin:
            try:
                v = int(bp.get("group_index", -1))
                if 0 <= v < len(DECINA_GROUPS):
                    gi = v
            except (TypeError, ValueError):
                gi = None

        row = {
            "origin_key": str(current_key),
            "created_at": now_txt(),
            "engine_top1": engine_top1,
            "engine_confidence": ep.get("confidence"),
            "engine_threshold": ep.get("threshold"),
            "engine_support": ep.get("support"),
            "sosia_top1": sosia_top1,
            "sosia_score": sp.get("score"),
            "sosia_consensus": sp.get("consensus"),
            "agreement": agreement,
            "signal_type": signal_type,
            "is_main": agreement,
            "is_super": super_signal,
            "burst_signal": burst_signal,
            "burst_contains": burst_contains,
            "burst_group_index": gi,
            "burst_group": DECINA_LABELS[gi] if gi is not None else None,
            "burst_score": bp.get("score") if burst_same_origin else None,
            "burst_gap": bp.get("gap") if burst_same_origin else None,
            "control_num": control_num,
        }
        self.pending.append(row)
        self.pending = self.pending[-20:]
        return row

    def settle(self, day, draw_id, nums):
        if not self.pending:
            return []
        key = draw_key(day, draw_id)
        actual = set(map(int, nums))
        old = list(self.pending)
        self.pending = []
        closed = []
        for p in old:
            if not sim_draw_is_consecutive(p["origin_key"], day, draw_id):
                self.skipped += 1
                self.last_result = {"origin_key": p["origin_key"], "key": key,
                                    "signal_type": p.get("signal_type"), "skipped": True}
                continue
            r = dict(p)
            r.update({
                "key": key,
                "engine_hit": int(p["engine_top1"]) in actual,
                "control_hit": int(p["control_num"]) in actual,
                "skipped": False,
            })
            self.records.append(r)
            self.last_result = r
            closed.append(r)
        self.records = self.records[-HC_METHOD_RECORD_MAX:]
        return closed

    @staticmethod
    def _stats(rows):
        n = len(rows)
        h = sum(int(bool(r.get("engine_hit"))) for r in rows)
        c = sum(int(bool(r.get("control_hit"))) for r in rows)
        wins = sum(int(bool(r.get("engine_hit")) and not bool(r.get("control_hit"))) for r in rows)
        losses = sum(int(bool(r.get("control_hit")) and not bool(r.get("engine_hit"))) for r in rows)
        ties = n - wins - losses
        return n, h, c, wins, losses, ties

    def signal_text(self, row):
        if not row or not row.get("is_main"):
            return None
        label = "🔥 SUPER" if row.get("is_super") else "🎯 MAIN"
        extra = ""
        if row.get("is_super"):
            extra = f"\nBURST SIGNAL: {row.get('burst_group','-')} contiene #{row['engine_top1']}"
        return (
            f"{label} — METODO CONVERGENZA HC v1\n\n"
            f"Origine: {row['origin_key']}\n"
            f"ENGINE HC TOP1: #{row['engine_top1']}\n"
            f"SOSIA rank#1: #{row['sosia_top1']}\n"
            f"Segnale congelato: #{row['engine_top1']} SOLO H1"
            f"{extra}\n"
            f"Controllo random congelato: #{row['control_num']}\n\n"
            "Shadow prospettico: nessuna puntata automatica."
        )

    def text(self):
        main = [r for r in self.records if r.get("is_main")]
        sup = [r for r in self.records if r.get("is_super")]
        disagree = [r for r in self.records if not r.get("agreement")]
        n, h, c, w, l, t = self._stats(main)
        sn, sh, sc, sw, sl, st = self._stats(sup)
        dn, dh, dc, dw, dl, dt = self._stats(disagree)
        lines = [
            "🎯 METODO CONVERGENZA HC v1 — H1 SHADOW",
            "MAIN: ENGINE HIGH CONFIDENCE TOP1 = SOSIA rank#1.",
            "SUPER: MAIN + BURST SIGNAL sulla decina che contiene il numero MAIN.",
            "BURST non crea e non blocca MAIN. Un solo H1; nessun recupero.",
            f"🧊 Inizio prospettico: dopo {self.start_from_key or '-'}" + (f" | {self.started_at}" if self.started_at else ""),
            f"HC valutati {len(self.records)} | pendenti {len(self.pending)} | salti {self.skipped} | contesto mancante {self.missing_context}",
            "",
            f"🎯 MAIN (include SUPER): {h}/{n} ({safe_pct(h,n):.2f}%) | random {c}/{n} ({safe_pct(c,n):.2f}%) | baseline 22.22%",
            f"   appaiato MAIN vs random: +{w}/-{l}/={t} | avanzamento {min(n,100)}/100 | {min(n,200)}/200 | {min(n,300)}/300",
            f"🔥 SUPER: {sh}/{sn} ({safe_pct(sh,sn):.2f}%) | random {sc}/{sn} ({safe_pct(sc,sn):.2f}%) | baseline 22.22%",
            f"🧪 HC ma SOSIA diverso: {dh}/{dn} ({safe_pct(dh,dn):.2f}%) | random {dc}/{dn} ({safe_pct(dc,dn):.2f}%)",
        ]
        for k in (50, 100, 200, 300):
            rows = main[-k:] if len(main) >= k else main
            if rows:
                rn, rh, rc, *_ = self._stats(rows)
                tag = "COMPLETA" if len(main) >= k else "PARZIALE"
                lines.append(f"• MAIN ultimi {k} ({tag}, n={rn}): {rh}/{rn} ({safe_pct(rh,rn):.2f}%) | random {rc}/{rn} ({safe_pct(rc,rn):.2f}%)")
        if self.pending:
            lines += ["", "⏳ PENDENTI:"]
            for r in self.pending[-5:]:
                if r.get("is_main"):
                    label = "SUPER" if r.get("is_super") else "MAIN"
                    lines.append(f"• {r['origin_key']} {label} #{r['engine_top1']} | random #{r['control_num']}")
                else:
                    lines.append(f"• {r['origin_key']} HC_DISAGREE ENGINE #{r['engine_top1']} vs SOSIA #{r['sosia_top1']}")
        if self.last_result and not self.last_result.get("skipped"):
            r = self.last_result
            lines += ["", f"🧾 Ultimo {r.get('key','-')}: {r.get('signal_type','-')} ENGINE #{r.get('engine_top1')} "
                      + ("✅ HIT" if r.get("engine_hit") else "❌ MISS")
                      + f" | random #{r.get('control_num')} " + ("✅" if r.get("control_hit") else "❌")]
        lines.append("⚠️ Nuovo test prospettico v13: nessun backfill e nessuna puntata automatica.")
        return "\n".join(lines)


# ============================================================
# FORCED ONE v1 — SHADOW PROSPETTICO dalla v14.
# Produce SEMPRE un solo numero per la H1 quando il contesto ENGINE+SOSIA
# e' disponibile. Gerarchia congelata:
#   A+ = ENGINE HC + ENGINE TOP1 = SOSIA #1 + BURST SIGNAL contiene il numero
#   A  = ENGINE HC + ENGINE TOP1 = SOSIA #1
#   B  = ENGINE HC, SOSIA diverso -> ENGINE TOP1
#   C  = ENGINE non HC ma ENGINE TOP1 = SOSIA #1
#   D  = ENGINE non HC e diverso -> SOSIA rank #1
# BURST non sceglie il numero: puo' solo promuovere A -> A+.
# Ogni previsione vale SOLO H1 ed e' confrontata con random congelato.
# Nessun backfill dei draw pre-v14.
# ============================================================
FORCED_ONE_VERSION = 1
FORCED_ONE_RECORD_MAX = max(300, int(os.getenv("FORCED_ONE_RECORD_MAX", "5000")))
FORCED_ONE_NOTIFY = os.getenv("FORCED_ONE_NOTIFY", "1").strip().lower() not in {"0", "false", "no", "off"}
FORCED_ONE_NOTIFY_RESULT = os.getenv("FORCED_ONE_NOTIFY_RESULT", "1").strip().lower() not in {"0", "false", "no", "off"}


class ForcedOneMethod:
    def __init__(self):
        self.start_from_key = None
        self.started_at = None
        self.pending = []
        self.records = []
        self.skipped = 0
        self.missing_context = 0
        self.last_result = None

    def ensure_start(self, engine):
        if self.start_from_key:
            return False
        if not engine.engine_history:
            return False
        key = str(engine.engine_history[-1].get("key") or "")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = datetime.now(BOT_TZ).isoformat(timespec="seconds")
        return True

    def load(self, obj):
        if not isinstance(obj, dict) or int(obj.get("version", 0) or 0) != FORCED_ONE_VERSION:
            return False
        key = obj.get("start_from_key")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = obj.get("started_at") if isinstance(obj.get("started_at"), str) else None
        self.skipped = max(0, int(obj.get("skipped", 0) or 0))
        self.missing_context = max(0, int(obj.get("missing_context", 0) or 0))
        self.last_result = obj.get("last_result") if isinstance(obj.get("last_result"), dict) else None
        raw = obj.get("pending", [])
        if isinstance(raw, list):
            self.pending = [dict(x) for x in raw[-5:] if isinstance(x, dict)
                            and isinstance(x.get("origin_key"), str)
                            and x.get("pick") and x.get("control_num")]
        rec = obj.get("records", [])
        if isinstance(rec, list):
            self.records = [dict(x) for x in rec[-FORCED_ONE_RECORD_MAX:]
                            if isinstance(x, dict) and isinstance(x.get("origin_key"), str)
                            and isinstance(x.get("key"), str) and x.get("pick")]
        return True

    def dump(self):
        return {
            "version": FORCED_ONE_VERSION,
            "start_from_key": self.start_from_key,
            "started_at": self.started_at,
            "pending": self.pending[-5:],
            "records": self.records[-FORCED_ONE_RECORD_MAX:],
            "skipped": self.skipped,
            "missing_context": self.missing_context,
            "last_result": self.last_result,
        }

    def _is_after_marker(self, key):
        a = _verifica_order(key)
        b = _verifica_order(self.start_from_key)
        return a is not None and b is not None and a > b

    @staticmethod
    def _burst_contains(bp, num):
        if not isinstance(bp, dict):
            return False
        try:
            gi = int(bp.get("group_index", -1))
            return 0 <= gi < len(DECINA_GROUPS) and int(num) in DECINA_GROUPS[gi]
        except (TypeError, ValueError, IndexError):
            return False

    def arm(self, current_key, engine):
        if not self.start_from_key:
            self.ensure_start(engine)
        if not self.start_from_key or not self._is_after_marker(current_key):
            return None
        # Una sola previsione per origine, anche dopo restart.
        if any(str(x.get("origin_key")) == str(current_key) for x in self.pending):
            return None
        if any(str(x.get("origin_key")) == str(current_key) for x in self.records[-10:]):
            return None

        ep = engine.engine_pending if isinstance(engine.engine_pending, dict) else {}
        sp = engine.sosiasniper_pending if isinstance(engine.sosiasniper_pending, dict) else {}
        if str(ep.get("signal_from_key")) != str(current_key) or not ep.get("top1"):
            self.missing_context += 1
            return None
        if str(sp.get("from_key")) != str(current_key) or not sp.get("top1"):
            self.missing_context += 1
            return None
        try:
            engine_top1 = int(ep.get("top1"))
            sosia_top1 = int(sp.get("top1"))
        except (TypeError, ValueError):
            self.missing_context += 1
            return None
        if not (1 <= engine_top1 <= 90 and 1 <= sosia_top1 <= 90):
            self.missing_context += 1
            return None

        hc = bool(ep.get("accepted"))
        agree = engine_top1 == sosia_top1
        if hc and agree:
            pick = engine_top1
            cls = "A"
            reason = "ENGINE HC + SOSIA #1 concordi"
        elif hc:
            pick = engine_top1
            cls = "B"
            reason = "ENGINE HC; SOSIA #1 diverso -> priorita ENGINE"
        elif agree:
            pick = engine_top1
            cls = "C"
            reason = "ENGINE non HC ma TOP1 = SOSIA #1"
        else:
            pick = sosia_top1
            cls = "D"
            reason = "fallback SOSIA rank #1"

        bp = engine.burst.pending if isinstance(engine.burst.pending, dict) else {}
        burst_same_origin = str(bp.get("from_key")) == str(current_key)
        burst_signal = bool(burst_same_origin and bp.get("signal"))
        burst_contains = bool(burst_same_origin and self._burst_contains(bp, pick))
        if cls == "A" and burst_signal and burst_contains:
            cls = "A+"
            reason = "ENGINE HC + SOSIA concordi + BURST SIGNAL sulla stessa decina"

        gi = None
        if burst_same_origin:
            try:
                v = int(bp.get("group_index", -1))
                if 0 <= v < len(DECINA_GROUPS):
                    gi = v
            except (TypeError, ValueError):
                gi = None

        pool = [n for n in range(1, 91) if n != pick]
        control_num = int(SOSIA_RANDOM.choice(pool))
        row = {
            "origin_key": str(current_key),
            "created_at": now_txt(),
            "class": cls,
            "pick": int(pick),
            "reason": reason,
            "engine_hc": hc,
            "engine_top1": engine_top1,
            "engine_confidence": ep.get("confidence"),
            "engine_threshold": ep.get("threshold"),
            "engine_support": ep.get("support"),
            "sosia_top1": sosia_top1,
            "sosia_score": sp.get("score"),
            "sosia_consensus": sp.get("consensus"),
            "agreement": agree,
            "burst_signal": burst_signal,
            "burst_contains": burst_contains,
            "burst_group_index": gi,
            "burst_group": DECINA_LABELS[gi] if gi is not None else None,
            "burst_score": bp.get("score") if burst_same_origin else None,
            "burst_gap": bp.get("gap") if burst_same_origin else None,
            "control_num": control_num,
        }
        self.pending.append(row)
        self.pending = self.pending[-5:]
        return row

    def settle(self, day, draw_id, nums):
        if not self.pending:
            return []
        key = draw_key(day, draw_id)
        actual = set(map(int, nums))
        old = list(self.pending)
        self.pending = []
        closed = []
        for p in old:
            if not sim_draw_is_consecutive(p["origin_key"], day, draw_id):
                self.skipped += 1
                self.last_result = {"origin_key": p["origin_key"], "key": key,
                                    "class": p.get("class"), "skipped": True}
                continue
            r = dict(p)
            r.update({
                "key": key,
                "hit": int(p["pick"]) in actual,
                "control_hit": int(p["control_num"]) in actual,
                "skipped": False,
            })
            self.records.append(r)
            self.last_result = r
            closed.append(r)
        self.records = self.records[-FORCED_ONE_RECORD_MAX:]
        return closed

    @staticmethod
    def _stats(rows):
        n = len(rows)
        h = sum(int(bool(r.get("hit"))) for r in rows)
        c = sum(int(bool(r.get("control_hit"))) for r in rows)
        w = sum(int(bool(r.get("hit")) and not bool(r.get("control_hit"))) for r in rows)
        l = sum(int(bool(r.get("control_hit")) and not bool(r.get("hit"))) for r in rows)
        return n, h, c, w, l, n-w-l

    def signal_text(self, row):
        if not row:
            return None
        boost = "\n🔥 BURST BOOST: " + str(row.get("burst_group")) if row.get("class") == "A+" else ""
        return (
            "🎯 FORCED ONE v1 — NUMERO H1\n\n"
            f"Origine: {row['origin_key']}\n"
            f"CLASSE {row['class']}\n"
            f"➡️ NUMERO: #{row['pick']} — SOLO PROSSIMA H1\n\n"
            f"ENGINE: #{row['engine_top1']} | {'HC' if row.get('engine_hc') else 'NO HC'}\n"
            f"SOSIA #1: #{row['sosia_top1']}\n"
            f"Motivo: {row.get('reason','-')}"
            f"{boost}\n"
            f"Controllo random: #{row['control_num']}\n\n"
            "Tracker prospettico: nessuna garanzia di vincita."
        )

    def result_text(self, row):
        if not row or row.get("skipped"):
            return None
        return (
            "🧾 FORCED ONE v1 — ESITO H1\n\n"
            f"Origine: {row.get('origin_key','-')} → {row.get('key','-')}\n"
            f"CLASSE {row.get('class','-')} | #{row.get('pick')} "
            + ("✅ HIT" if row.get("hit") else "❌ MISS") + "\n"
            f"Random #{row.get('control_num')} " + ("✅ HIT" if row.get("control_hit") else "❌ MISS")
        )

    def text(self):
        n,h,c,w,l,t = self._stats(self.records)
        lines = [
            "🎯 FORCED ONE v1 — UN NUMERO A OGNI H1",
            "A+ = HC + ENGINE=SOSIA + BURST SIGNAL stessa decina",
            "A = HC + ENGINE=SOSIA | B = HC -> ENGINE | C = non-HC ma ENGINE=SOSIA | D = fallback SOSIA #1",
            f"🧊 Inizio prospettico: dopo {self.start_from_key or '-'}" + (f" | {self.started_at}" if self.started_at else ""),
            f"Valutati {n} | pendenti {len(self.pending)} | salti {self.skipped} | contesto mancante {self.missing_context}",
            f"🎯 TOTALE: {h}/{n} ({safe_pct(h,n):.2f}%) | random {c}/{n} ({safe_pct(c,n):.2f}%) | baseline 22.22%",
            f"Appaiato vs random: +{w}/-{l}/={t} | avanzamento {min(n,100)}/100 | {min(n,200)}/200 | {min(n,300)}/300",
        ]
        for cls in ("A+","A","B","C","D"):
            rows = [r for r in self.records if r.get("class") == cls]
            rn,rh,rc,*_ = self._stats(rows)
            lines.append(f"• {cls}: {rh}/{rn} ({safe_pct(rh,rn):.2f}%) | random {rc}/{rn} ({safe_pct(rc,rn):.2f}%)")
        for k in (50,100,200,300):
            rows = self.records[-k:] if len(self.records) >= k else self.records
            if rows:
                rn,rh,rc,*_ = self._stats(rows)
                tag = "COMPLETA" if len(self.records) >= k else "PARZIALE"
                lines.append(f"• ultimi {k} ({tag}, n={rn}): {rh}/{rn} ({safe_pct(rh,rn):.2f}%) | random {rc}/{rn} ({safe_pct(rc,rn):.2f}%)")
        if self.pending:
            lines += ["", "⏳ PENDENTE:"]
            for r in self.pending[-3:]:
                lines.append(f"• {r['origin_key']} | classe {r['class']} | #{r['pick']} | random #{r['control_num']}")
        if self.last_result and not self.last_result.get("skipped"):
            r = self.last_result
            lines += ["", f"🧾 Ultimo {r.get('key','-')}: {r.get('class','-')} #{r.get('pick')} "
                      + ("✅ HIT" if r.get("hit") else "❌ MISS")
                      + f" | random #{r.get('control_num')} " + ("✅" if r.get("control_hit") else "❌")]
        lines.append("⚠️ Test prospettico v14: un solo numero per H1, nessun recupero e nessun backfill.")
        return "\n".join(lines)


# ============================================================
# TRIPLETTE CO-OCCORRENZA v1 — SHADOW PROSPETTICO dalla v15.
# Obiettivo: 4 ticket x 9 numeri per la H1 successiva.
# Ogni ticket contiene 3 triplette, su 3 decine diverse.
# Ogni tripletta ha ESATTAMENTE: 2 numeri consecutivi + 1 staccato.
# Ranking delle triplette calcolato SOLO sugli ultimi 320 draw gia' conclusi:
#   score = somma co-uscite delle 3 coppie + 2 * co-uscite di tutti e 3.
# Costruzione: massima diversificazione, 36 numeri distinti quando possibile,
# massimo 2 triplette per la stessa decina nell'intero portafoglio.
# Controllo: 4 ticket casuali con IDENTICA struttura e 36 numeri distinti.
# Un solo H1; nessun recupero; nessun backfill dei draw pre-v15.
# ============================================================
TRIPLETTE_VERSION = 1
TRIPLETTE_WINDOW = max(80, int(os.getenv("TRIPLETTE_WINDOW", "320")))
TRIPLETTE_TICKETS = 4
TRIPLETTE_TRIPLETS_PER_TICKET = 3
TRIPLETTE_RECORD_MAX = max(300, int(os.getenv("TRIPLETTE_RECORD_MAX", "5000")))
TRIPLETTE_NOTIFY = os.getenv("TRIPLETTE_NOTIFY", "1").strip().lower() not in {"0","false","no","off"}
TRIPLETTE_NOTIFY_RESULT = os.getenv("TRIPLETTE_NOTIFY_RESULT", "1").strip().lower() not in {"0","false","no","off"}


class TripletteCooccLab:
    def __init__(self):
        self.start_from_key = None
        self.started_at = None
        self.pending = []
        self.records = []
        self.skipped = 0
        self.missing_history = 0
        self.last_result = None
        self._candidate_cache = None

    def ensure_start(self, engine):
        if self.start_from_key:
            return False
        if not engine.engine_history:
            return False
        key = str(engine.engine_history[-1].get("key") or "")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = datetime.now(BOT_TZ).isoformat(timespec="seconds")
        return True

    def load(self, obj):
        if not isinstance(obj, dict) or int(obj.get("version",0) or 0) != TRIPLETTE_VERSION:
            return False
        key = obj.get("start_from_key")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = obj.get("started_at") if isinstance(obj.get("started_at"),str) else None
        self.skipped = max(0, int(obj.get("skipped",0) or 0))
        self.missing_history = max(0, int(obj.get("missing_history",0) or 0))
        self.last_result = obj.get("last_result") if isinstance(obj.get("last_result"),dict) else None
        raw = obj.get("pending",[])
        if isinstance(raw,list):
            self.pending = [dict(x) for x in raw[-3:] if self._valid_pending(x)]
        rec = obj.get("records",[])
        if isinstance(rec,list):
            self.records = [dict(x) for x in rec[-TRIPLETTE_RECORD_MAX:] if self._valid_record(x)]
        return True

    def dump(self):
        return {
            "version": TRIPLETTE_VERSION,
            "start_from_key": self.start_from_key,
            "started_at": self.started_at,
            "pending": self.pending[-3:],
            "records": self.records[-TRIPLETTE_RECORD_MAX:],
            "skipped": self.skipped,
            "missing_history": self.missing_history,
            "last_result": self.last_result,
        }

    @staticmethod
    def _valid_portfolio(v):
        if not isinstance(v,list) or len(v) != TRIPLETTE_TICKETS:
            return False
        flat=[]
        for ticket in v:
            if not isinstance(ticket,list) or len(ticket) != 9:
                return False
            try: vals=[int(x) for x in ticket]
            except Exception: return False
            if len(set(vals)) != 9 or any(x<1 or x>90 for x in vals):
                return False
            flat.extend(vals)
        return len(flat)==36 and len(set(flat))==36

    @classmethod
    def _valid_pending(cls, x):
        return isinstance(x,dict) and isinstance(x.get("origin_key"),str) and cls._valid_portfolio(x.get("tickets")) and cls._valid_portfolio(x.get("control_tickets"))

    @classmethod
    def _valid_record(cls, x):
        return cls._valid_pending(x) and isinstance(x.get("key"),str) and isinstance(x.get("ticket_hits"),list)

    def _is_after_marker(self,key):
        a=_verifica_order(key); b=_verifica_order(self.start_from_key)
        return a is not None and b is not None and a>b

    @staticmethod
    def _all_candidates():
        out=[]
        for gi, group in enumerate(DECINA_GROUPS):
            vals=sorted(int(x) for x in group)
            # La fascia 90-09 mantiene 90 nella decina ma la coppia consecutiva
            # e' numericamente reale: 01-02 ... 08-09. 90-01 NON e' trattata come consecutiva.
            pairs=[(a,b) for a,b in zip(vals, vals[1:]) if b-a==1]
            for a,b in pairs:
                for c in vals:
                    if c in (a,b):
                        continue
                    # terzo numero realmente staccato dalla coppia
                    if abs(c-a)<=1 or abs(c-b)<=1:
                        continue
                    tri=tuple(sorted((a,b,c)))
                    out.append((gi,tri,(a,b)))
        # dedup deterministico
        seen=set(); clean=[]
        for row in out:
            k=(row[0],row[1])
            if k not in seen:
                seen.add(k); clean.append(row)
        return tuple(clean)

    @classmethod
    def _score_candidates(cls, history):
        rows=list(history)[-TRIPLETTE_WINDOW:]
        pair=Counter(); triple=Counter()
        for row in rows:
            s=set(map(int,row.get("nums",[]) or []))
            if len(s)!=20:
                continue
            for gi, group in enumerate(DECINA_GROUPS):
                hit=sorted(s.intersection(group))
                for a,b in combinations(hit,2):
                    pair[(gi,a,b)] += 1
                for a,b,c in combinations(hit,3):
                    triple[(gi,a,b,c)] += 1
        scored=[]
        for gi,tri,conspair in cls._all_candidates():
            a,b,c=tri
            pair_sum = pair[(gi,a,b)] + pair[(gi,a,c)] + pair[(gi,b,c)]
            tri_n = triple[(gi,a,b,c)]
            cp=tuple(sorted(conspair))
            cons_n=pair[(gi,cp[0],cp[1])]
            score=float(pair_sum + 2.0*tri_n)
            scored.append({"group_index":gi,"triple":list(tri),"score":score,
                           "pair_sum":int(pair_sum),"triple_n":int(tri_n),"cons_pair_n":int(cons_n)})
        scored.sort(key=lambda r:(r["score"],r["triple_n"],r["cons_pair_n"],-r["group_index"],tuple(-x for x in r["triple"])), reverse=True)
        return scored

    @staticmethod
    def _build_from_ranked(ranked):
        tickets=[[] for _ in range(TRIPLETTE_TICKETS)]
        ticket_groups=[set() for _ in range(TRIPLETTE_TICKETS)]
        used=set(); group_uses=Counter(); chosen=[]
        # 3 giri x 4 ticket. Prima prova max2 triplette/decina, poi max3 solo come fallback.
        for round_i in range(TRIPLETTE_TRIPLETS_PER_TICKET):
            for ti in range(TRIPLETTE_TICKETS):
                pick=None
                for max_group in (2,3):
                    for r in ranked:
                        gi=int(r["group_index"]); tri=tuple(map(int,r["triple"]))
                        if gi in ticket_groups[ti] or group_uses[gi] >= max_group:
                            continue
                        if any(n in used for n in tri):
                            continue
                        pick=r; break
                    if pick is not None:
                        break
                if pick is None:
                    return None
                gi=int(pick["group_index"]); tri=tuple(map(int,pick["triple"]))
                tickets[ti].extend(tri); ticket_groups[ti].add(gi); group_uses[gi]+=1; used.update(tri)
                chosen.append(dict(pick, ticket_index=ti))
        tickets=[sorted(x) for x in tickets]
        if len(used)!=36 or any(len(x)!=9 for x in tickets):
            return None
        return {"tickets":tickets,"chosen":chosen,"coverage":len(used)}

    @classmethod
    def _random_portfolio(cls):
        base=[{"group_index":gi,"triple":list(tri)} for gi,tri,_ in cls._all_candidates()]
        for _ in range(60):
            ranked=list(base); SOSIA_RANDOM.shuffle(ranked)
            built=cls._build_from_ranked(ranked)
            if built:
                return built["tickets"]
        return None

    def arm(self,current_key,engine):
        if not self.start_from_key:
            self.ensure_start(engine)
        if not self.start_from_key or not self._is_after_marker(current_key):
            return None
        if any(str(x.get("origin_key"))==str(current_key) for x in self.pending):
            return None
        if any(str(x.get("origin_key"))==str(current_key) for x in self.records[-5:]):
            return None
        hist=list(engine.engine_history)
        if len(hist) < TRIPLETTE_WINDOW:
            self.missing_history += 1
            return None
        ranked=self._score_candidates(hist)
        built=self._build_from_ranked(ranked)
        controls=self._random_portfolio()
        if not built or not controls:
            self.missing_history += 1
            return None
        row={
            "origin_key":str(current_key),"created_at":now_txt(),"window":TRIPLETTE_WINDOW,
            "tickets":built["tickets"],"coverage":built["coverage"],"control_tickets":controls,
            "chosen":[{"ticket_index":int(x["ticket_index"]),"group_index":int(x["group_index"]),
                       "group":DECINA_LABELS[int(x["group_index"])],"triple":list(map(int,x["triple"])),
                       "score":float(x["score"]),"pair_sum":int(x["pair_sum"]),"triple_n":int(x["triple_n"])}
                      for x in built["chosen"]],
        }
        self.pending.append(row); self.pending=self.pending[-3:]
        return row

    def settle(self,day,draw_id,nums):
        if not self.pending:
            return []
        key=draw_key(day,draw_id); actual=set(map(int,nums)); old=list(self.pending); self.pending=[]; closed=[]
        for p in old:
            if not sim_draw_is_consecutive(p["origin_key"],day,draw_id):
                self.skipped += 1
                self.last_result={"origin_key":p["origin_key"],"key":key,"skipped":True}
                continue
            th=[len(actual.intersection(t)) for t in p["tickets"]]
            ch=[len(actual.intersection(t)) for t in p["control_tickets"]]
            r=dict(p); r.update({"key":key,"ticket_hits":th,"control_ticket_hits":ch,
                "any5":any(v>=5 for v in th),"any6":any(v>=6 for v in th),"best":max(th),
                "ticket5_count":sum(v>=5 for v in th),"ticket6_count":sum(v>=6 for v in th),
                "control_any5":any(v>=5 for v in ch),"control_any6":any(v>=6 for v in ch),"control_best":max(ch),
                "control_ticket5_count":sum(v>=5 for v in ch),"control_ticket6_count":sum(v>=6 for v in ch),
                "skipped":False})
            self.records.append(r); self.last_result=r; closed.append(r)
        self.records=self.records[-TRIPLETTE_RECORD_MAX:]
        return closed

    @staticmethod
    def _stats(rows):
        n=len(rows); h5=sum(bool(r.get("any5")) for r in rows); h6=sum(bool(r.get("any6")) for r in rows)
        c5=sum(bool(r.get("control_any5")) for r in rows); c6=sum(bool(r.get("control_any6")) for r in rows)
        w=sum(bool(r.get("any5")) and not bool(r.get("control_any5")) for r in rows)
        l=sum(bool(r.get("control_any5")) and not bool(r.get("any5")) for r in rows)
        return n,h5,c5,h6,c6,w,l,n-w-l

    @staticmethod
    def _fmt_ticket(t):
        return " ".join(f"{int(x):02d}" for x in sorted(t))

    def signal_text(self,row):
        if not row: return None
        lines=["🎟 TRIPLETTE CO-OCC v1 — 4 GIOCATE H1 SHADOW",f"Origine: {row['origin_key']} | finestra {row['window']} draw",
               "Struttura: 3 decine × (2 consecutivi + 1 staccato), 36 numeri distinti."]
        for i,t in enumerate(row["tickets"],1): lines.append(f"G{i}: {self._fmt_ticket(t)}")
        lines += ["", "Valide SOLO per la prossima H1. Nessun recupero.", "Controllo casuale equivalente congelato ma non mostrato prima dell'esito."]
        return "\n".join(lines)

    def result_text(self,row):
        if not row or row.get("skipped"): return None
        lines=["🧾 TRIPLETTE CO-OCC v1 — ESITO H1",f"{row.get('origin_key')} → {row.get('key')}"]
        for i,(t,h) in enumerate(zip(row["tickets"],row["ticket_hits"]),1):
            flag="✅ 5+" if h>=5 else "❌"
            lines.append(f"G{i}: {h}/9 {flag}")
        lines.append(f"PORTAFOGLIO: {'✅ almeno un 5+' if row.get('any5') else '❌ nessun 5+'} | best {row.get('best')}/9")
        lines.append(f"Random equivalente: {'✅ 5+' if row.get('control_any5') else '❌'} | best {row.get('control_best')}/9")
        return "\n".join(lines)

    def text(self):
        n,h5,c5,h6,c6,w,l,t=self._stats(self.records)
        lines=["🎟 TRIPLETTE CO-OCCORRENZA v1 — 4×9 H1 SHADOW",
               "4 giocate; ciascuna = 3 decine × (2 consecutivi + 1 staccato).",
               f"Score triplette: co-uscite coppie + 2×co-uscite triple su ultimi {TRIPLETTE_WINDOW} draw.",
               "Massima diversificazione: 36 numeri distinti; controllo casuale con stessa struttura.",
               f"🧊 Inizio prospettico: dopo {self.start_from_key or '-'}" + (f" | {self.started_at}" if self.started_at else ""),
               f"Valutati {n} | pendenti {len(self.pending)} | salti {self.skipped} | history insufficiente {self.missing_history}",
               f"🎯 almeno una G 5+: {h5}/{n} ({safe_pct(h5,n):.2f}%) | random {c5}/{n} ({safe_pct(c5,n):.2f}%)",
               f"🔥 almeno una G 6+: {h6}/{n} ({safe_pct(h6,n):.2f}%) | random {c6}/{n} ({safe_pct(c6,n):.2f}%)",
               f"Appaiato 5+ vs random: +{w}/-{l}/={t} | progress {min(n,100)}/100 {min(n,200)}/200 {min(n,300)}/300"]
        for k in (50,100,200,300):
            rows=self.records[-k:] if len(self.records)>=k else self.records
            if rows:
                rn,rh,rc,*_=self._stats(rows); tag="COMPLETA" if len(self.records)>=k else "PARZIALE"
                lines.append(f"• ultimi {k} ({tag}, n={rn}): 5+ {rh}/{rn} ({safe_pct(rh,rn):.2f}%) | random {rc}/{rn} ({safe_pct(rc,rn):.2f}%)")
        if self.pending:
            p=self.pending[-1]; lines += ["",f"⏳ PENDENTE da {p['origin_key']}:"]
            for i,ticket in enumerate(p["tickets"],1): lines.append(f"G{i}: {self._fmt_ticket(ticket)}")
        if self.last_result and not self.last_result.get("skipped"):
            r=self.last_result; lines += ["",f"🧾 Ultimo {r.get('key')}: best {r.get('best')}/9 | {'5+ ✅' if r.get('any5') else '5+ ❌'} | random best {r.get('control_best')}/9"]
        lines.append("⚠️ Shadow prospettico: non modifica ENGINE/SOSIA/BURST/FORCED ONE e non effettua puntate automatiche.")
        return "\n".join(lines)



# ============================================================
# FOCUS FAST v2 — UN SOLO NUMERO H1, UNICO METODO ATTIVO
# ============================================================
# Regola congelata:
#   1) calcola il ritardo di ogni numero 1..90 DOPO il draw corrente;
#   2) candidati = numeri con ritardo 13..18 inclusi;
#   3) segnale SOLO se i candidati sono 3 oppure 4;
#   4) per ciascun candidato calcola TRANS80: probabilita' media empirica
#      di comparire al draw successivo condizionata ai 20 numeri appena usciti,
#      usando al massimo le ultime 80 transizioni gia' concluse;
#   5) sceglie il candidato con TRANS80 piu' alto.
# Un solo H1, nessun recupero. Random appaiato congelato prima della H1.
# Tutti i metodi LEGACY sono PAUSATI: FOCUS + INCROCIO + CORE SYNC20 restano attivi.
# ============================================================
FOCUS_VERSION = 2
FOCUS_GAP_MIN = max(1, int(os.getenv("FOCUS_GAP_MIN", "13")))
FOCUS_GAP_MAX = max(FOCUS_GAP_MIN, int(os.getenv("FOCUS_GAP_MAX", "18")))
FOCUS_MIN_CANDIDATES = max(2, int(os.getenv("FOCUS_MIN_CANDIDATES", "3")))
FOCUS_MAX_CANDIDATES = max(FOCUS_MIN_CANDIDATES, int(os.getenv("FOCUS_MAX_CANDIDATES", "4")))
FOCUS_TRANS_WINDOW = max(20, int(os.getenv("FOCUS_TRANS_WINDOW", "80")))
FOCUS_RECORD_MAX = max(300, int(os.getenv("FOCUS_RECORD_MAX", "5000")))
FOCUS_NOTIFY = os.getenv("FOCUS_NOTIFY", "1").strip().lower() not in {"0","false","no","off"}
FOCUS_NOTIFY_RESULT = os.getenv("FOCUS_NOTIFY_RESULT", "1").strip().lower() not in {"0","false","no","off"}
LEGACY_METHODS_PAUSED = True


class FocusFastV2:
    def __init__(self):
        self.start_from_key = None
        self.started_at = None
        self.pending = []
        self.records = []
        self.scans = 0
        self.no_signal = 0
        self.skipped = 0
        self.history_insufficient = 0
        self.last_result = None
        self.last_scan = None

    def ensure_start(self, engine):
        if self.start_from_key:
            return False
        if not engine.engine_history:
            return False
        key = str(engine.engine_history[-1].get("key") or "")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = datetime.now(BOT_TZ).isoformat(timespec="seconds")
        return True

    def load(self, obj):
        if not isinstance(obj, dict) or int(obj.get("version", 0) or 0) != FOCUS_VERSION:
            return False
        key = obj.get("start_from_key")
        if _verifica_order(key) is None:
            return False
        self.start_from_key = key
        self.started_at = obj.get("started_at") if isinstance(obj.get("started_at"), str) else None
        self.scans = max(0, int(obj.get("scans", 0) or 0))
        self.no_signal = max(0, int(obj.get("no_signal", 0) or 0))
        self.skipped = max(0, int(obj.get("skipped", 0) or 0))
        self.history_insufficient = max(0, int(obj.get("history_insufficient", 0) or 0))
        self.last_result = obj.get("last_result") if isinstance(obj.get("last_result"), dict) else None
        self.last_scan = obj.get("last_scan") if isinstance(obj.get("last_scan"), dict) else None
        raw = obj.get("pending", [])
        if isinstance(raw, list):
            self.pending = [dict(x) for x in raw[-5:] if isinstance(x, dict)
                            and isinstance(x.get("origin_key"), str)
                            and x.get("pick") and x.get("control_num")]
        rec = obj.get("records", [])
        if isinstance(rec, list):
            self.records = [dict(x) for x in rec[-FOCUS_RECORD_MAX:]
                            if isinstance(x, dict) and isinstance(x.get("origin_key"), str)
                            and isinstance(x.get("key"), str) and x.get("pick")]
        return True

    def dump(self):
        return {
            "version": FOCUS_VERSION,
            "start_from_key": self.start_from_key,
            "started_at": self.started_at,
            "pending": self.pending[-5:],
            "records": self.records[-FOCUS_RECORD_MAX:],
            "scans": self.scans,
            "no_signal": self.no_signal,
            "skipped": self.skipped,
            "history_insufficient": self.history_insufficient,
            "last_result": self.last_result,
            "last_scan": self.last_scan,
        }

    def _is_after_marker(self, key):
        a = _verifica_order(key); b = _verifica_order(self.start_from_key)
        return a is not None and b is not None and a > b

    @staticmethod
    def _nums(row):
        if not isinstance(row, dict): return []
        try: vals = [int(x) for x in row.get("nums", [])]
        except Exception: return []
        return vals if len(vals) == 20 and len(set(vals)) == 20 else []

    @classmethod
    def _gaps(cls, history):
        # Ritardo 0 = presente nel draw corrente.
        rows = list(history); gaps = {}
        for n in range(1, 91):
            g = None
            for back, row in enumerate(reversed(rows)):
                vals = cls._nums(row)
                if vals and n in vals:
                    g = back; break
            if g is None: g = len(rows) + 1
            gaps[n] = int(g)
        return gaps

    @classmethod
    def _transition_score(cls, history, current_nums, candidate):
        rows = [r for r in list(history) if cls._nums(r)]
        if len(rows) < 2: return None, 0, 0
        start = max(0, len(rows) - 1 - FOCUS_TRANS_WINDOW)
        pairs = []
        for i in range(start, len(rows) - 1):
            a = cls._nums(rows[i]); b = cls._nums(rows[i+1])
            if a and b: pairs.append((set(a), set(b)))
        if not pairs: return None, 0, 0
        cond=[]; supports=0; hits=0; cand=int(candidate)
        for src in map(int, current_nums):
            den=num=0
            for a,b in pairs:
                if src in a:
                    den += 1
                    if cand in b: num += 1
            if den:
                # Shrinkage leggero: evita estremi da supporti piccoli.
                cond.append((num + 0.5) / (den + 1.0))
                supports += den; hits += num
        if not cond: return None, supports, hits
        return float(sum(cond)/len(cond)), supports, hits

    def arm(self, current_key, engine):
        if not self.start_from_key: self.ensure_start(engine)
        if not self.start_from_key or not self._is_after_marker(current_key): return None
        if any(str(x.get("origin_key")) == str(current_key) for x in self.pending): return None
        if any(str(x.get("origin_key")) == str(current_key) for x in self.records[-10:]): return None
        self.scans += 1
        hist = list(engine.engine_history)
        if len(hist) < max(FOCUS_GAP_MAX + 2, FOCUS_TRANS_WINDOW + 1):
            self.history_insufficient += 1
            self.last_scan={"origin_key":str(current_key),"signal":False,"reason":"history_insufficient"}
            return None
        current_nums=self._nums(hist[-1])
        if not current_nums or str(hist[-1].get("key")) != str(current_key):
            self.history_insufficient += 1
            self.last_scan={"origin_key":str(current_key),"signal":False,"reason":"current_history_missing"}
            return None
        gaps=self._gaps(hist)
        candidates=[n for n in range(1,91) if FOCUS_GAP_MIN <= gaps[n] <= FOCUS_GAP_MAX]
        if not (FOCUS_MIN_CANDIDATES <= len(candidates) <= FOCUS_MAX_CANDIDATES):
            self.no_signal += 1
            self.last_scan={"origin_key":str(current_key),"signal":False,
                            "candidate_count":len(candidates),"candidates":candidates[:12]}
            return None
        details=[]
        for n in candidates:
            score,support,trans_hits=self._transition_score(hist,current_nums,n)
            if score is None:
                self.history_insufficient += 1
                self.last_scan={"origin_key":str(current_key),"signal":False,"reason":"transition_missing"}
                return None
            details.append({"num":int(n),"gap":int(gaps[n]),"trans":float(score),
                            "support":int(support),"transition_hits":int(trans_hits)})
        details.sort(key=lambda x:(-x["trans"],-x["gap"],x["num"]))
        pick=int(details[0]["num"])
        control_num=int(SOSIA_RANDOM.choice([n for n in range(1,91) if n != pick]))
        row={
            "origin_key":str(current_key),"created_at":now_txt(),"pick":pick,
            "ranked_candidates":details,"candidate_count":len(details),
            "pick_gap":int(details[0]["gap"]),"pick_trans":round(float(details[0]["trans"]),8),
            "runner_up":int(details[1]["num"]),"runner_gap":int(details[1]["gap"]),
            "runner_trans":round(float(details[1]["trans"]),8),
            "third_candidate":int(details[2]["num"]),"third_gap":int(details[2]["gap"]),
            "third_trans":round(float(details[2]["trans"]),8),
            "fourth_candidate":int(details[3]["num"]) if len(details)>3 else None,
            "fourth_gap":int(details[3]["gap"]) if len(details)>3 else None,
            "fourth_trans":round(float(details[3]["trans"]),8) if len(details)>3 else None,
            "margin":round(float(details[0]["trans"]-details[1]["trans"]),8),
            "control_num":control_num,
            "rule":f"gap {FOCUS_GAP_MIN}-{FOCUS_GAP_MAX}; {FOCUS_MIN_CANDIDATES}-{FOCUS_MAX_CANDIDATES} candidates; max TRANS{FOCUS_TRANS_WINDOW}",
        }
        self.pending.append(row); self.pending=self.pending[-5:]
        self.last_scan=dict(row,signal=True)
        return row

    def settle(self, day, draw_id, nums):
        if not self.pending: return []
        key=draw_key(day,draw_id); actual=set(map(int,nums)); old=list(self.pending); self.pending=[]; closed=[]
        for p in old:
            if not sim_draw_is_consecutive(p.get("origin_key"),day,draw_id):
                self.skipped += 1
                self.last_result={"origin_key":p.get("origin_key"),"key":key,"pick":p.get("pick"),"skipped":True}
                continue
            r=dict(p)
            ranked=list(p.get("ranked_candidates") or [])
            rank_hits=[bool(int(x.get("num")) in actual) for x in ranked]
            r.update({"key":key,"hit":bool(int(p["pick"]) in actual),
                      "control_hit":bool(int(p["control_num"]) in actual),
                      "rank_hits":rank_hits,
                      "runner_hit":rank_hits[1] if len(rank_hits)>1 else False,
                      "third_hit":rank_hits[2] if len(rank_hits)>2 else False,
                      "fourth_hit":rank_hits[3] if len(rank_hits)>3 else False})
            self.records.append(r); self.records=self.records[-FOCUS_RECORD_MAX:]
            self.last_result=r; closed.append(r)
        return closed

    @staticmethod
    def _stats(rows):
        rows=[r for r in rows if isinstance(r,dict) and not r.get("skipped")]
        n=len(rows); h=sum(bool(r.get("hit")) for r in rows); c=sum(bool(r.get("control_hit")) for r in rows)
        r2=sum(bool(r.get("runner_hit")) for r in rows); r3=sum(bool(r.get("third_hit")) for r in rows)
        r4=sum(bool(r.get("fourth_hit")) for r in rows if r.get("candidate_count")==4)
        n4=sum(int(r.get("candidate_count",0) or 0)==4 for r in rows)
        w=sum(bool(r.get("hit")) and not bool(r.get("control_hit")) for r in rows)
        l=sum(bool(r.get("control_hit")) and not bool(r.get("hit")) for r in rows)
        return n,h,c,r2,r3,r4,n4,w,l,n-w-l

    def signal_text(self,row):
        if not row: return None
        parts=[]
        for x in row.get("ranked_candidates",[]):
            parts.append(f"#{x.get('num')} R{x.get('gap')} T{x.get('trans',0):.4f}")
        return ("⚡ FOCUS FAST v2 — NUMERO H1\n\n"
                f"Origine: {row.get('origin_key','-')}\n"
                f"Candidati ({row.get('candidate_count')}): " + " | ".join(parts) + "\n"
                f"Margine 1°-2°: {float(row.get('margin',0)):.4f}\n\n"
                f"➡️ NUMERO FOCUS: #{row.get('pick')} — SOLO PROSSIMA H1\n"
                f"Controllo random: #{row.get('control_num')}\n\n"
                f"Regola: ritardo {FOCUS_GAP_MIN}-{FOCUS_GAP_MAX}, 3-4 candidati, TRANS{FOCUS_TRANS_WINDOW} massimo.")

    def result_text(self,row):
        if not row or row.get("skipped"): return None
        ranks=list(row.get("ranked_candidates") or [])
        hits=list(row.get("rank_hits") or [])
        details=[]
        for i,x in enumerate(ranks):
            details.append(f"{i+1}° #{x.get('num')}: " + ("✅" if i < len(hits) and hits[i] else "❌"))
        return ("🧾 FOCUS FAST v2 — ESITO H1\n\n"
                f"Origine: {row.get('origin_key','-')} → {row.get('key','-')}\n"
                f"FOCUS #{row.get('pick')}: " + ("✅ HIT" if row.get("hit") else "❌ MISS") + "\n" +
                "\n".join(details[1:]) + "\n" +
                f"Random #{row.get('control_num')}: " + ("✅ HIT" if row.get("control_hit") else "❌ MISS"))

    def text(self):
        n,h,c,r2,r3,r4,n4,w,l,t=self._stats(self.records)
        rate=100.0*(n+len(self.pending))/self.scans if self.scans else 0.0
        lines=[
            "⚡ FOCUS FAST v2 — UNICO METODO ATTIVO",
            f"Regola: ritardo {FOCUS_GAP_MIN}-{FOCUS_GAP_MAX}; segnale con {FOCUS_MIN_CANDIDATES}-{FOCUS_MAX_CANDIDATES} candidati; scelgo TRANS{FOCUS_TRANS_WINDOW} massimo.",
            f"🧊 Inizio prospettico v2: dopo {self.start_from_key or '-'}" + (f" | {self.started_at}" if self.started_at else ""),
            f"Scan {self.scans} | valutati {n} | pendenti {len(self.pending)} | NO SIGNAL {self.no_signal} | frequenza segnali {rate:.1f}% | salti {self.skipped}",
            f"🎯 H1: {h}/{n} ({safe_pct(h,n):.2f}%) | random {c}/{n} ({safe_pct(c,n):.2f}%) | baseline 22.22%",
            f"2° candidato {r2}/{n} ({safe_pct(r2,n):.2f}%) | 3° {r3}/{n} ({safe_pct(r3,n):.2f}%)" + (f" | 4° {r4}/{n4} ({safe_pct(r4,n4):.2f}%)" if n4 else ""),
            f"Appaiato FOCUS vs random: +{w}/-{l}/={t}",
            f"Avanzamento {min(n,50)}/50 | {min(n,100)}/100 | {min(n,200)}/200 | {min(n,300)}/300",
        ]
        for size in (50,100,200,300):
            rows=self.records[-size:]
            if not rows: continue
            nn,hh,cc,*_=self._stats(rows); tag="COMPLETA" if nn>=size else "PARZIALE"
            lines.append(f"• ultimi {size} ({tag}, n={nn}): FOCUS {hh}/{nn} ({safe_pct(hh,nn):.2f}%) | random {cc}/{nn} ({safe_pct(cc,nn):.2f}%)")
        if self.pending:
            p=self.pending[-1]
            lines += ["", "⏳ PENDENTE:", f"• {p.get('origin_key')} | NUMERO #{p.get('pick')} | candidati {p.get('candidate_count')} | TRANS{FOCUS_TRANS_WINDOW} {float(p.get('pick_trans',0)):.4f} | random #{p.get('control_num')}"]
        if self.last_result and not self.last_result.get("skipped"):
            r=self.last_result
            lines += ["", f"🧾 Ultimo {r.get('origin_key','-')}: FOCUS #{r.get('pick','-')} " + ("✅ HIT" if r.get("hit") else "❌ MISS") + f" | random #{r.get('control_num','-')} " + ("✅" if r.get("control_hit") else "❌")]
        lines += ["🔗 INCROCIO v1 e' attivo in parallelo; tutti i metodi LEGACY restano PAUSATI e conservati.",
                  "⚠️ FOCUS resta prospettico: un solo H1; INCROCIO e' un tracker separato H1-H5."]
        return "\n".join(lines)

# Alias interno per compatibilita' con eventuali riferimenti di test/vecchie importazioni.
FocusR14Trans40 = FocusFastV2


# ============================================================
# INCROCIO v1 — PERSISTENZA CANDIDATI FOCUS, AMBATA + AMBO H1-H5
# ============================================================
# Deriva ESCLUSIVAMENTE dai candidati FOCUS FAST gia' congelati prima della H1.
# - un numero e' "persistente" se compare in >=2 segnali FOCUS consecutivi;
# - una coppia e' "persistente" se entrambi i numeri compaiono insieme in >=2
#   segnali FOCUS consecutivi;
# - per ogni nuovo segnale FOCUS si sceglie UNA ambata persistente e, se esiste,
#   UN ambo persistente; entrambi vengono seguiti fino a H5;
# - priorita': streak piu' lungo, poi TRANS80 corrente (somma per l'ambo).
# I segnali FOCUS v17 gia' conclusi possono essere usati SOLO come contesto per
# calcolare lo streak del primo segnale v18; nessun risultato INCROCIO viene
# ricostruito retroattivamente.
# ============================================================
INCROCIO_VERSION = 1
INCROCIO_HORIZON = max(1, int(os.getenv("INCROCIO_HORIZON", "5")))
INCROCIO_MIN_STREAK = max(2, int(os.getenv("INCROCIO_MIN_STREAK", "2")))
INCROCIO_RECORD_MAX = max(300, int(os.getenv("INCROCIO_RECORD_MAX", "5000")))
INCROCIO_NOTIFY = os.getenv("INCROCIO_NOTIFY", "1").strip().lower() not in {"0","false","no","off"}
INCROCIO_NOTIFY_RESULT = os.getenv("INCROCIO_NOTIFY_RESULT", "1").strip().lower() not in {"0","false","no","off"}


class IncrocioFocusV1:
    def __init__(self):
        self.start_from_key=None
        self.started_at=None
        self.signal_history=[]
        self.pending=[]
        self.records=[]
        self.focus_signals_seen=0
        self.incrocio_signals=0
        self.no_incrocio=0
        self.skipped=0
        self.seeded_context=False
        self.last_signal=None
        self.last_result=None

    def ensure_start(self, engine):
        if self.start_from_key:
            return False
        if not engine.engine_history:
            return False
        key=str(engine.engine_history[-1].get("key") or "")
        if _verifica_order(key) is None:
            return False
        self.start_from_key=key
        self.started_at=datetime.now(BOT_TZ).isoformat(timespec="seconds")
        return True

    @staticmethod
    def _candidate_snapshot(row):
        if not isinstance(row,dict) or not isinstance(row.get("origin_key"),str):
            return None
        ranked=[]
        for x in list(row.get("ranked_candidates") or []):
            if not isinstance(x,dict):
                continue
            try:
                n=int(x.get("num")); tr=float(x.get("trans",0) or 0); gap=int(x.get("gap",0) or 0)
            except Exception:
                continue
            if 1 <= n <= 90:
                ranked.append({"num":n,"trans":tr,"gap":gap})
        if len(ranked) < 2:
            return None
        return {"origin_key":str(row.get("origin_key")),"ranked_candidates":ranked,
                "candidate_count":len(ranked),"seed":False}

    def seed_from_focus(self, focus):
        if self.signal_history or self.seeded_context:
            return False
        rows=[]
        for r in list(getattr(focus,"records",[]) or [])[-6:]:
            s=self._candidate_snapshot(r)
            if s: rows.append(s)
        for r in list(getattr(focus,"pending",[]) or [])[-3:]:
            s=self._candidate_snapshot(r)
            if s: rows.append(s)
        ded={}
        for r in rows:
            ded[r["origin_key"]]=r
        rows=sorted(ded.values(), key=lambda r: _verifica_order(r["origin_key"]) or (-1,-1))[-4:]
        for r in rows:
            r=dict(r); r["seed"]=True; self.signal_history.append(r)
        self.seeded_context=True
        self.signal_history=self.signal_history[-8:]
        return bool(rows)

    def load(self,obj):
        if not isinstance(obj,dict) or int(obj.get("version",0) or 0) != INCROCIO_VERSION:
            return False
        key=obj.get("start_from_key")
        if _verifica_order(key) is None:
            return False
        self.start_from_key=key
        self.started_at=obj.get("started_at") if isinstance(obj.get("started_at"),str) else None
        self.focus_signals_seen=max(0,int(obj.get("focus_signals_seen",0) or 0))
        self.incrocio_signals=max(0,int(obj.get("incrocio_signals",0) or 0))
        self.no_incrocio=max(0,int(obj.get("no_incrocio",0) or 0))
        self.skipped=max(0,int(obj.get("skipped",0) or 0))
        self.seeded_context=bool(obj.get("seeded_context",False))
        sh=obj.get("signal_history",[])
        if isinstance(sh,list):
            self.signal_history=[dict(x) for x in sh[-8:] if isinstance(x,dict) and isinstance(x.get("origin_key"),str)]
        pp=obj.get("pending",[])
        if isinstance(pp,list):
            self.pending=[dict(x) for x in pp[-40:] if isinstance(x,dict) and isinstance(x.get("origin_key"),str)]
        rr=obj.get("records",[])
        if isinstance(rr,list):
            self.records=[dict(x) for x in rr[-INCROCIO_RECORD_MAX:] if isinstance(x,dict) and isinstance(x.get("origin_key"),str)]
        self.last_signal=obj.get("last_signal") if isinstance(obj.get("last_signal"),dict) else None
        self.last_result=obj.get("last_result") if isinstance(obj.get("last_result"),dict) else None
        return True

    def dump(self):
        return {"version":INCROCIO_VERSION,"start_from_key":self.start_from_key,"started_at":self.started_at,
                "signal_history":self.signal_history[-8:],"pending":self.pending[-40:],
                "records":self.records[-INCROCIO_RECORD_MAX:],"focus_signals_seen":self.focus_signals_seen,
                "incrocio_signals":self.incrocio_signals,"no_incrocio":self.no_incrocio,
                "skipped":self.skipped,"seeded_context":self.seeded_context,
                "last_signal":self.last_signal,"last_result":self.last_result}

    @staticmethod
    def _set(row):
        vals=[]
        for x in list(row.get("ranked_candidates") or []):
            try: vals.append(int(x.get("num")))
            except Exception: pass
        return set(n for n in vals if 1<=n<=90)

    @staticmethod
    def _trans_map(row):
        out={}
        for x in list(row.get("ranked_candidates") or []):
            try: out[int(x.get("num"))]=float(x.get("trans",0) or 0)
            except Exception: pass
        return out

    def _streak_number(self, seq, n):
        s=0
        for r in reversed(seq):
            if n in self._set(r): s+=1
            else: break
        return s

    def _streak_pair(self, seq, a, b):
        s=0
        for r in reversed(seq):
            ss=self._set(r)
            if a in ss and b in ss: s+=1
            else: break
        return s

    def observe_focus(self, focus_row):
        cur=self._candidate_snapshot(focus_row)
        if not cur:
            return None
        if any(str(x.get("origin_key"))==cur["origin_key"] for x in self.signal_history):
            return None
        self.focus_signals_seen += 1
        seq=(self.signal_history+[cur])[-8:]
        curset=self._set(cur); tr=self._trans_map(cur)
        nums=[]
        for n in sorted(curset):
            st=self._streak_number(seq,n)
            if st>=INCROCIO_MIN_STREAK:
                nums.append({"num":n,"streak":st,"trans":round(float(tr.get(n,0.0)),8),
                             "hit":False,"hit_colpo":None})
        nums.sort(key=lambda x:(-x["streak"],-x["trans"],x["num"]))
        pairs=[]
        cs=sorted(curset)
        for i,a in enumerate(cs):
            for b in cs[i+1:]:
                st=self._streak_pair(seq,a,b)
                if st>=INCROCIO_MIN_STREAK:
                    pairs.append({"pair":[a,b],"streak":st,
                                  "trans_sum":round(float(tr.get(a,0.0)+tr.get(b,0.0)),8),
                                  "hit":False,"hit_colpo":None})
        pairs.sort(key=lambda x:(-x["streak"],-x["trans_sum"],x["pair"][0],x["pair"][1]))
        self.signal_history.append(cur); self.signal_history=self.signal_history[-8:]
        if not nums and not pairs:
            self.no_incrocio += 1
            return None
        row={"origin_key":cur["origin_key"],"created_at":now_txt(),"age":0,
             "ambate":nums,"ambi":pairs,
             "top_ambata":int(nums[0]["num"]) if nums else None,
             "top_ambo":list(pairs[0]["pair"]) if pairs else None,
             "source_candidates":sorted(curset),"closed":False}
        self.pending.append(row); self.pending=self.pending[-40:]
        self.incrocio_signals += 1
        self.last_signal=dict(row)
        return row

    def advance(self, day, draw_id, nums):
        if not self.pending:
            return []
        key=draw_key(day,draw_id); actual=set(map(int,nums)); remain=[]; notices=[]
        for p in self.pending:
            r=dict(p)
            r["ambate"]=[dict(x) for x in list(p.get("ambate") or [])]
            r["ambi"]=[dict(x) for x in list(p.get("ambi") or [])]
            age=int(r.get("age",0) or 0)+1
            r["age"]=age; r["last_key"]=key
            new_a=[]; new_b=[]
            for x in r["ambate"]:
                if not x.get("hit") and int(x.get("num")) in actual:
                    x["hit"]=True; x["hit_colpo"]=age; new_a.append(int(x["num"]))
            for x in r["ambi"]:
                pair=list(x.get("pair") or [])
                if len(pair)==2 and not x.get("hit") and int(pair[0]) in actual and int(pair[1]) in actual:
                    x["hit"]=True; x["hit_colpo"]=age; new_b.append([int(pair[0]),int(pair[1])])
            all_a=all(bool(x.get("hit")) for x in r["ambate"]) if r["ambate"] else True
            all_b=all(bool(x.get("hit")) for x in r["ambi"]) if r["ambi"] else True
            close=age>=INCROCIO_HORIZON or (all_a and all_b)
            if close:
                r["closed"]=True; r["closed_key"]=key
                self.records.append(r); self.records=self.records[-INCROCIO_RECORD_MAX:]
                self.last_result=r
            else:
                remain.append(r)
            if new_a or new_b or close:
                notices.append({"row":r,"new_ambate":new_a,"new_ambi":new_b,"closed":close})
        self.pending=remain
        return notices

    @staticmethod
    def _stats(rows):
        rr=[r for r in rows if isinstance(r,dict) and r.get("closed")]
        n=len(rr)
        an=sum(len(list(r.get("ambate") or [])) for r in rr)
        ah=sum(sum(bool(x.get("hit")) for x in list(r.get("ambate") or [])) for r in rr)
        pn=sum(len(list(r.get("ambi") or [])) for r in rr)
        ph=sum(sum(bool(x.get("hit")) for x in list(r.get("ambi") or [])) for r in rr)
        sr=[r for r in rr if r.get("ambi")]
        anyph=sum(any(bool(x.get("hit")) for x in list(r.get("ambi") or [])) for r in sr)
        return n,an,ah,pn,ph,len(sr),anyph

    def signal_text(self,row):
        if not row: return None
        lines=["🔗 INCROCIO FOCUS v1 — RETE PERSISTENTE H1-H5",f"Origine: {row.get('origin_key')}"]
        aa=list(row.get("ambate") or [])
        pp=list(row.get("ambi") or [])
        if aa:
            lines.append("🎯 AMBATE PERSISTENTI:")
            for x in aa:
                star=" ⭐TOP" if int(x.get("num"))==int(row.get("top_ambata") or -1) else ""
                lines.append(f"• #{x.get('num')} ×{x.get('streak')} | T80 {float(x.get('trans') or 0):.4f}{star}")
        if pp:
            lines.append("💥 AMBI PERSISTENTI:")
            top=list(row.get("top_ambo") or [])
            for x in pp:
                a,b=x["pair"]; lvl=" 🔥" if int(x.get("streak",0) or 0)>=3 else ""
                star=" ⭐TOP" if [a,b]==top else ""
                lines.append(f"• {a}-{b} ×{x.get('streak')}{lvl}{star}")
        lines.append(f"⏳ Tutti gli incroci restano congelati fino a H{INCROCIO_HORIZON}; ambo valido solo se i 2 numeri escono nello STESSO draw.")
        return "\n".join(lines)

    def result_text(self,event):
        if not isinstance(event,dict): return None
        r=event.get("row") or {}
        lines=["🧾 INCROCIO FOCUS v1 — AGGIORNAMENTO",f"Origine {r.get('origin_key')} | H{r.get('age')} → {r.get('last_key','-')}"]
        if event.get("new_ambate"):
            lines.append("🎯 AMBATA HIT: " + ", ".join(f"#{n}" for n in event["new_ambate"]))
        if event.get("new_ambi"):
            lines.append("💥 AMBO HIT: " + ", ".join(f"{a}-{b}" for a,b in event["new_ambi"]))
        if event.get("closed"):
            miss_a=[x for x in r.get("ambate",[]) if not x.get("hit")]
            miss_b=[x for x in r.get("ambi",[]) if not x.get("hit")]
            if miss_a: lines.append("❌ AMBATE non uscite entro H5: " + ", ".join(f"#{x['num']}" for x in miss_a))
            if miss_b: lines.append("❌ AMBI non usciti entro H5: " + ", ".join(f"{x['pair'][0]}-{x['pair'][1]}" for x in miss_b))
            if not miss_a and not miss_b: lines.append("✅ Tutti i target INCROCIO di questa origine sono chiusi in HIT.")
        return "\n".join(lines) if len(lines)>2 else None

    def text(self):
        n,an,ah,pn,ph,sn,sah=self._stats(self.records)
        lines=["🔗 INCROCIO FOCUS v1 — TUTTI GLI INCROCI H1-H5",
               "Regola: ogni numero/coppia presente in almeno 2 segnali FOCUS consecutivi viene congelato e seguito.",
               f"🧊 Inizio prospettico: dopo {self.start_from_key or '-'}" + (f" | {self.started_at}" if self.started_at else ""),
               f"FOCUS osservati: {self.focus_signals_seen} | origini INCROCIO: {self.incrocio_signals} | senza incrocio: {self.no_incrocio} | pending {len(self.pending)}",
               f"🎯 AMBATE individuali entro H{INCROCIO_HORIZON}: {ah}/{an} ({safe_pct(ah,an):.2f}%) | baseline teorica H5 ≈71.54%",
               f"💥 AMBI individuali stesso draw entro H{INCROCIO_HORIZON}: {ph}/{pn} ({safe_pct(ph,pn):.2f}%) | baseline coppia fissa H5 ≈21.57%",
               f"🕸️ Origini con almeno un AMBO: {sah}/{sn} ({safe_pct(sah,sn):.2f}%)"]
        if self.pending:
            lines += ["", "⏳ PENDENTI:"]
            for p in self.pending[-6:]:
                aa=" ".join(f"#{x['num']}×{x['streak']}" for x in p.get("ambate",[])) or "-"
                pp=" ".join(f"{x['pair'][0]}-{x['pair'][1]}×{x['streak']}" for x in p.get("ambi",[])) or "-"
                lines.append(f"• {p.get('origin_key')} | prossimo H{int(p.get('age',0))+1} | A {aa} | AMBI {pp}")
        if self.last_result:
            r=self.last_result
            hit_a=sum(bool(x.get("hit")) for x in r.get("ambate",[])); tot_a=len(r.get("ambate",[]))
            hit_b=sum(bool(x.get("hit")) for x in r.get("ambi",[])); tot_b=len(r.get("ambi",[]))
            lines += ["",f"🧾 Ultimo chiuso {r.get('origin_key')}: ambate {hit_a}/{tot_a} | ambi {hit_b}/{tot_b}"]
        lines.append("⚠️ Nuovo tracker prospettico v18: nessun backfill dei risultati INCROCIO.")
        return "\n".join(lines)


# ============================================================
# FOCUS CORE + SYNC20 v1 — PRIMO x2, 3 CANDIDATI, AMBO H1-H5
# ============================================================
# Tracker prospettico separato. Non modifica FOCUS FAST o INCROCIO v1.
# Regola congelata:
# - usa SOLO un nuovo segnale FOCUS con esattamente 3 candidati;
# - una coppia entra in CORE solo quando raggiunge per la PRIMA volta streak x2
#   tra segnali FOCUS consecutivi (streak corrente ESATTAMENTE 2);
# - SYNC20 viene calcolato PRIMA della finestra futura usando esclusivamente i
#   20 draw conclusi PRECEDENTI al draw origine (il draw origine e' escluso);
# - observed = quante volte i 2 numeri sono usciti insieme nei 20 draw;
# - expected = countA * countB / 20, cioe' atteso sotto indipendenza empirica;
# - il target nasce solo se observed > expected;
# - ogni coppia ammessa e' congelata fino a H5 e fa HIT solo se i due numeri
#   escono nello STESSO draw.
# ============================================================
CORE_SYNC_VERSION = 1
CORE_SYNC_WINDOW = max(5, int(os.getenv("CORE_SYNC_WINDOW", "20")))
CORE_SYNC_HORIZON = max(1, int(os.getenv("CORE_SYNC_HORIZON", "5")))
CORE_SYNC_RECORD_MAX = max(300, int(os.getenv("CORE_SYNC_RECORD_MAX", "5000")))
CORE_SYNC_NOTIFY = os.getenv("CORE_SYNC_NOTIFY", "1").strip().lower() not in {"0","false","no","off"}
CORE_SYNC_NOTIFY_RESULT = os.getenv("CORE_SYNC_NOTIFY_RESULT", "1").strip().lower() not in {"0","false","no","off"}


class FocusCoreSync20V1:
    def __init__(self):
        self.start_from_key=None
        self.started_at=None
        self.signal_history=[]
        self.pending=[]
        self.records=[]
        self.focus_signals_seen=0
        self.focus3_seen=0
        self.first_x2_pairs=0
        self.sync_pass_pairs=0
        self.core_signals=0
        self.no_signal=0
        self.history_insufficient=0
        self.skipped=0
        self.seeded_context=False
        self.last_signal=None
        self.last_result=None

    def ensure_start(self, engine):
        if self.start_from_key:
            return False
        if not engine.engine_history:
            return False
        key=str(engine.engine_history[-1].get("key") or "")
        if _verifica_order(key) is None:
            return False
        self.start_from_key=key
        self.started_at=datetime.now(BOT_TZ).isoformat(timespec="seconds")
        return True

    @staticmethod
    def _candidate_snapshot(row):
        if not isinstance(row,dict) or not isinstance(row.get("origin_key"),str):
            return None
        ranked=[]
        for x in list(row.get("ranked_candidates") or []):
            if not isinstance(x,dict):
                continue
            try:
                n=int(x.get("num")); tr=float(x.get("trans",0) or 0); gap=int(x.get("gap",0) or 0)
            except Exception:
                continue
            if 1 <= n <= 90:
                ranked.append({"num":n,"trans":tr,"gap":gap})
        if len(ranked) < 2:
            return None
        return {"origin_key":str(row.get("origin_key")),"ranked_candidates":ranked,
                "candidate_count":len(ranked),"seed":False}

    @staticmethod
    def _set(row):
        out=set()
        for x in list((row or {}).get("ranked_candidates") or []):
            try:
                n=int(x.get("num"))
                if 1 <= n <= 90: out.add(n)
            except Exception:
                pass
        return out

    def seed_from_focus(self, focus):
        if self.signal_history or self.seeded_context:
            return False
        rows=[]
        for r in list(getattr(focus,"records",[]) or [])[-3:]:
            x=self._candidate_snapshot(r)
            if x: rows.append(x)
        for r in list(getattr(focus,"pending",[]) or [])[-2:]:
            x=self._candidate_snapshot(r)
            if x: rows.append(x)
        ded={x["origin_key"]:x for x in rows}
        rows=sorted(ded.values(),key=lambda r:_verifica_order(r["origin_key"]) or (-1,-1))
        if rows:
            x=dict(rows[-1]); x["seed"]=True; self.signal_history=[x]
        self.seeded_context=True
        return bool(rows)

    def load(self,obj):
        if not isinstance(obj,dict) or int(obj.get("version",0) or 0) != CORE_SYNC_VERSION:
            return False
        key=obj.get("start_from_key")
        if _verifica_order(key) is None:
            return False
        self.start_from_key=key
        self.started_at=obj.get("started_at") if isinstance(obj.get("started_at"),str) else None
        for name in ("focus_signals_seen","focus3_seen","first_x2_pairs","sync_pass_pairs","core_signals","no_signal","history_insufficient","skipped"):
            setattr(self,name,max(0,int(obj.get(name,0) or 0)))
        self.seeded_context=bool(obj.get("seeded_context",False))
        sh=obj.get("signal_history",[])
        if isinstance(sh,list):
            self.signal_history=[dict(x) for x in sh[-2:] if isinstance(x,dict) and isinstance(x.get("origin_key"),str)]
        pp=obj.get("pending",[])
        if isinstance(pp,list):
            self.pending=[dict(x) for x in pp[-30:] if isinstance(x,dict) and isinstance(x.get("origin_key"),str)]
        rr=obj.get("records",[])
        if isinstance(rr,list):
            self.records=[dict(x) for x in rr[-CORE_SYNC_RECORD_MAX:] if isinstance(x,dict) and isinstance(x.get("origin_key"),str)]
        self.last_signal=obj.get("last_signal") if isinstance(obj.get("last_signal"),dict) else None
        self.last_result=obj.get("last_result") if isinstance(obj.get("last_result"),dict) else None
        return True

    def dump(self):
        return {"version":CORE_SYNC_VERSION,"start_from_key":self.start_from_key,"started_at":self.started_at,
                "signal_history":self.signal_history[-2:],"pending":self.pending[-30:],
                "records":self.records[-CORE_SYNC_RECORD_MAX:],"focus_signals_seen":self.focus_signals_seen,
                "focus3_seen":self.focus3_seen,"first_x2_pairs":self.first_x2_pairs,
                "sync_pass_pairs":self.sync_pass_pairs,"core_signals":self.core_signals,
                "no_signal":self.no_signal,"history_insufficient":self.history_insufficient,
                "skipped":self.skipped,"seeded_context":self.seeded_context,
                "last_signal":self.last_signal,"last_result":self.last_result}

    @staticmethod
    def _phi(n, ca, cb, both):
        # 2x2 phi, solo descrittivo; non decide il segnale.
        a=float(both); b=float(ca-both); c=float(cb-both); d=float(n-ca-cb+both)
        den=(a+b)*(c+d)*(a+c)*(b+d)
        if den <= 0: return 0.0
        return (a*d-b*c)/math.sqrt(den)

    def _sync20(self, engine, origin_key, a, b):
        hist=list(getattr(engine,"engine_history",[]) or [])
        idx=None
        for i in range(len(hist)-1,-1,-1):
            if str(hist[i].get("key"))==str(origin_key):
                idx=i; break
        if idx is None or idx < CORE_SYNC_WINDOW:
            return None
        # ESCLUDE il draw origine: ultimi 20 draw completamente precedenti.
        rows=hist[idx-CORE_SYNC_WINDOW:idx]
        if len(rows) != CORE_SYNC_WINDOW:
            return None
        ca=cb=both=0
        for r in rows:
            ss=set(map(int,r.get("nums") or []))
            ha=a in ss; hb=b in ss
            ca += int(ha); cb += int(hb); both += int(ha and hb)
        expected=(ca*cb)/float(CORE_SYNC_WINDOW)
        lift=(both/expected) if expected>0 else (float("inf") if both>0 else 0.0)
        delta=both-expected
        return {"window":CORE_SYNC_WINDOW,"count_a":ca,"count_b":cb,"observed":both,
                "expected":round(expected,6),"delta":round(delta,6),
                "lift":round(lift,6) if math.isfinite(lift) else 999.0,
                "phi":round(self._phi(CORE_SYNC_WINDOW,ca,cb,both),6),
                "pass":bool(both>expected)}

    def observe_focus(self, focus_row, engine):
        cur=self._candidate_snapshot(focus_row)
        if not cur:
            return None
        if any(str(x.get("origin_key"))==cur["origin_key"] for x in self.signal_history):
            return None
        self.focus_signals_seen += 1
        prev=self.signal_history[-1] if self.signal_history else None
        self.signal_history.append(cur); self.signal_history=self.signal_history[-2:]

        # CORE valuta SOLO il segnale corrente con esattamente 3 candidati.
        if int(cur.get("candidate_count",0) or 0) != 3:
            self.no_signal += 1
            return None
        self.focus3_seen += 1
        if not prev:
            self.no_signal += 1
            return None

        curset=self._set(cur); prevset=self._set(prev)
        # Prima x2 = presenti ora e nel precedente, ma non possiamo avere streak >2
        # perché signal_history conserva anche il contesto; per distinguere >2 usiamo
        # i candidati del penultimo segnale se disponibili dal focus state via seed/list.
        # Qui il criterio operativo e' semplicemente: coppia comune con il segnale
        # immediatamente precedente e streak INCROCIO corrente esattamente 2.
        common=sorted(curset & prevset)
        if len(common)<2:
            self.no_signal += 1
            return None

        # Recupera, quando possibile, il segnale FOCUS precedente al prev per evitare
        # di riaprire una coppia gia' x3+. Usiamo records+pending gia' congelati.
        older=None
        rows=[]
        for r in list(getattr(engine.focus,"records",[]) or [])[-6:]:
            x=self._candidate_snapshot(r)
            if x and x["origin_key"] not in {cur["origin_key"],prev.get("origin_key")}:
                rows.append(x)
        for r in list(getattr(engine.focus,"pending",[]) or [])[-4:]:
            x=self._candidate_snapshot(r)
            if x and x["origin_key"] not in {cur["origin_key"],prev.get("origin_key")}:
                rows.append(x)
        po=_verifica_order(prev.get("origin_key"))
        candidates=[]
        for x in rows:
            xo=_verifica_order(x.get("origin_key"))
            if xo is not None and po is not None and xo < po:
                candidates.append(x)
        if candidates:
            older=max(candidates,key=lambda x:_verifica_order(x["origin_key"]) or (-1,-1))
        oldset=self._set(older) if older else set()

        pairs=[]
        for a,b in combinations(common,2):
            # Se entrambi erano anche nel segnale ancora precedente, la coppia e' gia' x3+.
            if a in oldset and b in oldset:
                continue
            self.first_x2_pairs += 1
            sync=self._sync20(engine,cur["origin_key"],a,b)
            if sync is None:
                self.history_insufficient += 1
                continue
            if not sync.get("pass"):
                continue
            self.sync_pass_pairs += 1
            pairs.append({"pair":[a,b],"streak":2,"sync20":sync,
                          "hit":False,"hit_colpo":None})
        if not pairs:
            self.no_signal += 1
            return None
        pairs.sort(key=lambda x:(-float(x["sync20"].get("delta",0)),
                                 -float(x["sync20"].get("phi",0)),x["pair"][0],x["pair"][1]))
        row={"origin_key":cur["origin_key"],"created_at":now_txt(),"age":0,
             "pairs":pairs,"source_candidates":sorted(curset),"candidate_count":3,
             "closed":False,"rule":"FOCUS3 + first_x2 + SYNC20 observed>expected"}
        self.pending.append(row); self.pending=self.pending[-30:]
        self.core_signals += 1
        self.last_signal=dict(row)
        return row

    def advance(self,day,draw_id,nums):
        if not self.pending:
            return []
        key=draw_key(day,draw_id); actual=set(map(int,nums)); remain=[]; notices=[]
        for p in self.pending:
            r=dict(p); r["pairs"]=[dict(x) for x in list(p.get("pairs") or [])]
            age=int(r.get("age",0) or 0)+1; r["age"]=age; r["last_key"]=key
            new=[]
            for x in r["pairs"]:
                pair=list(x.get("pair") or [])
                if len(pair)==2 and not x.get("hit") and int(pair[0]) in actual and int(pair[1]) in actual:
                    x["hit"]=True; x["hit_colpo"]=age; new.append([int(pair[0]),int(pair[1])])
            all_hit=all(bool(x.get("hit")) for x in r["pairs"]) if r["pairs"] else True
            close=age>=CORE_SYNC_HORIZON or all_hit
            if close:
                r["closed"]=True; r["closed_key"]=key
                self.records.append(r); self.records=self.records[-CORE_SYNC_RECORD_MAX:]
                self.last_result=r
            else:
                remain.append(r)
            if new or close:
                notices.append({"row":r,"new_pairs":new,"closed":close})
        self.pending=remain
        return notices

    @staticmethod
    def _stats(rows):
        rr=[r for r in rows if isinstance(r,dict) and r.get("closed")]
        targets=[x for r in rr for x in list(r.get("pairs") or [])]
        n=len(targets); h=sum(bool(x.get("hit")) for x in targets)
        origins=[r for r in rr if r.get("pairs")]
        oh=sum(any(bool(x.get("hit")) for x in r.get("pairs",[])) for r in origins)
        by={i:[0,0] for i in range(1,CORE_SYNC_HORIZON+1)}
        for x in targets:
            if x.get("hit"):
                c=int(x.get("hit_colpo",0) or 0)
                if c in by: by[c][1]+=1
            # denominator cumulative target count is reported separately, not per-colpo probability
        return len(rr),n,h,len(origins),oh,by

    def signal_text(self,row):
        if not row: return None
        lines=["🧬 FOCUS CORE + SYNC20 v1 — AMBO SHADOW H1-H5",
               f"Origine: {row.get('origin_key')}",
               "Regola: SOLO 3 candidati | coppia alla PRIMA ×2 | SYNC20 observed > expected.",
               "💥 COPPIE CORE:"]
        for x in row.get("pairs",[]):
            a,b=x["pair"]; q=x.get("sync20") or {}
            lines.append(f"• {a}-{b} ×2 | obs {q.get('observed')}/{CORE_SYNC_WINDOW} | att {float(q.get('expected',0)):.2f} | lift {float(q.get('lift',0)):.2f} | φ {float(q.get('phi',0)):.3f}")
        lines.append(f"⏳ Ogni coppia resta congelata fino a H{CORE_SYNC_HORIZON}; HIT solo nello STESSO draw.")
        lines.append("⚠️ Tracker prospettico: non modifica FOCUS FAST o INCROCIO v1.")
        return "\n".join(lines)

    def result_text(self,event):
        if not isinstance(event,dict): return None
        r=event.get("row") or {}
        lines=["🧾 FOCUS CORE + SYNC20 v1 — AGGIORNAMENTO",
               f"Origine {r.get('origin_key')} | H{r.get('age')} → {r.get('last_key','-')}"]
        if event.get("new_pairs"):
            lines.append("💥 AMBO CORE HIT: " + ", ".join(f"{a}-{b}" for a,b in event["new_pairs"]))
        if event.get("closed"):
            miss=[x for x in r.get("pairs",[]) if not x.get("hit")]
            if miss:
                lines.append(f"❌ CORE non usciti entro H{CORE_SYNC_HORIZON}: " + ", ".join(f"{x['pair'][0]}-{x['pair'][1]}" for x in miss))
            elif r.get("pairs"):
                lines.append("✅ Tutte le coppie CORE di questa origine sono chiuse in HIT.")
        return "\n".join(lines) if len(lines)>2 else None

    def text(self):
        rn,n,h,on,oh,by=self._stats(self.records)
        lines=["🧬 FOCUS CORE + SYNC20 v1 — PRIMA ×2 / SOLO 3 CANDIDATI",
               "Regola congelata: segnale FOCUS a 3 candidati; coppia al primo streak ×2; SYNC20 sui 20 draw PRECEDENTI; passa solo observed > expected.",
               f"🧊 Inizio prospettico: dopo {self.start_from_key or '-'}" + (f" | {self.started_at}" if self.started_at else ""),
               f"FOCUS osservati {self.focus_signals_seen} | FOCUS a 3 {self.focus3_seen} | prime ×2 esaminate {self.first_x2_pairs} | SYNC20 PASS {self.sync_pass_pairs}",
               f"Origini CORE {self.core_signals} | chiuse {rn} | pending {len(self.pending)} | no signal {self.no_signal} | history insufficiente {self.history_insufficient}",
               f"💥 AMBI CORE H{CORE_SYNC_HORIZON}: {h}/{n} ({safe_pct(h,n):.2f}%) | baseline coppia fissa H5 ≈21.57%",
               f"🕸️ Origini con almeno un ambo: {oh}/{on} ({safe_pct(oh,on):.2f}%)"]
        if self.pending:
            lines += ["","⏳ PENDENTI CORE:"]
            for p in self.pending[-6:]:
                vals=[]
                for x in p.get("pairs",[]):
                    a,b=x["pair"]; q=x.get("sync20") or {}
                    vals.append(f"{a}-{b}(obs{q.get('observed')}>att{float(q.get('expected',0)):.1f})")
                lines.append(f"• {p.get('origin_key')} | prossimo H{int(p.get('age',0))+1} | " + " ".join(vals))
        if self.last_result:
            r=self.last_result; hh=sum(bool(x.get("hit")) for x in r.get("pairs",[])); tt=len(r.get("pairs",[]))
            lines += ["",f"🧾 Ultimo chiuso {r.get('origin_key')}: ambi CORE {hh}/{tt}"]
        lines.append("⚠️ Nuovo tracker prospettico v19: nessun backfill dei risultati CORE.")
        return "\n".join(lines)


# ============================================================
# MULTI-CHANNEL BD12 + ED12 + O2F12 v1 — LIVE TEST prospettico
# ============================================================
# Regola congelata dal test storico gennaio-settembre 2025:
#   TOP12 Base RITARDATARI
# ∩ TOP12 Extra RITARDATARI
# ∩ TOP12 Oro2 / Doppio Oro FREQUENTI negli ultimi 80 draw
# Ogni numero dell'intersezione e' un segnale individuale Base H1/H3/H5.
# Cooldown: 5 draw sullo stesso numero. Nessun backfill dei risultati.
MULTI_BD_ED_O2_VERSION = 1
MULTI_BD_ED_O2_WINDOW = max(20, int(os.getenv("MULTI_BD_ED_O2_WINDOW", "80")))
MULTI_BD_ED_O2_TOP_N = max(1, min(30, int(os.getenv("MULTI_BD_ED_O2_TOP_N", "12"))))
MULTI_BD_ED_O2_COOLDOWN = max(0, int(os.getenv("MULTI_BD_ED_O2_COOLDOWN", "5")))
MULTI_BD_ED_O2_HORIZON = max(1, int(os.getenv("MULTI_BD_ED_O2_HORIZON", "5")))
MULTI_BD_ED_O2_HISTORY_MAX = max(200, int(os.getenv("MULTI_BD_ED_O2_HISTORY_MAX", "900")))
MULTI_BD_ED_O2_RECORD_MAX = max(500, int(os.getenv("MULTI_BD_ED_O2_RECORD_MAX", "8000")))
MULTI_BD_ED_O2_NOTIFY = os.getenv("MULTI_BD_ED_O2_NOTIFY", "1").strip().lower() not in {"0","false","no","off"}
MULTI_BD_ED_O2_NOTIFY_RESULT = os.getenv("MULTI_BD_ED_O2_NOTIFY_RESULT", "1").strip().lower() not in {"0","false","no","off"}

class MultiChannelBD12ED12O2F12V1:
    def __init__(self):
        self.start_from_key=None; self.started_at=None; self.history=[]; self.history_keys=set()
        self.pending=[]; self.records=[]; self.draw_seq=0; self.last_signal_seq={}
        self.last_armed_key=None; self.scans=0; self.signals=0; self.no_signal=0
        self.cooldown_skips=0; self.last_signal=None; self.last_result=None

    @staticmethod
    def _sanitize_row(row):
        if not isinstance(row,dict): return None
        try:
            key=str(row.get("key") or draw_key(row.get("day"),row.get("draw_id")))
            day,sid=key.rsplit("#",1); draw_id=int(sid)
            nums=[int(x) for x in row.get("nums",[])]; extra=[int(x) for x in row.get("extra",[])]
            oro=int(row.get("oro")); doppio=int(row.get("doppio_oro"))
        except Exception: return None
        if len(nums)!=20 or len(set(nums))!=20 or any(n<1 or n>90 for n in nums): return None
        if len(extra)!=15 or len(set(extra))!=15 or any(n<1 or n>90 for n in extra): return None
        if oro not in nums or doppio not in nums: return None
        return {"key":key,"day":day,"draw_id":draw_id,"nums":nums,"oro":oro,"doppio_oro":doppio,"extra":extra}

    def _refresh_keys(self): self.history_keys={str(r.get("key")) for r in self.history if isinstance(r,dict)}
    def bootstrap(self,rows):
        clean=[r for row in (rows or []) if (r:=self._sanitize_row(row))]
        ded={r["key"]:r for r in clean}
        clean=sorted(ded.values(),key=lambda r:_verifica_order(r["key"]) or (-1,-1))
        if clean:
            self.history=clean[-MULTI_BD_ED_O2_HISTORY_MAX:]; self.draw_seq=max(self.draw_seq,len(self.history)); self._refresh_keys()
        return len(self.history)
    def ensure_start(self):
        if self.start_from_key or not self.history: return False
        self.start_from_key=str(self.history[-1]["key"]); self.started_at=datetime.now(BOT_TZ).isoformat(timespec="seconds"); return True
    def seen(self,key): return str(key) in self.history_keys
    def load(self,obj):
        if not isinstance(obj,dict) or int(obj.get("version",0) or 0)!=MULTI_BD_ED_O2_VERSION: return False
        hist=[r for row in obj.get("history",[]) if (r:=self._sanitize_row(row))]
        ded={r["key"]:r for r in hist}
        self.history=sorted(ded.values(),key=lambda r:_verifica_order(r["key"]) or (-1,-1))[-MULTI_BD_ED_O2_HISTORY_MAX:]; self._refresh_keys()
        sfk=obj.get("start_from_key"); self.start_from_key=str(sfk) if _verifica_order(sfk) is not None else None
        self.started_at=obj.get("started_at") if isinstance(obj.get("started_at"),str) else None
        self.pending=[dict(x) for x in obj.get("pending",[]) if isinstance(x,dict) and x.get("origin_key")][-200:]
        self.records=[dict(x) for x in obj.get("records",[]) if isinstance(x,dict) and x.get("origin_key")][-MULTI_BD_ED_O2_RECORD_MAX:]
        self.draw_seq=max(int(obj.get("draw_seq",0) or 0),len(self.history))
        raw=obj.get("last_signal_seq",{}); self.last_signal_seq={int(k):int(v) for k,v in raw.items() if str(k).isdigit() and 1<=int(k)<=90} if isinstance(raw,dict) else {}
        self.last_armed_key=obj.get("last_armed_key") if isinstance(obj.get("last_armed_key"),str) else None
        for a in ("scans","signals","no_signal","cooldown_skips"): setattr(self,a,max(0,int(obj.get(a,0) or 0)))
        self.last_signal=obj.get("last_signal") if isinstance(obj.get("last_signal"),dict) else None
        self.last_result=obj.get("last_result") if isinstance(obj.get("last_result"),dict) else None
        return True
    def dump(self):
        return {"version":MULTI_BD_ED_O2_VERSION,"start_from_key":self.start_from_key,"started_at":self.started_at,
                "history":self.history[-MULTI_BD_ED_O2_HISTORY_MAX:],"pending":self.pending[-200:],"records":self.records[-MULTI_BD_ED_O2_RECORD_MAX:],
                "draw_seq":self.draw_seq,"last_signal_seq":{str(k):int(v) for k,v in self.last_signal_seq.items()},"last_armed_key":self.last_armed_key,
                "scans":self.scans,"signals":self.signals,"no_signal":self.no_signal,"cooldown_skips":self.cooldown_skips,
                "last_signal":self.last_signal,"last_result":self.last_result}
    @staticmethod
    def _gap(history,n,field):
        gap=0
        for r in reversed(history):
            vals=r[field] if isinstance(r.get(field),list) else [r.get(field)]
            if n in vals: return gap
            gap+=1
        return len(history)+1
    def _rankings(self):
        if len(self.history)<MULTI_BD_ED_O2_WINDOW: return None
        w=self.history[-MULTI_BD_ED_O2_WINDOW:]
        base_gap={n:self._gap(self.history,n,"nums") for n in range(1,91)}
        extra_gap={n:self._gap(self.history,n,"extra") for n in range(1,91)}
        o2_freq={n:0 for n in range(1,91)}
        for r in w: o2_freq[int(r["doppio_oro"])]+=1
        top_base_delay=sorted(range(1,91),key=lambda n:(-base_gap[n],n))[:MULTI_BD_ED_O2_TOP_N]
        top_extra_delay=sorted(range(1,91),key=lambda n:(-extra_gap[n],n))[:MULTI_BD_ED_O2_TOP_N]
        top_o2=sorted(range(1,91),key=lambda n:(-o2_freq[n],n))[:MULTI_BD_ED_O2_TOP_N]
        return {"base_gap":base_gap,"extra_gap":extra_gap,"o2_freq":o2_freq,
                "top_base_delay":top_base_delay,"top_extra_delay":top_extra_delay,"top_o2":top_o2}
    def advance(self,row):
        r=self._sanitize_row(row)
        if not r or not self.pending: return []
        actual=set(r["nums"]); remain=[]; events=[]
        for p in self.pending:
            q=dict(p); age=int(q.get("age",0) or 0)+1; q["age"]=age; q["last_key"]=r["key"]
            hit_now=(not q.get("hit")) and int(q.get("num",0)) in actual
            if hit_now: q["hit"]=True; q["hit_colpo"]=age
            close=bool(q.get("hit")) or age>=MULTI_BD_ED_O2_HORIZON
            if age==1 or hit_now or (close and not q.get("hit")): events.append({"row":dict(q),"hit_now":hit_now,"closed":close})
            if close:
                q["closed"]=True; q["closed_key"]=r["key"]; self.records.append(q); self.records=self.records[-MULTI_BD_ED_O2_RECORD_MAX:]; self.last_result=dict(q)
            else: remain.append(q)
        self.pending=remain; return events
    def ingest(self,row):
        r=self._sanitize_row(row)
        if not r or self.seen(r["key"]): return []
        events=self.advance(r); self.history.append(r); self.history=self.history[-MULTI_BD_ED_O2_HISTORY_MAX:]
        self.draw_seq+=1; self._refresh_keys(); return events
    def arm(self):
        if not self.history or len(self.history)<MULTI_BD_ED_O2_WINDOW: return None
        origin_key=str(self.history[-1]["key"])
        if self.last_armed_key==origin_key: return None
        self.last_armed_key=origin_key; self.scans+=1; ranks=self._rankings()
        if not ranks: self.no_signal+=1; return None
        inter=sorted(set(ranks["top_base_delay"]) & set(ranks["top_extra_delay"]) & set(ranks["top_o2"]))
        selected=[]; blocked=[]
        for n in inter:
            last=self.last_signal_seq.get(int(n))
            if last is not None and self.draw_seq-int(last)<MULTI_BD_ED_O2_COOLDOWN:
                self.cooldown_skips+=1; blocked.append(int(n)); continue
            selected.append(int(n))
        if not selected: self.no_signal+=1; return None
        details=[]
        for n in selected:
            d={"num":n,"base_gap":int(ranks["base_gap"][n]),"extra_gap":int(ranks["extra_gap"][n]),"o2_freq80":int(ranks["o2_freq"][n])}
            details.append(d)
            self.pending.append({"origin_key":origin_key,"num":n,"age":0,"hit":False,"hit_colpo":None,"created_at":now_txt(),
                                 "base_gap":d["base_gap"],"extra_gap":d["extra_gap"],"o2_freq80":d["o2_freq80"]})
            self.last_signal_seq[n]=self.draw_seq
        self.pending=self.pending[-200:]; self.signals+=len(selected)
        out={"origin_key":origin_key,"numbers":selected,"details":details,"top_base_delay":ranks["top_base_delay"],
             "top_extra_delay":ranks["top_extra_delay"],"top_o2":ranks["top_o2"],"blocked":blocked}
        self.last_signal=dict(out); return out
    @staticmethod
    def signal_text(sig):
        if not sig: return None
        lines=["🧪 MULTI BD12+ED12+O2F12 — SEGNALE LIVE","Origine: "+str(sig.get("origin_key")),
               "Metodo congelato: Base RIT TOP12 ∩ Extra RIT TOP12 ∩ Oro2 FREQ TOP12 (W80)",
               f"🎯 AMBATA/E Base H1-H5: {' '.join(f'{int(n):02d}' for n in sig.get('numbers',[]))}",""]
        for d in sig.get("details",[]): lines.append(f"• {int(d['num']):02d}: Base ritardo={d['base_gap']} | Extra ritardo={d['extra_gap']} | Oro2 freq80={d['o2_freq80']}")
        lines += ["","⏱️ Valuto H1 / H3 / H5. Cooldown stesso numero: 5 draw.","⚠️ Modulo prospettico separato: nessun backfill; FOCUS/INCROCIO/CORE invariati."]
        return "\n".join(lines)
    @staticmethod
    def result_text(ev):
        if not ev or not isinstance(ev.get("row"),dict): return None
        r=ev["row"]; n=int(r.get("num",0)); age=int(r.get("age",0) or 0)
        status=f"✅ HIT al colpo H{age}" if ev.get("hit_now") else ("❌ H1 MISS — resta aperto fino a H5" if age==1 else "🛑 STOP H5")
        return ("🧾 MULTI BD12+ED12+O2F12 — ESITO\n\n"+f"Origine {r.get('origin_key')} | numero {n:02d}\n{status}\n"+
                f"Base ritardo={r.get('base_gap')} | Extra ritardo={r.get('extra_gap')} | Oro2 freq80={r.get('o2_freq80')}")
    def _stats(self):
        rows=list(self.records); n=len(rows)
        h1=sum(1 for r in rows if int(r.get("hit_colpo") or 99)<=1); h3=sum(1 for r in rows if int(r.get("hit_colpo") or 99)<=3); h5=sum(1 for r in rows if bool(r.get("hit")))
        return n,h1,h3,h5
    def text(self):
        n,h1,h3,h5=self._stats()
        lines=["🧪 MULTI BD12+ED12+O2F12 v1 — LIVE TEST","Regola: Base RIT TOP12 ∩ Extra RIT TOP12 ∩ Oro2 FREQ TOP12",
               f"Finestra Oro2: {MULTI_BD_ED_O2_WINDOW} | cooldown stesso numero: {MULTI_BD_ED_O2_COOLDOWN} | horizon H{MULTI_BD_ED_O2_HORIZON}",
               f"Storico completo: {len(self.history)} | scan live {self.scans} | segnali {self.signals} | pending {len(self.pending)} | cooldown skip {self.cooldown_skips}",
               f"H1 {h1}/{n} ({safe_pct(h1,n):.2f}%) | H3 {h3}/{n} ({safe_pct(h3,n):.2f}%) | H5 {h5}/{n} ({safe_pct(h5,n):.2f}%)",
               "Baseline teorica: H1 22.22% | H3 52.95% | H5 71.54%."]
        if self.pending: lines.append("Pending: "+", ".join(f"{int(x['num']):02d}@H{int(x.get('age',0))+1}" for x in self.pending[-12:]))
        if self.last_signal: lines.append("Ultimo segnale: "+str(self.last_signal.get("origin_key"))+" → "+" ".join(f"{int(n):02d}" for n in self.last_signal.get("numbers",[])))
        lines.append("⚠️ Prospettico dal momento dell'installazione: nessun risultato ricostruito a posteriori.")
        return "\n".join(lines)


class EngineOnly:
    def __init__(self, load=True):
        self.processed = []
        self.processed_set = set()
        self.last_draw_key = None

        self.engine_model_version = ENGINE_MODEL_VERSION
        self.engine_bootstrap_done = False
        self.engine_history = []
        self.engine_pending = None
        self.engine_margin_history = []
        self.engine_recent_events = []
        self.engine_stats_warmup = self._new_engine_stats()
        self.engine_stats_live = self._new_engine_stats()

        self.engine_h5_sessions = []
        self.engine_h5_records_warmup = []
        self.engine_h5_records_live = []
        self.engine_multi_diag_version = ENGINE_MULTI_DIAG_VERSION

        # PLAY SHADOW derivato dal MULTI-HIT: nessun impatto su score/soglia/HC.
        self.engine_play_diag_version = ENGINE_PLAY_DIAG_VERSION
        self.engine_play_sessions = []
        self.engine_play_records_warmup = []
        self.engine_play_records_live = []

        # AMBO e' prospettico. Le strategie precedenti vengono archiviate e
        # NON mescolate con il nuovo 2xHOT5 NO-LOCK.
        self.ambo_h2_legacy = {}
        self.ambo_hot5_single_legacy = {}
        self.ambo_sim_draw_index = 0
        self.ambo_sim_last_candidate_index = -100000
        self.ambo_sim_skipped_overlap = 0
        self.ambo_sim_sessions = []
        self.ambo_sim_records_live = []
        self.ambo_sim_bets_live = []
        self.ambo_sim_account = {"bets": 0, "wins": 0, "cost_cents": 0, "gross_cents": 0}

        # Registro indipendente e prospettico del generatore-sosia casuale 20/90.
        self.sosia_pending = None
        self.sosia_records = []
        self.sosia_totals = self._new_sosia_totals()
        # Un registro IN PIU': non azzerare o sostituire gli altri moduli.
        self.sosiap_pending = None
        self.sosiap_records = []
        self.sosiap_learning = {
            name: {"n": 0, "hits": 0, "ema_hits": 20.0 / 90.0 * 20.0}
            for name in SOSIA_PRED_NAMES
        }
        self.sosiap_totals = {"evaluated": 0, "hits": 0, "baseline_hits": 0,
                               "baseline_n": 0, "skipped": 0, "zero": 0}
        # Pre-training separato: non modifica i contatori prospettici, le sessioni
        # attive o i risultati degli altri moduli.
        self.sosiap_pretrain = None

        # SOSIA SNIPER e' SOLO un tracker prospettico della graduatoria interna
        # del SOSIA adattivo. E' aggiuntivo: non azzera e non modifica nulla.
        self.sosiasniper_pending = None
        self.sosiasniper_records = []
        self.sosiasniper_totals = {
            "evaluated": 0, "skipped": 0, "top1_hits": 0, "top2_hits": 0,
            "rank3_hits": 0, "rank4_hits": 0, "rank5_hits": 0,
            "ambo_hits": 0, "strong_evaluated": 0, "strong_top1_hits": 0,
            "strong_ambo_hits": 0,
            "prob_evaluated": 0, "prob_hits": 0,
            "bestpair_evaluated": 0, "bestpair_hits": 0,
            "fusion_evaluated": 0, "fusion_hits": 0,
            "fusion_top3_evaluated": 0, "fusion_top3_hits": 0,
            "ultra_evaluated": 0, "ultra_hits": 0,
        }

        # Registro indipendente: un record per draw confrontato, senza tagliare
        # i record di questo NUOVO tracker alle ultime N estrazioni.
        self.sosiapattern_pending = None
        self.sosiapattern_records = []
        self.sosiapattern_skipped = 0

        # Laboratorio prospettico sopra SOSIA PATTERN. Parte dal momento in cui
        # viene installato: usa il vecchio pattern come training, ma NON inventa
        # risultati retroattivi per le nuove regole.
        self.sosiapatternlab_pending = None
        self.sosiapatternlab_records = []
        self.sosiapatternlab_totals = {
            "evaluated": 0, "skipped": 0,
            "pos_evaluated": 0, "pos_hits": 0,
            "watch_evaluated": 0, "watch_picks": 0, "watch_hits": 0,
            "watch_top1_hits": 0,
            "transition_evaluated": 0, "transition_band_hits": 0,
            "transition_dom_evaluated": 0, "transition_dom_correct": 0,
            "transition_ties": 0,
        }

        # Stato isolato: nessuno dei contatori preesistenti viene modificato.
        self.dual = DualTargetLab()
        self.decina = DecinaEngine()
        self.flow = DecinaFlowLab()
        self.burst = DecinaBurstLab()
        self.postburst = DecinaPostBurstLab()
        self.post6 = Post6ExtremeShadow()  # v10: dopo 6+ segue stessa decina solo H1
        self.verifica = VerificationLab()  # read-only report, marker persistente isolato
        self.burstgate = BurstGateLab()    # audit derivato dai record BURST, nessun nuovo motore
        self.convergence = ConvergenceLab()  # v11: audit prospettico delle convergenze POST-6
        self.hc_method = HCConvergenceMethod()  # v13: ENGINE HC + SOSIA rank1, BURST solo promozione SUPER
        self.forced_one = ForcedOneMethod()  # v14: un numero H1 sempre, classi A+/A/B/C/D
        self.triplette = TripletteCooccLab()  # v15: 4x9, triplette co-occorrenza, H1 shadow
        self.focus_legacy_state = None  # archivio raw v16, NON aggiornato
        self.focus = FocusFastV2()  # v19: generatore candidati, R13-18 / 3-4 candidati / TRANS80
        self.incrocio = IncrocioFocusV1()  # v19: persistenza candidati FOCUS, ambata+ambo H1-H5
        self.core_sync = FocusCoreSync20V1()  # v19: FOCUS3 + prima x2 + SYNC20 positivo, ambo H1-H5
        self.multichannel_bf12_legacy_state = None  # conserva il vecchio BF12, non piu attivo
        self.multichannel = MultiChannelBD12ED12O2F12V1()  # v20.2: BD12+ED12+O2F12 prospettico

        self.state_load_info = {
            "loaded": False,
            "migrated_legacy": False,
            "reason": "non ancora controllato",
            "saved_at": None,
            "path": STATE_FILE,
        }
        self.last_git_status = _git_status(True, "not-run", "nessun push ancora eseguito")
        if load:
            self.load_state()
            # v19: tutti i vecchi metodi legacy restano caricati nello state ma PAUSATI.
            # Nessun bootstrap/arm/settle live viene eseguito per loro.
            self.focus.ensure_start(self)  # marker v2 esistente, nessun backfill
            self.incrocio.ensure_start(self)
            self.incrocio.seed_from_focus(self.focus)  # solo contesto streak, nessun risultato retroattivo
            self.core_sync.ensure_start(self)
            self.core_sync.seed_from_focus(self.focus)  # solo ultimo segnale come contesto, nessun backfill

    @staticmethod
    def _new_engine_stats():
        return {
            "predictions": 0,
            "evaluated": 0,
            "all_top1_hits": 0,
            "signals": 0,
            "signals_evaluated": 0,
            "signal_top1_hits": 0,
            "no_signal": 0,
        }

    @staticmethod
    def _merge_engine_stats(dst, raw):
        raw = raw if isinstance(raw, dict) else {}
        for k in dst:
            try:
                dst[k] = int(raw.get(k, dst[k]) or 0)
            except Exception:
                pass
        return dst

    @staticmethod
    def _sanitize_engine_history(raw):
        out = []
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            try:
                nums = sorted(set(map(int, row.get("nums", []) or [])))
            except Exception:
                continue
            if len(nums) != 20 or any(n < 1 or n > 90 for n in nums):
                continue
            out.append({"key": str(row.get("key") or ""), "nums": nums})
        return out[-ENGINE_HISTORY_MAX:]

    @staticmethod
    def _sanitize_engine_pending(raw):
        if not isinstance(raw, dict):
            return None
        try:
            top1 = int(raw.get("top1"))
        except Exception:
            return None
        if not 1 <= top1 <= 90:
            return None
        clean = {
            "signal_from_key": str(raw.get("signal_from_key") or ""),
            "created_at": raw.get("created_at"),
            "origin_mode": raw.get("origin_mode") if raw.get("origin_mode") in {"warmup", "live"} else "live",
            "top1": top1,
            "score1": float(raw.get("score1", 0.0) or 0.0),
            "score2": float(raw.get("score2", 0.0) or 0.0),
            "margin": float(raw.get("margin", 0.0) or 0.0),
            "confidence": float(raw.get("confidence", 0.0) or 0.0),
            "threshold": None,
            "support": int(raw.get("support", 0) or 0),
            "accepted": bool(raw.get("accepted", False)),
        }
        try:
            clean["threshold"] = float(raw["threshold"]) if raw.get("threshold") is not None else None
        except Exception:
            clean["threshold"] = None
        return clean

    @staticmethod
    def _sanitize_h5_sessions(raw):
        out = []
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            try:
                top1 = int(row.get("top1"))
                age = int(row.get("age", 0) or 0)
                support = int(row.get("support", 0) or 0)
                hit_ages = sorted({int(x) for x in (row.get("hit_ages", row.get("top1_hit_ages", [])) or []) if 1 <= int(x) <= 5})
            except Exception:
                continue
            if not (1 <= top1 <= 90 and 0 <= age < 5 and 0 <= support <= 4):
                continue
            out.append({
                "signal_from_key": str(row.get("signal_from_key") or ""),
                "created_at": row.get("created_at"),
                "origin_mode": row.get("origin_mode") if row.get("origin_mode") in {"warmup", "live"} else "live",
                "top1": top1,
                "support": support,
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "threshold": row.get("threshold"),
                "confidence_ratio": row.get("confidence_ratio"),
                "age": age,
                "hit_ages": hit_ages,
            })
        return out[-1000:]

    @staticmethod
    def _sanitize_h5_records(raw):
        out = []
        seen = set()
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            try:
                top1 = int(row.get("top1"))
                support = int(row.get("support", 0) or 0)
                hit_ages = sorted({int(x) for x in (row.get("hit_ages", row.get("top1_hit_ages", [])) or []) if 1 <= int(x) <= 5})
            except Exception:
                continue
            if not (1 <= top1 <= 90 and 0 <= support <= 4):
                continue
            key = (str(row.get("signal_from_key") or ""), row.get("origin_mode", "live"))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "signal_from_key": str(row.get("signal_from_key") or ""),
                "completed_at": str(row.get("completed_at", row.get("result_key", "")) or ""),
                "origin_mode": row.get("origin_mode") if row.get("origin_mode") in {"warmup", "live"} else "live",
                "top1": top1,
                "support": support,
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "threshold": row.get("threshold"),
                "confidence_ratio": row.get("confidence_ratio"),
                "hit_ages": hit_ages,
                "hits5": len(hit_ages),
            })
        return out[-ENGINE_H5_RECORD_MAX:]

    def _migrate_h5_from_legacy_horizon(self, d):
        # Vecchi record horizon: a H5 contengono gia' tutti i top1_hit_ages della sessione.
        if self.engine_h5_records_warmup or self.engine_h5_records_live:
            return
        for origin, field in (("warmup", "engine_horizon_records_warmup"), ("live", "engine_horizon_records_live")):
            rows = []
            for r in list(d.get(field, []) or []):
                if not isinstance(r, dict):
                    continue
                try:
                    if int(r.get("horizon", 0) or 0) != 5:
                        continue
                except Exception:
                    continue
                rows.append({
                    "signal_from_key": r.get("signal_from_key"),
                    "completed_at": r.get("result_key"),
                    "origin_mode": origin,
                    "top1": r.get("top1"),
                    "support": r.get("support", 0),
                    "confidence": r.get("confidence", 0.0),
                    "threshold": r.get("threshold"),
                    "confidence_ratio": r.get("confidence_ratio"),
                    "hit_ages": r.get("top1_hit_ages", []),
                })
            clean = self._sanitize_h5_records(rows)
            if origin == "warmup":
                self.engine_h5_records_warmup = clean
            else:
                self.engine_h5_records_live = clean

        # Migra anche eventuali sessioni ancora aperte.
        if not self.engine_h5_sessions:
            self.engine_h5_sessions = self._sanitize_h5_sessions(d.get("engine_horizon_sessions", []))


    @staticmethod
    def _sanitize_play_sessions(raw):
        out = []
        seen = set()
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            try:
                top1 = int(row.get("top1"))
                age = int(row.get("age", 0) or 0)
                support = int(row.get("support", 0) or 0)
                activation_age = row.get("activation_age")
                activation_age = int(activation_age) if activation_age is not None else None
                hit_ages = sorted({int(x) for x in (row.get("hit_ages", []) or []) if 1 <= int(x) <= 5})
                play_ages = sorted({int(x) for x in (row.get("play_ages", []) or []) if 1 <= int(x) <= 5})
            except Exception:
                continue
            if not (1 <= top1 <= 90 and 0 <= age < 5 and 0 <= support <= 4):
                continue
            if activation_age is not None and activation_age not in (1, 2, 3):
                continue
            key = (str(row.get("signal_from_key") or ""), row.get("origin_mode", "live"))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "signal_from_key": key[0],
                "created_at": row.get("created_at"),
                "origin_mode": row.get("origin_mode") if row.get("origin_mode") in {"warmup", "live"} else "live",
                "top1": top1,
                "support": support,
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "threshold": row.get("threshold"),
                "confidence_ratio": row.get("confidence_ratio"),
                "age": age,
                "hit_ages": hit_ages,
                "activation_age": activation_age,
                "play_ages": play_ages,
            })
        return out[-1000:]

    @staticmethod
    def _sanitize_play_records(raw):
        out = []
        seen = set()
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            try:
                top1 = int(row.get("top1"))
                support = int(row.get("support", 0) or 0)
                activation_age = row.get("activation_age")
                activation_age = int(activation_age) if activation_age is not None else None
                hit_age = row.get("hit_age")
                hit_age = int(hit_age) if hit_age is not None else None
                play_ages = [int(x) for x in (row.get("play_ages", []) or []) if 1 <= int(x) <= 5]
                result = str(row.get("result") or "").lower()
            except Exception:
                continue
            if not (1 <= top1 <= 90 and 0 <= support <= 4):
                continue
            if result not in {"hit", "stop", "no_play"}:
                continue
            if activation_age is not None and activation_age not in (1, 2, 3):
                continue
            if hit_age is not None and hit_age not in (2, 3, 4, 5):
                continue
            key = (str(row.get("signal_from_key") or ""), row.get("origin_mode", "live"))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "signal_from_key": key[0],
                "completed_at": str(row.get("completed_at") or ""),
                "origin_mode": row.get("origin_mode") if row.get("origin_mode") in {"warmup", "live"} else "live",
                "top1": top1,
                "support": support,
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "threshold": row.get("threshold"),
                "confidence_ratio": row.get("confidence_ratio"),
                "activation_age": activation_age,
                "hit_age": hit_age,
                "play_ages": play_ages,
                "bets": int(row.get("bets", len(play_ages)) or 0),
                "result": result,
            })
        return out[-ENGINE_PLAY_RECORD_MAX:]

    def _play_bank(self, mode):
        return self.engine_play_records_warmup if mode == "warmup" else self.engine_play_records_live

    @staticmethod
    def _derive_play_record_from_h5(row):
        hits = sorted({int(x) for x in (row.get("hit_ages", []) or []) if 1 <= int(x) <= 5})
        activation_age = next((a for a in hits if a <= 3), None)
        if activation_age is None:
            result = "no_play"
            hit_age = None
            play_ages = []
        else:
            hit_age = next((a for a in hits if a > activation_age), None)
            if hit_age is not None:
                result = "hit"
                play_ages = list(range(activation_age + 1, hit_age + 1))
            else:
                result = "stop"
                play_ages = list(range(activation_age + 1, 6))
        return {
            "signal_from_key": str(row.get("signal_from_key") or ""),
            "completed_at": str(row.get("completed_at") or ""),
            "origin_mode": row.get("origin_mode") if row.get("origin_mode") in {"warmup", "live"} else "live",
            "top1": int(row.get("top1")),
            "support": int(row.get("support", 0) or 0),
            "confidence": float(row.get("confidence", 0.0) or 0.0),
            "threshold": row.get("threshold"),
            "confidence_ratio": row.get("confidence_ratio"),
            "activation_age": activation_age,
            "hit_age": hit_age,
            "play_ages": play_ages,
            "bets": len(play_ages),
            "result": result,
        }

    def _migrate_play_from_h5(self):
        """Ricostruisce/integra la nuova strategia dai record H5 gia' salvati, senza perdere storico."""
        # Idempotente: aggiunge solo i segnali H5 che ancora non esistono nel registro PLAY.
        for origin, h5_bank, play_bank in (
            ("warmup", self.engine_h5_records_warmup, self.engine_play_records_warmup),
            ("live", self.engine_h5_records_live, self.engine_play_records_live),
        ):
            existing = {(str(r.get("signal_from_key") or ""), origin) for r in play_bank}
            for h5 in h5_bank:
                key = (str(h5.get("signal_from_key") or ""), origin)
                if key not in existing:
                    play_bank.append(self._derive_play_record_from_h5(h5))
                    existing.add(key)
        self.engine_play_records_warmup = self._sanitize_play_records(self.engine_play_records_warmup)
        self.engine_play_records_live = self._sanitize_play_records(self.engine_play_records_live)

        known = {
            (str(r.get("signal_from_key") or ""), r.get("origin_mode", "live"))
            for r in (self.engine_play_records_warmup + self.engine_play_records_live)
        }
        known.update({
            (str(r.get("signal_from_key") or ""), r.get("origin_mode", "live"))
            for r in self.engine_play_sessions
        })
        for h5 in self.engine_h5_sessions:
            origin = h5.get("origin_mode") if h5.get("origin_mode") in {"warmup", "live"} else "live"
            key = (str(h5.get("signal_from_key") or ""), origin)
            if key in known:
                continue
            age = int(h5.get("age", 0) or 0)
            hits = sorted({int(x) for x in (h5.get("hit_ages", []) or []) if 1 <= int(x) <= 5})
            activation_age = next((a for a in hits if a <= 3), None)
            second_hit = next((a for a in hits if activation_age is not None and a > activation_age), None)
            base = {
                "signal_from_key": key[0], "created_at": h5.get("created_at"), "origin_mode": origin,
                "top1": int(h5.get("top1")), "support": int(h5.get("support", 0) or 0),
                "confidence": float(h5.get("confidence", 0.0) or 0.0), "threshold": h5.get("threshold"),
                "confidence_ratio": h5.get("confidence_ratio"),
            }
            if second_hit is not None:
                rec = {**base, "completed_at": "migrated", "activation_age": activation_age,
                       "hit_age": second_hit, "play_ages": list(range(activation_age + 1, second_hit + 1)),
                       "bets": second_hit - activation_age, "result": "hit"}
                self._play_bank(origin).append(rec)
            elif activation_age is None and age >= 3:
                rec = {**base, "completed_at": "migrated", "activation_age": None,
                       "hit_age": None, "play_ages": [], "bets": 0, "result": "no_play"}
                self._play_bank(origin).append(rec)
            else:
                play_ages = list(range(activation_age + 1, age + 1)) if activation_age is not None and age > activation_age else []
                self.engine_play_sessions.append({**base, "age": age, "hit_ages": hits,
                                                  "activation_age": activation_age, "play_ages": play_ages})
            known.add(key)
        self.engine_play_records_warmup = self._sanitize_play_records(self.engine_play_records_warmup)
        self.engine_play_records_live = self._sanitize_play_records(self.engine_play_records_live)
        self.engine_play_sessions = self._sanitize_play_sessions(self.engine_play_sessions)

    def _start_play_session(self, pending):
        if not pending or not pending.get("accepted"):
            return False
        key = str(pending.get("signal_from_key") or "")
        origin = pending.get("origin_mode") if pending.get("origin_mode") in {"warmup", "live"} else "live"
        if any(str(x.get("signal_from_key") or "") == key and x.get("origin_mode") == origin for x in self.engine_play_sessions):
            return False
        if any(str(x.get("signal_from_key") or "") == key and x.get("origin_mode") == origin
               for x in (self.engine_play_records_warmup + self.engine_play_records_live)):
            return False
        conf = float(pending.get("confidence", 0.0) or 0.0)
        thr = pending.get("threshold")
        try:
            thr_f = float(thr) if thr is not None else None
        except Exception:
            thr_f = None
        ratio = (conf / thr_f) if thr_f and thr_f > 0 else None
        self.engine_play_sessions.append({
            "signal_from_key": key, "created_at": pending.get("created_at"), "origin_mode": origin,
            "top1": int(pending["top1"]), "support": int(pending.get("support", 0) or 0),
            "confidence": conf, "threshold": thr_f, "confidence_ratio": ratio,
            "age": 0, "hit_ages": [], "activation_age": None, "play_ages": [],
        })
        self.engine_play_sessions = self.engine_play_sessions[-1000:]
        return True

    async def settle_play_sessions(self, app, day, e, nums, mode="live", notify=True):
        if not self.engine_play_sessions:
            return []
        actual = set(map(int, nums))
        result_key = draw_key(day, e)
        kept, completed = [], []
        for sess in self.engine_play_sessions:
            origin = sess.get("origin_mode") if sess.get("origin_mode") in {"warmup", "live"} else mode
            age = int(sess.get("age", 0) or 0) + 1
            sess["age"] = age
            hit_now = int(sess["top1"]) in actual
            if hit_now and age not in sess["hit_ages"]:
                sess["hit_ages"].append(age)

            activation_age = sess.get("activation_age")
            # Prima uscita entro H1-H3 = sola CONFERMA. Non e' una giocata.
            if activation_age is None:
                if hit_now and age <= 3:
                    activation_age = age
                    sess["activation_age"] = age
                    if notify and mode == "live" and origin == "live" and ENGINE_NOTIFY_PLAY_CONFIRM:
                        max_bets = 5 - age
                        await self.tg(
                            app,
                            "✅ ENGINE PLAY SHADOW — CONFERMA\n\n"
                            f"Segnale: {sess.get('signal_from_key','-')}\n"
                            f"TOP1 #{sess['top1']} uscito a H{age}.\n"
                            "Questa uscita e' SOLO conferma: nessuna giocata conteggiata.\n\n"
                            f"▶️ DALLA PROSSIMA: PLAY #{sess['top1']}\n"
                            f"Fino a H5, massimo {max_bets} colpi, STOP alla seconda uscita.\n"
                            "⚠️ PLAY SHADOW: nessuna puntata automatica."
                        )
                elif age >= 3:
                    rec = {
                        "signal_from_key": sess.get("signal_from_key"), "completed_at": result_key,
                        "origin_mode": origin, "top1": int(sess["top1"]), "support": int(sess.get("support",0) or 0),
                        "confidence": sess.get("confidence"), "threshold": sess.get("threshold"),
                        "confidence_ratio": sess.get("confidence_ratio"), "activation_age": None,
                        "hit_age": None, "play_ages": [], "bets": 0, "result": "no_play",
                    }
                    bank = self._play_bank(origin); bank.append(rec); del bank[:-ENGINE_PLAY_RECORD_MAX]
                    completed.append(rec)
                    continue

            # Se la conferma era gia' avvenuta in un colpo precedente, questo draw e' una PLAY.
            activation_age = sess.get("activation_age")
            if activation_age is not None and age > int(activation_age):
                if age not in sess["play_ages"]:
                    sess["play_ages"].append(age)
                if hit_now:
                    rec = {
                        "signal_from_key": sess.get("signal_from_key"), "completed_at": result_key,
                        "origin_mode": origin, "top1": int(sess["top1"]), "support": int(sess.get("support",0) or 0),
                        "confidence": sess.get("confidence"), "threshold": sess.get("threshold"),
                        "confidence_ratio": sess.get("confidence_ratio"), "activation_age": int(activation_age),
                        "hit_age": age, "play_ages": list(sess["play_ages"]), "bets": len(sess["play_ages"]),
                        "result": "hit",
                    }
                    bank = self._play_bank(origin); bank.append(rec); del bank[:-ENGINE_PLAY_RECORD_MAX]
                    completed.append(rec)
                    if notify and mode == "live" and origin == "live" and ENGINE_NOTIFY_PLAY_RESULT:
                        await self.tg(
                            app,
                            "🎯 ENGINE PLAY SHADOW — HIT / STOP\n\n"
                            f"TOP1 #{sess['top1']} | conferma H{activation_age}\n"
                            f"Seconda uscita a H{age} | colpo giocato {len(sess['play_ages'])}\n"
                            f"PLAY: {', '.join('H'+str(x) for x in sess['play_ages'])}\n\n"
                            "✅ Obiettivo seconda uscita centrato. Sessione chiusa."
                        )
                    continue
                if age >= 5:
                    rec = {
                        "signal_from_key": sess.get("signal_from_key"), "completed_at": result_key,
                        "origin_mode": origin, "top1": int(sess["top1"]), "support": int(sess.get("support",0) or 0),
                        "confidence": sess.get("confidence"), "threshold": sess.get("threshold"),
                        "confidence_ratio": sess.get("confidence_ratio"), "activation_age": int(activation_age),
                        "hit_age": None, "play_ages": list(sess["play_ages"]), "bets": len(sess["play_ages"]),
                        "result": "stop",
                    }
                    bank = self._play_bank(origin); bank.append(rec); del bank[:-ENGINE_PLAY_RECORD_MAX]
                    completed.append(rec)
                    if notify and mode == "live" and origin == "live" and ENGINE_NOTIFY_PLAY_RESULT:
                        await self.tg(
                            app,
                            "⛔ ENGINE PLAY SHADOW — STOP H5\n\n"
                            f"TOP1 #{sess['top1']} | conferma H{activation_age}\n"
                            f"PLAY senza seconda uscita: {', '.join('H'+str(x) for x in sess['play_ages'])}\n"
                            f"Colpi giocati: {len(sess['play_ages'])}\n\n"
                            "Sessione chiusa a H5."
                        )
                    continue

            kept.append(sess)
        self.engine_play_sessions = kept
        return completed

    # ========================================================
    # AMBO 2xHOT5 H1-H3 NO-LOCK — simulazione prospettica separata dall'ENGINE
    # ========================================================
    @staticmethod
    def _ambo_validate_session(row):
        if not isinstance(row, dict):
            return None
        try:
            top = int(row['top1'])
            age = int(row.get('age', 0))
            phase = str(row.get('phase', ''))
            conf_age = row.get('confirmation_age')
            conf_age = int(conf_age) if conf_age is not None else None

            raw_partners = row.get('partners')
            if raw_partners is None:
                raw_partners = []
            partners = [int(x) for x in raw_partners]
            if len(set(partners)) != len(partners):
                return None
            if any(n < 1 or n > 90 or n == top for n in partners):
                return None

            raw_counts = row.get('partner_hot5_counts') or []
            counts = [int(x) for x in raw_counts]
            while len(counts) < len(partners):
                counts.append(0)
            counts = counts[:len(partners)]

            if not (1 <= top <= 90 and 0 <= age <= 5 and
                    phase in {'await_h1','await_h2','await_h3','needs_partners','play'}):
                return None
            if phase == 'play' and (len(partners) != 2 or conf_age not in (1,2,3)):
                return None

            return {
                'signal_from_key': str(row.get('signal_from_key', '')),
                'top1': top,
                'support': int(row.get('support', 0)),
                'age': age,
                'phase': phase,
                'partners': partners,
                'confirmation_age': conf_age,
                'confirmation_draw_key': row.get('confirmation_draw_key'),
                'partner_hot5_counts': counts,
                'bets': int(row.get('bets', 0)),
                'wins': int(row.get('wins', 0)),
                'created_at': row.get('created_at'),
                'strategy': 'two_hot5_confirm_h1_h3_nolock',
            }
        except (ValueError, TypeError, KeyError):
            return None

    def _ambo_load_fields(self, data):
        saved_ver = int(data.get('ambo_sim_diag_version', 0) or 0)
        self.ambo_h2_legacy = dict(data.get('ambo_h2_legacy', {}) or {})
        self.ambo_hot5_single_legacy = dict(data.get('ambo_hot5_single_legacy', {}) or {})

        # v1 = vecchio AMBO H2; v2 = HOT5 singolo con lock 5.
        # Entrambi vengono conservati come archivi ma NON sommati alla nuova strategia.
        if saved_ver != AMBO_SIM_DIAG_VERSION:
            if saved_ver == 1 and not self.ambo_h2_legacy:
                self.ambo_h2_legacy = {
                    'strategy': 'ambo_h2_ranking_legacy',
                    'diag_version': 1,
                    'archived_at': now_txt(),
                    'draw_index': int(data.get('ambo_sim_draw_index', 0) or 0),
                    'skipped_overlap': int(data.get('ambo_sim_skipped_overlap', 0) or 0),
                    'sessions': list(data.get('ambo_sim_sessions', []) or []),
                    'records_live': list(data.get('ambo_sim_records_live', []) or []),
                    'bets_live': list(data.get('ambo_sim_bets_live', []) or []),
                    'account': dict(data.get('ambo_sim_account', {}) or {}),
                }
            elif saved_ver == 2 and not self.ambo_hot5_single_legacy:
                self.ambo_hot5_single_legacy = {
                    'strategy': 'hot5_single_lock5_legacy',
                    'diag_version': 2,
                    'archived_at': now_txt(),
                    'draw_index': int(data.get('ambo_sim_draw_index', 0) or 0),
                    'skipped_overlap': int(data.get('ambo_sim_skipped_overlap', 0) or 0),
                    'sessions': list(data.get('ambo_sim_sessions', []) or []),
                    'records_live': list(data.get('ambo_sim_records_live', []) or []),
                    'bets_live': list(data.get('ambo_sim_bets_live', []) or []),
                    'account': dict(data.get('ambo_sim_account', {}) or {}),
                }

            self.ambo_sim_draw_index = 0
            self.ambo_sim_last_candidate_index = -100000
            self.ambo_sim_skipped_overlap = 0
            self.ambo_sim_sessions = []
            self.ambo_sim_records_live = []
            self.ambo_sim_bets_live = []
            self.ambo_sim_account = {'bets': 0, 'wins': 0, 'cost_cents': 0, 'gross_cents': 0}
            return

        self.ambo_sim_draw_index = max(0, int(data.get('ambo_sim_draw_index', 0) or 0))
        self.ambo_sim_last_candidate_index = int(data.get('ambo_sim_last_candidate_index', -100000) or -100000)
        self.ambo_sim_skipped_overlap = max(0, int(data.get('ambo_sim_skipped_overlap', 0) or 0))
        self.ambo_sim_sessions = [x for row in data.get('ambo_sim_sessions', [])
                                  if (x := self._ambo_validate_session(row)) is not None][-100:]
        self.ambo_sim_records_live = list(data.get('ambo_sim_records_live', []) or [])[-AMBO_SIM_RECORD_MAX:]
        self.ambo_sim_bets_live = list(data.get('ambo_sim_bets_live', []) or [])[-AMBO_SIM_BET_LOG_MAX:]
        a = data.get('ambo_sim_account', {})
        self.ambo_sim_account = {
            name: max(0, int(a.get(name, 0) or 0))
            for name in ('bets','wins','cost_cents','gross_cents')
        }

    def _ambo_start_candidate(self, pending):
        """Ogni HIGH CONFIDENCE live apre una sessione indipendente: nessun lock."""
        if not AMBO_SIM_ENABLED or not pending or not pending.get('accepted'):
            return False
        signal_key = str(pending.get('signal_from_key') or '')
        if not signal_key:
            return False
        # Protezione solo contro la duplicazione dello STESSO segnale dopo un retry.
        if any(str(s.get('signal_from_key')) == signal_key for s in self.ambo_sim_sessions):
            return False
        if any(str(r.get('signal_from_key')) == signal_key for r in self.ambo_sim_records_live[-100:]):
            return False

        self.ambo_sim_last_candidate_index = self.ambo_sim_draw_index
        self.ambo_sim_sessions.append({
            'signal_from_key': signal_key,
            'created_at': pending.get('created_at'),
            'top1': int(pending['top1']),
            'support': int(pending.get('support', 0)),
            'age': 0,
            'phase': 'await_h1',
            'partners': [],
            'confirmation_age': None,
            'confirmation_draw_key': None,
            'partner_hot5_counts': [],
            'bets': 0,
            'wins': 0,
            'strategy': 'two_hot5_confirm_h1_h3_nolock',
        })
        return True

    def _ambo_close(self, session, result, current_key, reason=''):
        record = {
            **dict(session),
            'result': result,
            'completed_at': current_key,
            'reason': reason,
            'stake_cents_per_ambo': AMBO_SIM_STAKE_CENTS,
            'payout_multiplier': AMBO_SIM_PAYOUT_MULTIPLIER,
            'strategy': 'two_hot5_confirm_h1_h3_nolock',
        }
        self.ambo_sim_records_live.append(record)
        self.ambo_sim_records_live = self.ambo_sim_records_live[-AMBO_SIM_RECORD_MAX:]
        self.ambo_sim_sessions = [s for s in self.ambo_sim_sessions if s is not session]
        return record

    def _ambo_balance(self):
        a = self.ambo_sim_account
        return int(a['gross_cents']) - int(a['cost_cents'])

    async def _ambo_notice(self, app, message, notify=True):
        if notify and AMBO_SIM_NOTIFY:
            await self.tg(app, message + '\n\n⚠️ SIMULAZIONE: nessuna puntata effettuata automaticamente.')

    def _ambo_hot5_partners(self, top, confirmation_nums, limit=2):
        """I due co-usciti piu' frequenti nelle ultime 5, senza usare futuro."""
        candidates = sorted(set(map(int, confirmation_nums)) - {int(top)})
        if len(candidates) < limit:
            return []
        rows = self.engine_history[-5:]
        if not rows:
            return []

        scored = []
        for n in candidates:
            count = sum(1 for row in rows if n in set(row.get('nums', [])))
            recency = sum(i + 1 for i, row in enumerate(rows) if n in set(row.get('nums', [])))
            scored.append((count, recency, -n, n))
        scored.sort(reverse=True)
        out = []
        for count, recency, _, partner in scored[:limit]:
            out.append({
                'partner': int(partner),
                'count5': int(count),
                'recency_score': int(recency),
                'window': len(rows),
            })
        return out

    async def _ambo_settle_current(self, app, current_key, nums, notify=True):
        """Valuta TUTTE le sessioni attive prima di aggiungere il draw allo storico."""
        if not self.ambo_sim_sessions:
            return
        actual = set(map(int, nums))

        for session in list(self.ambo_sim_sessions):
            if session not in self.ambo_sim_sessions:
                continue
            age = int(session['age']) + 1
            session['age'] = age
            top = int(session['top1'])
            phase = session['phase']

            # Prima uscita TOP1 entro H1-H3 = conferma, non giocata.
            if phase in {'await_h1', 'await_h2', 'await_h3'} and age in (1, 2, 3):
                if top in actual:
                    session['phase'] = 'needs_partners'
                    session['confirmation_age'] = age
                    session['confirmation_draw_key'] = current_key
                elif age == 1:
                    session['phase'] = 'await_h2'
                elif age == 2:
                    session['phase'] = 'await_h3'
                else:
                    self._ambo_close(session, 'no_play', current_key, 'nessuna_prima_uscita_entro_h3')
                continue

            if phase == 'needs_partners':
                self._ambo_close(session, 'interrupted', current_key, 'partners_non_finalizzati')
                continue

            if phase != 'play' or age not in (2, 3, 4, 5):
                self._ambo_close(session, 'interrupted', current_key, 'stato_temporale_incoerente')
                continue

            partners = [int(x) for x in session.get('partners', [])]
            if len(partners) != 2:
                self._ambo_close(session, 'interrupted', current_key, 'numero_partner_non_valido')
                continue

            top_hit = top in actual
            winning_partners = [p for p in partners if top_hit and p in actual]
            hits_this_draw = len(winning_partners)
            stake_each = AMBO_SIM_STAKE_CENTS
            total_cost = stake_each * len(partners)
            prize_each = int(round(stake_each * AMBO_SIM_PAYOUT_MULTIPLIER))
            total_prize = prize_each * hits_this_draw

            a = self.ambo_sim_account
            a['bets'] += len(partners)
            a['cost_cents'] += total_cost
            a['gross_cents'] += total_prize
            a['wins'] += hits_this_draw
            session['bets'] += len(partners)
            session['wins'] += hits_this_draw

            counts = list(session.get('partner_hot5_counts') or [0, 0])
            for idx, partner in enumerate(partners):
                hit = partner in winning_partners
                self.ambo_sim_bets_live.append({
                    'strategy': 'two_hot5_confirm_h1_h3_nolock',
                    'signal_from_key': session['signal_from_key'],
                    'draw_key': current_key,
                    'confirmation_age': session.get('confirmation_age'),
                    'age': age,
                    'top1': top,
                    'partner': partner,
                    'partner_rank': idx + 1,
                    'partner_hot5_count': counts[idx] if idx < len(counts) else None,
                    'hit': bool(hit),
                    'top1_hit': bool(top_hit),
                    'cost_cents': stake_each,
                    'gross_cents': prize_each if hit else 0,
                    'net_cents': (prize_each if hit else 0) - stake_each,
                })
            self.ambo_sim_bets_live = self.ambo_sim_bets_live[-AMBO_SIM_BET_LOG_MAX:]

            if hits_this_draw:
                self._ambo_close(session, 'hit', current_key,
                                 'due_ambi_hot5' if hits_this_draw == 2 else 'un_ambo_hot5')
                label = ('✅✅ DOPPIO AMBO HOT5 — 2 HIT / STOP' if hits_this_draw == 2
                         else '✅ AMBO HOT5 CENTRATO — 1 HIT / STOP')
            elif top_hit:
                self._ambo_close(session, 'stop', current_key, 'secondo_top1_senza_hot5')
                label = '⛔ STOP: TOP1 uscito senza i due accompagnatori HOT5'
            elif age >= 5:
                self._ambo_close(session, 'stop', current_key, 'fine_h5')
                label = '⛔ STOP H5: nessun ambo'
            else:
                label = '❌ NESSUN AMBO — sessione ancora aperta'

            pair_txt = ' | '.join(f'{top}-{p}' for p in partners)
            count_txt = ' / '.join(f'{partners[i]}={counts[i] if i < len(counts) else 0}/5'
                                   for i in range(len(partners)))
            still_open = session in self.ambo_sim_sessions
            await self._ambo_notice(
                app,
                f'🎮 AMBO 2xHOT5 NO-LOCK — ESITO H{age}\n'
                f'Segnale {session["signal_from_key"]} | estrazione {current_key}\n'
                f'Conferma TOP1 a H{session.get("confirmation_age")} | AMBI {pair_txt}\n'
                f'HOT5: {count_txt}\n'
                f'Puntata virtuale: {sim_euro(stake_each)} x 2 = {sim_euro(total_cost)}\n'
                f'{label}\n'
                f'Ambi centrati in questo colpo: {hits_this_draw}/2\n'
                f'Premio di questo colpo: {sim_euro(total_prize)}\n'
                f'Bilancio di questo colpo: {sim_euro(total_prize-total_cost)}\n'
                f'SALDO TOTALE VIRTUALE 2xHOT5: {sim_euro(self._ambo_balance())}' +
                (f'\n\n▶️ PROSSIMA H{age+1}: ripeti ENTRAMBI gli ambi {pair_txt} '
                 f'| totale {sim_euro(total_cost)} simulati.' if still_open else
                 '\n\n🏁 Sessione chiusa, non ripetere questi ambi.'),
                notify=notify
            )

            # Un catch-up silenzioso non deve inventare una giocata notificata per il futuro.
            if still_open and not notify:
                self._ambo_close(session, 'interrupted', current_key, 'prossimo_colpo_non_notificato')

    async def _ambo_finalize_confirmation(self, app, current_key, nums, notify=True):
        """Dopo append_history finalizza tutte le conferme avvenute in questo draw."""
        if not self.ambo_sim_sessions:
            return

        for session in list(self.ambo_sim_sessions):
            if session not in self.ambo_sim_sessions or session.get('phase') != 'needs_partners':
                continue
            if str(session.get('confirmation_draw_key')) != str(current_key):
                self._ambo_close(session, 'interrupted', current_key, 'conferma_non_finalizzata_nel_draw_corretto')
                continue
            if not notify:
                self._ambo_close(session, 'no_play', current_key, 'conferma_recuperata_senza_notifica')
                continue

            top = int(session['top1'])
            picks = self._ambo_hot5_partners(top, nums, limit=2)
            if len(picks) != 2:
                self._ambo_close(session, 'no_play', current_key, 'due_hot5_non_disponibili')
                continue

            session['partners'] = [int(x['partner']) for x in picks]
            session['partner_hot5_counts'] = [int(x['count5']) for x in picks]
            session['phase'] = 'play'
            conf_age = int(session['confirmation_age'])
            first_play_age = conf_age + 1
            stake_each = AMBO_SIM_STAKE_CENTS
            total_cost = stake_each * 2
            p1, p2 = session['partners']
            c1, c2 = session['partner_hot5_counts']

            await self._ambo_notice(
                app,
                f'🎯 AMBO 2xHOT5 NO-LOCK — SEGNALE DI GIOCATA\n'
                f'HC da {session["signal_from_key"]} | conferma {current_key}\n'
                f'TOP1 #{top}: PRIMA uscita a H{conf_age} (solo conferma, non giocata).\n'
                f'Due accompagnatori HOT5 co-usciti: #{p1} ({c1}/5) e #{p2} ({c2}/5).\n\n'
                f'▶️ PROSSIMA ESTRAZIONE H{first_play_age}:\n'
                f'• AMBO {top}-{p1} — {sim_euro(stake_each)} virtuale\n'
                f'• AMBO {top}-{p2} — {sim_euro(stake_each)} virtuale\n'
                f'TOTALE COLPO: {sim_euro(total_cost)}\n'
                f'Premio lordo simulato per OGNI ambo centrato: '
                f'{sim_euro(round(stake_each*AMBO_SIM_PAYOUT_MULTIPLIER))}.\n'
                'Se TOP1 esce con uno o entrambi: contabilizza 1 o 2 HIT e STOP.\n'
                'Se TOP1 esce senza entrambi: STOP. Se TOP1 manca: ripeti i due ambi fino a H5.',
                notify=notify
            )

    def ambo_sim_text(self):
        a = self.ambo_sim_account
        n = int(a['bets'])
        wins = int(a['wins'])
        net = self._ambo_balance()
        completed = self.ambo_sim_records_live
        active = self.ambo_sim_sessions
        hit_sessions = sum(r.get('result') == 'hit' for r in completed)
        no_play = sum(r.get('result') == 'no_play' for r in completed)
        stops = sum(r.get('result') == 'stop' for r in completed)
        double_sessions = sum(int(r.get('wins', 0) or 0) >= 2 for r in completed if r.get('result') == 'hit')

        parts = [
            '🎮 AMBO 2xHOT5 H1-H3 — NO LOCK / SIMULATORE',
            'Regola: OGNI HC apre la propria sessione, anche se altre sono attive.',
            'Prima uscita TOP1 entro H1/H2/H3 = CONFERMA non giocata.',
            'Accompagnatori = i DUE piu frequenti ultime 5 fra i co-usciti della conferma.',
            'Dalla successiva: 2 ambi fino alla seconda uscita TOP1 o massimo H5.',
            'Secondo TOP1: 0/1/2 ambi possibili e poi STOP.',
            f'💶 {sim_euro(AMBO_SIM_STAKE_CENTS)} per ambo = {sim_euro(AMBO_SIM_STAKE_CENTS*2)} per sessione/colpo | '
            f'premio lordo {AMBO_SIM_PAYOUT_MULTIPLIER:g}x per ogni ambo.',
            '',
            '📊 SOLO DATI PROSPETTICI 2xHOT5 NO-LOCK',
            f'• sessioni chiuse: {len(completed)} | HIT sessione={hit_sessions} | STOP={stops} | NO PLAY={no_play}',
            f'• sessioni con DOPPIO AMBO nello stesso stop: {double_sessions}',
            f'• sessioni attive adesso: {len(active)} | lock 5: DISATTIVATO',
            f'• puntate AMBO {n} | AMBI HIT {wins} | HIT/puntata {safe_pct(wins,n):.2f}%',
            f'• COSTO {sim_euro(a["cost_cents"])} | LORDO {sim_euro(a["gross_cents"])}',
            f'• SALDO NETTO {sim_euro(net)} | ROI {safe_pct(net,a["cost_cents"]):.2f}%',
            f'• pareggio teorico: {100.0/AMBO_SIM_PAYOUT_MULTIPLIER:.2f}% di ambi per puntata.',
        ]

        parts += ['', '⏱ PER CONFERMA']
        for age in (1, 2, 3):
            rows = [r for r in completed if r.get('confirmation_age') == age and r.get('result') in {'hit','stop'}]
            hs = sum(r.get('result') == 'hit' for r in rows)
            bets = sum(int(r.get('bets', 0) or 0) for r in rows)
            ambi = sum(int(r.get('wins', 0) or 0) for r in rows)
            parts.append(
                f'• H{age}: sessioni {len(rows)} | sessioni HIT {hs}/{len(rows)} '
                f'({safe_pct(hs,len(rows)):.2f}%) | puntate ambo {bets} | ambi {ambi}'
            )

        parts += ['', '📍 SESSIONI ATTIVE']
        if not active:
            parts.append('• nessuna: attendi un nuovo avviso HIGH CONFIDENCE/AMBO.')
        else:
            for s in active[-10:]:
                if s['phase'] == 'play':
                    partners = s.get('partners', [])
                    counts = s.get('partner_hot5_counts', [])
                    if len(partners) == 2:
                        parts.append(
                            f'• {s["signal_from_key"]}: {s["top1"]}-{partners[0]} + {s["top1"]}-{partners[1]} | '
                            f'conf H{s.get("confirmation_age")} | HOT5 {counts} | prossima H{s["age"]+1}'
                        )
                else:
                    parts.append(
                        f'• {s["signal_from_key"]}: TOP1 {s["top1"]} | {s["phase"]} | '
                        f'prossimo H{s["age"]+1}; nessuna puntata ora.'
                    )
            if len(active) > 10:
                parts.append(f'• ... altre {len(active)-10} sessioni attive')

        parts.extend(['', '🧾 ULTIME PUNTATE AMBO'])
        if not self.ambo_sim_bets_live:
            parts.append('• nessuna puntata 2xHOT5 ancora registrata')
        else:
            for bet in self.ambo_sim_bets_live[-12:]:
                parts.append(
                    f'• {bet.get("draw_key","-")} H{bet.get("age","-")} '
                    f'{bet.get("top1","-")}-{bet.get("partner","-")} '
                    f'#{bet.get("partner_rank","-")} {"✅ HIT" if bet.get("hit") else "❌ MISS"} '
                    f'| costo {sim_euro(bet.get("cost_cents",0))} | premio {sim_euro(bet.get("gross_cents",0))}'
                )

        if self.ambo_hot5_single_legacy:
            old_a = dict(self.ambo_hot5_single_legacy.get('account', {}) or {})
            old_bets = int(old_a.get('bets', 0) or 0)
            old_wins = int(old_a.get('wins', 0) or 0)
            old_cost = int(old_a.get('cost_cents', 0) or 0)
            old_gross = int(old_a.get('gross_cents', 0) or 0)
            parts += [
                '', '📦 ARCHIVIO HOT5 SINGOLO + LOCK5 (NON SOMMATO)',
                f'• puntate={old_bets} | ambi={old_wins} | costo={sim_euro(old_cost)} | '
                f'lordo={sim_euro(old_gross)} | netto={sim_euro(old_gross-old_cost)}'
            ]

        if self.ambo_h2_legacy:
            old_a = dict(self.ambo_h2_legacy.get('account', {}) or {})
            old_bets = int(old_a.get('bets', 0) or 0)
            old_wins = int(old_a.get('wins', 0) or 0)
            old_cost = int(old_a.get('cost_cents', 0) or 0)
            old_gross = int(old_a.get('gross_cents', 0) or 0)
            parts += [
                '', '📦 ARCHIVIO PRECEDENTE AMBO H2 (NON SOMMATO)',
                f'• puntate={old_bets} | ambi={old_wins} | costo={sim_euro(old_cost)} | '
                f'lordo={sim_euro(old_gross)} | netto={sim_euro(old_gross-old_cost)}'
            ]

        parts.append('⚠️ Solo simulazione. ENGINE / MULTI-HIT / PLAY e relativo storico restano invariati.')
        return '\n'.join(parts)

    @staticmethod
    def _sosiap_tie(key, name, n):
        # Pareggi pseudo-casuali RIPRODUCIBILI solo da info note al segnale.
        seed = f"{key}|{name}|{n}".encode("utf-8")
        return int.from_bytes(hashlib.blake2s(seed, digest_size=8).digest(), "big")

    def _sosiap_experts(self, from_key):
        # Ogni mappa e' ricavata ESCLUSIVAMENTE dai draw originali gia' noti.
        hist = self.engine_history
        if len(hist) < ENGINE_MIN_HISTORY:
            return {}
        rows = [set(row["nums"]) for row in hist]
        last = rows[-1]
        raw = {}
        for window in (5, 20, 100):
            cnt = Counter(n for row in rows[-window:] for n in row)
            raw[f"hot{window}"] = {n: cnt[n] for n in range(1, 91)}
        raw["repeat"] = {n: int(n in last) for n in range(1, 91)}
        raw["transition"] = self._engine_transition_scores()
        # Stessi mini-engine dell'ENGINE, ma usa la classifica di TUTTI i 90.
        comp_raw = {"freq": self._engine_frequency_scores(),
                    "transition": raw["transition"],
                    "neighbor": self._engine_neighbor_scores(),
                    "gap": self._engine_gap_hazard_scores()}
        comp = {name: self._engine_standardize(vals) for name, vals in comp_raw.items()}
        weights = {"freq": .35, "transition": .30, "neighbor": .20, "gap": .15}
        raw["engine4"] = {n: sum(weights[k] * comp[k][n] for k in weights)
                          for n in range(1, 91)}
        # I pareggi non devono favorire sistematicamente i numeri 1-20.
        return {name: sorted(range(1, 91),
                             key=lambda n: (-score[n], self._sosiap_tie(from_key, name, n)))
                for name, score in raw.items()}

    @staticmethod
    def _sosiap_valid_pretrain(raw):
        if not isinstance(raw, dict) or raw.get("schema") != "sosiap-pretrain-v1":
            return None
        experts = raw.get("experts", {})
        if not isinstance(experts, dict):
            return None
        parsed = {}
        for name in SOSIA_PRED_NAMES:
            item = experts.get(name)
            if not isinstance(item, dict):
                return None
            try:
                n = int(item["n"])
                ema = float(item["ema_hits"])
                hits = int(item["hits"])
            except (KeyError, TypeError, ValueError, OverflowError):
                return None
            if n < 1 or not (0 <= hits <= 20 * n) or not math.isfinite(ema) or not 0 <= ema <= 20:
                return None
            parsed[name] = {"n": n, "hits": hits, "ema_hits": ema}
        try:
            train_draws = int(raw.get("training_draws", 0))
        except (TypeError, ValueError):
            return None
        if train_draws < ENGINE_MIN_HISTORY:
            return None
        return {"schema": "sosiap-pretrain-v1", "experts": parsed,
                "training_draws": train_draws,
                "source_sha256": str(raw.get("source_sha256", ""))[:64],
                "test": raw.get("test", {}) if isinstance(raw.get("test"), dict) else {}}

    def _sosiap_load_pretrain(self):
        # Priorita' allo state persistito. Un nuovo file esplicito nel repository
        # puo' sostituire soltanto questo pretrain: mai i risultati LIVE.
        if not os.path.isfile(SOSIA_PRETRAIN_FILE):
            return
        try:
            with open(SOSIA_PRETRAIN_FILE, encoding="utf-8") as f:
                candidate = self._sosiap_valid_pretrain(json.load(f))
            if candidate:
                self.sosiap_pretrain = candidate
                console_log(f"SOSIA BACKTEST PRETRAIN CARICATO | draw train={candidate['training_draws']}")
            else:
                console_log("SOSIA BACKTEST PRETRAIN NON VALIDO: nessun peso importato")
        except (OSError, ValueError) as exc:
            console_log(f"SOSIA BACKTEST PRETRAIN NON CARICATO: {exc}")

    def _sosiap_weights(self):
        # Prior offline + adattamento online: il passato non e' aggiunto alle
        # metriche forward, e perde influenza man mano che arrivano esiti LIVE.
        baseline = 400.0 / 90.0
        weights = {}
        prior = self.sosiap_pretrain or {}
        prior_experts = prior.get("experts", {})
        for name in SOSIA_PRED_NAMES:
            st = self.sosiap_learning[name]
            old = prior_experts.get(name)
            if old:
                effective_prior = min(SOSIA_PRETRAIN_STRENGTH, float(old["n"]))
                n_live = max(0, st["n"])
                ema = (effective_prior * old["ema_hits"] + n_live * st["ema_hits"]) / (effective_prior + n_live)
                shrink = min(1.0, (effective_prior + n_live) / 60.0)
            else:
                ema = st["ema_hits"]
                shrink = min(1.0, st["n"] / 60.0)
            advantage = max(-3.0, min(3.0, ema - baseline))
            weights[name] = math.exp(0.5 * shrink * advantage)
        total = sum(weights.values())
        return {name: value / total for name, value in weights.items()}

    def _sosiap_arm(self, current_key):
        if not SOSIA_PRED_ENABLED or len(self.engine_history) < ENGINE_MIN_HISTORY:
            return
        if self.sosiap_pending and self.sosiap_pending.get("from_key") == current_key:
            return
        experts = self._sosiap_experts(current_key)
        if any(len(experts.get(name, [])) != 90 for name in SOSIA_PRED_NAMES):
            return
        weights = self._sosiap_weights()
        total = {n: 0.0 for n in range(1, 91)}
        selections = {}
        for name in SOSIA_PRED_NAMES:
            ranking = experts[name]
            selections[name] = sorted(ranking[:20])
            for position, n in enumerate(ranking):
                total[n] += weights[name] * (89 - position) / 89.0
        ranking = sorted(range(1, 91),
                         key=lambda n: (-total[n], self._sosiap_tie(current_key, "ensemble", n)))
        self.sosiap_pending = {"from_key": str(current_key), "prediction": sorted(ranking[:20]),
                               "experts": selections, "weights": weights,
                               "previous": list(self.engine_history[-1]["nums"])}

    def _sosiap_settle(self, day, e, nums):
        p = self.sosiap_pending
        if not SOSIA_PRED_ENABLED or not p:
            return
        self.sosiap_pending = None
        if not sim_draw_is_consecutive(p.get("from_key"), day, e):
            self.sosiap_totals["skipped"] += 1
            return
        if not self._sosia_valid20(p.get("prediction")) or not all(
                self._sosia_valid20(p.get("experts", {}).get(name))
                for name in SOSIA_PRED_NAMES):
            self.sosiap_totals["skipped"] += 1
            return
        actual = set(nums)
        hits = len(actual.intersection(p["prediction"]))
        expert_hits = {name: len(actual.intersection(p["experts"][name]))
                       for name in SOSIA_PRED_NAMES}
        # Il sosia casuale era a sua volta congelato prima del draw; non creare
        # un nuovo random dopo aver visto l'estrazione da confrontare.
        baseline_hits = None
        if self.sosia_records and self.sosia_records[-1].get("key") == draw_key(day, e):
            br = self.sosia_records[-1]
            if br.get("source_key") == p["from_key"]:
                baseline_hits = int(br["overlap"])
        rec = {"key": draw_key(day, e), "source_key": p["from_key"],
               "prediction": p["prediction"], "real": sorted(nums), "hits": hits,
               "common": sorted(actual.intersection(p["prediction"])),
               "previous_repeated": len(actual.intersection(p["previous"])),
               "baseline_hits": baseline_hits, "expert_hits": expert_hits,
               "weights_before": p["weights"]}
        self.sosiap_records.append(rec)
        self.sosiap_records = self.sosiap_records[-SOSIA_PRED_RECORD_MAX:]
        t = self.sosiap_totals
        t["evaluated"] += 1
        t["hits"] += hits
        t["zero"] += int(hits == 0)
        if baseline_hits is not None:
            t["baseline_n"] += 1
            t["baseline_hits"] += baseline_hits
        for name, count in expert_hits.items():
            st = self.sosiap_learning[name]
            st["n"] += 1
            st["hits"] += count
            # Il modello puo' cambiare preferenza se cambia il comportamento
            # osservato, senza riottimizzare le vecchie predizioni.
            st["ema_hits"] = 0.96 * st["ema_hits"] + 0.04 * count

    def sosiap_text(self):
        pending = self.sosiap_pending
        t = self.sosiap_totals
        count = int(t["evaluated"])
        rows = self.sosiap_records
        lines = ["🧠 SOSIA ADATTIVO — PREVISIONE DI 20 NUMERI PER LA PROSSIMA ESTRAZIONE",
                 "Legge le estrazioni reali precedenti, emette la previsione, poi aggiorna i criteri dopo l'esito.",
                 "Non modifica ENGINE TOP1 / AMBO. Nessuna puntata automatica.", ""]
        if pending:
            lines += [f"🎯 PREVISIONE CONGELATA DOPO {pending['from_key']}:",
                      " ".join(f"{n:02d}" for n in pending["prediction"]),
                      "Valida soltanto per l'estrazione immediatamente successiva."]
        else:
            lines += ["🎯 In attesa di un nuovo draw originale per generare la prossima previsione."]
        lines += ["", f"📊 CONFRONTI PROSPETTICI: {count} | salti: {t['skipped']}",
                  f"• numeri indovinati: {t['hits']}/{count * 20} | media {t['hits']/count:.3f}/20" if count
                  else "• primi risultati: in attesa della prossima estrazione",
                  "• riferimento casuale teorico: 4,444 su 20"]
        if t["baseline_n"]:
            lines.append(f"• controllo SOSIA casuale sugli stessi {t['baseline_n']} draw: "
                         f"{t['baseline_hits']/t['baseline_n']:.3f}/20")
        if rows:
            last = rows[-1]
            tail = rows[-min(100, len(rows)):]
            lines += [f"• ultimi {len(tail)} draw: {sum(x['hits'] for x in tail)/len(tail):.3f}/20", "",
                      f"🧾 ULTIMO CONFRONTO {last['key']}",
                      "• previsti: " + " ".join(f"{n:02d}" for n in last["prediction"]),
                      "• reali: " + " ".join(f"{n:02d}" for n in last["real"]),
                      f"• centrati {last['hits']}/20: " + (
                          " ".join(f"{n:02d}" for n in last["common"]) or "nessuno")]
        if self.sosiap_pretrain:
            prior = self.sosiap_pretrain
            lines += ["", f"🎓 BACKTEST PRETRAIN: {prior['training_draws']} draw storici; "
                      "pesi separati dai risultati LIVE."]
            test = prior.get("test", {})
            if int(test.get("n", 0) or 0):
                lines.append(f"• verifica successiva fuori train: "
                             f"{int(test['hits']) / int(test['n']):.3f}/20 "
                             f"su {int(test['n'])} draw "
                             f"| casuale {int(test.get('random_hits',0))/int(test['n']):.3f}/20")
        if pending:
            lines += ["", "⚙️ PESI APPRESI DAI RISULTATI PRECEDENTI:"]
            for name in SOSIA_PRED_NAMES:
                st = self.sosiap_learning[name]
                lines.append(f"• {name}: peso {pending['weights'][name]*100:.1f}% "
                             f"| media storica {st['hits']/st['n']:.2f}/20" if st["n"]
                             else f"• {name}: peso {pending['weights'][name]*100:.1f}% | nessun esito ancora")
        lines += ["", "⚠️ L'apprendimento e' verificabile, ma non garantisce un vantaggio: "
                  "i draw indipendenti non sono prevedibili dallo storico.",
                  "TOP5 interno, SNIPER PROB, coppia 190 e FUSION: /sosiasniper",
                  "Controllo uniforme separato: /sosiarandom"]
        return "\n".join(lines)

    def _sosiasniper_rank(self, from_key, weights=None):
        """Graduatoria interna del SOSIA, calcolata senza usare il draw futuro."""
        experts = self._sosiap_experts(from_key)
        if any(len(experts.get(name, [])) != 90 for name in SOSIA_PRED_NAMES):
            return None
        if not isinstance(weights, dict) or any(name not in weights for name in SOSIA_PRED_NAMES):
            weights = self._sosiap_weights()
        try:
            w = {name: float(weights[name]) for name in SOSIA_PRED_NAMES}
        except (TypeError, ValueError, KeyError):
            return None
        sw = sum(w.values())
        if not math.isfinite(sw) or sw <= 0:
            return None
        w = {name: value / sw for name, value in w.items()}
        total = {n: 0.0 for n in range(1, 91)}
        expert_pos = {n: {} for n in range(1, 91)}
        top20 = {}
        for name in SOSIA_PRED_NAMES:
            ranking = experts[name]
            top20[name] = set(ranking[:20])
            for position, n in enumerate(ranking):
                expert_pos[n][name] = position + 1
                total[n] += w[name] * (89 - position) / 89.0
        ranking = sorted(range(1, 91),
                         key=lambda n: (-total[n], self._sosiap_tie(from_key, "ensemble", n)))
        top = ranking[:20]
        if len(top) < 5:
            return None
        # ProbScore = indice comparativo, NON probabilita' reale. Serve solo a
        # riordinare i 20 candidati con segnali indipendenti dal futuro.
        top_scores = [total[n] for n in top]
        lo, hi = min(top_scores), max(top_scores)
        span = max(1e-12, hi - lo)
        engine_p = self.engine_pending if isinstance(self.engine_pending, dict) else None
        engine_hc = bool(engine_p and engine_p.get("accepted") and
                         str(engine_p.get("signal_from_key") or "") == str(from_key))
        engine_num = int(engine_p.get("top1")) if engine_hc and engine_p.get("top1") else None
        prob_score = {}
        consensus_map = {}
        for rank_idx, n in enumerate(top, start=1):
            cons = sum(n in top20[name] for name in SOSIA_PRED_NAMES)
            consensus_map[n] = int(cons)
            norm_score = (total[n] - lo) / span
            rank_bonus = (20 - rank_idx) / 19.0
            # L'ENGINE entra solo se ha creato HIGH CONFIDENCE PRIMA del draw futuro.
            fusion_bonus = 1.0 if engine_num == n else 0.0
            prob_score[n] = (0.58 * norm_score + 0.24 * (cons / 6.0) +
                             0.10 * rank_bonus + 0.08 * fusion_bonus)
        prob_rank = sorted(top, key=lambda n: (-prob_score[n], -total[n],
                                               self._sosiap_tie(from_key, "prob", n)))

        # Miglior coppia tra tutte le 190 coppie dei TOP20. La co-uscita e' solo
        # una componente piccola; non deve dominare i due punteggi individuali.
        recent = self.engine_history[-SOSIA_SNIPER_PAIR_LOOKBACK:]
        pair_counts = Counter()
        if recent:
            top_set = set(top)
            for row in recent:
                vals = sorted(top_set.intersection(set(map(int, row.get("nums", [])))))
                for a, b in combinations(vals, 2):
                    pair_counts[(a, b)] += 1
        max_pair = max(pair_counts.values(), default=1)
        best_pair = None
        best_pair_score = -1.0
        for a, b in combinations(top, 2):
            key = tuple(sorted((a, b)))
            co = pair_counts.get(key, 0)
            co_norm = co / max_pair if max_pair else 0.0
            sc = 0.45 * prob_score[a] + 0.45 * prob_score[b] + 0.10 * co_norm
            if sc > best_pair_score:
                best_pair_score = sc
                best_pair = key
        a, b = top[0], top[1]
        engine_rank = (top.index(engine_num) + 1) if engine_num in top else None
        return {
            "ranking": ranking, "top20": top, "top5": top[:5],
            "top1": a, "top2": b,
            "score": float(total[a]), "score2": float(total[b]),
            "gap": float(total[a] - total[b]),
            "consensus": int(consensus_map[a]), "consensus2": int(consensus_map[b]),
            "weights": w, "scores": {n: float(total[n]) for n in top},
            "consensus_map": consensus_map, "expert_pos": expert_pos,
            "prob_score": {n: float(prob_score[n]) for n in top},
            "prob_rank": prob_rank, "prob_pick": int(prob_rank[0]),
            "best_pair": list(best_pair) if best_pair else [a, b],
            "best_pair_score": float(best_pair_score),
            "engine_hc": engine_hc, "engine_top1": engine_num,
            "engine_rank": engine_rank,
        }

    def _sosiasniper_build_pending(self, current_key, info):
        prob_pick = int(info["prob_pick"])
        pair = [int(x) for x in info["best_pair"]]
        return {
            "from_key": str(current_key),
            "top1": int(info["top1"]), "top2": int(info["top2"]),
            "top5": [int(x) for x in info["top5"]],
            "score": info["score"], "score2": info["score2"],
            "gap": info["gap"], "consensus": info["consensus"],
            "consensus2": info["consensus2"],
            "strong": bool(info["gap"] >= SOSIA_SNIPER_STRONG_GAP),
            "strong_threshold": SOSIA_SNIPER_STRONG_GAP,
            "prob_pick": prob_pick,
            "prob_score": float(info["prob_score"][prob_pick]),
            "prob_consensus": int(info["consensus_map"].get(prob_pick, 0)),
            "prob_rank_original": int(info["top20"].index(prob_pick) + 1),
            "best_pair": pair,
            "best_pair_score": float(info["best_pair_score"]),
            "engine_hc": bool(info.get("engine_hc")),
            "engine_top1": info.get("engine_top1"),
            "engine_rank": info.get("engine_rank"),
            "ultra": bool(info["score"] >= SOSIA_SNIPER_ULTRA_SCORE and
                          info["gap"] >= SOSIA_SNIPER_ULTRA_GAP),
            "ultra_score_threshold": SOSIA_SNIPER_ULTRA_SCORE,
            "ultra_gap_threshold": SOSIA_SNIPER_ULTRA_GAP,
        }

    def _sosiasniper_arm(self, current_key):
        if not SOSIA_PRED_ENABLED or not self.sosiap_pending:
            return None
        p = self.sosiap_pending
        if str(p.get("from_key") or "") != str(current_key):
            return None
        info = self._sosiasniper_rank(current_key, p.get("weights"))
        if not info:
            return None
        if sorted(info["ranking"][:20]) != sorted(p.get("prediction", [])):
            console_log("SOSIA SNIPER: ranking non coerente col TOP20 congelato; nessun segnale")
            return None
        self.sosiasniper_pending = self._sosiasniper_build_pending(current_key, info)
        return self.sosiasniper_pending

    def _sosiasniper_migrate_pending(self):
        if self.sosiasniper_pending or not self.sosiap_pending or not self.engine_history:
            return False
        from_key = str(self.sosiap_pending.get("from_key") or "")
        if not from_key or str(self.engine_history[-1].get("key") or "") != from_key:
            return False
        return bool(self._sosiasniper_arm(from_key))

    def _sosiasniper_upgrade_pending(self):
        """Arricchisce un pending creato dalla versione precedente senza cambiarne il draw."""
        p = self.sosiasniper_pending
        if not p or p.get("top5") or not self.sosiap_pending:
            return False
        from_key = str(p.get("from_key") or "")
        if str(self.sosiap_pending.get("from_key") or "") != from_key:
            return False
        info = self._sosiasniper_rank(from_key, self.sosiap_pending.get("weights"))
        if not info:
            return False
        upgraded = self._sosiasniper_build_pending(from_key, info)
        # TOP1/TOP2 della vecchia previsione devono essere identici; altrimenti
        # non sostituiamo retroattivamente il segnale gia' congelato.
        if int(upgraded["top1"]) != int(p.get("top1", -1)) or int(upgraded["top2"]) != int(p.get("top2", -1)):
            return False
        p.update(upgraded)
        return True

    def _sosiasniper_settle(self, day, e, nums):
        p = self.sosiasniper_pending
        if not p:
            return None
        self.sosiasniper_pending = None
        if not sim_draw_is_consecutive(p.get("from_key"), day, e):
            self.sosiasniper_totals["skipped"] += 1
            return {"skipped": True, "key": draw_key(day, e), "source_key": p.get("from_key"),
                    "top1": p.get("top1"), "top2": p.get("top2")}
        actual = set(map(int, nums))
        top1 = int(p["top1"]); top2 = int(p["top2"])
        top5 = [int(x) for x in p.get("top5", [top1, top2])][:5]
        h1 = top1 in actual; h2 = top2 in actual; ambo = h1 and h2
        rank_hits = [n in actual for n in top5]
        prob_pick = int(p.get("prob_pick", top1)); prob_hit = prob_pick in actual
        pair = [int(x) for x in p.get("best_pair", [top1, top2])][:2]
        pair_hit = len(pair) == 2 and pair[0] in actual and pair[1] in actual
        engine_hc = bool(p.get("engine_hc")); engine_num = p.get("engine_top1")
        fusion_hit = bool(engine_hc and engine_num is not None and int(engine_num) in actual)
        rec = {
            "key": draw_key(day, e), "source_key": str(p["from_key"]),
            "top1": top1, "top2": top2, "top5": top5,
            "score": float(p["score"]), "score2": float(p["score2"]), "gap": float(p["gap"]),
            "consensus": int(p["consensus"]), "consensus2": int(p.get("consensus2", 0)),
            "strong": bool(p.get("strong")), "strong_threshold": float(p.get("strong_threshold", SOSIA_SNIPER_STRONG_GAP)),
            "top1_hit": bool(h1), "top2_hit": bool(h2), "ambo_hit": bool(ambo),
            "rank_hits": rank_hits,
            "prob_pick": prob_pick, "prob_score": float(p.get("prob_score", 0.0)),
            "prob_rank_original": int(p.get("prob_rank_original", 1)), "prob_hit": bool(prob_hit),
            "best_pair": pair, "best_pair_score": float(p.get("best_pair_score", 0.0)),
            "best_pair_hit": bool(pair_hit),
            "engine_hc": engine_hc, "engine_top1": engine_num, "engine_rank": p.get("engine_rank"),
            "fusion_hit": fusion_hit,
            "ultra": bool(p.get("ultra")), "ultra_hit": bool(h1 and p.get("ultra")),
            "real": sorted(actual),
        }
        self.sosiasniper_records.append(rec)
        self.sosiasniper_records = self.sosiasniper_records[-SOSIA_SNIPER_RECORD_MAX:]
        t = self.sosiasniper_totals
        t["evaluated"] += 1
        t["top1_hits"] += int(h1); t["top2_hits"] += int(h2); t["ambo_hits"] += int(ambo)
        for idx, key in ((2, "rank3_hits"), (3, "rank4_hits"), (4, "rank5_hits")):
            if len(rank_hits) > idx:
                t[key] += int(rank_hits[idx])
        if rec["strong"]:
            t["strong_evaluated"] += 1; t["strong_top1_hits"] += int(h1); t["strong_ambo_hits"] += int(ambo)
        t["prob_evaluated"] += 1; t["prob_hits"] += int(prob_hit)
        t["bestpair_evaluated"] += 1; t["bestpair_hits"] += int(pair_hit)
        if engine_hc:
            t["fusion_evaluated"] += 1; t["fusion_hits"] += int(fusion_hit)
            if p.get("engine_rank") is not None and int(p.get("engine_rank")) <= 3:
                t["fusion_top3_evaluated"] += 1; t["fusion_top3_hits"] += int(fusion_hit)
        if rec["ultra"]:
            t["ultra_evaluated"] += 1; t["ultra_hits"] += int(h1)
        return rec

    def _sosiapattern_arm(self, current_key):
        """Congela ranking COMPLETO prima del risultato; nessun uso del futuro."""
        old = self.sosiapattern_pending
        if old:
            # Non riscrivere una classifica gia' salvata, neanche al riavvio.
            return old if str(old.get("from_key")) == str(current_key) else None
        pred = self.sosiap_pending
        if not pred or str(pred.get("from_key") or "") != str(current_key):
            return None
        if not self.engine_history or str(self.engine_history[-1].get("key")) != str(current_key):
            return None
        info = self._sosiasniper_rank(current_key, pred.get("weights"))
        if not info:
            return None
        ranking = [int(n) for n in info["ranking"][:20]]
        if sorted(ranking) != sorted(map(int, pred.get("prediction", []))):
            console_log("SOSIA PATTERN: ranking diverso dal SOSIA congelato; tracker non attivato")
            return None
        sp = self.sosiasniper_pending
        if sp and str(sp.get("from_key")) == str(current_key):
            old5 = [int(n) for n in sp.get("top5", [])]
            if old5 and ranking[:len(old5)] != old5:
                console_log("SOSIA PATTERN: TOP5 diverso dal segnale congelato; tracker non attivato")
                return None
        # Gli score sono diagnostici, NON probabilita'. Memorizziamo il ranking
        # e le 20 posizioni prima di conoscere il prossimo esito.
        self.sosiapattern_pending = {
            "from_key": str(current_key), "rank20": ranking,
            "scores": [round(float(info["scores"][n]), 6) for n in ranking],
            "consensus": [int(info["consensus_map"][n]) for n in ranking],
        }
        return self.sosiapattern_pending

    def _sosiapattern_settle(self, day, e, nums):
        p = self.sosiapattern_pending
        if not p:
            return None
        self.sosiapattern_pending = None
        key = draw_key(day, e)
        if not sim_draw_is_consecutive(p.get("from_key"), day, e):
            self.sosiapattern_skipped += 1
            return {"skipped": True, "key": key, "from_key": p.get("from_key")}
        rank20 = p.get("rank20", [])
        if not self._sosia_valid20(rank20):
            self.sosiapattern_skipped += 1
            return {"skipped": True, "key": key, "from_key": p.get("from_key")}
        actual = sorted(map(int, nums))
        actual_pos = {n: i+1 for i, n in enumerate(actual)}
        numerical_pred_pos = {n: i+1 for i, n in enumerate(sorted(rank20))}
        hit_ranks = [i+1 for i, n in enumerate(rank20) if n in actual_pos]
        hit_nums = [rank20[i-1] for i in hit_ranks]
        r = {
            "key": key, "from_key": p["from_key"],
            "rank20": list(rank20), "hits": len(hit_ranks),
            "hit_ranks": hit_ranks, "hit_nums": hit_nums,
            "hit_pred_numeric_positions": [numerical_pred_pos[n] for n in hit_nums],
            "hit_real_numeric_positions": [actual_pos[n] for n in hit_nums],
            "hit_scores": [p.get("scores", [None]*20)[i-1] for i in hit_ranks],
            "hit_consensus": [p.get("consensus", [None]*20)[i-1] for i in hit_ranks],
        }
        self.sosiapattern_records.append(r)
        return r

    @staticmethod
    def _sosiapattern_result_lines(result):
        if not result:
            return []
        if result.get("skipped"):
            return ["🔎 PATTERN: draw non consecutivo, nessuna posizione inventata."]
        ranks = result["hit_ranks"]
        hits = result["hit_nums"]
        pred_pos = result["hit_pred_numeric_positions"]
        real_pos = result["hit_real_numeric_positions"]
        detail = (
            ", ".join(f"{n:02d}(rank#{r},lista#{p},reale#{a})"
                      for n,r,p,a in zip(hits,ranks,pred_pos,real_pos))
            if ranks else "nessuno"
        )
        bins = [sum(lo <= rank <= lo+4 for rank in ranks) for lo in (1,6,11,16)]
        return [f"🔎 PATTERN — {result['hits']}/20 | posizioni HIT nel ranking: " +
                (" ".join(f"#{r}" for r in ranks) if ranks else "nessuna"),
                f"• numeri (rank interno, lista ordinata, estrazione ordinata): {detail}",
                f"• HIT per fascia ranking 1–5 / 6–10 / 11–15 / 16–20: " + " / ".join(map(str,bins))]

    def sosiapattern_text(self):
        rows = self.sosiapattern_records
        n = len(rows)
        lines = ["🔎 SOSIA PATTERN — DOVE SI TROVANO I NUMERI CENTRATI", "",
                 f"Confronti con ranking completo congelato: {n} | salti: {self.sosiapattern_skipped}",
                 "Ranking congelato PRIMA del draw; HIT registrati soltanto DOPO l’esito."]
        if not n:
            lines += ["Nessun confronto completo ancora disponibile. Il vecchio storico rimane conservato."]
            return "\n".join(lines)
        counts = [0]*20
        selected = Counter(); hits = Counter()
        for row in rows:
            good = set(row["hit_ranks"])
            for idx,num in enumerate(row["rank20"], 1):
                selected[int(num)] += 1
                if idx in good:
                    counts[idx-1] += 1
                    hits[int(num)] += 1
        recent = rows[-min(n,100):]
        recent_hits = sum(row["hits"] for row in recent)
        lines += [f"Media HIT dei 20: {sum(counts)/n:.3f}/20 | casuale teorico 4.444/20",
                  f"Ultimi {len(recent)} draw: {recent_hits/len(recent):.3f}/20", "",
                  "📍 HIT PER POSIZIONE INTERNA (#1..#20), senza rimescolare il ranking:"]
        for start in (0,5,10,15):
            lines.append(" ".join(f"#{j+1}:{counts[j]}/{n}({safe_pct(counts[j],n):.1f}%)"
                                  for j in range(start,start+5)))
        lines += ["", "📦 FASCE DI 5 POSIZIONI (su 5 numeri per draw):"]
        for a in (0,5,10,15):
            c=sum(counts[a:a+5]); lines.append(f"• #{a+1}–#{a+5}: {c}/{5*n} ({safe_pct(c,5*n):.2f}% per numero) | riferimento 22.22%")
        last = rows[-1]
        lines += ["",f"🧾 ULTIMO {last['key']} | {last['hits']}/20"] + self._sosiapattern_result_lines(last)[1:]
        lines += ["", "📚 NUMERI CENTRATI PIU' SPESSO (frequenza di selezione tra parentesi):"]
        for number,hit_count in sorted(hits.items(), key=lambda t:(-t[1],t[0]))[:8]:
            times=selected[number]
            lines.append(f"• {number:02d}: {hit_count}/{times} selezioni ({safe_pct(hit_count,times):.1f}%)")
        lines += ["", "🧩 ULTIMI 10 SCHEMI DI POSIZIONE (X=HIT, ·=MISS, 4 blocchi da 5):"]
        for row in rows[-10:]:
            good = set(row["hit_ranks"])
            mask = " ".join("".join("X" if i in good else "·" for i in range(start,start+5))
                            for start in (1,6,11,16))
            lines.append(f"• {row['key']}: {mask} ({row['hits']}/20)")
        lines += self._sosiapatternlab_summary_lines()
        lines += ["", "Le posizioni nella lista numerica 01..90 NON sono il ranking per score.",
                  "POSITION/TRANSITION/WATCH usano shrink e sono tracker prospettici, non probabilita' garantite.",
                  "La frequenza di uno schema passato non garantisce ripetizioni future.",
                  "Non cambia previsione, pesi, ENGINE o giocate: ricerca SHADOW."]
        return "\n".join(lines)

    @staticmethod
    def _pattern_band_counts(row):
        good = set(int(x) for x in row.get("hit_ranks", []) if isinstance(x, (int, float)))
        return [sum(start <= r <= start + 4 for r in good) for start in (1, 6, 11, 16)]

    @classmethod
    def _pattern_dominant_band(cls, row):
        counts = cls._pattern_band_counts(row)
        if not counts or max(counts) <= 0:
            return None
        m = max(counts)
        winners = [i for i, value in enumerate(counts) if value == m]
        return winners[0] if len(winners) == 1 else None

    @staticmethod
    def _pattern_band_name(idx):
        return ("A #1-5", "B #6-10", "C #11-15", "D #16-20")[idx] if idx in range(4) else "-"

    @staticmethod
    def _pattern_keys_consecutive(a, b):
        try:
            day, draw_id = str(b).rsplit("#", 1)
            return sim_draw_is_consecutive(a, day, int(draw_id))
        except Exception:
            return False

    def _sosiapattern_position_stats(self):
        """Posterior shrink per ogni posizione, usando SOLO draw gia' conclusi."""
        rows = self.sosiapattern_records
        n = len(rows)
        hits = [0] * 20
        for row in rows:
            for r in row.get("hit_ranks", []):
                try:
                    rr = int(r)
                except (TypeError, ValueError):
                    continue
                if 1 <= rr <= 20:
                    hits[rr - 1] += 1
        base = 20.0 / 90.0
        prior = SOSIA_POS_PRIOR_DRAWS
        posterior = [(h + prior * base) / (n + prior) for h in hits]
        return {"n": n, "hits": hits, "posterior": posterior, "baseline": base}

    def _sosiapattern_number_stats(self):
        selected = Counter(); hits = Counter()
        for row in self.sosiapattern_records:
            good = set(int(x) for x in row.get("hit_nums", []))
            for num in row.get("rank20", []):
                try:
                    n = int(num)
                except (TypeError, ValueError):
                    continue
                selected[n] += 1
                if n in good:
                    hits[n] += 1
        base = 20.0 / 90.0
        prior = SOSIA_NUMBER_WATCH_PRIOR
        out = {}
        for n in range(1, 91):
            sel = int(selected.get(n, 0)); hit = int(hits.get(n, 0))
            post = (hit + prior * base) / (sel + prior)
            out[n] = {"selected": sel, "hits": hit, "posterior": post,
                      "raw": (hit / sel) if sel else None}
        return out

    def _sosiapattern_transition_stats(self):
        """Transizioni fra fascia dominante, ignorando tie e buchi temporali."""
        matrix = [[0 for _ in range(4)] for _ in range(4)]
        rows = self.sosiapattern_records
        for left, right in zip(rows, rows[1:]):
            if not self._pattern_keys_consecutive(left.get("key"), right.get("key")):
                continue
            a = self._pattern_dominant_band(left)
            b = self._pattern_dominant_band(right)
            if a is None or b is None:
                continue
            matrix[a][b] += 1
        last_band = self._pattern_dominant_band(rows[-1]) if rows else None
        support = sum(matrix[last_band]) if last_band is not None else 0
        predicted = None
        if last_band is not None and support >= SOSIA_TRANSITION_MIN_SUPPORT:
            # Laplace non cambia l'ordine ma rende esplicito che non trattiamo
            # pochi casi come una probabilita' certa.
            vals = [matrix[last_band][j] + 1 for j in range(4)]
            best = max(vals)
            winners = [j for j, v in enumerate(vals) if v == best]
            if len(winners) == 1:
                predicted = winners[0]
        return {"matrix": matrix, "last_band": last_band,
                "support": support, "predicted": predicted}

    def _sosiapatternlab_arm(self, current_key):
        """Congela le tre nuove piste prima del prossimo draw."""
        if not current_key:
            return None
        old = self.sosiapatternlab_pending
        if old:
            return old if str(old.get("from_key")) == str(current_key) else None
        pat = self.sosiapattern_pending
        if not pat or str(pat.get("from_key") or "") != str(current_key):
            return None
        rank20 = [int(x) for x in pat.get("rank20", [])]
        if not self._sosia_valid20(rank20):
            return None
        scores = list(pat.get("scores", []))
        cons = list(pat.get("consensus", []))
        if len(scores) != 20:
            scores = [20 - i for i in range(20)]
        if len(cons) != 20:
            cons = [0] * 20

        # 1) POSITION CALIBRATED. Il posterior e' shrinkato verso 22.22%; non e'
        # una probabilita' garantita. La correzione resta moderata.
        pst = self._sosiapattern_position_stats()
        base = pst["baseline"]
        pos_post = pst["posterior"]
        calibrated = []
        for i, n in enumerate(rank20):
            raw_score = max(1e-9, float(scores[i]))
            ratio = max(0.50, min(1.50, pos_post[i] / base))
            idx = raw_score * (ratio ** SOSIA_POS_CAL_EXPONENT)
            calibrated.append((idx, raw_score, pos_post[i], n, i + 1, int(cons[i])))
        calibrated.sort(key=lambda x: (-x[0], x[4], x[3]))
        best = calibrated[0]

        # 2) NUMBER WATCH: soltanto numeri gia' nel TOP20 corrente. Il confronto
        # prospettico parte ora; lo storico serve solo a creare il ranking iniziale.
        nstats = self._sosiapattern_number_stats()
        watch_rows = []
        for rank_idx, n in enumerate(rank20, start=1):
            st = nstats[n]
            mature = st["selected"] >= SOSIA_NUMBER_WATCH_MIN_SELECT
            watch_rows.append((1 if mature else 0, st["posterior"], st["selected"],
                               -rank_idx, n, rank_idx, st["hits"], st["raw"]))
        watch_rows.sort(reverse=True)
        watch_rows = watch_rows[:SOSIA_NUMBER_WATCH_SIZE]
        watch = [{"num": int(x[4]), "rank": int(x[5]), "selected": int(x[2]),
                  "hits": int(x[6]), "posterior": float(x[1]),
                  "mature": bool(x[0])} for x in watch_rows]

        # 3) PATTERN TRANSITION: previsione della fascia dominante successiva,
        # solo se lo stato precedente ha supporto storico minimo.
        trans = self._sosiapattern_transition_stats()

        self.sosiapatternlab_pending = {
            "from_key": str(current_key),
            "position_pick": int(best[3]), "position_rank": int(best[4]),
            "position_index": float(best[0]), "position_raw_score": float(best[1]),
            "position_posterior": float(best[2]), "position_history_n": int(pst["n"]),
            "watch": watch,
            "transition_from": trans["last_band"],
            "transition_pred": trans["predicted"],
            "transition_support": int(trans["support"]),
        }
        return self.sosiapatternlab_pending

    def _sosiapatternlab_settle(self, day, e, nums, pattern_result=None):
        p = self.sosiapatternlab_pending
        if not p:
            return None
        self.sosiapatternlab_pending = None
        key = draw_key(day, e)
        if not sim_draw_is_consecutive(p.get("from_key"), day, e):
            self.sosiapatternlab_totals["skipped"] += 1
            return {"skipped": True, "key": key, "from_key": p.get("from_key")}
        actual = set(map(int, nums))
        pos_pick = int(p["position_pick"])
        pos_hit = pos_pick in actual
        watch = [dict(x) for x in p.get("watch", []) if isinstance(x, dict) and x.get("num")]
        watch_hit_nums = [int(x["num"]) for x in watch if int(x["num"]) in actual]
        watch_top1_hit = bool(watch and int(watch[0]["num"]) in actual)

        trans_pred = p.get("transition_pred")
        trans_band_hits = None
        trans_dom = None
        trans_dom_correct = None
        if pattern_result and not pattern_result.get("skipped"):
            trans_dom = self._pattern_dominant_band(pattern_result)
            if trans_pred is not None:
                lo = 1 + 5 * int(trans_pred)
                good = set(int(x) for x in pattern_result.get("hit_ranks", []))
                trans_band_hits = sum(lo <= r <= lo + 4 for r in good)
                if trans_dom is not None:
                    trans_dom_correct = int(trans_dom) == int(trans_pred)

        rec = {
            "key": key, "from_key": str(p["from_key"]),
            "position_pick": pos_pick, "position_rank": int(p["position_rank"]),
            "position_posterior": float(p["position_posterior"]),
            "position_hit": bool(pos_hit),
            "watch": watch, "watch_hit_nums": watch_hit_nums,
            "watch_hits": len(watch_hit_nums), "watch_top1_hit": watch_top1_hit,
            "transition_from": p.get("transition_from"),
            "transition_pred": trans_pred, "transition_support": int(p.get("transition_support", 0)),
            "transition_band_hits": trans_band_hits,
            "transition_actual_dom": trans_dom,
            "transition_dom_correct": trans_dom_correct,
        }
        self.sosiapatternlab_records.append(rec)
        self.sosiapatternlab_records = self.sosiapatternlab_records[-SOSIA_SNIPER_RECORD_MAX:]
        t = self.sosiapatternlab_totals
        t["evaluated"] += 1
        t["pos_evaluated"] += 1; t["pos_hits"] += int(pos_hit)
        if watch:
            t["watch_evaluated"] += 1
            t["watch_picks"] += len(watch)
            t["watch_hits"] += len(watch_hit_nums)
            t["watch_top1_hits"] += int(watch_top1_hit)
        if trans_pred is not None and trans_band_hits is not None:
            t["transition_evaluated"] += 1
            t["transition_band_hits"] += int(trans_band_hits)
            if trans_dom is None:
                t["transition_ties"] += 1
            else:
                t["transition_dom_evaluated"] += 1
                t["transition_dom_correct"] += int(bool(trans_dom_correct))
        return rec

    @classmethod
    def _sosiapatternlab_result_lines(cls, r):
        if not r:
            return []
        if r.get("skipped"):
            return ["🧭 PATTERN LAB: draw non consecutivo, nessun esito inventato."]
        watch_nums = [int(x["num"]) for x in r.get("watch", [])]
        wh = set(int(x) for x in r.get("watch_hit_nums", []))
        lines = [
            "🧭 PATTERN LAB — RISULTATO",
            f"• POSITION CALIBRATED {int(r['position_pick']):02d} (rank originale #{int(r['position_rank'])}): "
            f"{'✅ HIT' if r.get('position_hit') else '❌ MISS'}",
        ]
        if watch_nums:
            lines.append(f"• NUMBER WATCH: {len(wh)}/{len(watch_nums)} HIT | " +
                         " ".join(f"{n:02d}{'✅' if n in wh else '❌'}" for n in watch_nums))
        if r.get("transition_pred") is not None:
            pred = int(r["transition_pred"])
            bh = r.get("transition_band_hits")
            dom = r.get("transition_actual_dom")
            dom_txt = "tie/non unico" if dom is None else cls._pattern_band_name(int(dom))
            lines.append(f"• TRANSITION watch {cls._pattern_band_name(pred)}: {int(bh or 0)}/5 HIT | "
                         f"dominante reale {dom_txt}" +
                         (" | ✅" if r.get("transition_dom_correct") is True else
                          " | ❌" if r.get("transition_dom_correct") is False else ""))
        return lines

    @classmethod
    def _sosiapatternlab_signal_lines(cls, p):
        if not p:
            return ["🧭 PATTERN LAB: in attesa del prossimo congelamento."]
        watch = p.get("watch", [])
        lines = [
            "🧭 PATTERN LAB — PROSSIMA H1",
            f"🎛 POSITION CALIBRATED: {int(p['position_pick']):02d} | rank originale #{int(p['position_rank'])} "
            f"| resa posizione shrink {100*float(p['position_posterior']):.1f}%",
        ]
        if watch:
            parts = []
            for x in watch:
                mark = "*" if x.get("mature") else "~"
                parts.append(f"{int(x['num']):02d}{mark}(r#{int(x['rank'])},{100*float(x['posterior']):.1f}%)")
            lines.append("👁 NUMBER WATCH: " + " ".join(parts))
            lines.append(f"  *=≥{SOSIA_NUMBER_WATCH_MIN_SELECT} selezioni storiche; ~=campione piccolo")
        if p.get("transition_pred") is None:
            prev = cls._pattern_band_name(p.get("transition_from")) if p.get("transition_from") is not None else "-"
            lines.append(f"🔄 PATTERN TRANSITION: stato {prev} | nessun segnale (supporto {int(p.get('transition_support',0))}/{SOSIA_TRANSITION_MIN_SUPPORT})")
        else:
            lines.append(f"🔄 PATTERN TRANSITION: {cls._pattern_band_name(int(p['transition_from']))} → "
                         f"{cls._pattern_band_name(int(p['transition_pred']))} | supporto {int(p.get('transition_support',0))}")
        return lines

    def _sosiapatternlab_summary_lines(self):
        t = self.sosiapatternlab_totals
        pe = int(t.get("pos_evaluated", 0) or 0)
        wp = int(t.get("watch_picks", 0) or 0)
        we = int(t.get("watch_evaluated", 0) or 0)
        te = int(t.get("transition_evaluated", 0) or 0)
        de = int(t.get("transition_dom_evaluated", 0) or 0)
        lines = ["", "🧭 PATTERN LAB — FORWARD NUOVE PISTE"]
        lines += self._sosiapatternlab_signal_lines(self.sosiapatternlab_pending)
        if pe:
            lines.append(f"• POSITION CALIBRATED: {int(t['pos_hits'])}/{pe} ({safe_pct(t['pos_hits'],pe):.2f}%) | baseline 22.22%")
        if wp:
            lines.append(f"• NUMBER WATCH: {int(t['watch_hits'])}/{wp} numeri ({safe_pct(t['watch_hits'],wp):.2f}%) | baseline 22.22%")
            if we:
                lines.append(f"• NUMBER WATCH #1: {int(t['watch_top1_hits'])}/{we} ({safe_pct(t['watch_top1_hits'],we):.2f}%)")
        if te:
            avg = float(t["transition_band_hits"]) / te
            lines.append(f"• TRANSITION fascia scelta: {int(t['transition_band_hits'])}/{5*te} ({safe_pct(t['transition_band_hits'],5*te):.2f}% per numero) "
                         f"| media {avg:.3f}/5 | casuale 1.111/5")
        if de:
            lines.append(f"• TRANSITION dominante corretta: {int(t['transition_dom_correct'])}/{de} ({safe_pct(t['transition_dom_correct'],de):.2f}%) | tie esclusi")
        return lines

    @staticmethod
    def _sosiasniper_signal_lines(p):
        if not p:
            return ["🎯 Nessun segnale SOSIA SNIPER pronto."]
        top5 = [int(x) for x in p.get("top5", [p['top1'], p['top2']])]
        pair = [int(x) for x in p.get("best_pair", [p['top1'], p['top2']])]
        lines = [
            f"🎯 SOSIA SNIPER — PROSSIMA H1 (da {p['from_key']})",
            f"TOP5 interno: " + " > ".join(f"{n:02d}" for n in top5),
            f"Ambata ranking #1: {int(p['top1']):02d} | score {float(p['score']):.3f} | cons {int(p['consensus'])}/6",
            f"Gap #1-#2: +{float(p['gap']):.3f} | STRONG vecchio: {'SÌ' if p.get('strong') else 'NO'}",
            f"🧠 SNIPER PROB: {int(p.get('prob_pick', p['top1'])):02d} | indice {float(p.get('prob_score',0)):.3f} "
            f"| rank originale #{int(p.get('prob_rank_original',1))} | cons {int(p.get('prob_consensus',0))}/6",
            f"🔗 MIGLIOR COPPIA 190: {pair[0]:02d}-{pair[1]:02d} | indice {float(p.get('best_pair_score',0)):.3f}",
        ]
        if p.get("engine_hc"):
            lines.append(f"⚡ FUSION ENGINE: TOP1 ENGINE {int(p['engine_top1']):02d} | posizione SOSIA #{int(p['engine_rank']) if p.get('engine_rank') else 0}")
        else:
            lines.append("⚡ FUSION ENGINE: nessun HIGH CONFIDENCE su questo draw")
        lines.append(f"🧪 ULTRA SHADOW: {'SÌ' if p.get('ultra') else 'NO'} | richiede score≥{SOSIA_SNIPER_ULTRA_SCORE:.2f} e gap≥{SOSIA_SNIPER_ULTRA_GAP:.2f}")
        return lines

    async def _sosiasniper_notice(self, app, result, notify=True, pattern_result=None, lab_result=None):
        if not notify or not SOSIA_SNIPER_NOTIFY:
            return
        lines = []
        if result and result.get("skipped"):
            lines += ["⚠️ SOSIA SNIPER — RISULTATO NON VALUTATO",
                      f"Manca la consecutività dopo {result.get('source_key','-')}; nessun HIT/MISS inventato.", ""]
        elif result:
            pair = result.get("best_pair", [result['top1'], result['top2']])
            lines += [
                f"🧾 SOSIA SNIPER — RISULTATO {result['key']}",
                f"Segnale da: {result['source_key']}",
                f"Ranking #1 {result['top1']:02d}: {'✅ HIT' if result['top1_hit'] else '❌ MISS'}",
                f"SNIPER PROB {result.get('prob_pick', result['top1']):02d}: {'✅ HIT' if result.get('prob_hit') else '❌ MISS'}",
                f"Miglior coppia {int(pair[0]):02d}-{int(pair[1]):02d}: {'✅ HIT' if result.get('best_pair_hit') else '❌ MISS'}",
            ]
            if result.get("engine_hc"):
                lines.append(f"FUSION ENGINE {int(result['engine_top1']):02d} (rank SOSIA #{int(result['engine_rank']) if result.get('engine_rank') else 0}): "
                             f"{'✅ HIT' if result.get('fusion_hit') else '❌ MISS'}")
            if result.get("ultra"):
                lines.append(f"🧪 ULTRA SHADOW ranking #1: {'✅ HIT' if result.get('ultra_hit') else '❌ MISS'}")
            lines.append("")
        else:
            lines += ["🧾 SOSIA SNIPER — PRIMO AVVIO", "Nessun risultato precedente da valutare.", ""]
        if pattern_result:
            lines += self._sosiapattern_result_lines(pattern_result) + [""]
        if lab_result:
            lines += self._sosiapatternlab_result_lines(lab_result) + [""]
        lines += self._sosiasniper_signal_lines(self.sosiasniper_pending)
        lines += [""] + self._sosiapatternlab_signal_lines(self.sosiapatternlab_pending)
        t = self.sosiasniper_totals; ev = int(t.get("evaluated",0) or 0)
        if ev:
            lines += ["", "📊 FORWARD SOSIA SNIPER",
                      f"• rank #1: {t['top1_hits']}/{ev} ({safe_pct(t['top1_hits'],ev):.2f}%)",
                      f"• SNIPER PROB: {t['prob_hits']}/{t['prob_evaluated']} ({safe_pct(t['prob_hits'],t['prob_evaluated']):.2f}%)",
                      f"• coppia 190: {t['bestpair_hits']}/{t['bestpair_evaluated']} ({safe_pct(t['bestpair_hits'],t['bestpair_evaluated']):.2f}%)"]
        fe=int(t.get("fusion_evaluated",0) or 0); f3=int(t.get("fusion_top3_evaluated",0) or 0); ue=int(t.get("ultra_evaluated",0) or 0)
        if fe: lines.append(f"• FUSION ENGINE: {t['fusion_hits']}/{fe} ({safe_pct(t['fusion_hits'],fe):.2f}%)")
        if f3: lines.append(f"• FUSION ENGINE in SOSIA TOP3: {t['fusion_top3_hits']}/{f3} ({safe_pct(t['fusion_top3_hits'],f3):.2f}%)")
        if ue: lines.append(f"• ULTRA SHADOW: {t['ultra_hits']}/{ue} ({safe_pct(t['ultra_hits'],ue):.2f}%)")
        lines += ["", "⚠️ Tutto shadow/sperimentale: nessuna puntata automatica."]
        await self.tg(app, "\n".join(lines))

    def sosiasniper_text(self):
        p=self.sosiasniper_pending; t=self.sosiasniper_totals; ev=int(t.get("evaluated",0) or 0)
        lines=["🎯 SOSIA SNIPER PROB + FUSION", ""] + self._sosiasniper_signal_lines(p)
        lines += ["", f"📊 FORWARD: {ev} valutati | salti: {int(t.get('skipped',0) or 0)}"]
        if ev:
            lines += [
                f"• rank #1: {t['top1_hits']}/{ev} ({safe_pct(t['top1_hits'],ev):.2f}%) | baseline 22.22%",
                f"• rank #2: {t['top2_hits']}/{ev} ({safe_pct(t['top2_hits'],ev):.2f}%)",
                f"• rank #3: {t['rank3_hits']}/{ev} ({safe_pct(t['rank3_hits'],ev):.2f}%)",
                f"• rank #4: {t['rank4_hits']}/{ev} ({safe_pct(t['rank4_hits'],ev):.2f}%)",
                f"• rank #5: {t['rank5_hits']}/{ev} ({safe_pct(t['rank5_hits'],ev):.2f}%)",
                f"• vecchio ambo #1-#2: {t['ambo_hits']}/{ev} ({safe_pct(t['ambo_hits'],ev):.2f}%) | baseline 4.74%",
                f"• SNIPER PROB: {t['prob_hits']}/{t['prob_evaluated']} ({safe_pct(t['prob_hits'],t['prob_evaluated']):.2f}%)",
                f"• miglior coppia 190: {t['bestpair_hits']}/{t['bestpair_evaluated']} ({safe_pct(t['bestpair_hits'],t['bestpair_evaluated']):.2f}%) | baseline 4.74%",
            ]
        fe=int(t.get("fusion_evaluated",0) or 0); f3=int(t.get("fusion_top3_evaluated",0) or 0); ue=int(t.get("ultra_evaluated",0) or 0)
        if fe: lines.append(f"• FUSION ENGINE: {t['fusion_hits']}/{fe} ({safe_pct(t['fusion_hits'],fe):.2f}%)")
        if f3: lines.append(f"• FUSION ENGINE quando ENGINE e' SOSIA TOP3: {t['fusion_top3_hits']}/{f3} ({safe_pct(t['fusion_top3_hits'],f3):.2f}%)")
        if ue: lines.append(f"• ULTRA SHADOW score/gap: {t['ultra_hits']}/{ue} ({safe_pct(t['ultra_hits'],ue):.2f}%)")
        se=int(t.get("strong_evaluated",0) or 0)
        if se: lines.append(f"• STRONG storico gap: {t['strong_top1_hits']}/{se} ({safe_pct(t['strong_top1_hits'],se):.2f}%)")
        if self.sosiasniper_records:
            last=self.sosiasniper_records[-1]; pair=last.get("best_pair",[last['top1'],last['top2']])
            lines += ["", f"🧾 ULTIMO ESITO {last['key']}",
                      f"• rank #1 {last['top1']:02d}: {'HIT' if last['top1_hit'] else 'MISS'}",
                      f"• PROB {last.get('prob_pick',last['top1']):02d}: {'HIT' if last.get('prob_hit') else 'MISS'}",
                      f"• coppia {int(pair[0]):02d}-{int(pair[1]):02d}: {'HIT' if last.get('best_pair_hit') else 'MISS'}"]
        lines += self._sosiapatternlab_summary_lines()
        lines += ["", "ℹ️ ProbScore e indice coppia sono punteggi comparativi, non probabilita' garantite.",
                  "Posizioni + POSITION CALIBRATED + TRANSITION + NUMBER WATCH: /sosiapattern",
                  "Le nuove regole sono tracciate in shadow e non riscrivono lo storico precedente.",
                  "⚠️ Nessuna puntata automatica."]
        return "\n".join(lines)

    @staticmethod
    def _new_sosia_totals():
        return {
            "evaluated": 0, "skipped_gaps": 0, "overlap_sum": 0,
            "sim_repeat_count": 0,
            "real_repeat_sum": 0, "sim_repeat_sum": 0,
            "real_dense4_sum": 0, "sim_dense4_sum": 0,
            "real_any_dense4": 0, "sim_any_dense4": 0,
        }

    @staticmethod
    def _sosia_sample():
        # secrets.SystemRandom usa il generatore casuale del sistema operativo.
        # L'estrazione e' uniforme senza reinserimento; nessuna quota di numeri
        # frequenti, ritardatari, ripetuti o di una particolare decina e' forzata.
        return sorted(SOSIA_RANDOM.sample(range(1, 91), 20))

    @staticmethod
    def _sosia_dense4_count(nums):
        # Decine convenzionali 10-19,...,80-89: include esattamente 50-59.
        # 1-9 e 90 sono esclusi da QUESTO specifico diagnostico, non dal gioco.
        return sum(sum(10*d <= int(n) <= 10*d+9 for n in nums) >= 4 for d in range(1, 9))

    @staticmethod
    def _sosia_valid20(nums):
        return (isinstance(nums, list) and len(nums) == 20 and
                all(type(n) is int and 1 <= n <= 90 for n in nums) and
                len(set(nums)) == 20)

    def _sosia_arm(self, current_key, current_nums):
        if not SOSIA_ENABLED:
            self.sosia_pending = None
            return
        self.sosia_pending = {
            "from_key": str(current_key),
            "real_previous": sorted(current_nums),
            "simulation_previous": (
                list(self.sosia_records[-1]["simulation"])
                if self.sosia_records and self.sosia_records[-1].get("key") == current_key
                else None
            ),
            "simulation_next": self._sosia_sample(),
        }

    def _sosia_settle(self, day, e, nums):
        if not SOSIA_ENABLED:
            return
        pending = self.sosia_pending
        if pending is None:
            return
        self.sosia_pending = None
        if not sim_draw_is_consecutive(pending.get("from_key"), day, e):
            self.sosia_totals["skipped_gaps"] += 1
            return
        simulated = pending.get("simulation_next")
        before_real = pending.get("real_previous")
        before_sim = pending.get("simulation_previous")
        if not self._sosia_valid20(simulated) or not self._sosia_valid20(before_real):
            self.sosia_totals["skipped_gaps"] += 1
            return
        real_set, sim_set = set(nums), set(simulated)
        n_overlap = len(real_set & sim_set)
        real_rep = len(real_set & set(before_real))
        sim_rep = len(sim_set & set(before_sim)) if self._sosia_valid20(before_sim) else None
        real_dense = self._sosia_dense4_count(nums)
        sim_dense = self._sosia_dense4_count(simulated)
        rec = {
            "key": draw_key(day, e), "source_key": pending.get("from_key"),
            "real": sorted(nums), "simulation": list(simulated),
            "overlap": n_overlap, "real_repeat": real_rep,
            "simulation_repeat": sim_rep, "real_dense4": real_dense,
            "simulation_dense4": sim_dense,
        }
        self.sosia_records.append(rec)
        self.sosia_records = self.sosia_records[-SOSIA_RECORD_MAX:]
        totals = self.sosia_totals
        totals["evaluated"] += 1
        totals["overlap_sum"] += n_overlap
        totals["real_repeat_sum"] += real_rep
        if sim_rep is not None:
            totals["sim_repeat_sum"] += sim_rep
            totals["sim_repeat_count"] += 1
        totals["real_dense4_sum"] += real_dense
        totals["sim_dense4_sum"] += sim_dense
        totals["real_any_dense4"] += int(real_dense > 0)
        totals["sim_any_dense4"] += int(sim_dense > 0)

    def sosia_text(self):
        rows = list(self.sosia_records)
        totals = self.sosia_totals
        n = int(totals["evaluated"])
        lines = [
            "🎲 10eLOTTO — GENERATORE SOSIA 20/90 (SHADOW)",
            "20 numeri distinti fra 1 e 90, scelti uniformemente, senza reinserimento.",
            "La simulazione viene congelata PRIMA dell'estrazione reale successiva.",
            "Non modifica ENGINE, HIGH CONFIDENCE, PLAY o AMBO.",
            "",
            f"📊 ESTRAZIONI CONFRONTATE: {n} | salti non valutati: {totals['skipped_gaps']}",
            f"• coincidenze reali/sosia nello stesso draw: "
            f"{totals['overlap_sum']/n:.2f} su 20 in media" if n else "• coincidenze: in attesa dei primi confronti",
            "• riferimento uniforme: 4.44 numeri comuni su 20",
        ]
        if n:
            recent = rows[-100:]
            # Il primo draw del sosia non ha una simulazione precedente.
            recent_sim_reps = [r['simulation_repeat'] for r in recent if r['simulation_repeat'] is not None]
            lines += [
                f"• ripetizioni reali / sosia fra draw consecutivi: "
                f"{totals['real_repeat_sum']/n:.2f} / "
                f"{totals['sim_repeat_sum']/totals['sim_repeat_count']:.2f}" if totals['sim_repeat_count'] else
                f"• ripetizioni reali: {totals['real_repeat_sum']/n:.2f}; sosia in avvio",
                f"• decine 10-19,...,80-89 con almeno 4 numeri per draw: "
                f"reale {totals['real_dense4_sum']/n:.2f} / "
                f"sosia {totals['sim_dense4_sum']/n:.2f}",
                f"• almeno una decina con 4+ numeri: "
                f"reale {safe_pct(totals['real_any_dense4'], n):.1f}% / "
                f"sosia {safe_pct(totals['sim_any_dense4'], n):.1f}%",
                "",
                f"📈 ULTIMI {len(recent)} CONFRONTI",
                f"• numeri comuni: {sum(r['overlap'] for r in recent)/len(recent):.2f} / 20",
                f"• ripetizioni reali: {sum(r['real_repeat'] for r in recent)/len(recent):.2f} "
                + (f"| sosia: {sum(recent_sim_reps)/len(recent_sim_reps):.2f}" if recent_sim_reps else ""),
            ]
            last = rows[-1]
            lines += [
                "",
                f"🧾 ULTIMO CONFRONTO {last['key']}",
                f"• reale: {' '.join(f'{v:02d}' for v in last['real'])}",
                f"• sosia: {' '.join(f'{v:02d}' for v in last['simulation'])}",
                f"• numeri comuni: {last['overlap']}/20",
            ]
        pending = self.sosia_pending
        if pending:
            lines += ["", f"🎯 SOSIA GIA' GENERATO dopo {pending['from_key']} "
                      "per la prossima estrazione:",
                      " ".join(f"{v:02d}" for v in pending['simulation_next'])]
        else:
            lines += ["", "🎯 Prossimo campione: in attesa della prossima estrazione elaborata."]
        lines += ["", "⚠️ SOSIA STATISTICO, NON una previsione dei numeri vincenti. "
                  "Nessuna puntata o modifica del motore predittivo."]
        return "\n".join(lines)

    def load_state(self):
        path = STATE_FILE if os.path.exists(STATE_FILE) else (LEGACY_STATE_FILE if os.path.exists(LEGACY_STATE_FILE) else None)
        if not path:
            self.state_load_info["reason"] = "nessuno state presente"
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)

            found_engine_version = int(d.get("engine_model_version", 0) or 0)
            if found_engine_version != ENGINE_MODEL_VERSION:
                self.state_load_info["reason"] = f"ENGINE version mismatch: {found_engine_version}"
                return False

            self.processed = [str(x) for x in (d.get("processed", []) or [])][-PROCESSED_MAX:]
            self.processed_set = set(self.processed)
            self.last_draw_key = d.get("last_draw_key")

            self.engine_model_version = ENGINE_MODEL_VERSION
            self.engine_history = self._sanitize_engine_history(d.get("engine_history", []))
            self.engine_pending = self._sanitize_engine_pending(d.get("engine_pending"))
            self.engine_margin_history = [
                float(x) for x in (d.get("engine_margin_history", []) or [])
                if isinstance(x, (int, float)) and math.isfinite(float(x))
            ][-ENGINE_MARGIN_LOOKBACK:]
            self.engine_recent_events = list(d.get("engine_recent_events", []) or [])[-ENGINE_RECENT_MAX:]
            self._merge_engine_stats(self.engine_stats_warmup, d.get("engine_stats_warmup", {}))
            self._merge_engine_stats(self.engine_stats_live, d.get("engine_stats_live", {}))
            self.engine_bootstrap_done = bool(d.get("engine_bootstrap_done", False)) or len(self.engine_history) >= ENGINE_MIN_HISTORY

            self.engine_multi_diag_version = ENGINE_MULTI_DIAG_VERSION
            self.engine_h5_sessions = self._sanitize_h5_sessions(d.get("engine_h5_sessions", []))
            self.engine_h5_records_warmup = self._sanitize_h5_records(d.get("engine_h5_records_warmup", []))
            self.engine_h5_records_live = self._sanitize_h5_records(d.get("engine_h5_records_live", []))
            self._migrate_h5_from_legacy_horizon(d)

            self.engine_play_diag_version = ENGINE_PLAY_DIAG_VERSION
            self.engine_play_sessions = self._sanitize_play_sessions(d.get("engine_play_sessions", []))
            self.engine_play_records_warmup = self._sanitize_play_records(d.get("engine_play_records_warmup", []))
            self.engine_play_records_live = self._sanitize_play_records(d.get("engine_play_records_live", []))
            self._migrate_play_from_h5()

            # Lo storico ENGINE/MULTI-HIT/PLAY esistente NON viene azzerato.
            # L'AMBO parte da zero: manca il partner/ranking H2 nei vecchi record.
            self._ambo_load_fields(d)

            # SOSIA v1: se il vecchio state non contiene questi campi, parte
            # prospetticamente, senza alterare lo storico degli altri moduli.
            totals = d.get("sosia_totals")
            if isinstance(totals, dict):
                for field in self.sosia_totals:
                    try:
                        self.sosia_totals[field] = max(0, int(totals.get(field, 0)))
                    except (ValueError, TypeError):
                        pass
            recs = d.get("sosia_records", [])
            if isinstance(recs, list):
                self.sosia_records = [r for r in recs if isinstance(r, dict) and
                                      self._sosia_valid20(r.get("real")) and
                                      self._sosia_valid20(r.get("simulation"))][-SOSIA_RECORD_MAX:]
            pending = d.get("sosia_pending")
            if (isinstance(pending, dict) and pending.get("from_key") and
                self._sosia_valid20(pending.get("real_previous")) and
                self._sosia_valid20(pending.get("simulation_next"))):
                self.sosia_pending = pending

            prior = self._sosiap_valid_pretrain(d.get("sosiap_pretrain"))
            if prior:
                self.sosiap_pretrain = prior

            if d.get("sosiap_version") == SOSIA_PRED_VERSION:
                raw = d.get("sosiap_learning", {})
                if isinstance(raw, dict):
                    for name in SOSIA_PRED_NAMES:
                        source = raw.get(name)
                        if not isinstance(source, dict):
                            continue
                        try:
                            n = max(0, int(source.get("n", 0)))
                            self.sosiap_learning[name] = {
                                "n": n, "hits": max(0, int(source.get("hits", 0))),
                                "ema_hits": max(0.0, min(20.0, float(source.get("ema_hits", 400/90))))}
                        except (TypeError, ValueError):
                            pass
                totals = d.get("sosiap_totals", {})
                if isinstance(totals, dict):
                    for k in self.sosiap_totals:
                        try:
                            self.sosiap_totals[k] = max(0, int(totals.get(k, 0)))
                        except (TypeError, ValueError):
                            pass
                records = d.get("sosiap_records", [])
                if isinstance(records, list):
                    self.sosiap_records = [r for r in records if isinstance(r, dict)
                                           and self._sosia_valid20(r.get("prediction"))
                                           and self._sosia_valid20(r.get("real"))][-SOSIA_PRED_RECORD_MAX:]
                p = d.get("sosiap_pending")
                if (isinstance(p, dict) and p.get("from_key") and
                    self._sosia_valid20(p.get("prediction")) and
                    self._sosia_valid20(p.get("previous")) and
                    isinstance(p.get("experts"), dict) and
                    all(self._sosia_valid20(p["experts"].get(n)) for n in SOSIA_PRED_NAMES)):
                    self.sosiap_pending = p

            if d.get("sosiasniper_version") == SOSIA_SNIPER_VERSION:
                totals = d.get("sosiasniper_totals", {})
                if isinstance(totals, dict):
                    for k in self.sosiasniper_totals:
                        try:
                            self.sosiasniper_totals[k] = max(0, int(totals.get(k, 0)))
                        except (TypeError, ValueError):
                            pass
                recs = d.get("sosiasniper_records", [])
                if isinstance(recs, list):
                    self.sosiasniper_records = [r for r in recs if isinstance(r, dict)
                                                and r.get("top1") and r.get("top2")][-SOSIA_SNIPER_RECORD_MAX:]
                sp = d.get("sosiasniper_pending")
                if isinstance(sp, dict) and sp.get("from_key") and sp.get("top1") and sp.get("top2"):
                    self.sosiasniper_pending = sp

            if d.get("sosiapattern_version") == SOSIA_PATTERN_VERSION:
                saved = d.get("sosiapattern_records", [])
                if isinstance(saved, list):
                    self.sosiapattern_records = [r for r in saved if isinstance(r, dict)
                        and self._sosia_valid20(r.get("rank20"))
                        and isinstance(r.get("hit_ranks"), list)
                        and isinstance(r.get("key"), str)]
                self.sosiapattern_skipped = max(0, int(d.get("sosiapattern_skipped", 0) or 0))
                pt = d.get("sosiapattern_pending")
                if isinstance(pt, dict) and pt.get("from_key") and self._sosia_valid20(pt.get("rank20")):
                    self.sosiapattern_pending = pt

            if d.get("sosiapatternlab_version") == SOSIA_PATTERN_LAB_VERSION:
                totals = d.get("sosiapatternlab_totals", {})
                if isinstance(totals, dict):
                    for k in self.sosiapatternlab_totals:
                        try:
                            self.sosiapatternlab_totals[k] = max(0, int(totals.get(k, 0) or 0))
                        except (TypeError, ValueError):
                            pass
                lr = d.get("sosiapatternlab_records", [])
                if isinstance(lr, list):
                    self.sosiapatternlab_records = [r for r in lr if isinstance(r, dict)
                        and isinstance(r.get("key"), str) and r.get("position_pick")][-SOSIA_SNIPER_RECORD_MAX:]
                lp = d.get("sosiapatternlab_pending")
                if isinstance(lp, dict) and lp.get("from_key") and lp.get("position_pick"):
                    self.sosiapatternlab_pending = lp

            self.dual.load(d.get("dual_target_v1"))
            self.decina.load(d.get("dual_decina_v1"))
            self.flow.load(d.get("decina_flow_v1"))
            self.burst.load(d.get("decina_burst_v2") or d.get("decina_burst_v1"))
            self.postburst.load(d.get("decina_postburst_v1"))
            self.post6.load(d.get("decina_post6_v1"))
            self.verifica.load(d.get("verification_v1"))
            self.convergence.load(d.get("convergence_v1"))
            self.hc_method.load(d.get("hc_convergence_v1"))
            self.forced_one.load(d.get("forced_one_v1"))
            self.triplette.load(d.get("triplette_coocc_v1"))
            self.focus_legacy_state = d.get("focus_r14_trans40_v1") if isinstance(d.get("focus_r14_trans40_v1"), dict) else None
            self.focus.load(d.get("focus_fast_v2"))
            self.incrocio.load(d.get("incrocio_focus_v1"))
            self.core_sync.load(d.get("focus_core_sync20_v1"))
            self.multichannel_bf12_legacy_state = d.get("multichannel_bf12_v1") if isinstance(d.get("multichannel_bf12_v1"), dict) else self.multichannel_bf12_legacy_state
            self.multichannel.load(d.get("multichannel_bd12_ed12_o2f12_v1"))

            # v19: pending e sessioni legacy restano congelati esattamente come salvati.

            migrated = os.path.abspath(path) == os.path.abspath(LEGACY_STATE_FILE)
            self.state_load_info = {
                "loaded": True,
                "migrated_legacy": migrated,
                "reason": "OK",
                "saved_at": d.get("saved_at"),
                "path": path,
            }
            console_log(
                f"STATE ENGINE CARICATO | legacy={'SI' if migrated else 'NO'} | "
                f"history={len(self.engine_history)} | margins={len(self.engine_margin_history)} | "
                f"HC live={self.engine_stats_live.get('signals_evaluated',0)} | "
                f"H5 live={len(self.engine_h5_records_live)}"
            )
            return True
        except Exception as exc:
            self.state_load_info["reason"] = f"{type(exc).__name__}: {exc}"
            console_log(f"STATE ENGINE NON CARICATO | {self.state_load_info['reason']}")
            return False

    def save_state(self, git=False, force_git=False):
        data = {
            "state_version": STATE_VERSION,
            "saved_at": now_txt(),
            "processed": self.processed[-PROCESSED_MAX:],
            "last_draw_key": self.last_draw_key,
            "engine_model_version": ENGINE_MODEL_VERSION,
            "engine_bootstrap_done": self.engine_bootstrap_done,
            "engine_history": self.engine_history[-ENGINE_HISTORY_MAX:],
            "engine_pending": self.engine_pending,
            "engine_margin_history": self.engine_margin_history[-ENGINE_MARGIN_LOOKBACK:],
            "engine_recent_events": self.engine_recent_events[-ENGINE_RECENT_MAX:],
            "engine_stats_warmup": self.engine_stats_warmup,
            "engine_stats_live": self.engine_stats_live,
            "engine_multi_diag_version": ENGINE_MULTI_DIAG_VERSION,
            "engine_h5_sessions": self.engine_h5_sessions[-1000:],
            "engine_h5_records_warmup": self.engine_h5_records_warmup[-ENGINE_H5_RECORD_MAX:],
            "engine_h5_records_live": self.engine_h5_records_live[-ENGINE_H5_RECORD_MAX:],
            "engine_play_diag_version": ENGINE_PLAY_DIAG_VERSION,
            "engine_play_sessions": self.engine_play_sessions[-1000:],
            "engine_play_records_warmup": self.engine_play_records_warmup[-ENGINE_PLAY_RECORD_MAX:],
            "engine_play_records_live": self.engine_play_records_live[-ENGINE_PLAY_RECORD_MAX:],
            "ambo_sim_diag_version": AMBO_SIM_DIAG_VERSION,
            "ambo_h2_legacy": self.ambo_h2_legacy,
            "ambo_hot5_single_legacy": self.ambo_hot5_single_legacy,
            "ambo_sim_draw_index": self.ambo_sim_draw_index,
            "ambo_sim_last_candidate_index": self.ambo_sim_last_candidate_index,
            "ambo_sim_skipped_overlap": self.ambo_sim_skipped_overlap,
            "ambo_sim_sessions": self.ambo_sim_sessions,
            "ambo_sim_records_live": self.ambo_sim_records_live[-AMBO_SIM_RECORD_MAX:],
            "ambo_sim_bets_live": self.ambo_sim_bets_live[-AMBO_SIM_BET_LOG_MAX:],
            "ambo_sim_account": self.ambo_sim_account,
            "sosia_version": SOSIA_VERSION,
            "sosia_pending": self.sosia_pending,
            "sosia_records": self.sosia_records[-SOSIA_RECORD_MAX:],
            "sosia_totals": self.sosia_totals,
            "sosiap_version": SOSIA_PRED_VERSION,
            "sosiap_pending": self.sosiap_pending,
            "sosiap_records": self.sosiap_records[-SOSIA_PRED_RECORD_MAX:],
            "sosiap_learning": self.sosiap_learning,
            "sosiap_totals": self.sosiap_totals,
            "sosiap_pretrain": self.sosiap_pretrain,
            "sosiasniper_version": SOSIA_SNIPER_VERSION,
            "sosiasniper_pending": self.sosiasniper_pending,
            "sosiasniper_records": self.sosiasniper_records[-SOSIA_SNIPER_RECORD_MAX:],
            "sosiasniper_totals": self.sosiasniper_totals,
            "sosiapattern_version": SOSIA_PATTERN_VERSION,
            "sosiapattern_pending": self.sosiapattern_pending,
            "sosiapattern_records": self.sosiapattern_records,
            "sosiapattern_skipped": self.sosiapattern_skipped,
            "sosiapatternlab_version": SOSIA_PATTERN_LAB_VERSION,
            "sosiapatternlab_pending": self.sosiapatternlab_pending,
            "sosiapatternlab_records": self.sosiapatternlab_records[-SOSIA_SNIPER_RECORD_MAX:],
            "sosiapatternlab_totals": self.sosiapatternlab_totals,
            "dual_target_v1": self.dual.dump(),
            "dual_decina_v1": self.decina.dump(),
            "decina_flow_v1": self.flow.dump(),
            "decina_burst_v2": self.burst.dump(),
            "decina_postburst_v1": self.postburst.dump(),
            "decina_post6_v1": self.post6.dump(),
            "verification_v1": self.verifica.dump(),
            "convergence_v1": self.convergence.dump(),
            "hc_convergence_v1": self.hc_method.dump(),
            "forced_one_v1": self.forced_one.dump(),
            "triplette_coocc_v1": self.triplette.dump(),
            "focus_r14_trans40_v1": self.focus_legacy_state,
            "focus_fast_v2": self.focus.dump(),
            "incrocio_focus_v1": self.incrocio.dump(),
            "focus_core_sync20_v1": self.core_sync.dump(),
            "multichannel_bf12_v1": self.multichannel_bf12_legacy_state,
            "multichannel_bd12_ed12_o2f12_v1": self.multichannel.dump(),
        }
        atomic_write_json(STATE_FILE, data)
        if git:
            self.last_git_status = git_commit_state_if_needed(force=force_git)
            return self.last_git_status
        return _git_status(True, "local-only", "state scritto localmente")

    def already_processed(self, day, e):
        return draw_key(day, e) in self.processed_set

    def remember_processed(self, day, e):
        k = draw_key(day, e)
        if k not in self.processed_set:
            self.processed.append(k)
            self.processed = self.processed[-PROCESSED_MAX:]
            self.processed_set = set(self.processed)
        self.last_draw_key = k
        return k

    async def tg(self, app, text):
        if not app or not CHAT_ID:
            print(text)
            return
        try:
            await app.bot.send_message(chat_id=CHAT_ID, text=text)
        except Exception as exc:
            console_log(f"⚠️ Telegram: {exc}")

    def _engine_stats(self, mode):
        return self.engine_stats_warmup if mode == "warmup" else self.engine_stats_live

    def _h5_bank(self, mode):
        return self.engine_h5_records_warmup if mode == "warmup" else self.engine_h5_records_live

    def _start_h5_session(self, pending):
        if not pending or not pending.get("accepted"):
            return False
        key = str(pending.get("signal_from_key") or "")
        origin = pending.get("origin_mode") if pending.get("origin_mode") in {"warmup", "live"} else "live"
        if any(str(x.get("signal_from_key") or "") == key and x.get("origin_mode") == origin for x in self.engine_h5_sessions):
            return False
        if any(str(x.get("signal_from_key") or "") == key and x.get("origin_mode") == origin
               for x in (self.engine_h5_records_warmup + self.engine_h5_records_live)):
            return False
        conf = float(pending.get("confidence", 0.0) or 0.0)
        thr = pending.get("threshold")
        try:
            thr_f = float(thr) if thr is not None else None
        except Exception:
            thr_f = None
        ratio = (conf / thr_f) if thr_f and thr_f > 0 else None
        self.engine_h5_sessions.append({
            "signal_from_key": key,
            "created_at": pending.get("created_at"),
            "origin_mode": origin,
            "top1": int(pending["top1"]),
            "support": int(pending.get("support", 0) or 0),
            "confidence": conf,
            "threshold": thr_f,
            "confidence_ratio": ratio,
            "age": 0,
            "hit_ages": [],
        })
        self.engine_h5_sessions = self.engine_h5_sessions[-1000:]
        return True

    async def settle_h5_sessions(self, app, day, e, nums, mode="live", notify=True):
        if not self.engine_h5_sessions:
            return []
        actual = set(map(int, nums))
        result_key = draw_key(day, e)
        kept, completed = [], []
        for sess in self.engine_h5_sessions:
            age = int(sess.get("age", 0) or 0) + 1
            sess["age"] = age
            if int(sess["top1"]) in actual and age not in sess["hit_ages"]:
                sess["hit_ages"].append(age)
            if age >= 5:
                origin = sess.get("origin_mode") if sess.get("origin_mode") in {"warmup", "live"} else mode
                hits = sorted(sess.get("hit_ages", []))
                rec = {
                    "signal_from_key": sess.get("signal_from_key"),
                    "completed_at": result_key,
                    "origin_mode": origin,
                    "top1": int(sess["top1"]),
                    "support": int(sess.get("support", 0) or 0),
                    "confidence": sess.get("confidence"),
                    "threshold": sess.get("threshold"),
                    "confidence_ratio": sess.get("confidence_ratio"),
                    "hit_ages": hits,
                    "hits5": len(hits),
                }
                bank = self._h5_bank(origin)
                bank.append(rec)
                del bank[:-ENGINE_H5_RECORD_MAX]
                completed.append(rec)

                if notify and mode == "live" and origin == "live" and ENGINE_NOTIFY_H5_RESULT:
                    label = "🎯 ESATTO 2/5" if len(hits) == 2 else ("🔥 3+/5" if len(hits) >= 3 else "—")
                    ages_txt = ", ".join(f"H{x}" for x in hits) if hits else "-"
                    await self.tg(
                        app,
                        "🧪 ENGINE ONLY — MULTI-HIT H5 CHIUSO\n\n"
                        f"Segnale: {sess.get('signal_from_key','-')}\n"
                        f"TOP1 congelato: #{sess['top1']}\n"
                        f"Uscite nelle 5 successive: {len(hits)}/5 | {label}\n"
                        f"Colpi HIT: {ages_txt}\n\n"
                        f"Forward H5 completati: {len(self.engine_h5_records_live)}\n"
                        f"Dettagli: /multih5"
                    )
            else:
                kept.append(sess)
        self.engine_h5_sessions = kept
        return completed

    def engine_append_history(self, current_key, nums):
        self.engine_history.append({"key": str(current_key), "nums": sorted(set(map(int, nums)))})
        self.engine_history = self.engine_history[-ENGINE_HISTORY_MAX:]
        self.engine_bootstrap_done = len(self.engine_history) >= ENGINE_MIN_HISTORY

    @staticmethod
    def _engine_standardize(score_map):
        vals = [float(score_map.get(n, 0.0)) for n in range(1, 91)]
        mu = sum(vals) / len(vals)
        var = sum((x - mu) ** 2 for x in vals) / len(vals)
        sd = math.sqrt(var)
        if sd <= 1e-12:
            return {n: 0.0 for n in range(1, 91)}
        return {n: (float(score_map.get(n, 0.0)) - mu) / sd for n in range(1, 91)}

    @staticmethod
    def _engine_quantile(values, q):
        vals = sorted(float(x) for x in values if isinstance(x, (int, float)) and math.isfinite(float(x)))
        if not vals:
            return None
        q = max(0.0, min(1.0, float(q)))
        if len(vals) == 1:
            return vals[0]
        pos = q * (len(vals) - 1)
        lo = int(math.floor(pos)); hi = int(math.ceil(pos))
        if lo == hi:
            return vals[lo]
        w = pos - lo
        return vals[lo] * (1.0 - w) + vals[hi] * w

    def _engine_frequency_scores(self):
        hist = self.engine_history
        p0 = 20.0 / 90.0
        windows = ((3, 1.00), (5, 1.15), (10, 1.00), (20, 0.80), (50, 0.50), (100, 0.30))
        raw = {n: 0.0 for n in range(1, 91)}
        rates = {}
        for w, weight in windows:
            if len(hist) < w:
                continue
            rows = hist[-w:]
            denom = math.sqrt(max(1e-9, w * p0 * (1.0 - p0)))
            for n in range(1, 91):
                c = sum(1 for row in rows if n in row["nums"])
                z = (c - w * p0) / denom
                raw[n] += weight * z
                rates[(n, w)] = c / float(w)
        if len(hist) >= 20:
            for n in range(1, 91):
                r5 = rates.get((n, 5), p0)
                r10 = rates.get((n, 10), p0)
                r20 = rates.get((n, 20), p0)
                raw[n] += 1.25 * (r5 - r20) + 0.75 * (r10 - r20)
        return raw

    def _engine_transition_scores(self):
        hist = self.engine_history
        out = {n: 0.0 for n in range(1, 91)}
        if len(hist) < 3:
            return out
        cur = set(hist[-1]["nums"])
        start = max(0, len(hist) - 1 - ENGINE_TRANSITION_LOOKBACK)
        den = {x: 0 for x in cur}
        num = {x: {n: 0 for n in range(1, 91)} for x in cur}
        for i in range(start, len(hist) - 1):
            a = set(hist[i]["nums"])
            b = hist[i + 1]["nums"]
            active = cur.intersection(a)
            if not active:
                continue
            for x in active:
                den[x] += 1
                nx = num[x]
                for n in b:
                    nx[n] += 1
        p0 = 20.0 / 90.0
        for n in range(1, 91):
            vals = []
            for x in cur:
                d = den[x]
                if d <= 0:
                    continue
                vals.append((num[x][n] + 8.0 * p0) / (d + 8.0) - p0)
            out[n] = (sum(vals) / len(vals)) if vals else 0.0
        return out

    def _engine_neighbor_scores(self):
        hist = self.engine_history
        out = {n: 0.0 for n in range(1, 91)}
        if len(hist) < 3:
            return out
        cur = set(hist[-1]["nums"])
        start = max(0, len(hist) - 1 - ENGINE_TRANSITION_LOOKBACK)
        total_w = 0.0
        for i in range(start, len(hist) - 1):
            a = set(hist[i]["nums"])
            sim = len(cur.intersection(a))
            w = 0.20 + max(0.0, sim - 3.0) ** 2
            total_w += w
            for n in hist[i + 1]["nums"]:
                out[n] += w
        if total_w > 0:
            p0 = 20.0 / 90.0
            for n in out:
                out[n] = out[n] / total_w - p0
        return out

    def _engine_gap_hazard_scores(self):
        hist = self.engine_history
        out = {n: 0.0 for n in range(1, 91)}
        if len(hist) < 20:
            return out
        start = max(0, len(hist) - 1 - ENGINE_TRANSITION_LOOKBACK)
        last_seen = {n: None for n in range(1, 91)}
        exp = {g: 0 for g in range(16)}
        hit = {g: 0 for g in range(16)}
        for i in range(len(hist) - 1):
            for n in hist[i]["nums"]:
                last_seen[n] = i
            if i < start:
                continue
            nxt = set(hist[i + 1]["nums"])
            for n in range(1, 91):
                ls = last_seen[n]
                g = 15 if ls is None else min(15, i - ls)
                exp[g] += 1
                if n in nxt:
                    hit[g] += 1
        p0 = 20.0 / 90.0
        hazard = {g: (hit[g] + 30.0 * p0) / (exp[g] + 30.0) for g in exp}
        current_last = {n: None for n in range(1, 91)}
        for i, row in enumerate(hist):
            for n in row["nums"]:
                current_last[n] = i
        i = len(hist) - 1
        for n in range(1, 91):
            ls = current_last[n]
            g = 15 if ls is None else min(15, i - ls)
            out[n] = hazard[g] - p0
        return out

    def engine_score_current(self):
        if len(self.engine_history) < ENGINE_MIN_HISTORY:
            return None
        components_raw = {
            "freq": self._engine_frequency_scores(),
            "transition": self._engine_transition_scores(),
            "neighbor": self._engine_neighbor_scores(),
            "gap": self._engine_gap_hazard_scores(),
        }
        components = {k: self._engine_standardize(v) for k, v in components_raw.items()}
        weights = {"freq": 0.35, "transition": 0.30, "neighbor": 0.20, "gap": 0.15}
        total = {n: sum(weights[k] * components[k][n] for k in weights) for n in range(1, 91)}
        ranked = sorted(range(1, 91), key=lambda n: (-total[n], n))
        top1, top2 = ranked[0], ranked[1]
        margin = float(total[top1] - total[top2])
        support = 0
        for sc in components.values():
            rk = sorted(range(1, 91), key=lambda n: (-sc[n], n))
            if top1 in rk[:5]:
                support += 1
        confidence = margin * (0.75 + 0.25 * (support / 4.0))
        return {
            "top1": int(top1),
            "top2_internal": int(top2),
            "score1": float(total[top1]),
            "score2": float(total[top2]),
            "margin": margin,
            "confidence": float(confidence),
            "support": int(support),
        }

    def engine_current_threshold(self):
        bank = self.engine_margin_history[-ENGINE_MARGIN_LOOKBACK:]
        if len(bank) < ENGINE_MIN_MARGIN_SAMPLES:
            return None
        return self._engine_quantile(bank, 1.0 - max(0.01, min(0.50, ENGINE_SELECT_RATE)))

    async def settle_engine_pending(self, app, day, e, nums, mode="live", notify=True):
        p = self.engine_pending
        if not p:
            return None
        self.engine_pending = None
        actual = set(map(int, nums))
        origin = p.get("origin_mode") if p.get("origin_mode") in {"warmup", "live"} else mode
        st = self._engine_stats(origin)
        st["evaluated"] += 1
        hit1 = int(p["top1"] in actual)
        st["all_top1_hits"] += hit1
        if p.get("accepted"):
            st["signals_evaluated"] += 1
            st["signal_top1_hits"] += hit1
            ev = {
                "signal_from_key": p.get("signal_from_key"),
                "result_key": draw_key(day, e),
                "top1": p["top1"],
                "top1_hit": bool(hit1),
                "confidence": p.get("confidence"),
                "threshold": p.get("threshold"),
                "support": p.get("support"),
                "origin_mode": origin,
            }
            self.engine_recent_events.append(ev)
            self.engine_recent_events = self.engine_recent_events[-ENGINE_RECENT_MAX:]
            if notify and mode == "live" and ENGINE_NOTIFY_H1_RESULT:
                await self.tg(
                    app,
                    "🧠 ENGINE ONLY — H1\n\n"
                    f"Segnale da: {p.get('signal_from_key','-')}\n"
                    f"Risultato: {draw_key(day,e)}\n"
                    f"TOP1 #{p['top1']}: {'✅ HIT' if hit1 else '❌ MISS'}\n\n"
                    f"Forward HC H1: {st['signal_top1_hits']}/{st['signals_evaluated']} "
                    f"({safe_pct(st['signal_top1_hits'], st['signals_evaluated']):.2f}%)\n"
                    "Il TOP1 resta comunque osservato fino a H5 per MULTI-HIT."
                )
        return {"top1_hit": bool(hit1), "accepted": bool(p.get("accepted"))}

    async def arm_engine_shadow(self, app, current_key, mode="live", notify=True):
        scored = self.engine_score_current()
        if not scored:
            self.engine_pending = None
            return None
        threshold = self.engine_current_threshold()
        accepted = bool(threshold is not None and scored["confidence"] >= threshold)
        st = self._engine_stats(mode)
        st["predictions"] += 1
        if accepted:
            st["signals"] += 1
        else:
            st["no_signal"] += 1

        p = {
            "signal_from_key": str(current_key),
            "created_at": now_txt(),
            "origin_mode": mode,
            "top1": int(scored["top1"]),
            "score1": round(float(scored["score1"]), 8),
            "score2": round(float(scored["score2"]), 8),
            "margin": round(float(scored["margin"]), 8),
            "confidence": round(float(scored["confidence"]), 8),
            "threshold": None if threshold is None else round(float(threshold), 8),
            "support": int(scored["support"]),
            "accepted": accepted,
        }
        self.engine_pending = p
        if accepted:
            self._start_h5_session(p)
            self._start_play_session(p)
            # Il modulo ambo e' puramente prospettico: NON creare segnali
            # dalle predizioni di warmup o da un catch-up non notificabile.
            if mode == "live" and notify:
                ambo_new = self._ambo_start_candidate(p)
                if ambo_new:
                    await self._ambo_notice(
                        app,
                        "👀 AMBO 2xHOT5 NO-LOCK — IN OSSERVAZIONE\n"
                        f"HIGH CONFIDENCE da {current_key} | TOP1 #{p['top1']}\n"
                        "NON giocare ora. Aspetto la PRIMA uscita del TOP1 entro H1-H3.\n"
                        "Nel draw di conferma scegliero' i DUE co-usciti piu' frequenti "
                        "nelle ultime 5 e riceverai due ambi per il colpo successivo.\n"
                        "NO-LOCK: altri HIGH CONFIDENCE possono aprire sessioni parallele.",
                        notify=notify
                    )

        # IMPORTANTISSIMO: prima si decide usando la soglia PRE-FUTURO, poi si aggiunge
        # la confidence corrente alla calibrazione. Nessun future leakage.
        self.engine_margin_history.append(float(scored["confidence"]))
        self.engine_margin_history = self.engine_margin_history[-ENGINE_MARGIN_LOOKBACK:]

        if accepted and notify and mode == "live" and ENGINE_NOTIFY_SIGNALS:
            await self.tg(
                app,
                "🔥 10eLOTTO ENGINE ONLY — HIGH CONFIDENCE\n\n"
                f"Segnale da: {current_key}\n"
                f"🎯 TOP1: {p['top1']}\n"
                f"Confidence: {p['confidence']:.4f} | soglia: {p['threshold']:.4f}\n"
                f"Consensus mini-engine: {p['support']}/4\n\n"
                "🧪 TRACKER: il TOP1 viene congelato e seguito per H1-H5.\n"
                "🎮 PLAY SHADOW: aspetta la PRIMA uscita entro H1-H3.\n"
                "Se confermato, dalla successiva cerca la SECONDA uscita entro H5 e poi STOP.\n"
                "⚠️ Nessuna puntata automatica."
            )
        return p

    async def rebuild_engine_from_records(self, records):
        self.engine_bootstrap_done = False
        self.engine_history = []
        self.engine_pending = None
        self.engine_margin_history = []
        self.engine_recent_events = []
        self.engine_stats_warmup = self._new_engine_stats()
        self.engine_stats_live = self._new_engine_stats()
        self.engine_h5_sessions = []
        self.engine_h5_records_warmup = []
        self.engine_h5_records_live = []
        self.engine_play_sessions = []
        self.engine_play_records_warmup = []
        self.engine_play_records_live = []
        # Il nuovo AMBO rimane prospettico anche in caso di rebuild del warmup:
        # nessun vecchio esito viene spacciato per una giocata notificata.
        usable = list(records or [])[-ENGINE_HISTORY_MAX:]
        for d, e, nums in usable:
            clean = list(map(int, nums))
            if len(clean) != 20 or len(set(clean)) != 20:
                continue
            await self.settle_play_sessions(None, d, e, clean, mode="warmup", notify=False)
            await self.settle_h5_sessions(None, d, e, clean, mode="warmup", notify=False)
            await self.settle_engine_pending(None, d, e, clean, mode="warmup", notify=False)
            k = draw_key(d, e)
            self.engine_append_history(k, clean)
            await self.arm_engine_shadow(None, k, mode="warmup", notify=False)

        self.engine_bootstrap_done = len(self.engine_history) >= ENGINE_MIN_HISTORY

        # L'ultima previsione del replay deve diventare prospettica LIVE.
        self.engine_pending = None
        if self.engine_bootstrap_done and self.engine_history:
            final_key = self.engine_history[-1]["key"]
            self.engine_h5_sessions = [
                x for x in self.engine_h5_sessions
                if not (x.get("origin_mode") == "warmup" and int(x.get("age",0) or 0) == 0
                        and str(x.get("signal_from_key") or "") == str(final_key))
            ]
            self.engine_play_sessions = [
                x for x in self.engine_play_sessions
                if not (x.get("origin_mode") == "warmup" and int(x.get("age",0) or 0) == 0
                        and str(x.get("signal_from_key") or "") == str(final_key))
            ]
            await self.arm_engine_shadow(None, final_key, mode="live", notify=False)
        return self.engine_bootstrap_done

    async def process_draw(self, app, day, e, nums, mode="live", notify=True, persist=True, sniper_notify=None):
        """v19 live loop: history + FOCUS FAST v2 + INCROCIO v1 + CORE SYNC20 v1.

        Tutti gli altri motori/tracker legacy restano congelati nello state.
        """
        clean=list(map(int,nums))
        if len(clean)!=20 or len(set(clean))!=20: return None
        if self.already_processed(day,e): return None

        if mode == "live":
            self.focus.ensure_start(self)
            self.incrocio.ensure_start(self); self.incrocio.seed_from_focus(self.focus)
            self.core_sync.ensure_start(self); self.core_sync.seed_from_focus(self.focus)

            # Prima aggiorna tutte le finestre H1..H5 gia' congelate.
            inc_events=self.incrocio.advance(day,e,clean)
            if INCROCIO_NOTIFY_RESULT and notify:
                for ev in inc_events:
                    msg=self.incrocio.result_text(ev)
                    if msg: await self.tg(app,msg)
            core_events=self.core_sync.advance(day,e,clean)
            if CORE_SYNC_NOTIFY_RESULT and notify:
                for ev in core_events:
                    msg=self.core_sync.result_text(ev)
                    if msg: await self.tg(app,msg)

            # Poi chiude l'H1 FOCUS del draw precedente.
            closed=self.focus.settle(day,e,clean)
            if FOCUS_NOTIFY_RESULT and notify:
                for row in closed:
                    msg=self.focus.result_text(row)
                    if msg: await self.tg(app,msg)

        current_key=self.remember_processed(day,e)
        self.engine_append_history(current_key,clean)

        if mode == "live" and notify:
            row=self.focus.arm(current_key,self)
            if FOCUS_NOTIFY and row:
                msg=self.focus.signal_text(row)
                if msg: await self.tg(app,msg)
            if row:
                inc=self.incrocio.observe_focus(row)
                if INCROCIO_NOTIFY and inc:
                    msg=self.incrocio.signal_text(inc)
                    if msg: await self.tg(app,msg)
                core=self.core_sync.observe_focus(row,self)
                if CORE_SYNC_NOTIFY and core:
                    msg=self.core_sync.signal_text(core)
                    if msg: await self.tg(app,msg)

        if persist:
            self.save_state(git=True)
        return current_key

    def _stats_line(label, st):
        ev = int(st.get("evaluated", 0) or 0)
        sig_ev = int(st.get("signals_evaluated", 0) or 0)
        return (
            f"• {label} tutte: TOP1 {st.get('all_top1_hits',0)}/{ev} "
            f"({safe_pct(st.get('all_top1_hits',0), ev):.2f}%)\n"
            f"• {label} HIGH CONFIDENCE: TOP1 {st.get('signal_top1_hits',0)}/{sig_ev} "
            f"({safe_pct(st.get('signal_top1_hits',0), sig_ev):.2f}%) | segnali creati={st.get('signals',0)}"
        )

    @staticmethod
    def _binom_prob(n, k, p):
        return math.comb(n, k) * (p ** k) * ((1.0-p) ** (n-k))

    @classmethod
    def _baseline_exact2_5(cls):
        p = 20.0/90.0
        return 100.0 * cls._binom_prob(5, 2, p)

    @classmethod
    def _baseline_ge2_5(cls):
        p = 20.0/90.0
        return 100.0 * (1.0 - cls._binom_prob(5,0,p) - cls._binom_prob(5,1,p))

    @classmethod
    def _baseline_ge3_5(cls):
        p = 20.0/90.0
        return 100.0 * sum(cls._binom_prob(5,k,p) for k in range(3,6))

    @classmethod
    def _baseline_h1miss_ge2_h2h5(cls):
        p = 20.0/90.0
        return 100.0 * (1.0 - cls._binom_prob(4,0,p) - cls._binom_prob(4,1,p))

    @classmethod
    def _baseline_h1hit_second_h2h5(cls):
        p = 20.0/90.0
        return 100.0 * (1.0 - (1.0-p)**4)

    @staticmethod
    def _summarize_h5(rows):
        n = len(rows)
        hist = {i: 0 for i in range(6)}
        for r in rows:
            h = max(0, min(5, int(r.get("hits5", len(r.get("hit_ages", []))) or 0)))
            hist[h] += 1
        exact2 = hist[2]
        ge2 = sum(hist[i] for i in range(2,6))
        ge3 = sum(hist[i] for i in range(3,6))
        return {"n":n, "hist":hist, "exact2":exact2, "ge2":ge2, "ge3":ge3}

    def _h5_summary_line(self, title, rows):
        s = self._summarize_h5(rows)
        n=s["n"]; h=s["hist"]
        return (
            f"• {title}: n={n} | 0/5 {h[0]} | 1/5 {h[1]} | ESATTO 2/5 {s['exact2']}/{n} "
            f"({safe_pct(s['exact2'],n):.2f}%) | >=2/5 {s['ge2']}/{n} ({safe_pct(s['ge2'],n):.2f}%) | "
            f">=3/5 {s['ge3']}/{n} ({safe_pct(s['ge3'],n):.2f}%)"
        )

    def multih5_text(self):
        rows = list(self.engine_h5_records_live)
        lines = [
            "🧪 10eLOTTO ENGINE ONLY — MULTI-HIT H5",
            "• SOLO HIGH CONFIDENCE",
            "• TOP1 congelato alla nascita e contato nelle 5 estrazioni successive",
            "",
            self._h5_summary_line("LIVE COMPLETO", rows),
            f"  baseline casuale: ESATTO 2/5 {self._baseline_exact2_5():.2f}% | "
            f">=2/5 {self._baseline_ge2_5():.2f}% | >=3/5 {self._baseline_ge3_5():.2f}%",
            "",
            "📈 ROLLING",
            self._h5_summary_line("ultimi 50", rows[-50:]),
            self._h5_summary_line("ultimi 100", rows[-100:]),
            "",
            "🧩 PER CONSENSUS",
        ]
        supports = sorted({int(r.get("support",0) or 0) for r in rows})
        if supports:
            for s in supports:
                rr=[r for r in rows if int(r.get("support",0) or 0)==s]
                lines.append(self._h5_summary_line(f"{s}/4", rr))
        else:
            lines.append("• nessun record")

        # Test condizionali emersi dal backtest.
        h1miss = [r for r in rows if 1 not in set(r.get("hit_ages", []))]
        miss_success = sum(sum(1 for a in r.get("hit_ages",[]) if 2 <= int(a) <= 5) >= 2 for r in h1miss)
        h1hit = [r for r in rows if 1 in set(r.get("hit_ages", []))]
        hit_second = sum(any(2 <= int(a) <= 5 for a in r.get("hit_ages",[])) for r in h1hit)

        lines.extend([
            "",
            "🔎 TEST CONDIZIONALI",
            f"• se H1 MISS: >=2 hit tra H2-H5 = {miss_success}/{len(h1miss)} "
            f"({safe_pct(miss_success,len(h1miss)):.2f}%) | rnd {self._baseline_h1miss_ge2_h2h5():.2f}%",
            f"• se H1 HIT: almeno un secondo hit H2-H5 = {hit_second}/{len(h1hit)} "
            f"({safe_pct(hit_second,len(h1hit)):.2f}%) | rnd {self._baseline_h1hit_second_h2h5():.2f}%",
            "",
            f"Sessioni H5 LIVE attive: {sum(1 for x in self.engine_h5_sessions if x.get('origin_mode')=='live')}",
            "⚠️ Diagnostica forward: non modifica score, soglia o segnali.",
        ])
        return "\n".join(lines)


    @staticmethod
    def _summarize_play(rows):
        activated = [r for r in rows if r.get("result") in {"hit", "stop"}]
        hits = [r for r in activated if r.get("result") == "hit"]
        stops = [r for r in activated if r.get("result") == "stop"]
        no_play = [r for r in rows if r.get("result") == "no_play"]
        bets = sum(int(r.get("bets", 0) or 0) for r in activated)
        return {
            "n": len(rows), "activated": len(activated), "hits": len(hits), "stops": len(stops),
            "no_play": len(no_play), "bets": bets,
            "hit_per_bet": safe_pct(len(hits), bets),
            "success": safe_pct(len(hits), len(activated)),
            "avg_bets": (bets / len(activated)) if activated else 0.0,
        }

    def _play_summary_line(self, title, rows):
        s = self._summarize_play(rows)
        return (
            f"• {title}: HC={s['n']} | attivate={s['activated']} | HIT {s['hits']}/{s['activated']} "
            f"({s['success']:.2f}%) | STOP={s['stops']} | NO PLAY={s['no_play']} | "
            f"puntate={s['bets']} | HIT/puntata {s['hits']}/{s['bets']} ({s['hit_per_bet']:.2f}%) | "
            f"media colpi={s['avg_bets']:.2f}"
        )

    def play_text(self):
        rows = list(self.engine_play_records_live)
        activated = [r for r in rows if r.get("result") in {"hit", "stop"}]
        lines = [
            "🎮 ENGINE ONLY — PLAY SHADOW SECONDA USCITA",
            "• HIGH CONFIDENCE -> congela TOP1",
            "• prima uscita valida SOLO a H1/H2/H3 = CONFERMA (non giocata)",
            "• dalla successiva: PLAY TOP1 fino a H5",
            "• seconda uscita = HIT + STOP; senza seconda uscita = STOP H5",
            "• prima uscita solo a H4/H5 = NO PLAY",
            "",
            self._play_summary_line("LIVE COMPLETO", rows),
            "  baseline singola puntata casuale: 22.22%",
            "",
            "📈 ROLLING SESSIONI ATTIVATE",
            self._play_summary_line("ultime 50 attivate", activated[-50:]),
            self._play_summary_line("ultime 100 attivate", activated[-100:]),
            "",
            "⏱ PER COLPO DI CONFERMA",
        ]
        for a in (1, 2, 3):
            rr = [r for r in activated if int(r.get("activation_age", 0) or 0) == a]
            max_tries = 5 - a
            theoretical = 100.0 * (1.0 - (70.0/90.0) ** max_tries)
            hit = sum(r.get("result") == "hit" for r in rr)
            lines.append(
                f"• conferma H{a}: HIT {hit}/{len(rr)} ({safe_pct(hit,len(rr)):.2f}%) | "
                f"rnd entro {max_tries} colpi {theoretical:.2f}%"
            )
        lines.append("")
        lines.append("🧩 PER CONSENSUS")
        supports = sorted({int(r.get("support",0) or 0) for r in activated})
        if supports:
            for sp in supports:
                rr=[r for r in activated if int(r.get("support",0) or 0)==sp]
                hit=sum(r.get("result")=="hit" for r in rr)
                bets=sum(int(r.get("bets",0) or 0) for r in rr)
                lines.append(
                    f"• {sp}/4: HIT {hit}/{len(rr)} ({safe_pct(hit,len(rr)):.2f}%) | "
                    f"HIT/puntata {hit}/{bets} ({safe_pct(hit,bets):.2f}%)"
                )
        else:
            lines.append("• nessuna sessione attivata")
        lines.extend(["", "📍 SESSIONI ATTUALI"])
        active = [x for x in self.engine_play_sessions if x.get("origin_mode") == "live"]
        if not active:
            lines.append("• nessuna")
        else:
            for x in active[-10:]:
                age=int(x.get("age",0) or 0); act=x.get("activation_age")
                if act is None:
                    state=f"ATTESA CONFERMA | H{age}/3"
                else:
                    state=f"PLAY ATTIVO | conferma H{act} | prossimo H{age+1}/5"
                lines.append(f"• {x.get('signal_from_key','-')} | #{x.get('top1')} | {state} | cons={x.get('support',0)}/4")
        lines.extend([
            "",
            "⚠️ PLAY SHADOW: diagnostica forward; nessuna puntata automatica.",
            "Lo storico MULTI-HIT originale resta separato e invariato.",
        ])
        return "\n".join(lines)

    def horizon_text(self):
        rows = list(self.engine_h5_records_live)
        lines = [
            "🧭 ENGINE ONLY — H1/H2/H3/H5",
            "• calcolato sui soli HIGH CONFIDENCE COMPLETATI a H5",
            "",
        ]
        for h in (1,2,3,5):
            n=len(rows)
            exact=sum(h in set(r.get("hit_ages",[])) for r in rows)
            cum=sum(any(int(a)<=h for a in r.get("hit_ages",[])) for r in rows)
            baseline=100.0*(1.0-(70.0/90.0)**h)
            lines.append(
                f"• H{h}: exact {exact}/{n} ({safe_pct(exact,n):.2f}%) | "
                f"entro H{h} {cum}/{n} ({safe_pct(cum,n):.2f}%) | baseline cum {baseline:.2f}%"
            )
        lines.append("\nDettaglio multi-hit: /multih5")
        return "\n".join(lines)

    def engine_text(self):
        p = self.engine_pending
        thr = self.engine_current_threshold()
        if p:
            if p.get("accepted"):
                current = (
                    f"🔥 HIGH CONFIDENCE | TOP1 {p['top1']} | conf={p['confidence']:.4f} | "
                    f"soglia={float(p.get('threshold') or 0):.4f} | consensus={p.get('support',0)}/4"
                )
            else:
                current = f"NO SIGNAL | TOP1 ranking={p['top1']} | conf={p['confidence']:.4f}"
        else:
            current = "nessuna previsione armata"

        recent=[x for x in self.engine_recent_events if x.get("origin_mode")=="live"][-10:]
        recent_txt="\n".join(
            f"• {x.get('result_key','-')}: #{x.get('top1')} {'HIT' if x.get('top1_hit') else 'MISS'} "
            f"| cons={x.get('support',0)}/4"
            for x in recent
        ) or "• -"

        return (
            "🧠 10eLOTTO ENGINE ONLY\n"
            "• UNICO motore attivo\n"
            "• frequenza/accelerazione + transizioni + vicini di stato + hazard gap\n"
            "• filtro HIGH CONFIDENCE dinamico; focus TOP1 + MULTI-HIT H5\n"
            "• PLAY SHADOW: prima uscita H1-H3 -> cerca la seconda entro H5\n\n"
            f"Storico: {len(self.engine_history)}/{ENGINE_MIN_HISTORY}+ | "
            f"calibrazione: {len(self.engine_margin_history)}/{ENGINE_MIN_MARGIN_SAMPLES}+\n"
            f"Filtro target: top {ENGINE_SELECT_RATE*100:.0f}% | soglia: "
            f"{'BUILD' if thr is None else f'{thr:.4f}'}\n"
            f"Prossima: {current}\n\n"
            "📊 FORWARD\n" + self._stats_line("LIVE", self.engine_stats_live) + "\n\n"
            "🕰️ WARMUP\n" + self._stats_line("WARMUP", self.engine_stats_warmup) + "\n\n"
            "🧾 ULTIMI HIGH CONFIDENCE\n" + recent_txt + "\n\n"
            f"🧪 H5 completati LIVE={len(self.engine_h5_records_live)} | attivi="
            f"{sum(1 for x in self.engine_h5_sessions if x.get('origin_mode')=='live')}\n"
            "Dettagli: /multih5 | /engineh | /play | /ambo | /sosia | /sosiasniper\n\n"
            "Baseline H1 TOP1 casuale: 22.22%.\n"
            "⚠️ Nessuna puntata automatica."
        )

    def verify_all_text(self):
        fx=self.focus.records
        n,h,c,r2,r3,r4,n4,w,l,t=self.focus._stats(fx)
        p=self.focus.pending[-1] if self.focus.pending else None
        rate=100.0*(n+len(self.focus.pending))/self.focus.scans if self.focus.scans else 0.0
        _,an,ah,pn,ph,sn,sah=self.incrocio._stats(self.incrocio.records)
        cr,cn,ch,con,coh,_=self.core_sync._stats(self.core_sync.records)
        lines=[
            "🧾 VERIFICA TUTTO v20.2 — FOCUS + INCROCIO + CORE + MULTI BD12+ED12+O2F12",
            "⏸️ Tutti gli altri metodi legacy sono PAUSATI e conservati nello state.",
            f"📡 Feed Base: {LIVE_FEED_LAST_SOURCE} | ultimo {LIVE_FEED_LAST_KEY} | Lottologia {LIVE_FEED_LAST_LOTTOLOGIA_KEY} | vecchia fonte {LIVE_FEED_LAST_PRIMARY_KEY}",
            "",
            "⚡ FOCUS FAST v2 — R13-18 / 3-4 candidati / TRANS80",
            f"Scan {self.focus.scans} | valutati {n} | NO SIGNAL {self.focus.no_signal} | frequenza segnali {rate:.1f}% | salti {self.focus.skipped}",
            f"H1 {h}/{n} ({safe_pct(h,n):.2f}%) | random {c}/{n} ({safe_pct(c,n):.2f}%) | baseline 22.22%",
            f"2° {r2}/{n} ({safe_pct(r2,n):.2f}%) | 3° {r3}/{n} ({safe_pct(r3,n):.2f}%)" + (f" | 4° {r4}/{n4} ({safe_pct(r4,n4):.2f}%)" if n4 else ""),
            f"Appaiato vs random +{w}/-{l}/={t}",
            f"progress {min(n,50)}/50 {min(n,100)}/100 {min(n,200)}/200 {min(n,300)}/300" + (f" | PENDING #{p.get('pick')}" if p else " | pending 0"),
            "",
            "🔗 INCROCIO FOCUS v1 — persistenza candidati H1-H5",
            f"FOCUS osservati {self.incrocio.focus_signals_seen} | segnali incrocio {self.incrocio.incrocio_signals} | pending {len(self.incrocio.pending)}",
            f"AMBATE H5 {ah}/{an} ({safe_pct(ah,an):.2f}%) | AMBI H5 {ph}/{pn} ({safe_pct(ph,pn):.2f}%) | origini con ambo {sah}/{sn}",
            "",
            "🧬 CORE SYNC20 v1 — SOLO FOCUS3 / PRIMA ×2 / observed>expected",
            f"FOCUS3 {self.core_sync.focus3_seen} | prime ×2 {self.core_sync.first_x2_pairs} | SYNC20 PASS {self.core_sync.sync_pass_pairs} | origini {self.core_sync.core_signals} | pending {len(self.core_sync.pending)}",
            f"AMBI CORE H5 {ch}/{cn} ({safe_pct(ch,cn):.2f}%) | origini con ambo {coh}/{con} ({safe_pct(coh,con):.2f}%) | baseline 21.57%",
            "",
            "🧪 MULTI BD12+ED12+O2F12 v1 — Base RIT12 ∩ Extra RIT12 ∩ Oro2 FREQ12",
            self.multichannel.text().split("\n", 4)[3] if len(self.multichannel.text().split("\n")) > 3 else self.multichannel.text(),
        ]
        return "\n".join(lines)

    def menu_text(self):
        return (
            "⚡ FOCUS + INCROCIO + CORE + MULTI BD12+ED12+O2F12 — v20.2 FEED FIX + BD12/ED12/O2F12\n\n"
            "METODI/TRACKER ATTIVI:\n"
            "1) FOCUS FAST v2: R13-18, 3-4 candidati, TRANS80 max, un numero H1.\n"
            "2) INCROCIO v1: tutti i candidati/coppie persistenti >=×2, monitor H1-H5.\n"
            "3) CORE SYNC20 v1: SOLO FOCUS con 3 candidati; coppia alla prima ×2; passa se nei 20 draw precedenti observed > expected; ambo H1-H5.\n"
            "4) MULTI BD12+ED12+O2F12 v1 TEST: Base ritardatari TOP12 ∩ Extra ritardatari TOP12 ∩ Oro2 frequenti TOP12; ambata/e Base H1-H5.\n\n"
            "/focus — stato FOCUS FAST\n"
            "/incrocio — stato INCROCIO generale\n"
            "/core — stato FOCUS CORE + SYNC20\n"
            "/multi — stato MULTI BD12+ED12+O2F12 live test\n"
            "/status — riepilogo FOCUS/INCROCIO/CORE/MULTI\n"
            "/verificatutto — audit compatto\n"
            "/menu — questa schermata\n\n"
            "⏸️ Tutti gli altri metodi restano in pausa; lo state storico non viene cancellato."
        )


# ============================================================
# TELEGRAM + STARTUP + LIVE
# ============================================================

async def reply(update, text):
    if update and update.message:
        await update.message.reply_text(text)

async def cmd_engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].engine_text())

async def cmd_engineh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].horizon_text())

async def cmd_multih5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].multih5_text())

async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].play_text())

async def cmd_ambo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].ambo_sim_text())

async def cmd_sosia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].sosiap_text())

async def cmd_sosiasniper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].sosiasniper_text())

async def cmd_sosiapattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].sosiapattern_text())

async def cmd_dual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.dual.text() + "\n\n" + engine.decina.short_text())

async def cmd_decine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].decina.text())

async def cmd_burst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].burst.text())

async def cmd_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].flow.text())

async def cmd_postburst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].postburst.text())

async def cmd_post6(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].post6.text())

async def cmd_convergenza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].convergence.text())

async def cmd_metodohc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].hc_method.text())

async def cmd_forcedone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].forced_one.text())

async def cmd_triplette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].triplette.text())

async def cmd_focus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].focus.text())

async def cmd_incrocio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].incrocio.text())

async def cmd_core(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].core_sync.text())

async def cmd_multi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].multichannel.text())

async def cmd_verificatutto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].verify_all_text())

async def cmd_verifica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.verifica.text(engine))

async def cmd_burstgate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.burstgate.text(engine))

async def cmd_sosiarandom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].sosia_text())

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    eng=context.application.bot_data["engine"]
    await reply(update, eng.verify_all_text())

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].menu_text())

async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("focus", "FOCUS FAST v2: un numero H1"),
        BotCommand("incrocio", "INCROCIO generale H1-H5"),
        BotCommand("core", "CORE SYNC20: primo x2, ambo H1-H5"),
        BotCommand("multi", "MULTI BD12+ED12+O2F12: BaseRit/ExtraRit/Oro2Freq"),
        BotCommand("status", "Riepilogo FOCUS + INCROCIO + CORE + MULTI"),
        BotCommand("verificatutto", "Audit dei 4 metodi attivi"),
        BotCommand("menu", "Comandi attivi"),
    ])

async def ensure_engine_ready(engine):
    """v19: serve uno storico consecutivo per gap + TRANS80 + INCROCIO + SYNC20.

    Se lo state e' gia' pronto non tocca nulla. Su installazione nuova carica
    esclusivamente engine_history/processed, senza costruire segnali dei vecchi motori.
    """
    if len(engine.engine_history) >= ENGINE_MIN_HISTORY:
        engine.engine_bootstrap_done=True
        return {"ok":True,"already_done":True,"draws":len(engine.engine_history)}
    try:
        all_records,sources=fetch_warmup_records(WARMUP_DAYS)
        records,sources2,continuity=_select_latest_contiguous_warmup(all_records,sources)
        if continuity.get("problems"):
            return {"ok":False,"draws":len(records),"sources":sources2,
                    "reason":"; ".join(continuity["problems"][:5]),
                    "continuity_note":continuity.get("note")}
        records=sorted(records,key=lambda x:(x[0],x[1]))
        if len(records)<ENGINE_MIN_HISTORY:
            return {"ok":False,"draws":len(records),"sources":sources2,
                    "reason":f"storico insufficiente: {len(records)}<{ENGINE_MIN_HISTORY}",
                    "continuity_note":continuity.get("note")}
        usable=records[-ENGINE_HISTORY_MAX:]
        engine.engine_history=[]
        for d,e,nums in usable:
            clean=sorted(set(map(int,nums)))
            if len(clean)==20:
                engine.engine_history.append({"key":draw_key(d,e),"nums":clean})
        engine.engine_bootstrap_done=len(engine.engine_history)>=ENGINE_MIN_HISTORY
        engine.processed=[draw_key(d,e) for d,e,_ in records][-PROCESSED_MAX:]
        engine.processed_set=set(engine.processed)
        if records: engine.last_draw_key=draw_key(records[-1][0],records[-1][1])
        return {"ok":bool(engine.engine_bootstrap_done),"already_done":False,
                "draws":len(engine.engine_history),"sources":sources2,
                "continuity_note":continuity.get("note"),
                "reason":None if engine.engine_bootstrap_done else "warmup FOCUS fallito"}
    except Exception as exc:
        return {"ok":False,"draws":0,"reason":f"{type(exc).__name__}: {exc}"}

async def notify_pending(engine, app):
    p=engine.engine_pending
    if not p or not p.get("accepted"):
        return
    await engine.tg(
        app,
        "🔥 ENGINE ONLY — HIGH CONFIDENCE GIA' ARMATO\n\n"
        f"Segnale da: {p.get('signal_from_key','-')}\n"
        f"🎯 TOP1: {p.get('top1')}\n"
        f"Confidence: {float(p.get('confidence',0)):.4f} | soglia: {float(p.get('threshold') or 0):.4f}\n"
        f"Consensus: {p.get('support',0)}/4\n\n"
        "Il TOP1 viene seguito fino a H5 per MULTI-HIT.\n"
        "PLAY SHADOW: prima uscita H1-H3 = conferma; dalla successiva cerca la seconda entro H5."
    )


async def notify_ambo_active(engine, app):
    """Al riavvio ricorda tutte le sessioni 2xHOT5 senza contabilizzare retroattivamente."""
    if not AMBO_SIM_ENABLED or not engine.ambo_sim_sessions:
        return
    lines = [
        '♻️ AMBO 2xHOT5 NO-LOCK — SESSIONI RECUPERATE DALLO STATE',
        f'Attive: {len(engine.ambo_sim_sessions)}',
    ]
    for s in engine.ambo_sim_sessions[-12:]:
        if s.get('phase') == 'play' and len(s.get('partners', [])) == 2:
            p1, p2 = s['partners']
            lines.append(
                f'• {s["signal_from_key"]}: {s["top1"]}-{p1} + {s["top1"]}-{p2} | '
                f'conf H{s.get("confirmation_age")} | prossima H{s["age"]+1} | '
                f'{sim_euro(AMBO_SIM_STAKE_CENTS)} x2'
            )
        else:
            lines.append(
                f'• {s["signal_from_key"]}: TOP1 {s["top1"]} | {s.get("phase")} | '
                f'prossimo H{s["age"]+1}; nessun ambo finché non arriva la conferma.'
            )
    if len(engine.ambo_sim_sessions) > 12:
        lines.append(f'• ... altre {len(engine.ambo_sim_sessions)-12} sessioni attive')
    lines.append('Non contabilizzo alcun colpo finché non arriva la relativa estrazione.')
    await engine._ambo_notice(app, '\n'.join(lines))


async def sync_multichannel(engine, app, notify=True, bootstrap_if_empty=False, days=1, prefetched_rows=None):
    """Sincronizza Lottologia MULTI senza poter bloccare il loop Base."""
    rows = list(prefetched_rows) if prefetched_rows is not None else fetch_multichannel_recent(days=days)
    if not rows:
        return {"rows":0,"unseen":0,"signal":None,"events":[]}
    mc = engine.multichannel
    events = []
    if bootstrap_if_empty and not mc.history:
        mc.bootstrap(rows)
        mc.ensure_start()
        sig = mc.arm()
        if sig and notify and MULTI_BD_ED_O2_NOTIFY:
            msg = mc.signal_text(sig)
            if msg: await engine.tg(app, msg)
        return {"rows":len(rows),"unseen":0,"signal":sig,"events":events,"bootstrapped":True}
    unseen = [r for r in rows if not mc.seen(r.get("key"))]
    unseen.sort(key=lambda r: _verifica_order(r.get("key")) or (-1,-1))
    for r in unseen:
        evs = mc.ingest(r)
        events.extend(evs)
        if notify and MULTI_BD_ED_O2_NOTIFY_RESULT:
            for ev in evs:
                msg = mc.result_text(ev)
                if msg: await engine.tg(app, msg)
    mc.ensure_start()
    sig = mc.arm() if mc.history else None
    if sig and notify and MULTI_BD_ED_O2_NOTIFY:
        msg = mc.signal_text(sig)
        if msg: await engine.tg(app, msg)
    return {"rows":len(rows),"unseen":len(unseen),"signal":sig,"events":events,"bootstrapped":False}

async def startup(engine, app, retry_state=None):
    retry_state = retry_state if isinstance(retry_state, dict) else {}
    ready = await ensure_engine_ready(engine)
    if not ready.get("ok"):
        reason=ready.get("reason","warmup non pronto")
        console_log(f"FOCUS WARMUP FAIL | {reason}")
        now_ts=time.time()
        if (reason != retry_state.get("last_reason") or now_ts-float(retry_state.get("last_tg_ts",0) or 0) >= WARMUP_FAIL_TG_MIN_SECONDS):
            await engine.tg(app,"⚠️ FOCUS FAST — WARMUP NON PRONTO\n\n"+f"Motivo: {reason}\nDraw raccolti: {ready.get('draws',0)}\nRiprovo tra {WARMUP_RETRY_SEC}s.")
            retry_state["last_reason"]=reason; retry_state["last_tg_ts"]=now_ts
        return False

    try:
        rows, _startup_multi_today, _startup_source = fetch_live_bundle_today()
        console_log(f"CATCH-UP feed={_startup_source} | latest={LIVE_FEED_LAST_KEY}")
    except Exception as exc:
        console_log(f"CATCH-UP parser fail | {exc}"); rows=[]
    unseen=[x for x in rows if not engine.already_processed(x[0],x[1])]
    unseen.sort(key=lambda x:(x[0],x[1]))
    for d,e,nums in unseen:
        await engine.process_draw(None,d,e,nums,mode="live",notify=False,persist=False)

    multi_sig=None
    try:
        mr = await sync_multichannel(engine, app, notify=False, bootstrap_if_empty=True, days=3)
        multi_sig = mr.get("signal")
    except Exception as exc:
        console_log(f"MULTI startup fail | {type(exc).__name__}: {exc}")

    engine.focus.ensure_start(engine)
    engine.incrocio.ensure_start(engine)
    engine.incrocio.seed_from_focus(engine.focus)
    engine.core_sync.ensure_start(engine)
    engine.core_sync.seed_from_focus(engine.focus)
    # Dopo il catch-up, l'ultimo draw e' noto ma la sua H1 non lo e' ancora:
    # possiamo congelare legittimamente il segnale v2 senza backfill.
    armed=None
    if rows and engine.engine_history:
        latest=max(rows,key=lambda r:(r[0],r[1]))
        latest_key=draw_key(latest[0],latest[1])
        if latest_key == engine.engine_history[-1]["key"]:
            armed=engine.focus.arm(latest_key,engine)
            if armed:
                inc_armed=engine.incrocio.observe_focus(armed)
                core_armed=engine.core_sync.observe_focus(armed,engine)
            else:
                inc_armed=None; core_armed=None
        else:
            inc_armed=None; core_armed=None
    else:
        inc_armed=None; core_armed=None
    engine.save_state(git=True,force_git=True)

    await engine.tg(app,
        "🚀 FOCUS + INCROCIO + CORE + MULTI BD12+ED12+O2F12 v20.2 AVVIATO\n\n"
        "⚡ FOCUS FAST v2: R13-18, 3-4 candidati, TRANS80 max, un numero H1.\n"
        "🔗 INCROCIO v1: persistenza generale candidati FOCUS, ambata + ambo H1-H5.\n"
        "🧬 CORE SYNC20 v1: SOLO FOCUS3, prima ×2, SYNC20 observed>expected, ambo H1-H5.\n"
        "🧪 MULTI BD12+ED12+O2F12 v1 TEST: Base RIT12 ∩ Extra RIT12 ∩ Oro2 FREQ12, H1-H5.\n"
        "📡 v20.2: feed Base automatico dalla sorgente piu aggiornata (Lottologia con fallback).\n\n"
        "⏸️ ENGINE predittivo, SOSIA, FORCED ONE, TRIPLETTE, HC, BURST, POST-6, PLAY, AMBO, DUAL e altri tracker: PAUSATI.\n"
        "✅ Il loro state storico resta conservato e non viene aggiornato.\n\n"
        "Comandi: /focus /incrocio /core /multi /status /verificatutto /menu"
    )
    if armed and FOCUS_NOTIFY:
        msg=engine.focus.signal_text(armed)
        if msg: await engine.tg(app,msg)
    if inc_armed and INCROCIO_NOTIFY:
        msg=engine.incrocio.signal_text(inc_armed)
        if msg: await engine.tg(app,msg)
    if core_armed and CORE_SYNC_NOTIFY:
        msg=engine.core_sync.signal_text(core_armed)
        if msg: await engine.tg(app,msg)
    if multi_sig and MULTI_BD_ED_O2_NOTIFY:
        msg=engine.multichannel.signal_text(multi_sig)
        if msg: await engine.tg(app,msg)
    return True

async def startup_until_ready(engine, app):
    retry={}
    while True:
        if await startup(engine,app,retry):
            return
        await asyncio.sleep(max(30,WARMUP_RETRY_SEC))

async def live_loop(engine, app):
    console_log(f"FOCUS + INCROCIO + CORE + MULTI LIVE | poll={LOOP_SEC}s | rotation={BOT_MAX_RUNTIME_SECONDS}s")
    started=time.monotonic()
    last_error=""
    last_error_ts=0.0
    while True:
        if BOT_MAX_RUNTIME_SECONDS > 0 and time.monotonic()-started >= BOT_MAX_RUNTIME_SECONDS:
            try:
                st=engine.save_state(git=True,force_git=True)
                console_log(f"ROTATION save | {st.get('action')} | {st.get('detail','')}")
            except Exception as exc:
                console_log(f"ROTATION save fail | {exc}")
            if BOT_ROTATION_NOTIFY:
                await engine.tg(app,"♻️ FOCUS + INCROCIO + CORE — ROTAZIONE RUNNER\nState salvato; avvio successivo automatico.")
            return "rotation"

        try:
            rows, live_multi_rows, live_source = fetch_live_bundle_today()
            unseen=[x for x in rows if not engine.already_processed(x[0],x[1])]
            unseen.sort(key=lambda x:(x[0],x[1]))
            if unseen:
                if len(unseen)==1:
                    d,e,nums=unseen[0]
                    await engine.process_draw(app,d,e,nums,mode="live",notify=True,persist=True)
                else:
                    # Catch-up: nessun backfill di segnali ormai conoscibili.
                    # Dopo aver incorporato tutti i draw, armiamo SOLO l'ultimo,
                    # la cui H1 e' ancora realmente futura.
                    for d,e,nums in unseen:
                        await engine.process_draw(app,d,e,nums,mode="live",notify=False,persist=False)
                    row=None; inc=None; core=None
                    if engine.engine_history:
                        row=engine.focus.arm(engine.engine_history[-1]["key"],engine)
                        if row:
                            inc=engine.incrocio.observe_focus(row)
                            core=engine.core_sync.observe_focus(row,engine)
                    engine.save_state(git=True,force_git=True)
                    if row and FOCUS_NOTIFY:
                        msg=engine.focus.signal_text(row)
                        if msg: await engine.tg(app,msg)
                    if inc and INCROCIO_NOTIFY:
                        msg=engine.incrocio.signal_text(inc)
                        if msg: await engine.tg(app,msg)
                    if core and CORE_SYNC_NOTIFY:
                        msg=engine.core_sync.signal_text(core)
                        if msg: await engine.tg(app,msg)
            try:
                mr = await sync_multichannel(engine, app, notify=True, bootstrap_if_empty=True, days=1, prefetched_rows=live_multi_rows)
                if mr.get("unseen") or mr.get("signal") or mr.get("events"):
                    engine.save_state(git=True)
            except Exception as mc_exc:
                console_log(f"MULTI LIVE ERROR | {type(mc_exc).__name__}: {mc_exc}")
            await asyncio.sleep(LOOP_SEC)
        except Exception as exc:
            txt=f"{type(exc).__name__}: {exc}"
            console_log(f"LOOP ERROR | {txt}")
            now=time.time()
            if txt!=last_error or now-last_error_ts>=900:
                await engine.tg(app,f"⚠️ FOCUS + INCROCIO + CORE — ERRORE\n{txt}\nRiprovo automaticamente.")
                last_error=txt; last_error_ts=now
            await asyncio.sleep(max(30,LOOP_SEC))

async def run_self_test():
    # FOCUS: 3 candidati, TRANS80 massimo.
    class DummyEngine: pass
    de=DummyEngine(); de.engine_history=[]
    for i in range(1,102):
        nums=[((i+j-2)%90)+1 for j in range(1,21)]
        de.engine_history.append({"key":f"2099-12-01#{i:03d}","nums":nums})
    fx=FocusFastV2(); fx.start_from_key='2099-12-01#100'; fx.started_at='2099-12-01T12:00:00+01:00'
    fx._gaps=lambda hist:{n:(13 if n==11 else 15 if n==22 else 18 if n==33 else 0) for n in range(1,91)}
    fx._transition_score=lambda hist,current,n:({11:0.21,22:0.31,33:0.25}[n],100,20)
    row1=fx.arm('2099-12-01#101',de)
    assert row1 and row1['pick']==22 and row1['candidate_count']==3

    # INCROCIO: primo segnale solo contesto, secondo con 22 e 33 ripetuti -> ambata + ambo.
    inc=IncrocioFocusV1(); inc.start_from_key='2099-12-01#100'; inc.seeded_context=True
    assert inc.observe_focus(row1) is None
    row2=dict(row1); row2['origin_key']='2099-12-01#102'; row2['ranked_candidates']=[
        {"num":22,"gap":16,"trans":0.34},{"num":33,"gap":18,"trans":0.28},{"num":44,"gap":13,"trans":0.19}]
    sig=inc.observe_focus(row2)
    assert sig and sig['top_ambata']==22 and sig['top_ambo']==[22,33]
    assert {x['num'] for x in sig['ambate']}=={22,33} and any(x['pair']==[22,33] for x in sig['ambi'])
    ev=inc.advance('2099-12-01',103,[22,33]+list(range(50,68)))
    assert ev and set(ev[0]['new_ambate'])=={22,33} and [22,33] in ev[0]['new_ambi'] and ev[0]['closed']
    rt=IncrocioFocusV1(); assert rt.load(inc.dump()) and len(rt.records)==1
    assert 'AMBO' in rt.text()

    # CORE SYNC20: FOCUS3, prima x2, relazione positiva nei 20 draw precedenti.
    ce=DummyEngine(); ce.engine_history=[]; ce.focus=type('F',(),{'records':[],'pending':[]})()
    for i in range(1,22):
        nums=list(range(50,68))
        if i <= 8: nums=[22,33]+list(range(50,68))
        ce.engine_history.append({'key':f'2099-12-03#{i:03d}','nums':nums[:20]})
    core=FocusCoreSync20V1(); core.start_from_key='2099-12-03#020'; core.seeded_context=True
    c1={'origin_key':'2099-12-03#020','ranked_candidates':[{'num':22,'gap':15,'trans':0.3},{'num':33,'gap':16,'trans':0.2},{'num':44,'gap':14,'trans':0.1}], 'candidate_count':3}
    core.signal_history=[core._candidate_snapshot(c1)]
    c2={'origin_key':'2099-12-03#021','ranked_candidates':[{'num':22,'gap':16,'trans':0.32},{'num':33,'gap':17,'trans':0.24},{'num':55,'gap':13,'trans':0.12}], 'candidate_count':3}
    sigc=core.observe_focus(c2,ce)
    assert sigc and any(x['pair']==[22,33] for x in sigc['pairs'])
    evc=core.advance('2099-12-03',22,[22,33]+list(range(60,78)))
    assert evc and [22,33] in evc[0]['new_pairs'] and evc[0]['closed']
    rtc=FocusCoreSync20V1(); assert rtc.load(core.dump()) and len(rtc.records)==1 and 'SYNC20' in rtc.text()

    # MULTI BD12+ED12+O2F12: intersezione e H1 prospettico, parser/state isolati.
    mc=MultiChannelBD12ED12O2F12V1()
    rows=[]
    # Costruisce 90 draw validi: 42 molto frequente Base/Oro e mai Extra negli ultimi draw.
    for i in range(1,91):
        base=[42] + [n for n in range(1,91) if n!=42][:19]
        # variazione sufficiente ma validita' strutturale garantita
        shift=(i-1)%69
        pool=[n for n in range(1,91) if n!=42]
        tail=[pool[(shift+j)%len(pool)] for j in range(19)]
        base=[42]+tail
        # Extra disgiunti dalla Base; evita 42 per creare ritardo.
        extra=[n for n in range(1,91) if n not in set(base) and n!=42][:15]
        rows.append({'key':f'2099-12-04#{i:03d}','day':'2099-12-04','draw_id':i,
                     'nums':base,'oro':base[1],'doppio_oro':42,'extra':extra})
    mc.bootstrap(rows); mc.ensure_start()
    # Forza rankings per test deterministico dell'intersezione/cooldown.
    mc._rankings=lambda:{'base_gap':{n:(30 if n==42 else 0) for n in range(1,91)},
                         'extra_gap':{n:(30 if n==42 else 0) for n in range(1,91)},
                         'o2_freq':{n:(40 if n==42 else 0) for n in range(1,91)},
                         'top_base_delay':[42]+list(range(1,12)),
                         'top_extra_delay':[42]+list(range(12,23)),
                         'top_o2':[42]+list(range(23,34))}
    ms=mc.arm(); assert ms and ms['numbers']==[42] and len(mc.pending)==1
    nxt={'key':'2099-12-04#091','day':'2099-12-04','draw_id':91,
         'nums':[42]+list(range(50,69)),'oro':50,'doppio_oro':42,
         'extra':list(range(1,16))}
    mev=mc.ingest(nxt); assert mev and mev[0]['hit_now'] and len(mc.records)==1
    n,h1,h3,h5=mc._stats(); assert (n,h1,h3,h5)==(1,1,1,1)
    mcrt=MultiChannelBD12ED12O2F12V1(); assert mcrt.load(mc.dump()) and len(mcrt.records)==1

    # Engine live v19: legacy congelati; FOCUS + INCROCIO + CORE possono avanzare.
    eng=EngineOnly(load=False); eng.engine_history=[]
    for i in range(1,102):
        nums=[((i+j-2)%90)+1 for j in range(1,21)]
        eng.engine_history.append({"key":f"2099-12-02#{i:03d}","nums":nums})
    eng.engine_bootstrap_done=True; eng.last_draw_key='2099-12-02#101'
    eng.processed=[f"2099-12-02#{i:03d}" for i in range(1,102)]; eng.processed_set=set(eng.processed)
    eng.focus.start_from_key='2099-12-02#101'; eng.incrocio.start_from_key='2099-12-02#101'; eng.incrocio.seeded_context=True; eng.core_sync.start_from_key='2099-12-02#101'; eng.core_sync.seeded_context=True
    eng.focus._gaps=lambda hist:{n:(13 if n==12 else 15 if n==24 else 18 if n==36 else 0) for n in range(1,91)}
    eng.focus._transition_score=lambda hist,current,n:({12:0.22,24:0.33,36:0.25}[n],100,20)
    async def _noop(*a,**k): return None
    eng.tg=_noop
    old=(len(eng.forced_one.records),len(eng.triplette.records),len(eng.hc_method.records),int(eng.burst.totals.get('evaluated',0)))
    await eng.process_draw(None,'2099-12-02',102,list(range(1,21)),mode='live',notify=True,persist=False)
    new=(len(eng.forced_one.records),len(eng.triplette.records),len(eng.hc_method.records),int(eng.burst.totals.get('evaluated',0)))
    assert old==new and len(eng.focus.pending)==1
    assert LEGACY_METHODS_PAUSED is True
    assert '/focus' in eng.menu_text() and '/incrocio' in eng.menu_text() and '/core' in eng.menu_text() and '/multi' in eng.menu_text() and '/forcedone' not in eng.menu_text()
    vt=eng.verify_all_text(); assert 'CORE SYNC20' in vt and 'FORCED ONE' not in vt and len(vt)<4096

    print('SELF-TEST OK: v20.2 = FOCUS/INCROCIO/CORE + MULTI BD12+ED12+O2F12 v1; BF12 legacy conservato.')

async def main():
    if "--self-test" in sys.argv:
        await run_self_test()
        return

    acquire_single_instance_lock()
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN mancante")
    if CHAT_ID is None:
        raise RuntimeError("CHAT_ID mancante/non valido")

    app=ApplicationBuilder().token(TOKEN).build()
    engine=EngineOnly(load=True)
    app.bot_data["engine"]=engine

    app.add_handler(CommandHandler("focus",cmd_focus))
    app.add_handler(CommandHandler("incrocio",cmd_incrocio))
    app.add_handler(CommandHandler("core",cmd_core))
    app.add_handler(CommandHandler("multi",cmd_multi))
    app.add_handler(CommandHandler("status",cmd_status))
    app.add_handler(CommandHandler("verificatutto",cmd_verificatutto))
    app.add_handler(CommandHandler("menu",cmd_menu))

    await app.initialize()
    await app.start()
    await setup_commands(app)
    await app.updater.start_polling(drop_pending_updates=True)
    try:
        await startup_until_ready(engine,app)
        await live_loop(engine,app)
    finally:
        try:
            engine.save_state(git=True,force_git=True)
        except Exception:
            pass
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
