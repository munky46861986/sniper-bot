# ============================================================
# 🎯 SUPERAMBO — GAP 4 + GAP 27 / DECINE DIVERSE / SOLO H1
# ============================================================
#
# STRATEGIA UNICA, CONGELATA — FORWARD/SHADOW:
#
#   1) Dopo ogni estrazione aggiorna il GAP (ritardo) dei numeri 1..90.
#      - numero uscito nell'ultima estrazione -> gap = 0
#      - se resta assente -> gap aumenta di 1
#
#   2) Cerca TUTTI i numeri con gap esattamente 4 e TUTTI quelli
#      con gap esattamente 27.
#
#   3) Forma tutti gli ambi GAP4 x GAP27, ma accetta SOLO coppie
#      appartenenti a DECINE DIVERSE.
#
#      Decine usate (coerenti con il progetto precedente):
#        90-9, 10-19, 20-29, 30-39, 40-49,
#        50-59, 60-69, 70-79, 80-89.
#
#   4) Tutti gli ambi validi vengono armati per UNA SOLA estrazione:
#      SOLO H1 sulla prossima estrazione.
#      - HIT se entrambi i numeri dell'ambo compaiono
#      - STOP se non compaiono insieme
#      - nessun H2, nessuna progressione, nessun WAIT30
#
#   5) Se nella stessa estrazione esistono piu' ambi validi, vengono
#      mantenuti TUTTI, come nel test storico. Ogni ambo e' deduplicato.
#
# WARMUP / PERSISTENZA:
#   • scarica gli ultimi WARMUP_DAYS giorni e usa solo il segmento
#     cronologico continuo piu' recente;
#   • i giorni conclusi devono avere 288 estrazioni senza buchi;
#   • ricostruisce i gap e l'eventuale H1 gia' valido per la prossima;
#   • ai riavvii riparte dallo state persistente GitHub;
#   • se il warmup non e' pronto il processo resta acceso e ritenta.
#
# SHADOW_MODE=1 (default): segnala soltanto; NON effettua puntate.
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
STATE_FILE = os.path.join(BASE_DIR, "superambo_gap4_gap27_h1_state.json")
LOCK_FILE = "/tmp/superambo_gap4_gap27_h1.lock"

# Nuova strategia = nuovo state. Non riusa lo state del vecchio basket5.
LOGIC_VERSION = 1

LOOP_SEC = int(os.getenv("LOOP_SEC", "60"))
WARMUP_RETRY_SEC = int(os.getenv("WARMUP_RETRY_SEC", "300"))
WARMUP_FAIL_TG_MIN_SECONDS = int(os.getenv("WARMUP_FAIL_TG_MIN_SECONDS", "900"))
WARMUP_DAYS = int(os.getenv("WARMUP_DAYS", "7"))
# Per un gap massimo 27 non servono 900 colpi: 120 colpi continui danno
# un margine ampio per inizializzare correttamente tutti i ritardi.
WARMUP_MIN_DRAWS = int(os.getenv("WARMUP_MIN_DRAWS", "120"))
WARMUP_FULL_DAY_DRAWS = int(os.getenv("WARMUP_FULL_DAY_DRAWS", "288"))
WARMUP_REQUIRE_COMPLETE_PAST_DAYS = os.getenv("WARMUP_REQUIRE_COMPLETE_PAST_DAYS", "1") != "0"
PROCESSED_MAX = int(os.getenv("PROCESSED_MAX", "12000"))

GAP_A = int(os.getenv("GAP_A", "4"))
GAP_B = int(os.getenv("GAP_B", "27"))
STAKE_H1 = float(os.getenv("STAKE_H1", "1"))
AMBO_PAYOUT = float(os.getenv("AMBO_PAYOUT", "14"))
SHADOW_MODE = os.getenv("SHADOW_MODE", "1") != "0"

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
# MOTORE GAP 4 + GAP 27 / DECINE DIVERSE / SOLO H1
# ============================================================

class Gap427Engine:
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

        # Ultima sequenza in cui ogni numero e' comparso. None = non ancora noto.
        self.last_seen_seq = {n: None for n in range(1, 91)}

        # Un unico evento H1 per la prossima estrazione; contiene TUTTI gli ambi
        # validi generati dal draw precedente.
        self.pending_event = None

        # Solo diagnostica recente, non influenza mai la logica.
        self.recent_events = []

        self.stats_warmup = self._new_stats()
        self.stats_live = self._new_stats()

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

    def _stats(self, mode):
        return self.stats_warmup if mode == "warmup" else self.stats_live

    # ----------------------------
    # Stato / serializzazione
    # ----------------------------

    def _sanitize_pending(self, raw):
        if not isinstance(raw, dict):
            return None
        items = []
        seen = set()
        for x in raw.get("items", []) or []:
            try:
                g4 = int(x["gap4"])
                g27 = int(x["gap27"])
                pair = tuple(sorted((g4, g27)))
            except Exception:
                continue
            if not (1 <= g4 <= 90 and 1 <= g27 <= 90):
                continue
            if not different_decades(g4, g27):
                continue
            if pair in seen:
                continue
            seen.add(pair)
            items.append({"gap4": g4, "gap27": g27, "pair": list(pair)})
        if not items:
            return None
        return {
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

            self.pending_event = self._sanitize_pending(d.get("pending_event"))
            self.recent_events = list(d.get("recent_events", []) or [])[-100:]

            self.stats_warmup.update(d.get("stats_warmup") or {})
            self.stats_live.update(d.get("stats_live") or {})

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
                f"pending_ambi={self.pending_pairs_count()}"
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
            "pending_event": self.pending_event,
            "recent_events": self.recent_events[-100:],
            "stats_warmup": self.stats_warmup,
            "stats_live": self.stats_live,
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

    def update_last_seen(self, nums):
        for n in set(map(int, nums)):
            self.last_seen_seq[n] = int(self.seq)

    def build_signal_items(self):
        nums4 = self.numbers_at_gap(GAP_A)
        nums27 = self.numbers_at_gap(GAP_B)
        items = []
        seen_pairs = set()

        for n4 in nums4:
            for n27 in nums27:
                if n4 == n27:
                    continue
                if not different_decades(n4, n27):
                    continue
                pair = tuple(sorted((int(n4), int(n27))))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                items.append({
                    "gap4": int(n4),
                    "gap27": int(n27),
                    "pair": list(pair),
                })

        items.sort(key=lambda x: tuple(x["pair"]))
        return items

    def pending_pairs_count(self):
        return len((self.pending_event or {}).get("items", []) or [])

    def pending_pairs(self):
        return [tuple(map(int, x["pair"])) for x in (self.pending_event or {}).get("items", []) or []]

    @staticmethod
    def _format_pairs(items, limit=30):
        items = list(items or [])
        shown = items[:limit]
        parts = []
        for x in shown:
            pair = tuple(x.get("pair", []))
            if len(pair) != 2:
                continue
            parts.append(fmt_pair(pair))
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
        event = self.pending_event
        if not event:
            return None

        # Consuma l'evento subito: non potra' essere contabilizzato due volte.
        self.pending_event = None
        items = list(event.get("items", []) or [])
        if not items:
            return None

        numset = set(map(int, nums))
        hits = []
        misses = []
        for item in items:
            pair = tuple(map(int, item.get("pair", [])))
            if len(pair) != 2:
                continue
            if pair[0] in numset and pair[1] in numset:
                hits.append(item)
            else:
                misses.append(item)

        plays = len(hits) + len(misses)
        hit_count = len(hits)
        st = self._stats(mode)
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

        self.recent_events.append({
            "type": "RESULT",
            "at": draw_key(day, e),
            "signal_from": event.get("signal_from_key"),
            "plays": plays,
            "hits": hit_count,
            "net": draw_net,
        })
        self.recent_events = self.recent_events[-100:]

        if notify and mode == "live":
            hit_txt = self._format_pairs(hits)
            miss_txt = self._format_pairs(misses)
            icon = "✅" if hit_count else "❌"
            title = "HIT H1" if hit_count else "STOP H1"
            await self.tg(
                app,
                f"{icon} {signal_word()} {title} — GAP {GAP_A}+{GAP_B}\n\n"
                f"Segnale da: {event.get('signal_from_key', '-')}\n"
                f"Risultato: {draw_key(day, e)}\n"
                f"Ambi giocati: {plays} | costo: {draw_cost:.2f}€\n"
                f"✅ HIT ({hit_count}): {hit_txt}\n"
                f"❌ MISS ({len(misses)}): {miss_txt}\n\n"
                f"Lordo draw: {draw_gross:.2f}€ | netto draw: {draw_net:+.2f}€\n"
                f"Forward: {self.live_summary_one_line()}"
            )

        return {
            "plays": plays,
            "hits": hit_count,
            "misses": len(misses),
            "cost": draw_cost,
            "gross": draw_gross,
            "net": draw_net,
        }

    async def arm_from_current_gaps(self, app, current_key, mode="live", notify=True):
        items = self.build_signal_items()
        if not items:
            self.pending_event = None
            return None

        nums4 = sorted({int(x["gap4"]) for x in items})
        nums27 = sorted({int(x["gap27"]) for x in items})
        self.pending_event = {
            "signal_from_key": current_key,
            "armed_at_seq": int(self.seq),
            "created_at": now_txt(),
            "items": items,
        }

        st = self._stats(mode)
        st["signal_draws"] = int(st.get("signal_draws", 0)) + 1
        st["pairs_signaled"] = int(st.get("pairs_signaled", 0)) + len(items)
        st["max_pairs_signal"] = max(int(st.get("max_pairs_signal", 0) or 0), len(items))

        self.recent_events.append({
            "type": "SIGNAL",
            "at": current_key,
            "pairs": len(items),
            "gap4": nums4,
            "gap27": nums27,
        })
        self.recent_events = self.recent_events[-100:]

        if notify and mode == "live":
            potential_cost = len(items) * STAKE_H1
            await self.tg(
                app,
                f"🎯 {signal_word()} GAP {GAP_A}+{GAP_B} — H1 ARMATO\n\n"
                f"Segnale da: {current_key}\n"
                f"Gap {GAP_A}: {', '.join(map(str, nums4)) or '-'}\n"
                f"Gap {GAP_B}: {', '.join(map(str, nums27)) or '-'}\n"
                f"Regola: SOLO decine diverse\n\n"
                f"Ambi validi ({len(items)}):\n{self._format_pairs(items)}\n\n"
                f"➡️ PROSSIMA estrazione: SOLO H1\n"
                f"Stake: {STAKE_H1:.2f}€ per ambo | costo potenziale: {potential_cost:.2f}€\n"
                "Nessun H2, nessuna progressione."
            )

        return self.pending_event

    async def process_draw(self, app, day, e, nums, mode="live", notify=True, persist=True):
        clean = list(map(int, nums))
        if len(clean) != 20 or len(set(clean)) != 20 or any(n < 1 or n > 90 for n in clean):
            return None
        if self.already_processed(day, e):
            return None

        current_key = self.remember_processed(day, e)
        st = self._stats(mode)
        st["draws"] = int(st.get("draws", 0)) + 1

        # 1) Il segnale generato dal draw precedente si gioca ORA.
        result = await self.settle_pending(app, day, e, clean, mode=mode, notify=notify)

        # 2) Aggiorna i gap con il draw corrente.
        self.update_last_seen(clean)

        # 3) Sui gap DOPO il draw corrente arma l'eventuale H1 per il PROSSIMO.
        signal = await self.arm_from_current_gaps(
            app, current_key=current_key, mode=mode, notify=notify
        )

        if persist:
            self.save_state(git=(mode == "live"))

        return {"result": result, "signal": signal}

    # ----------------------------
    # Warmup
    # ----------------------------

    def _reset_for_warmup(self):
        self.processed = []
        self.processed_set = set()
        self.last_draw_key = None
        self.seq = 0
        self.last_seen_seq = {n: None for n in range(1, 91)}
        self.pending_event = None
        self.recent_events = []
        self.stats_warmup = self._new_stats()
        self.stats_live = self._new_stats()

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
                app=None,
                day=d,
                e=e,
                nums=nums,
                mode="warmup",
                notify=False,
                persist=False,
            )

        # Con un warmup ampio tutti i 90 numeri devono essere stati osservati.
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
        return self.numbers_at_gap(GAP_A), self.numbers_at_gap(GAP_B)

    def pending_text(self):
        if not self.pending_event:
            return "• nessun H1 armato"
        items = self.pending_event.get("items", []) or []
        nums4 = sorted({int(x["gap4"]) for x in items})
        nums27 = sorted({int(x["gap27"]) for x in items})
        return (
            f"• segnale da {self.pending_event.get('signal_from_key', '-')}\n"
            f"• gap {GAP_A}: {', '.join(map(str, nums4)) or '-'}\n"
            f"• gap {GAP_B}: {', '.join(map(str, nums27)) or '-'}\n"
            f"• H1 prossima = {len(items)} ambi | costo potenziale = {len(items)*STAKE_H1:.2f}€\n"
            f"• ambi: {self._format_pairs(items)}"
        )

    def live_summary_one_line(self):
        s = self.stats_live
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
            f"• draw con segnale generato = {int(s.get('signal_draws', 0))} | ambi segnalati = {int(s.get('pairs_signaled', 0))}",
            f"• draw H1 chiusi = {result_draws} | con >=1 HIT = {hit_draws} ({safe_pct(hit_draws, result_draws):.2f}%) | senza HIT = {stop_draws}",
            f"• multi-HIT nello stesso draw = {int(s.get('multi_hit_draws', 0))}",
            f"• AMBI H1 = {hits}/{plays} ({safe_pct(hits, plays):.2f}%) | break-even = {break_even:.2f}%",
            f"• MISS ambo = {misses} | max ambi in un singolo segnale = {int(s.get('max_pairs_signal', 0))}",
            f"• costo = {cost:.2f}€ | lordo = {gross:.2f}€ | netto = {net:+.2f}€ | ROI = {safe_pct(net, cost):+.2f}%",
        ])
        return lines

    def stats_text(self):
        lines = self._stats_block(
            f"📊 FORWARD LIVE — GAP {GAP_A}+{GAP_B} / DECINE DIVERSE / SOLO H1",
            self.stats_live,
        )
        lines.extend([
            "",
            "🎯 H1 ATTUALE",
            self.pending_text(),
            "",
            *self._stats_block("🕰️ WARMUP DIAGNOSTICO", self.stats_warmup),
        ])
        return "\n".join(lines)

    def status_text(self):
        nums4, nums27 = self.current_gap_lists()
        lines = [
            f"🎯 GAP {GAP_A} + GAP {GAP_B} → DECINE DIVERSE → SOLO H1",
            f"• modalita' = {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}",
            f"• ultimo draw = {self.last_draw_key or '-'} | seq = {self.seq}",
            f"• gap {GAP_A} ora = {', '.join(map(str, nums4)) or '-'}",
            f"• gap {GAP_B} ora = {', '.join(map(str, nums27)) or '-'}",
            f"• H1 attivi per prossima = {self.pending_pairs_count()} ambi",
            f"• warmup = {'OK' if self.warmup_done else 'NO'} | {self.warmup_draws} draw",
            f"• state checkout = {'CARICATO' if self.state_load_info.get('loaded') else 'NUOVO'} | saved_at={self.state_load_info.get('saved_at') or '-'}",
            f"• state Git = {'OK' if self.last_git_status.get('ok') else 'ERRORE'} | {self.last_git_status.get('action', '-')} | {self.last_git_status.get('detail', '-')}",
            "",
            "🎯 EVENTO ATTUALE",
            self.pending_text(),
            "",
            self.live_summary_one_line(),
        ]
        return "\n".join(lines)

    def menu_text(self):
        return (
            "🎯 SUPERAMBO — GAP 4 + GAP 27 / SOLO H1\n\n"
            f"Dopo ogni estrazione aggiorno i gap 1..90.\n"
            f"Cerco tutti i numeri con gap esatto {GAP_A} e gap esatto {GAP_B}.\n"
            "Formo tutti gli ambi tra i due gruppi, ma SOLO se appartengono a decine diverse.\n"
            "Le decine sono: 90-9, 10-19, 20-29, ..., 80-89.\n"
            "Tutti gli ambi validi vengono mantenuti e deduplicati.\n\n"
            f"➡️ SOLO H1 sulla prossima estrazione: {STAKE_H1:.2f}€ per ambo.\n"
            "Nessun H2, nessuna progressione, nessun WAIT30.\n"
            f"Pagamento statistico impostato: {AMBO_PAYOUT:.2f}x.\n"
            f"Modalita': {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}; il bot non effettua puntate automatiche.\n\n"
            "/status — gap correnti + H1 armato\n"
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
        BotCommand("status", "Gap correnti e H1 armato"),
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
    event = engine.pending_event
    if not event:
        return
    items = event.get("items", []) or []
    nums4 = sorted({int(x["gap4"]) for x in items})
    nums27 = sorted({int(x["gap27"]) for x in items})
    await engine.tg(
        app,
        f"🎯 {signal_word()} H1 GIA' ARMATO DALLO STATO CORRENTE\n\n"
        f"Segnale da: {event.get('signal_from_key', '-')}\n"
        f"Gap {GAP_A}: {', '.join(map(str, nums4)) or '-'}\n"
        f"Gap {GAP_B}: {', '.join(map(str, nums27)) or '-'}\n"
        f"Ambi ({len(items)}): {engine._format_pairs(items)}\n\n"
        f"➡️ PROSSIMA estrazione: {STAKE_H1:.2f}€ H1 per ambo.\n"
        "Nessun H2."
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

    # Recupera eventuali draw di oggi successivi allo state/warmup.
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
        # Catch-up silenzioso: mai inviare segnali o risultati ormai scaduti.
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
            "Controlla che il workflow abbia `permissions: contents: write`."
        )

    if not warm.get("already_done"):
        source_txt = format_warmup_sources(warm.get("sources", []))
        nums4, nums27 = engine.current_gap_lists()
        await engine.tg(
            app,
            "🕰️ WARMUP INIZIALE COMPLETATO\n\n"
            f"• estrazioni = {warm.get('draws', 0)}\n"
            f"• fonti = {source_txt or '-'}\n"
            f"• continuita' = {warm.get('continuity_note') or 'segmento richiesto integro'}\n"
            f"• gap {GAP_A} attuali = {', '.join(map(str, nums4)) or '-'}\n"
            f"• gap {GAP_B} attuali = {', '.join(map(str, nums27)) or '-'}\n"
            f"• H1 gia' valido per la prossima = {engine.pending_pairs_count()} ambi\n\n"
            f"{engine.stats_text()}"
        )

    await engine.tg(
        app,
        f"🚀 BOT GAP {GAP_A}+{GAP_B} / DECINE DIVERSE / SOLO H1 AVVIATO\n\n"
        f"✅ gap esatti = {GAP_A} e {GAP_B}\n"
        "✅ tutte le coppie valide tra i due gruppi\n"
        "✅ SOLO decine diverse: 90-9, 10-19, ..., 80-89\n"
        "✅ ogni ambo deduplicato\n"
        f"✅ SOLO H1 = {STAKE_H1:.2f}€ per ambo\n"
        "✅ nessun H2 / progressione / WAIT30\n"
        f"✅ modalita' = {'SHADOW/FORWARD' if SHADOW_MODE else 'PLAY'}\n"
        "✅ warmup continuo + state persistente GitHub\n"
        f"✅ warmup minimo = {WARMUP_MIN_DRAWS} estrazioni continue\n"
        f"✅ se il warmup fallisce resta acceso e ritenta ogni {WARMUP_RETRY_SEC}s\n\n"
        f"H1 attivi per la prossima: {engine.pending_pairs_count()} ambi"
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
                    # Se il processo era rimasto indietro, elabora tutto ma non invia
                    # messaggi ormai scaduti. Alla fine mostra solo il vero H1 corrente.
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
    eng = Gap427Engine(load=False)
    eng.save_state = lambda *a, **k: _git_status(True, "test", "no-op")

    # 1) Gap: se un numero e' uscito alla seq 96 e ora siamo a 100 -> gap 4.
    eng.seq = 100
    eng.last_seen_seq = {n: None for n in range(1, 91)}
    eng.last_seen_seq[17] = 96
    eng.last_seen_seq[73] = 73
    assert eng.current_gap(17) == 4
    assert eng.current_gap(73) == 27

    # 2) Decine diverse -> ambo valido.
    items = eng.build_signal_items()
    assert len(items) == 1
    assert tuple(items[0]["pair"]) == (17, 73)

    # 3) Stessa decina -> esclusione totale.
    eng.last_seen_seq = {n: None for n in range(1, 91)}
    eng.last_seen_seq[72] = 96
    eng.last_seen_seq[78] = 73
    assert eng.build_signal_items() == []

    # 4) Multipli: 2 gap4 x 2 gap27, uno stesso-decade escluso.
    eng.last_seen_seq = {n: None for n in range(1, 91)}
    eng.last_seen_seq[17] = 96   # gap4, decade 10-19
    eng.last_seen_seq[25] = 96   # gap4, decade 20-29
    eng.last_seen_seq[73] = 73   # gap27, decade 70-79
    eng.last_seen_seq[28] = 73   # gap27, decade 20-29
    items = eng.build_signal_items()
    pairs = {tuple(x["pair"]) for x in items}
    assert pairs == {(17, 28), (17, 73), (25, 73)}

    # 5) Arma H1, poi sul draw successivo 17-73 deve essere HIT.
    await eng.arm_from_current_gaps(None, "2099-01-01#100", mode="live", notify=False)
    assert eng.pending_pairs_count() == 3
    result = await eng.settle_pending(
        None, "2099-01-01", 101,
        [17, 73] + [n for n in range(1, 91) if n not in {17, 73}][:18],
        mode="live", notify=False,
    )
    assert result["plays"] == 3
    assert result["hits"] == 1
    assert eng.stats_live["h1_plays"] == 3
    assert eng.stats_live["h1_hits"] == 1
    assert abs(float(eng.stats_live["cost"]) - 3 * STAKE_H1) < 1e-9
    assert abs(float(eng.stats_live["gross"]) - AMBO_PAYOUT * STAKE_H1) < 1e-9

    # 6) Il draw corrente azzera il gap dei numeri usciti PRIMA di creare il segnale nuovo.
    eng = Gap427Engine(load=False)
    eng.save_state = lambda *a, **k: _git_status(True, "test", "no-op")
    eng.seq = 99
    eng.last_seen_seq = {n: 99 for n in range(1, 91)}
    eng.last_seen_seq[17] = 95  # diventerebbe gap5 dopo incremento seq se assente
    eng.last_seen_seq[73] = 72  # diventerebbe gap28 dopo incremento seq se assente
    draw = list(range(1, 21))
    await eng.process_draw(None, "2099-01-02", 100, draw, mode="live", notify=False, persist=False)
    assert eng.current_gap(17) == 0  # 17 era nel draw corrente
    assert eng.pending_event is None

    print("SELF-TEST OK: gap4+gap27 + decine diverse + tutti gli ambi + SOLO H1 + contabilita' multi-ambo")


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
    engine = Gap427Engine()
    app.bot_data["engine"] = engine

    console_log(
        f"STATE STARTUP | loaded={engine.state_load_info.get('loaded')} | "
        f"reason={engine.state_load_info.get('reason')} | "
        f"saved_at={engine.state_load_info.get('saved_at') or '-'}"
    )

    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("menu", cmd_menu))

    await app.initialize()
    await app.start()
    await setup_commands(app)

    # Telegram resta disponibile anche durante eventuali retry del warmup.
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
