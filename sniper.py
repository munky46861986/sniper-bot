# ============================================================
# 🎯 SUPERAMBO — CORE + FAST + FREQ LAB SHADOW
# ============================================================
#
# MOTORE CORE — CONGELATO / INVARIATO:
#   • GAP 4 + GAP 27 esatto
#   • solo decine diverse
#   • tutti gli ambi validi, deduplicati
#   • SOLO H1 sulla prossima estrazione
#
# MOTORE FAST LAB — INVARIATO:
#   • GAP 4 + GAP 24..29
#   • solo decine diverse
#   • tutti gli ambi validi, deduplicati
#   • SOLO H1 sulla prossima estrazione
#
# FREQ LAB ENTRY-ONLY — SOLO OSSERVAZIONE:
#   • FREQ-BIRTH = numero uscito esattamente 2 volte nelle ultime 5
#                  e 2 volte nelle ultime 20
#     => quindi 0 uscite nelle 15 precedenti e accelerazione recente 2/5
#   • ENTRY-ONLY: apre UNA sessione solo al passaggio NON-FREQ -> FREQ
#     (se resta FREQ per piu' draw consecutivi NON duplica la sessione)
#   • salva lo snapshot della nascita: pattern delle 2 uscite, spacing,
#     gap precedente, frequenze 30/50 e contesto pregresso
#   • NON genera ambi e NON genera puntate
#   • segue ogni vera nascita a H1, H2, H3, H5 e H10
#   • a H5 verifica >=3 uscite nelle 5 successive
#   • a H10 verifica >=4 uscite nelle 10 successive
#
# IMPORTANTE:
#   • CORE e FAST NON vengono modificati.
#   • FAST include anche i casi CORE (gap 27), ma statistiche e risultati
#     restano completamente separati.
#   • FREQ LAB e' sempre SHADOW: zero costo, zero puntate automatiche.
#   • Nessun H2/progressione/WAIT30 viene aggiunto a CORE o FAST.
#
# WARMUP / PERSISTENZA:
#   • usa il segmento cronologico continuo piu' recente;
#   • conserva lo state CORE/FAST esistente (LOGIC_VERSION invariata);
#   • se lo state e' precedente al FREQ LAB, ricostruisce SOLO il FREQ LAB
#     dai draw recenti gia' processati, senza azzerare il forward CORE/FAST;
#   • state persistente GitHub, retry warmup senza spegnere il processo.
# ============================================================

import asyncio
import atexit
import json
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
STATE_FILE = os.path.join(BASE_DIR, "superambo_gap4_core_fast_h1_state.json")
LOCK_FILE = "/tmp/superambo_gap4_core_fast_h1.lock"

# Doppio motore = nuovo state pulito.
LOGIC_VERSION = 2

LOOP_SEC = int(os.getenv("LOOP_SEC", "60"))
WARMUP_RETRY_SEC = int(os.getenv("WARMUP_RETRY_SEC", "300"))
WARMUP_FAIL_TG_MIN_SECONDS = int(os.getenv("WARMUP_FAIL_TG_MIN_SECONDS", "900"))
WARMUP_DAYS = int(os.getenv("WARMUP_DAYS", "7"))
# Per un gap massimo 29 non servono 900 colpi: 120 colpi continui danno
# un margine ampio per inizializzare correttamente tutti i ritardi.
WARMUP_MIN_DRAWS = int(os.getenv("WARMUP_MIN_DRAWS", "120"))
WARMUP_FULL_DAY_DRAWS = int(os.getenv("WARMUP_FULL_DAY_DRAWS", "288"))
WARMUP_REQUIRE_COMPLETE_PAST_DAYS = os.getenv("WARMUP_REQUIRE_COMPLETE_PAST_DAYS", "1") != "0"
PROCESSED_MAX = int(os.getenv("PROCESSED_MAX", "12000"))

GAP_A = int(os.getenv("GAP_A", "4"))
CORE_GAP = int(os.getenv("CORE_GAP", "27"))
FAST_GAP_MIN = int(os.getenv("FAST_GAP_MIN", "24"))
FAST_GAP_MAX = int(os.getenv("FAST_GAP_MAX", "29"))

STRATEGY_ORDER = ("core", "fast")
STRATEGIES = {
    "core": {
        "label": "CORE",
        "gap_min": CORE_GAP,
        "gap_max": CORE_GAP,
        "description": f"GAP {GAP_A}+{CORE_GAP}",
    },
    "fast": {
        "label": "FAST LAB",
        "gap_min": FAST_GAP_MIN,
        "gap_max": FAST_GAP_MAX,
        "description": f"GAP {GAP_A}+{FAST_GAP_MIN}-{FAST_GAP_MAX}",
    },
}
STAKE_H1 = float(os.getenv("STAKE_H1", "1"))
AMBO_PAYOUT = float(os.getenv("AMBO_PAYOUT", "14"))
SHADOW_MODE = os.getenv("SHADOW_MODE", "1") != "0"

# FREQ LAB: laboratorio indipendente, SEMPRE shadow/diagnostico.
FREQ_LAB_ENABLED = os.getenv("FREQ_LAB_ENABLED", "1") != "0"
FREQ_NOTIFY_SIGNALS = os.getenv("FREQ_NOTIFY_SIGNALS", "1") != "0"
# I milestone possono diventare frequenti: OFF di default. Tutto resta in /freq e nello state.
FREQ_NOTIFY_MILESTONES = os.getenv("FREQ_NOTIFY_MILESTONES", "0") != "0"
# Versione separata: se cambia, viene ricostruito SOLO FREQ; CORE/FAST e relativo forward restano intatti.
FREQ_LOGIC_VERSION = 2
FREQ_HISTORY_LEN = 20
# 120 draw permettono snapshot 30/50 + gap precedente senza toccare CORE/FAST.
FREQ_HISTORY_MAX = int(os.getenv("FREQ_HISTORY_MAX", "120"))
FREQ_HORIZONS = (1, 2, 3, 5, 10)
FREQ_TARGET5_MIN_HITS = 3
FREQ_TARGET10_MIN_HITS = 4
FREQ_RECENT_MAX = int(os.getenv("FREQ_RECENT_MAX", "250"))
FREQ_RECORD_MAX = int(os.getenv("FREQ_RECORD_MAX", "5000"))
FREQ_ANALYSIS_MIN_GROUP = int(os.getenv("FREQ_ANALYSIS_MIN_GROUP", "12"))

PERSIST_GIT_STATE = os.getenv("PERSIST_GIT_STATE", "1") != "0"
GIT_COMMIT_MIN_SECONDS = int(os.getenv("GIT_COMMIT_MIN_SECONDS", "300"))
_LAST_GIT_COMMIT_TS = 0.0

DECADE_NAMES = [
    "90-9", "10-19", "20-29", "30-39", "40-49",
    "50-59", "60-69", "70-79", "80-89",
]


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
    print(f"[{now_txt()}] {message}", flush=True)


def draw_key(day, e):
    return f"{day}#{int(e):03d}"


def safe_pct(num, den):
    return (100.0 * float(num) / float(den)) if den else 0.0


def signal_word():
    return "SHADOW" if SHADOW_MODE else "PLAY"


def fmt_pair(pair):
    a, b = sorted(map(int, pair))
    return f"{a}-{b}"


def decade_index(n):
    n = int(n)
    if n == 90 or 1 <= n <= 9:
        return 0
    if 10 <= n <= 89:
        return n // 10
    raise ValueError(f"numero fuori range: {n}")


def decade_name(n):
    return DECADE_NAMES[decade_index(n)]


def different_decades(a, b):
    return decade_index(a) != decade_index(b)


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
# PERSISTENZA GIT VERIFICATA
# ============================================================

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
        rc, out, err = _git_run(["commit", "-m", "state: gap4-gap27 h1"], root)
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



# ============================================================
# MOTORE DUAL GAP — CORE 4+27 + FAST 4+24..29 / SOLO H1
# ============================================================

class DualGapEngine:
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

        # Ultima seq in cui ogni numero e' comparso. None = non ancora noto.
        self.last_seen_seq = {n: None for n in range(1, 91)}

        # Un evento H1 per strategia, valido esclusivamente sul draw successivo.
        self.pending_events = {name: None for name in STRATEGY_ORDER}

        self.recent_events = []
        self.stats_warmup = {name: self._new_stats() for name in STRATEGY_ORDER}
        self.stats_live = {name: self._new_stats() for name in STRATEGY_ORDER}

        # FREQ LAB e' completamente separato da CORE/FAST.
        self.freq_logic_version = FREQ_LOGIC_VERSION
        self.freq_bootstrap_done = False
        self.freq_history = []
        self.freq_sessions = []
        # Numeri che erano gia' nella condizione 2/5+2/20 al draw precedente.
        # Serve a creare una sessione solo sul vero ingresso NON-FREQ -> FREQ.
        self.freq_condition_active = set()
        self.freq_recent_events = []
        self.freq_uid = 0
        self.freq_stats_warmup = self._new_freq_stats()
        self.freq_stats_live = self._new_freq_stats()
        self.freq_h5_warmup = []
        self.freq_h5_live = []
        self.freq_h10_warmup = []
        self.freq_h10_live = []

        self.state_load_info = {
            "loaded": False,
            "reason": "non ancora controllato",
            "saved_at": None,
            "path": STATE_FILE,
        }
        self.last_git_status = _git_status(True, "not-run", "nessun push ancora eseguito")

        if load:
            self.load_state()

    @staticmethod
    def _new_stats():
        return {
            "draws": 0,
            "signal_draws": 0,
            "pairs_signaled": 0,
            "result_draws": 0,
            "hit_draws": 0,
            "stop_draws": 0,
            "multi_hit_draws": 0,
            "h1_plays": 0,
            "h1_hits": 0,
            "h1_misses": 0,
            "cost": 0.0,
            "gross": 0.0,
            "max_pairs_signal": 0,
        }

    @staticmethod
    def _new_freq_stats():
        return {
            "draws": 0,
            # condition_* = quante volte la condizione grezza 2/5+2/20 e' presente.
            "condition_draws": 0,
            "condition_candidates": 0,
            # signal/candidates = SOLO vere ENTRY NON-FREQ -> FREQ.
            "signal_draws": 0,
            "candidates_signaled": 0,
            "suppressed_repeats": 0,
            "max_candidates_signal": 0,
            "horizon_eval": {str(h): 0 for h in FREQ_HORIZONS},
            "horizon_hits": {str(h): 0 for h in FREQ_HORIZONS},
            "target5_eval": 0,
            "target5_success": 0,
            "target5_total_hits": 0,
            "target10_eval": 0,
            "target10_success": 0,
            "target10_total_hits": 0,
            "completed_sessions": 0,
        }

    @staticmethod
    def _merge_freq_stats(dst, raw):
        raw = raw if isinstance(raw, dict) else {}
        for key in (
            "draws", "condition_draws", "condition_candidates",
            "signal_draws", "candidates_signaled", "suppressed_repeats", "max_candidates_signal",
            "target5_eval", "target5_success", "target5_total_hits",
            "target10_eval", "target10_success", "target10_total_hits",
            "completed_sessions",
        ):
            try:
                dst[key] = int(raw.get(key, dst.get(key, 0)) or 0)
            except Exception:
                pass
        for bucket in ("horizon_eval", "horizon_hits"):
            src = raw.get(bucket, {}) if isinstance(raw.get(bucket, {}), dict) else {}
            for h in FREQ_HORIZONS:
                try:
                    dst[bucket][str(h)] = int(src.get(str(h), src.get(h, dst[bucket][str(h)])) or 0)
                except Exception:
                    pass
        return dst

    def _stats(self, mode, strategy):
        bank = self.stats_warmup if mode == "warmup" else self.stats_live
        return bank[strategy]

    def strategy_gap_values(self, strategy):
        cfg = STRATEGIES[strategy]
        return range(int(cfg["gap_min"]), int(cfg["gap_max"]) + 1)

    def _freq_stats(self, mode):
        return self.freq_stats_warmup if mode == "warmup" else self.freq_stats_live

    @staticmethod
    def _sanitize_freq_history(raw):
        out = []
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            nums = row.get("nums", []) or []
            try:
                nums = sorted(set(map(int, nums)))
            except Exception:
                continue
            if len(nums) != 20 or any(n < 1 or n > 90 for n in nums):
                continue
            out.append({"key": str(row.get("key") or ""), "nums": nums})
        return out[-max(FREQ_HISTORY_LEN, FREQ_HISTORY_MAX):]

    @staticmethod
    def _sanitize_freq_sessions(raw):
        out = []
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            try:
                n = int(row.get("number"))
                age = int(row.get("age", 0) or 0)
                hit_ages = sorted({int(x) for x in (row.get("hit_ages", []) or []) if 1 <= int(x) <= 10})
            except Exception:
                continue
            if not (1 <= n <= 90 and 0 <= age < 10):
                continue
            snap = row.get("snapshot", {}) if isinstance(row.get("snapshot", {}), dict) else {}
            out.append({
                "id": str(row.get("id") or ""),
                "number": n,
                "signal_from_key": row.get("signal_from_key"),
                "created_at": row.get("created_at"),
                "age": age,
                "hit_ages": hit_ages,
                "snapshot": dict(snap),
                "h5_hits": row.get("h5_hits"),
                "h5_success": row.get("h5_success"),
            })
        return out[-1000:]

    @staticmethod
    def _sanitize_freq_records(raw):
        out = []
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            try:
                n = int(row.get("number"))
            except Exception:
                continue
            if not 1 <= n <= 90:
                continue
            snap = row.get("snapshot", {}) if isinstance(row.get("snapshot", {}), dict) else {}
            clean = dict(row)
            clean["number"] = n
            clean["snapshot"] = dict(snap)
            out.append(clean)
        return out[-FREQ_RECORD_MAX:]

    # ----------------------------
    # Stato / serializzazione
    # ----------------------------

    def _sanitize_pending(self, raw, strategy):
        if not isinstance(raw, dict):
            return None
        allowed = set(self.strategy_gap_values(strategy))
        items = []
        seen = set()
        for x in raw.get("items", []) or []:
            try:
                n4 = int(x.get("gap4"))
                target = int(x.get("target", x.get("gap27")))
                target_gap = int(x.get("target_gap", CORE_GAP if strategy == "core" else -1))
                pair = tuple(sorted((n4, target)))
            except Exception:
                continue
            if not (1 <= n4 <= 90 and 1 <= target <= 90):
                continue
            if target_gap not in allowed:
                continue
            if not different_decades(n4, target):
                continue
            if pair in seen:
                continue
            seen.add(pair)
            items.append({
                "gap4": n4,
                "target": target,
                "target_gap": target_gap,
                "pair": list(pair),
            })
        if not items:
            return None
        return {
            "strategy": strategy,
            "signal_from_key": raw.get("signal_from_key"),
            "armed_at_seq": int(raw.get("armed_at_seq", 0) or 0),
            "created_at": raw.get("created_at"),
            "items": items,
        }

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            self.state_load_info = {
                "loaded": False,
                "reason": "state non presente nel checkout",
                "saved_at": None,
                "path": STATE_FILE,
            }
            console_log(f"STATE NON TROVATO | {STATE_FILE}")
            return False

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)

            found_logic = int(d.get("logic_version", 0) or 0)
            if found_logic != LOGIC_VERSION:
                self.state_load_info = {
                    "loaded": False,
                    "reason": f"logic_version incompatibile: file={found_logic} bot={LOGIC_VERSION}",
                    "saved_at": d.get("saved_at"),
                    "path": STATE_FILE,
                }
                console_log(f"STATE IGNORATO | {self.state_load_info['reason']}")
                return False

            self.warmup_done = bool(d.get("warmup_done", False))
            self.warmup_completed_at = d.get("warmup_completed_at")
            self.warmup_draws = int(d.get("warmup_draws", 0) or 0)
            self.warmup_sources = list(d.get("warmup_sources", []) or [])

            self.processed = list(d.get("processed", []) or [])[-PROCESSED_MAX:]
            self.processed_set = set(self.processed)
            self.last_draw_key = d.get("last_draw_key")
            self.seq = int(d.get("seq", 0) or 0)

            raw_seen = d.get("last_seen_seq", {}) or {}
            self.last_seen_seq = {}
            for n in range(1, 91):
                v = raw_seen.get(str(n), raw_seen.get(n))
                self.last_seen_seq[n] = None if v is None else int(v)

            raw_pending = d.get("pending_events", {}) or {}
            self.pending_events = {
                name: self._sanitize_pending(raw_pending.get(name), name)
                for name in STRATEGY_ORDER
            }
            self.recent_events = list(d.get("recent_events", []) or [])[-150:]

            for name in STRATEGY_ORDER:
                self.stats_warmup[name].update((d.get("stats_warmup", {}) or {}).get(name, {}) or {})
                self.stats_live[name].update((d.get("stats_live", {}) or {}).get(name, {}) or {})

            # Compatibilita' retroattiva: CORE/FAST non vengono MAI invalidati da una modifica FREQ.
            # Se lo state contiene la vecchia logica FREQ multi-sessione, resetto e ricostruisco SOLO FREQ.
            found_freq_logic = int(d.get("freq_logic_version", 1) or 1)
            if found_freq_logic != FREQ_LOGIC_VERSION:
                self._reset_freq_lab()
                console_log(
                    f"FREQ STATE DA RICOSTRUIRE | old={found_freq_logic} new={FREQ_LOGIC_VERSION} | "
                    "CORE/FAST preservati"
                )
            else:
                self.freq_logic_version = FREQ_LOGIC_VERSION
                self.freq_bootstrap_done = bool(d.get("freq_bootstrap_done", False))
                self.freq_history = self._sanitize_freq_history(d.get("freq_history", []))
                self.freq_sessions = self._sanitize_freq_sessions(d.get("freq_sessions", []))
                self.freq_condition_active = {
                    int(x) for x in (d.get("freq_condition_active", []) or [])
                    if str(x).isdigit() and 1 <= int(x) <= 90
                }
                self.freq_recent_events = list(d.get("freq_recent_events", []) or [])[-FREQ_RECENT_MAX:]
                self.freq_uid = int(d.get("freq_uid", 0) or 0)
                self._merge_freq_stats(self.freq_stats_warmup, d.get("freq_stats_warmup", {}))
                self._merge_freq_stats(self.freq_stats_live, d.get("freq_stats_live", {}))
                self.freq_h5_warmup = self._sanitize_freq_records(d.get("freq_h5_warmup", []))
                self.freq_h5_live = self._sanitize_freq_records(d.get("freq_h5_live", []))
                self.freq_h10_warmup = self._sanitize_freq_records(d.get("freq_h10_warmup", []))
                self.freq_h10_live = self._sanitize_freq_records(d.get("freq_h10_live", []))
                if len(self.freq_history) >= FREQ_HISTORY_LEN:
                    self.freq_bootstrap_done = True
                # Fallback prudente: con history valida, il set corrente impedisce una falsa nuova entry al riavvio.
                if not self.freq_condition_active and self.freq_bootstrap_done:
                    self.freq_condition_active = set(self.freq_candidates())

            self.state_load_info = {
                "loaded": True,
                "reason": "OK",
                "saved_at": d.get("saved_at"),
                "path": STATE_FILE,
            }
            console_log(
                f"STATE CARICATO | saved_at={d.get('saved_at') or '-'} | "
                f"warmup={'OK' if self.warmup_done else 'NO'} | seq={self.seq} | "
                f"last={self.last_draw_key or '-'} | "
                f"pending_core={self.pending_pairs_count('core')} | "
                f"pending_fast={self.pending_pairs_count('fast')} | "
                f"freq_ready={'SI' if self.freq_bootstrap_done else 'NO'} | "
                f"freq_active={len(self.freq_sessions)}"
            )
            return True
        except Exception as exc:
            self.state_load_info = {
                "loaded": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "saved_at": None,
                "path": STATE_FILE,
            }
            console_log(f"STATE NON CARICATO | {self.state_load_info['reason']}")
            return False

    def save_state(self, git=False, force_git=False):
        data = {
            "logic_version": LOGIC_VERSION,
            "saved_at": now_txt(),
            "warmup_done": self.warmup_done,
            "warmup_completed_at": self.warmup_completed_at,
            "warmup_draws": self.warmup_draws,
            "warmup_sources": self.warmup_sources,
            "processed": self.processed[-PROCESSED_MAX:],
            "last_draw_key": self.last_draw_key,
            "seq": self.seq,
            "last_seen_seq": {str(n): self.last_seen_seq.get(n) for n in range(1, 91)},
            "pending_events": self.pending_events,
            "recent_events": self.recent_events[-150:],
            "stats_warmup": self.stats_warmup,
            "stats_live": self.stats_live,
            "freq_logic_version": FREQ_LOGIC_VERSION,
            "freq_bootstrap_done": self.freq_bootstrap_done,
            "freq_history": self.freq_history[-max(FREQ_HISTORY_LEN, FREQ_HISTORY_MAX):],
            "freq_sessions": self.freq_sessions[-1000:],
            "freq_condition_active": sorted(self.freq_condition_active),
            "freq_recent_events": self.freq_recent_events[-FREQ_RECENT_MAX:],
            "freq_uid": self.freq_uid,
            "freq_stats_warmup": self.freq_stats_warmup,
            "freq_stats_live": self.freq_stats_live,
            "freq_h5_warmup": self.freq_h5_warmup[-FREQ_RECORD_MAX:],
            "freq_h5_live": self.freq_h5_live[-FREQ_RECORD_MAX:],
            "freq_h10_warmup": self.freq_h10_warmup[-FREQ_RECORD_MAX:],
            "freq_h10_live": self.freq_h10_live[-FREQ_RECORD_MAX:],
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
        self.seq += 1
        return k

    # ----------------------------
    # Gap e segnali
    # ----------------------------

    def current_gap(self, n):
        seen = self.last_seen_seq.get(int(n))
        if seen is None:
            return None
        return int(self.seq) - int(seen)

    def current_gaps(self):
        return {n: self.current_gap(n) for n in range(1, 91)}

    def numbers_at_gap(self, gap_value):
        gap_value = int(gap_value)
        return [n for n in range(1, 91) if self.current_gap(n) == gap_value]

    def numbers_in_gap_range(self, gap_min, gap_max):
        return [
            n for n in range(1, 91)
            if self.current_gap(n) is not None and int(gap_min) <= self.current_gap(n) <= int(gap_max)
        ]

    def update_last_seen(self, nums):
        for n in set(map(int, nums)):
            self.last_seen_seq[n] = int(self.seq)

    def build_signal_items(self, strategy):
        nums4 = self.numbers_at_gap(GAP_A)
        target_nums = self.numbers_in_gap_range(
            STRATEGIES[strategy]["gap_min"], STRATEGIES[strategy]["gap_max"]
        )
        items = []
        seen_pairs = set()

        for n4 in nums4:
            for target in target_nums:
                if n4 == target:
                    continue
                if not different_decades(n4, target):
                    continue
                pair = tuple(sorted((int(n4), int(target))))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                items.append({
                    "gap4": int(n4),
                    "target": int(target),
                    "target_gap": int(self.current_gap(target)),
                    "pair": list(pair),
                })

        items.sort(key=lambda x: (tuple(x["pair"]), x["target_gap"]))
        return items

    def pending_pairs_count(self, strategy=None):
        if strategy is None:
            return sum(self.pending_pairs_count(name) for name in STRATEGY_ORDER)
        return len((self.pending_events.get(strategy) or {}).get("items", []) or [])

    def pending_pairs(self, strategy):
        return [
            tuple(map(int, x["pair"]))
            for x in (self.pending_events.get(strategy) or {}).get("items", []) or []
        ]

    @staticmethod
    def _format_pairs(items, limit=30, with_gap=False):
        items = list(items or [])
        shown = items[:limit]
        parts = []
        for x in shown:
            pair = tuple(x.get("pair", []))
            if len(pair) != 2:
                continue
            txt = fmt_pair(pair)
            if with_gap and x.get("target_gap") is not None:
                txt += f"(g{x.get('target_gap')})"
            parts.append(txt)
        if len(items) > limit:
            parts.append(f"... +{len(items)-limit} altri")
        return ", ".join(parts) if parts else "-"

    async def tg(self, app, text):
        if not app or not CHAT_ID:
            print(text)
            return
        try:
            await app.bot.send_message(chat_id=CHAT_ID, text=text)
        except Exception as exc:
            console_log(f"⚠️ Telegram: {exc}")

    async def settle_pending(self, app, day, e, nums, mode="live", notify=True):
        numset = set(map(int, nums))
        all_results = {}
        sections = []

        for strategy in STRATEGY_ORDER:
            event = self.pending_events.get(strategy)
            if not event:
                continue

            # Consuma subito: mai doppia contabilizzazione.
            self.pending_events[strategy] = None
            items = list(event.get("items", []) or [])
            if not items:
                continue

            hits, misses = [], []
            for item in items:
                pair = tuple(map(int, item.get("pair", [])))
                if len(pair) != 2:
                    continue
                (hits if pair[0] in numset and pair[1] in numset else misses).append(item)

            plays = len(hits) + len(misses)
            hit_count = len(hits)
            st = self._stats(mode, strategy)
            st["result_draws"] = int(st.get("result_draws", 0)) + 1
            st["h1_plays"] = int(st.get("h1_plays", 0)) + plays
            st["h1_hits"] = int(st.get("h1_hits", 0)) + hit_count
            st["h1_misses"] = int(st.get("h1_misses", 0)) + len(misses)
            st["cost"] = float(st.get("cost", 0.0)) + plays * STAKE_H1
            st["gross"] = float(st.get("gross", 0.0)) + hit_count * AMBO_PAYOUT * STAKE_H1
            if hit_count:
                st["hit_draws"] = int(st.get("hit_draws", 0)) + 1
                if hit_count > 1:
                    st["multi_hit_draws"] = int(st.get("multi_hit_draws", 0)) + 1
            else:
                st["stop_draws"] = int(st.get("stop_draws", 0)) + 1

            draw_cost = plays * STAKE_H1
            draw_gross = hit_count * AMBO_PAYOUT * STAKE_H1
            draw_net = draw_gross - draw_cost
            result = {
                "strategy": strategy,
                "signal_from": event.get("signal_from_key"),
                "plays": plays,
                "hits": hit_count,
                "misses": len(misses),
                "cost": draw_cost,
                "gross": draw_gross,
                "net": draw_net,
                "hit_items": hits,
                "miss_items": misses,
            }
            all_results[strategy] = result

            self.recent_events.append({
                "type": "RESULT",
                "strategy": strategy,
                "at": draw_key(day, e),
                "signal_from": event.get("signal_from_key"),
                "plays": plays,
                "hits": hit_count,
                "net": draw_net,
            })

            cfg = STRATEGIES[strategy]
            icon = "✅" if hit_count else "❌"
            title = "HIT H1" if hit_count else "STOP H1"
            sections.extend([
                f"{icon} {cfg['label']} — {title}",
                f"Segnale da: {event.get('signal_from_key', '-')}",
                f"Ambi: {plays} | HIT: {hit_count} | MISS: {len(misses)}",
                f"✅ {self._format_pairs(hits, with_gap=(strategy == 'fast'))}",
                f"❌ {self._format_pairs(misses, with_gap=(strategy == 'fast'))}",
                f"Costo: {draw_cost:.2f}€ | lordo: {draw_gross:.2f}€ | netto: {draw_net:+.2f}€",
                f"Forward {cfg['label']}: {self.live_summary_one_line(strategy)}",
                "",
            ])

        self.recent_events = self.recent_events[-150:]

        if notify and mode == "live" and all_results:
            await self.tg(
                app,
                f"📌 {signal_word()} RISULTATI H1 — DUAL GAP\n"
                f"Risultato: {draw_key(day, e)}\n\n" +
                "\n".join(sections).rstrip() +
                "\n\nℹ️ FAST include il CORE: non sommare i due costi come portafogli indipendenti."
            )

        return all_results or None

    async def arm_from_current_gaps(self, app, current_key, mode="live", notify=True):
        armed = {}
        sections = []
        nums4_all = self.numbers_at_gap(GAP_A)

        for strategy in STRATEGY_ORDER:
            items = self.build_signal_items(strategy)
            if not items:
                self.pending_events[strategy] = None
                continue

            self.pending_events[strategy] = {
                "strategy": strategy,
                "signal_from_key": current_key,
                "armed_at_seq": int(self.seq),
                "created_at": now_txt(),
                "items": items,
            }
            armed[strategy] = self.pending_events[strategy]

            st = self._stats(mode, strategy)
            st["signal_draws"] = int(st.get("signal_draws", 0)) + 1
            st["pairs_signaled"] = int(st.get("pairs_signaled", 0)) + len(items)
            st["max_pairs_signal"] = max(int(st.get("max_pairs_signal", 0) or 0), len(items))

            target_by_gap = {}
            for item in items:
                target_by_gap.setdefault(int(item["target_gap"]), set()).add(int(item["target"]))
            self.recent_events.append({
                "type": "SIGNAL",
                "strategy": strategy,
                "at": current_key,
                "pairs": len(items),
                "gap4": sorted({int(x["gap4"]) for x in items}),
                "targets": {str(g): sorted(v) for g, v in sorted(target_by_gap.items())},
            })

            cfg = STRATEGIES[strategy]
            targets_txt = " | ".join(
                f"g{g}: {','.join(map(str, sorted(vals)))}"
                for g, vals in sorted(target_by_gap.items())
            ) or "-"
            sections.extend([
                f"🎯 {cfg['label']} — {cfg['description']}",
                f"Gap {GAP_A}: {', '.join(map(str, sorted({int(x['gap4']) for x in items}))) or '-'}",
                f"Target: {targets_txt}",
                f"Ambi validi ({len(items)}): {self._format_pairs(items, with_gap=(strategy == 'fast'))}",
                f"Costo teorico H1: {len(items)*STAKE_H1:.2f}€",
                "",
            ])

        self.recent_events = self.recent_events[-150:]

        if notify and mode == "live" and armed:
            await self.tg(
                app,
                f"🎯 {signal_word()} H1 ARMATO — DUAL GAP\n\n"
                f"Segnale da: {current_key}\n"
                f"Regola comune: decine diverse / SOLO H1\n\n" +
                "\n".join(sections).rstrip() +
                f"\n\n➡️ PROSSIMA estrazione: {STAKE_H1:.2f}€ H1 per ambo in ciascun laboratorio.\n"
                "Nessun H2, nessuna progressione.\n"
                "ℹ️ FAST 24-29 include anche gli ambi CORE a gap27: statistiche separate."
            )

        return armed or None

    # ----------------------------
    # FREQ LAB — ENTRY-ONLY 2/5 e 2/20
    # ----------------------------

    def _reset_freq_lab(self):
        self.freq_logic_version = FREQ_LOGIC_VERSION
        self.freq_bootstrap_done = False
        self.freq_history = []
        self.freq_sessions = []
        self.freq_condition_active = set()
        self.freq_recent_events = []
        self.freq_uid = 0
        self.freq_stats_warmup = self._new_freq_stats()
        self.freq_stats_live = self._new_freq_stats()
        self.freq_h5_warmup = []
        self.freq_h5_live = []
        self.freq_h10_warmup = []
        self.freq_h10_live = []

    def freq_append_history(self, current_key, nums):
        row = {"key": str(current_key), "nums": sorted(set(map(int, nums)))}
        self.freq_history.append(row)
        self.freq_history = self.freq_history[-max(FREQ_HISTORY_LEN, FREQ_HISTORY_MAX):]
        if len(self.freq_history) >= FREQ_HISTORY_LEN:
            self.freq_bootstrap_done = True

    def freq_candidates(self):
        """Condizione grezza corrente: 2 presenze nelle ultime 5 E 2 nelle ultime 20."""
        if not FREQ_LAB_ENABLED or len(self.freq_history) < FREQ_HISTORY_LEN:
            return []
        last20 = self.freq_history[-20:]
        last5 = self.freq_history[-5:]
        out = []
        for n in range(1, 91):
            c20 = sum(1 for row in last20 if n in set(row.get("nums", [])))
            c5 = sum(1 for row in last5 if n in set(row.get("nums", [])))
            if c5 == 2 and c20 == 2:
                out.append(n)
        return out

    def freq_entry_snapshot(self, n, current_key):
        """Fotografia PRE-FUTURO della vera nascita FREQ. Nessun leakage."""
        n = int(n)
        hist = list(self.freq_history)
        total = len(hist)

        def cnt(w):
            rows = hist[-min(int(w), total):]
            return sum(1 for row in rows if n in set(row.get("nums", [])))

        last5 = hist[-5:] if total >= 5 else hist
        # Convenzione leggibile: -1 = draw del segnale, -2 = precedente, ... -5.
        offsets = []
        base = len(last5)
        for i, row in enumerate(last5):
            if n in set(row.get("nums", [])):
                offsets.append(-(base - i))
        offsets = sorted(offsets)
        pattern5 = "/".join(str(x) for x in offsets) if offsets else "-"
        spacing = abs(offsets[-1] - offsets[-2]) if len(offsets) == 2 else None
        current_hit = (-1 in offsets)

        # Prima delle due uscite recenti: quante ASSENZE consecutive separavano la precedente uscita?
        hit_idx = [i for i, row in enumerate(hist) if n in set(row.get("nums", []))]
        pre_absences = None
        prev_distance = None
        if len(hit_idx) >= 3:
            first_recent_idx = hit_idx[-2]
            prev_idx = hit_idx[-3]
            prev_distance = first_recent_idx - prev_idx
            pre_absences = max(0, prev_distance - 1)

        c20 = cnt(20)
        c30 = cnt(30) if total >= 30 else None
        c50 = cnt(50) if total >= 50 else None
        extra_20_30 = (c30 - c20) if c30 is not None else None
        extra_20_50 = (c50 - c20) if c50 is not None else None

        return {
            "signal_key": str(current_key),
            "history_len": total,
            "pattern5": pattern5,
            "offsets5": offsets,
            "spacing": spacing,
            "current_hit": bool(current_hit),
            "c5": cnt(5),
            "c10": cnt(10),
            "c20": c20,
            "c30": c30,
            "c50": c50,
            "extra_20_30": extra_20_30,
            "extra_20_50": extra_20_50,
            "pre_absences": pre_absences,
            "prev_distance": prev_distance,
            "decade": decade_index(n),
        }

    def _freq_record_bank(self, mode, horizon):
        if int(horizon) == 5:
            return self.freq_h5_warmup if mode == "warmup" else self.freq_h5_live
        return self.freq_h10_warmup if mode == "warmup" else self.freq_h10_live

    async def settle_freq_sessions(self, app, day, e, nums, mode="live", notify=True):
        if not FREQ_LAB_ENABLED or not self.freq_sessions:
            return None

        numset = set(map(int, nums))
        st = self._freq_stats(mode)
        survivors = []
        milestone_lines = []
        current_key = draw_key(day, e)

        for session in list(self.freq_sessions):
            age = int(session.get("age", 0) or 0) + 1
            session["age"] = age
            n = int(session["number"])
            hit_now = n in numset
            hit_ages = list(session.get("hit_ages", []) or [])
            if hit_now and age not in hit_ages:
                hit_ages.append(age)
                hit_ages.sort()
            session["hit_ages"] = hit_ages

            if age in FREQ_HORIZONS:
                h = str(age)
                st["horizon_eval"][h] = int(st["horizon_eval"].get(h, 0)) + 1
                if hit_now:
                    st["horizon_hits"][h] = int(st["horizon_hits"].get(h, 0)) + 1

            hits_so_far = len([x for x in hit_ages if x <= age])

            if age == 5:
                success5 = hits_so_far >= FREQ_TARGET5_MIN_HITS
                session["h5_hits"] = hits_so_far
                session["h5_success"] = bool(success5)
                st["target5_eval"] = int(st.get("target5_eval", 0)) + 1
                st["target5_success"] = int(st.get("target5_success", 0)) + int(success5)
                st["target5_total_hits"] = int(st.get("target5_total_hits", 0)) + hits_so_far
                rec5 = {
                    "id": session.get("id"), "number": n,
                    "signal_from_key": session.get("signal_from_key"),
                    "evaluated_at": current_key, "hits5": hits_so_far,
                    "success5": bool(success5),
                    "hit_ages5": [x for x in hit_ages if x <= 5],
                    "snapshot": dict(session.get("snapshot", {}) or {}),
                }
                bank5 = self._freq_record_bank(mode, 5)
                bank5.append(rec5)
                del bank5[:-FREQ_RECORD_MAX]
                self.freq_recent_events.append({
                    "type": "FREQ_H5", "at": current_key, "id": session.get("id"),
                    "number": n, "hits_5": hits_so_far, "success": bool(success5),
                })
                if FREQ_NOTIFY_MILESTONES and notify and mode == "live":
                    milestone_lines.append(
                        f"H5 | #{n} | uscite={hits_so_far}/5 | "
                        f"target >=3: {'✅' if success5 else '❌'}"
                    )

            if age == 10:
                hits10 = len([x for x in hit_ages if x <= 10])
                success10 = hits10 >= FREQ_TARGET10_MIN_HITS
                st["target10_eval"] = int(st.get("target10_eval", 0)) + 1
                st["target10_success"] = int(st.get("target10_success", 0)) + int(success10)
                st["target10_total_hits"] = int(st.get("target10_total_hits", 0)) + hits10
                st["completed_sessions"] = int(st.get("completed_sessions", 0)) + 1
                rec10 = {
                    "id": session.get("id"), "number": n,
                    "signal_from_key": session.get("signal_from_key"),
                    "evaluated_at": current_key, "hits10": hits10,
                    "success10": bool(success10),
                    "hit_ages10": [x for x in hit_ages if x <= 10],
                    "h5_hits": session.get("h5_hits"),
                    "h5_success": session.get("h5_success"),
                    "snapshot": dict(session.get("snapshot", {}) or {}),
                }
                bank10 = self._freq_record_bank(mode, 10)
                bank10.append(rec10)
                del bank10[:-FREQ_RECORD_MAX]
                self.freq_recent_events.append({
                    "type": "FREQ_H10", "at": current_key, "id": session.get("id"),
                    "number": n, "hits_10": hits10, "success": bool(success10),
                })
                if FREQ_NOTIFY_MILESTONES and notify and mode == "live":
                    milestone_lines.append(
                        f"H10 | #{n} | uscite={hits10}/10 | "
                        f"target >=4: {'✅' if success10 else '❌'}"
                    )
            else:
                survivors.append(session)

        self.freq_sessions = survivors[-1000:]
        self.freq_recent_events = self.freq_recent_events[-FREQ_RECENT_MAX:]

        if milestone_lines and notify and mode == "live":
            await self.tg(
                app,
                "🧪 FREQ LAB — MILESTONE SHADOW\n"
                f"Risultato: {current_key}\n\n" +
                "\n".join(milestone_lines) +
                "\n\nZero puntate: laboratorio statistico indipendente da CORE/FAST."
            )
        return milestone_lines or None

    async def arm_freq_birth(self, app, current_key, mode="live", notify=True):
        if not FREQ_LAB_ENABLED:
            return []

        current = set(self.freq_candidates())
        previous = set(self.freq_condition_active)
        entries = sorted(current - previous)
        repeats = sorted(current & previous)
        # Aggiorno SEMPRE lo stato della condizione, anche se non ci sono nuove entry.
        self.freq_condition_active = current

        st = self._freq_stats(mode)
        if current:
            st["condition_draws"] = int(st.get("condition_draws", 0)) + 1
            st["condition_candidates"] = int(st.get("condition_candidates", 0)) + len(current)
        if repeats:
            st["suppressed_repeats"] = int(st.get("suppressed_repeats", 0)) + len(repeats)
        if not entries:
            return []

        st["signal_draws"] = int(st.get("signal_draws", 0)) + 1
        st["candidates_signaled"] = int(st.get("candidates_signaled", 0)) + len(entries)
        st["max_candidates_signal"] = max(int(st.get("max_candidates_signal", 0)), len(entries))

        created = []
        for n in entries:
            self.freq_uid += 1
            snapshot = self.freq_entry_snapshot(n, current_key)
            session = {
                "id": f"FREQ-{self.freq_uid:07d}",
                "number": int(n),
                "signal_from_key": current_key,
                "created_at": now_txt(),
                "age": 0,
                "hit_ages": [],
                "snapshot": snapshot,
                "h5_hits": None,
                "h5_success": None,
            }
            self.freq_sessions.append(session)
            created.append(session)

        self.freq_sessions = self.freq_sessions[-1000:]
        self.freq_recent_events.append({
            "type": "FREQ_ENTRY", "at": current_key,
            "numbers": list(entries), "count": len(entries),
            "suppressed_same_episode": list(repeats),
        })
        self.freq_recent_events = self.freq_recent_events[-FREQ_RECENT_MAX:]

        if notify and mode == "live" and FREQ_NOTIFY_SIGNALS:
            detail = []
            for x in created:
                snap = x.get("snapshot", {})
                pg = snap.get("pre_absences")
                pg_txt = "?" if pg is None else str(pg)
                detail.append(
                    f"#{x['number']} pattern={snap.get('pattern5','-')} "
                    f"spacing={snap.get('spacing','?')} pre-gap={pg_txt}"
                )
            await self.tg(
                app,
                "🧪 FREQ LAB SHADOW — VERA FREQ-BIRTH ENTRY\n\n"
                f"Segnale da: {current_key}\n"
                f"Nuove entry: {', '.join(map(str, entries))}\n"
                + ("\n".join(detail) + "\n\n" if detail else "\n") +
                "Regola: 2 uscite nelle ultime 5 e 2 nelle ultime 20.\n"
                "ENTRY-ONLY: se il numero resta nella condizione nei draw successivi NON viene riaperto.\n\n"
                "Osservazione: H1 / H2 / H3 / H5 / H10.\n"
                "Target H5: >=3 uscite nelle prossime 5.\n"
                "Target H10: >=4 uscite nelle prossime 10.\n\n"
                "⚠️ ZERO puntate: non modifica CORE o FAST."
            )
        return created

    async def rebuild_freq_lab_from_records(self, records):
        # Ricostruisce SOLO il laboratorio FREQ ENTRY-ONLY; CORE/FAST non vengono toccati.
        self._reset_freq_lab()
        for d, e, nums in list(records or []):
            clean = list(map(int, nums))
            if len(clean) != 20 or len(set(clean)) != 20:
                continue
            self.freq_stats_warmup["draws"] = int(self.freq_stats_warmup.get("draws", 0)) + 1
            await self.settle_freq_sessions(None, d, e, clean, mode="warmup", notify=False)
            current_key = draw_key(d, e)
            self.freq_append_history(current_key, clean)
            await self.arm_freq_birth(None, current_key, mode="warmup", notify=False)
        self.freq_bootstrap_done = len(self.freq_history) >= FREQ_HISTORY_LEN
        return self.freq_bootstrap_done

    async def ensure_freq_lab_bootstrap(self):
        if not FREQ_LAB_ENABLED:
            return {"ok": True, "disabled": True, "draws": 0}
        if self.freq_bootstrap_done and len(self.freq_history) >= FREQ_HISTORY_LEN:
            return {"ok": True, "already_done": True, "draws": len(self.freq_history)}

        try:
            all_records, sources = fetch_warmup_records(WARMUP_DAYS)
            records, _, continuity = _select_latest_contiguous_warmup(all_records, sources)
            # Per uno state CORE/FAST gia' attivo usiamo SOLO draw che risultano gia' processati.
            if self.processed_set:
                usable = [
                    (d, e, nums) for d, e, nums in records
                    if draw_key(d, e) in self.processed_set
                ]
            else:
                usable = list(records)
            usable.sort(key=lambda x: (x[0], x[1]))
            if len(usable) > 800:
                usable = usable[-800:]
            ok = await self.rebuild_freq_lab_from_records(usable)
            return {
                "ok": bool(ok),
                "already_done": False,
                "draws": len(usable),
                "continuity_note": continuity.get("note"),
                "reason": None if ok else f"storico FREQ insufficiente: {len(usable)} draw",
            }
        except Exception as exc:
            return {
                "ok": False, "already_done": False, "draws": 0,
                "reason": f"{type(exc).__name__}: {exc}",
            }

    def freq_active_text(self, limit=25):
        if not self.freq_sessions:
            return "-"
        rows = []
        for s in self.freq_sessions[:limit]:
            snap = s.get("snapshot", {}) or {}
            rows.append(
                f"{s.get('id')} #{s.get('number')} da {s.get('signal_from_key')} "
                f"| H{s.get('age', 0)}/10 | hit={len(s.get('hit_ages', []) or [])} "
                f"| p5={snap.get('pattern5','-')}"
            )
        if len(self.freq_sessions) > limit:
            rows.append(f"... +{len(self.freq_sessions)-limit} altri")
        return "\n".join(rows)

    def _freq_stats_block(self, title, st):
        lines = [title]
        lines.append(f"• draw elaborati = {int(st.get('draws', 0))}")
        lines.append(
            f"• condizione grezza = {int(st.get('condition_draws', 0))} draw | "
            f"presenze-candidato = {int(st.get('condition_candidates', 0))}"
        )
        lines.append(
            f"• VERE ENTRY = {int(st.get('signal_draws', 0))} draw | "
            f"candidati entry = {int(st.get('candidates_signaled', 0))} | "
            f"repliche stesso episodio scartate = {int(st.get('suppressed_repeats', 0))}"
        )
        lines.append(f"• max nuove entry nello stesso draw = {int(st.get('max_candidates_signal', 0))}")
        for h in FREQ_HORIZONS:
            ev = int(st.get("horizon_eval", {}).get(str(h), 0))
            hi = int(st.get("horizon_hits", {}).get(str(h), 0))
            lines.append(f"• H{h} esatto = {hi}/{ev} ({safe_pct(hi, ev):.2f}%)")
        e5 = int(st.get("target5_eval", 0))
        s5 = int(st.get("target5_success", 0))
        e10 = int(st.get("target10_eval", 0))
        s10 = int(st.get("target10_success", 0))
        lines.extend([
            f"• TARGET H5 >=3/5 = {s5}/{e5} ({safe_pct(s5, e5):.2f}%) | media uscite={safe_pct(st.get('target5_total_hits', 0), e5)/100.0:.3f}/5",
            f"• TARGET H10 >=4/10 = {s10}/{e10} ({safe_pct(s10, e10):.2f}%) | media uscite={safe_pct(st.get('target10_total_hits', 0), e10)/100.0:.3f}/10",
            f"• sessioni completate H10 = {int(st.get('completed_sessions', 0))}",
        ])
        return lines

    @staticmethod
    def _freq_gap_bucket(v):
        if v is None:
            return "?"
        v = int(v)
        if v <= 4:
            return "0-4"
        if v <= 9:
            return "5-9"
        if v <= 14:
            return "10-14"
        if v <= 19:
            return "15-19"
        return "20+"

    @staticmethod
    def _freq_group_lines(records, key_fn, limit=8):
        groups = {}
        for r in records:
            key = str(key_fn(r))
            g = groups.setdefault(key, [0, 0])
            g[0] += 1
            g[1] += int(bool(r.get("success5")))
        rows = sorted(groups.items(), key=lambda kv: (-kv[1][0], kv[0]))[:limit]
        return [f"• {k}: {suc}/{n} = {safe_pct(suc,n):.2f}%" for k, (n, suc) in rows]

    def _freq_rule_catalog(self):
        # Catalogo PREDEFINITO: evita di inventare una soglia diversa per ogni singolo HIT.
        return [
            ("seconda uscita nel draw-segnale", lambda s: bool(s.get("current_hit"))),
            ("seconda uscita NON nel draw-segnale", lambda s: not bool(s.get("current_hit"))),
            ("spacing=1", lambda s: s.get("spacing") == 1),
            ("spacing=2", lambda s: s.get("spacing") == 2),
            ("spacing=3", lambda s: s.get("spacing") == 3),
            ("spacing=4", lambda s: s.get("spacing") == 4),
            ("pre-gap >=10", lambda s: s.get("pre_absences") is not None and int(s.get("pre_absences")) >= 10),
            ("pre-gap >=15", lambda s: s.get("pre_absences") is not None and int(s.get("pre_absences")) >= 15),
            ("pre-gap >=20", lambda s: s.get("pre_absences") is not None and int(s.get("pre_absences")) >= 20),
            ("pre-gap >=10 + ultimo draw", lambda s: bool(s.get("current_hit")) and s.get("pre_absences") is not None and int(s.get("pre_absences")) >= 10),
            ("pre-gap >=15 + ultimo draw", lambda s: bool(s.get("current_hit")) and s.get("pre_absences") is not None and int(s.get("pre_absences")) >= 15),
            ("spacing<=2 + pre-gap>=10", lambda s: s.get("spacing") is not None and int(s.get("spacing")) <= 2 and s.get("pre_absences") is not None and int(s.get("pre_absences")) >= 10),
            ("nessuna uscita extra 20-30", lambda s: s.get("extra_20_30") == 0),
            (">=1 uscita extra 20-30", lambda s: s.get("extra_20_30") is not None and int(s.get("extra_20_30")) >= 1),
            ("<=1 uscita extra 20-50", lambda s: s.get("extra_20_50") is not None and int(s.get("extra_20_50")) <= 1),
            (">=2 uscite extra 20-50", lambda s: s.get("extra_20_50") is not None and int(s.get("extra_20_50")) >= 2),
        ]

    def _freq_validated_rules(self, records):
        if len(records) < 30:
            return []
        cut = max(1, int(len(records) * 0.60))
        train, valid = records[:cut], records[cut:]
        min_train = max(FREQ_ANALYSIS_MIN_GROUP, 8)
        min_valid = max(6, int(FREQ_ANALYSIS_MIN_GROUP * 0.5))
        out = []
        for label, rule in self._freq_rule_catalog():
            tr = [r for r in train if rule(r.get("snapshot", {}) or {})]
            va = [r for r in valid if rule(r.get("snapshot", {}) or {})]
            if len(tr) < min_train or len(va) < min_valid:
                continue
            trs = sum(int(bool(r.get("success5"))) for r in tr)
            vas = sum(int(bool(r.get("success5"))) for r in va)
            trp = safe_pct(trs, len(tr))
            vap = safe_pct(vas, len(va))
            out.append((label, len(tr), trs, trp, len(va), vas, vap))
        # Ordino per validation, poi numerosita'. Non significa che sia gia' una regola valida.
        return sorted(out, key=lambda x: (-x[6], -x[4], -x[3]))

    def freq_analysis_text(self):
        warm = list(self.freq_h5_warmup)
        live = list(self.freq_h5_live)
        ws = sum(int(bool(r.get("success5"))) for r in warm)
        ls = sum(int(bool(r.get("success5"))) for r in live)
        lines = [
            "🔬 FREQ ENTRY-ONLY — ANALISI NASCITE",
            "• ogni numero conta UNA volta finche' non esce dalla condizione e poi rientra",
            "• baseline teorica >=3/5 ≈ 7.64%",
            f"• WARMUP H5 = {ws}/{len(warm)} ({safe_pct(ws,len(warm)):.2f}%)",
            f"• FORWARD H5 = {ls}/{len(live)} ({safe_pct(ls,len(live)):.2f}%)",
            "",
        ]
        if not warm:
            lines.append("Warmup ENTRY-ONLY non ancora disponibile: riavvia/lascia completare il bootstrap FREQ.")
            return "\n".join(lines)

        lines.append("🧬 PATTERN DELLE 2 USCITE NELLE ULTIME 5")
        lines.extend(self._freq_group_lines(warm, lambda r: (r.get("snapshot", {}) or {}).get("pattern5", "?"), limit=10))
        lines.extend(["", "⏱ PRE-GAP (assenze prima della prima delle 2 uscite)"] )
        lines.extend(self._freq_group_lines(warm, lambda r: self._freq_gap_bucket((r.get("snapshot", {}) or {}).get("pre_absences")), limit=6))

        rules = self._freq_validated_rules(warm)
        lines.extend(["", "🧪 SPLIT CRONOLOGICO 60/40 — FILTRI PREDEFINITI"] )
        robust = []
        for x in rules:
            label, tn, ts, tp, vn, vs, vp = x
            # Per essere evidenziato deve stare sopra il teorico in ENTRAMBE le meta'.
            if tp > 7.64 and vp > 7.64:
                robust.append(x)
        if robust:
            for label, tn, ts, tp, vn, vs, vp in robust[:6]:
                lines.append(f"• {label}: TRAIN {ts}/{tn}={tp:.1f}% | VALID {vs}/{vn}={vp:.1f}%")
        else:
            lines.append("• Nessun filtro con campione minimo resta >7.64% sia in TRAIN sia in VALIDATION.")

        lines.extend([
            "",
            "⚠️ Lettura: anche un filtro evidenziato resta esplorativo; serve il forward indipendente prima di usarlo.",
            "CORE e FAST non sono coinvolti in questa analisi.",
        ])
        return "\n".join(lines)

    def freq_stats_text(self):
        if not FREQ_LAB_ENABLED:
            return "🧪 FREQ LAB disabilitato (FREQ_LAB_ENABLED=0)."
        candidates_now = self.freq_candidates()
        lines = [
            "🧪 FREQ LAB SHADOW — ENTRY-ONLY 2/5 + 2/20",
            "• zero puntate / nessun impatto su CORE e FAST",
            f"• FREQ logic = v{FREQ_LOGIC_VERSION} ENTRY-ONLY",
            f"• bootstrap = {'OK' if self.freq_bootstrap_done else 'IN COSTRUZIONE'} | storico={len(self.freq_history)}/{FREQ_HISTORY_LEN}+",
            f"• in condizione adesso = {', '.join(map(str, candidates_now)) or '-'}",
            f"• sessioni vere attive = {len(self.freq_sessions)}",
            "",
        ]
        lines.extend(self._freq_stats_block("📊 FORWARD FREQ LAB", self.freq_stats_live))
        lines.extend(["", *self._freq_stats_block("🕰️ WARMUP FREQ LAB", self.freq_stats_warmup)])
        lines.extend([
            "",
            "🎯 SESSIONI ATTIVE",
            self.freq_active_text(),
            "",
            "Baseline teorica singolo H1 = 22.22%; >=3/5 ≈ 7.64%; >=4/10 ≈ 16.32%.",
            "Usa /freqanalysis per confrontare pattern, pre-gap e split cronologico 60/40.",
        ])
        return "\n".join(lines)

    async def process_draw(self, app, day, e, nums, mode="live", notify=True, persist=True):
        clean = list(map(int, nums))
        if len(clean) != 20 or len(set(clean)) != 20 or any(n < 1 or n > 90 for n in clean):
            return None
        if self.already_processed(day, e):
            return None

        current_key = self.remember_processed(day, e)
        for strategy in STRATEGY_ORDER:
            st = self._stats(mode, strategy)
            st["draws"] = int(st.get("draws", 0)) + 1
        if FREQ_LAB_ENABLED:
            fst = self._freq_stats(mode)
            fst["draws"] = int(fst.get("draws", 0)) + 1

        # 1) Chiude gli H1 CORE/FAST armati dal draw precedente.
        results = await self.settle_pending(app, day, e, clean, mode=mode, notify=notify)
        # 1b) Avanza e valuta le sessioni FREQ nate nei draw precedenti.
        freq_results = await self.settle_freq_sessions(app, day, e, clean, mode=mode, notify=notify)
        # 2) Aggiorna i gap CORE/FAST col draw corrente.
        self.update_last_seen(clean)
        # 2b) Aggiorna lo storico FREQ col draw corrente.
        if FREQ_LAB_ENABLED:
            self.freq_append_history(current_key, clean)
        # 3) Arma CORE e FAST per il draw successivo — LOGICA INVARIATA.
        signals = await self.arm_from_current_gaps(app, current_key, mode=mode, notify=notify)
        # 3b) Apre nuove osservazioni FREQ-BIRTH — solo shadow.
        freq_signals = await self.arm_freq_birth(app, current_key, mode=mode, notify=notify)

        if persist:
            self.save_state(git=(mode == "live"))

        return {
            "results": results, "signals": signals,
            "freq_results": freq_results, "freq_signals": freq_signals,
        }

    # ----------------------------
    # Warmup
    # ----------------------------

    def _reset_for_warmup(self):
        self.processed = []
        self.processed_set = set()
        self.last_draw_key = None
        self.seq = 0
        self.last_seen_seq = {n: None for n in range(1, 91)}
        self.pending_events = {name: None for name in STRATEGY_ORDER}
        self.recent_events = []
        self.stats_warmup = {name: self._new_stats() for name in STRATEGY_ORDER}
        self.stats_live = {name: self._new_stats() for name in STRATEGY_ORDER}
        self._reset_freq_lab()

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

        self._reset_for_warmup()
        for d, e, nums in records:
            await self.process_draw(
                app=None, day=d, e=e, nums=nums,
                mode="warmup", notify=False, persist=False,
            )

        if FREQ_LAB_ENABLED:
            self.freq_bootstrap_done = len(self.freq_history) >= FREQ_HISTORY_LEN

        unknown = [n for n in range(1, 91) if self.last_seen_seq.get(n) is None]
        if unknown:
            self._reset_for_warmup()
            return {
                "already_done": False,
                "ok": False,
                "draws": len(records),
                "sources": sources,
                "continuity_note": continuity.get("note"),
                "reason": f"warmup senza ultima uscita nota per: {unknown}",
            }

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
    # Testi / diagnostica
    # ----------------------------

    def current_gap_lists(self):
        nums4 = self.numbers_at_gap(GAP_A)
        core = self.numbers_at_gap(CORE_GAP)
        fast = {g: self.numbers_at_gap(g) for g in range(FAST_GAP_MIN, FAST_GAP_MAX + 1)}
        return nums4, core, fast

    def fast_targets_text(self):
        _, _, fast = self.current_gap_lists()
        parts = [f"g{g}: {','.join(map(str, nums))}" for g, nums in fast.items() if nums]
        return " | ".join(parts) if parts else "-"

    def pending_text(self):
        blocks = []
        for strategy in STRATEGY_ORDER:
            cfg = STRATEGIES[strategy]
            event = self.pending_events.get(strategy)
            if not event:
                blocks.append(f"• {cfg['label']}: nessun H1 armato")
                continue
            items = event.get("items", []) or []
            target_by_gap = {}
            for x in items:
                target_by_gap.setdefault(int(x["target_gap"]), set()).add(int(x["target"]))
            targets_txt = " | ".join(
                f"g{g}: {','.join(map(str, sorted(vals)))}" for g, vals in sorted(target_by_gap.items())
            ) or "-"
            blocks.extend([
                f"• {cfg['label']}: segnale da {event.get('signal_from_key', '-')}",
                f"  target = {targets_txt}",
                f"  H1 prossima = {len(items)} ambi | costo teorico = {len(items)*STAKE_H1:.2f}€",
                f"  ambi = {self._format_pairs(items, with_gap=(strategy == 'fast'))}",
            ])
        return "\n".join(blocks)

    def live_summary_one_line(self, strategy):
        s = self.stats_live[strategy]
        plays = int(s.get("h1_plays", 0))
        hits = int(s.get("h1_hits", 0))
        cost = float(s.get("cost", 0.0))
        gross = float(s.get("gross", 0.0))
        return (
            f"HIT {hits}/{plays} ({safe_pct(hits, plays):.2f}%) | "
            f"netto {gross-cost:+.2f}€ | ROI {safe_pct(gross-cost, cost):+.2f}%"
        )

    def _stats_block(self, title, s, include_draws=True):
        plays = int(s.get("h1_plays", 0))
        hits = int(s.get("h1_hits", 0))
        misses = int(s.get("h1_misses", 0))
        result_draws = int(s.get("result_draws", 0))
        hit_draws = int(s.get("hit_draws", 0))
        stop_draws = int(s.get("stop_draws", 0))
        cost = float(s.get("cost", 0.0))
        gross = float(s.get("gross", 0.0))
        net = gross - cost
        break_even = 100.0 / AMBO_PAYOUT if AMBO_PAYOUT else 0.0
        lines = [title]
        if include_draws:
            lines.append(f"• draw elaborati = {int(s.get('draws', 0))}")
        lines.extend([
            f"• draw con segnale = {int(s.get('signal_draws', 0))} | ambi segnalati = {int(s.get('pairs_signaled', 0))}",
            f"• draw H1 chiusi = {result_draws} | con >=1 HIT = {hit_draws} ({safe_pct(hit_draws, result_draws):.2f}%) | senza HIT = {stop_draws}",
            f"• multi-HIT nello stesso draw = {int(s.get('multi_hit_draws', 0))}",
            f"• AMBI H1 = {hits}/{plays} ({safe_pct(hits, plays):.2f}%) | break-even = {break_even:.2f}%",
            f"• MISS ambo = {misses} | max ambi/segnale = {int(s.get('max_pairs_signal', 0))}",
            f"• costo = {cost:.2f}€ | lordo = {gross:.2f}€ | netto = {net:+.2f}€ | ROI = {safe_pct(net, cost):+.2f}%",
        ])
        return lines

    def stats_text(self):
        lines = []
        for strategy in STRATEGY_ORDER:
            cfg = STRATEGIES[strategy]
            lines.extend(self._stats_block(
                f"📊 FORWARD {cfg['label']} — {cfg['description']} / SOLO H1",
                self.stats_live[strategy],
            ))
            lines.append("")

        lines.extend(["🎯 H1 ATTUALI", self.pending_text(), ""])

        for strategy in STRATEGY_ORDER:
            cfg = STRATEGIES[strategy]
            lines.extend(self._stats_block(
                f"🕰️ WARMUP {cfg['label']} — {cfg['description']}",
                self.stats_warmup[strategy],
            ))
            lines.append("")

        lines.append("ℹ️ FAST 24-29 include il CORE gap27: confronta i due laboratori, non sommare i costi.")
        if FREQ_LAB_ENABLED:
            fs = self.freq_stats_live
            lines.extend([
                "",
                "🧪 FREQ LAB ENTRY-ONLY SHADOW — riepilogo",
                f"• vere entry={int(fs.get('signal_draws',0))} | candidati={int(fs.get('candidates_signaled',0))} | repliche scartate={int(fs.get('suppressed_repeats',0))} | attivi={len(self.freq_sessions)}",
                f"• target >=3/5 = {int(fs.get('target5_success',0))}/{int(fs.get('target5_eval',0))} ({safe_pct(fs.get('target5_success',0), fs.get('target5_eval',0)):.2f}%)",
                f"• target >=4/10 = {int(fs.get('target10_success',0))}/{int(fs.get('target10_eval',0))} ({safe_pct(fs.get('target10_success',0), fs.get('target10_eval',0)):.2f}%)",
                "• dettagli completi: /freq",
            ])
        return "\n".join(lines).rstrip()

    def status_text(self):
        nums4, core, _ = self.current_gap_lists()
        lines = [
            "🎯 DUAL GAP — CORE + FAST LAB — SOLO H1",
            f"• modalita' = {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}",
            f"• ultimo draw = {self.last_draw_key or '-'} | seq = {self.seq}",
            f"• gap {GAP_A} ora = {', '.join(map(str, nums4)) or '-'}",
            f"• CORE gap {CORE_GAP} = {', '.join(map(str, core)) or '-'}",
            f"• FAST gap {FAST_GAP_MIN}-{FAST_GAP_MAX} = {self.fast_targets_text()}",
            f"• H1 CORE prossima = {self.pending_pairs_count('core')} ambi",
            f"• H1 FAST prossima = {self.pending_pairs_count('fast')} ambi",
            f"• FREQ LAB ENTRY-ONLY = {'READY' if self.freq_bootstrap_done else 'BUILD'} | condizione ora={','.join(map(str, self.freq_candidates())) or '-'} | sessioni={len(self.freq_sessions)}",
            f"• warmup = {'OK' if self.warmup_done else 'NO'} | {self.warmup_draws} draw",
            f"• state checkout = {'CARICATO' if self.state_load_info.get('loaded') else 'NUOVO'} | saved_at={self.state_load_info.get('saved_at') or '-'}",
            f"• state Git = {'OK' if self.last_git_status.get('ok') else 'ERRORE'} | {self.last_git_status.get('action', '-')} | {self.last_git_status.get('detail', '-')}",
            "",
            "🎯 EVENTI ATTUALI",
            self.pending_text(),
            "",
            f"CORE: {self.live_summary_one_line('core')}",
            f"FAST: {self.live_summary_one_line('fast')}",
        ]
        return "\n".join(lines)

    def menu_text(self):
        return (
            "🎯 SUPERAMBO — CORE + FAST + FREQ LAB\n\n"
            f"CORE: GAP {GAP_A}+{CORE_GAP} esatto, decine diverse, SOLO H1.\n"
            f"FAST LAB: GAP {GAP_A}+{FAST_GAP_MIN}-{FAST_GAP_MAX}, decine diverse, SOLO H1.\n"
            "CORE e FAST restano invariati.\n\n"
            "🧪 FREQ LAB ENTRY-ONLY: 2 uscite nelle ultime 5 e 2 nelle ultime 20.\n"
            "Apre solo NON-FREQ -> FREQ; niente duplicati dello stesso episodio.\n"
            "Segue H1/H2/H3/H5/H10; target >=3/5 e >=4/10.\n"
            "FREQ LAB non genera puntate e non modifica CORE/FAST.\n\n"
            "FAST include anche i casi a gap27 del CORE, ma le statistiche sono separate.\n"
            "Non sommare CORE e FAST come due sistemi indipendenti.\n"
            f"Pagamento diagnostico ambo: {AMBO_PAYOUT:.2f}x.\n"
            f"Modalita' CORE/FAST: {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}; FREQ sempre SHADOW.\n\n"
            "/status — gap correnti + H1 + stato FREQ\n"
            "/stats — CORE/FAST + riepilogo FREQ\n"
            "/freq — dettaglio completo FREQ LAB\n"
            "/freqanalysis — analisi pattern/pre-gap ENTRY-ONLY\n"
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


async def cmd_freq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.freq_stats_text())


async def cmd_freqanalysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.freq_analysis_text())


async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("status", "Gap correnti, H1 CORE/FAST e stato FREQ"),
        BotCommand("stats", "Statistiche CORE/FAST + riepilogo FREQ"),
        BotCommand("freq", "Statistiche complete FREQ ENTRY-ONLY"),
        BotCommand("freqanalysis", "Analisi pattern/pre-gap FREQ ENTRY-ONLY"),
        BotCommand("menu", "Mostra CORE, FAST e FREQ LAB"),
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
    active = [name for name in STRATEGY_ORDER if engine.pending_events.get(name)]
    if not active:
        return
    sections = []
    for strategy in active:
        cfg = STRATEGIES[strategy]
        event = engine.pending_events[strategy]
        items = event.get("items", []) or []
        sections.extend([
            f"🎯 {cfg['label']} — {cfg['description']}",
            f"Segnale da: {event.get('signal_from_key', '-')}",
            f"Ambi ({len(items)}): {engine._format_pairs(items, with_gap=(strategy == 'fast'))}",
            f"Costo teorico H1: {len(items)*STAKE_H1:.2f}€",
            "",
        ])
    await engine.tg(
        app,
        f"🎯 {signal_word()} H1 GIA' ARMATI DALLO STATO CORRENTE\n\n" +
        "\n".join(sections).rstrip() +
        f"\n\n➡️ PROSSIMA estrazione: {STAKE_H1:.2f}€ H1 per ambo.\n"
        "ℹ️ FAST include il CORE; statistiche separate."
    )


async def startup(engine, app, warmup_retry_state=None):
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
        console_log(f"  il processo RESTA ATTIVO; nuovo tentativo tra {WARMUP_RETRY_SEC}s")

        now_ts = time.time()
        last_reason = str(warmup_retry_state.get("last_reason", ""))
        last_tg_ts = float(warmup_retry_state.get("last_tg_ts", 0.0) or 0.0)
        should_tg = reason != last_reason or now_ts - last_tg_ts >= max(60, WARMUP_FAIL_TG_MIN_SECONDS)
        if should_tg:
            await engine.tg(
                app,
                "⚠️ WARMUP INIZIALE NON COMPLETATO\n\n"
                f"• estrazioni raccolte = {warm.get('draws', 0)}\n"
                f"• motivo = {reason}\n"
                f"• giorni/fonti = {sources_txt}\n"
                f"• continuita' = {continuity_txt}\n\n"
                "⏳ Il bot RESTA ACCESO e NON entra ancora nel motore live.\n"
                f"Riprova automaticamente ogni {WARMUP_RETRY_SEC} secondi.\n"
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

    # Se arriva da uno state CORE+FAST precedente al FREQ LAB, ricostruisce SOLO FREQ.
    if FREQ_LAB_ENABLED and not engine.freq_bootstrap_done:
        freq_boot = await engine.ensure_freq_lab_bootstrap()
        if freq_boot.get("ok"):
            console_log(
                f"FREQ BOOTSTRAP OK | draws={freq_boot.get('draws', 0)} | "
                f"active={len(engine.freq_sessions)}"
            )
        else:
            console_log(f"FREQ BOOTSTRAP PARZIALE | {freq_boot.get('reason', '-')}")
            await engine.tg(
                app,
                "⚠️ FREQ LAB NON ANCORA PRONTO\n\n"
                f"Motivo: {freq_boot.get('reason', '-')}\n"
                "CORE e FAST restano regolarmente attivi e INVARIATI.\n"
                "Il FREQ LAB costruira' lo storico necessario con i prossimi draw."
            )

    # Catch-up di eventuali draw successivi allo state/warmup.
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
        await engine.process_draw(
            app=None, day=d, e=e, nums=nums,
            mode="live", notify=False, persist=False,
        )

    persist = engine.save_state(git=True, force_git=True)
    if not persist.get("ok"):
        await engine.tg(
            app,
            "⚠️ STATE NON PERSISTITO SU GITHUB\n\n"
            f"Azione: {persist.get('action', '-')}\n"
            f"Dettaglio: {persist.get('detail', '-')}\n\n"
            "Il bot resta attivo, ma un riavvio potrebbe perdere lo stato forward. "
            "Controlla `permissions: contents: write`."
        )

    if not warm.get("already_done"):
        source_txt = format_warmup_sources(warm.get("sources", []))
        nums4, core, _ = engine.current_gap_lists()
        await engine.tg(
            app,
            "🕰️ WARMUP INIZIALE COMPLETATO — DUAL GAP\n\n"
            f"• estrazioni = {warm.get('draws', 0)}\n"
            f"• fonti = {source_txt or '-'}\n"
            f"• continuita' = {warm.get('continuity_note') or 'segmento richiesto integro'}\n"
            f"• gap {GAP_A} attuali = {', '.join(map(str, nums4)) or '-'}\n"
            f"• CORE gap {CORE_GAP} = {', '.join(map(str, core)) or '-'}\n"
            f"• FAST gap {FAST_GAP_MIN}-{FAST_GAP_MAX} = {engine.fast_targets_text()}\n"
            f"• H1 CORE prossima = {engine.pending_pairs_count('core')} ambi\n"
            f"• H1 FAST prossima = {engine.pending_pairs_count('fast')} ambi\n"
            f"• FREQ LAB = {'READY' if engine.freq_bootstrap_done else 'BUILD'} | sessioni attive={len(engine.freq_sessions)}\n\n"
            f"{engine.stats_text()}"
        )

    await engine.tg(
        app,
        "🚀 BOT CORE + FAST + FREQ LAB AVVIATO\n\n"
        f"✅ CORE = GAP {GAP_A}+{CORE_GAP} — INVARIATO\n"
        f"✅ FAST LAB = GAP {GAP_A}+{FAST_GAP_MIN}-{FAST_GAP_MAX} — INVARIATO\n"
        "✅ CORE/FAST: tutte le coppie valide, decine diverse, SOLO H1\n"
        f"✅ H1 CORE/FAST = {STAKE_H1:.2f}€ per ambo diagnostico\n"
        "✅ nessun H2 / progressione / WAIT30 aggiunto\n"
        f"✅ modalita' CORE/FAST = {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}\n"
        "🧪 FREQ LAB = ENTRY-ONLY 2/5 + 2/20, SEMPRE SHADOW, zero puntate\n"
        "🧪 niente duplicati stesso episodio; snapshot nascita + H1/H2/H3/H5/H10\n"
        "✅ warmup continuo + state persistente GitHub\n"
        f"✅ warmup minimo = {WARMUP_MIN_DRAWS} estrazioni continue\n"
        f"✅ retry warmup ogni {WARMUP_RETRY_SEC}s\n\n"
        f"H1 CORE prossima: {engine.pending_pairs_count('core')} ambi\n"
        f"H1 FAST prossima: {engine.pending_pairs_count('fast')} ambi\n"
        f"FREQ LAB: {'READY' if engine.freq_bootstrap_done else 'BUILD'} | sessioni={len(engine.freq_sessions)}\n\n"
        "ℹ️ FAST include il CORE a gap27: statistiche separate, costi non sommabili.\n"
        "ℹ️ /freq mostra il forward; /freqanalysis confronta pattern e pre-gap ENTRY-ONLY."
    )
    await notify_actionable_state(engine, app)
    console_log("STARTUP COMPLETATO -> entro nel live_loop")
    return True


async def startup_until_ready(engine, app):
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
                    await engine.process_draw(
                        app=app, day=d, e=e, nums=nums,
                        mode="live", notify=True, persist=True,
                    )
                else:
                    for d, e, nums in unseen:
                        await engine.process_draw(
                            app=None, day=d, e=e, nums=nums,
                            mode="live", notify=False, persist=False,
                        )
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

async def run_self_test():
    eng = DualGapEngine(load=False)
    eng.save_state = lambda *a, **k: _git_status(True, "test", "no-op")

    # Stato sintetico: 17 gap4, 73 gap27, 62 gap26.
    eng.seq = 100
    eng.last_seen_seq = {n: None for n in range(1, 91)}
    eng.last_seen_seq[17] = 96
    eng.last_seen_seq[73] = 73
    eng.last_seen_seq[62] = 74
    assert eng.current_gap(17) == 4
    assert eng.current_gap(73) == 27
    assert eng.current_gap(62) == 26

    core = eng.build_signal_items("core")
    fast = eng.build_signal_items("fast")
    assert {tuple(x["pair"]) for x in core} == {(17, 73)}
    assert {tuple(x["pair"]) for x in fast} == {(17, 62), (17, 73)}

    # Stessa decina esclusa: 72 gap4 e 78 gap27 non possono formare ambo.
    eng2 = DualGapEngine(load=False)
    eng2.seq = 100
    eng2.last_seen_seq = {n: None for n in range(1, 91)}
    eng2.last_seen_seq[72] = 96
    eng2.last_seen_seq[78] = 73
    assert eng2.build_signal_items("core") == []
    assert eng2.build_signal_items("fast") == []

    # Arma entrambi. CORE=1, FAST=2. Il draw successivo centra 17-73 soltanto.
    await eng.arm_from_current_gaps(None, "2099-01-01#100", mode="live", notify=False)
    assert eng.pending_pairs_count("core") == 1
    assert eng.pending_pairs_count("fast") == 2
    draw = [17, 73] + [n for n in range(1, 91) if n not in {17, 73}][:18]
    res = await eng.settle_pending(None, "2099-01-01", 101, draw, mode="live", notify=False)
    assert res["core"]["plays"] == 1 and res["core"]["hits"] == 1
    assert res["fast"]["plays"] == 2 and res["fast"]["hits"] == 1
    assert eng.stats_live["core"]["h1_plays"] == 1
    assert eng.stats_live["core"]["h1_hits"] == 1
    assert eng.stats_live["fast"]["h1_plays"] == 2
    assert eng.stats_live["fast"]["h1_hits"] == 1

    # Il draw corrente aggiorna i gap prima di armare il successivo.
    eng3 = DualGapEngine(load=False)
    eng3.save_state = lambda *a, **k: _git_status(True, "test", "no-op")
    eng3.seq = 99
    eng3.last_seen_seq = {n: 99 for n in range(1, 91)}
    eng3.last_seen_seq[17] = 95
    eng3.last_seen_seq[73] = 72
    await eng3.process_draw(
        None, "2099-01-02", 100, list(range(1, 21)),
        mode="live", notify=False, persist=False,
    )
    assert eng3.current_gap(17) == 0
    assert eng3.pending_events["core"] is None

    # FREQ ENTRY-ONLY: 42 compare 2 volte nelle ultime 5 e 2 nelle ultime 20.
    freq = DualGapEngine(load=False)
    freq.save_state = lambda *a, **k: _git_status(True, "test", "no-op")
    freq._reset_freq_lab()
    filler = list(range(1, 21))
    for i in range(20):
        nums = list(filler)
        if i in (16, 19):
            nums[-1] = 42
        freq.freq_stats_warmup["draws"] += 1
        await freq.settle_freq_sessions(None, "2099-02-01", i + 1, nums, mode="warmup", notify=False)
        k = draw_key("2099-02-01", i + 1)
        freq.freq_append_history(k, nums)
        await freq.arm_freq_birth(None, k, mode="warmup", notify=False)
    assert 42 in freq.freq_candidates()
    sessions_42 = [x for x in freq.freq_sessions if x.get("number") == 42 and x.get("age") == 0]
    assert len(sessions_42) == 1, "FREQ-BIRTH ENTRY non armata una sola volta per 42"
    uid_before = freq.freq_uid

    # Il draw successivo mantiene ancora 42 nella condizione (le due uscite restano nella finestra 5),
    # ma NON deve aprire una seconda sessione dello stesso episodio.
    nums = list(filler)
    await freq.settle_freq_sessions(None, "2099-02-01", 21, nums, mode="warmup", notify=False)
    k = draw_key("2099-02-01", 21)
    freq.freq_append_history(k, nums)
    await freq.arm_freq_birth(None, k, mode="warmup", notify=False)
    assert 42 in freq.freq_candidates()
    assert freq.freq_uid == uid_before, "ENTRY-ONLY ha duplicato la stessa nascita"
    assert freq.freq_stats_warmup["suppressed_repeats"] >= 1
    assert sessions_42[0].get("snapshot", {}).get("pattern5") in {"-4/-1", "-5/-2", "-3/-1", "-4/-2", "-5/-1", "-3/-2", "-2/-1", "-5/-3", "-5/-4", "-4/-3"}

    # Una sessione isolata su 42 deve riconoscere 3/5.
    testfreq = DualGapEngine(load=False)
    testfreq.save_state = lambda *a, **k: _git_status(True, "test", "no-op")
    testfreq.freq_sessions = [{
        "id": "FREQ-TEST", "number": 42, "signal_from_key": "2099-02-02#001",
        "created_at": now_txt(), "age": 0, "hit_ages": [],
    }]
    for i in range(1, 6):
        nums = list(range(1, 21))
        if i in (1, 3, 5):
            nums[-1] = 42
        await testfreq.settle_freq_sessions(None, "2099-02-02", i + 1, nums, mode="live", notify=False)
    assert testfreq.freq_stats_live["target5_eval"] == 1
    assert testfreq.freq_stats_live["target5_success"] == 1

    print("SELF-TEST OK: CORE/FAST invariati + FREQ ENTRY-ONLY + snapshot + H1/H2/H3/H5/H10")


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
    engine = DualGapEngine()
    app.bot_data["engine"] = engine

    console_log(
        f"STATE STARTUP | loaded={engine.state_load_info.get('loaded')} | "
        f"reason={engine.state_load_info.get('reason')} | "
        f"saved_at={engine.state_load_info.get('saved_at') or '-'}"
    )

    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("freq", cmd_freq))
    app.add_handler(CommandHandler("freqanalysis", cmd_freqanalysis))
    app.add_handler(CommandHandler("menu", cmd_menu))

    await app.initialize()
    await app.start()
    await setup_commands(app)
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
