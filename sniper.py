# ============================================================
# 🧠 10eLOTTO ENGINE ONLY — MULTI-HIT H5 + PLAY SHADOW + AMBO HOT5 H1-H3
# ============================================================
#
# UNICO MOTORE ATTIVO:
#   • surrogate multi-engine PRE-FUTURO:
#       frequenza/accelerazione + transizioni + vicini di stato + hazard gap
#   • HIGH CONFIDENCE = coda superiore dinamica dei margini recenti (default top 15%)
#   • UNICO NUMERO OSSERVATO = TOP1
#
# DIAGNOSTICA PRINCIPALE:
#   • H1/H2/H3/H5 sul TOP1 congelato alla nascita del segnale
#   • MULTI-HIT H5:
#       0/5, 1/5, ESATTO 2/5, 3+/5
#       >=2/5 e >=3/5
#   • rolling ultimi 50 / 100 HIGH CONFIDENCE completati
#   • split per consensus 1/4..4/4
#   • controllo H1 MISS -> >=2 hit tra H2-H5
#   • controllo H1 HIT -> almeno un secondo hit tra H2-H5
#
# RIMOSSI:
#   • CORE
#   • FAST
#   • FREQ
#   • TOP5/TOP10 ranking depth
#   • qualsiasi puntata automatica / progressione
#
# PLAY SHADOW AGGIUNTO:
#   • HC -> congela TOP1
#   • prima uscita valida solo H1-H3 = conferma (non giocata)
#   • dalla successiva si cerca la seconda uscita entro H5
#   • seconda uscita = HIT + STOP; se manca entro H5 = STOP
#   • se nessuna conferma entro H3 = NO PLAY
#
# AMBO HOT5 H1-H3 (modulo separato, simulazione con notifiche):
#   • solo HIGH CONFIDENCE prospettici, distanziati >=5 draw;
#   • attende la PRIMA uscita del TOP1 entro H1/H2/H3 = conferma;
#   • nel draw di conferma considera i 19 numeri usciti insieme al TOP1;
#   • sceglie fra questi il numero piu' frequente nelle ultime 5 estrazioni
#     (finestra inclusiva del draw di conferma; tie-break recency, poi numero);
#   • dalla successiva gioca virtualmente l'ambo TOP1-HOT5 fino a H5;
#   • HIT se TOP1 e accompagnatore escono insieme; STOP alla prima seconda
#     uscita del TOP1 senza accompagnatore, o comunque a H5;
#   • contabilizza ogni colpo dopo l'estrazione (1 euro e premio lordo 14x default).
#   • SOLO SIMULAZIONE: NON si collega a bookmaker/concessionari.
#
# MIGRAZIONE:
#   • se esiste il vecchio state combinato, importa SOLO i campi ENGINE;
#   • ignora completamente CORE/FAST/FREQ;
#   • converte i vecchi record ENGINE H5 nella nuova diagnostica MULTI-HIT,
#     quindi non riparte da zero quando i dati sono disponibili.
#
# INFRASTRUTTURA:
#   • polling sito ogni LOOP_SEC
#   • state persistente GitHub
#   • rotazione automatica GitHub runner prima del limite
# ============================================================

import asyncio
import atexit
import json
import math
import os
import re
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

# AMBO HOT5: simulazione con notifiche Telegram, nessuna interazione con concessionari.
# Prima uscita TOP1 entro H1-H3 = conferma. L'accompagnatore viene scelto fra
# i numeri PRESENTI nel draw di conferma: massimo conteggio nelle ultime 5
# estrazioni (inclusa la conferma), tie-break recency e poi numero piu' basso.
AMBO_SIM_ENABLED = os.getenv("AMBO_SIM_ENABLED", "1") != "0"
AMBO_SIM_STAKE_CENTS = max(1, int(os.getenv("AMBO_SIM_STAKE_CENTS", "100")))
AMBO_SIM_PAYOUT_MULTIPLIER = float(os.getenv("AMBO_SIM_PAYOUT_MULTIPLIER", "14"))
AMBO_SIM_NOTIFY = os.getenv("AMBO_SIM_NOTIFY", "1") != "0"
AMBO_SIM_RECORD_MAX = max(100, int(os.getenv("AMBO_SIM_RECORD_MAX", "5000")))
AMBO_SIM_BET_LOG_MAX = max(100, int(os.getenv("AMBO_SIM_BET_LOG_MAX", "15000")))
AMBO_SIM_DIAG_VERSION = 2

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

        # AMBO HOT5 e' prospettico. Se lo state contiene il precedente AMBO H2
        # (diag v1), viene archiviato come legacy e NON mescolato nelle nuove statistiche.
        self.ambo_h2_legacy = {}
        self.ambo_sim_draw_index = 0
        self.ambo_sim_last_candidate_index = -100000
        self.ambo_sim_skipped_overlap = 0
        self.ambo_sim_sessions = []
        self.ambo_sim_records_live = []
        self.ambo_sim_bets_live = []
        self.ambo_sim_account = {"bets": 0, "wins": 0, "cost_cents": 0, "gross_cents": 0}

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
    # AMBO HOT5 H1-H3 — simulazione prospettica separata dall'ENGINE
    # ========================================================
    @staticmethod
    def _ambo_validate_session(row):
        if not isinstance(row, dict):
            return None
        try:
            top = int(row['top1'])
            age = int(row.get('age', 0))
            partner = row.get('partner')
            partner = int(partner) if partner is not None else None
            phase = str(row.get('phase', ''))
            conf_age = row.get('confirmation_age')
            conf_age = int(conf_age) if conf_age is not None else None
            hot5_count = row.get('partner_hot5_count')
            hot5_count = int(hot5_count) if hot5_count is not None else None
            if not (1 <= top <= 90 and 0 <= age <= 5 and
                    (partner is None or (1 <= partner <= 90 and partner != top)) and
                    phase in {'await_h1','await_h2','await_h3','needs_partner','play'}):
                return None
            if phase == 'play' and (partner is None or conf_age not in (1,2,3)):
                return None
            return {
                'signal_from_key': str(row.get('signal_from_key', '')),
                'top1': top, 'support': int(row.get('support', 0)),
                'age': age, 'phase': phase, 'partner': partner,
                'confirmation_age': conf_age,
                'confirmation_draw_key': row.get('confirmation_draw_key'),
                'partner_hot5_count': hot5_count,
                'bets': int(row.get('bets', 0)), 'wins': int(row.get('wins', 0)),
                'created_at': row.get('created_at'),
                'strategy': 'hot5_confirm_h1_h3',
            }
        except (ValueError, TypeError, KeyError):
            return None

    def _ambo_load_fields(self, data):
        saved_ver = int(data.get('ambo_sim_diag_version', 0) or 0)
        self.ambo_h2_legacy = dict(data.get('ambo_h2_legacy', {}) or {})

        # Migrazione dal precedente AMBO H2 (diag v1): conserva lo storico in
        # un archivio legacy ma parte da zero con HOT5, evitando statistiche miste.
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
            self.ambo_sim_draw_index = 0
            self.ambo_sim_last_candidate_index = -100000
            self.ambo_sim_skipped_overlap = 0
            self.ambo_sim_sessions = []
            self.ambo_sim_records_live = []
            self.ambo_sim_bets_live = []
            self.ambo_sim_account = {"bets": 0, "wins": 0, "cost_cents": 0, "gross_cents": 0}
            return

        self.ambo_sim_draw_index = max(0, int(data.get('ambo_sim_draw_index', 0) or 0))
        self.ambo_sim_last_candidate_index = int(data.get('ambo_sim_last_candidate_index', -100000) or -100000)
        self.ambo_sim_skipped_overlap = max(0, int(data.get('ambo_sim_skipped_overlap', 0) or 0))
        self.ambo_sim_sessions = [x for row in data.get('ambo_sim_sessions', [])
                                  if (x := self._ambo_validate_session(row)) is not None][-1:]
        self.ambo_sim_records_live = list(data.get('ambo_sim_records_live', []) or [])[-AMBO_SIM_RECORD_MAX:]
        self.ambo_sim_bets_live = list(data.get('ambo_sim_bets_live', []) or [])[-AMBO_SIM_BET_LOG_MAX:]
        a = data.get('ambo_sim_account', {})
        self.ambo_sim_account = {
            name: max(0, int(a.get(name, 0) or 0))
            for name in ('bets','wins','cost_cents','gross_cents')
        }

    def _ambo_start_candidate(self, pending):
        """Lock di 5 draw fra due nascite HC per evitare sessioni sovrapposte."""
        if not AMBO_SIM_ENABLED or not pending or not pending.get('accepted'):
            return False
        if self.ambo_sim_sessions or self.ambo_sim_draw_index - self.ambo_sim_last_candidate_index < 5:
            self.ambo_sim_skipped_overlap += 1
            return False
        self.ambo_sim_last_candidate_index = self.ambo_sim_draw_index
        self.ambo_sim_sessions = [{
            'signal_from_key': str(pending['signal_from_key']),
            'created_at': pending.get('created_at'),
            'top1': int(pending['top1']),
            'support': int(pending.get('support', 0)),
            'age': 0, 'phase': 'await_h1', 'partner': None,
            'confirmation_age': None, 'confirmation_draw_key': None,
            'partner_hot5_count': None, 'bets': 0, 'wins': 0,
            'strategy': 'hot5_confirm_h1_h3',
        }]
        return True

    def _ambo_close(self, session, result, current_key, reason=''):
        record = {
            **dict(session), 'result': result, 'completed_at': current_key,
            'reason': reason, 'stake_cents': AMBO_SIM_STAKE_CENTS,
            'payout_multiplier': AMBO_SIM_PAYOUT_MULTIPLIER,
            'strategy': 'hot5_confirm_h1_h3',
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

    def _ambo_hot5_partner(self, top, confirmation_nums):
        """Numero piu' frequente nelle ultime 5 fra i co-usciti della conferma.

        Finestra: ultime 5 righe di engine_history, quindi comprende il draw di
        conferma appena aggiunto. Tie-break: recency-weighted presence, poi numero
        piu' basso. Non usa alcun draw futuro.
        """
        candidates = sorted(set(map(int, confirmation_nums)) - {int(top)})
        if not candidates:
            return None
        rows = self.engine_history[-5:]
        if not rows:
            return None

        scored = []
        for n in candidates:
            count = sum(1 for row in rows if n in set(row.get('nums', [])))
            # Pesi 1..N: il draw piu' recente pesa di piu' solo come tie-break.
            recency = sum(i + 1 for i, row in enumerate(rows) if n in set(row.get('nums', [])))
            scored.append((count, recency, -n, n))
        count, recency, _, partner = max(scored)
        return {
            'partner': int(partner),
            'count5': int(count),
            'recency_score': int(recency),
            'window': len(rows),
        }

    async def _ambo_settle_current(self, app, current_key, nums, notify=True):
        """Valuta il draw corrente PRIMA di aggiungerlo allo storico.

        La conferma puo' avvenire a H1/H2/H3. Il partner viene scelto solo DOPO
        l'append dello stesso draw, quindi la finestra HOT5 include la conferma
        e non contiene futuro.
        """
        if not self.ambo_sim_sessions:
            return
        session = self.ambo_sim_sessions[0]
        age = int(session['age']) + 1
        session['age'] = age
        top = int(session['top1'])
        actual = set(map(int, nums))
        phase = session['phase']

        # Attesa della PRIMA uscita del TOP1 entro H1-H3.
        if phase in {'await_h1', 'await_h2', 'await_h3'} and age in (1, 2, 3):
            if top in actual:
                session['phase'] = 'needs_partner'
                session['confirmation_age'] = age
                session['confirmation_draw_key'] = current_key
            elif age == 1:
                session['phase'] = 'await_h2'
            elif age == 2:
                session['phase'] = 'await_h3'
            else:
                self._ambo_close(session, 'no_play', current_key, 'nessuna_prima_uscita_entro_h3')
            return

        if phase == 'needs_partner':
            # La finalize doveva avvenire nello stesso draw dopo append_history.
            self._ambo_close(session, 'interrupted', current_key, 'partner_non_finalizzato')
            return

        if phase != 'play' or age not in (2, 3, 4, 5):
            self._ambo_close(session, 'interrupted', current_key, 'stato_temporale_incoerente')
            return

        partner = int(session['partner'])
        hit = top in actual and partner in actual
        top_hit = top in actual
        stake = AMBO_SIM_STAKE_CENTS
        prize = int(round(stake * AMBO_SIM_PAYOUT_MULTIPLIER)) if hit else 0
        a = self.ambo_sim_account
        a['bets'] += 1
        a['cost_cents'] += stake
        a['gross_cents'] += prize
        a['wins'] += int(hit)
        session['bets'] += 1
        session['wins'] += int(hit)
        self.ambo_sim_bets_live.append({
            'strategy': 'hot5_confirm_h1_h3',
            'signal_from_key': session['signal_from_key'], 'draw_key': current_key,
            'confirmation_age': session.get('confirmation_age'),
            'age': age, 'top1': top, 'partner': partner,
            'partner_hot5_count': session.get('partner_hot5_count'),
            'hit': bool(hit), 'top1_hit': bool(top_hit),
            'cost_cents': stake, 'gross_cents': prize, 'net_cents': prize-stake,
        })
        self.ambo_sim_bets_live = self.ambo_sim_bets_live[-AMBO_SIM_BET_LOG_MAX:]

        if hit:
            self._ambo_close(session, 'hit', current_key, 'ambo_hot5_centrato')
            label = '✅ AMBO HOT5 CENTRATO — HIT / STOP'
        elif top_hit:
            self._ambo_close(session, 'stop', current_key, 'secondo_top1_senza_hot5')
            label = '⛔ STOP: TOP1 uscito senza accompagnatore HOT5'
        elif age >= 5:
            self._ambo_close(session, 'stop', current_key, 'fine_h5')
            label = '⛔ STOP H5: nessun ambo'
        else:
            label = '❌ AMBO NON USCITO — sessione ancora aperta'

        await self._ambo_notice(
            app,
            f'🎮 AMBO HOT5 — ESITO H{age}\n'
            f'Segnale {session["signal_from_key"]} | estrazione {current_key}\n'
            f'Conferma TOP1 a H{session.get("confirmation_age")} | '
            f'AMBO {top}-{partner} | HOT5 partner={session.get("partner_hot5_count")}/5\n'
            f'Puntata virtuale {sim_euro(stake)}\n'
            f'{label}\n'
            f'Premio di questo colpo: {sim_euro(prize)}\n'
            f'Bilancio di questo colpo: {sim_euro(prize-stake)}\n'
            f'SALDO TOTALE VIRTUALE HOT5: {sim_euro(self._ambo_balance())}' +
            (f'\n\n▶️ PROSSIMA ESTRAZIONE: ripeti AMBO {top}-{partner} '
             f'a H{age+1} | {sim_euro(stake)} (simulati).' if self.ambo_sim_sessions else
             '\n\n🏁 Sessione chiusa, non ripetere questo ambo.'),
            notify=notify
        )

        # Se il draw e' stato recuperato in silenzio non fingiamo che il successivo
        # colpo fosse stato notificato prima dell'estrazione.
        if self.ambo_sim_sessions and not notify:
            self._ambo_close(session, 'interrupted', current_key, 'prossimo_colpo_non_notificato')

    async def _ambo_finalize_confirmation(self, app, current_key, nums, notify=True):
        """Dopo append_history del draw di conferma sceglie il partner HOT5."""
        if not self.ambo_sim_sessions:
            return
        session = self.ambo_sim_sessions[0]
        if session['phase'] != 'needs_partner':
            return
        if not notify:
            self._ambo_close(session, 'no_play', current_key, 'conferma_recuperata_senza_notifica')
            return

        top = int(session['top1'])
        pick = self._ambo_hot5_partner(top, nums)
        if not pick:
            self._ambo_close(session, 'no_play', current_key, 'hot5_non_disponibile')
            return

        session['partner'] = int(pick['partner'])
        session['partner_hot5_count'] = int(pick['count5'])
        session['phase'] = 'play'
        conf_age = int(session['confirmation_age'])
        first_play_age = conf_age + 1
        stake = AMBO_SIM_STAKE_CENTS

        await self._ambo_notice(
            app,
            f'🎯 AMBO HOT5 — SEGNALE DI GIOCATA\n'
            f'HC da {session["signal_from_key"]} | conferma {current_key}\n'
            f'TOP1 #{top}: PRIMA uscita a H{conf_age} (solo conferma, non giocata).\n'
            f'Accompagnatore HOT5 #{session["partner"]}: presente nello stesso draw e '
            f'frequenza {session["partner_hot5_count"]}/5 nelle ultime 5.\n\n'
            f'▶️ PROSSIMA ESTRAZIONE H{first_play_age}: AMBO {top}-{session["partner"]}\n'
            f'Puntata VIRTUALE: {sim_euro(stake)}\n'
            f'Se entrambi escono: premio lordo simulato '
            f'{sim_euro(round(stake*AMBO_SIM_PAYOUT_MULTIPLIER))}.\n'
            'Se esce TOP1 senza accompagnatore: STOP immediato.\n'
            'Se TOP1 manca: ripeti lo stesso ambo fino a H5.',
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

        parts = [
            '🎮 AMBO HOT5 H1-H3 — SIMULATORE CON NOTIFICHE',
            'Regola: HC -> prima uscita TOP1 entro H1/H2/H3 = CONFERMA non giocata.',
            'Partner = piu frequente ultime 5 fra i numeri usciti insieme al TOP1 nella conferma.',
            'Dalla successiva: stesso ambo fino a seconda uscita TOP1 o massimo H5.',
            'Secondo TOP1 + partner = HIT; secondo TOP1 senza partner = STOP.',
            f'💶 Puntata virtuale {sim_euro(AMBO_SIM_STAKE_CENTS)} | '
            f'premio lordo ipotizzato {AMBO_SIM_PAYOUT_MULTIPLIER:g}x.',
            '',
            '📊 SOLO DATI PROSPETTICI AMBO HOT5',
            f'• sessioni chiuse: {len(completed)} | HIT={hit_sessions} | STOP={stops} | NO PLAY={no_play}',
            f'• HC esclusi per lock di 5 draw: {self.ambo_sim_skipped_overlap}',
            f'• colpi virtuali {n} | AMBI HIT {wins} | HIT/puntata {safe_pct(wins,n):.2f}%',
            f'• COSTO {sim_euro(a["cost_cents"])} | LORDO {sim_euro(a["gross_cents"])}',
            f'• SALDO NETTO {sim_euro(net)} | ROI {safe_pct(net,a["cost_cents"]):.2f}%',
            f'• pareggio teorico: {100.0/AMBO_SIM_PAYOUT_MULTIPLIER:.2f}% '
            'di ambi per puntata (costi extra esclusi).',
        ]

        # Split prospettico per eta' di conferma.
        parts += ['', '⏱ PER CONFERMA']
        for age in (1, 2, 3):
            rows = [r for r in completed if r.get('confirmation_age') == age and r.get('result') in {'hit','stop'}]
            h = sum(r.get('result') == 'hit' for r in rows)
            bets = sum(int(r.get('bets', 0) or 0) for r in rows)
            parts.append(
                f'• H{age}: sessioni {len(rows)} | HIT {h}/{len(rows)} ({safe_pct(h,len(rows)):.2f}%) '
                f'| colpi {bets}'
            )

        parts += ['', '📍 SESSIONE ATTIVA']
        if not active:
            parts.append('• nessuna: non giocare ambo finché non arriva un nuovo avviso.')
        else:
            s = active[0]
            if s['phase'] == 'play':
                parts.append(
                    f'• {s["signal_from_key"]}: AMBO {s["top1"]}-{s["partner"]} | '
                    f'conferma H{s.get("confirmation_age")} | HOT5 {s.get("partner_hot5_count")}/5 | '
                    f'PROSSIMA H{s["age"]+1}, {sim_euro(AMBO_SIM_STAKE_CENTS)} VIRTUALI.'
                )
            else:
                parts.append(
                    f'• {s["signal_from_key"]}: TOP1 {s["top1"]}, fase {s["phase"]}, '
                    f'prossimo H{s["age"]+1}; nessuna puntata ora.'
                )

        parts.extend(['', '🧾 ULTIMI COLPI VIRTUALI'])
        if not self.ambo_sim_bets_live:
            parts.append('• nessuna puntata HOT5 ancora registrata')
        else:
            for bet in self.ambo_sim_bets_live[-8:]:
                parts.append(
                    f'• {bet.get("draw_key","-")} H{bet.get("age","-")} '
                    f'{bet.get("top1","-")}-{bet.get("partner","-")} '
                    f'{"✅ HIT" if bet.get("hit") else "❌ MISS"} '
                    f'| costo {sim_euro(bet.get("cost_cents",0))} '
                    f'| premio {sim_euro(bet.get("gross_cents",0))}'
                )

        if self.ambo_h2_legacy:
            old_a = dict(self.ambo_h2_legacy.get('account', {}) or {})
            old_bets = int(old_a.get('bets', 0) or 0)
            old_wins = int(old_a.get('wins', 0) or 0)
            old_cost = int(old_a.get('cost_cents', 0) or 0)
            old_gross = int(old_a.get('gross_cents', 0) or 0)
            parts += [
                '', '📦 ARCHIVIO PRECEDENTE AMBO H2 (NON SOMMATO)',
                f'• colpi={old_bets} | hit={old_wins} | costo={sim_euro(old_cost)} | '
                f'lordo={sim_euro(old_gross)} | netto={sim_euro(old_gross-old_cost)}'
            ]

        parts.append('⚠️ Solo simulazione. /engine /multih5 /play e relativo storico restano invariati.')
        return '\n'.join(parts)

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

            # Se c'e' un pending HC ma manca la sessione H5/PLAY, aggancialo senza duplicare.
            if self.engine_pending and self.engine_pending.get("accepted"):
                self._start_h5_session(self.engine_pending)
                self._start_play_session(self.engine_pending)

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
            "ambo_sim_draw_index": self.ambo_sim_draw_index,
            "ambo_sim_last_candidate_index": self.ambo_sim_last_candidate_index,
            "ambo_sim_skipped_overlap": self.ambo_sim_skipped_overlap,
            "ambo_sim_sessions": self.ambo_sim_sessions,
            "ambo_sim_records_live": self.ambo_sim_records_live[-AMBO_SIM_RECORD_MAX:],
            "ambo_sim_bets_live": self.ambo_sim_bets_live[-AMBO_SIM_BET_LOG_MAX:],
            "ambo_sim_account": self.ambo_sim_account,
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
                        "👀 AMBO HOT5 — IN OSSERVAZIONE\n"
                        f"HIGH CONFIDENCE da {current_key} | TOP1 #{p['top1']}\n"
                        "NON giocare ora. Aspetto la PRIMA uscita del TOP1 entro H1-H3.\n"
                        "Nel draw di conferma scegliero' tra i co-usciti il numero piu' "
                        "frequente nelle ultime 5, poi riceverai l'ambo per il colpo successivo.",
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

    async def process_draw(self, app, day, e, nums, mode="live", notify=True, persist=True):
        clean = list(map(int, nums))
        if len(clean) != 20 or len(set(clean)) != 20:
            return None
        if self.already_processed(day, e):
            return None

        if mode == "live":
            if self.ambo_sim_sessions and not sim_draw_is_consecutive(self.last_draw_key, day, e):
                old = self.ambo_sim_sessions[0]
                self._ambo_close(old, "interrupted", draw_key(day, e), "estrazioni_mancanti")
                await self._ambo_notice(
                    app,
                    "⚠️ AMBO HOT5 — SESSIONE INTERROTTA\n"
                    "Mancano estrazioni consecutive: annullo la sessione per non inventare puntate.\n"
                    "Nuovi segnali saranno valutati soltanto sui draw successivi.",
                    notify=notify,
                )
            self.ambo_sim_draw_index += 1
            await self._ambo_settle_current(app, draw_key(day, e), clean, notify=notify)

        await self.settle_play_sessions(app, day, e, clean, mode=mode, notify=notify)
        await self.settle_h5_sessions(app, day, e, clean, mode=mode, notify=notify)
        await self.settle_engine_pending(app, day, e, clean, mode=mode, notify=notify)

        current_key = self.remember_processed(day, e)
        self.engine_append_history(current_key, clean)
        if mode == "live":
            # Partner HOT5 determinato DOPO il draw di conferma H1/H2/H3, senza futuro.
            await self._ambo_finalize_confirmation(app, current_key, clean, notify=notify)
        p = await self.arm_engine_shadow(app, current_key, mode=mode, notify=notify)

        if persist:
            self.save_state(git=True)
        return p

    @staticmethod
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
            "Dettagli: /multih5 | /engineh | /play | /ambo\n\n"
            "Baseline H1 TOP1 casuale: 22.22%.\n"
            "⚠️ Nessuna puntata automatica."
        )

    def menu_text(self):
        return (
            "🧠 10eLOTTO ENGINE ONLY\n\n"
            "Unico motore: HIGH CONFIDENCE TOP1.\n"
            "Il TOP1 viene seguito per 5 estrazioni per misurare ESATTO 2/5 e >=2/5.\n\n"
            "/engine — stato, TOP1 e statistiche HIGH CONFIDENCE\n"
            "/engineh — H1/H2/H3/H5 del TOP1\n"
            "/multih5 — 0/5, 1/5, esatto 2/5, >=2/5, >=3/5\n"
            "/play — strategia conferma H1-H3 -> seconda uscita entro H5\n"
            "/ambo — AMBO HOT5 H1-H3: notifiche, costo, premi e saldo\n"
            "/status — stato rapido ENGINE\n"
            "/menu — questa schermata"
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

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].engine_text())

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].menu_text())

async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("engine", "ENGINE ONLY: TOP1 + HIGH CONFIDENCE"),
        BotCommand("engineh", "TOP1 H1/H2/H3/H5"),
        BotCommand("multih5", "TOP1 multi-hit nelle 5 successive"),
        BotCommand("play", "PLAY SHADOW: seconda uscita dopo conferma"),
        BotCommand("ambo", "AMBO HOT5 H1-H3: notifiche e saldo"),
        BotCommand("status", "Stato rapido ENGINE"),
        BotCommand("menu", "Comandi ENGINE ONLY"),
    ])

async def ensure_engine_ready(engine):
    if engine.engine_bootstrap_done and len(engine.engine_history) >= ENGINE_MIN_HISTORY:
        return {"ok": True, "already_done": True, "draws": len(engine.engine_history)}
    try:
        all_records, sources = fetch_warmup_records(WARMUP_DAYS)
        records, sources2, continuity = _select_latest_contiguous_warmup(all_records, sources)
        if continuity.get("problems"):
            return {
                "ok": False, "draws": len(records), "sources": sources2,
                "reason": "; ".join(continuity["problems"][:5]),
                "continuity_note": continuity.get("note"),
            }
        records = sorted(records, key=lambda x:(x[0],x[1]))
        if len(records) < ENGINE_MIN_HISTORY:
            return {
                "ok": False, "draws": len(records), "sources": sources2,
                "reason": f"storico insufficiente: {len(records)}<{ENGINE_MIN_HISTORY}",
                "continuity_note": continuity.get("note"),
            }

        ok = await engine.rebuild_engine_from_records(records[-ENGINE_HISTORY_MAX:])
        if ok:
            # Tutto il segmento letto e' gia' incorporato nel replay.
            engine.processed = [draw_key(d,e) for d,e,_ in records][-PROCESSED_MAX:]
            engine.processed_set = set(engine.processed)
            if records:
                engine.last_draw_key = draw_key(records[-1][0], records[-1][1])
        return {
            "ok": bool(ok), "already_done": False, "draws": len(records),
            "sources": sources2, "continuity_note": continuity.get("note"),
            "reason": None if ok else "rebuild ENGINE fallito",
        }
    except Exception as exc:
        return {"ok": False, "draws": 0, "reason": f"{type(exc).__name__}: {exc}"}

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
    """Al riavvio ricorda lo stato HOT5 senza contabilizzare colpi retroattivi."""
    if not AMBO_SIM_ENABLED or not engine.ambo_sim_sessions:
        return
    s = engine.ambo_sim_sessions[0]
    if s['phase'] == 'play':
        await engine._ambo_notice(
            app,
            f'♻️ AMBO HOT5 — SESSIONE RECUPERATA DALLO STATE\n'
            f'Segnale {s["signal_from_key"]} | AMBO {s["top1"]}-{s["partner"]}\n'
            f'Conferma H{s.get("confirmation_age")} | HOT5 {s.get("partner_hot5_count")}/5\n'
            f'▶️ PROSSIMA ESTRAZIONE H{s["age"]+1}: '
            f'puntata VIRTUALE {sim_euro(AMBO_SIM_STAKE_CENTS)}.\n'
            'Non contabilizzo il colpo finché non arriva la relativa estrazione.',
        )
    else:
        await engine._ambo_notice(
            app,
            f'♻️ AMBO HOT5 — OSSERVAZIONE RIPRESA\n'
            f'Segnale {s["signal_from_key"]} | TOP1 {s["top1"]}\n'
            f'Fase: {s["phase"]} | prossimo H{s["age"]+1}.\n'
            'Nessun ambo da giocare finché non arriva la prima uscita TOP1 entro H1-H3.',
        )

async def startup(engine, app, retry_state=None):
    retry_state = retry_state if isinstance(retry_state, dict) else {}
    ready = await ensure_engine_ready(engine)
    if not ready.get("ok"):
        reason=ready.get("reason","warmup non pronto")
        console_log(f"ENGINE WARMUP FAIL | {reason}")
        now_ts=time.time()
        if (reason != retry_state.get("last_reason") or
            now_ts - float(retry_state.get("last_tg_ts",0) or 0) >= WARMUP_FAIL_TG_MIN_SECONDS):
            await engine.tg(
                app,
                "⚠️ ENGINE ONLY — WARMUP NON PRONTO\n\n"
                f"Motivo: {reason}\n"
                f"Draw raccolti: {ready.get('draws',0)}\n"
                f"Riprovo tra {WARMUP_RETRY_SEC}s."
            )
            retry_state["last_reason"]=reason
            retry_state["last_tg_ts"]=now_ts
        return False

    # Catch-up dei draw arrivati dopo lo state/replay.
    try:
        rows=parse_site_today()
    except Exception as exc:
        console_log(f"CATCH-UP parser fail | {exc}")
        rows=[]
    unseen=[x for x in rows if not engine.already_processed(x[0],x[1])]
    unseen.sort(key=lambda x:(x[0],x[1]))
    for d,e,nums in unseen:
        await engine.process_draw(None,d,e,nums,mode="live",notify=False,persist=False)

    engine.save_state(git=True, force_git=True)

    await engine.tg(
        app,
        "🚀 10eLOTTO ENGINE ONLY AVVIATO\n\n"
        "✅ CORE rimosso\n"
        "✅ FAST rimosso\n"
        "✅ FREQ rimosso\n"
        "✅ TOP5/TOP10 diagnostica rimossa\n"
        "🧠 unico motore: ENGINE HIGH CONFIDENCE TOP1\n"
        "🧪 tracker: H1-H5 + MULTI-HIT H5\n"
        "🎯 focus: ESATTO 2/5 e >=2/5\n"
        "🎯 AMBO HOT5 H1-H3: conferma TOP1 -> accompagnatore caldo -> notifiche prima dei colpi\n"
        "🎮 PLAY SHADOW: conferma H1-H3 -> seconda uscita entro H5\n"
        "✅ state persistente + autorotation\n\n"
        f"ENGINE: {'READY' if engine.engine_bootstrap_done else 'BUILD'} | "
        f"filtro target top {ENGINE_SELECT_RATE*100:.0f}%\n"
        f"H5 LIVE gia' disponibili: {len(engine.engine_h5_records_live)}\n"
        f"PLAY storico ricostruito: {len(engine.engine_play_records_live)} record | "
        f"attivi={sum(1 for x in engine.engine_play_sessions if x.get('origin_mode')=='live')}\n\n"
        "Comandi: /engine /engineh /multih5 /play /ambo /menu"
    )
    await notify_pending(engine,app)
    await notify_ambo_active(engine,app)
    return True

async def startup_until_ready(engine, app):
    retry={}
    while True:
        if await startup(engine,app,retry):
            return
        await asyncio.sleep(max(30,WARMUP_RETRY_SEC))

async def live_loop(engine, app):
    console_log(f"ENGINE ONLY LIVE | poll={LOOP_SEC}s | rotation={BOT_MAX_RUNTIME_SECONDS}s")
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
                await engine.tg(app,"♻️ ENGINE ONLY — ROTAZIONE RUNNER\nState salvato; avvio successivo automatico.")
            return "rotation"

        try:
            rows=parse_site_today()
            unseen=[x for x in rows if not engine.already_processed(x[0],x[1])]
            unseen.sort(key=lambda x:(x[0],x[1]))
            if unseen:
                if len(unseen)==1:
                    d,e,nums=unseen[0]
                    await engine.process_draw(app,d,e,nums,mode="live",notify=True,persist=True)
                else:
                    for d,e,nums in unseen:
                        await engine.process_draw(None,d,e,nums,mode="live",notify=False,persist=False)
                    engine.save_state(git=True,force_git=True)
                    await notify_pending(engine,app)
                    await notify_ambo_active(engine,app)
            await asyncio.sleep(LOOP_SEC)
        except Exception as exc:
            txt=f"{type(exc).__name__}: {exc}"
            console_log(f"LOOP ERROR | {txt}")
            now=time.time()
            if txt!=last_error or now-last_error_ts>=900:
                await engine.tg(app,f"⚠️ ENGINE ONLY — ERRORE\n{txt}\nRiprovo automaticamente.")
                last_error=txt; last_error_ts=now
            await asyncio.sleep(max(30,LOOP_SEC))

async def run_self_test():
    import random
    random.seed(5601)
    e=EngineOnly(load=False)
    e.save_state=lambda *a,**k:_git_status(True,"test","no-op")
    recs=[]
    for i in range(260):
        recs.append(("2099-01-01",i+1,sorted(random.sample(range(1,91),20))))
    assert await e.rebuild_engine_from_records(recs)
    assert len(e.engine_history)>=ENGINE_MIN_HISTORY
    assert len(e.engine_margin_history)>=ENGINE_MIN_MARGIN_SAMPLES
    assert e.engine_pending is not None

    # Test H5 = esattamente 2 hit.
    x=EngineOnly(load=False)
    x.save_state=lambda *a,**k:_git_status(True,"test","no-op")
    p={"signal_from_key":"T#001","created_at":now_txt(),"origin_mode":"live","top1":42,
       "confidence":0.6,"threshold":0.4,"support":2,"accepted":True}
    assert x._start_h5_session(p)
    for age in range(1,6):
        nums=[n for n in range(1,91) if n != 42][:20]
        if age in (2,5):
            nums[-1]=42
        await x.settle_h5_sessions(None,"2099-02-01",age,nums,mode="live",notify=False)
    assert len(x.engine_h5_records_live)==1
    r=x.engine_h5_records_live[0]
    assert r["hits5"]==2 and r["hit_ages"]==[2,5]
    s=x._summarize_h5(x.engine_h5_records_live)
    assert s["exact2"]==1 and s["ge2"]==1 and s["ge3"]==0

    # Test PLAY SHADOW: conferma H2, PLAY H3/H4, seconda uscita a H4 -> HIT + STOP.
    y=EngineOnly(load=False)
    y.save_state=lambda *a,**k:_git_status(True,"test","no-op")
    p2={"signal_from_key":"P#001","created_at":now_txt(),"origin_mode":"live","top1":33,
        "confidence":0.7,"threshold":0.5,"support":2,"accepted":True}
    assert y._start_play_session(p2)
    for age in range(1,5):
        nums=[n for n in range(1,91) if n != 33][:20]
        if age in (2,4): nums[-1]=33
        await y.settle_play_sessions(None,"2099-03-01",age,nums,mode="live",notify=False)
    assert len(y.engine_play_records_live)==1
    pr=y.engine_play_records_live[0]
    assert pr["result"]=="hit" and pr["activation_age"]==2 and pr["hit_age"]==4
    assert pr["play_ages"]==[3,4] and pr["bets"]==2

    # Test NO PLAY: nessuna prima uscita entro H3.
    z=EngineOnly(load=False)
    z.save_state=lambda *a,**k:_git_status(True,"test","no-op")
    assert z._start_play_session({**p2,"signal_from_key":"P#002","top1":34})
    for age in range(1,4):
        nums=[n for n in range(1,91) if n != 34][:20]
        await z.settle_play_sessions(None,"2099-03-02",age,nums,mode="live",notify=False)
    assert len(z.engine_play_records_live)==1 and z.engine_play_records_live[0]["result"]=="no_play"
    assert z.engine_play_records_live[0]["bets"]==0

    # Test AMBO HOT5: prima uscita TOP1 a H2; nel draw di conferma il 72
    # e' l'unico co-uscito con forte frequenza nelle ultime 5; H3 MISS, H4 AMBO HIT.
    a = EngineOnly(load=False)
    sent = []
    async def fake_tg(app, text):
        sent.append(text)
    a.tg = fake_tg
    ambo_p = {"signal_from_key":"2099-04-01#100", "created_at":now_txt(),
              "origin_mode":"live", "top1":21,"support":2,"accepted":True}
    assert a._ambo_start_candidate(ambo_p)

    pre = [
        sorted(list(range(1,20)) + [72]),
        sorted(list(range(20,39)) + [72]),
        sorted(list(range(39,58)) + [72]),
        sorted(list(range(1,20)) + [72]),
    ]
    a.engine_history = [{"key":f"2099-04-01#09{i}", "nums":x} for i,x in enumerate(pre,1)]

    # H1 TOP1 miss, 72 ancora presente.
    h1 = sorted(list(range(40,59)) + [72])
    await a._ambo_settle_current(None,"2099-04-01#101",h1,notify=True)
    a.engine_append_history("2099-04-01#101",h1)
    await a._ambo_finalize_confirmation(None,"2099-04-01#101",h1,notify=True)
    assert a.ambo_sim_sessions[0]["phase"] == "await_h2"

    # H2 prima uscita 21; gli altri sono 72..90. Solo 72 e' caldo.
    h2 = [21,72] + list(range(73,91))
    assert len(h2) == 20
    await a._ambo_settle_current(None,"2099-04-01#102",h2,notify=True)
    a.engine_append_history("2099-04-01#102",h2)
    await a._ambo_finalize_confirmation(None,"2099-04-01#102",h2,notify=True)
    assert a.ambo_sim_sessions[0]["phase"] == "play"
    assert a.ambo_sim_sessions[0]["partner"] == 72
    assert a.ambo_sim_sessions[0]["confirmation_age"] == 2
    assert any("H3: AMBO 21-72" in msg for msg in sent)

    # H3 miss; H4 ambo hit. 2 euro costo -> 14 lordo.
    h3 = list(range(1,21))
    await a._ambo_settle_current(None,"2099-04-01#103",h3,notify=True)
    assert any("H4" in msg for msg in sent)
    h4 = [21,72] + list(range(73,91))
    await a._ambo_settle_current(None,"2099-04-01#104",h4,notify=True)
    assert a.ambo_sim_account == {"bets":2,"wins":1,"cost_cents":200,"gross_cents":1400}
    assert a._ambo_balance() == 1200 and not a.ambo_sim_sessions
    assert a.ambo_sim_records_live[0]["result"] == "hit"

    # Test conferma H1: deve generare primo PLAY a H2.
    b = EngineOnly(load=False)
    b.tg = fake_tg
    assert b._ambo_start_candidate({**ambo_p, "signal_from_key":"2099-04-02#100"})
    b.engine_history = [{"key":f"X{i}", "nums":sorted(list(range(1,20))+[60])} for i in range(4)]
    c1 = [21,60] + list(range(61,79))
    await b._ambo_settle_current(None,"2099-04-02#101",c1,notify=True)
    b.engine_append_history("2099-04-02#101",c1)
    await b._ambo_finalize_confirmation(None,"2099-04-02#101",c1,notify=True)
    assert b.ambo_sim_sessions[0]["phase"] == "play"
    assert b.ambo_sim_sessions[0]["confirmation_age"] == 1
    assert b.ambo_sim_sessions[0]["age"] == 1

    print("SELF-TEST OK: ENGINE ONLY + MULTI-HIT H5 + PLAY SHADOW + AMBO HOT5 H1-H3")

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

    app.add_handler(CommandHandler("engine",cmd_engine))
    app.add_handler(CommandHandler("engineh",cmd_engineh))
    app.add_handler(CommandHandler("multih5",cmd_multih5))
    app.add_handler(CommandHandler("play",cmd_play))
    app.add_handler(CommandHandler("ambo",cmd_ambo))
    app.add_handler(CommandHandler("status",cmd_status))
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
