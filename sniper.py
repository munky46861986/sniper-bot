# ============================================================
# 🎯 SUPERAMBO — 5 SUPERSTITI / OLDEST 70-79 / +30 / H1-H2
# ============================================================
#
# STRATEGIA UNICA, CONGELATA:
#
#   • Ogni estrazione diventa un NUOVO PUNTO DI PARTENZA (origine).
#     Esempio: origine = estrazione 127 -> il conteggio parte dalla 128.
#
#   • Per OGNI origine vengono seguite in parallelo tutte le 9 decine:
#       90-9, 10-19, 20-29, 30-39, 40-49,
#       50-59, 60-69, 70-79, 80-89.
#
#   • Ogni decina parte con tutti i suoi 45 ambi possibili.
#     Man mano che gli ambi compaiono, vengono eliminati.
#
#   • Quando una decina resta con 1 solo ambo non ancora uscito,
#     quell'ambo e' un SUPERSTITE e si memorizza da quale estrazione
#     e' rimasto solo.
#
#   • Quando, per la stessa origine, ci sono ESATTAMENTE 5 superstiti
#     contemporaneamente, si forma un BASKET da 5.
#
#   • Lo stesso IDENTICO basket (stesse 5 decine + stessi 5 ambi)
#     viene considerato UNA SOLA VOLTA globalmente, anche se compare
#     da origini diverse. Questa e' la deduplica usata nel test.
#
#   • Tra i 5 superstiti si sceglie il PIU' VECCHIO, cioe' quello
#     che e' rimasto unico da piu' tempo.
#
#   • Il basket e' valido SOLO se il piu' vecchio appartiene alla 70-79.
#
#   • Da quando nasce il basket, l'ambo 70-79 deve restare ASSENTE
#     per altre 30 estrazioni complete.
#       - se esce durante le 30 -> candidato annullato
#       - se sopravvive -> H1 sulla PROSSIMA estrazione
#       - se H1 perde -> H2 sulla PROSSIMA
#       - dopo HIT H1 / HIT H2 / STOP H2 -> chiusura
#
# WARMUP INIZIALE v5:
#   • al primo avvio scarica gli ultimi WARMUP_DAYS giorni
#   • ogni giorno GIA' CONCLUSO deve avere esattamente 288 estrazioni
#   • se una fonte e' incompleta prova automaticamente le altre e integra
#   • se restano buchi/conflitti il il warmup usa SOLO il segmento continuo successivo al buco; blocca solo se insufficiente
#   • crea retroattivamente tutte le origini storiche necessarie
#   • ricostruisce basket, superstiti e candidati ancora vivi
#   • NON manda segnali retroattivi
#   • quindi all'avvio non bisogna aspettare decine di estrazioni
#   • agli avvii successivi riparte dallo state persistente
#   • se il warmup non e' pronto il processo NON termina: resta acceso e ritenta
#
# SHADOW/FORWARD:
#   • default SHADOW_MODE=1 -> messaggi marcati SHADOW
#   • SHADOW_MODE=0 -> messaggi marcati PLAY
#   • il bot NON effettua puntate automaticamente
#
# ============================================================

import asyncio
import atexit
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from itertools import combinations
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
STATE_FILE = os.path.join(BASE_DIR, "superambo_5survivors_70_79_wait30_state.json")
LOCK_FILE = "/tmp/superambo_5survivors_70_79_wait30.lock"

LOGIC_VERSION = 5
LOOP_SEC = int(os.getenv("LOOP_SEC", "60"))
WARMUP_RETRY_SEC = int(os.getenv("WARMUP_RETRY_SEC", "300"))
WARMUP_FAIL_TG_MIN_SECONDS = int(os.getenv("WARMUP_FAIL_TG_MIN_SECONDS", "900"))
WARMUP_DAYS = int(os.getenv("WARMUP_DAYS", "7"))
WARMUP_MIN_DRAWS = int(os.getenv("WARMUP_MIN_DRAWS", "900"))
WARMUP_FULL_DAY_DRAWS = int(os.getenv("WARMUP_FULL_DAY_DRAWS", "288"))
WARMUP_REQUIRE_COMPLETE_PAST_DAYS = os.getenv("WARMUP_REQUIRE_COMPLETE_PAST_DAYS", "1") != "0"
ORIGIN_MAX_AGE = int(os.getenv("ORIGIN_MAX_AGE", "1000"))

BASKET_SIZE = 5
TARGET_DECADE = "70-79"
TARGET_DECADE_INDEX = 7
EXTRA_WAIT = 30
STAKE_H1 = float(os.getenv("STAKE_H1", "1"))
STAKE_H2 = float(os.getenv("STAKE_H2", "1"))
AMBO_PAYOUT = float(os.getenv("AMBO_PAYOUT", "14"))
SHADOW_MODE = os.getenv("SHADOW_MODE", "1") != "0"

PERSIST_GIT_STATE = os.getenv("PERSIST_GIT_STATE", "1") != "0"
GIT_COMMIT_MIN_SECONDS = int(os.getenv("GIT_COMMIT_MIN_SECONDS", "300"))
_LAST_GIT_COMMIT_TS = 0.0

DECADES = [
    ("90-9", (90, 1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ("10-19", tuple(range(10, 20))),
    ("20-29", tuple(range(20, 30))),
    ("30-39", tuple(range(30, 40))),
    ("40-49", tuple(range(40, 50))),
    ("50-59", tuple(range(50, 60))),
    ("60-69", tuple(range(60, 70))),
    ("70-79", tuple(range(70, 80))),
    ("80-89", tuple(range(80, 90))),
]
DECADE_NAMES = [x[0] for x in DECADES]
PAIR_LISTS = [tuple(combinations(nums, 2)) for _, nums in DECADES]
PAIR_INDEX = [
    {tuple(sorted(pair)): idx for idx, pair in enumerate(pairs)}
    for pairs in PAIR_LISTS
]
FULL_MASK = (1 << 45) - 1


# ============================================================
# UTILITY
# ============================================================

def now_dt():
    return datetime.now(BOT_TZ)


def now_txt():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def day_key():
    return now_dt().strftime("%Y-%m-%d")


def console_log(message):
    """Log immediato nei GitHub Actions (stdout non bufferizzato lato applicazione)."""
    print(f"[{now_txt()}] {message}", flush=True)


def draw_key(day, e):
    return f"{day}#{int(e):03d}"


def safe_pct(num, den):
    return (100.0 * float(num) / float(den)) if den else 0.0


def signal_word():
    return "SHADOW" if SHADOW_MODE else "PLAY"


def fmt_pair(pair):
    a, b = sorted(map(int, pair))
    if b == 90:
        return f"90-{a}"
    return f"{a}-{b}"


def bit_index(single_bit_mask):
    return int(single_bit_mask).bit_length() - 1


def pair_from_mask(decade_index, mask):
    if int(mask).bit_count() != 1:
        return None
    return PAIR_LISTS[decade_index][bit_index(int(mask))]


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


# ============================================================
# PARSER STORICO / LIVE
# ============================================================

_ITALIAN_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


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


# ============================================================
# PERSISTENZA GIT OPZIONALE
# ============================================================

def git_commit_state_if_needed(force=False):
    global _LAST_GIT_COMMIT_TS
    if not PERSIST_GIT_STATE:
        return False
    now = time.time()
    if not force and (now - _LAST_GIT_COMMIT_TS) < GIT_COMMIT_MIN_SECONDS:
        return False
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=BASE_DIR, stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if not root:
            return False
        rel = os.path.relpath(STATE_FILE, root)
        subprocess.run(["git", "add", rel], cwd=root, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root)
        if diff.returncode == 0:
            _LAST_GIT_COMMIT_TS = now
            return False
        subprocess.run(
            ["git", "commit", "-m", "update 5-survivors 70-79 state"],
            cwd=root, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        subprocess.run(["git", "push"], cwd=root, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _LAST_GIT_COMMIT_TS = now
        return True
    except Exception:
        return False


# ============================================================
# MOTORE MULTI-ORIGINE
# ============================================================

class FiveSurvivorsEngine:
    def __init__(self, load=True):
        self.logic_version = LOGIC_VERSION

        self.warmup_done = False
        self.warmup_completed_at = None
        self.warmup_draws = 0
        self.warmup_sources = []

        self.processed = []
        self.processed_set = set()
        self.last_draw_key = None
        self.seq = 0

        # Ogni draw crea una nuova origine; restano in RAM solo quelle
        # che possono ancora generare un basket da 5.
        self.origins = []
        self.next_origin_id = 1

        # Deduplica GLOBALE dei basket: stesse 5 decine + stessi 5 ambi = 1 caso.
        self.seen_baskets = []
        self.seen_basket_set = set()

        # Piu' candidati possono essere contemporaneamente in WAIT/H1/H2.
        self.candidates = []
        self.next_candidate_id = 1

        self.stats_warmup = self._new_stats()
        self.stats_live = self._new_stats()

        if load:
            self.load_state()

    @staticmethod
    def _new_stats():
        return {
            "origins_started": 0,
            "origins_pruned": 0,
            "baskets5": 0,
            "baskets5_oldest_target": 0,
            "candidates": 0,
            "canceled_wait30": 0,
            "armed_h1": 0,
            "h1_plays": 0,
            "h1_hits": 0,
            "h1_misses": 0,
            "h2_plays": 0,
            "h2_hits": 0,
            "stops_h2": 0,
            "cost": 0.0,
            "gross": 0.0,
        }

    def _stats(self, mode):
        return self.stats_warmup if mode == "warmup" else self.stats_live

    # ----------------------------
    # Stato / serializzazione
    # ----------------------------

    @staticmethod
    def _serialize_origin(o):
        return {
            "id": int(o["id"]),
            "anchor_seq": int(o["anchor_seq"]),
            "anchor_key": o.get("anchor_key"),
            "remaining": [int(x) for x in o["remaining"]],
            "survivor_since": [None if x is None else int(x) for x in o["survivor_since"]],
            "survivor_since_key": list(o.get("survivor_since_key", [None] * 9)),
        }

    @staticmethod
    def _deserialize_origin(o):
        rem = list(o.get("remaining", []))
        ss = list(o.get("survivor_since", []))
        ssk = list(o.get("survivor_since_key", []))
        if len(rem) != 9 or len(ss) != 9:
            return None
        if len(ssk) != 9:
            ssk = [None] * 9
        return {
            "id": int(o.get("id", 0)),
            "anchor_seq": int(o.get("anchor_seq", 0)),
            "anchor_key": o.get("anchor_key"),
            "remaining": [int(x) for x in rem],
            "survivor_since": [None if x is None else int(x) for x in ss],
            "survivor_since_key": ssk,
        }

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if int(d.get("logic_version", 0)) != LOGIC_VERSION:
                return

            self.warmup_done = bool(d.get("warmup_done", False))
            self.warmup_completed_at = d.get("warmup_completed_at")
            self.warmup_draws = int(d.get("warmup_draws", 0) or 0)
            self.warmup_sources = list(d.get("warmup_sources", []) or [])

            self.processed = list(d.get("processed", []) or [])[-12000:]
            self.processed_set = set(self.processed)
            self.last_draw_key = d.get("last_draw_key")
            self.seq = int(d.get("seq", 0) or 0)

            self.origins = []
            for raw in d.get("origins", []) or []:
                o = self._deserialize_origin(raw)
                if o:
                    self.origins.append(o)
            self.next_origin_id = int(d.get("next_origin_id", 1) or 1)

            self.seen_baskets = list(d.get("seen_baskets", []) or [])
            self.seen_basket_set = set(self.seen_baskets)

            self.candidates = list(d.get("candidates", []) or [])
            self.next_candidate_id = int(d.get("next_candidate_id", 1) or 1)

            self.stats_warmup.update(d.get("stats_warmup") or {})
            self.stats_live.update(d.get("stats_live") or {})
        except Exception as exc:
            print(f"⚠️ state non caricato: {exc}")

    def save_state(self, git=False, force_git=False):
        data = {
            "logic_version": LOGIC_VERSION,
            "saved_at": now_txt(),
            "warmup_done": self.warmup_done,
            "warmup_completed_at": self.warmup_completed_at,
            "warmup_draws": self.warmup_draws,
            "warmup_sources": self.warmup_sources,
            "processed": self.processed[-12000:],
            "last_draw_key": self.last_draw_key,
            "seq": self.seq,
            "origins": [self._serialize_origin(o) for o in self.origins],
            "next_origin_id": self.next_origin_id,
            "seen_baskets": self.seen_baskets,
            "candidates": self.candidates,
            "next_candidate_id": self.next_candidate_id,
            "stats_warmup": self.stats_warmup,
            "stats_live": self.stats_live,
        }
        atomic_write_json(STATE_FILE, data)
        if git:
            git_commit_state_if_needed(force=force_git)

    def already_processed(self, day, e):
        return draw_key(day, e) in self.processed_set

    def remember_processed(self, day, e):
        k = draw_key(day, e)
        if k not in self.processed_set:
            self.processed.append(k)
            self.processed = self.processed[-12000:]
            self.processed_set = set(self.processed)
        self.last_draw_key = k
        self.seq += 1
        return k

    # ----------------------------
    # Bitmask ambi
    # ----------------------------

    @staticmethod
    def hit_masks_for_draw(nums):
        numset = set(map(int, nums))
        masks = []
        for i, (_, decade_nums) in enumerate(DECADES):
            inside = [n for n in decade_nums if n in numset]
            mask = 0
            for pair in combinations(inside, 2):
                idx = PAIR_INDEX[i][tuple(sorted(pair))]
                mask |= 1 << idx
            masks.append(mask)
        return masks

    @staticmethod
    def basket_signature(origin, survivor_indexes):
        # Firma volutamente SENZA origin_id e SENZA eta':
        # stesse 5 decine + stessi 5 ambi = identico basket globale.
        parts = []
        for i in survivor_indexes:
            mask = int(origin["remaining"][i])
            idx = bit_index(mask)
            parts.append(f"{i}:{idx}")
        raw = "|".join(parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20], raw

    def mark_basket_seen(self, fingerprint):
        if fingerprint in self.seen_basket_set:
            return False
        self.seen_baskets.append(fingerprint)
        self.seen_basket_set.add(fingerprint)
        return True

    # ----------------------------
    # Telegram
    # ----------------------------

    async def tg(self, app, text):
        if not app or not CHAT_ID:
            print(text)
            return
        try:
            await app.bot.send_message(chat_id=CHAT_ID, text=text)
        except Exception as exc:
            print(f"⚠️ Telegram: {exc}")

    # ----------------------------
    # Candidati +30 / H1-H2
    # ----------------------------

    @staticmethod
    def candidate_pair(candidate):
        return PAIR_LISTS[TARGET_DECADE_INDEX][int(candidate["pair_index"])]

    async def advance_candidates(self, app, day, e, nums, mode="live", notify=True):
        if not self.candidates:
            return

        st = self._stats(mode)
        numset = set(map(int, nums))
        keep = []

        for c in self.candidates:
            pair = self.candidate_pair(c)
            hit = pair[0] in numset and pair[1] in numset
            phase = c.get("phase")

            if phase == "WAIT30":
                if hit:
                    st["canceled_wait30"] = int(st.get("canceled_wait30", 0)) + 1
                    if notify and mode == "live":
                        await self.tg(
                            app,
                            "♻️ CANDIDATO 70-79 ANNULLATO\n\n"
                            f"Ambo: {fmt_pair(pair)}\n"
                            f"Attesa raggiunta: {int(c.get('wait_count', 0))}/{EXTRA_WAIT}\n"
                            f"Uscito all'estrazione {e} | {day}.\n"
                            "Nessun H1/H2."
                        )
                    continue

                c["wait_count"] = int(c.get("wait_count", 0)) + 1
                if c["wait_count"] >= EXTRA_WAIT:
                    c["phase"] = "H1"
                    st["armed_h1"] = int(st.get("armed_h1", 0)) + 1
                    if notify and mode == "live":
                        await self.tg(
                            app,
                            f"🎯 {signal_word()} H1 ARMATO — 70-79\n\n"
                            f"Ambo: {fmt_pair(pair)}\n"
                            f"Origine: {c.get('origin_anchor_key', '-')}\n"
                            f"Basket da {BASKET_SIZE}: {c.get('basket_text', '-')}\n"
                            f"Completate altre {EXTRA_WAIT} assenze.\n"
                            f"Ultima osservata: {e} | {day}\n\n"
                            f"➡️ PROSSIMA ESTRAZIONE: {STAKE_H1:.2f}€ H1 su {fmt_pair(pair)}.\n"
                            "Se H1 perde, il bot arma H2."
                        )
                elif notify and mode == "live" and c["wait_count"] in {10, 20, 25}:
                    await self.tg(
                        app,
                        f"⏳ CANDIDATO {fmt_pair(pair)} — attesa "
                        f"{c['wait_count']}/{EXTRA_WAIT}\nNessun H1 ancora."
                    )
                keep.append(c)
                continue

            if phase == "H1":
                st["h1_plays"] = int(st.get("h1_plays", 0)) + 1
                st["cost"] = float(st.get("cost", 0.0)) + STAKE_H1
                if hit:
                    st["h1_hits"] = int(st.get("h1_hits", 0)) + 1
                    st["gross"] = float(st.get("gross", 0.0)) + AMBO_PAYOUT * STAKE_H1
                    if notify and mode == "live":
                        await self.tg(
                            app,
                            f"✅ {signal_word()} H1 HIT\n\n"
                            f"Ambo: {fmt_pair(pair)}\n"
                            f"Estrazione: {e} | {day}\n"
                            f"Puntata teorica: {STAKE_H1:.2f}€\n"
                            f"Lordo teorico: {AMBO_PAYOUT * STAKE_H1:.2f}€\n\n"
                            f"{self.stats_text(live_only=True)}"
                        )
                    continue

                st["h1_misses"] = int(st.get("h1_misses", 0)) + 1
                c["phase"] = "H2"
                if notify and mode == "live":
                    await self.tg(
                        app,
                        f"➡️ {signal_word()} H1 MISS — H2 ARMATO\n\n"
                        f"Ambo: {fmt_pair(pair)}\n"
                        f"H1: estrazione {e} | {day}\n"
                        f"➡️ PROSSIMA ESTRAZIONE: {STAKE_H2:.2f}€ H2 su {fmt_pair(pair)}.\n"
                        "Dopo H2 si chiude comunque."
                    )
                keep.append(c)
                continue

            if phase == "H2":
                st["h2_plays"] = int(st.get("h2_plays", 0)) + 1
                st["cost"] = float(st.get("cost", 0.0)) + STAKE_H2
                if hit:
                    st["h2_hits"] = int(st.get("h2_hits", 0)) + 1
                    st["gross"] = float(st.get("gross", 0.0)) + AMBO_PAYOUT * STAKE_H2
                else:
                    st["stops_h2"] = int(st.get("stops_h2", 0)) + 1

                if notify and mode == "live":
                    icon = "✅" if hit else "❌"
                    label = "H2 HIT" if hit else "STOP H2"
                    await self.tg(
                        app,
                        f"{icon} {signal_word()} {label}\n\n"
                        f"Ambo: {fmt_pair(pair)}\n"
                        f"Estrazione: {e} | {day}\n\n"
                        f"{self.stats_text(live_only=True)}"
                    )
                continue

        self.candidates = keep

    # ----------------------------
    # Origini / superstiti / basket
    # ----------------------------

    def start_new_origin(self, current_key, mode):
        self.origins.append({
            "id": int(self.next_origin_id),
            "anchor_seq": int(self.seq),
            "anchor_key": current_key,
            "remaining": [FULL_MASK] * 9,
            "survivor_since": [None] * 9,
            "survivor_since_key": [None] * 9,
        })
        self.next_origin_id += 1
        st = self._stats(mode)
        st["origins_started"] = int(st.get("origins_started", 0)) + 1

    async def advance_origins(self, app, day, e, nums, hit_masks, current_key,
                              mode="live", notify=True):
        st = self._stats(mode)
        keep = []

        for origin in self.origins:
            rem = origin["remaining"]
            since = origin["survivor_since"]
            since_key = origin["survivor_since_key"]

            for i in range(9):
                prev = int(rem[i])
                new = prev & ~int(hit_masks[i])
                if new == prev:
                    continue

                rem[i] = new
                prev_count = prev.bit_count()
                new_count = new.bit_count()

                if new_count == 1 and prev_count != 1:
                    since[i] = int(self.seq)
                    since_key[i] = current_key
                elif new_count != 1:
                    since[i] = None
                    since_key[i] = None

            survivors = [i for i in range(9) if int(rem[i]).bit_count() == 1]

            if len(survivors) == BASKET_SIZE:
                fingerprint, raw_sig = self.basket_signature(origin, survivors)
                if self.mark_basket_seen(fingerprint):
                    st["baskets5"] = int(st.get("baskets5", 0)) + 1

                    oldest = min(
                        survivors,
                        key=lambda i: (
                            int(since[i]) if since[i] is not None else 10**18,
                            i,
                        ),
                    )

                    if oldest == TARGET_DECADE_INDEX:
                        st["baskets5_oldest_target"] = int(st.get("baskets5_oldest_target", 0)) + 1
                        pair_index = bit_index(int(rem[oldest]))
                        basket_text = ", ".join(
                            f"{DECADE_NAMES[i]}:{fmt_pair(pair_from_mask(i, rem[i]))}"
                            for i in survivors
                        )

                        self.candidates.append({
                            "id": int(self.next_candidate_id),
                            "phase": "WAIT30",
                            "pair_index": int(pair_index),
                            "wait_count": 0,
                            "origin_id": int(origin["id"]),
                            "origin_anchor_key": origin.get("anchor_key"),
                            "basket_created_key": current_key,
                            "basket_created_seq": int(self.seq),
                            "basket_fingerprint": fingerprint,
                            "basket_raw": raw_sig,
                            "basket_text": basket_text,
                            "target_survivor_since_key": since_key[oldest],
                            "target_age_at_basket": int(self.seq) - int(since[oldest]),
                        })
                        self.next_candidate_id += 1
                        st["candidates"] = int(st.get("candidates", 0)) + 1

                        if notify and mode == "live":
                            target_pair = pair_from_mask(oldest, rem[oldest])
                            await self.tg(
                                app,
                                "🧩 NUOVO BASKET DA 5 — CANDIDATO 70-79\n\n"
                                f"Origine: {origin.get('anchor_key', '-')}\n"
                                f"Basket: {basket_text}\n\n"
                                f"✅ Piu' vecchio: {fmt_pair(target_pair)} della 70-79\n"
                                f"Era superstite da {int(self.seq) - int(since[oldest])} estrazioni.\n"
                                f"Ora deve restare assente per ALTRE {EXTRA_WAIT}.\n"
                                "⚠️ NON E' ANCORA H1."
                            )

            # Un'origine puo' ancora arrivare a 5 superstiti solo se almeno
            # 5 decine hanno ancora almeno un ambo mancante.
            nonzero_decades = sum(1 for mask in rem if int(mask) != 0)
            age = int(self.seq) - int(origin["anchor_seq"])
            if nonzero_decades >= BASKET_SIZE and age <= ORIGIN_MAX_AGE:
                keep.append(origin)
            else:
                st["origins_pruned"] = int(st.get("origins_pruned", 0)) + 1

        self.origins = keep

    async def process_draw(self, app, day, e, nums, mode="live", notify=True):
        if len(nums) != 20 or len(set(nums)) != 20:
            return
        if self.already_processed(day, e):
            return

        current_key = self.remember_processed(day, e)

        # 1) I candidati gia' esistenti usano il draw corrente per WAIT/H1/H2.
        await self.advance_candidates(app, day, e, nums, mode=mode, notify=notify)

        # 2) Le origini gia' esistenti eliminano gli ambi usciti nel draw corrente.
        hit_masks = self.hit_masks_for_draw(nums)
        await self.advance_origins(
            app, day, e, nums, hit_masks, current_key,
            mode=mode, notify=notify,
        )

        # 3) SOLO ORA il draw corrente diventa una nuova origine.
        #    Quindi il suo conteggio partira' dalla prossima estrazione.
        self.start_new_origin(current_key, mode)

        self.save_state(git=(mode == "live"))

    # ----------------------------
    # Warmup
    # ----------------------------

    async def run_initial_warmup(self, app=None):
        if self.warmup_done:
            return {
                "already_done": True,
                "ok": True,
                "draws": self.warmup_draws,
                "sources": self.warmup_sources,
            }

        all_records, sources = fetch_warmup_records(WARMUP_DAYS)
        records, sources, continuity = _select_latest_contiguous_warmup(all_records, sources)
        integrity_problems = list(continuity.get("problems", []) or [])
        if integrity_problems:
            return {
                "already_done": False,
                "ok": False,
                "draws": len(records),
                "sources": sources,
                "continuity_note": continuity.get("note"),
                "reason": "warmup bloccato per integrita' nel segmento utilizzabile: " + " | ".join(integrity_problems),
            }

        if len(records) < WARMUP_MIN_DRAWS:
            extra = f"; {continuity.get('note')}" if continuity.get("note") else ""
            return {
                "already_done": False,
                "ok": False,
                "draws": len(records),
                "sources": sources,
                "continuity_note": continuity.get("note"),
                "reason": f"warmup continuo insufficiente: {len(records)}<{WARMUP_MIN_DRAWS}{extra}",
            }

        # Stato completamente pulito.
        self.processed = []
        self.processed_set = set()
        self.last_draw_key = None
        self.seq = 0
        self.origins = []
        self.next_origin_id = 1
        self.seen_baskets = []
        self.seen_basket_set = set()
        self.candidates = []
        self.next_candidate_id = 1
        self.stats_warmup = self._new_stats()
        self.stats_live = self._new_stats()

        for d, e, nums in records:
            await self.process_draw(
                app=None, day=d, e=e, nums=nums,
                mode="warmup", notify=False,
            )

        self.warmup_done = True
        self.warmup_completed_at = now_txt()
        self.warmup_draws = len(records)
        self.warmup_sources = sources
        self.save_state(git=True, force_git=True)

        return {
            "already_done": False,
            "ok": True,
            "draws": len(records),
            "sources": sources,
            "continuity_note": continuity.get("note"),
            "dropped_days": continuity.get("dropped_days", []),
        }

    # ----------------------------
    # Testi stato/stats
    # ----------------------------

    def candidate_lines(self, max_rows=12):
        if not self.candidates:
            return ["• nessun candidato attivo"]
        out = []
        for c in self.candidates[:max_rows]:
            pair = self.candidate_pair(c)
            phase = c.get("phase")
            if phase == "WAIT30":
                desc = f"WAIT {int(c.get('wait_count', 0))}/{EXTRA_WAIT}"
            elif phase == "H1":
                desc = "🎯 H1 PROSSIMA"
            elif phase == "H2":
                desc = "🎯 H2 PROSSIMA"
            else:
                desc = str(phase)
            out.append(
                f"• #{c.get('id')} {fmt_pair(pair)} | {desc} | origine {c.get('origin_anchor_key', '-')}"
            )
        if len(self.candidates) > max_rows:
            out.append(f"• ... +{len(self.candidates) - max_rows} altri")
        return out

    def stats_text(self, live_only=False):
        s = self.stats_live
        h1p = int(s.get("h1_plays", 0))
        h1h = int(s.get("h1_hits", 0))
        h2p = int(s.get("h2_plays", 0))
        h2h = int(s.get("h2_hits", 0))
        stops = int(s.get("stops_h2", 0))
        closed = h1h + h2h + stops
        hits = h1h + h2h
        cost = float(s.get("cost", 0.0))
        gross = float(s.get("gross", 0.0))
        net = gross - cost

        lines = [
            "📊 FORWARD LIVE — 5 SURV / 70-79 / +30 / H1-H2",
            f"• origini attive = {len(self.origins)} | basket unici storici = {len(self.seen_basket_set)}",
            f"• nuovi basket5 live = {int(s.get('baskets5', 0))}",
            f"• oldest70-79 live = {int(s.get('baskets5_oldest_target', 0))}",
            f"• candidati live = {int(s.get('candidates', 0))} | annullati WAIT30 = {int(s.get('canceled_wait30', 0))}",
            f"• chiusi = {closed} | HIT = {hits} | STOP = {stops} | HIT H1-H2 = {safe_pct(hits, closed):.2f}%",
            f"• H1 = {h1h}/{h1p} | H2 = {h2h}/{h2p}",
            f"• costo = {cost:.2f}€ | lordo = {gross:.2f}€ | netto = {net:+.2f}€ | ROI = {safe_pct(net, cost):+.2f}%",
        ]

        if not live_only:
            w = self.stats_warmup
            wh1p = int(w.get("h1_plays", 0))
            wh1h = int(w.get("h1_hits", 0))
            wh2p = int(w.get("h2_plays", 0))
            wh2h = int(w.get("h2_hits", 0))
            wstops = int(w.get("stops_h2", 0))
            wclosed = wh1h + wh2h + wstops
            whits = wh1h + wh2h
            wc = float(w.get("cost", 0.0))
            wg = float(w.get("gross", 0.0))
            lines.extend([
                "",
                "🕰️ WARMUP DIAGNOSTICO",
                f"• draw = {self.warmup_draws}",
                f"• origini create = {int(w.get('origins_started', 0))}",
                f"• basket5 unici = {int(w.get('baskets5', 0))}",
                f"• oldest70-79 = {int(w.get('baskets5_oldest_target', 0))}",
                f"• candidati = {int(w.get('candidates', 0))} | annullati WAIT30 = {int(w.get('canceled_wait30', 0))}",
                f"• chiusi H1-H2 = {wclosed} | HIT = {whits} ({safe_pct(whits, wclosed):.2f}%)",
                f"• H1 = {wh1h}/{wh1p} | H2 = {wh2h}/{wh2p}",
                f"• ROI warmup = {safe_pct(wg - wc, wc):+.2f}%",
            ])

        return "\n".join(lines)

    def status_text(self):
        lines = [
            "🎯 5 SUPERSTITI → OLDEST 70-79 → +30 → H1/H2",
            f"• modalita' = {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}",
            f"• ultimo draw = {self.last_draw_key or '-'} | seq = {self.seq}",
            f"• origini ancora attive = {len(self.origins)}",
            f"• basket globali gia' deduplicati = {len(self.seen_basket_set)}",
            f"• candidati attivi = {len(self.candidates)}",
            f"• warmup = {'OK' if self.warmup_done else 'NO'} | {self.warmup_draws} draw",
            "",
            "🧩 CANDIDATI ATTUALI",
            *self.candidate_lines(),
            "",
            self.stats_text(),
        ]
        return "\n".join(lines)

    def menu_text(self):
        return (
            "🎯 SUPERAMBO — STRATEGIA UNICA\n\n"
            "Ogni estrazione crea una nuova origine. Dalla successiva, per quella origine, "
            "seguo i 45 ambi di tutte le 9 decine.\n"
            "Quando ci sono esattamente 5 superstiti, il basket viene deduplicato globalmente.\n"
            "Scelgo il superstite rimasto unico da piu' tempo.\n"
            f"Valido SOLO se e' della {TARGET_DECADE}.\n"
            f"Poi altre {EXTRA_WAIT} assenze; quindi {STAKE_H1:.2f}€ H1 e, se perde, {STAKE_H2:.2f}€ H2.\n\n"
            f"Modalita': {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}.\n"
            "Warmup iniziale attivo; nessun reset giornaliero.\n\n"
            "/status — stato origini/candidati\n"
            "/stats — risultati forward + warmup\n"
            "/menu — questa schermata"
        )


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

async def reply(update, text):
    if update and update.message:
        await update.message.reply_text(text)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.status_text())


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.stats_text())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.menu_text())


async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("status", "Stato origini e candidati"),
        BotCommand("stats", "Statistiche forward e warmup"),
        BotCommand("menu", "Mostra la strategia"),
    ])


# ============================================================
# SINGLE INSTANCE LOCK
# ============================================================

_LOCK_HANDLE = None


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
# STARTUP / CATCH-UP / LIVE LOOP
# ============================================================

async def notify_actionable_state(engine, app):
    actionable = [c for c in engine.candidates if c.get("phase") in {"H1", "H2"}]
    for c in actionable:
        pair = engine.candidate_pair(c)
        phase = c.get("phase")
        stake = STAKE_H1 if phase == "H1" else STAKE_H2
        await engine.tg(
            app,
            f"🎯 {signal_word()} {phase} GIA' ARMATO DALLO STATO CORRENTE\n\n"
            f"Ambo: {fmt_pair(pair)}\n"
            f"Origine: {c.get('origin_anchor_key', '-')}\n"
            f"➡️ PROSSIMA estrazione: {stake:.2f}€ {phase}."
        )


async def startup(engine, app, warmup_retry_state=None):
    """Esegue UN tentativo di startup.

    Se il warmup non e' ancora utilizzabile restituisce False ma NON chiude il bot.
    Il chiamante puo' quindi lasciare Telegram polling attivo e ritentare.
    """
    warmup_retry_state = warmup_retry_state if warmup_retry_state is not None else {}

    console_log(
        f"STARTUP tentativo warmup | logic={LOGIC_VERSION} | "
        f"days={WARMUP_DAYS} | min_draws={WARMUP_MIN_DRAWS}"
    )

    try:
        warm = await engine.run_initial_warmup(app)
    except Exception as exc:
        warm = {
            "already_done": False,
            "ok": False,
            "draws": 0,
            "sources": [],
            "continuity_note": None,
            "reason": f"eccezione warmup: {type(exc).__name__}: {exc}",
        }

    if not warm.get("already_done") and not warm.get("ok"):
        reason = str(warm.get("reason", "non disponibile"))
        sources_txt = format_warmup_sources(warm.get("sources", [])) or "-"
        continuity_txt = warm.get("continuity_note") or "nessun taglio applicato"

        console_log("WARMUP FAIL")
        console_log(f"  draws raccolti = {warm.get('draws', 0)}")
        console_log(f"  motivo = {reason}")
        console_log(f"  giorni/fonti = {sources_txt}")
        console_log(f"  continuita = {continuity_txt}")
        console_log(
            f"  il processo RESTA ATTIVO; nuovo tentativo tra {WARMUP_RETRY_SEC}s"
        )

        # Evita spam Telegram: avvisa al cambio motivo oppure almeno ogni N secondi.
        now_ts = time.time()
        last_reason = str(warmup_retry_state.get("last_reason", ""))
        last_tg_ts = float(warmup_retry_state.get("last_tg_ts", 0.0) or 0.0)
        should_tg = (
            reason != last_reason
            or now_ts - last_tg_ts >= max(60, WARMUP_FAIL_TG_MIN_SECONDS)
        )
        if should_tg:
            await engine.tg(
                app,
                "⚠️ WARMUP INIZIALE NON COMPLETATO\n\n"
                f"• estrazioni raccolte = {warm.get('draws', 0)}\n"
                f"• motivo = {reason}\n"
                f"• giorni/fonti = {sources_txt}\n"
                f"• continuita' = {continuity_txt}\n\n"
                "⏳ Il bot RESTA ACCESO e NON entra ancora nel motore live.\n"
                f"Riprova automaticamente il warmup ogni {WARMUP_RETRY_SEC} secondi.\n"
                "Nel frattempo /status e /stats restano disponibili."
            )
            warmup_retry_state["last_tg_ts"] = now_ts
            warmup_retry_state["last_reason"] = reason
        return False

    console_log(
        f"WARMUP OK | already_done={bool(warm.get('already_done'))} | "
        f"draws={warm.get('draws', engine.warmup_draws)} | "
        f"continuita={warm.get('continuity_note') or 'state/segmento valido'}"
    )
    if warm.get("sources"):
        console_log(f"WARMUP SOURCES | {format_warmup_sources(warm.get('sources', []))}")

    # Recupera eventuali draw di oggi successivi all'ultimo draw nello state.
    try:
        rows = parse_site_today()
        console_log(f"CATCH-UP iniziale | righe live lette={len(rows)}")
    except Exception as exc:
        console_log(f"CATCH-UP parser fallito | {type(exc).__name__}: {exc}")
        await engine.tg(app, f"⚠️ Parser live iniziale fallito: {exc}")
        rows = []

    unseen = [(d, e, nums) for d, e, nums in rows if not engine.already_processed(d, e)]
    unseen.sort(key=lambda x: (x[0], x[1]))
    console_log(f"CATCH-UP iniziale | unseen={len(unseen)}")
    for d, e, nums in unseen:
        # Catch-up silenzioso: mai inviare un segnale scaduto.
        await engine.process_draw(app=None, day=d, e=e, nums=nums, mode="live", notify=False)

    engine.save_state(git=True, force_git=True)

    if not warm.get("already_done"):
        source_txt = format_warmup_sources(warm.get("sources", []))
        await engine.tg(
            app,
            "🕰️ WARMUP INIZIALE COMPLETATO\n\n"
            f"• estrazioni = {warm.get('draws', 0)}\n"
            f"• giorni = {WARMUP_DAYS}\n"
            f"• fonti = {source_txt or '-'}\n"
            f"• continuita' = {warm.get('continuity_note') or 'tutti i giorni richiesti integri'}\n"
            f"• origini ancora attive = {len(engine.origins)}\n"
            f"• basket unici ricostruiti = {len(engine.seen_basket_set)}\n"
            f"• candidati ancora attivi = {len(engine.candidates)}\n\n"
            f"{engine.stats_text()}"
        )

    await engine.tg(
        app,
        "🚀 BOT 5 SUPERSTITI / 70-79 AVVIATO\n\n"
        "✅ nuova origine a ogni estrazione\n"
        "✅ 9 decine x 45 ambi seguite in parallelo\n"
        "✅ basket valido = esattamente 5 superstiti\n"
        "✅ basket identici deduplicati globalmente\n"
        "✅ scelgo il piu' vecchio\n"
        "✅ valido solo se e' 70-79\n"
        f"✅ +{EXTRA_WAIT} assenze\n"
        f"✅ H1 {STAKE_H1:.2f}€ + eventuale H2 {STAKE_H2:.2f}€\n"
        f"✅ modalita' = {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}\n"
        "✅ warmup iniziale + state persistente\n"
        f"✅ giorni conclusi richiesti = {WARMUP_FULL_DAY_DRAWS} estrazioni senza buchi\n"
        "✅ fallback automatico tra fonti\n"
        "✅ se un vecchio giorno e' incompleto usa solo il segmento continuo successivo\n"
        f"✅ se il warmup fallisce il processo resta acceso e ritenta ogni {WARMUP_RETRY_SEC}s\n\n"
        f"Candidati attivi: {len(engine.candidates)}"
    )
    await notify_actionable_state(engine, app)
    console_log("STARTUP COMPLETATO -> entro nel live_loop")
    return True


async def startup_until_ready(engine, app):
    """Resta vivo finche' il warmup non e' pronto."""
    retry_state = {}
    attempt = 0
    while True:
        attempt += 1
        console_log(f"STARTUP attempt #{attempt}")
        ok = await startup(engine, app, warmup_retry_state=retry_state)
        if ok:
            return True
        await asyncio.sleep(max(30, WARMUP_RETRY_SEC))


async def live_loop(engine, app):
    console_log(f"LIVE LOOP ATTIVO | polling sito ogni {LOOP_SEC}s")
    last_error = ""
    last_error_ts = 0.0

    while True:
        try:
            rows = parse_site_today()
            unseen = [(d, e, nums) for d, e, nums in rows if not engine.already_processed(d, e)]

            if unseen:
                unseen.sort(key=lambda x: (x[0], x[1]))

                if len(unseen) == 1:
                    d, e, nums = unseen[0]
                    await engine.process_draw(app=app, day=d, e=e, nums=nums, mode="live", notify=True)
                else:
                    for d, e, nums in unseen:
                        await engine.process_draw(app=None, day=d, e=e, nums=nums, mode="live", notify=False)
                    engine.save_state(git=True, force_git=True)
                    await notify_actionable_state(engine, app)

            await asyncio.sleep(LOOP_SEC)

        except Exception as exc:
            txt = f"{type(exc).__name__}: {exc}"
            now = time.time()
            console_log(f"⚠️ loop: {txt}")
            if txt != last_error or now - last_error_ts >= 900:
                await engine.tg(app, f"⚠️ ERRORE BOT\n{txt}\nRiprovo automaticamente.")
                last_error = txt
                last_error_ts = now
            await asyncio.sleep(max(30, LOOP_SEC))


# ============================================================
# SELF TEST
# ============================================================

def _draw_without(pair):
    excluded = set(pair)
    return [n for n in range(1, 91) if n not in excluded][:20]


def _draw_with(pair):
    out = [pair[0], pair[1]]
    for n in range(1, 91):
        if n not in out:
            out.append(n)
        if len(out) == 20:
            break
    return out


async def run_self_test():
    eng = FiveSurvivorsEngine(load=False)
    eng.save_state = lambda *a, **k: None

    # Test 1: una nuova origine NON usa il proprio draw, ma parte dal successivo.
    nums0 = list(range(1, 21))
    await eng.process_draw(None, "2099-01-01", 1, nums0, mode="warmup", notify=False)
    assert len(eng.origins) == 1
    assert all(mask == FULL_MASK for mask in eng.origins[0]["remaining"])

    # Test 2: costruiamo direttamente un'origine con 5 superstiti e 70-79 oldest.
    origin = {
        "id": 999,
        "anchor_seq": 1,
        "anchor_key": "2099-01-01#001",
        "remaining": [0] * 9,
        "survivor_since": [None] * 9,
        "survivor_since_key": [None] * 9,
    }
    setup = {
        1: ((10, 11), 80),
        2: ((20, 21), 85),
        4: ((40, 41), 90),
        7: ((70, 71), 50),
        8: ((80, 81), 95),
    }
    eng.seq = 100
    for i, (pair, since) in setup.items():
        idx = PAIR_INDEX[i][tuple(sorted(pair))]
        origin["remaining"][i] = 1 << idx
        origin["survivor_since"][i] = since
        origin["survivor_since_key"][i] = f"T#{since}"
    eng.origins = [origin]

    # Nessun hit mask: il basket viene rilevato e crea candidato.
    await eng.advance_origins(
        None, "2099-01-01", 2, _draw_without((70, 71)), [0] * 9,
        "2099-01-01#002", mode="warmup", notify=False,
    )
    assert len(eng.candidates) == 1
    assert eng.candidate_pair(eng.candidates[0]) == (70, 71)
    assert eng.candidates[0]["phase"] == "WAIT30"

    # Lo stesso basket, anche se ritrovato da un'altra origine, NON deve duplicarsi.
    clone = json.loads(json.dumps(eng._serialize_origin(origin)))
    clone = eng._deserialize_origin(clone)
    clone["id"] = 1000
    eng.origins = [origin, clone]
    old_candidates = len(eng.candidates)
    await eng.advance_origins(
        None, "2099-01-01", 3, _draw_without((70, 71)), [0] * 9,
        "2099-01-01#003", mode="warmup", notify=False,
    )
    assert len(eng.candidates) == old_candidates, "deduplica globale basket fallita"

    # 30 draw assenti -> H1 armato.
    eng.origins = []
    nohit = _draw_without((70, 71))
    for k in range(EXTRA_WAIT):
        await eng.advance_candidates(None, "2099-01-02", 10 + k, nohit, mode="warmup", notify=False)
    assert len(eng.candidates) == 1 and eng.candidates[0]["phase"] == "H1"

    # H1 miss -> H2; H2 hit -> chiusura.
    await eng.advance_candidates(None, "2099-01-02", 50, nohit, mode="warmup", notify=False)
    assert eng.candidates[0]["phase"] == "H2"
    await eng.advance_candidates(None, "2099-01-02", 51, _draw_with((70, 71)), mode="warmup", notify=False)
    assert len(eng.candidates) == 0

    s = eng.stats_warmup
    assert s["h1_plays"] == 1
    assert s["h2_plays"] == 1
    assert s["h2_hits"] == 1
    assert abs(float(s["cost"]) - (STAKE_H1 + STAKE_H2)) < 1e-9
    assert abs(float(s["gross"]) - AMBO_PAYOUT * STAKE_H2) < 1e-9

    print("SELF-TEST OK: multi-origin + dedup basket + oldest70-79 + WAIT30 + H1/H2")


# ============================================================
# MAIN
# ============================================================

async def main():
    if "--self-test" in sys.argv:
        await run_self_test()
        return

    acquire_single_instance_lock()

    if not TOKEN:
        raise RuntimeError("BOT_TOKEN mancante nelle variabili ambiente")
    if CHAT_ID is None:
        raise RuntimeError("CHAT_ID mancante/non valido nelle variabili ambiente")

    app = ApplicationBuilder().token(TOKEN).build()
    engine = FiveSurvivorsEngine()
    app.bot_data["engine"] = engine

    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("menu", cmd_menu))

    await app.initialize()
    await app.start()
    await setup_commands(app)

    # Avvia subito il polling Telegram: anche durante un warmup non pronto
    # /status, /stats e /menu restano disponibili e GitHub Actions resta in corso.
    await app.updater.start_polling(drop_pending_updates=True)
    console_log("TELEGRAM polling attivo; avvio/ritento warmup fino a successo")

    try:
        await startup_until_ready(engine, app)
        await live_loop(engine, app)
    finally:
        try:
            engine.save_state(git=True, force_git=True)
        except Exception:
            pass
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
