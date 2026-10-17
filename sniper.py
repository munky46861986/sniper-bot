# ============================================================
# 🎯 10eLOTTO MULTI BD12+ED12+O2F12 — v20.9.2 PRIME + QUATERNA + SETTINA PROFIT FAST + NOVINA LIVE — HARD LOCK
# ============================================================
# UNICO RAMO ATTIVO: MULTI
#   STANDARD (shadow/control): BD12 ∩ ED12 ∩ O2F12, W80, cooldown 5
#   PRIME A: STANDARD + BD rank 11-12 + O2 rank 6-12 (INVARIATO da v20.4)
#   PRIME A2 ELITE: STANDARD + BD rank 11-12 + O2 rank 2-4 + ora <=08:00 oppure >16:00
#   PRIME D ELITE: STANDARD + BD rank 1-4 + ora >16:00 + intersezione BD∩ED∩O2 unica
#   PRIME D WIDE: STANDARD + BD rank 5-8 + ora >16:00 + intersezione BD∩ED∩O2 unica
#   PRIME X ULTRA SHADOW: sottoinsieme D con ED rank 9-12 + ora >17:00 + Extra margin13 >=1
#   PRIME C SHADOW: legacy sperimentale v20.6, continua solo dove non scatta D
#   PRIME B: LEGACY congelato; nessun nuovo B viene creato
#
# AMBI:
#   P1/P2 = 2 partner O2F12 con maggiore co-occorrenza Base nei 900 draw precedenti
#   A: AMBO1 M-P1 + AMBO2 M-P2 FAST + terzo lato sempre monitorato
#   A2: AMBO1 + AMBO2 + terzo lato monitorati come nuovo forward operativo
#   D ELITE/WIDE: AMBATA operativa; AMBO1/AMBO2/terzo lato SOLO shadow
#   X ULTRA: overlay shadow sui D, nessuna notifica separata
#   C: ambata/ambi solo shadow; nessuna notifica operativa
#   B legacy: eventuali pending precedenti vengono solo chiusi
#   SUPER = P1-P2 se support_sum >= 4
#   TRIANGLE_OFF = P1-P2 se support_sum < 4, sempre shadow su A/A2/D/C
#
# FORWARD TEST:
#   - nessun backfill PRIME D / PRIME X; A/A2 restano invariati; C/B legacy preservati
#   - PRIME A migra dalla v20.4 senza reset
#   - state anti-regressione fra rotazioni GitHub runner
#   - v20.7.1: recupero anche dalla STORIA GIT dello state, non solo HEAD locale/remoto
#   - v20.7.1: marker A2/D/X fissati solo dopo il catch-up reale, mai ereditati da uno state vecchio
#   - v20.8: QUATERNA PLUS/ELITE solo A2 + D ELITE, nessun backfill
#   - v20.9: SETTINA/NOVINA LIVE con premi standard, costo/ROI e stop al primo premio
#   - v20.9.1 HARD LOCK: snapshot locale PRIMA di Git + backup persistente + floor anti-regressione
#   - v20.9.2: SETTINA PROFIT FAST sostituisce la SETTINA normale per i nuovi segnali (A2/DE gate, H1-H2)
#   - QUATERNA: MAX-MIN Jaccard900 su TOP10/TOP11/TOP12; 2/3 consenso=PLUS, 3/3=ELITE
#   - gestione operativa: 1 euro/colpo, STOP al primo 2/4 o meglio; shadow continua fino H5
#   - mantiene FIX state v20.5.1: merge conservativo LOCAL+REMOTE + push esplicito sul branch
#   - STANDARD totalmente shadow: NON arma piu AMBO/SUPER
#   - FOCUS / INCROCIO / CORE / legacy: PAUSATI, state conservato ma non aggiornato
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
from collections import Counter
from itertools import combinations

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
# v20.9.1 HARD LOCK: seconda copia persistente dello state. Viene letta PRIMA di qualsiasi
# fast-forward/reset Git e viene pubblicata insieme allo state principale.
STATE_HARDLOCK_FILE = os.path.join(BASE_DIR, "10elotto_engine_only_state.hardlock.json")
LEGACY_STATE_FILE = os.path.join(BASE_DIR, "superambo_gap4_core_fast_h1_state.json")
LOCK_FILE = "/tmp/10elotto_multi_prime_only.lock"

LOOP_SEC = int(os.getenv("LOOP_SEC", "60"))
BOT_MAX_RUNTIME_SECONDS = int(os.getenv("BOT_MAX_RUNTIME_SECONDS", "19800"))
BOT_ROTATION_NOTIFY = os.getenv("BOT_ROTATION_NOTIFY", "1") != "0"
WARMUP_RETRY_SEC = int(os.getenv("WARMUP_RETRY_SEC", "300"))
PERSIST_GIT_STATE = os.getenv("PERSIST_GIT_STATE", "1") != "0"
GIT_COMMIT_MIN_SECONDS = int(os.getenv("GIT_COMMIT_MIN_SECONDS", "300"))
PROCESSED_MAX = int(os.getenv("PROCESSED_MAX", "12000"))

CODE_RELEASE = "v20.9.2+V27+V28+V38+V52-MULTI+V55-INCROCI+V56-CORE-LIVE+V67+V70+V72-DAILY-SHADOW"
STATE_GUARD_SCHEMA = 2092
STATE_HISTORY_RECOVERY_COMMITS = max(10, min(120, int(os.getenv("STATE_HISTORY_RECOVERY_COMMITS", "60"))))

MULTI_VERSION = 1  # compatibile con state v20.2/v20.3
MULTI_WINDOW = max(20, int(os.getenv("MULTI_BD_ED_O2_WINDOW", "80")))
MULTI_TOP_N = max(3, min(30, int(os.getenv("MULTI_BD_ED_O2_TOP_N", "12"))))
MULTI_COOLDOWN = max(0, int(os.getenv("MULTI_BD_ED_O2_COOLDOWN", "5")))
MULTI_HORIZON = max(1, int(os.getenv("MULTI_BD_ED_O2_HORIZON", "5")))
MULTI_COOC_WINDOW = max(80, int(os.getenv("MULTI_BD_ED_O2_AMBO_COOC_WINDOW", "900")))
MULTI_SUPER_GATE = max(2, int(os.getenv("MULTI_BD_ED_O2_AMBO_SUPER_GATE", "4")))
MULTI_HISTORY_MAX = max(MULTI_COOC_WINDOW, int(os.getenv("MULTI_BD_ED_O2_HISTORY_MAX", "900")))

# v20.9.2 SETTINA PROFIT FAST — sostituisce la SETTINA normale solo per i NUOVI segnali.
SETTINA_FAST_STRATEGY = "PROFIT_FAST"
SETTINA_FAST_HORIZON = 2
SETTINA_FAST_A2_O2_RANK = 3
SETTINA_FAST_A2_SUPPORT_SUM_MIN = 7
SETTINA_FAST_DE_BD_RANK_MIN = 1
SETTINA_FAST_DE_BD_RANK_MAX = 3
SETTINA_FAST_DE_O2_RANK_MIN = 10
SETTINA_FAST_DE_O2_RANK_MAX = 12
MULTI_RECORD_MAX = max(500, int(os.getenv("MULTI_BD_ED_O2_RECORD_MAX", "8000")))
MULTI_AMBO_RECORD_MAX = max(1500, int(os.getenv("MULTI_BD_ED_O2_AMBO_RECORD_MAX", "24000")))
MULTI_QUAD_RECORD_MAX = max(500, int(os.getenv("MULTI_QUAD_RECORD_MAX", "8000")))
MULTI_QUAD_PENDING_MAX = max(50, int(os.getenv("MULTI_QUAD_PENDING_MAX", "500")))
QUAD_JACCARD_WINDOW = max(160, int(os.getenv("MULTI_QUAD_JACCARD_WINDOW", "900")))
QUAD_POOLS = (10, 11, 12)
QUAD_STAKE_PER_COLPO = 1.0
QUAD_PRIZE_2 = 1.0
QUAD_PRIZE_3 = 10.0
QUAD_PRIZE_4 = 90.0

# v20.9 — SISTEMI LIVE 7 e 9 numeri, sempre 1 €/colpo H1-H5.
# Premi standard 10eLotto (senza Oro/Doppio Oro/Extra).
MULTI_BIG_RECORD_MAX = max(500, int(os.getenv("MULTI_BIG_RECORD_MAX", "12000")))
MULTI_BIG_PENDING_MAX = max(50, int(os.getenv("MULTI_BIG_PENDING_MAX", "1200")))
BIG_STAKE_PER_COLPO = 1.0
BIG7_PRIZES = {0: 1.0, 4: 4.0, 5: 40.0, 6: 400.0, 7: 1600.0}
BIG9_PRIZES = {0: 2.0, 5: 10.0, 6: 40.0, 7: 400.0, 8: 2000.0, 9: 100000.0}

# PRIME — regole congelate dal test storico Jan-Sep 2025.
# A = originale: BD rank 11-12 + O2 rank 6-12.
# A2 ELITE = BD rank 11-12 + O2 rank 2-4 + ora <=08:00 oppure >16:00.
# D = nuova famiglia disgiunta da A/A2: intersezione BD∩ED∩O2 UNICA + ora >16:00.
#     D ELITE = BD rank 1-4; D WIDE = BD rank 5-8.
# X ULTRA = overlay SHADOW dentro D: ED rank 9-12 + ora >17:00 +
#           Extra gap del candidato >= 1 draw sopra il gap del 13° ED.
# C SHADOW = legacy sperimentale v20.6; continua solo sui casi non assorbiti da D.
# B = legacy v20.5: conservato nello state ma NON genera nuovi segnali.
PRIME_VERSION = 4
PRIME_A_BD_RANK_MIN = 11
PRIME_A_BD_RANK_MAX = 12
PRIME_A_O2_RANK_MIN = 6
PRIME_A_O2_RANK_MAX = 12
PRIME_A2_BD_RANK_MIN = 11
PRIME_A2_BD_RANK_MAX = 12
PRIME_A2_O2_RANK_MIN = 2
PRIME_A2_O2_RANK_MAX = 4
PRIME_A2_MORNING_MAX_MIN = 8 * 60       # <= 08:00
PRIME_A2_EVENING_AFTER_MIN = 16 * 60    # > 16:00
PRIME_D_ELITE_BD_RANK_MIN = 1
PRIME_D_ELITE_BD_RANK_MAX = 4
PRIME_D_WIDE_BD_RANK_MIN = 5
PRIME_D_WIDE_BD_RANK_MAX = 8
PRIME_D_AFTER_MIN = 16 * 60              # > 16:00
PRIME_D_INTERSECTION_SIZE = 1
PRIME_X_BD_RANK_MIN = 1
PRIME_X_BD_RANK_MAX = 8
PRIME_X_ED_RANK_MIN = 9
PRIME_X_ED_RANK_MAX = 12
PRIME_X_AFTER_MIN = 17 * 60              # > 17:00
PRIME_X_EXTRA_MARGIN13_MIN = 1            # gap Extra candidato - gap Extra rank13 >= 1
PRIME_C_BD_RANK_MIN = 1
PRIME_C_BD_RANK_MAX = 6
PRIME_C_O2_RANK_MIN = 7
PRIME_C_O2_RANK_MAX = 12
PRIME_C_AFTER_MIN = 16 * 60              # > 16:00

# Notifiche. STANDARD/C/X restano shadow. A, A2 e D notificano l'AMBATA.
NOTIFY_PRIME_A_SIGNAL = os.getenv("MULTI_PRIME_A_NOTIFY_SIGNAL", os.getenv("MULTI_PRIME_NOTIFY_SIGNAL", "1")).lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_A_RESULT = os.getenv("MULTI_PRIME_A_NOTIFY_RESULT", os.getenv("MULTI_PRIME_NOTIFY_RESULT", "1")).lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_A2_SIGNAL = os.getenv("MULTI_PRIME_A2_NOTIFY_SIGNAL", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_A2_RESULT = os.getenv("MULTI_PRIME_A2_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_D_SIGNAL = os.getenv("MULTI_PRIME_D_NOTIFY_SIGNAL", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_D_RESULT = os.getenv("MULTI_PRIME_D_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}
# B non crea nuovi segnali; questa opzione serve solo a chiudere eventuali pending legacy.
NOTIFY_PRIME_B_RESULT = os.getenv("MULTI_PRIME_B_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_TRIANGLE_OFF_HIT = os.getenv("MULTI_TRIANGLE_OFF_NOTIFY_HIT", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_STANDARD_SIGNAL = os.getenv("MULTI_STANDARD_NOTIFY_SIGNAL", "0").lower() not in {"0", "false", "no", "off"}
NOTIFY_STANDARD_RESULT = os.getenv("MULTI_STANDARD_NOTIFY_RESULT", "0").lower() not in {"0", "false", "no", "off"}
NOTIFY_SUPER_RESULT = os.getenv("MULTI_SUPER_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_QUAD_SIGNAL = os.getenv("MULTI_QUAD_NOTIFY_SIGNAL", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_QUAD_RESULT = os.getenv("MULTI_QUAD_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_QUAD_SHADOW_UPGRADE = os.getenv("MULTI_QUAD_NOTIFY_SHADOW_UPGRADE", "0").lower() not in {"0", "false", "no", "off"}
NOTIFY_BIG_SIGNAL = os.getenv("MULTI_BIG_NOTIFY_SIGNAL", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_BIG_RESULT = os.getenv("MULTI_BIG_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_BIG_SHADOW_UPGRADE = os.getenv("MULTI_BIG_NOTIFY_SHADOW_UPGRADE", "0").lower() not in {"0", "false", "no", "off"}

_LAST_GIT_COMMIT_TS = 0.0

_ITALIAN_MONTHS = {
    "gen": 1, "gennaio": 1, "feb": 2, "febbraio": 2, "mar": 3, "marzo": 3,
    "apr": 4, "aprile": 4, "mag": 5, "maggio": 5, "giu": 6, "giugno": 6,
    "lug": 7, "luglio": 7, "ago": 8, "agosto": 8, "set": 9, "sett": 9,
    "settembre": 9, "ott": 10, "ottobre": 10, "nov": 11, "novembre": 11,
    "dic": 12, "dicembre": 12,
}


# ============================================================
# UTILS
# ============================================================
def now_dt():
    return datetime.now(BOT_TZ)


def now_txt():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def day_key():
    return now_dt().strftime("%Y-%m-%d")


def draw_key(day, draw_id):
    return f"{str(day)}#{int(draw_id):03d}"


def order_key(key):
    try:
        day, sid = str(key).rsplit("#", 1)
        return datetime.fromisoformat(day).date().toordinal(), int(sid)
    except Exception:
        return None


def safe_pct(num, den):
    return (100.0 * float(num) / float(den)) if den else 0.0


def split_telegram_text(text, limit=3900):
    """Divide messaggi lunghi senza spezzare brutalmente le righe."""
    txt=str(text or "")
    if len(txt)<=limit:
        return [txt] if txt else []
    out=[]; cur=[]; n=0
    for line in txt.splitlines(True):
        if cur and n+len(line)>limit:
            out.append("".join(cur).rstrip()); cur=[]; n=0
        while len(line)>limit:
            if cur:
                out.append("".join(cur).rstrip()); cur=[]; n=0
            out.append(line[:limit]); line=line[limit:]
        cur.append(line); n+=len(line)
    if cur:
        out.append("".join(cur).rstrip())
    return [x for x in out if x]


def console_log(message):
    print(f"[{now_txt()}] {message}", flush=True)


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


def lottologia_url_for_offset(day_offset):
    day_offset = int(day_offset)
    if day_offset <= 0:
        return f"{LOTTOLOGIA_BASE}/estrazioni/"
    if day_offset == 1:
        return f"{LOTTOLOGIA_BASE}/estrazioni-ieri"
    return f"{LOTTOLOGIA_BASE}/estrazioni-{day_offset}gg-fa"


def parse_lottologia_multichannel_records(url, expected_day=None):
    """Estrae Base + Oro + Doppio Oro + Extra da Lottologia."""
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
        mon = _ITALIAN_MONTHS.get(str(m.group(3)).lower().strip().rstrip("."))
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
            block,
            re.IGNORECASE | re.DOTALL,
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
        distinct = [n for n in dlist if n != oro]
        doppio = int(distinct[0] if distinct else (dlist[-1] if dlist else 0))
        if not (1 <= doppio <= 90):
            continue
        if oro not in nums or doppio not in nums:
            continue
        if len(extra) != 15 or len(set(extra)) != 15 or (set(extra) & set(nums)):
            continue

        out.append({
            "day": rec_day,
            "draw_id": draw_id,
            "key": draw_key(rec_day, draw_id),
            "nums": list(map(int, nums)),
            "oro": oro,
            "doppio_oro": doppio,
            "extra": list(map(int, extra)),
            "time": str(m.group(5)),
        })

    dedup = {str(r["key"]): r for r in out}
    return sorted(dedup.values(), key=lambda r: (r["day"], int(r["draw_id"])))


def fetch_multichannel_recent(days=5):
    days = max(1, min(5, int(days)))
    merged = {}
    today = now_dt().date()
    for offset in range(days):
        expected = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            rows = parse_lottologia_multichannel_records(
                lottologia_url_for_offset(offset), expected_day=expected
            )
        except Exception as exc:
            console_log(f"MULTI parser offset={offset} fail | {type(exc).__name__}: {exc}")
            continue
        for row in rows:
            merged[str(row["key"])] = row
    return sorted(merged.values(), key=lambda r: (r["day"], int(r["draw_id"])))


# ============================================================
# GIT STATE PERSISTENCE
# ============================================================
def _run_git(args, timeout=35):
    return subprocess.run(
        ["git", *args],
        cwd=BASE_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def git_commit_state_if_needed(force=False):
    """Pubblica state principale + copia HARD LOCK nello stesso commit.

    In caso di push concorrente conserva in memoria le copie locali PRIMA del reset --hard,
    le fonde con entrambe le copie remote e solo dopo riallinea il checkout.
    """
    global _LAST_GIT_COMMIT_TS
    if not PERSIST_GIT_STATE:
        return {"ok": True, "action": "disabled", "detail": "PERSIST_GIT_STATE=0"}
    if not os.path.exists(os.path.join(BASE_DIR, ".git")):
        return {"ok": True, "action": "no-git", "detail": "repository .git non presente"}

    now = time.time()
    if not force and now - _LAST_GIT_COMMIT_TS < GIT_COMMIT_MIN_SECONDS:
        return {"ok": True, "action": "throttled", "detail": "commit rimandato"}

    rel = os.path.relpath(STATE_FILE, BASE_DIR)
    hard_rel = os.path.relpath(STATE_HARDLOCK_FILE, BASE_DIR)
    rels = [rel]
    if os.path.exists(STATE_HARDLOCK_FILE):
        rels.append(hard_rel)

    a = _run_git(["add", *rels])
    if a.returncode != 0:
        return {"ok": False, "action": "add-fail", "detail": a.stderr.strip()[-500:]}

    diff = _run_git(["diff", "--cached", "--quiet", "--", *rels])
    if diff.returncode == 0:
        _LAST_GIT_COMMIT_TS = now
        return {"ok": True, "action": "no-change", "detail": "state invariato"}

    msg = f"state: MULTI PRIME HARD LOCK {now_txt()}"
    c = _run_git(["-c", "user.name=github-actions[bot]",
                  "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                  "commit", "-m", msg, "--", *rels])
    if c.returncode != 0:
        return {"ok": False, "action": "commit-fail", "detail": c.stderr.strip()[-500:]}

    branch = _git_remote_branch()
    p = _run_git(["push", "origin", f"HEAD:{branch}"], timeout=45)
    if p.returncode != 0:
        # Congela le copie LOCALI prima di qualunque reset Git.
        local_snapshot = _read_json_file(STATE_FILE)
        hard_snapshot = _read_json_file(STATE_HARDLOCK_FILE)
        local_anchor, _ = _merge_state_data(local_snapshot, hard_snapshot)

        f = _run_git(["fetch", "--quiet", "origin", branch], timeout=45)
        if f.returncode != 0:
            return {"ok": False, "action": "push-fail-fetch-fail", "detail": p.stderr.strip()[-500:]}
        remote_snapshot, _ = _fetch_remote_state()
        remote_hard, _ = _fetch_remote_hardlock_state()
        remote_merged, _ = _merge_state_data(remote_snapshot, remote_hard)
        merged_snapshot, _ = _merge_state_data(local_anchor, remote_merged)
        merged_snapshot, _, _ = _apply_hardlock_floor(merged_snapshot, local_anchor)
        if not isinstance(merged_snapshot, dict):
            return {"ok": False, "action": "push-fail-merge-fail", "detail": p.stderr.strip()[-500:]}

        rr = _run_git(["reset", "--hard", f"origin/{branch}"], timeout=45)
        if rr.returncode != 0:
            return {"ok": False, "action": "push-fail-reset-fail", "detail": rr.stderr.strip()[-500:]}
        atomic_write_json(STATE_FILE, merged_snapshot)
        atomic_write_json(STATE_HARDLOCK_FILE, merged_snapshot)

        a2 = _run_git(["add", rel, hard_rel])
        if a2.returncode != 0:
            return {"ok": False, "action": "retry-add-fail", "detail": a2.stderr.strip()[-500:]}
        d2 = _run_git(["diff", "--cached", "--quiet", "--", rel, hard_rel])
        if d2.returncode == 0:
            _LAST_GIT_COMMIT_TS = now
            return {"ok": True, "action": "remote-already-current", "detail": "state HARD LOCK gia presente sul remoto"}
        c2 = _run_git(["-c", "user.name=github-actions[bot]",
                       "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                       "commit", "-m", msg + " [retry]", "--", rel, hard_rel])
        if c2.returncode != 0:
            return {"ok": False, "action": "retry-commit-fail", "detail": c2.stderr.strip()[-500:]}
        p2 = _run_git(["push", "origin", f"HEAD:{branch}"], timeout=45)
        if p2.returncode != 0:
            return {"ok": False, "action": "retry-push-fail", "detail": p2.stderr.strip()[-500:]}
        _LAST_GIT_COMMIT_TS = now
        return {"ok": True, "action": "pushed-after-hardlock-merge", "detail": msg}

    _LAST_GIT_COMMIT_TS = now
    return {"ok": True, "action": "pushed", "detail": msg}

def _git_remote_branch():
    """Trova il branch remoto senza assumere che GitHub Actions sia su HEAD locale."""
    env_branch = str(os.getenv("GITHUB_REF_NAME") or "").strip()
    if env_branch and env_branch not in {"HEAD", ""} and not env_branch.startswith("refs/"):
        return env_branch
    r = _run_git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if r.returncode == 0 and r.stdout.strip():
        x = r.stdout.strip()
        return x.split("/", 1)[1] if x.startswith("origin/") else x
    r = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if r.returncode == 0:
        x = r.stdout.strip()
        if x and x != "HEAD":
            return x
    return "main"


def _state_progress(data):
    """Score monotono per scegliere lo state più avanzato, non il file più recente per timestamp."""
    if not isinstance(data, dict):
        return (-1, -1, -1, -1, -1, -1)
    mc = data.get("multichannel_bd12_ed12_o2f12_v1")
    if not isinstance(mc, dict):
        return (-1, -1, -1, -1, -1, -1)
    last_key = None
    hist = mc.get("history") or []
    if hist and isinstance(hist[-1], dict):
        last_key = hist[-1].get("key")
    if not last_key:
        last_key = data.get("last_draw_key")
    ok = order_key(last_key) or (-1, -1)
    closed = len(mc.get("records") or []) + len(mc.get("ambo_records") or []) + len(mc.get("quad_records") or []) + len(mc.get("big_records") or [])
    counters = (
        int(mc.get("scans", 0) or 0)
        + int(mc.get("signals", 0) or 0)
        + int(mc.get("prime_a_signals", mc.get("prime_signals", 0)) or 0)
        + int(mc.get("prime_b_signals", 0) or 0)
        + int(mc.get("prime_a2_signals", 0) or 0)
        + int(mc.get("prime_d_elite_signals", 0) or 0)
        + int(mc.get("prime_d_wide_signals", 0) or 0)
        + int(mc.get("prime_x_signals", 0) or 0)
        + int(mc.get("prime_c_signals", 0) or 0)
        + int(mc.get("quad_signals", 0) or 0)
        + int(mc.get("quad_elite_signals", 0) or 0)
        + int(mc.get("big7_signals", 0) or 0)
        + int(mc.get("big9_signals", 0) or 0)
    )
    pending = len(mc.get("pending") or []) + len(mc.get("ambo_pending") or []) + len(mc.get("quad_pending") or []) + len(mc.get("big_pending") or [])
    rev = int(data.get("multi_state_revision", 0) or 0)
    return (ok[0], ok[1], int(mc.get("draw_seq", 0) or 0), closed, counters, rev + pending)


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            x = json.load(f)
        return x if isinstance(x, dict) else None
    except Exception:
        return None


def _fast_forward_repo_to_remote():
    """
    GitHub Actions può avviare un runner da uno SHA precedente agli ultimi commit di state.
    Prima di caricare lo state prova un fast-forward del checkout al branch remoto.
    È sicuro: non crea merge commit e non forza niente.
    """
    if not os.path.exists(os.path.join(BASE_DIR, ".git")):
        return "no-git"
    branch = _git_remote_branch()
    f = _run_git(["fetch", "--quiet", "origin", branch], timeout=45)
    if f.returncode != 0:
        return "fetch-fail"
    m = _run_git(["merge", "--ff-only", f"origin/{branch}"], timeout=45)
    if m.returncode == 0:
        return "ff-ok"
    # Se non è possibile fare FF, non tocchiamo il checkout: useremo comunque
    # il confronto LOCAL/REMOTE sul solo JSON dello state.
    return "ff-skip"


def _fetch_remote_json_file(path, missing_label="remote-state-missing"):
    """Legge un JSON tracciato dal branch remoto senza modificare il checkout."""
    if not os.path.exists(os.path.join(BASE_DIR, ".git")):
        return None, "no-git"
    branch = _git_remote_branch()
    f = _run_git(["fetch", "--quiet", "origin", branch], timeout=45)
    if f.returncode != 0:
        return None, "fetch-fail"
    rel = os.path.relpath(path, BASE_DIR).replace(os.sep, "/")
    g = _run_git(["show", f"origin/{branch}:{rel}"], timeout=20)
    if g.returncode != 0 or not g.stdout.strip():
        return None, missing_label
    try:
        data = json.loads(g.stdout)
        if not isinstance(data, dict):
            return None, "remote-json-invalid"
        return data, f"origin/{branch}:{rel}"
    except Exception as exc:
        return None, f"remote-json-{type(exc).__name__}"


def _fetch_remote_state():
    """Legge SOLO lo state principale dal branch remoto."""
    return _fetch_remote_json_file(STATE_FILE, "remote-state-missing")


def _fetch_remote_hardlock_state():
    """Legge la copia ridondante HARD LOCK dal branch remoto, se esiste."""
    return _fetch_remote_json_file(STATE_HARDLOCK_FILE, "remote-hardlock-missing")


def _fetch_state_history_candidates(limit=None):
    """
    Recupera versioni precedenti dello state dalla STORIA Git del branch remoto.
    Serve a ripristinare uno state avanzato anche se HEAD e' stato accidentalmente
    sovrascritto con una copia piu vecchia durante un cambio versione.
    """
    if not os.path.exists(os.path.join(BASE_DIR, ".git")):
        return [], {"status": "no-git", "count": 0, "max_rev": 0}
    branch = _git_remote_branch()
    f = _run_git(["fetch", "--quiet", "origin", branch], timeout=45)
    if f.returncode != 0:
        return [], {"status": "fetch-fail", "count": 0, "max_rev": 0}
    rel = os.path.relpath(STATE_FILE, BASE_DIR).replace(os.sep, "/")
    lim = int(limit or STATE_HISTORY_RECOVERY_COMMITS)
    lg = _run_git(["log", f"-n{lim}", "--format=%H", f"origin/{branch}", "--", rel], timeout=35)
    if lg.returncode != 0:
        return [], {"status": "log-fail", "count": 0, "max_rev": 0}
    out = []
    max_rev = 0
    for sha in [x.strip() for x in lg.stdout.splitlines() if x.strip()]:
        g = _run_git(["show", f"{sha}:{rel}"], timeout=12)
        if g.returncode != 0 or not g.stdout.strip():
            continue
        try:
            data = json.loads(g.stdout)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        rev = int(data.get("multi_state_revision", 0) or 0)
        max_rev = max(max_rev, rev)
        out.append((sha, data))
    return out, {"status": "ok", "count": len(out), "max_rev": max_rev, "branch": branch}


def _key_max(a, b):
    oa, ob = order_key(a), order_key(b)
    if oa is None: return b
    if ob is None: return a
    return a if oa >= ob else b


def _key_min(a, b):
    oa, ob = order_key(a), order_key(b)
    if oa is None: return b
    if ob is None: return a
    return a if oa <= ob else b


def _row_last_order(row):
    if not isinstance(row, dict): return (-1, -1)
    for k in ("closed_key", "last_key", "origin_key", "key"):
        o = order_key(row.get(k))
        if o is not None: return o
    return (-1, -1)


def _row_progress(row):
    if not isinstance(row, dict): return (-1, -1, -1, -1, -1)
    o = _row_last_order(row)
    return (int(bool(row.get("closed"))), int(row.get("age",0) or 0), int(bool(row.get("hit"))), o[0]*1000+o[1], -int(row.get("hit_colpo") or 999))


def _merge_rows(a_rows, b_rows, identity, max_len):
    out = {}
    for row in list(a_rows or []) + list(b_rows or []):
        if not isinstance(row, dict): continue
        rid = identity(row)
        if rid is None: continue
        old = out.get(rid)
        if old is None or _row_progress(row) > _row_progress(old): out[rid] = dict(row)
    rows = list(out.values())
    rows.sort(key=lambda r: (_row_last_order(r), str(identity(r))))
    return rows[-max_len:]


def _signal_id(r):
    try: return f"{r.get('origin_key')}|N{int(r.get('num')):02d}"
    except Exception: return None


def _ambo_id(r):
    try:
        oid = str(r.get("origin_id") or f"{r.get('origin_key')}|M{int(r.get('main')):02d}")
        return f"{oid}|{str(r.get('slot') or 'AMBO')}"
    except Exception: return None


def _history_id(r):
    return str(r.get("key")) if isinstance(r, dict) and r.get("key") else None


def _quad_id(r):
    try:
        q = tuple(sorted(int(x) for x in (r.get("quartet") or [])))
        if len(q) != 4:
            return None
        return f"{r.get('origin_key')}|M{int(r.get('main')):02d}|Q{'-'.join(f'{x:02d}' for x in q)}"
    except Exception:
        return None


def _big_id(r):
    try:
        nums = tuple(sorted(int(x) for x in (r.get("numbers") or [])))
        size = int(r.get("system_size") or len(nums))
        if size not in (7, 9) or len(nums) != size:
            return None
        return f"{r.get('origin_key')}|M{int(r.get('main')):02d}|S{size}|{'-'.join(f'{x:02d}' for x in nums)}"
    except Exception:
        return None


def _latest_obj(a, b, keys=("closed_key", "origin_key", "key")):
    if not isinstance(a, dict): return b if isinstance(b, dict) else None
    if not isinstance(b, dict): return a
    def score(x):
        for k in keys:
            o = order_key(x.get(k))
            if o is not None: return o
        return (-1,-1)
    return a if score(a) >= score(b) else b


def _merge_multichannel_state(a, b):
    if not isinstance(a, dict): return dict(b) if isinstance(b, dict) else None
    if not isinstance(b, dict): return dict(a)
    da={"multichannel_bd12_ed12_o2f12_v1":a}; db={"multichannel_bd12_ed12_o2f12_v1":b}
    base = dict(a if _state_progress(da) >= _state_progress(db) else b)
    hist = _merge_rows(a.get("history"), b.get("history"), _history_id, MULTI_HISTORY_MAX)
    rec = _merge_rows(a.get("records"), b.get("records"), _signal_id, MULTI_RECORD_MAX)
    pen = _merge_rows(a.get("pending"), b.get("pending"), _signal_id, 200)
    closed={_signal_id(r) for r in rec}; pen=[r for r in pen if _signal_id(r) not in closed]
    arec = _merge_rows(a.get("ambo_records"), b.get("ambo_records"), _ambo_id, MULTI_AMBO_RECORD_MAX)
    apen = _merge_rows(a.get("ambo_pending"), b.get("ambo_pending"), _ambo_id, 900)
    aclosed={_ambo_id(r) for r in arec}; apen=[r for r in apen if _ambo_id(r) not in aclosed]
    qrec = _merge_rows(a.get("quad_records"), b.get("quad_records"), _quad_id, MULTI_QUAD_RECORD_MAX)
    qpen = _merge_rows(a.get("quad_pending"), b.get("quad_pending"), _quad_id, MULTI_QUAD_PENDING_MAX)
    qclosed={_quad_id(r) for r in qrec}; qpen=[r for r in qpen if _quad_id(r) not in qclosed]
    brec = _merge_rows(a.get("big_records"), b.get("big_records"), _big_id, MULTI_BIG_RECORD_MAX)
    bpen = _merge_rows(a.get("big_pending"), b.get("big_pending"), _big_id, MULTI_BIG_PENDING_MAX)
    bclosed={_big_id(r) for r in brec}; bpen=[r for r in bpen if _big_id(r) not in bclosed]
    base.update({"history":hist,"records":rec,"pending":pen,"ambo_records":arec,"ambo_pending":apen,"quad_records":qrec,"quad_pending":qpen,"big_records":brec,"big_pending":bpen})
    base["draw_seq"] = max(int(a.get("draw_seq",0) or 0), int(b.get("draw_seq",0) or 0), len(hist))
    for k in ("scans","signals","no_signal","cooldown_skips","ambo_origins","ambo_super_signals","quad_signals","quad_elite_signals","big7_signals","big9_signals","big7_fast_signals"):
        base[k]=max(int(a.get(k,0) or 0),int(b.get(k,0) or 0))
    # I contatori quaterna non possono essere inferiori ai record/pending effettivamente fusi.
    qids={_quad_id(r) for r in qrec+qpen if _quad_id(r)}
    elite_ids={_quad_id(r) for r in qrec+qpen if _quad_id(r) and str(r.get("quad_level") or "").upper()=="ELITE"}
    base["quad_signals"]=max(int(base.get("quad_signals",0) or 0),len(qids))
    base["quad_elite_signals"]=max(int(base.get("quad_elite_signals",0) or 0),len(elite_ids))
    big7_ids={_big_id(r) for r in brec+bpen if _big_id(r) and int(r.get("system_size",0) or 0)==7}
    big9_ids={_big_id(r) for r in brec+bpen if _big_id(r) and int(r.get("system_size",0) or 0)==9}
    base["big7_signals"]=max(int(base.get("big7_signals",0) or 0),len(big7_ids))
    base["big9_signals"]=max(int(base.get("big9_signals",0) or 0),len(big9_ids))
    big7_fast_ids={_big_id(r) for r in brec+bpen if _big_id(r) and int(r.get("system_size",0) or 0)==7 and str(r.get("strategy") or "").upper()==SETTINA_FAST_STRATEGY}
    base["big7_fast_signals"]=max(int(a.get("big7_fast_signals",0) or 0),int(b.get("big7_fast_signals",0) or 0),len(big7_fast_ids))
    sigrows=rec+pen
    def tier(r):
        t=str(r.get("tier") or "").upper()
        if t in {"A","A2","DE","DW","B","C","STD"}: return t
        return "A" if bool(r.get("prime")) else "STD"
    ac=len({_signal_id(r) for r in sigrows if tier(r)=="A"})
    a2c=len({_signal_id(r) for r in sigrows if tier(r)=="A2"})
    dec=len({_signal_id(r) for r in sigrows if tier(r)=="DE"})
    dwc=len({_signal_id(r) for r in sigrows if tier(r)=="DW"})
    xc=len({_signal_id(r) for r in sigrows if bool(r.get("x_ultra"))})
    bc=len({_signal_id(r) for r in sigrows if tier(r)=="B"})
    cc=len({_signal_id(r) for r in sigrows if tier(r)=="C"})
    base["prime_a_signals"]=max(int(a.get("prime_a_signals",a.get("prime_signals",0)) or 0),int(b.get("prime_a_signals",b.get("prime_signals",0)) or 0),ac)
    base["prime_signals"]=base["prime_a_signals"]
    base["prime_a2_signals"]=max(int(a.get("prime_a2_signals",0) or 0),int(b.get("prime_a2_signals",0) or 0),a2c)
    base["prime_d_elite_signals"]=max(int(a.get("prime_d_elite_signals",0) or 0),int(b.get("prime_d_elite_signals",0) or 0),dec)
    base["prime_d_wide_signals"]=max(int(a.get("prime_d_wide_signals",0) or 0),int(b.get("prime_d_wide_signals",0) or 0),dwc)
    base["prime_x_signals"]=max(int(a.get("prime_x_signals",0) or 0),int(b.get("prime_x_signals",0) or 0),xc)
    base["prime_b_signals"]=max(int(a.get("prime_b_signals",0) or 0),int(b.get("prime_b_signals",0) or 0),bc)
    base["prime_c_signals"]=max(int(a.get("prime_c_signals",0) or 0),int(b.get("prime_c_signals",0) or 0),cc)
    lss={}
    for src in (a.get("last_signal_seq"),b.get("last_signal_seq")):
        if isinstance(src,dict):
            for k,v in src.items():
                try: ik,iv=int(k),int(v)
                except Exception: continue
                lss[str(ik)]=max(int(lss.get(str(ik),0) or 0),iv)
    base["last_signal_seq"]=lss
    for k in ("start_from_key","ambo_started_from_key","prime_started_from_key","prime_a_started_from_key","prime_a2_started_from_key","prime_d_elite_started_from_key","prime_d_wide_started_from_key","prime_x_started_from_key","prime_b_started_from_key","prime_c_started_from_key","triangle_started_from_key","v2071_started_from_key","quad_started_from_key","big_started_from_key","big7_fast_started_from_key"):
        base[k]=_key_min(a.get(k),b.get(k))
    for k in ("started_at","ambo_started_at","prime_started_at","prime_a_started_at","prime_a2_started_at","prime_d_elite_started_at","prime_d_wide_started_at","prime_x_started_at","prime_b_started_at","prime_c_started_at","triangle_started_at","v2071_started_at","quad_started_at","big_started_at","big7_fast_started_at"):
        vals=[x for x in (a.get(k),b.get(k)) if isinstance(x,str) and x]; base[k]=min(vals) if vals else None
    # I baseline della FIX devono riferirsi alla stessa prima base forward: prendiamo il minimo
    # quando entrambe le copie li hanno, altrimenti quello disponibile.
    for k in ("v2071_scans_base","v2071_signals_base","v2071_draw_seq_base"):
        vals=[]
        for src in (a,b):
            try:
                if src.get("v2071_started_from_key") and src.get(k) is not None:
                    vals.append(int(src.get(k) or 0))
            except Exception:
                pass
        base[k]=min(vals) if vals else 0
    base["last_armed_key"]=_key_max(a.get("last_armed_key"),b.get("last_armed_key"))
    base["last_signal"]=_latest_obj(a.get("last_signal"),b.get("last_signal"),("origin_key","key"))
    base["last_result"]=_latest_obj(a.get("last_result"),b.get("last_result"))
    base["last_ambo_signal"]=_latest_obj(a.get("last_ambo_signal"),b.get("last_ambo_signal"),("origin_key","key"))
    base["last_ambo_result"]=_latest_obj(a.get("last_ambo_result"),b.get("last_ambo_result"))
    base["last_quad_signal"]=_latest_obj(a.get("last_quad_signal"),b.get("last_quad_signal"),("origin_key","key"))
    base["last_quad_result"]=_latest_obj(a.get("last_quad_result"),b.get("last_quad_result"))
    base["last_big_signal"]=_latest_obj(a.get("last_big_signal"),b.get("last_big_signal"),("origin_key","key"))
    base["last_big_result"]=_latest_obj(a.get("last_big_result"),b.get("last_big_result"))
    return base



def _merge_forward_tracker_state(a, b):
    """Merge conservativo dei tracker V27/V28 in tutti i percorsi HARD LOCK.
    Closed vince su pending del medesimo origin per impedire di riaprire H1.
    """
    if not isinstance(a, dict):
        return dict(b) if isinstance(b, dict) else None
    if not isinstance(b, dict):
        return dict(a)
    def merged_rows(k):
        saved = {}
        for d in (a,b):
            for x in d.get(k) or []:
                if isinstance(x,dict) and x.get('origin_key'):
                    saved[str(x['origin_key'])] = x
        return [saved[k] for k in sorted(saved, key=lambda x:order_key(x) or (-1,-1))][-1500:]
    closed = merged_rows('closed')
    signals = merged_rows('signals')
    ended = {x['origin_key'] for x in closed}
    pending = []
    for d in (a,b):
        p = d.get('pending')
        if isinstance(p,dict) and p.get('origin_key') and p['origin_key'] not in ended:
            pending.append(p)
    pending.sort(key=lambda x: order_key(x.get('origin_key')) or (-1,-1))
    return {'start_key':_key_min(a.get('start_key'),b.get('start_key')) or a.get('start_key') or b.get('start_key') or '',
            'last_evaluated_origin':_key_max(a.get('last_evaluated_origin'),b.get('last_evaluated_origin')) or '',
            'pending':pending[-1] if pending else None, 'signals':signals,'closed':closed}

def _merge_v38_state(a, b):
    """Conserva coppie distinte anche se generate nello stesso concorso.
    Per un ID, CLOSED/MISSING prevale sempre su PENDING; nessuna riapertura H1.
    """
    aa = a if isinstance(a, dict) else {}
    bb = b if isinstance(b, dict) else {}
    if not aa and not bb:
        return None
    entries = {}
    for src in (aa, bb):
        for item in (src.get("plays") or []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            key = str(item["id"])
            previous = entries.get(key)
            rank = {"PENDING": 0, "MISSING": 1, "CLOSED": 2}
            if previous is None or rank.get(str(item.get("status")), -1) > rank.get(str(previous.get("status")), -1):
                entries[key] = dict(item)
    plays = sorted(entries.values(), key=lambda x: (order_key(x.get("origin_key")) or (-1,-1), str(x.get("id"))))
    starts = [str(src.get("start_key")) for src in (aa,bb) if src.get("start_key")]
    return {
        "start_key": min(starts, key=lambda x: order_key(x) or (99999999,99999999)) if starts else "",
        "last_evaluated_origin": _key_max(aa.get("last_evaluated_origin"), bb.get("last_evaluated_origin")) or "",
        "plays": plays[-12000:],
    }


def _merge_state_data(local_data, remote_data):
    if not isinstance(local_data, dict): return (dict(remote_data),"REMOTE") if isinstance(remote_data,dict) else (None,"NONE")
    if not isinstance(remote_data, dict): return dict(local_data),"LOCAL"
    lp,rp=_state_progress(local_data),_state_progress(remote_data)
    base=dict(local_data if lp>=rp else remote_data)
    mm=_merge_multichannel_state(local_data.get("multichannel_bd12_ed12_o2f12_v1"),remote_data.get("multichannel_bd12_ed12_o2f12_v1"))
    if mm is not None: base["multichannel_bd12_ed12_o2f12_v1"]=mm
    for branch in (V27_KEY,V28_KEY):
        merged_branch=_merge_forward_tracker_state(local_data.get(branch),remote_data.get(branch))
        if merged_branch is not None:
            base[branch]=merged_branch
    merged_v38 = _merge_v38_state(local_data.get(V38_KEY), remote_data.get(V38_KEY))
    if merged_v38 is not None:
        base[V38_KEY] = merged_v38
    merged_v52 = _merge_v52_state(local_data.get(V52_KEY),remote_data.get(V52_KEY))
    if merged_v52 is not None:
        base[V52_KEY] = merged_v52
    merged_v55 = _merge_v55_state(local_data.get(V55_KEY), remote_data.get(V55_KEY))
    if merged_v55 is not None:
        base[V55_KEY] = merged_v55
    merged_v56 = _merge_v56_state(local_data.get(V56_KEY), remote_data.get(V56_KEY))
    if merged_v56 is not None:
        base[V56_KEY] = merged_v56
    merged_v67 = _merge_v67_state(local_data.get(V67_KEY), remote_data.get(V67_KEY))
    if merged_v67 is not None:
        base[V67_KEY] = merged_v67
    merged_v70 = _merge_v70_state(local_data.get(V70_KEY), remote_data.get(V70_KEY))
    if merged_v70 is not None:
        base[V70_KEY] = merged_v70
    merged_v72 = _merge_v72_state(local_data.get(V72_KEY), remote_data.get(V72_KEY))
    if merged_v72 is not None:
        base[V72_KEY] = merged_v72
    vals=[]; seen=set()
    for x in list(local_data.get("processed") or [])+list(remote_data.get("processed") or []):
        if isinstance(x,str) and x not in seen: seen.add(x); vals.append(x)
    vals.sort(key=lambda x:order_key(x) or (-1,-1)); base["processed"]=vals[-PROCESSED_MAX:]
    base["last_draw_key"]=_key_max(local_data.get("last_draw_key"),remote_data.get("last_draw_key"))
    base["multi_state_revision"]=max(int(local_data.get("multi_state_revision",0) or 0),int(remote_data.get("multi_state_revision",0) or 0))
    ss=[x for x in (local_data.get("saved_at"),remote_data.get("saved_at")) if isinstance(x,str) and x]
    if ss: base["saved_at"]=max(ss)
    return base,"MERGED_LOCAL_REMOTE"


def _merge_many_states(candidates):
    merged = None
    used = []
    for label, data in candidates:
        if not isinstance(data, dict):
            continue
        if merged is None:
            merged = dict(data)
            used.append(label)
            continue
        merged, _ = _merge_state_data(merged, data)
        used.append(label)
    return merged, used


def _state_last_key(data):
    if not isinstance(data, dict):
        return None
    mc = data.get("multichannel_bd12_ed12_o2f12_v1")
    if isinstance(mc, dict):
        hist = mc.get("history") or []
        if hist and isinstance(hist[-1], dict) and hist[-1].get("key"):
            return str(hist[-1].get("key"))
    return str(data.get("last_draw_key")) if data.get("last_draw_key") else None


def _detect_state_regressions(candidate, floor):
    """Ritorna le regressioni che un candidato causerebbe rispetto al floor già raggiunto.

    I pending non sono usati come contatore monotono perché possono chiudersi normalmente;
    record/pending vengono comunque fusi per ID da _merge_multichannel_state.
    """
    if not isinstance(floor, dict):
        return []
    if not isinstance(candidate, dict):
        return ["state-assente"]
    out = []
    ck, fk = order_key(_state_last_key(candidate)), order_key(_state_last_key(floor))
    if fk is not None and (ck is None or ck < fk):
        out.append(f"last:{_state_last_key(candidate) or '-'}<{_state_last_key(floor)}")
    cm = candidate.get("multichannel_bd12_ed12_o2f12_v1") or {}
    fm = floor.get("multichannel_bd12_ed12_o2f12_v1") or {}
    for k in (
        "draw_seq", "scans", "signals", "no_signal", "cooldown_skips",
        "prime_a_signals", "prime_a2_signals", "prime_d_elite_signals",
        "prime_d_wide_signals", "prime_x_signals", "prime_c_signals",
        "quad_signals", "quad_elite_signals", "big7_signals", "big9_signals", "big7_fast_signals",
    ):
        cv = int(cm.get(k, cm.get("prime_signals", 0) if k == "prime_a_signals" else 0) or 0)
        fv = int(fm.get(k, fm.get("prime_signals", 0) if k == "prime_a_signals" else 0) or 0)
        if cv < fv:
            out.append(f"{k}:{cv}<{fv}")
    for k in ("records", "ambo_records", "quad_records", "big_records"):
        if len(cm.get(k) or []) < len(fm.get(k) or []):
            out.append(f"{k}:{len(cm.get(k) or [])}<{len(fm.get(k) or [])}")
    return out


def _apply_hardlock_floor(candidate, floor):
    """Fonde il floor dentro il candidato e preserva i marker forward già congelati.

    Il floor è lo snapshot letto PRIMA di qualsiasi operazione Git nel processo corrente.
    Nessuna copia remota può quindi spostare indietro la base #196 (o qualunque base futura).
    """
    if not isinstance(floor, dict):
        return candidate, False, []
    regressions = _detect_state_regressions(candidate, floor)
    merged, _ = _merge_state_data(candidate, floor)
    if not isinstance(merged, dict):
        merged = dict(floor)
    mm = merged.get("multichannel_bd12_ed12_o2f12_v1")
    fm = floor.get("multichannel_bd12_ed12_o2f12_v1")
    if isinstance(mm, dict) and isinstance(fm, dict):
        # Questi marker sono forward/no-backfill: una volta fissati NON devono tornare
        # a una base diversa durante un cambio codice o una rotazione runner.
        for k in (
            "prime_a2_started_from_key", "prime_d_elite_started_from_key",
            "prime_d_wide_started_from_key", "prime_x_started_from_key",
            "v2071_started_from_key", "quad_started_from_key", "big_started_from_key", "big7_fast_started_from_key",
        ):
            if fm.get(k):
                mm[k] = fm.get(k)
        for k in (
            "prime_a2_started_at", "prime_d_elite_started_at", "prime_d_wide_started_at",
            "prime_x_started_at", "v2071_started_at", "quad_started_at", "big_started_at",
        ):
            if fm.get(k):
                mm[k] = fm.get(k)
        if fm.get("v2071_started_from_key"):
            for k in ("v2071_scans_base", "v2071_signals_base", "v2071_draw_seq_base"):
                if fm.get(k) is not None:
                    mm[k] = int(fm.get(k) or 0)
        merged["multichannel_bd12_ed12_o2f12_v1"] = mm
    return merged, bool(regressions), regressions


def _merge_state_candidates(candidates):
    merged = None
    labels = []
    for label, data in candidates:
        if not isinstance(data, dict):
            continue
        if merged is None:
            merged = dict(data)
        else:
            merged, _ = _merge_state_data(merged, data)
        labels.append(label)
    return merged, labels


def _best_available_state(local_data, remote_data, history_candidates=None):
    candidates = [("LOCAL", local_data), ("REMOTE_HEAD", remote_data)]
    for sha, data in (history_candidates or []):
        candidates.append((f"GIT:{sha[:8]}", data))
    merged, used = _merge_many_states(candidates)
    if not isinstance(merged, dict):
        return None, "NONE", []
    source = "MERGED_LOCAL_REMOTE_GIT_HISTORY" if history_candidates else "MERGED_LOCAL_REMOTE"
    return merged, source, used


# ============================================================
# MULTI BD12 + ED12 + O2F12 + PRIME A + A2 + D + X ULTRA SHADOW + TRIANGLE
# ============================================================
class MultiPrimeV1:
    def __init__(self):
        self.start_from_key = None
        self.started_at = None
        self.history = []
        self.history_keys = set()
        self.pending = []
        self.records = []
        self.draw_seq = 0
        self.last_signal_seq = {}
        self.last_armed_key = None
        self.scans = 0
        self.signals = 0
        self.no_signal = 0
        self.cooldown_skips = 0
        self.last_signal = None
        self.last_result = None

        self.ambo_started_from_key = None
        self.ambo_started_at = None
        self.ambo_pending = []
        self.ambo_records = []
        self.ambo_origins = 0
        self.ambo_super_signals = 0
        self.last_ambo_signal = None
        self.last_ambo_result = None

        # PRIME A migra dalla v20.4; B e TRIANGLE partono dalla v20.5 senza backfill.
        self.prime_version = PRIME_VERSION
        self.prime_a_started_from_key = None
        self.prime_a_started_at = None
        self.prime_a_signals = 0
        # A2 e C nascono in v20.6 senza backfill.
        self.prime_a2_started_from_key = None
        self.prime_a2_started_at = None
        self.prime_a2_signals = 0
        # D/X nascono in v20.7 senza backfill.
        self.prime_d_elite_started_from_key = None
        self.prime_d_elite_started_at = None
        self.prime_d_elite_signals = 0
        self.prime_d_wide_started_from_key = None
        self.prime_d_wide_started_at = None
        self.prime_d_wide_signals = 0
        self.prime_x_started_from_key = None
        self.prime_x_started_at = None
        self.prime_x_signals = 0
        # B resta solo legacy: storico/pending preservati, nessun nuovo segnale.
        self.prime_b_started_from_key = None
        self.prime_b_started_at = None
        self.prime_b_signals = 0
        self.prime_c_started_from_key = None
        self.prime_c_started_at = None
        self.prime_c_signals = 0
        self.triangle_started_from_key = None
        self.triangle_started_at = None

        # v20.7.1: base forward reale della FIX. Viene fissata UNA SOLA VOLTA
        # dopo il catch-up alle estrazioni piu recenti, mai durante il load di uno state vecchio.
        self.v2071_started_from_key = None
        self.v2071_started_at = None
        self.v2071_scans_base = 0
        self.v2071_signals_base = 0
        self.v2071_draw_seq_base = 0

        # v20.8: QUATERNA PLUS/ELITE, forward puro senza backfill.
        self.quad_started_from_key = None
        self.quad_started_at = None
        self.quad_pending = []
        self.quad_records = []
        self.quad_signals = 0
        self.quad_elite_signals = 0
        self.last_quad_signal = None
        self.last_quad_result = None

        # v20.9: SISTEMI 7/9 LIVE, forward puro senza backfill.
        self.big_started_from_key = None
        self.big_started_at = None
        self.big_pending = []
        self.big_records = []
        self.big7_signals = 0  # totale/legacy SETTINA conservato
        self.big9_signals = 0
        self.big7_fast_started_from_key = None
        self.big7_fast_started_at = None
        self.big7_fast_signals = 0
        self.last_big_signal = None
        self.last_big_result = None

    @staticmethod
    def _sanitize_row(row):
        if not isinstance(row, dict):
            return None
        try:
            key = str(row.get("key") or draw_key(row.get("day"), row.get("draw_id")))
            day, sid = key.rsplit("#", 1)
            draw_id = int(sid)
            nums = [int(x) for x in row.get("nums", [])]
            extra = [int(x) for x in row.get("extra", [])]
            oro = int(row.get("oro"))
            doppio = int(row.get("doppio_oro"))
        except Exception:
            return None
        if len(nums) != 20 or len(set(nums)) != 20 or any(n < 1 or n > 90 for n in nums):
            return None
        if len(extra) != 15 or len(set(extra)) != 15 or any(n < 1 or n > 90 for n in extra):
            return None
        if oro not in nums or doppio not in nums:
            return None
        time_txt = str(row.get("time") or "").strip()
        return {
            "key": key, "day": day, "draw_id": draw_id, "nums": nums,
            "oro": oro, "doppio_oro": doppio, "extra": extra, "time": time_txt,
        }

    @staticmethod
    def _tier_from_obj(row):
        if not isinstance(row, dict):
            return "STD"
        tier = str(row.get("tier") or "").upper()
        if tier in {"A", "A2", "DE", "DW", "B", "C", "STD"}:
            return tier
        # Migrazione v20.4: prime=True significava l'attuale PRIME A.
        if bool(row.get("prime", False)):
            return "A"
        return "STD"

    @classmethod
    def _sanitize_ambo_row(cls, row):
        if not isinstance(row, dict) or not row.get("origin_key"):
            return None
        try:
            pair = sorted({int(x) for x in (row.get("pair") or [])})
            main = int(row.get("main"))
            age = max(0, int(row.get("age", 0) or 0))
        except Exception:
            return None
        if len(pair) != 2 or any(n < 1 or n > 90 for n in pair) or not 1 <= main <= 90:
            return None
        q = dict(row)
        q["pair"] = pair
        q["main"] = main
        q["age"] = age
        q["slot"] = str(q.get("slot") or "BASE")
        q["origin_id"] = str(q.get("origin_id") or f"{q['origin_key']}|M{main:02d}")
        q["tier"] = cls._tier_from_obj(q)
        q["prime"] = q["tier"] == "A"  # alias legacy: solo A originale
        return q

    @classmethod
    def _sanitize_signal_row(cls, row):
        if not isinstance(row, dict) or not row.get("origin_key"):
            return None
        q = dict(row)
        q["tier"] = cls._tier_from_obj(q)
        q["prime"] = q["tier"] == "A"
        return q

    @classmethod
    def _sanitize_quad_row(cls, row):
        if not isinstance(row, dict) or not row.get("origin_key"):
            return None
        try:
            quartet = sorted({int(x) for x in (row.get("quartet") or [])})
            main = int(row.get("main"))
            age = max(0, int(row.get("age", 0) or 0))
        except Exception:
            return None
        if len(quartet) != 4 or any(n < 1 or n > 90 for n in quartet) or main not in quartet:
            return None
        q = dict(row)
        q["quartet"] = quartet
        q["main"] = main
        q["age"] = age
        q["tier"] = cls._tier_from_obj(q)
        q["quad_level"] = "ELITE" if str(q.get("quad_level") or "").upper() == "ELITE" or int(q.get("consensus",0) or 0) >= 3 else "PLUS"
        q["consensus"] = max(2, min(3, int(q.get("consensus", 2) or 2)))
        q["cost"] = float(q.get("cost", 0.0) or 0.0)
        q["payout"] = float(q.get("payout", 0.0) or 0.0)
        return q

    @classmethod
    def _sanitize_big_row(cls, row):
        if not isinstance(row, dict) or not row.get("origin_key"):
            return None
        try:
            nums = sorted({int(x) for x in (row.get("numbers") or [])})
            size = int(row.get("system_size") or len(nums))
            main = int(row.get("main"))
            age = max(0, int(row.get("age", 0) or 0))
        except Exception:
            return None
        if size not in (7, 9) or len(nums) != size or any(n < 1 or n > 90 for n in nums) or main not in nums:
            return None
        q = dict(row)
        q["numbers"] = nums
        q["system_size"] = size
        q["main"] = main
        q["age"] = age
        q["tier"] = cls._tier_from_obj(q)
        q["cost"] = float(q.get("cost", 0.0) or 0.0)
        q["payout"] = float(q.get("payout", 0.0) or 0.0)
        q["max_shadow_payout"] = float(q.get("max_shadow_payout", 0.0) or 0.0)
        q["max_shadow_match"] = int(q.get("max_shadow_match", 0) or 0)
        q["strategy"] = str(q.get("strategy") or ("LEGACY_7" if size == 7 else "NOVINA_LIVE")).upper()
        q["operational_horizon"] = max(1, min(MULTI_HORIZON, int(q.get("operational_horizon", MULTI_HORIZON) or MULTI_HORIZON)))
        q["support_sum"] = int(q.get("support_sum", 0) or 0)
        return q

    def _refresh_keys(self):
        self.history_keys = {str(r.get("key")) for r in self.history if isinstance(r, dict)}

    def seen(self, key):
        return str(key) in self.history_keys

    def bootstrap(self, rows):
        clean = [r for row in (rows or []) if (r := self._sanitize_row(row))]
        ded = {r["key"]: r for r in clean}
        clean = sorted(ded.values(), key=lambda r: order_key(r["key"]) or (-1, -1))
        if clean:
            self.history = clean[-MULTI_HISTORY_MAX:]
            self.draw_seq = max(self.draw_seq, len(self.history))
            self._refresh_keys()
        return len(self.history)

    def ensure_start(self):
        """Inizializza soltanto i marker storici/legacy sicuri.
        A2/D/X vengono gestiti da ensure_v2071_forward_base DOPO il catch-up.
        """
        if not self.history:
            return False
        current = str(self.history[-1]["key"])
        now_iso = now_dt().isoformat(timespec="seconds")
        changed = False
        if not self.start_from_key:
            self.start_from_key = current
            self.started_at = now_iso
            changed = True
        if not self.ambo_started_from_key:
            self.ambo_started_from_key = current
            self.ambo_started_at = now_iso
            changed = True
        if not self.prime_a_started_from_key:
            self.prime_a_started_from_key = current
            self.prime_a_started_at = now_iso
            changed = True
        if not self.prime_b_started_from_key:
            self.prime_b_started_from_key = current
            self.prime_b_started_at = now_iso
            changed = True
        if not self.prime_c_started_from_key:
            self.prime_c_started_from_key = current
            self.prime_c_started_at = now_iso
            changed = True
        if not self.triangle_started_from_key:
            self.triangle_started_from_key = current
            self.triangle_started_at = now_iso
            changed = True
        return changed

    def _tier_has_evidence(self, tiers=None, x_ultra=False):
        tiers = set(tiers or [])
        for r in list(self.records) + list(self.pending):
            if not isinstance(r, dict):
                continue
            if x_ultra and bool(r.get("x_ultra")):
                return True
            if tiers and self._tier_from_obj(r) in tiers:
                return True
        for r in list(self.ambo_records) + list(self.ambo_pending):
            if not isinstance(r, dict):
                continue
            if x_ultra and bool(r.get("x_ultra")):
                return True
            if tiers and self._tier_from_obj(r) in tiers:
                return True
        return False

    def ensure_v2071_forward_base(self):
        """
        Congela la base forward della v20.7.1 SOLO dopo che il feed e' stato
        portato all'ultima estrazione disponibile. Se A2/D/X non hanno alcuna
        evidenza salvata, corregge i vecchi marker ereditati (es. #127) e li
        riallinea a questa base reale. Se esistono record/pending, li preserva.
        """
        if not self.history:
            return False
        if self.v2071_started_from_key:
            return False
        current = str(self.history[-1]["key"])
        now_iso = now_dt().isoformat(timespec="seconds")
        self.v2071_started_from_key = current
        self.v2071_started_at = now_iso
        self.v2071_scans_base = int(self.scans)
        self.v2071_signals_base = int(self.signals)
        self.v2071_draw_seq_base = int(self.draw_seq)

        # A resta storico e non viene toccato.
        if self.prime_a2_signals <= 0 and not self._tier_has_evidence({"A2"}):
            self.prime_a2_started_from_key = current
            self.prime_a2_started_at = now_iso
        if self.prime_d_elite_signals <= 0 and not self._tier_has_evidence({"DE"}):
            self.prime_d_elite_started_from_key = current
            self.prime_d_elite_started_at = now_iso
        if self.prime_d_wide_signals <= 0 and not self._tier_has_evidence({"DW"}):
            self.prime_d_wide_started_from_key = current
            self.prime_d_wide_started_at = now_iso
        if self.prime_x_signals <= 0 and not self._tier_has_evidence(x_ultra=True):
            self.prime_x_started_from_key = current
            self.prime_x_started_at = now_iso
        return True

    def ensure_quad_forward_base(self):
        """v20.8: congela il punto zero QUATERNA dopo il catch-up, senza backfill."""
        if not self.history or self.quad_started_from_key:
            return False
        current = str(self.history[-1]["key"])
        self.quad_started_from_key = current
        self.quad_started_at = now_dt().isoformat(timespec="seconds")
        return True

    def ensure_big_forward_base(self):
        """v20.9: congela il punto zero dei sistemi 7/9 LIVE dopo il catch-up, senza backfill."""
        if not self.history or self.big_started_from_key:
            return False
        current = str(self.history[-1]["key"])
        self.big_started_from_key = current
        self.big_started_at = now_dt().isoformat(timespec="seconds")
        return True

    def ensure_big7_fast_forward_base(self):
        """v20.9.2: punto zero separato della SETTINA PROFIT FAST, dopo il catch-up."""
        if not self.history or self.big7_fast_started_from_key:
            return False
        current = str(self.history[-1]["key"])
        self.big7_fast_started_from_key = current
        self.big7_fast_started_at = now_dt().isoformat(timespec="seconds")
        return True

    def load(self, obj):
        if not isinstance(obj, dict) or int(obj.get("version", 0) or 0) != MULTI_VERSION:
            return False

        hist = [r for row in obj.get("history", []) if (r := self._sanitize_row(row))]
        ded = {r["key"]: r for r in hist}
        self.history = sorted(ded.values(), key=lambda r: order_key(r["key"]) or (-1, -1))[-MULTI_HISTORY_MAX:]
        self._refresh_keys()

        sfk = obj.get("start_from_key")
        self.start_from_key = str(sfk) if order_key(sfk) is not None else None
        self.started_at = obj.get("started_at") if isinstance(obj.get("started_at"), str) else None
        self.pending = [q for x in obj.get("pending", []) if (q := self._sanitize_signal_row(x))][-200:]
        self.records = [q for x in obj.get("records", []) if (q := self._sanitize_signal_row(x))][-MULTI_RECORD_MAX:]
        self.draw_seq = max(int(obj.get("draw_seq", 0) or 0), len(self.history))

        raw = obj.get("last_signal_seq", {})
        self.last_signal_seq = {
            int(k): int(v) for k, v in raw.items()
            if str(k).isdigit() and 1 <= int(k) <= 90
        } if isinstance(raw, dict) else {}
        self.last_armed_key = obj.get("last_armed_key") if isinstance(obj.get("last_armed_key"), str) else None
        for a in ("scans", "signals", "no_signal", "cooldown_skips"):
            setattr(self, a, max(0, int(obj.get(a, 0) or 0)))
        self.last_signal = obj.get("last_signal") if isinstance(obj.get("last_signal"), dict) else None
        self.last_result = obj.get("last_result") if isinstance(obj.get("last_result"), dict) else None

        ask = obj.get("ambo_started_from_key")
        self.ambo_started_from_key = str(ask) if order_key(ask) is not None else None
        self.ambo_started_at = obj.get("ambo_started_at") if isinstance(obj.get("ambo_started_at"), str) else None
        self.ambo_pending = [q for x in obj.get("ambo_pending", []) if (q := self._sanitize_ambo_row(x))][-900:]
        self.ambo_records = [q for x in obj.get("ambo_records", []) if (q := self._sanitize_ambo_row(x))][-MULTI_AMBO_RECORD_MAX:]
        self.ambo_origins = max(0, int(obj.get("ambo_origins", 0) or 0))
        self.ambo_super_signals = max(0, int(obj.get("ambo_super_signals", 0) or 0))
        self.last_ambo_signal = obj.get("last_ambo_signal") if isinstance(obj.get("last_ambo_signal"), dict) else None
        self.last_ambo_result = obj.get("last_ambo_result") if isinstance(obj.get("last_ambo_result"), dict) else None

        # Migrazione v20.4 -> v20.5: PRIME vecchio = PRIME A.
        ask = obj.get("prime_a_started_from_key", obj.get("prime_started_from_key"))
        self.prime_a_started_from_key = str(ask) if order_key(ask) is not None else None
        self.prime_a_started_at = (
            obj.get("prime_a_started_at") if isinstance(obj.get("prime_a_started_at"), str)
            else (obj.get("prime_started_at") if isinstance(obj.get("prime_started_at"), str) else None)
        )
        self.prime_a_signals = max(0, int(obj.get("prime_a_signals", obj.get("prime_signals", 0)) or 0))

        a2sk = obj.get("prime_a2_started_from_key")
        self.prime_a2_started_from_key = str(a2sk) if order_key(a2sk) is not None else None
        self.prime_a2_started_at = obj.get("prime_a2_started_at") if isinstance(obj.get("prime_a2_started_at"), str) else None
        self.prime_a2_signals = max(0, int(obj.get("prime_a2_signals", 0) or 0))

        desk = obj.get("prime_d_elite_started_from_key")
        self.prime_d_elite_started_from_key = str(desk) if order_key(desk) is not None else None
        self.prime_d_elite_started_at = obj.get("prime_d_elite_started_at") if isinstance(obj.get("prime_d_elite_started_at"), str) else None
        self.prime_d_elite_signals = max(0, int(obj.get("prime_d_elite_signals", 0) or 0))

        dwsk = obj.get("prime_d_wide_started_from_key")
        self.prime_d_wide_started_from_key = str(dwsk) if order_key(dwsk) is not None else None
        self.prime_d_wide_started_at = obj.get("prime_d_wide_started_at") if isinstance(obj.get("prime_d_wide_started_at"), str) else None
        self.prime_d_wide_signals = max(0, int(obj.get("prime_d_wide_signals", 0) or 0))

        xsk = obj.get("prime_x_started_from_key")
        self.prime_x_started_from_key = str(xsk) if order_key(xsk) is not None else None
        self.prime_x_started_at = obj.get("prime_x_started_at") if isinstance(obj.get("prime_x_started_at"), str) else None
        self.prime_x_signals = max(0, int(obj.get("prime_x_signals", 0) or 0))

        bsk = obj.get("prime_b_started_from_key")
        self.prime_b_started_from_key = str(bsk) if order_key(bsk) is not None else None
        self.prime_b_started_at = obj.get("prime_b_started_at") if isinstance(obj.get("prime_b_started_at"), str) else None
        self.prime_b_signals = max(0, int(obj.get("prime_b_signals", 0) or 0))

        csk = obj.get("prime_c_started_from_key")
        self.prime_c_started_from_key = str(csk) if order_key(csk) is not None else None
        self.prime_c_started_at = obj.get("prime_c_started_at") if isinstance(obj.get("prime_c_started_at"), str) else None
        self.prime_c_signals = max(0, int(obj.get("prime_c_signals", 0) or 0))

        tsk = obj.get("triangle_started_from_key")
        self.triangle_started_from_key = str(tsk) if order_key(tsk) is not None else None
        self.triangle_started_at = obj.get("triangle_started_at") if isinstance(obj.get("triangle_started_at"), str) else None

        fsk = obj.get("v2071_started_from_key")
        self.v2071_started_from_key = str(fsk) if order_key(fsk) is not None else None
        self.v2071_started_at = obj.get("v2071_started_at") if isinstance(obj.get("v2071_started_at"), str) else None
        self.v2071_scans_base = max(0, int(obj.get("v2071_scans_base", 0) or 0))
        self.v2071_signals_base = max(0, int(obj.get("v2071_signals_base", 0) or 0))
        self.v2071_draw_seq_base = max(0, int(obj.get("v2071_draw_seq_base", 0) or 0))

        qsk = obj.get("quad_started_from_key")
        self.quad_started_from_key = str(qsk) if order_key(qsk) is not None else None
        self.quad_started_at = obj.get("quad_started_at") if isinstance(obj.get("quad_started_at"), str) else None
        self.quad_pending = [q for x in obj.get("quad_pending", []) if (q := self._sanitize_quad_row(x))][-MULTI_QUAD_PENDING_MAX:]
        self.quad_records = [q for x in obj.get("quad_records", []) if (q := self._sanitize_quad_row(x))][-MULTI_QUAD_RECORD_MAX:]
        self.quad_signals = max(0, int(obj.get("quad_signals", 0) or 0), len(self.quad_pending)+len(self.quad_records))
        self.quad_elite_signals = max(0, int(obj.get("quad_elite_signals", 0) or 0), sum(1 for q in self.quad_pending+self.quad_records if q.get("quad_level")=="ELITE"))
        self.last_quad_signal = obj.get("last_quad_signal") if isinstance(obj.get("last_quad_signal"), dict) else None
        self.last_quad_result = obj.get("last_quad_result") if isinstance(obj.get("last_quad_result"), dict) else None

        bgsk = obj.get("big_started_from_key")
        self.big_started_from_key = str(bgsk) if order_key(bgsk) is not None else None
        self.big_started_at = obj.get("big_started_at") if isinstance(obj.get("big_started_at"), str) else None
        self.big_pending = [q for x in obj.get("big_pending", []) if (q := self._sanitize_big_row(x))][-MULTI_BIG_PENDING_MAX:]
        self.big_records = [q for x in obj.get("big_records", []) if (q := self._sanitize_big_row(x))][-MULTI_BIG_RECORD_MAX:]
        self.big7_signals = max(0, int(obj.get("big7_signals", 0) or 0), sum(1 for q in self.big_pending+self.big_records if int(q.get("system_size",0) or 0)==7))
        self.big9_signals = max(0, int(obj.get("big9_signals", 0) or 0), sum(1 for q in self.big_pending+self.big_records if int(q.get("system_size",0) or 0)==9))
        b7fsk = obj.get("big7_fast_started_from_key")
        self.big7_fast_started_from_key = str(b7fsk) if order_key(b7fsk) is not None else None
        self.big7_fast_started_at = obj.get("big7_fast_started_at") if isinstance(obj.get("big7_fast_started_at"), str) else None
        self.big7_fast_signals = max(0, int(obj.get("big7_fast_signals", 0) or 0), sum(1 for q in self.big_pending+self.big_records if int(q.get("system_size",0) or 0)==7 and str(q.get("strategy") or "").upper()==SETTINA_FAST_STRATEGY))
        self.last_big_signal = obj.get("last_big_signal") if isinstance(obj.get("last_big_signal"), dict) else None
        self.last_big_result = obj.get("last_big_result") if isinstance(obj.get("last_big_result"), dict) else None

        self.ensure_start()
        return True

    def dump(self):
        return {
            "version": MULTI_VERSION,
            "start_from_key": self.start_from_key,
            "started_at": self.started_at,
            "history": self.history[-MULTI_HISTORY_MAX:],
            "pending": self.pending[-200:],
            "records": self.records[-MULTI_RECORD_MAX:],
            "draw_seq": self.draw_seq,
            "last_signal_seq": {str(k): int(v) for k, v in self.last_signal_seq.items()},
            "last_armed_key": self.last_armed_key,
            "scans": self.scans,
            "signals": self.signals,
            "no_signal": self.no_signal,
            "cooldown_skips": self.cooldown_skips,
            "last_signal": self.last_signal,
            "last_result": self.last_result,
            "ambo_version": 2,
            "ambo_started_from_key": self.ambo_started_from_key,
            "ambo_started_at": self.ambo_started_at,
            "ambo_pending": self.ambo_pending[-900:],
            "ambo_records": self.ambo_records[-MULTI_AMBO_RECORD_MAX:],
            "ambo_origins": self.ambo_origins,
            "ambo_super_signals": self.ambo_super_signals,
            "last_ambo_signal": self.last_ambo_signal,
            "last_ambo_result": self.last_ambo_result,
            "prime_version": PRIME_VERSION,
            # Alias vecchi mantenuti per compatibilità.
            "prime_started_from_key": self.prime_a_started_from_key,
            "prime_started_at": self.prime_a_started_at,
            "prime_signals": self.prime_a_signals,
            # Campi v20.5.
            "prime_a_started_from_key": self.prime_a_started_from_key,
            "prime_a_started_at": self.prime_a_started_at,
            "prime_a_signals": self.prime_a_signals,
            "prime_a2_started_from_key": self.prime_a2_started_from_key,
            "prime_a2_started_at": self.prime_a2_started_at,
            "prime_a2_signals": self.prime_a2_signals,
            # Campi v20.7 D/X.
            "prime_d_elite_started_from_key": self.prime_d_elite_started_from_key,
            "prime_d_elite_started_at": self.prime_d_elite_started_at,
            "prime_d_elite_signals": self.prime_d_elite_signals,
            "prime_d_wide_started_from_key": self.prime_d_wide_started_from_key,
            "prime_d_wide_started_at": self.prime_d_wide_started_at,
            "prime_d_wide_signals": self.prime_d_wide_signals,
            "prime_x_started_from_key": self.prime_x_started_from_key,
            "prime_x_started_at": self.prime_x_started_at,
            "prime_x_signals": self.prime_x_signals,
            "prime_b_started_from_key": self.prime_b_started_from_key,
            "prime_b_started_at": self.prime_b_started_at,
            "prime_b_signals": self.prime_b_signals,
            "prime_c_started_from_key": self.prime_c_started_from_key,
            "prime_c_started_at": self.prime_c_started_at,
            "prime_c_signals": self.prime_c_signals,
            "triangle_started_from_key": self.triangle_started_from_key,
            "triangle_started_at": self.triangle_started_at,
            "v2071_started_from_key": self.v2071_started_from_key,
            "v2071_started_at": self.v2071_started_at,
            "v2071_scans_base": int(self.v2071_scans_base),
            "v2071_signals_base": int(self.v2071_signals_base),
            "v2071_draw_seq_base": int(self.v2071_draw_seq_base),
            "quad_started_from_key": self.quad_started_from_key,
            "quad_started_at": self.quad_started_at,
            "quad_pending": self.quad_pending[-MULTI_QUAD_PENDING_MAX:],
            "quad_records": self.quad_records[-MULTI_QUAD_RECORD_MAX:],
            "quad_signals": int(self.quad_signals),
            "quad_elite_signals": int(self.quad_elite_signals),
            "last_quad_signal": self.last_quad_signal,
            "last_quad_result": self.last_quad_result,
            "big_started_from_key": self.big_started_from_key,
            "big_started_at": self.big_started_at,
            "big_pending": self.big_pending[-MULTI_BIG_PENDING_MAX:],
            "big_records": self.big_records[-MULTI_BIG_RECORD_MAX:],
            "big7_signals": int(self.big7_signals),
            "big9_signals": int(self.big9_signals),
            "big7_fast_started_from_key": self.big7_fast_started_from_key,
            "big7_fast_started_at": self.big7_fast_started_at,
            "big7_fast_signals": int(self.big7_fast_signals),
            "last_big_signal": self.last_big_signal,
            "last_big_result": self.last_big_result,
        }

    @staticmethod
    def _gap(history, n, field):
        gap = 0
        for r in reversed(history):
            vals = r[field] if isinstance(r.get(field), list) else [r.get(field)]
            if n in vals:
                return gap
            gap += 1
        return len(history) + 1

    def _rankings(self):
        if len(self.history) < MULTI_WINDOW:
            return None
        w = self.history[-MULTI_WINDOW:]
        base_gap = {n: self._gap(self.history, n, "nums") for n in range(1, 91)}
        extra_gap = {n: self._gap(self.history, n, "extra") for n in range(1, 91)}
        o2_freq = {n: 0 for n in range(1, 91)}
        for r in w:
            o2_freq[int(r["doppio_oro"])] += 1
        ranked_base_delay = sorted(range(1, 91), key=lambda n: (-base_gap[n], n))
        ranked_extra_delay = sorted(range(1, 91), key=lambda n: (-extra_gap[n], n))
        top_base_delay = ranked_base_delay[:MULTI_TOP_N]
        top_extra_delay = ranked_extra_delay[:MULTI_TOP_N]
        top_o2 = sorted(range(1, 91), key=lambda n: (-o2_freq[n], n))[:MULTI_TOP_N]
        extra_rank13_gap = int(extra_gap[ranked_extra_delay[MULTI_TOP_N]]) if len(ranked_extra_delay) > MULTI_TOP_N else 0
        return {
            "base_gap": base_gap, "extra_gap": extra_gap, "o2_freq": o2_freq,
            "top_base_delay": top_base_delay,
            "top_extra_delay": top_extra_delay,
            "top_o2": top_o2,
            "extra_rank13_gap": extra_rank13_gap,
        }

    @staticmethod
    def _rank_of(n, ordered):
        try:
            return int(ordered.index(int(n)) + 1)
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _clock_minutes(row):
        if not isinstance(row, dict):
            return None
        txt = str(row.get("time") or "").strip()
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", txt)
        if not m:
            return None
        hh, mm = int(m.group(1)), int(m.group(2))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        return hh * 60 + mm

    @classmethod
    def _tier(cls, bd_rank, o2_rank, origin_row=None, inter_size=None):
        if bd_rank is None or o2_rank is None:
            return "STD"
        bd_rank, o2_rank = int(bd_rank), int(o2_rank)
        # PRIME A originale: NON cambia.
        if (PRIME_A_BD_RANK_MIN <= bd_rank <= PRIME_A_BD_RANK_MAX
                and PRIME_A_O2_RANK_MIN <= o2_rank <= PRIME_A_O2_RANK_MAX):
            return "A"

        mins = cls._clock_minutes(origin_row)
        elite_time = mins is not None and (mins <= PRIME_A2_MORNING_MAX_MIN or mins > PRIME_A2_EVENING_AFTER_MIN)
        if (elite_time
                and PRIME_A2_BD_RANK_MIN <= bd_rank <= PRIME_A2_BD_RANK_MAX
                and PRIME_A2_O2_RANK_MIN <= o2_rank <= PRIME_A2_O2_RANK_MAX):
            return "A2"

        # PRIME D: famiglia nuova, disgiunta da A/A2 per BD rank.
        d_time = mins is not None and mins > PRIME_D_AFTER_MIN
        unique_inter = int(inter_size or 0) == PRIME_D_INTERSECTION_SIZE
        if d_time and unique_inter:
            if PRIME_D_ELITE_BD_RANK_MIN <= bd_rank <= PRIME_D_ELITE_BD_RANK_MAX:
                return "DE"
            if PRIME_D_WIDE_BD_RANK_MIN <= bd_rank <= PRIME_D_WIDE_BD_RANK_MAX:
                return "DW"

        # C legacy shadow continua solo nei casi non assorbiti da D.
        c_time = mins is not None and mins > PRIME_C_AFTER_MIN
        if (c_time
                and PRIME_C_BD_RANK_MIN <= bd_rank <= PRIME_C_BD_RANK_MAX
                and PRIME_C_O2_RANK_MIN <= o2_rank <= PRIME_C_O2_RANK_MAX):
            return "C"
        # PRIME B v20.5 NON viene più creato.
        return "STD"

    @classmethod
    def _is_x_ultra(cls, bd_rank, ed_rank, origin_row, inter_size, extra_gap, extra_rank13_gap):
        if bd_rank is None or ed_rank is None:
            return False
        mins = cls._clock_minutes(origin_row)
        if mins is None or mins <= PRIME_X_AFTER_MIN:
            return False
        margin13 = int(extra_gap or 0) - int(extra_rank13_gap or 0)
        return bool(
            int(inter_size or 0) == PRIME_D_INTERSECTION_SIZE
            and PRIME_X_BD_RANK_MIN <= int(bd_rank) <= PRIME_X_BD_RANK_MAX
            and PRIME_X_ED_RANK_MIN <= int(ed_rank) <= PRIME_X_ED_RANK_MAX
            and margin13 >= PRIME_X_EXTRA_MARGIN13_MIN
        )

    def _partner_plan(self, main, ranks):
        candidates = [int(n) for n in ranks["top_o2"] if int(n) != int(main)]
        if len(candidates) < 2:
            return None
        hw = self.history[-MULTI_COOC_WINDOW:]
        bset = set(ranks["top_base_delay"])
        eset = set(ranks["top_extra_delay"])
        scored = []
        for p in candidates:
            cooc = sum(
                1 for r in hw
                if int(main) in set(r["nums"]) and int(p) in set(r["nums"])
            )
            support = 1 + int(p in bset) + int(p in eset)
            scored.append({
                "num": p, "cooc": int(cooc), "support": int(support),
                "in_bd12": bool(p in bset), "in_ed12": bool(p in eset),
                "o2_freq80": int(ranks["o2_freq"].get(p, 0)),
            })
        scored.sort(key=lambda x: (-x["cooc"], x["num"]))
        p1, p2 = scored[0], scored[1]
        support_sum = int(p1["support"] + p2["support"])
        return {
            "main": int(main), "p1": p1, "p2": p2,
            "support_sum": support_sum,
            "super_enabled": bool(support_sum >= MULTI_SUPER_GATE),
            "cooc_window": min(len(hw), MULTI_COOC_WINDOW),
        }

    def _quad_jaccard_pick(self, main, ranks, pool_n):
        """MAX-MIN Jaccard Base su history lunga; tie-break congelato e deterministico."""
        main = int(main)
        candidates = [int(n) for n in ranks["top_o2"][:int(pool_n)] if int(n) != main]
        if len(candidates) < 3:
            return None
        hw = self.history[-min(len(self.history), QUAD_JACCARD_WINDOW):]
        nums = [main] + candidates
        freq = {n: 0 for n in nums}
        cooc = {}
        for r in hw:
            b = set(int(x) for x in r.get("nums", []))
            present = [n for n in nums if n in b]
            for n in present:
                freq[n] += 1
            for a, bnum in combinations(present, 2):
                k = (min(a,bnum), max(a,bnum))
                cooc[k] = cooc.get(k, 0) + 1

        def edge(a,b):
            k=(min(a,b),max(a,b))
            c=int(cooc.get(k,0))
            den=int(freq.get(a,0))+int(freq.get(b,0))-c
            j=(c/den) if den>0 else 0.0
            return j,c

        best_score = None
        best = None
        for partners in combinations(candidates, 3):
            quartet = tuple(sorted((main,) + tuple(int(x) for x in partners)))
            js=[]; cs=[]
            for a,b in combinations(quartet,2):
                j,c=edge(a,b); js.append(float(j)); cs.append(int(c))
            # Prima massimizziamo la coppia più debole; poi la coesione totale.
            # In ultimo preferiamo la quaterna numericamente più piccola per tie-break stabile.
            score=(min(js), sum(js), min(cs), sum(cs), tuple(-x for x in quartet))
            if best_score is None or score > best_score:
                best_score=score
                best={
                    "pool": int(pool_n), "quartet": list(quartet),
                    "min_jaccard": float(min(js)), "sum_jaccard": float(sum(js)),
                    "mean_jaccard": float(sum(js)/len(js)),
                    "min_cooc": int(min(cs)), "sum_cooc": int(sum(cs)),
                    "window": int(len(hw)),
                }
        return best

    def _quad_consensus_plan(self, main, ranks, tier):
        tier=str(tier or "").upper()
        if tier not in {"A2","DE"}:
            return None
        picks=[self._quad_jaccard_pick(main,ranks,p) for p in QUAD_POOLS]
        picks=[p for p in picks if p]
        if len(picks) != len(QUAD_POOLS):
            return None
        cnt=Counter(tuple(p["quartet"]) for p in picks)
        quartet, consensus=max(cnt.items(), key=lambda kv:(kv[1], tuple(-x for x in kv[0])))
        if int(consensus) < 2:
            return None
        agreeing=[p for p in picks if tuple(p["quartet"])==tuple(quartet)]
        level="ELITE" if int(consensus)>=3 else "PLUS"
        return {
            "main":int(main), "tier":tier, "quartet":list(quartet),
            "quad_level":level, "consensus":int(consensus),
            "picks":picks,
            "min_jaccard":min(float(p["min_jaccard"]) for p in agreeing),
            "mean_jaccard":sum(float(p["mean_jaccard"]) for p in agreeing)/len(agreeing),
            "min_cooc":min(int(p["min_cooc"]) for p in agreeing),
            "window":min(int(p["window"]) for p in agreeing),
        }

    def _arm_quad(self, origin_key, main, plan, tier, bd_rank=None, o2_rank=None):
        if not plan:
            return None
        quartet=sorted(int(x) for x in plan.get("quartet",[]))
        if len(quartet)!=4:
            return None
        q={
            "origin_key":str(origin_key), "origin_id":f"{origin_key}|M{int(main):02d}|Q",
            "main":int(main), "quartet":quartet, "tier":str(tier).upper(),
            "quad_level":str(plan.get("quad_level") or "PLUS").upper(),
            "consensus":int(plan.get("consensus",2) or 2),
            "age":0, "closed":False,
            "operational_stopped":False, "stop_age":None, "stop_match":None,
            "cost":0.0, "payout":0.0,
            "max_shadow_match":0, "first2_colpo":None, "first3_colpo":None, "first4_colpo":None,
            "bd_rank":bd_rank, "o2_rank":o2_rank,
            "min_jaccard":float(plan.get("min_jaccard",0.0) or 0.0),
            "mean_jaccard":float(plan.get("mean_jaccard",0.0) or 0.0),
            "min_cooc":int(plan.get("min_cooc",0) or 0),
            "jaccard_window":int(plan.get("window",0) or 0),
            "picks":plan.get("picks",[]), "created_at":now_txt(),
        }
        self.quad_pending.append(q)
        self.quad_pending=self.quad_pending[-MULTI_QUAD_PENDING_MAX:]
        self.quad_signals += 1
        if q["quad_level"]=="ELITE":
            self.quad_elite_signals += 1
        self.last_quad_signal=dict(q)
        return dict(q)

    def _big7_plan(self, main, ranks, tier):
        """SETTINA PROFIT FAST v20.9.2.

        A2: O2 rank == 3 + support_sum dei 6 partner COOC900 >= 7.
        D-ELITE: BD rank 1-3 + O2 rank 10-12.
        Operativa H1-H2; H3-H5 solo shadow.
        """
        tier=str(tier or "").upper()
        if tier not in {"A2","DE"}:
            return None
        main=int(main)
        bd_rank=self._rank_of(main, ranks["top_base_delay"])
        o2_rank=self._rank_of(main, ranks["top_o2"])
        candidates=[int(n) for n in ranks["top_o2"] if int(n)!=main]
        if len(candidates)<6:
            return None
        hw=self.history[-min(len(self.history),MULTI_COOC_WINDOW):]
        bset=set(int(x) for x in ranks["top_base_delay"])
        eset=set(int(x) for x in ranks["top_extra_delay"])
        scored=[]
        for p in candidates:
            c=sum(1 for r in hw if main in set(r.get("nums",[])) and p in set(r.get("nums",[])))
            support=1 + int(p in bset) + int(p in eset)
            scored.append((int(c),int(p),int(support)))
        scored.sort(key=lambda z:(-z[0],z[1]))
        chosen=scored[:6]
        support_sum=sum(x[2] for x in chosen)
        if tier=="A2":
            if int(o2_rank or 0) != SETTINA_FAST_A2_O2_RANK or int(support_sum) < SETTINA_FAST_A2_SUPPORT_SUM_MIN:
                return None
        else:
            if not (SETTINA_FAST_DE_BD_RANK_MIN <= int(bd_rank or 0) <= SETTINA_FAST_DE_BD_RANK_MAX):
                return None
            if not (SETTINA_FAST_DE_O2_RANK_MIN <= int(o2_rank or 0) <= SETTINA_FAST_DE_O2_RANK_MAX):
                return None
        partners=[p for _,p,_ in chosen]
        nums=sorted([main]+partners)
        return {
            "system_size":7,"numbers":nums,"selector":"COOC900_PROFIT_FAST",
            "strategy":SETTINA_FAST_STRATEGY,"operational_horizon":SETTINA_FAST_HORIZON,
            "scores":[{"num":p,"cooc":c,"support":sup} for c,p,sup in chosen],
            "support_sum":int(support_sum),"window":len(hw),
            "bd_rank":bd_rank,"o2_rank":o2_rank,
        }

    def _big9_plan(self, main, ranks, tier):
        """NOVINA LIVE: A2 + D ELITE/WIDE; M + 8 O2F12 con Jaccard900 rispetto a M."""
        tier=str(tier or "").upper()
        if tier not in {"A2","DE","DW"}:
            return None
        main=int(main)
        candidates=[int(n) for n in ranks["top_o2"] if int(n)!=main]
        if len(candidates)<8:
            return None
        hw=self.history[-min(len(self.history),MULTI_COOC_WINDOW):]
        fm=0; fp={p:0 for p in candidates}; co={p:0 for p in candidates}
        for r in hw:
            b=set(int(x) for x in r.get("nums",[]))
            mhere=main in b
            if mhere: fm+=1
            for p in candidates:
                if p in b:
                    fp[p]+=1
                    if mhere: co[p]+=1
        scored=[]
        for p in candidates:
            den=fm+fp[p]-co[p]
            j=(co[p]/den) if den>0 else 0.0
            scored.append((float(j),int(co[p]),int(p)))
        scored.sort(key=lambda z:(-z[0],-z[1],z[2]))
        partners=[p for _,_,p in scored[:8]]
        nums=sorted([main]+partners)
        return {"system_size":9,"numbers":nums,"selector":"JACCARD900_M","scores":[{"num":p,"jaccard":j,"cooc":c} for j,c,p in scored[:8]],"window":len(hw)}

    @staticmethod
    def _big_prize(size, matches):
        table=BIG7_PRIZES if int(size)==7 else BIG9_PRIZES if int(size)==9 else {}
        return float(table.get(int(matches),0.0) or 0.0)

    def _arm_big(self, origin_key, main, plan, tier, bd_rank=None, o2_rank=None):
        if not plan:
            return None
        nums=sorted(int(x) for x in plan.get("numbers",[]))
        size=int(plan.get("system_size") or len(nums))
        if size not in (7,9) or len(nums)!=size:
            return None
        q={
            "origin_key":str(origin_key),"origin_id":f"{origin_key}|M{int(main):02d}|S{size}",
            "main":int(main),"numbers":nums,"system_size":size,"tier":str(tier).upper(),
            "selector":str(plan.get("selector") or ""),"scores":plan.get("scores",[]),"window":int(plan.get("window",0) or 0),
            "strategy":str(plan.get("strategy") or ("LEGACY_7" if size==7 else "NOVINA_LIVE")).upper(),
            "operational_horizon":max(1,min(MULTI_HORIZON,int(plan.get("operational_horizon",MULTI_HORIZON) or MULTI_HORIZON))),
            "support_sum":int(plan.get("support_sum",0) or 0),
            "age":0,"closed":False,"operational_stopped":False,"stop_age":None,"stop_match":None,
            "cost":0.0,"payout":0.0,"max_shadow_payout":0.0,"max_shadow_match":0,
            "bd_rank":bd_rank,"o2_rank":o2_rank,"created_at":now_txt(),
        }
        self.big_pending.append(q); self.big_pending=self.big_pending[-MULTI_BIG_PENDING_MAX:]
        if size==7:
            self.big7_signals+=1
            if str(q.get("strategy") or "").upper()==SETTINA_FAST_STRATEGY:
                self.big7_fast_signals+=1
        else:
            self.big9_signals+=1
        self.last_big_signal=dict(q)
        return dict(q)

    def _arm_ambo(self, origin_key, main, plan, tier="STD", bd_rank=None, o2_rank=None, x_ultra=False, inter_size=None, extra_margin13=None):
        if not plan:
            return []
        tier = str(tier or "STD").upper()
        origin_id = f"{origin_key}|M{int(main):02d}"
        p1 = int(plan["p1"]["num"])
        p2 = int(plan["p2"]["num"])
        specs = [("BASE1", sorted([int(main), p1])), ("BASE2", sorted([int(main), p2]))]
        if plan.get("super_enabled"):
            specs.append(("SUPER", sorted([p1, p2])))
        elif tier in {"A", "A2", "DE", "DW", "C"}:
            # A/A2/D/C seguono SEMPRE il terzo lato;
            # ma se il gate non passa resta TRIANGLE_OFF shadow.
            specs.append(("TRIANGLE_OFF", sorted([p1, p2])))

        created = []
        for slot, pair in specs:
            q = {
                "origin_key": str(origin_key), "origin_id": origin_id,
                "main": int(main), "slot": slot, "pair": pair,
                "age": 0, "hit": False, "hit_colpo": None, "created_at": now_txt(),
                "p1": p1, "p2": p2,
                "p1_cooc": int(plan["p1"]["cooc"]), "p2_cooc": int(plan["p2"]["cooc"]),
                "p1_support": int(plan["p1"]["support"]), "p2_support": int(plan["p2"]["support"]),
                "support_sum": int(plan["support_sum"]), "cooc_window": int(plan["cooc_window"]),
                "tier": tier, "prime": tier == "A",
                "bd_rank": bd_rank, "o2_rank": o2_rank,
                "x_ultra": bool(x_ultra), "intersection_size": inter_size,
                "extra_margin13": extra_margin13,
            }
            self.ambo_pending.append(q)
            created.append(dict(q))

        self.ambo_pending = self.ambo_pending[-900:]
        self.ambo_origins += 1
        if plan.get("super_enabled"):
            self.ambo_super_signals += 1
        self.last_ambo_signal = {
            "origin_key": str(origin_key), "origin_id": origin_id,
            "main": int(main), "p1": dict(plan["p1"]), "p2": dict(plan["p2"]),
            "support_sum": int(plan["support_sum"]),
            "super_enabled": bool(plan.get("super_enabled")),
            "tier": tier, "bd_rank": bd_rank, "o2_rank": o2_rank,
            "x_ultra": bool(x_ultra), "intersection_size": inter_size, "extra_margin13": extra_margin13,
            "pairs": [{"slot": x["slot"], "pair": list(x["pair"])} for x in created],
        }
        return created

    def advance(self, row):
        r = self._sanitize_row(row)
        if not r:
            return []
        actual = set(r["nums"])
        events = []

        remain = []
        for p in self.pending:
            q = dict(p)
            q["tier"] = self._tier_from_obj(q)
            age = int(q.get("age", 0) or 0) + 1
            q["age"] = age
            q["last_key"] = r["key"]
            hit_now = (not q.get("hit")) and int(q.get("num", 0)) in actual
            if hit_now:
                q["hit"] = True
                q["hit_colpo"] = age
            close = bool(q.get("hit")) or age >= MULTI_HORIZON
            if age == 1 or hit_now or (close and not q.get("hit")):
                events.append({"kind": "ambata", "row": dict(q), "hit_now": hit_now, "closed": close})
            if close:
                q["closed"] = True
                q["closed_key"] = r["key"]
                self.records.append(q)
                self.records = self.records[-MULTI_RECORD_MAX:]
                self.last_result = dict(q)
            else:
                remain.append(q)
        self.pending = remain

        aremain = []
        for p in self.ambo_pending:
            q = dict(p)
            q["tier"] = self._tier_from_obj(q)
            age = int(q.get("age", 0) or 0) + 1
            q["age"] = age
            q["last_key"] = r["key"]
            pair = [int(x) for x in q.get("pair", [])]
            hit_now = (
                (not q.get("hit")) and len(pair) == 2
                and pair[0] in actual and pair[1] in actual
            )
            if hit_now:
                q["hit"] = True
                q["hit_colpo"] = age
            close = bool(q.get("hit")) or age >= MULTI_HORIZON
            if hit_now or (close and not q.get("hit")):
                events.append({"kind": "ambo", "row": dict(q), "hit_now": hit_now, "closed": close})
            if close:
                q["closed"] = True
                q["closed_key"] = r["key"]
                self.ambo_records.append(q)
                self.ambo_records = self.ambo_records[-MULTI_AMBO_RECORD_MAX:]
                self.last_ambo_result = dict(q)
            else:
                aremain.append(q)
        self.ambo_pending = aremain

        qremain=[]
        for p in self.quad_pending:
            q=dict(p)
            age=int(q.get("age",0) or 0)+1
            q["age"]=age
            q["last_key"]=r["key"]
            quartet=[int(x) for x in q.get("quartet",[])]
            matches=sum(1 for x in quartet if x in actual)
            prev_max=int(q.get("max_shadow_match",0) or 0)
            q["max_shadow_match"]=max(prev_max,matches)
            if matches>=2 and q.get("first2_colpo") is None: q["first2_colpo"]=age
            if matches>=3 and q.get("first3_colpo") is None: q["first3_colpo"]=age
            if matches>=4 and q.get("first4_colpo") is None: q["first4_colpo"]=age

            op_stop_now=False
            if not bool(q.get("operational_stopped")):
                q["cost"]=float(q.get("cost",0.0) or 0.0)+QUAD_STAKE_PER_COLPO
                if matches>=2:
                    q["operational_stopped"]=True
                    q["stop_age"]=age
                    q["stop_match"]=matches
                    q["payout"]={2:QUAD_PRIZE_2,3:QUAD_PRIZE_3,4:QUAD_PRIZE_4}.get(matches,0.0)
                    op_stop_now=True
                    events.append({"kind":"quad_stop","row":dict(q),"matches":matches,"closed":age>=MULTI_HORIZON})

            # Shadow: anche dopo STOP continuiamo fino a H5 per sapere se sarebbe migliorata.
            if bool(q.get("operational_stopped")) and matches>=3 and matches>prev_max and not op_stop_now:
                events.append({"kind":"quad_shadow_upgrade","row":dict(q),"matches":matches,"closed":age>=MULTI_HORIZON})

            close=age>=MULTI_HORIZON
            if close:
                q["closed"]=True; q["closed_key"]=r["key"]
                q["shadow_prize_max"]={0:0.0,1:0.0,2:QUAD_PRIZE_2,3:QUAD_PRIZE_3,4:QUAD_PRIZE_4}.get(int(q.get("max_shadow_match",0) or 0),0.0)
                self.quad_records.append(q)
                self.quad_records=self.quad_records[-MULTI_QUAD_RECORD_MAX:]
                self.last_quad_result=dict(q)
                if not bool(q.get("operational_stopped")):
                    events.append({"kind":"quad_stop","row":dict(q),"matches":0,"closed":True,"no_hit":True})
            else:
                qremain.append(q)
        self.quad_pending=qremain

        bremain=[]
        for p in self.big_pending:
            q=dict(p)
            age=int(q.get("age",0) or 0)+1
            q["age"]=age; q["last_key"]=r["key"]
            nums=[int(x) for x in q.get("numbers",[])]
            size=int(q.get("system_size",0) or 0)
            op_horizon=max(1,min(MULTI_HORIZON,int(q.get("operational_horizon",MULTI_HORIZON) or MULTI_HORIZON)))
            matches=sum(1 for x in nums if x in actual)
            prize=self._big_prize(size,matches)
            prev_best=float(q.get("max_shadow_payout",0.0) or 0.0)
            if prize>prev_best:
                q["max_shadow_payout"]=prize; q["max_shadow_match"]=matches; q["max_shadow_age"]=age
            op_stop_now=False
            if not bool(q.get("operational_stopped")):
                if age <= op_horizon:
                    q["cost"]=float(q.get("cost",0.0) or 0.0)+BIG_STAKE_PER_COLPO
                    if prize>0:
                        q["operational_stopped"]=True; q["stop_age"]=age; q["stop_match"]=matches; q["payout"]=prize
                        op_stop_now=True
                        events.append({"kind":"big_stop","row":dict(q),"matches":matches,"prize":prize,"closed":age>=MULTI_HORIZON})
                if (not bool(q.get("operational_stopped"))) and age >= op_horizon:
                    q["operational_stopped"]=True; q["stop_age"]=age; q["stop_match"]=None; q["payout"]=0.0
                    op_stop_now=True
                    events.append({"kind":"big_stop","row":dict(q),"matches":matches,"prize":0.0,"closed":age>=MULTI_HORIZON,"no_hit":True})
            if bool(q.get("operational_stopped")) and prize>float(q.get("payout",0.0) or 0.0) and prize>prev_best and not op_stop_now:
                events.append({"kind":"big_shadow_upgrade","row":dict(q),"matches":matches,"prize":prize,"closed":age>=MULTI_HORIZON})
            close=age>=MULTI_HORIZON
            if close:
                q["closed"]=True; q["closed_key"]=r["key"]
                self.big_records.append(q); self.big_records=self.big_records[-MULTI_BIG_RECORD_MAX:]
                self.last_big_result=dict(q)
                if not bool(q.get("operational_stopped")):
                    q["operational_stopped"]=True; q["stop_age"]=age; q["stop_match"]=None; q["payout"]=0.0
                    events.append({"kind":"big_stop","row":dict(q),"matches":matches,"prize":0.0,"closed":True,"no_hit":True})
            else:
                bremain.append(q)
        self.big_pending=bremain
        return events

    def ingest(self, row):
        r = self._sanitize_row(row)
        if not r or self.seen(r["key"]):
            return []
        events = self.advance(r)
        self.history.append(r)
        self.history = self.history[-MULTI_HISTORY_MAX:]
        self.draw_seq += 1
        self._refresh_keys()
        return events

    def arm(self):
        if not self.history or len(self.history) < MULTI_WINDOW:
            return None
        self.ensure_start()
        # arm() viene chiamato solo sulla piu recente estrazione nota: qui e' sicuro
        # fissare la base forward se startup/sync non l'hanno gia fatto.
        self.ensure_v2071_forward_base()
        self.ensure_quad_forward_base()
        self.ensure_big_forward_base()
        self.ensure_big7_fast_forward_base()
        origin_key = str(self.history[-1]["key"])
        if self.last_armed_key == origin_key:
            return None

        self.last_armed_key = origin_key
        self.scans += 1
        ranks = self._rankings()
        if not ranks:
            self.no_signal += 1
            return None

        inter = sorted(
            set(ranks["top_base_delay"])
            & set(ranks["top_extra_delay"])
            & set(ranks["top_o2"])
        )
        selected, blocked = [], []
        for n in inter:
            last = self.last_signal_seq.get(int(n))
            if last is not None and self.draw_seq - int(last) < MULTI_COOLDOWN:
                self.cooldown_skips += 1
                blocked.append(int(n))
                continue
            selected.append(int(n))

        if not selected:
            self.no_signal += 1
            return None

        details, ambo_plans, quad_plans, big_plans = [], [], [], []
        a_numbers, a2_numbers, de_numbers, dw_numbers, x_numbers, c_numbers = [], [], [], [], [], []
        origin_row = self.history[-1]
        origin_time = str(origin_row.get("time") or "")
        inter_size = len(inter)
        extra_rank13_gap = int(ranks.get("extra_rank13_gap", 0) or 0)
        for n in selected:
            bd_rank = self._rank_of(n, ranks["top_base_delay"])
            ed_rank = self._rank_of(n, ranks["top_extra_delay"])
            o2_rank = self._rank_of(n, ranks["top_o2"])
            tier = self._tier(bd_rank, o2_rank, origin_row, inter_size=inter_size)
            extra_margin13 = int(ranks["extra_gap"][n]) - extra_rank13_gap
            x_ultra = self._is_x_ultra(
                bd_rank, ed_rank, origin_row, inter_size,
                ranks["extra_gap"][n], extra_rank13_gap,
            )
            if tier == "A":
                a_numbers.append(int(n))
                self.prime_a_signals += 1
            elif tier == "A2":
                a2_numbers.append(int(n))
                self.prime_a2_signals += 1
            elif tier == "DE":
                de_numbers.append(int(n))
                self.prime_d_elite_signals += 1
            elif tier == "DW":
                dw_numbers.append(int(n))
                self.prime_d_wide_signals += 1
            elif tier == "C":
                c_numbers.append(int(n))
                self.prime_c_signals += 1
            if x_ultra:
                x_numbers.append(int(n))
                self.prime_x_signals += 1

            d = {
                "num": n,
                "base_gap": int(ranks["base_gap"][n]),
                "extra_gap": int(ranks["extra_gap"][n]),
                "o2_freq80": int(ranks["o2_freq"][n]),
                "bd_rank": bd_rank, "ed_rank": ed_rank, "o2_rank": o2_rank,
                "origin_time": origin_time, "tier": tier, "prime": tier == "A",
                "intersection_size": inter_size, "extra_rank13_gap": extra_rank13_gap,
                "extra_margin13": extra_margin13, "x_ultra": bool(x_ultra),
            }
            plan = self._partner_plan(n, ranks)
            if plan:
                d["ambo"] = {
                    "p1": dict(plan["p1"]), "p2": dict(plan["p2"]),
                    "support_sum": int(plan["support_sum"]),
                    "super_enabled": bool(plan["super_enabled"]),
                    "cooc_window": int(plan["cooc_window"]),
                }
                # v20.5.1: STANDARD e' controllo puro e NON arma ambi/SUPER.
                if tier in {"A", "A2", "DE", "DW", "C"}:
                    self._arm_ambo(
                        origin_key, n, plan, tier=tier, bd_rank=bd_rank, o2_rank=o2_rank,
                        x_ultra=x_ultra, inter_size=inter_size, extra_margin13=extra_margin13,
                    )
                    ambo_plans.append({"main": n, "tier": tier, **d["ambo"]})

            # v20.8 QUATERNA: SOLO origini A2 e D ELITE. D WIDE/A restano fuori.
            qplan = self._quad_consensus_plan(n, ranks, tier)
            if qplan:
                qcreated = self._arm_quad(origin_key, n, qplan, tier, bd_rank=bd_rank, o2_rank=o2_rank)
                if qcreated:
                    d["quad"] = qplan
                    quad_plans.append(dict(qcreated))

            # v20.9: SETTINA e NOVINA LIVE. Nessun backfill.
            p7=self._big7_plan(n,ranks,tier)
            if p7:
                b7=self._arm_big(origin_key,n,p7,tier,bd_rank=bd_rank,o2_rank=o2_rank)
                if b7:
                    d["big7"]=p7; big_plans.append(dict(b7))
            p9=self._big9_plan(n,ranks,tier)
            if p9:
                b9=self._arm_big(origin_key,n,p9,tier,bd_rank=bd_rank,o2_rank=o2_rank)
                if b9:
                    d["big9"]=p9; big_plans.append(dict(b9))

            details.append(d)
            self.pending.append({
                "origin_key": origin_key, "num": n, "age": 0,
                "hit": False, "hit_colpo": None, "created_at": now_txt(),
                "base_gap": d["base_gap"], "extra_gap": d["extra_gap"],
                "o2_freq80": d["o2_freq80"],
                "bd_rank": bd_rank, "ed_rank": ed_rank, "o2_rank": o2_rank,
                "origin_time": origin_time, "tier": tier, "prime": tier == "A",
                "intersection_size": inter_size, "extra_rank13_gap": extra_rank13_gap,
                "extra_margin13": extra_margin13, "x_ultra": bool(x_ultra),
            })
            self.last_signal_seq[n] = self.draw_seq

        self.pending = self.pending[-200:]
        self.signals += len(selected)
        out = {
            "origin_key": origin_key,
            "numbers": selected,
            "prime_a_numbers": a_numbers,
            "prime_a2_numbers": a2_numbers,
            "prime_d_elite_numbers": de_numbers,
            "prime_d_wide_numbers": dw_numbers,
            "prime_x_numbers": x_numbers,
            "prime_c_numbers": c_numbers,
            "prime_b_numbers": [],  # legacy: nessun nuovo B
            # alias v20.4
            "prime_numbers": a_numbers,
            "details": details,
            "ambo_plans": ambo_plans,
            "quad_plans": quad_plans,
            "big_plans": big_plans,
            "top_base_delay": ranks["top_base_delay"],
            "top_extra_delay": ranks["top_extra_delay"],
            "top_o2": ranks["top_o2"],
            "blocked": blocked,
        }
        self.last_signal = dict(out)
        return out

    @staticmethod
    def should_notify_signal(sig):
        if not sig:
            return False
        if sig.get("prime_a_numbers") and NOTIFY_PRIME_A_SIGNAL:
            return True
        if sig.get("prime_a2_numbers") and NOTIFY_PRIME_A2_SIGNAL:
            return True
        if (sig.get("prime_d_elite_numbers") or sig.get("prime_d_wide_numbers")) and NOTIFY_PRIME_D_SIGNAL:
            return True
        if sig.get("quad_plans") and NOTIFY_QUAD_SIGNAL:
            return True
        if sig.get("big_plans") and NOTIFY_BIG_SIGNAL:
            return True
        # C/X e STANDARD restano shadow; B non genera nuovi segnali.
        return NOTIFY_STANDARD_SIGNAL

    @staticmethod
    def signal_text(sig):
        if not sig:
            return None
        a_nums = {int(x) for x in sig.get("prime_a_numbers", [])}
        a2_nums = {int(x) for x in sig.get("prime_a2_numbers", [])}
        de_nums = {int(x) for x in sig.get("prime_d_elite_numbers", [])}
        dw_nums = {int(x) for x in sig.get("prime_d_wide_numbers", [])}
        x_nums = {int(x) for x in sig.get("prime_x_numbers", [])}
        c_nums = {int(x) for x in sig.get("prime_c_numbers", [])}
        origin_time = ""
        if sig.get("details"):
            origin_time = str((sig.get("details") or [{}])[0].get("origin_time") or "")
        lines = [
            "🧪 MULTI BD12+ED12+O2F12 — v20.9.2",
            "Origine: " + str(sig.get("origin_key")) + (f" | ora {origin_time}" if origin_time else ""),
            "STANDARD: Base RIT12 ∩ Extra RIT12 ∩ Oro2 FREQ12 (W80)",
            f"Segnali standard: {' '.join(f'{int(n):02d}' for n in sig.get('numbers', []))}",
        ]
        if a_nums:
            lines += [
                "", "🔥 PRIME A — QUALITÀ MASSIMA (INVARIATO)",
                f"🎯 A H1: {' '.join(f'{n:02d}' for n in sorted(a_nums))}",
                f"Gate A: BD rank 11-12 + O2 rank {PRIME_A_O2_RANK_MIN}-{PRIME_A_O2_RANK_MAX}",
            ]
        if a2_nums:
            lines += [
                "", "💎 PRIME A2 ELITE — ESPANSIONE SELETTIVA",
                f"🎯 A2 H1: {' '.join(f'{n:02d}' for n in sorted(a2_nums))}",
                f"Gate A2: BD rank 11-12 + O2 rank {PRIME_A2_O2_RANK_MIN}-{PRIME_A2_O2_RANK_MAX} + ora ≤08:00 oppure >16:00",
            ]
        if de_nums:
            lines += [
                "", "💠 PRIME D ELITE — AMBATA OPERATIVA",
                f"🎯 D-ELITE H1: {' '.join(f'{n:02d}' for n in sorted(de_nums))}",
                "Gate D-ELITE: BD rank 1-4 + ora >16:00 + intersezione unica",
            ]
        if dw_nums:
            lines += [
                "", "🔥 PRIME D WIDE — AMBATA OPERATIVA",
                f"🎯 D-WIDE H1: {' '.join(f'{n:02d}' for n in sorted(dw_nums))}",
                "Gate D-WIDE: BD rank 5-8 + ora >16:00 + intersezione unica",
            ]
        if x_nums:
            lines += [
                "", "🧬 X ULTRA SHADOW — CONFERMA EXTRA",
                f"👁️ X: {' '.join(f'{n:02d}' for n in sorted(x_nums))} | ED rank 9-12 + ora >17:00 + Extra margin13≥1",
            ]
        if not a_nums and not a2_nums and not de_nums and not dw_nums:
            lines += ["", "🌑 Nessun PRIME operativo A/A2/D; STANDARD/C/X restano shadow."]

        lines.append("")
        for d in sig.get("details", []):
            n = int(d["num"])
            tier = str(d.get("tier") or "STD")
            tag = {"A":"🔥 A", "A2":"💎 A2", "DE":"💠 D-ELITE", "DW":"🔥 D-WIDE", "C":"🧬 C SHADOW"}.get(tier, "• STD")
            lines.append(
                f"{tag} {n:02d}: BD rank={d.get('bd_rank')} rit={d.get('base_gap')} | "
                f"ED rank={d.get('ed_rank')} rit={d.get('extra_gap')} | "
                f"O2 rank={d.get('o2_rank')} freq80={d.get('o2_freq80')}"
            )
            a = d.get("ambo") or {}
            if a and tier in {"A", "A2", "DE", "DW", "C"}:
                p1, p2 = a.get("p1") or {}, a.get("p2") or {}
                n1, n2 = int(p1.get("num", 0)), int(p2.get("num", 0))
                if tier == "A":
                    lines.append(
                        f"  🔗 AMBO1 {n:02d}-{n1:02d} | ⚡ AMBO2 FAST H1 {n:02d}-{n2:02d} | COOC900 {p1.get('cooc',0)}/{p2.get('cooc',0)}"
                    )
                elif tier == "A2":
                    lines.append(
                        f"  🔗 A2 AMBO1 {n:02d}-{n1:02d} | 🔗 A2 AMBO2 {n:02d}-{n2:02d} | COOC900 {p1.get('cooc',0)}/{p2.get('cooc',0)}"
                    )
                elif tier in {"DE", "DW"}:
                    lines.append(
                        f"  👁️ D ambi shadow: {n:02d}-{n1:02d} / {n:02d}-{n2:02d} | COOC900 {p1.get('cooc',0)}/{p2.get('cooc',0)}"
                    )
                else:
                    lines.append(
                        f"  👁️ C ambi shadow: {n:02d}-{n1:02d} / {n:02d}-{n2:02d} | COOC900 {p1.get('cooc',0)}/{p2.get('cooc',0)}"
                    )
                if a.get("super_enabled"):
                    third_tag = "🔥 SUPER ON" if tier in {"A", "A2"} else "👁️ TERZO SUPER shadow"
                    lines.append(f"  {third_tag} {n1:02d}-{n2:02d} | support_sum={int(a.get('support_sum',0))} ≥ {MULTI_SUPER_GATE}")
                else:
                    lines.append(f"  🔺 TERZO {n1:02d}-{n2:02d} TRIANGLE SHADOW | support_sum={int(a.get('support_sum',0))} < {MULTI_SUPER_GATE}")
                if bool(d.get("x_ultra")):
                    lines.append(f"  🧬 X ULTRA shadow | ED rank={d.get('ed_rank')} | Extra margin13={d.get('extra_margin13')}")

        qplans=list(sig.get("quad_plans") or [])
        if qplans:
            lines += ["", "🔷 QUATERNA — FORWARD"]
            for q in qplans:
                qq=[int(x) for x in q.get("quartet",[])]
                icon="💎" if str(q.get("quad_level"))=="ELITE" else "🔷"
                lines.append(f"{icon} Q-{q.get('quad_level')} {'-'.join(f'{x:02d}' for x in qq)} | consenso {q.get('consensus')}/3 | Jmin={float(q.get('min_jaccard',0)):.3f}")
                lines.append("   💶 1€/colpo H1-H5 | STOP al primo 2/4 o meglio | shadow continua fino H5")

        bplans=list(sig.get("big_plans") or [])
        if bplans:
            lines += ["", "🎯 SETTINA PROFIT FAST + NOVINA v20.9.2 — LIVE"]
            for b in bplans:
                nums=[int(x) for x in b.get("numbers",[])]
                size=int(b.get("system_size",0) or 0)
                if size==7:
                    lines.append(f"🎯 SETTINA PROFIT FAST {'-'.join(f'{x:02d}' for x in nums)} | {b.get('selector')} | origine {b.get('tier')}")
                    lines.append(f"   Gate FAST: support_sum={int(b.get('support_sum',0) or 0)} | operativo H1-H{int(b.get('operational_horizon',SETTINA_FAST_HORIZON) or SETTINA_FAST_HORIZON)}")
                    lines.append("   💶 1€/colpo | premi: 0=€1, 4=€4, 5=€40, 6=€400, 7=€1600 | STOP al primo premio | H3-H5 shadow")
                elif size==9:
                    lines.append(f"💥 NOVINA LIVE {'-'.join(f'{x:02d}' for x in nums)} | {b.get('selector')} | origine {b.get('tier')}")
                    lines.append("   💶 1€/colpo H1-H5 | premi: 0=€2, 5=€10, 6=€40, 7=€400, 8=€2000, 9=€100000 | STOP al primo premio")

        lines += [
            "",
            "🧪 STANDARD resta shadow/control e NON arma ambi/SUPER.",
            "🔥 A e 💎 A2 restano invariati; 💠/🔥 D aggiunge solo intersezioni uniche serali.",
            "👁️ Gli ambi D restano shadow; 🧬 X ULTRA è solo overlay shadow.",
            "🧬 C continua shadow nei casi non-D; B legacy non genera nuovi segnali.",
            "🔺 TRIANGLE: terzo lato seguito su A/A2/D/C; OFF-gate resta shadow.",
            "⏸️ FOCUS / INCROCIO / CORE / legacy non vengono aggiornati.",
        ]
        return "\n".join(lines)

    @staticmethod
    def result_text(ev):
        if not ev or not isinstance(ev.get("row"), dict):
            return None
        r = ev["row"]
        age = int(r.get("age", 0) or 0)
        tier = MultiPrimeV1._tier_from_obj(r)

        if ev.get("kind") in {"big_stop","big_shadow_upgrade"}:
            nums=[int(x) for x in r.get("numbers",[])]
            size=int(r.get("system_size",0) or 0)
            if size not in (7,9) or len(nums)!=size:
                return None
            tag=("🎯 SETTINA PROFIT FAST" if str(r.get("strategy") or "").upper()==SETTINA_FAST_STRATEGY else "🎯 SETTINA LEGACY") if size==7 else "💥 NOVINA LIVE"
            matches=int(ev.get("matches",0) or 0); prize=float(ev.get("prize",0.0) or 0.0)
            if ev.get("kind")=="big_shadow_upgrade":
                return (
                    f"👁️ {tag} — SHADOW UPGRADE H{age}\n\n"
                    f"Origine {r.get('origin_key')} | {'-'.join(f'{x:02d}' for x in nums)}\n"
                    f"Dopo lo STOP operativo: {matches}/{size} → €{prize:.0f} in shadow.\n"
                    f"Operativo già chiuso H{r.get('stop_age')} con {'MISS' if r.get('stop_match') is None else str(r.get('stop_match'))+'/'+str(size)} → €{float(r.get('payout',0)):.0f}; nessuna nuova puntata."
                )
            if ev.get("no_hit"):
                status=f"🛑 STOP H{age} — nessun premio"
            else:
                status=f"✅ {matches}/{size} a H{age} → €{prize:.0f} — STOP"
                if prize>=400: status=f"💥 {matches}/{size} a H{age} → €{prize:.0f} — BIG HIT / STOP"
            return (
                f"{tag} — ESITO OPERATIVO\n\n"
                f"Origine {r.get('origin_key')} | M {int(r.get('main',0)):02d} | origine {r.get('tier')}\n"
                f"Numeri: {'-'.join(f'{x:02d}' for x in nums)}\n"
                f"{status}\n"
                f"Costo origine: €{float(r.get('cost',0)):.0f} | premio operativo: €{float(r.get('payout',0)):.0f}\n"
                f"Selettore {r.get('selector')} | finestra {r.get('window')}\n"
                "👁️ Dopo lo STOP il tracker continua in shadow fino a H5 senza altre puntate."
            )

        if ev.get("kind") in {"quad_stop","quad_shadow_upgrade"}:
            quartet=[int(x) for x in r.get("quartet",[])]
            if len(quartet)!=4:
                return None
            level=str(r.get("quad_level") or "PLUS")
            icon="💎" if level=="ELITE" else "🔷"
            matches=int(ev.get("matches",0) or 0)
            if ev.get("kind")=="quad_shadow_upgrade":
                return (
                    f"👁️ QUATERNA {level} — SHADOW UPGRADE H{age}\n\n"
                    f"Origine {r.get('origin_key')} | {'-'.join(f'{x:02d}' for x in quartet)}\n"
                    f"Dopo lo STOP operativo: {matches}/4 in shadow.\n"
                    f"Operativo già chiuso H{r.get('stop_age')} con {r.get('stop_match')}/4; nessuna nuova puntata."
                )
            if ev.get("no_hit"):
                status="🛑 STOP H5 — mai 2/4"
            elif matches==2:
                status=f"🟡 2/4 a H{age} → €{QUAD_PRIZE_2:.0f} — STOP"
            elif matches==3:
                status=f"✅ 3/4 a H{age} → €{QUAD_PRIZE_3:.0f} — STOP"
            elif matches>=4:
                status=f"💥 4/4 a H{age} → €{QUAD_PRIZE_4:.0f} — STOP"
            else:
                status="🛑 STOP H5"
            return (
                f"{icon} QUATERNA {level} — ESITO OPERATIVO\n\n"
                f"Origine {r.get('origin_key')} | M {int(r.get('main',0)):02d}\n"
                f"Numeri: {'-'.join(f'{x:02d}' for x in quartet)}\n"
                f"{status}\n"
                f"Costo origine fin qui: €{float(r.get('cost',0)):.0f} | premio operativo: €{float(r.get('payout',0)):.0f}\n"
                f"Consenso {r.get('consensus')}/3 | Jmin={float(r.get('min_jaccard',0)):.3f}\n"
                "👁️ Il tracker shadow continua fino a H5 senza altre puntate."
            )

        if ev.get("kind") == "ambo":
            pair = [int(x) for x in r.get("pair", [])]
            slot = str(r.get("slot") or "AMBO")
            if len(pair) != 2:
                return None
            if slot == "SUPER":
                tag = "🔥 SUPER"
            elif slot == "TRIANGLE_OFF":
                tag = "🔺 TRIANGLE SHADOW"
            elif slot == "BASE1":
                tag = "🔗 AMBO1"
            else:
                tag = "⚡ AMBO2 FAST" if tier == "A" else ("🔗 A2 AMBO2" if tier == "A2" else "🔗 AMBO2")
            status = f"✅ HIT al colpo H{age}" if ev.get("hit_now") else "🛑 STOP H5"
            tier_line = "\n🔥 PRIME A" if tier == "A" else ("\n💎 PRIME A2 ELITE" if tier == "A2" else ("\n💠 PRIME D ELITE" if tier == "DE" else ("\n🔥 PRIME D WIDE" if tier == "DW" else ("\n🟠 PRIME B LEGACY" if tier == "B" else ("\n🧬 PRIME C SHADOW" if tier == "C" else "")))))
            fast_note = "\n🎯 FAST H1 centrato." if tier == "A" and slot == "BASE2" and age == 1 and ev.get("hit_now") else ""
            off_note = "\n👁️ Era OFF-gate: hit registrato solo come TRIANGLE SHADOW." if slot == "TRIANGLE_OFF" and ev.get("hit_now") else ""
            return (
                f"🧾 MULTI v20.9.2 — {tag}\n\n"
                f"Origine {r.get('origin_key')} | M {int(r.get('main',0)):02d}\n"
                f"Coppia {pair[0]:02d}-{pair[1]:02d} | {status}"
                f"{tier_line} | BD rank={r.get('bd_rank')} | O2 rank={r.get('o2_rank')}"
                f"{fast_note}{off_note}\n"
                f"support_sum={r.get('support_sum')} | COOC900 P1/P2={r.get('p1_cooc')}/{r.get('p2_cooc')}"
            )

        n = int(r.get("num", 0))
        status = (
            f"✅ HIT al colpo H{age}" if ev.get("hit_now")
            else ("❌ H1 MISS — shadow fino a H5" if age == 1 else "🛑 STOP H5")
        )
        if tier == "A":
            title = "🔥 MULTI PRIME A — ESITO AMBATA"
        elif tier == "A2":
            title = "💎 MULTI PRIME A2 ELITE — ESITO AMBATA"
        elif tier == "DE":
            title = "💠 MULTI PRIME D ELITE — ESITO AMBATA"
        elif tier == "DW":
            title = "🔥 MULTI PRIME D WIDE — ESITO AMBATA"
        elif tier == "B":
            title = "🟠 MULTI PRIME B LEGACY — ESITO AMBATA"
        elif tier == "C":
            title = "🧬 MULTI PRIME C SHADOW — ESITO AMBATA"
        else:
            title = "🧾 MULTI STANDARD — ESITO AMBATA"
        return (
            f"{title}\n\n"
            f"Origine {r.get('origin_key')} | numero {n:02d}" + (f" | ora {r.get('origin_time')}" if r.get('origin_time') else "") + f"\n{status}\n"
            f"BD rank={r.get('bd_rank')} | ED rank={r.get('ed_rank')} | O2 rank={r.get('o2_rank')}\n"
            f"Base rit={r.get('base_gap')} | Extra rit={r.get('extra_gap')} | Oro2 freq80={r.get('o2_freq80')}"
            + (f"\n🧬 X ULTRA shadow | Extra margin13={r.get('extra_margin13')}" if bool(r.get("x_ultra")) else "")
        )

    def should_notify_event(self, ev):
        if not ev or not isinstance(ev.get("row"), dict):
            return False
        r = ev["row"]
        tier = self._tier_from_obj(r)
        kind = str(ev.get("kind") or "")
        slot = str(r.get("slot") or "")

        if kind == "big_stop":
            return NOTIFY_BIG_RESULT
        if kind == "big_shadow_upgrade":
            return NOTIFY_BIG_SHADOW_UPGRADE
        if kind == "quad_stop":
            return NOTIFY_QUAD_RESULT
        if kind == "quad_shadow_upgrade":
            return NOTIFY_QUAD_SHADOW_UPGRADE

        if tier == "A":
            if kind == "ambata":
                return NOTIFY_PRIME_A_RESULT
            if slot in {"BASE1", "BASE2", "SUPER"}:
                return NOTIFY_PRIME_A_RESULT
            if slot == "TRIANGLE_OFF":
                return bool(ev.get("hit_now")) and NOTIFY_TRIANGLE_OFF_HIT
        elif tier == "A2":
            if kind == "ambata":
                return NOTIFY_PRIME_A2_RESULT
            if slot in {"BASE1", "BASE2", "SUPER"}:
                return NOTIFY_PRIME_A2_RESULT
            if slot == "TRIANGLE_OFF":
                return bool(ev.get("hit_now")) and NOTIFY_TRIANGLE_OFF_HIT
        elif tier in {"DE", "DW"}:
            # D è operativo SOLO come ambata; tutti gli ambi restano shadow.
            return kind == "ambata" and NOTIFY_PRIME_D_RESULT
        elif tier == "B":
            # Solo eventuali pending legacy già nati in v20.5.
            return kind == "ambata" and NOTIFY_PRIME_B_RESULT
        elif tier == "C":
            return False
        return False

    def _stats(self, tier=None):
        rows = list(self.records)
        if tier is not None:
            rows = [r for r in rows if self._tier_from_obj(r) == str(tier).upper()]
        n = len(rows)
        h1 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 1)
        h3 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 3)
        h5 = sum(1 for r in rows if bool(r.get("hit")))
        return n, h1, h3, h5

    def _stats_x(self):
        rows = [r for r in self.records if bool(r.get("x_ultra"))]
        n = len(rows)
        h1 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 1)
        h3 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 3)
        h5 = sum(1 for r in rows if bool(r.get("hit")))
        return n, h1, h3, h5

    def _ambo_stats(self, slots=None, tier=None):
        slots = set(slots) if slots is not None else None
        rows = [
            r for r in self.ambo_records
            if (slots is None or str(r.get("slot")) in slots)
            and (tier is None or self._tier_from_obj(r) == str(tier).upper())
        ]
        n = len(rows)
        h1 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 1)
        h3 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 3)
        h5 = sum(1 for r in rows if bool(r.get("hit")))
        return n, h1, h3, h5

    def _ambo_stats_x(self, slots=None):
        slots = set(slots) if slots is not None else None
        rows = [r for r in self.ambo_records if bool(r.get("x_ultra")) and (slots is None or str(r.get("slot")) in slots)]
        n = len(rows)
        h1 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 1)
        h3 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 3)
        h5 = sum(1 for r in rows if bool(r.get("hit")))
        return n, h1, h3, h5

    def _origin_coverage(self, tier):
        tier = str(tier).upper()
        grouped = {}
        for r in self.ambo_records:
            if self._tier_from_obj(r) != tier:
                continue
            grouped.setdefault(str(r.get("origin_id")), []).append(r)
        pending_ids = {
            str(r.get("origin_id")) for r in self.ambo_pending
            if self._tier_from_obj(r) == tier
        }
        base_valid = {}
        tri_valid = {}
        for oid, rows in grouped.items():
            if oid in pending_ids:
                continue
            slots = {str(r.get("slot")) for r in rows}
            if {"BASE1", "BASE2"}.issubset(slots):
                base_valid[oid] = rows
            if {"BASE1", "BASE2"}.issubset(slots) and ("SUPER" in slots or "TRIANGLE_OFF" in slots):
                tri_valid[oid] = rows

        base_n = len(base_valid)
        base_hit = sum(
            1 for rows in base_valid.values()
            if any(bool(r.get("hit")) for r in rows if str(r.get("slot")) in {"BASE1", "BASE2"})
        )
        tri_n = len(tri_valid)
        all3_hit = 0
        rescue = 0
        for rows in tri_valid.values():
            base_rows = [r for r in rows if str(r.get("slot")) in {"BASE1", "BASE2"}]
            third_rows = [r for r in rows if str(r.get("slot")) in {"SUPER", "TRIANGLE_OFF"}]
            bh = any(bool(r.get("hit")) for r in base_rows)
            th = any(bool(r.get("hit")) for r in third_rows)
            if bh or th:
                all3_hit += 1
            if (not bh) and th:
                rescue += 1
        return {
            "base_n": base_n, "base_hit": base_hit,
            "tri_n": tri_n, "all3_hit": all3_hit, "rescue": rescue,
        }

    def _pending_counts(self, tier):
        tier = str(tier).upper()
        pa = sum(1 for r in self.pending if self._tier_from_obj(r) == tier)
        pam = sum(1 for r in self.ambo_pending if self._tier_from_obj(r) == tier)
        return pa, pam

    def _big_stats(self, size, strategy=None):
        size=int(size)
        rows=[r for r in self.big_records if int(r.get("system_size",0) or 0)==size]
        if strategy is not None:
            rows=[r for r in rows if str(r.get("strategy") or "").upper()==str(strategy).upper()]
        cost=sum(float(r.get("cost",0) or 0) for r in rows)
        payout=sum(float(r.get("payout",0) or 0) for r in rows)
        roi=(100.0*payout/cost) if cost>0 else 0.0
        dist=Counter(); miss=0; big400=0; shbig=0
        for r in rows:
            if float(r.get("payout",0) or 0)>0 and r.get("stop_match") is not None:
                m=int(r.get("stop_match")); dist[m]+=1
                if float(r.get("payout",0) or 0)>=400: big400+=1
            else:
                miss+=1
            if float(r.get("max_shadow_payout",0) or 0)>=400: shbig+=1
        return {"n":len(rows),"cost":cost,"payout":payout,"roi":roi,"dist":dist,"miss":miss,"big400":big400,"shadow400":shbig}

    def _quad_stats(self, elite_only=False):
        rows=[r for r in self.quad_records if (not elite_only or str(r.get("quad_level") or "").upper()=="ELITE")]
        n=len(rows)
        cost=sum(float(r.get("cost",0.0) or 0.0) for r in rows)
        payout=sum(float(r.get("payout",0.0) or 0.0) for r in rows)
        s2=sum(1 for r in rows if int(r.get("stop_match") or 0)==2)
        s3=sum(1 for r in rows if int(r.get("stop_match") or 0)==3)
        s4=sum(1 for r in rows if int(r.get("stop_match") or 0)>=4)
        miss=sum(1 for r in rows if not bool(r.get("operational_stopped")))
        sh2=sum(1 for r in rows if int(r.get("max_shadow_match",0) or 0)>=2)
        sh3=sum(1 for r in rows if int(r.get("max_shadow_match",0) or 0)>=3)
        sh4=sum(1 for r in rows if int(r.get("max_shadow_match",0) or 0)>=4)
        roi=(100.0*payout/cost) if cost>0 else 0.0
        return {"n":n,"cost":cost,"payout":payout,"roi":roi,"s2":s2,"s3":s3,"s4":s4,"miss":miss,"sh2":sh2,"sh3":sh3,"sh4":sh4}

    def text(self):
        n, h1, h3, h5 = self._stats(None)
        an, ah1, ah3, ah5 = self._stats("A")
        a2n, a2h1, a2h3, a2h5 = self._stats("A2")
        den, deh1, deh3, deh5 = self._stats("DE")
        dwn, dwh1, dwh3, dwh5 = self._stats("DW")
        xn, xh1, xh3, xh5 = self._stats_x()
        cn, ch1, ch3, ch5 = self._stats("C")
        bn, bh1, _, _ = self._stats("B")

        a1n, a1h1, _, a1h5 = self._ambo_stats({"BASE1"}, "A")
        a2bn, a2bh1, _, a2bh5 = self._ambo_stats({"BASE2"}, "A")
        e1n, e1h1, _, e1h5 = self._ambo_stats({"BASE1"}, "A2")
        e2n, e2h1, _, e2h5 = self._ambo_stats({"BASE2"}, "A2")
        d1n, d1h1, _, d1h5 = self._ambo_stats({"BASE1"}, None)
        d2n, d2h1, _, d2h5 = self._ambo_stats({"BASE2"}, None)
        # Solo D per gli ambi shadow.
        d_ambo_rows1 = [r for r in self.ambo_records if self._tier_from_obj(r) in {"DE","DW"} and str(r.get("slot"))=="BASE1"]
        d_ambo_rows2 = [r for r in self.ambo_records if self._tier_from_obj(r) in {"DE","DW"} and str(r.get("slot"))=="BASE2"]
        d1n=len(d_ambo_rows1); d1h5=sum(1 for r in d_ambo_rows1 if bool(r.get("hit")))
        d2n=len(d_ambo_rows2); d2h5=sum(1 for r in d_ambo_rows2 if bool(r.get("hit")))

        asn, ash1, ash3, ash5 = self._ambo_stats({"SUPER"}, "A")
        a2sn, a2sh1, a2sh3, a2sh5 = self._ambo_stats({"SUPER"}, "A2")
        op_sn, op_h1, op_h3, op_h5 = asn+a2sn, ash1+a2sh1, ash3+a2sh3, ash5+a2sh5

        acov = self._origin_coverage("A")
        ecov = self._origin_coverage("A2")
        decov = self._origin_coverage("DE")
        dwcov = self._origin_coverage("DW")
        apa, apam = self._pending_counts("A")
        epa, epam = self._pending_counts("A2")
        depa, depam = self._pending_counts("DE")
        dwpa, dwpam = self._pending_counts("DW")
        cpa, cpam = self._pending_counts("C")
        bpa, bpam = self._pending_counts("B")

        dclosed=den+dwn; dh1=deh1+dwh1; dh3=deh3+dwh3; dh5=deh5+dwh5
        dcov_n=decov['tri_n']+dwcov['tri_n']; dcov_hit=decov['all3_hit']+dwcov['all3_hit']
        qplus=self._quad_stats(False); qelite=self._quad_stats(True)
        qpending=len(self.quad_pending)
        b7=self._big_stats(7, SETTINA_FAST_STRATEGY); b9=self._big_stats(9)
        b7pending=sum(1 for r in self.big_pending if int(r.get("system_size",0) or 0)==7 and str(r.get("strategy") or "").upper()==SETTINA_FAST_STRATEGY)
        b9pending=sum(1 for r in self.big_pending if int(r.get("system_size",0) or 0)==9)

        lines = [
            "🧪 MULTI PRIME A + A2 + D + QUATERNA + SETTINA FAST + NOVINA — v20.9.2",
            "STANDARD shadow: BD12 ∩ ED12 ∩ O2F12",
            f"🔥 A: BD11-12 + O2 {PRIME_A_O2_RANK_MIN}-{PRIME_A_O2_RANK_MAX} | 💎 A2: BD11-12 + O2 {PRIME_A2_O2_RANK_MIN}-{PRIME_A2_O2_RANK_MAX} + fascia Elite",
            "💠 D-ELITE: BD1-4 | 🔥 D-WIDE: BD5-8 | entrambi >16:00 + intersezione unica",
            "🧬 X ULTRA shadow: D + ED9-12 + >17:00 + Extra margin13≥1",
            f"Oro2 W{MULTI_WINDOW} | cooldown {MULTI_COOLDOWN} | COOC W{MULTI_COOC_WINDOW} | H{MULTI_HORIZON}",
            f"🛡️ FIX base {self.v2071_started_from_key or '-'} | scan da fix {max(0,self.scans-self.v2071_scans_base)} | STD da fix {max(0,self.signals-self.v2071_signals_base)}",
            "",
            f"📚 MULTI history {len(self.history)} | scan {self.scans} | STD {self.signals} | skip {self.cooldown_skips}",
            f"STANDARD chiusi {n} | H1 {h1}/{n} ({safe_pct(h1,n):.2f}%) | H3 {h3}/{n} ({safe_pct(h3,n):.2f}%) | H5 {h5}/{n} ({safe_pct(h5,n):.2f}%)",
            "",
            f"🔥 A — start {self.prime_a_started_from_key or '-'} | creati {self.prime_a_signals} | pending {apa}",
            f"AMBATA A H1 {ah1}/{an} ({safe_pct(ah1,an):.2f}%) | H3 {ah3}/{an} ({safe_pct(ah3,an):.2f}%) | H5 {ah5}/{an} ({safe_pct(ah5,an):.2f}%)",
            f"A AMBO1 H5 {a1h5}/{a1n} ({safe_pct(a1h5,a1n):.2f}%) | AMBO2 H5 {a2bh5}/{a2bn} ({safe_pct(a2bh5,a2bn):.2f}%) | ≥1 dei 3 {acov['all3_hit']}/{acov['tri_n']} ({safe_pct(acov['all3_hit'],acov['tri_n']):.2f}%)",
            "",
            f"💎 A2 ELITE — start {self.prime_a2_started_from_key or '-'} | creati {self.prime_a2_signals} | pending {epa}",
            f"AMBATA A2 H1 {a2h1}/{a2n} ({safe_pct(a2h1,a2n):.2f}%) | H3 {a2h3}/{a2n} ({safe_pct(a2h3,a2n):.2f}%) | H5 {a2h5}/{a2n} ({safe_pct(a2h5,a2n):.2f}%)",
            f"A2 AMBO1 H5 {e1h5}/{e1n} ({safe_pct(e1h5,e1n):.2f}%) | AMBO2 H5 {e2h5}/{e2n} ({safe_pct(e2h5,e2n):.2f}%) | ≥1 dei 3 {ecov['all3_hit']}/{ecov['tri_n']} ({safe_pct(ecov['all3_hit'],ecov['tri_n']):.2f}%)",
            "",
            f"💠 D ELITE — start {self.prime_d_elite_started_from_key or '-'} | creati {self.prime_d_elite_signals} | pending {depa}",
            f"AMBATA DE H1 {deh1}/{den} ({safe_pct(deh1,den):.2f}%) | H3 {deh3}/{den} ({safe_pct(deh3,den):.2f}%) | H5 {deh5}/{den} ({safe_pct(deh5,den):.2f}%)",
            f"🔥 D WIDE — start {self.prime_d_wide_started_from_key or '-'} | creati {self.prime_d_wide_signals} | pending {dwpa}",
            f"AMBATA DW H1 {dwh1}/{dwn} ({safe_pct(dwh1,dwn):.2f}%) | H3 {dwh3}/{dwn} ({safe_pct(dwh3,dwn):.2f}%) | H5 {dwh5}/{dwn} ({safe_pct(dwh5,dwn):.2f}%)",
            f"D COMBINATO chiusi {dclosed} | H1 {dh1}/{dclosed} ({safe_pct(dh1,dclosed):.2f}%) | H3 {dh3}/{dclosed} ({safe_pct(dh3,dclosed):.2f}%) | H5 {dh5}/{dclosed} ({safe_pct(dh5,dclosed):.2f}%)",
            f"D AMBI shadow: A1 H5 {d1h5}/{d1n} ({safe_pct(d1h5,d1n):.2f}%) | A2 H5 {d2h5}/{d2n} ({safe_pct(d2h5,d2n):.2f}%) | ≥1 dei 3 {dcov_hit}/{dcov_n} ({safe_pct(dcov_hit,dcov_n):.2f}%)",
            "",
            f"🧬 X ULTRA SHADOW — start {self.prime_x_started_from_key or '-'} | marcati {self.prime_x_signals}",
            f"X AMBATA H1 {xh1}/{xn} ({safe_pct(xh1,xn):.2f}%) | H3 {xh3}/{xn} ({safe_pct(xh3,xn):.2f}%) | H5 {xh5}/{xn} ({safe_pct(xh5,xn):.2f}%)",
            "",
            f"🧬 C legacy shadow: creati {self.prime_c_signals} | chiusi {cn} | H1 {ch1}/{cn} ({safe_pct(ch1,cn):.2f}%) | pending {cpa}/{cpam}",
            f"🟠 B legacy congelato: creati {self.prime_b_signals} | chiusi {bn} | H1 {bh1}/{bn} ({safe_pct(bh1,bn):.2f}%) | pending {bpa}/{bpam}",
            f"🔥 SUPER operativo solo A+A2: H1 {op_h1}/{op_sn} ({safe_pct(op_h1,op_sn):.2f}%) | H5 {op_h5}/{op_sn} ({safe_pct(op_h5,op_sn):.2f}%)",
            "",
            f"🔷 QUATERNA PLUS/ELITE — start {self.quad_started_from_key or '-'} | creati PLUS≥2/3 {self.quad_signals} | ELITE 3/3 {self.quad_elite_signals} | pending {qpending}",
            f"Q-PLUS chiuse {qplus['n']} | costo €{qplus['cost']:.0f} | premi €{qplus['payout']:.0f} | ROI {qplus['roi']:.1f}%",
            f"Q-PLUS stop: 2/4 {qplus['s2']} | 3/4 {qplus['s3']} | 4/4 {qplus['s4']} | MISS {qplus['miss']} | shadow H5 ≥3/4 {qplus['sh3']} | 4/4 {qplus['sh4']}",
            f"💎 Q-ELITE chiuse {qelite['n']} | costo €{qelite['cost']:.0f} | premi €{qelite['payout']:.0f} | ROI {qelite['roi']:.1f}%",
            f"Q-ELITE stop: 2/4 {qelite['s2']} | 3/4 {qelite['s3']} | 4/4 {qelite['s4']} | MISS {qelite['miss']} | shadow H5 ≥3/4 {qelite['sh3']} | 4/4 {qelite['sh4']}",
            "💶 Regola live Q: 1€/colpo, STOP al primo 2/4+; tracking shadow continua fino H5.",
            "",
            f"🎯 SETTINA PROFIT FAST — start {self.big7_fast_started_from_key or '-'} | create {self.big7_fast_signals} | pending {b7pending} | chiuse {b7['n']}",
            "Gate: A2 O2rank=3 + support6≥7 | DE BDrank1-3 + O2rank10-12 | operativo H1-H2",
            f"SETTINA FAST costo €{b7['cost']:.0f} | premi €{b7['payout']:.0f} | ROI {b7['roi']:.1f}% | 0/7 {b7['dist'].get(0,0)} | 4/7 {b7['dist'].get(4,0)} | 5/7 {b7['dist'].get(5,0)} | 6/7 {b7['dist'].get(6,0)} | 7/7 {b7['dist'].get(7,0)} | MISS {b7['miss']}",
            f"SETTINA FAST BIG≥€400 operativi {b7['big400']} | shadow H5 ≥€400 {b7['shadow400']}",
            f"💥 NOVINA LIVE — start {self.big_started_from_key or '-'} | create {self.big9_signals} | pending {b9pending} | chiuse {b9['n']}",
            f"NOVINA costo €{b9['cost']:.0f} | premi €{b9['payout']:.0f} | ROI {b9['roi']:.1f}% | 0/9 {b9['dist'].get(0,0)} | 5/9 {b9['dist'].get(5,0)} | 6/9 {b9['dist'].get(6,0)} | 7/9 {b9['dist'].get(7,0)} | 8/9 {b9['dist'].get(8,0)} | 9/9 {b9['dist'].get(9,0)} | MISS {b9['miss']}",
            f"NOVINA BIG≥€400 operativi {b9['big400']} | shadow H5 ≥€400 {b9['shadow400']}",
            "💶 Regola LIVE: SETTINA FAST H1-H2; NOVINA H1-H5; STOP al primo premio ufficiale; shadow continua fino H5.",
            "Baseline: ambata H1 22.22% | ambo H1 ≈4.74% | ambo H5 ≈21.57%.",
            "⏸️ FOCUS / INCROCIO / CORE / legacy: PAUSATI; state conservato.",
        ]
        if self.pending:
            lines.append("Pending ambate: " + ", ".join(
                f"{self._tier_from_obj(x)}:{int(x['num']):02d}@H{int(x.get('age',0))+1}" for x in self.pending[-12:]
            ))
        if self.last_signal:
            lines.append("Ultimo segnale: " + str(self.last_signal.get("origin_key")) + " → " + " ".join(f"{int(n):02d}" for n in self.last_signal.get("numbers", [])))
        return "\n".join(lines)



# ============================================================
# V52 MULTI — LIVE, TUTTI I SEGNALI DELLE 5 COPPIE, SENZA LIMITE GIORNALIERO
# Regole V51/V52 bloccate, nessuna ricalibrazione, nessun backfill.
# ============================================================
class V52LiveTracker:
    def __init__(self, data=None):
        d = data if isinstance(data, dict) else {}
        self.start_key = str(d.get('start_key') or '')
        self.last_evaluated_origin = str(d.get('last_evaluated_origin') or '')
        self.plays = [dict(r) for r in (d.get('plays') or []) if isinstance(r, dict) and r.get('origin_key')][-12000:]
        self.used_days = set(str(x) for x in (d.get('used_days') or []) if x)
        self.used_days.update(str(r['day']) for r in self.plays if r.get('day'))

    def dump(self):
        return {
            'start_key': self.start_key,
            'last_evaluated_origin': self.last_evaluated_origin,
            'plays': self.plays[-12000:],
            'used_days': sorted(self.used_days)[-12000:],
            'rules_version': 'V52_MULTI_FIXED_5_2025',
        }

    def initialize(self, history):
        if not self.start_key and history:
            # Il primo avvio prende come base l'ULTIMA estrazione gia' nota.
            # Nessun segnale pregresso viene notificato o ricostruito.
            self.start_key = str(history[-1]['key'])
            self.last_evaluated_origin = self.start_key
            return True
        return False

    @staticmethod
    def _draw_stamp(row):
        if not isinstance(row, dict): return None
        try:
            hh, mm = (int(x) for x in str(row.get('time', '')).replace('.', ':').split(':')[:2])
            if not (0 <= hh <= 23 and 0 <= mm <= 59): return None
            start = datetime.fromisoformat(str(row['day'])).replace(tzinfo=BOT_TZ)
            # Concorso #288 delle 00:00: l'archivio lo associa al giorno precedente.
            # Cronologicamente avviene a mezzanotte del giorno successivo.
            if int(row.get('draw_id', 0) or 0) > 1 and hh == mm == 0:
                start += timedelta(days=1)
            return start.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except Exception:
            return None

    @staticmethod
    def _next_expected_key(row):
        try:
            d = str(row['day'])
            n = int(row['draw_id'])
            if n >= 1 and str(row.get('time','')).replace('.',':').strip() in ('00:00','0:00'):
                return draw_key((datetime.fromisoformat(d).date() + timedelta(days=1)).isoformat(), 1)
            if 1 <= n < 288: return draw_key(d, n + 1)
        except Exception:
            pass
        return None

    @classmethod
    def _consecutive(cls, earlier, later):
        a, b = cls._draw_stamp(earlier), cls._draw_stamp(later)
        return bool(a and b and (b-a).total_seconds() == 300 and
                    cls._next_expected_key(earlier) == str(later.get('key')))

    @classmethod
    def _eligible(cls, history):
        # Calcola la puntata su t=prossima estrazione, usando SOLO t-1..t-4.
        # Devono esistere quattro estrazioni cronologicamente adiacenti.
        if len(history) < 900: return None
        # Replica ESATTA V51/V52: scartare il target se almeno uno degli
        # 80 draw precedenti contiene Extra incoerenti (Base intersecato Extra).
        if any(len(r.get('extra',[])) != 15 or
               (set(r.get('nums',[])) & set(r.get('extra',[])))
               for r in history[-80:]): return None
        rows = history[-4:]
        if not all(cls._consecutive(a,b) for a,b in zip(rows, rows[1:])): return None
        if len(rows[-1].get('extra', [])) != 15: return None
        if any(n in set(rows[-1].get('nums', [])) for n in rows[-1]['extra']): return None
        oro = int(rows[0].get('oro') or 0)
        extra = set(int(n) for n in rows[-1]['extra'])
        # Tutte le coppie qualificate nello stesso concorso: nessun taglio al primo.
        return [(pair, spia_oro, spia_extra) for pair, spia_oro, spia_extra in V52_RULES
                if oro == spia_oro and spia_extra in extra]

    def close_with_draw(self, newest, previous, previous_time=None):
        out = []
        newest_key = str(newest.get('key') or '')
        for row in self.plays:
            if row.get('status') != 'PENDING': continue
            origin_key = str(row['origin_key'])
            expected = str(row.get('target_key') or '')
            if newest_key == expected:
                # Controlliamo tempo e continuita' con l'ultima estrazione reale.
                if previous and self._consecutive(previous, newest):
                    win = all(int(n) in set(newest['nums']) for n in row['pair'])
                    row.update(status='CLOSED', hit=win, result_key=newest_key,
                               prize=V52_PRIZE_H1 if win else 0.0)
                    symbol = '✅ HIT' if win else '❌ MISS'
                    out.append(f"{symbol} — V52 MULTI LIVE — AMBO H1\n"
                               f"{row['pair'][0]:02d}-{row['pair'][1]:02d} | concorso {newest_key}\n"
                               f"{'Premio simulato €14 | netto +€13' if win else 'Netto simulato -€1'}\n"
                               "Puntata di riferimento €1. Nessuna giocata automatica.")
                else:
                    row.update(status='MISSING', hit=None, result_key=newest_key, prize=0.0)
                    out.append(f"⚠️ V52 MULTI H1 NON VERIFICABILE {row['pair'][0]:02d}-{row['pair'][1]:02d} | {expected}; manca una continuita' certa del feed.")
            elif order_key(newest_key) and order_key(expected) and order_key(newest_key) > order_key(expected):
                row.update(status='MISSING', hit=None, result_key=newest_key, prize=0.0)
                out.append(f"⚠️ V52 MULTI H1 NON VERIFICABILE {row['pair'][0]:02d}-{row['pair'][1]:02d} | estrazione attesa {expected} non presente nel feed.")
        return out

    def arm(self, history, clock=None, check_freshness=True):
        if not V52_LIVE_ENABLED or not history: return []
        if self.initialize(history): return []
        current = history[-1]
        origin = str(current['key'])
        if not order_key(origin) or not order_key(self.start_key): return []
        if order_key(origin) <= order_key(self.start_key): return []
        if self.last_evaluated_origin and order_key(self.last_evaluated_origin) and order_key(origin) <= order_key(self.last_evaluated_origin): return []
        # Nessuna emissione retroattiva dopo riavvio / catch-up: si valuta soltanto l'origine piu' recente.
        self.last_evaluated_origin = origin
        target_key = self._next_expected_key(current)
        if target_key is None: return []
        candidates = self._eligible(history)
        if not candidates: return []
        # Il concorso previsto deve essere ancora futuro.
        if check_freshness:
            ts = self._draw_stamp(current)
            now = clock or now_dt()
            if ts is None or not (0 <= (now-ts).total_seconds() < 290): return []
        target_day = str(target_key).split('#')[0]
        existing = {(str(r.get('origin_key')), tuple(r.get('pair') or [])) for r in self.plays}
        messages = []
        for pair, oro, extra in candidates:
            if (origin, tuple(pair)) in existing: continue
            rec = {'id':f'V52|{origin}|{pair[0]:02d}-{pair[1]:02d}',
                   'day':target_day, 'origin_key':origin, 'target_key':target_key,
                   'pair':list(pair), 'oro1_t4':oro, 'extra_t1':extra,
                   'status':'PENDING', 'result_key':None, 'hit':None,
                   'stake':V52_STAKE_H1, 'prize':0.0,
                   'created_at':now_dt().isoformat(timespec='seconds')}
            self.plays.append(rec)
            existing.add((origin, tuple(pair)))
            self.used_days.add(target_day)  # solo compatibilita' state precedente
            messages.append(
                f"🚀 V52 MULTI — AMBO LIVE H1\n"
                f"🎯 AMBO: {pair[0]:02d}-{pair[1]:02d}\n"
                f"Spie: Oro1 {oro:02d} a t−4 + Extra {extra:02d} a t−1\n"
                f"Ultimo concorso noto: {origin}\n"
                f"✅ PROSSIMO CONCORSO: {target_key}\n"
                "TUTTI i segnali validi delle 5 coppie | €1 indicativo ciascuno | H1 | nessuna progressione.\n"
                "⚠️ Metodo sperimentale; nessuna vincita garantita.")
        self.plays = self.plays[-12000:]
        return messages

    def report(self, history):
        closed = [r for r in self.plays if r.get('status') == 'CLOSED']
        hits = sum(r.get('hit') is True for r in closed)
        missing = sum(r.get('status') == 'MISSING' for r in self.plays)
        pending = [r for r in self.plays if r.get('status') == 'PENDING']
        stakes = sum(float(r.get('stake') or 0) for r in closed)
        prize = sum(float(r.get('prize') or 0) for r in closed)
        last = self.plays[-1] if self.plays else {}
        today = str(history[-1]['day']) if history else now_dt().date().isoformat()
        today_rows = [r for r in self.plays if r.get('day') == today]
        lines = [
            '🚀 V52 MULTI — TUTTI I SEGNALI LIVE H1',
            f"Stato: {'ATTIVO' if V52_LIVE_ENABLED else 'SPENTO'} | Warmup {len(history)}/900",
            'Regola: ogni trigger di 80-86, 38-39, 60-61, 02-09, 71-78; anche ripetizioni nello stesso giorno.',
            f"Forward dal: {self.start_key or '-'}",
            f"Totale {len(self.plays)} | chiusi {len(closed)} | HIT {hits}/{len(closed)} "
            f"({safe_pct(hits,len(closed)):.2f}%) | pending {len(pending)} | MISSING {missing}",
            f"Saldo SOLO chiusi, €1/H1 ciascuno: €{prize-stakes:+.0f}",
            f"Oggi ({today}): {len(today_rows)} segnali V52",
        ]
        for pair, _, _ in V52_RULES:
            rows = [r for r in closed if tuple(r.get('pair',[])) == tuple(pair)]
            wins = sum(r.get('hit') is True for r in rows)
            lines.append(f"• {pair[0]:02d}-{pair[1]:02d}: {wins}/{len(rows)} HIT | €{14*wins-len(rows):+d}")
        lines += [
            f"Ultimo: {last.get('origin_key','-')} -> {last.get('target_key','-')} | "
            f"{('-'.join(f'{n:02d}' for n in last['pair'])) if last.get('pair') else '-'} | {last.get('status','-')}",
            '⚠️ Statistiche 2025 retrospettive; nessuna schedina acquistata automaticamente.',
        ]
        return '\n'.join(lines)


def _merge_v52_state(a,b):
    aa = a if isinstance(a,dict) else {}
    bb = b if isinstance(b,dict) else {}
    if not aa and not bb: return None
    best = {}
    ranks = {'PENDING':0, 'MISSING':1, 'CLOSED':2}
    for src in (aa,bb):
        for rec in src.get('plays') or []:
            if not isinstance(rec,dict) or not rec.get('origin_key'): continue
            # Merge compatibile anche con i record della V52 precedente (ID solo origine).
            identity = (str(rec['origin_key']), tuple(rec.get('pair') or []))
            old = best.get(identity)
            if old is None or ranks.get(str(rec.get('status')), -1) > ranks.get(str(old.get('status')),-1):
                best[identity] = dict(rec)
    plays = sorted(best.values(),key=lambda r:order_key(r['origin_key']) or (-1,-1))[-12000:]
    days = set(str(d) for src in (aa,bb) for d in (src.get('used_days') or []) if d)
    days.update(str(r['day']) for r in plays if r.get('day'))
    return {
        'start_key':_key_min(aa.get('start_key'),bb.get('start_key')) or aa.get('start_key') or bb.get('start_key') or '',
        'last_evaluated_origin':_key_max(aa.get('last_evaluated_origin'),bb.get('last_evaluated_origin')) or '',
        'plays':plays, 'used_days':sorted(days)[-12000:],
        'rules_version':'V52_MULTI_FIXED_5_2025',
    }


# ============================================================
# V55 INCROCI SELETTIVI — LIVE H1
# V52 resta LIVE; V55 produce UN SOLO incrocio per target.
# Regola: seconda coppia V52 entro 12 estrazioni dal precedente
# segnale V52 di un'ALTRA coppia, il cui H1 aveva una sola ambata.
# Scegli il partner della nuova coppia che massimizza la somma
# delle frequenze Base nelle 80 estrazioni PRIMA del nuovo H1.
# Nessun backfill, nessuna progressione, nessuna scommessa reale.
# ============================================================
class V55LiveTracker:
    def __init__(self, data=None):
        d = data if isinstance(data, dict) else {}
        self.start_key = str(d.get('start_key') or '')
        self.last_evaluated_origin = str(d.get('last_evaluated_origin') or '')
        self.plays = [dict(r) for r in d.get('plays', []) if isinstance(r, dict) and r.get('origin_key')][-12000:]

    def dump(self):
        return {
            'start_key': self.start_key,
            'last_evaluated_origin': self.last_evaluated_origin,
            'plays': self.plays[-12000:],
            'rules_version': 'V55_OLD_ONE_HIT_NEXT_V52_WITHIN_12_SUM_BASE80_ONE_PER_TARGET_H1',
        }

    def initialize(self, history):
        if self.start_key or not history:
            return False
        # Nuovo tracker: parte DOPO l'ultima estrazione già in archivio.
        # È intenzionale non ricostruire segnali LIVE precedenti al deploy.
        self.start_key = str(history[-1]['key'])
        self.last_evaluated_origin = self.start_key
        return True

    @staticmethod
    def _pair_code(pair):
        return '-'.join(f'{int(n):02d}' for n in sorted(pair))

    @staticmethod
    def _target_gap(older, newer):
        try:
            da, na = str(older).split('#')
            db, nb = str(newer).split('#')
            if da != db:
                return None
            g = int(nb) - int(na)
            return g if g > 0 else None
        except Exception:
            return None

    def close_with_draw(self, newest, previous):
        out = []
        newkey = str(newest.get('key') or '')
        for rec in self.plays:
            if rec.get('status') != 'PENDING':
                continue
            target = str(rec.get('target_key') or '')
            if newkey == target:
                if previous and V52LiveTracker._consecutive(previous, newest):
                    base = set(int(n) for n in newest.get('nums') or [])
                    hit = all(int(n) in base for n in rec['pair'])
                    rec.update(status='CLOSED', hit=bool(hit),
                               prize=(V55_PRIZE_H1 if hit else 0.0), result_key=newkey)
                    tag = '✅ HIT' if hit else '❌ MISS'
                    out.append(f'{tag} — V55 INCROCIO LIVE H1\n'
                               f"Ambo {self._pair_code(rec['pair'])} | concorso {newkey}\n"
                               f"{'Premio teorico €14, netto +€13' if hit else 'Netto teorico −€1'}\n"
                               '€1 indicativo; nessuna giocata automatica.')
                else:
                    rec.update(status='MISSING', hit=None, prize=0.0, result_key=newkey)
                    out.append(f"⚠️ V55 H1 NON VERIFICABILE | {self._pair_code(rec['pair'])} | {target}: feed discontinuo.")
            elif order_key(newkey) and order_key(target) and order_key(newkey) > order_key(target):
                rec.update(status='MISSING', hit=None, prize=0.0, result_key=newkey)
                out.append(f"⚠️ V55 H1 NON VERIFICABILE | {self._pair_code(rec['pair'])} | estrazione {target} mancante.")
        return out

    def arm(self, history, v52, clock=None, check_freshness=True):
        if not V55_LIVE_ENABLED or len(history) < 900:
            return []
        if self.initialize(history):
            return []
        current = history[-1]
        origin = str(current.get('key') or '')
        if not order_key(origin) or not order_key(self.start_key):
            return []
        if order_key(origin) <= order_key(self.start_key):
            return []
        if self.last_evaluated_origin and order_key(self.last_evaluated_origin) and order_key(origin) <= order_key(self.last_evaluated_origin):
            return []
        # Evidenziare l'origine già valutata anche se non c'è alcun incrocio.
        self.last_evaluated_origin = origin
        target = V52LiveTracker._next_expected_key(current)
        if not target:
            return []
        if check_freshness:
            stamp = V52LiveTracker._draw_stamp(current)
            instant = clock or now_dt()
            if stamp is None or not (0 <= (instant-stamp).total_seconds() < 290):
                return []

        new_signals = [r for r in v52.plays if r.get('origin_key') == origin
                       and r.get('target_key') == target and r.get('status') == 'PENDING']
        if not new_signals:
            return []

        # Le origini V52 meno recenti devono avere un esito H1 certo.
        # Usa il più recente segnale di ciascuna delle altre cinque coppie,
        # anche se quel segnale più recente non ha prodotto un'ambata.
        past = {}
        for rec in v52.plays:
            rk = str(rec.get('target_key') or '')
            pair = tuple(sorted(int(x) for x in rec.get('pair', [])))
            if len(pair) != 2 or rec.get('origin_key') == origin:
                continue
            gap = self._target_gap(rk, target)
            if not gap or gap > V55_MAX_GAP_DRAWS:
                continue
            old = past.get(pair)
            if old is None or self._target_gap(str(old['target_key']), rk):
                past[pair] = rec
        if not past:
            return []

        rows_by_key = {str(r.get('key')): (i, r) for i, r in enumerate(history)}
        candidates = []
        recent80 = history[-80:]
        counter = Counter(n for r in recent80 for n in r.get('nums', []))
        for fresh in new_signals:
            newpair = tuple(sorted(int(x) for x in fresh.get('pair', [])))
            if len(newpair) != 2:
                continue
            for oldpair, oldrec in past.items():
                if oldpair == newpair or oldrec.get('status') != 'CLOSED':
                    continue
                oldkey = str(oldrec['target_key'])
                if oldkey not in rows_by_key:
                    continue
                gap = self._target_gap(oldkey, target)
                if not gap or gap > V55_MAX_GAP_DRAWS:
                    continue
                old_idx, olddraw = rows_by_key[oldkey]
                # Tutta la catena fra H1 precedente e origine corrente
                # deve essere reale e senza concorsi saltati.
                chain = history[old_idx:]
                if len(chain) != gap or not all(
                    V52LiveTracker._consecutive(a, b) for a,b in zip(chain, chain[1:])
                ):
                    continue
                old_base = set(int(n) for n in olddraw.get('nums', []))
                numbers_won = [n for n in oldpair if n in old_base]
                if len(numbers_won) != 1:
                    continue
                anchor = numbers_won[0]
                # SUM80, tie-break numerico crescente, come analisi_v55.py.
                partner = max(newpair, key=lambda n: (counter[anchor] + counter[n], -anchor, -n))
                cross = tuple(sorted((anchor, partner)))
                if cross[0] == cross[1]:
                    continue
                candidates.append((gap, self._pair_code(oldpair), self._pair_code(newpair),
                                   cross, anchor, partner, oldkey))
        if not candidates:
            return []
        # Politica V55: massimo UN incrocio per concorso target.
        # Priorità al primo segnale passato in ordine di distanza, poi coppia.
        gap, old_name, new_name, cross, anchor, partner, oldtarget = min(candidates)
        if any(str(r.get('target_key')) == target for r in self.plays):
            return []
        rec = {
            'id': f'V55|{origin}|{self._pair_code(cross)}',
            'origin_key': origin, 'target_key': target, 'day': target.split('#')[0],
            'old_target_key': oldtarget, 'old_pair': old_name, 'new_pair': new_name,
            'old_ambata_h1': anchor, 'new_partner_base80': partner,
            'gap_draws': gap, 'pair': list(cross), 'status': 'PENDING',
            'hit': None, 'prize': 0.0, 'stake': V55_STAKE_H1,
            'created_at': now_dt().isoformat(timespec='seconds'),
        }
        self.plays.append(rec)
        self.plays = self.plays[-12000:]
        return [
            '🚀 V55 INCROCIO SELETTIVO — AMBO LIVE H1\n'
            f'Prima coppia V52: {old_name} | al suo H1 è uscito SOLO {anchor:02d}\n'
            f'Seconda coppia V52: {new_name} | distanza {gap} colpi ({gap*5} minuti)\n'
            f'🎯 NUOVO AMBO: {self._pair_code(cross)}\n'
            f'Origine: {origin} | PROSSIMA ESTRAZIONE: {target}\n'
            'Un solo incrocio per concorso, €1 indicativo, H1 soltanto.\n'
            '⚠️ Strategia sperimentale; nessuna vincita garantita.'
        ]

    def report(self, history):
        closed = [r for r in self.plays if r.get('status') == 'CLOSED']
        hits = sum(r.get('hit') is True for r in closed)
        pending = sum(r.get('status') == 'PENDING' for r in self.plays)
        missing = sum(r.get('status') == 'MISSING' for r in self.plays)
        cost = sum(float(r.get('stake') or 0) for r in closed)
        prize = sum(float(r.get('prize') or 0) for r in closed)
        day = str(history[-1]['day']) if history else now_dt().date().isoformat()
        today = [r for r in self.plays if r.get('day') == day]
        last = self.plays[-1] if self.plays else {}
        return '\n'.join([
            '🚀 V55 — INCROCI SELETTIVI LIVE H1',
            f"Stato: {'ATTIVO' if V55_LIVE_ENABLED else 'SPENTO'} | warmup {len(history)}/900",
            'Regola: 1 ambata precedente H1 + 2° V52 entro 12 estrazioni; max 1 incrocio per concorso.',
            f'Forward dal: {self.start_key or "-"}',
            f'Totale {len(self.plays)} | chiusi {len(closed)} | HIT {hits}/{len(closed)} ({safe_pct(hits,len(closed)):.2f}%)',
            f'Pending {pending} | non verificabili {missing} | saldo teorico €{prize-cost:+.0f}',
            f'Oggi ({day}): {len(today)} segnali V55',
            f"Ultimo: {last.get('origin_key','-')} -> {last.get('target_key','-')} | "
            f"{self._pair_code(last['pair']) if last.get('pair') else '-'} | {last.get('status','-')}",
            '⚠️ V55 deriva da un test retrospettivo molto piccolo (2 HIT/21 nel 2025).',
        ])


def _merge_v55_state(a, b):
    aa = a if isinstance(a, dict) else {}
    bb = b if isinstance(b, dict) else {}
    if not aa and not bb:
        return None
    ranks = {'PENDING': 0, 'MISSING': 1, 'CLOSED': 2}
    records = {}
    for src in (aa, bb):
        for rec in src.get('plays') or []:
            if not isinstance(rec, dict) or not rec.get('target_key'):
                continue
            identity = str(rec['target_key'])  # un segnale V55 per concorso.
            old = records.get(identity)
            if old is None or ranks.get(str(rec.get('status')), -1) > ranks.get(str(old.get('status')), -1):
                records[identity] = dict(rec)
    plays = sorted(records.values(), key=lambda x: order_key(x.get('target_key')) or (-1,-1))[-12000:]
    return {
        'start_key': _key_min(aa.get('start_key'), bb.get('start_key')) or '',
        'last_evaluated_origin': _key_max(aa.get('last_evaluated_origin'), bb.get('last_evaluated_origin')) or '',
        'plays': plays,
        'rules_version': 'V55_OLD_ONE_HIT_NEXT_V52_WITHIN_12_SUM_BASE80_ONE_PER_TARGET_H1',
    }


# ============================================================
# V56 SUPER CORE — selettore LIVE, MAI seconda puntata duplicata.
# Primo V52 di ogni giorno + primo V28 ELITE di ogni giorno.
# V52/V28 originali restano attivi; V56 NOTIFICA la scelta, NON
# crea una giocata aggiuntiva e NON modifica i loro contatori.
# ============================================================
V56_KEY = "v56_super_core_live_forward_v1"
V56_LIVE_ENABLED = os.getenv("V56_LIVE_ENABLED", "1").strip().lower() not in {"0","off","no","false"}
V56_LIVE_NOTIFY = os.getenv("V56_LIVE_NOTIFY", "1").strip().lower() not in {"0","off","no","false"}
V56_STAKE_H1 = 1.0
V56_PRIZE_H1 = 14.0

class V56SuperCoreTracker:
    CHANNELS = ("V52_DAILY", "V28_ELITE")
    def __init__(self, data=None):
        d = data if isinstance(data, dict) else {}
        self.start_key = str(d.get('start_key') or '')
        self.last_evaluated_origin = str(d.get('last_evaluated_origin') or '')
        self.plays = [dict(r) for r in (d.get('plays') or []) if isinstance(r, dict) and r.get('target_key')][-5000:]
        self.blocked = {str(x) for x in d.get('blocked') or [] if isinstance(x,str)}

    def dump(self):
        return {
            'start_key': self.start_key,
            'last_evaluated_origin': self.last_evaluated_origin,
            'plays': self.plays[-5000:],
            'blocked': sorted(self.blocked)[-1200:],
            'rules_version': 'V56_CORE_FIRST_V52_DAILY_PLUS_FIRST_V28_ELITE_DAILY_H1',
        }

    def initialize(self, history, v52=None, v28=None):
        if not self.start_key and history:
            self.start_key = str(history[-1]['key'])
            self.last_evaluated_origin = self.start_key
            # Installando V56 a meta' giornata, NON e' corretto chiamare
            # "primo V52/V28 del giorno" un successivo segnale dei due
            # canali se il primo era gia' stato inviato prima del deploy.
            expected = V52LiveTracker._next_expected_key(history[-1])
            day = expected.split('#')[0] if expected else str(history[-1]['day'])
            if v52 is not None and any(str(r.get('target_key') or '').startswith(day+'#')
                                       for r in v52.plays):
                self.blocked.add(day+'|V52_DAILY')
            if v28 is not None:
                by_key={str(r['key']):r for r in history}
                for r in v28.signals:
                    if r.get('tier') != 'ELITE_70': continue
                    origin_row=by_key.get(str(r.get('origin_key') or ''))
                    if origin_row and str(V52LiveTracker._next_expected_key(origin_row) or '').startswith(day+'#'):
                        self.blocked.add(day+'|V28_ELITE')
                        break
            return True
        return False

    @staticmethod
    def _ptext(pair):
        return '-'.join(f'{int(n):02d}' for n in pair)

    def close_with_draw(self, newest, previous):
        out=[]
        current = str(newest.get('key') or '')
        for r in self.plays:
            if r.get('status') != 'PENDING':
                continue
            expected = str(r.get('target_key') or '')
            if not expected or not order_key(current) or not order_key(expected):
                continue
            if current == expected:
                if previous and V52LiveTracker._consecutive(previous, newest):
                    win = all(int(n) in set(newest['nums']) for n in r['pair'])
                    r.update(status='CLOSED', hit=win, result_key=current,
                             prize=V56_PRIZE_H1 if win else 0.0)
                    out.append(f"{'✅ HIT' if win else '❌ MISS'} — V56 SUPER CORE {r['channel']} H1\n"
                               f"AMBO {self._ptext(r['pair'])} | concorso {current}\n"
                               f"Netto simulato: €{(13 if win else -1):+d} | nessuna puntata aggiuntiva V56")
                else:
                    r.update(status='MISSING', hit=None, result_key=current, prize=0.0)
                    out.append(f"⚠️ V56 {r['channel']} H1 NON VERIFICABILE {self._ptext(r['pair'])} "
                               f"| concorso {expected}: continuità temporale assente")
            elif order_key(current) > order_key(expected):
                r.update(status='MISSING', hit=None, result_key=current, prize=0.0)
                out.append(f"⚠️ V56 {r['channel']} H1 NON VERIFICABILE | concorso "
                           f"{expected} non disponibile: nessun HIT retroattivo")
        return out

    def arm(self, history, v52, v28, clock=None, check_freshness=True):
        if not V56_LIVE_ENABLED or not history:
            return []
        if self.initialize(history):
            return []
        last=history[-1]
        origin=str(last.get('key') or '')
        if (not order_key(origin) or not order_key(self.start_key) or
                order_key(origin) <= order_key(self.start_key)):
            return []
        if (self.last_evaluated_origin and order_key(self.last_evaluated_origin) and
                order_key(origin) <= order_key(self.last_evaluated_origin)):
            return []
        self.last_evaluated_origin=origin
        expected=V52LiveTracker._next_expected_key(last)
        if not expected:
            return []
        # Non annunciare operazioni quando il dato e' gia' vecchio.
        if check_freshness:
            ts=V52LiveTracker._draw_stamp(last)
            instant=clock or now_dt()
            if ts is None or not (0 <= (instant-ts).total_seconds() < 290):
                return []
        day=expected.split('#')[0]
        existing={(str(r.get('day')),str(r.get('channel'))) for r in self.plays}
        candidates=[]
        # V52: usare SOLO previsioni appena emesse dal tracker LIVE.
        fresh_v52=[r for r in v52.plays if r.get('origin_key') == origin and
                   r.get('target_key') == expected and r.get('status') == 'PENDING']
        if (day,'V52_DAILY') not in existing and day+'|V52_DAILY' not in self.blocked and fresh_v52:
            # Priorita' congelata dello storico a parita' di concorso.
            priority={tuple(x[0]):i for i,x in enumerate(V52_RULES)}
            first=min(fresh_v52,key=lambda r: (priority.get(tuple(r['pair']),99),tuple(r['pair'])))
            candidates.append(('V52_DAILY', tuple(first['pair']), 'V52 MULTI'))
        # V28: solo tier ELITE, segnale creato ADESSO e tuttora pending.
        if ((day,'V28_ELITE') not in existing and day+'|V28_ELITE' not in self.blocked and
                isinstance(v28.pending,dict) and
                v28.pending.get('origin_key') == origin and
                v28.pending.get('tier') == 'ELITE_70' and
                any(r.get('origin_key') == origin and r.get('tier') == 'ELITE_70' for r in v28.signals)):
            pair=tuple(sorted((int(v28.pending['main']),int(v28.pending['partner']))))
            candidates.append(('V28_ELITE',pair,'V28 ELITE'))
        out=[]
        for channel,pair,source in candidates:
            if (day,channel) in existing:
                continue
            if any(str(r.get('target_key')) == expected and tuple(r.get('pair') or []) == pair
                   for r in self.plays):
                self.blocked.add(day+'|'+channel)
                continue  # Stesso ambo sullo stesso concorso: MAI due volte.
            record={
                'id':f'V56|{day}|{channel}', 'day':day,'channel':channel,
                'origin_key':origin,'target_key':expected,'pair':list(pair),
                'status':'PENDING','hit':None,'prize':0.0,'stake':V56_STAKE_H1,
                'result_key':None,'source':source,
                'created_at':now_dt().isoformat(timespec='seconds'),
            }
            self.plays.append(record)
            existing.add((day,channel))
            out.append(
                f'🏆 V56 SUPER CORE — SELEZIONE LIVE H1\n'
                f'Canale: {channel} | AMBO {self._ptext(pair)}\n'
                f'Origine: {origin} | PROSSIMO CONCORSO: {expected}\n'
                'Questo stesso ambo e già stato segnalato da '+source+'.\n'
                'NON è una seconda puntata: V56 lo seleziona e ne conta l’esito separatamente.\n'
                'Massimo 1 V52 e 1 V28 ELITE al giorno; nessuna progressione. '
                'Strategia sperimentale senza vincite garantite.'
            )
        self.plays=self.plays[-5000:]
        return out

    def report(self, history):
        closed=[r for r in self.plays if r.get('status')=='CLOSED']
        pending=[r for r in self.plays if r.get('status')=='PENDING']
        missing=[r for r in self.plays if r.get('status')=='MISSING']
        wins=sum(r.get('hit') is True for r in closed)
        total=float(sum(r.get('prize') or 0 for r in closed)) - sum(float(r.get('stake') or 0) for r in closed)
        day=str(history[-1]['day']) if history else now_dt().date().isoformat()
        today=[r for r in self.plays if r.get('day')==day]
        lines=['🏆 V56 SUPER CORE — 1 V52 DAILY + 1 V28 ELITE DAILY',
               f"Stato: {'LIVE' if V56_LIVE_ENABLED else 'OFF'} | Inizio forward: {self.start_key or '-'}",
               'Massimo 2 selezioni H1/giorno: NON sono giocate ulteriori rispetto a V52/V28.',
               f'Totale {len(self.plays)} | chiusi {len(closed)} | HIT {wins}/{len(closed)} '
               f'({safe_pct(wins,len(closed)):.2f}%) | pending {len(pending)} | NON VERIFICABILI {len(missing)}',
               f'Saldo virtuale delle sole selezioni chiuse: €{total:+.0f}',
               f'Oggi ({day}): {len(today)}/2 canali emessi']
        for name in self.CHANNELS:
            rows=[r for r in closed if r['channel']==name]
            hit=sum(r.get('hit') is True for r in rows)
            lines.append(f'• {name}: {hit}/{len(rows)} HIT | €{14*hit-len(rows):+d}')
        last=self.plays[-1] if self.plays else None
        if last:
            lines.append(f"Ultimo: {last['channel']} | {self._ptext(last['pair'])} "
                         f"{last['origin_key']} → {last['target_key']} | {last['status']}")
        lines.append('⚠️ Backtest 2025 retrospettivo e selezionato dopo ricerca; redditività futura non dimostrata.')
        return '\n'.join(lines)


def _merge_v56_state(a,b):
    aa=a if isinstance(a,dict) else {}
    bb=b if isinstance(b,dict) else {}
    if not aa and not bb:
        return None
    statuses={'PENDING':0,'MISSING':1,'CLOSED':2}
    records={}
    for src in (aa,bb):
        for r in src.get('plays') or []:
            if not isinstance(r,dict):continue
            day=str(r.get('day') or '')
            channel=str(r.get('channel') or '')
            if not day or channel not in V56SuperCoreTracker.CHANNELS:continue
            identity=(day,channel)
            old=records.get(identity)
            if old is None or statuses.get(r.get('status'),-1)>statuses.get(old.get('status'),-1):
                records[identity]=dict(r)
    rows=sorted(records.values(),key=lambda r:(r['day'],r['channel']))[-5000:]
    return {
        'start_key':_key_min(aa.get('start_key'),bb.get('start_key')) or '',
        'last_evaluated_origin':_key_max(aa.get('last_evaluated_origin'),bb.get('last_evaluated_origin')) or '',
        'plays':rows,
        'blocked':sorted(set(aa.get('blocked') or []).union(bb.get('blocked') or []))[-1200:],
        'rules_version':'V56_CORE_FIRST_V52_DAILY_PLUS_FIRST_V28_ELITE_DAILY_H1'
    }



# ============================================================
# V67 DAILY — V66 H1 16:00, dopo MISS primo V52 successivo
# MONITORAGGIO PROSPETTICO: ogni record usa SOLO concorsi noti.
# Nessun acquisto o raddoppio: seconda selezione V52 non e' un
# secondo acquisto oltre all'eventuale segnale gia' inviato da V52.
# ============================================================
V67_KEY = 'v67_v66_1600_v52_after_miss_forward_v1'
V67_ENABLED = os.getenv('V67_ENABLED', '1').strip().lower() not in {'0','no','false','off'}
V67_NOTIFY = os.getenv('V67_NOTIFY', '1').strip().lower() not in {'0','no','false','off'}
V67_MODE = os.getenv('V67_MODE', 'SHADOW').strip().upper()  # LIVE = etichetta operativa, non acquista nulla
V67_FIXED_PAIRS = ((44,59),(15,78),(78,89),(46,57),(7,36),
                   (12,52),(22,64),(59,61),(57,80),(36,58))
V67_COOC_WINDOW = 320
V67_MIN_WARMUP = 900
V67_RULES_VERSION = 'V67_V66_1600_FIRST_V52_AFTER_MISS_H1_FIXED'


class V67DailyTracker:
    def __init__(self, data=None):
        d=data if isinstance(data,dict) else {}
        self.start_key=str(d.get('start_key') or '')
        self.blocked_days=set(str(x) for x in (d.get('blocked_days') or []) if x)
        self.plays=[dict(r) for r in (d.get('plays') or []) if isinstance(r,dict) and r.get('day')][-1200:]
        self.plays.sort(key=lambda r:r.get('day',''))

    def dump(self):
        return {'start_key':self.start_key,'blocked_days':sorted(self.blocked_days)[-1200:],
                'plays':self.plays[-1200:],'rules_version':V67_RULES_VERSION}

    def initialize(self, history):
        if self.start_key or not history:return False
        # Sul deploy NON ricostruiamo ne' selezioniamo la prima 16:00
        # della giornata in corso; si parte dalla giornata successiva.
        last=history[-1]
        self.start_key=str(last.get('key') or '')
        self.blocked_days.add(str(last.get('day') or ''))
        return True

    @staticmethod
    def _pair_txt(pair):
        return '-'.join(f'{int(n):02d}' for n in pair)

    @staticmethod
    def _stamp(row):
        return V52LiveTracker._draw_stamp(row)

    def _eligible_primary(self, history):
        if len(history)<V67_MIN_WARMUP:return None
        last=history[-1]
        stamp=self._stamp(last)
        if not stamp or (stamp.hour,stamp.minute)!=(15,55):return None
        day=str(last['day'])
        today=[r for r in history if str(r.get('day'))==day]
        row14=next((r for r in reversed(today) if self._stamp(r) and
                    (self._stamp(r).hour,self._stamp(r).minute)==(14,0)),None)
        if not row14:return None
        interval=[r for r in today if self._stamp(r) and
                  self._stamp(row14)<=self._stamp(r)<=stamp]
        if len(interval)!=24 or interval[0].get('key')!=row14.get('key') or interval[-1].get('key')!=last.get('key'):
            return None
        if not all(V52LiveTracker._consecutive(a,b) for a,b in zip(interval,interval[1:])):
            return None
        recent=history[-V67_COOC_WINDOW:]
        if any(len(r.get('nums') or [])!=20 or len(set(r['nums']))!=20 for r in recent):return None
        if len(row14.get('nums') or [])!=20:return None
        left=V67_FIXED_PAIRS[sum(int(n) for n in last['nums'])%10]
        right=V67_FIXED_PAIRS[sum(int(n) for n in row14['nums'])%10]
        def cooc(pair):return sum(all(int(n) in set(r['nums']) for n in pair) for r in recent)
        ca,cb=cooc(left),cooc(right)
        chosen=left if ca>=cb else right
        return {'pair':list(chosen),'v59':list(left),'v61':list(right),
                'sum_1555':sum(last['nums']),'sum_1400':sum(row14['nums']),
                'cooc_v59':ca,'cooc_v61':cb}

    def close_with_draw(self, newest,previous):
        out=[];key=str(newest.get('key') or '')
        for r in self.plays:
            for stage in ('primary','backup'):
                if r.get(stage+'_status')!='PENDING':continue
                target=str(r.get(stage+'_target_key') or '')
                if not target or not order_key(target) or not order_key(key):continue
                if order_key(key)<order_key(target):continue
                if key==target and previous and V52LiveTracker._consecutive(previous,newest):
                    hit=all(n in set(newest['nums']) for n in r[stage+'_pair'])
                    r[stage+'_status']='CLOSED';r[stage+'_hit']=hit
                    r[stage+'_result_key']=key
                    if stage=='primary':
                        r['backup_status']='NOT_NEEDED' if hit else 'WAITING'
                    out.append(f"{'✅ HIT' if hit else '❌ MISS'} — V67 {stage.upper()} H1 | "
                               f"{self._pair_txt(r[stage+'_pair'])} | concorso {key} | "
                               f"{'+13€ teorici' if hit and stage=='primary' else '+12€ giornalieri teorici' if hit else '-1€ teorico' if stage=='primary' else '-2€ giornalieri teorici'}")
                    if stage=='primary' and not hit:
                        out.append('🔎 V67: primo ambo delle 16:00 perso. Attendo il primo V52 successivo valido e DIVERSO, senza obbligo di giocare.')
                else:
                    r[stage+'_status']='MISSING';r[stage+'_hit']=None;r[stage+'_result_key']=key
                    if stage=='primary':r['backup_status']='NOT_NEEDED'
                    out.append(f'⚠️ V67 {stage.upper()} NON VERIFICABILE: concorso {target} mancante/non consecutivo; nessun HIT assegnato')
        return out

    def arm(self,history,v52,clock=None,check_freshness=True):
        if not V67_ENABLED or not history:return []
        if self.initialize(history):return []
        latest=history[-1]
        origin=str(latest.get('key') or '')
        if not order_key(origin) or not order_key(self.start_key) or order_key(origin)<=order_key(self.start_key):return []
        ts=self._stamp(latest);now=clock or now_dt()
        # Nessun backfill/catch-up: segnale emesso solo se il dato e' fresco.
        if check_freshness and (ts is None or not (0<=(now-ts).total_seconds()<290)):return []
        day=str(latest.get('day') or '')
        if not day or day in self.blocked_days:return []
        prior=next((x for x in self.plays if x.get('day')==day),None)
        target=V52LiveTracker._next_expected_key(latest)
        if not target or target.split('#')[0]!=day:return []
        if prior is None:
            prediction=self._eligible_primary(history)
            if not prediction:return []
            record={
                'id':'V67|'+day, 'day':day,
                'primary_origin_key':origin,'primary_target_key':target,
                'primary_pair':prediction['pair'],'primary_status':'PENDING',
                'primary_hit':None,'primary_result_key':None,
                'backup_status':'NOT_NEEDED','backup_hit':None,
                'backup_pair':None,'backup_target_key':None,
                'v59_pair':prediction['v59'],'v61_pair':prediction['v61'],
                'cooc_v59':prediction['cooc_v59'],'cooc_v61':prediction['cooc_v61'],
                'sum_1555':prediction['sum_1555'],'sum_1400':prediction['sum_1400'],
            }
            self.plays.append(record)
            self.plays=self.plays[-1200:]
            return [
                f'🎯 V67 {V67_MODE} — PRIMO AMBO H1 DELLE 16:00\n'
                f'V66: {self._pair_txt(record["primary_pair"])} | previsione {target}\n'
                f'V59 {self._pair_txt(record["v59_pair"])} (cooc320={record["cooc_v59"]}) · '
                f'V61 {self._pair_txt(record["v61_pair"])} (cooc320={record["cooc_v61"]})\n'
                'Se HIT: STOP giornata. Se MISS: attendo il primo V52 DOPO le 16:00 su coppia diversa.\n'
                '€1 indicativo H1 per segnale, niente progressione, nessun acquisto automatico.'
            ]
        if prior.get('primary_status')!='CLOSED' or prior.get('primary_hit') is not False:return []
        if prior.get('backup_status')!='WAITING':return []
        if ts is None or (ts.hour,ts.minute)<=(16,0):return []
        # Selezionare solamente le proposte V52 appena emesse, non ricalcolarle.
        pending=[r for r in v52.plays if r.get('origin_key')==origin and
                 r.get('target_key')==target and r.get('status')=='PENDING' and
                 tuple(sorted(int(x) for x in (r.get('pair') or [])))!=tuple(sorted(prior['primary_pair']))]
        if not pending:return []
        priority={tuple(x[0]):i for i,x in enumerate(V52_RULES)}
        first=min(pending,key=lambda r:(priority.get(tuple(r['pair']),99),tuple(r['pair'])))
        prior.update(backup_origin_key=origin,backup_target_key=target,
                     backup_pair=list(first['pair']),backup_status='PENDING',backup_hit=None,
                     backup_result_key=None)
        return [
            f'🔎 V67 {V67_MODE} — SECONDO AMBO DOPO MISS V66\n'
            f'Prima coppia {self._pair_txt(prior["primary_pair"])} → MISS alle 16:00\n'
            f'Seconda coppia V52 {self._pair_txt(first["pair"])} | TARGET {target} | SOLO H1\n'
            'Questa coppia e già segnalata da V52: NON effettuare una puntata aggiuntiva V67.\n'
            'Dopo H1 STOP giornaliero in ogni caso; €1 teorico, nessuna progressione.'
        ]

    def report(self,history):
        checked=[r for r in self.plays if r.get('primary_status')=='CLOSED']
        win1=sum(r.get('primary_hit') is True for r in checked)
        backups=[r for r in self.plays if r.get('backup_status')=='CLOSED']
        win2=sum(r.get('backup_hit') is True for r in backups)
        stakes=len(checked)+len(backups)
        # Nei saldi non contare backup pending o concorsi non verificabili.
        net=14*(win1+win2)-stakes
        missing=sum(r.get('primary_status')=='MISSING' or r.get('backup_status')=='MISSING' for r in self.plays)
        day=str(history[-1].get('day') or '') if history else now_dt().date().isoformat()
        r=next((x for x in self.plays if x.get('day')==day),None)
        lines=[
            '🎯 V67 — V66 ORE 16:00 + PRIMO V52 DOPO MISS',
            f'Modalità: {V67_MODE} | Forward da {self.start_key or "-"} | warmup {len(history)}/900',
            f'Giornate {len(self.plays)} | V66 H1: {win1}/{len(checked)} | backup V52 H1: {win2}/{len(backups)}',
            f'Saldo teorico delle sole selezioni verificate: €{net:+d} | NON verificabili {missing}',
            'Una previsione V66 al giorno; secondo V52 soltanto dopo MISS e su un ambo diverso.',
            'V52 continua a notificare tutti i propri segnali. V67 non aggiunge una seconda puntata.',
        ]
        if r:
            lines.append(f'Oggi {day}: V66 {self._pair_txt(r["primary_pair"])} = {r["primary_status"]}'
                         f' | V52 backup {r.get("backup_status") or "-"}'
                         + (f' {self._pair_txt(r["backup_pair"])}' if r.get('backup_pair') else ''))
        else:lines.append(f'Oggi {day}: nessuna previsione V67' + (' (installazione in giornata: avvio prossimo giorno)' if day in self.blocked_days else ''))
        lines.append('Sperimentale: i risultati 2025 sono retrospettivi, non garanzia di utili.')
        return '\n'.join(lines)


def _merge_v67_state(a,b):
    aa=a if isinstance(a,dict) else {}
    bb=b if isinstance(b,dict) else {}
    if not aa and not bb:return None
    scores={'NOT_NEEDED':0,'WAITING':1,'PENDING':2,'MISSING':3,'CLOSED':4}
    merged={}
    for src in (aa,bb):
        for r in src.get('plays') or []:
            if not isinstance(r,dict) or not r.get('day'):continue
            day=str(r['day'])
            existing=merged.get(day)
            if existing is None:merged[day]=dict(r);continue
            # L'avanzamento di una fase non deve far regredire l'altra.
            for stage in ('primary','backup'):
                k=stage+'_status'
                if scores.get(r.get(k),-1)>scores.get(existing.get(k),-1):
                    for fld,v in r.items():
                        if fld.startswith(stage+'_'):existing[fld]=v
            for k,v in r.items():
                if k not in existing or existing[k] is None:existing[k]=v
    return {'start_key':_key_min(aa.get('start_key'),bb.get('start_key')) or '',
            'blocked_days':sorted(set(aa.get('blocked_days') or []).union(bb.get('blocked_days') or []))[-1200:],
            'plays':sorted(merged.values(),key=lambda r:r['day'])[-1200:],
            'rules_version':V67_RULES_VERSION}


# ============================================================
# V70 DAILY — Incrocio V69 tripla Base+ V59 coppia fissa, H1
# Stesso concorso di origine, DUE simulazioni SEPARATE, niente
# giocata automatica e niente segnali retroattivi. Studio
# esplorativo V69/V70 2025, non una conferma indipendente.
# ============================================================
V70_KEY = 'v70_triplet_v59_same_sum_daily_forward_v1'
V70_ENABLED = os.getenv('V70_ENABLED', '1').strip().lower() not in {'0','false','no','off'}
V70_NOTIFY = os.getenv('V70_NOTIFY', '1').strip().lower() not in {'0','false','no','off'}
V70_MODE = 'SHADOW'  # non vi sono acquisti / puntate automatiche
V70_MIN_WARMUP = 900
V70_REPEAT_LAG = 12
V70_RULES_VERSION = 'V70_2_INDEPENDENT_TICKETS_MOD90_REPEAT12_FROM0800_H1'


class V70DailyTracker:
    """Prima origine >=08:00 con resto modulo 90 ripetuto negli ultimi 12
    concorsi consecutivi. Non altera le regole/stato del tracker V67.
    """
    def __init__(self, data=None):
        d = data if isinstance(data, dict) else {}
        self.start_key = str(d.get('start_key') or '')
        self.blocked_days = set(str(x) for x in (d.get('blocked_days') or []) if x)
        self.plays = [dict(r) for r in (d.get('plays') or []) if isinstance(r, dict) and r.get('day')][-1200:]
        self.plays.sort(key=lambda r: str(r.get('day') or ''))

    def dump(self):
        return {'start_key':self.start_key, 'blocked_days':sorted(self.blocked_days)[-1200:],
                'plays':self.plays[-1200:], 'rules_version':V70_RULES_VERSION}

    def initialize(self, history):
        if self.start_key or not history: return False
        latest = history[-1]
        self.start_key = str(latest.get('key') or '')
        self.blocked_days.add(str(latest.get('day') or ''))
        return True

    @staticmethod
    def formula(nums):
        if len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= int(x) <= 90 for x in nums):
            return None
        total = sum(int(x) for x in nums)
        reduced = ((total - 1) % 90) + 1
        trip = (reduced, 90 - reduced, 91 - reduced)
        # n=45 produce duplicato, n=90 produce lo 0 (inammissibile).
        if len(set(trip)) != 3 or not all(1 <= t <= 90 for t in trip):
            return None
        ambo = V67_FIXED_PAIRS[total % 10]
        return {'sum':total, 'reduced':reduced, 'last_digit':total%10,
                'triplet':list(trip), 'ambo':list(ambo)}

    @classmethod
    def _eligible(cls, history):
        if len(history) < V70_MIN_WARMUP: return None
        last = history[-1]
        stamp = V52LiveTracker._draw_stamp(last)
        if stamp is None or (stamp.hour,stamp.minute) < (8,0): return None
        formula = cls.formula(last.get('nums') or [])
        if formula is None: return None
        # Solo righe realmente consecutive, mai rimpiazzare concorsi mancanti.
        # La ricorrenza si puo' trovare in uno qualsiasi degli ultimi 12 draw;
        # per ogni lag verifichiamo TUTTI i passi fino a quel concorso.
        recent = history[-(V70_REPEAT_LAG+1):]
        if len(recent) != V70_REPEAT_LAG+1: return None
        for lag in range(1,V70_REPEAT_LAG+1):
            chain = recent[-lag-1:]
            if not all(V52LiveTracker._consecutive(a,b) for a,b in zip(chain,chain[1:])):
                continue
            # ATTENZIONE: il resto precedente puo' essere 45/90, quindi
            # confronto solo il modulo 90 dalla somma, anche se tripletta
            # precedente invalida. Uso somma direttamente e non formula().
            nums = chain[0].get('nums') or []
            if len(nums)!=20 or len(set(nums))!=20: continue
            if ((sum(int(x) for x in nums)-1)%90)+1 == formula['reduced']:
                formula['repeat_lag'] = lag
                return formula
        return None

    def arm(self, history, clock=None, check_freshness=True):
        if not V70_ENABLED or not history: return []
        if self.initialize(history): return []
        last = history[-1]
        origin = str(last.get('key') or '')
        if not order_key(origin) or not order_key(self.start_key) or order_key(origin)<=order_key(self.start_key):return []
        stamp = V52LiveTracker._draw_stamp(last)
        now = clock or now_dt()
        if check_freshness and (stamp is None or not (0 <= (now-stamp).total_seconds() < 290)):
            return []
        day = str(last.get('day') or '')
        if not day or day in self.blocked_days or any(str(r.get('day'))==day for r in self.plays):return []
        calc = self._eligible(history)
        if calc is None:return []
        target = V52LiveTracker._next_expected_key(last)
        if not target or target.split('#')[0]!=day:return []
        item = {'id':'V70|'+day,'day':day,'origin_key':origin,'target_key':target,
                'status':'PENDING','result_key':None,'sum':calc['sum'],
                'reduced':calc['reduced'],'last_digit':calc['last_digit'],
                'repeat_lag':calc['repeat_lag'],'ambo':calc['ambo'],
                'triplet':calc['triplet'],'ambo_hit':None,'triplet_hits':None,
                'gross_ambo':None,'gross_triplet':None}
        self.plays.append(item)
        self.plays=self.plays[-1200:]
        return [
            f'🔢 V70 {V70_MODE} — RIPETIZIONE SOMMA BASE | H1\n'
            f'Origine {origin} | somma {item["sum"]} | resto90 {item["reduced"]} '
            f'(ritornato dopo {item["repeat_lag"]} estrazioni)\n'
            f'🎯 AMBO V59: {V67DailyTracker._pair_txt(item["ambo"])} '
            f'(ultima cifra {item["last_digit"]})\n'
            f'🎯 TRIPLETTA V69: {V67DailyTracker._pair_txt(item["triplet"])}\n'
            f'Verifica SOLO prossimo concorso {target}. Entrambi calcolati da identica somma; '
            'NON sono conferme indipendenti. Due simulazioni separate da €1 ciascuna; '
            'nessuna giocata automatica. Metodo esplorativo.'
        ]

    def close_with_draw(self, newest, previous):
        out=[]
        key=str(newest.get('key') or '')
        kn=order_key(key)
        if not kn:return out
        for r in self.plays:
            if r.get('status')!='PENDING':continue
            kt=order_key(str(r.get('target_key') or ''))
            if kt is None or kn < kt:continue
            if key==str(r.get('target_key')) and previous and V52LiveTracker._consecutive(previous,newest):
                ns=set(newest.get('nums') or [])
                if len(ns)!=20 or not all(1<=int(n)<=90 for n in ns):
                    r['status']='MISSING'
                    r['result_key']=key
                    out.append(f'⚠️ V70 H1 non verificabile: 20 Base mancanti/anomali al {key}.')
                    continue
                ah=all(n in ns for n in r['ambo'])
                th=sum(n in ns for n in r['triplet'])
                g2=14 if ah else 0
                g3=45 if th==3 else (2 if th==2 else 0)
                r.update(status='CLOSED',result_key=key,ambo_hit=bool(ah),triplet_hits=th,
                         gross_ambo=g2,gross_triplet=g3)
                out.append(
                    f"{'✅' if ah else '❌'} V70 AMBO H1 {V67DailyTracker._pair_txt(r['ambo'])} "
                    f"| {'HIT' if ah else 'MISS'} | €{g2-1:+d} teorici\n"
                    f"{'✅' if th>=2 else '❌'} V70 TRIPLETTA H1 {V67DailyTracker._pair_txt(r['triplet'])} "
                    f'| {th}/3 | €{g3-1:+d} teorici\n'
                    f'Totale due simulazioni: €{g2+g3-2:+d}. '
                    'Nessun raddoppio o prolungamento H2–H5.'
                )
            else:
                r['status']='MISSING';r['result_key']=key
                out.append(f'⚠️ V70 H1 non verificabile: atteso {r.get("target_key")}, ricevuto {key}; nessun HIT attribuito.')
        return out

    def report(self, history):
        closed=[p for p in self.plays if p.get('status')=='CLOSED']
        missed=[p for p in self.plays if p.get('status')=='MISSING']
        ah=sum(p.get('ambo_hit') is True for p in closed)
        prizes=sum((p.get('triplet_hits') or 0)>=2 for p in closed)
        terni=sum(p.get('triplet_hits')==3 for p in closed)
        g2=sum(int(p.get('gross_ambo') or 0) for p in closed)
        g3=sum(int(p.get('gross_triplet') or 0) for p in closed)
        n=len(closed)
        day=str(history[-1].get('day')) if history else now_dt().date().isoformat()
        today=next((p for p in self.plays if p.get('day')==day), None)
        res=[f'🔢 V70 DAILY {V70_MODE} — V59 AMBO + V69 TRIPLETTA',
             f'Start forward: {self.start_key or "-"} | warmup {len(history)}/{V70_MIN_WARMUP}',
             f'Segnali: {len(self.plays)} | completati: {n} | non verificabili: {len(missed)}',
             f'Ambo V59 H1: {ah}/{n}, saldo teorico €{g2-n:+d}',
             f'Tripletta V69 H1: {prizes}/{n} premi, {terni} terni, saldo teorico €{g3-n:+d}',
             f'Due schedine virtuali da €1: netto teorico €{g2+g3-2*n:+d}',
             'Solo prima ripetizione del resto90 entro 12 concorsi dopo le 08:00; STOP H1.',
             'V70 non modifica V67: eventuali coppie in comune NON sono nuove puntate. Risultati storici non garantiti.']
        if today:
            res.append(f'Oggi {day}: {today["status"]} | ambo {V67DailyTracker._pair_txt(today["ambo"])} '
                       f'| terna {V67DailyTracker._pair_txt(today["triplet"])} '
                       f'| target {today["target_key"]}')
        else:res.append(f'Oggi {day}: nessun segnale V70' + (' (installazione: inizio domani)' if day in self.blocked_days else ''))
        return '\n'.join(res)


def _merge_v70_state(a,b):
    aa=a if isinstance(a,dict) else {}
    bb=b if isinstance(b,dict) else {}
    if not aa and not bb:return None
    score={'PENDING':0,'MISSING':1,'CLOSED':2}
    result={}
    for state in (aa,bb):
        for r in state.get('plays') or []:
            if not isinstance(r,dict) or not r.get('day'):continue
            k=str(r['day'])
            old=result.get(k)
            if old is None or score.get(r.get('status'),-1)>score.get(old.get('status'),-1):result[k]=dict(r)
    return {'start_key':_key_min(aa.get('start_key'),bb.get('start_key')) or '',
            'blocked_days':sorted(set(aa.get('blocked_days') or []).union(bb.get('blocked_days') or []))[-1200:],
            'plays':sorted(result.values(),key=lambda r:r['day'])[-1200:],
            'rules_version':V70_RULES_VERSION}

# ============================================================
# V72 DAILY SHADOW — coppie distanza 5 entro stessa decina
# Formula congelata dal test esplorativo V72. UN AMBO H1/GIORNO.
# Ritardi cumulativi aggiornati soltanto da estrazioni osservate.
# ============================================================
V72_KEY = 'v72_decine_cross_max_delay_daily_shadow_v1'
V72_ENABLED = os.getenv('V72_ENABLED', '1').lower() not in {'0','false','no','off'}
V72_NOTIFY = os.getenv('V72_NOTIFY', '1').lower() not in {'0','false','no','off'}
V72_RULES_VERSION = 'V72_SAME_DECADE_CROSS_MAX_SUM_DELAY_H1_V1'

class V72DailyTracker:
    STARTS = tuple(n for n in range(1,86) if n//10 == (n+5)//10)
    def __init__(self,data=None):
        d=data if isinstance(data,dict) else {}
        self.start_key=str(d.get('start_key') or '')
        self.blocked_days=set(d.get('blocked_days') or [])
        self.plays=[dict(v) for v in (d.get('plays') or []) if isinstance(v,dict) and v.get('day')][-1200:]
        self.last_seen={int(k):int(v) for k,v in (d.get('last_seen') or {}).items() if str(k).isdigit() and str(v).isdigit()}
        self.index=int(d.get('index') or 0)
        self.last_observed_key=str(d.get('last_observed_key') or '')
        self.partial_history=bool(d.get('partial_history',True))
    def dump(self):
        return {'start_key':self.start_key,'blocked_days':sorted(self.blocked_days)[-1200:],
                'plays':self.plays[-1200:], 'last_seen':{str(k):v for k,v in self.last_seen.items()},
                'index':self.index,'last_observed_key':self.last_observed_key,
                'partial_history':self.partial_history,'rules_version':V72_RULES_VERSION}
    def observe(self,row):
        key=str(row.get('key') or '')
        if not key or (self.last_observed_key and order_key(key)<=order_key(self.last_observed_key)):
            return False
        nums=row.get('nums') or []
        if len(nums)!=20 or len(set(nums))!=20 or not all(1<=int(n)<=90 for n in nums):return False
        self.index+=1
        for num in nums:self.last_seen[int(num)]=self.index
        self.last_observed_key=key
        return True
    def initialize(self,history):
        if self.start_key or not history:return False
        # Bootstrap solo sullo storico disponibile, nessun replay di segnali.
        for row in history:self.observe(row)
        last=history[-1]
        self.start_key=str(last.get('key') or '')
        self.blocked_days.add(str(last.get('day') or ''))
        return True
    def candidate(self,nums):
        if len(nums)!=20 or len(set(nums))!=20:return None
        base=set(nums)
        roots=[a for a in self.STARTS if a in base and (a+5) in base]
        if len(roots)<2:return None
        best=None
        from itertools import combinations
        for a,b in combinations(roots,2):
            x=((a+b-1)%90)+1
            y=((a+b+9)%90)+1
            v=90-y;u=90-x
            quartet=(x,y,v,u)
            if min(quartet)<1 or len(set(quartet))!=4:continue
            # Formula storica: al momento dell'origine, ritardi PRIMA
            # dell'aggiornamento con i numeri della stessa estrazione.
            score=sum(self.index-self.last_seen.get(n,-1) for n in quartet)
            key=(-score,a,b)
            if best is None or key<best[0]:best=(key,a,b,quartet,score)
        if best is None:return None
        _,a,b,quartet,score=best
        return {'pairs':[[a,a+5],[b,b+5]],'quad':list(quartet),
                'ambo':[quartet[0],quartet[2]],'score':score}
    def arm(self,history,clock=None,check_freshness=True):
        if not V72_ENABLED or not history:return []
        if self.initialize(history):return []
        last=history[-1];key=str(last.get('key') or '')
        if not key or not self.start_key or order_key(key)<=order_key(self.start_key):return []
        stamp=V52LiveTracker._draw_stamp(last);now=clock or now_dt()
        if check_freshness and (stamp is None or not 0 <= (now-stamp).total_seconds()<290):return []
        day=str(last.get('day') or '')
        # Prima si genera, poi si osserva l'origine; stato causale.
        if self.last_observed_key==key:return []
        already=day in self.blocked_days or any(r.get('day')==day for r in self.plays)
        calc=None if already else self.candidate(last.get('nums') or [])
        self.observe(last)
        if calc is None:return []
        target=V52LiveTracker._next_expected_key(last)
        if not target or target.split('#')[0]!=day:return []
        item={'id':'V72|'+day,'day':day,'origin_key':key,'target_key':target,
              'status':'PENDING','pairs':calc['pairs'],'quad':calc['quad'],
              'ambo':calc['ambo'],'score':calc['score'],'hit':None,'gross':None}
        self.plays.append(item);self.plays=self.plays[-1200:]
        pairs=' + '.join(V67DailyTracker._pair_txt(p) for p in item['pairs'])
        return [f'🎯 V72 SHADOW — AMBO CROSS H1\nOrigine {key} | coppie {pairs}\n'
                f'Quaterna: {V67DailyTracker._pair_txt(item["quad"])}\n'
                f'AMBO: {V67DailyTracker._pair_txt(item["ambo"])} | somma ritardi {item["score"]}\n'
                f'Verifica al prossimo concorso {target}. 1 sola simulazione da €1; nessuna giocata automatica.']
    def close_with_draw(self,newest,previous):
        out=[];key=str(newest.get('key') or ''); kn=order_key(key)
        if kn is None:return out
        for r in self.plays:
            if r.get('status')!='PENDING':continue
            kt=order_key(r.get('target_key'))
            if kt is None or kn<kt:continue
            if key==r['target_key'] and previous and V52LiveTracker._consecutive(previous,newest):
                nums=set(newest.get('nums') or [])
                if len(nums)==20 and all(1<=int(n)<=90 for n in nums):
                    hit=all(n in nums for n in r['ambo']);gross=14 if hit else 0
                    r.update(status='CLOSED',result_key=key,hit=bool(hit),gross=gross)
                    out.append(f'{"✅" if hit else "❌"} V72 AMBO H1 {V67DailyTracker._pair_txt(r["ambo"])} '
                               f'| {"HIT" if hit else "MISS"} | €{gross-1:+d} virtuali')
                    continue
            r.update(status='MISSING',result_key=key)
            out.append(f'⚠️ V72 H1 non verificabile per {r["target_key"]}; nessun HIT attribuito.')
        return out
    def report(self,history):
        closed=[r for r in self.plays if r.get('status')=='CLOSED']
        won=sum(r.get('hit') is True for r in closed)
        day=str(history[-1].get('day')) if history else now_dt().date().isoformat()
        today=next((r for r in self.plays if r.get('day')==day),None)
        return ('🎯 V72 DAILY SHADOW — COPPIE NELLA STESSA DECINA\n'
                f'Primo giorno attivo dopo installazione: {self.start_key or "-"}\n'
                f'Segnali {len(self.plays)}, chiusi {len(closed)}, HIT {won}, '
                f'netto ipotetico €{14*won-len(closed):+d}\n'
                f'Ultima osservazione {self.last_observed_key or "-"}; ritardi da dati locali disponibili.\n'
                f'Oggi: {today["status"]+" "+V67DailyTracker._pair_txt(today["ambo"]) if today else "nessun segnale"}\n'
                'Un ambo H1 al giorno, quando esiste segnale; solo monitoraggio.')

def _merge_v72_state(a,b):
    aa=a if isinstance(a,dict) else {};bb=b if isinstance(b,dict) else {}
    if not aa and not bb:return None
    # Gli accumuli last_seen vanno presi dal ramo più avanzato.
    newest=max((aa,bb),key=lambda d:(int(d.get('index') or 0),order_key(d.get('last_observed_key')) or (-1,-1)))
    records={};rank={'PENDING':0,'MISSING':1,'CLOSED':2}
    for src in (aa,bb):
        for r in src.get('plays') or []:
            if not isinstance(r,dict) or not r.get('day'):continue
            old=records.get(r['day'])
            if old is None or rank.get(r.get('status'),-1)>rank.get(old.get('status'),-1):records[r['day']]=dict(r)
    merged=dict(newest)
    merged['start_key']=_key_min(aa.get('start_key'),bb.get('start_key')) or ''
    merged['blocked_days']=sorted(set(aa.get('blocked_days') or [])|set(bb.get('blocked_days') or []))[-1200:]
    merged['plays']=sorted(records.values(),key=lambda r:r['day'])[-1200:]
    merged['rules_version']=V72_RULES_VERSION
    return merged

# ============================================================
# V27 ELITE + STANDARD — AUTO WARMUP / SOLO FORWARD
# Stato aggiuntivo nello stesso JSON HARD LOCK, nessun reset legacy.
# ============================================================
V27_HISTORY_REQUIRED = 900
V27_MIN_HISTORY = 320
V27_KEY = "v27_elite_standard_forward_v1"
# V28 adds one AMBO H1 to each new V27 signal; existing V27 predictions unchanged.
V28_KEY = "v28_ambo_v27_momentum_forward_v1"
V28_PRIZE_H1 = 14.0
V28_STAKE_H1 = 1.0

# V38 — MONITORAGGIO FORWARD H1, due policy indipendenti CONTROL (6) e ACTIVE (8).
# Tutte le puntate sono solo virtuali, NON acquistano giocate reali.
V38_KEY = "v38_daily_ambo_shadow_forward_v1"
V38_PRIZE_H1 = 14.0
V38_STAKE_H1 = 1.0
V38_METHODS = ("A_BASE2", "A2_BASE1", "A2_BASE2", "V28_ELITE", "V28_STANDARD")
V38_CAPS = {"CONTROL": 6, "ACTIVE": 8}
V38_NOTIFY = os.getenv("V38_NOTIFY", "1").strip().lower() not in {"0", "no", "false", "off"}

# V52 MULTI — LIVE Telegram (mai acquisto automatico di schedine).
# Regole congelate, deriva da ricerca retrospettiva 2025: NON vantaggio dimostrato.
V52_KEY = "v52_combinata_primo_cronologico_live_forward_v1"
V52_LIVE_ENABLED = os.getenv("V52_LIVE_ENABLED", "1").strip().lower() not in {"0", "no", "false", "off"}
V52_LIVE_NOTIFY = os.getenv("V52_LIVE_NOTIFY", "1").strip().lower() not in {"0", "no", "false", "off"}
V52_STAKE_H1 = 1.0
V52_PRIZE_H1 = 14.0
# (pair, numero in Oro1 a t-4, numero fra i 15 Extra a t-1)
V52_RULES = (
    ((80, 86), 33, 4),
    ((38, 39), 21, 14),
    ((60, 61), 86, 5),
    ((2, 9), 44, 37),
    ((71, 78), 48, 86),
)

# V55 INCROCI: attivo in LIVE Telegram, non invia puntate al concessionario.
V55_KEY = 'v55_incroci_selective_live_forward_v1'
V55_LIVE_ENABLED = os.getenv('V55_LIVE_ENABLED', '1').strip().lower() not in {'0','no','false','off'}
V55_LIVE_NOTIFY = os.getenv('V55_LIVE_NOTIFY', '1').strip().lower() not in {'0','no','false','off'}
V55_MAX_GAP_DRAWS = 12  # 60 minuti
V55_STAKE_H1 = 1.0
V55_PRIZE_H1 = 14.0





def _v27_z(values):
    mean = sum(values) / len(values)
    var = sum((v - mean)**2 for v in values) / len(values)
    return [(v-mean)/(var**0.5 + 1e-8) for v in values]


def v27_predict(history):
    """Replicazione causale V27, posizione t prevista dopo history[-1].
    Finestra [t-w,t): non include mai il draw futuro. Tie-break stabile numero crescente.
    """
    if len(history) < V27_MIN_HISTORY:
        return None
    before, last = history[-2], history[-1]
    group = list(range(70, 80))
    b0, b1 = set(before['nums']), set(last['nums'])
    if sum(n in b0 for n in group)-sum(n in b1 for n in group) < 3:
        return None
    if sum(n in b0 and n not in b1 for n in range(70,75)) < 3:
        return None
    rep = {n for n in range(70,75) if n in b0 and n in b1}
    elite = rep == {70}
    standard = 70 not in rep and bool(rep)
    if not elite and not standard:
        return None

    def counts(field, window, num):
        h = history[-window:]
        return sum(num in set(r['nums']) for r in h) if field == 'base' else sum(int(r['oro']) == num for r in h)

    base80=[counts('base',80,n) for n in group]
    base320=[counts('base',320,n) for n in group]
    base20=[counts('base',20,n) for n in group]
    # Stable sort conservando i numeri minori sui pareggi.
    top5=sorted(range(10),key=lambda j:(-base80[j], j))[:5]
    zb=_v27_z(base320)
    zm=_v27_z([base20[j]-base320[j]*20/320 for j in range(10)])
    choice=min(top5,key=lambda j:(-(zb[j]+zm[j]),j))
    num=group[choice]
    oro1=[counts('oro1',160,n) for n in group]
    oro1_z=_v27_z(oro1)[choice]
    if standard and oro1_z < 0.5:
        return None
    return {'number':num,'tier':'ELITE_70' if elite else 'STANDARD_ORO1',
            'oro1_z':round(oro1_z,5),'origin_key':last['key']}


class V27Tracker:
    def __init__(self, data=None):
        d = data if isinstance(data,dict) else {}
        self.start_key = str(d.get('start_key') or '')
        self.last_evaluated_origin = str(d.get('last_evaluated_origin') or '')
        self.pending = d.get('pending') if isinstance(d.get('pending'),dict) else None
        self.signals = list(d.get('signals',[]))[-1500:]
        self.closed = list(d.get('closed',[]))[-1500:]

    def dump(self):
        return {'start_key':self.start_key,'last_evaluated_origin':self.last_evaluated_origin,
                'pending':self.pending,'signals':self.signals[-1500:],
                'closed':self.closed[-1500:]}

    def refresh(self, history):
        """Chiude pending usando H1 effettivo; arma soltanto sull'ultimo draw noto.
        Non genera backfill V27. Ritorna messaggi nuovi.
        """
        if not history:
            return []
        out=[]; latest=str(history[-1]['key'])
        if not self.start_key:
            self.start_key=latest
        if self.pending:
            origin=self.pending['origin_key']
            pos=next((i for i,r in enumerate(history) if r['key']==origin),None)
            if pos is not None and pos+1 < len(history):
                r=history[pos+1]
                w=int(self.pending['number']) in set(r['nums'])
                q=dict(self.pending, result_key=r['key'], hit=bool(w))
                if not any(x.get('origin_key')==origin for x in self.closed):
                    self.closed.append(q)
                    out.append('✅ V27 HIT H1' if w else '❌ V27 MISS H1')
                    out[-1] += f" | {q['tier']} | {q['number']} | origine {origin} | estrazione {r['key']}"
                self.pending=None
            elif pos is None and order_key(latest) and order_key(origin) and order_key(latest)>order_key(origin):
                # Storico disconnesso: non inventare esito e non sovrascrivere pending.
                return out
        if self.last_evaluated_origin == latest or self.pending:
            return out
        # Unico armamento dopo ultimo record disponibile; niente segnali storici.
        self.last_evaluated_origin=latest
        pred=v27_predict(history)
        if pred:
            self.pending=pred
            if not any(x.get('origin_key')==latest for x in self.signals):
                self.signals.append(pred)
                out.append(f"🎯 V27 AMBATA H1 — {pred['tier']}\n"
                           f"Numero: {pred['number']}\nOrigine: {latest}\n"
                           f"Oro1 z: {pred['oro1_z']:+.3f}\n"
                           "Giocata teorica €1, solo colpo successivo. Nessuna martingala.")
        return out

    def report(self, history):
        n=len(self.closed); hit=sum(bool(x.get('hit')) for x in self.closed)
        miss=n-hit; net=3*hit-n; streak=mx=0; balance=peak=dd=0
        for x in self.closed:
            won=bool(x.get('hit')); streak=0 if won else streak+1; mx=max(mx,streak)
            balance+=(3 if won else 0)-1
            peak=max(peak,balance); dd=max(dd,peak-balance)
        return (f"🎯 V27 ELITE 70 + STANDARD ORO1\n"
                f"Warmup: {len(history)}/{V27_HISTORY_REQUIRED} (minimo {V27_MIN_HISTORY})\n"
                f"Inizio forward: {self.start_key or '-'}\n"
                f"Segnali: {len(self.signals)} | chiusi {n} | HIT {hit} | MISS {miss}\n"
                f"H1 {safe_pct(hit,n):.2f}% | ROI {safe_pct(3*hit,n):.2f}% | netto €{net:+}\n"
                f"Max MISS {mx} | max DD €{dd}\n"
                f"Pending: {self.pending['number'] if self.pending else '-'} | Ultima origine controllata: {self.last_evaluated_origin or '-'}\n"
                "Risultati solo forward; nessun backfill dei test storici.")


async def v27_notify_latest(engine, app, notify=True):
    history=engine.multichannel.history
    if len(history) < V27_MIN_HISTORY:
        console_log(f"V27/V28 WARMUP INCOMPLETO {len(history)}/{V27_MIN_HISTORY}")
        return False
    # La prima installazione V28 non trasforma vecchie ambate/pending V27 in AMBI.
    # Congeliamo il marker PRIMA che V27 controlli l'ultima estrazione disponibile.
    first_v28 = not bool(engine.v28.start_key)
    if first_v28:
        engine.v28.start_key=engine.v27.last_evaluated_origin or str(history[-1]['key'])
    messages=engine.v27.refresh(history)
    messages.extend(engine.v28.refresh(history,engine.v27))
    if notify:
        for msg in messages:
            await engine.tg(app,msg)
    return bool(messages) or first_v28


async def cmd_v27(update: Update, context: ContextTypes.DEFAULT_TYPE):
    en=context.application.bot_data['engine']
    await reply(update,en.v27.report(en.multichannel.history))


# ============================================================
# V28 — AMBO H1 abbinato alla V27, solo nuove origini.
# Selezione partner replicata da V28 backtest: DECADE_MOMENTUM.
# Momentum(n) = F20_Base(n) - 20 * F320_Base(n) / 320.
# Pool partner: 70..79 esclusa l'ambata V27; parita': numero minore.
# ============================================================
def v28_select_partner(history, main):
    if len(history) < V27_MIN_HISTORY:
        return None
    main = int(main)
    if main not in range(70, 80):
        return None
    last20 = history[-20:]
    last320 = history[-320:]
    f20 = Counter(n for r in last20 for n in r['nums'])
    f320 = Counter(n for r in last320 for n in r['nums'])
    candidates = [n for n in range(70, 80) if n != main]
    partner = min(candidates, key=lambda n: (-(f20[n] - f320[n] * 20.0 / 320), n))
    return {'partner': int(partner), 'momentum': round(f20[partner] - f320[partner] * 20.0 / 320, 6)}


class V28Tracker:
    """Monitor H1 separato; non modifica ne' duplica il pending V27."""
    def __init__(self, data=None):
        d = data if isinstance(data, dict) else {}
        self.start_key = str(d.get('start_key') or '')
        self.pending = d.get('pending') if isinstance(d.get('pending'), dict) else None
        self.signals = list(d.get('signals') or [])[-1500:]
        self.closed = list(d.get('closed') or [])[-1500:]
        self.last_evaluated_origin = str(d.get('last_evaluated_origin') or '')

    def dump(self):
        return {'start_key': self.start_key, 'pending': self.pending,
                'last_evaluated_origin': self.last_evaluated_origin,
                'signals': self.signals[-1500:], 'closed': self.closed[-1500:]}

    def refresh(self, history, v27):
        """Chiude l'ambo precedente e arma soltanto un'origine V27 nuova.

        Il marker iniziale viene fissato DAL CHIAMANTE prima di v27.refresh().
        Una eventuale ambata V27 gia' pending al momento dell'upgrade NON
        genera retroattivamente un ambo V28.
        """
        if not history:
            return []
        latest = str(history[-1]['key'])
        out = []
        if self.pending:
            origin = str(self.pending.get('origin_key') or '')
            i = next((i for i, r in enumerate(history) if r['key'] == origin), None)
            if i is not None and i + 1 < len(history):
                nxt = history[i+1]
                pair = [int(self.pending['main']), int(self.pending['partner'])]
                hits = len(set(pair) & set(nxt['nums']))
                won = hits == 2
                closed = dict(self.pending, result_key=nxt['key'], hit=won,
                              matches=hits, stake=V28_STAKE_H1,
                              prize=V28_PRIZE_H1 if won else 0.0)
                if not any(x.get('origin_key') == origin for x in self.closed):
                    self.closed.append(closed)
                    out.append(f"{'✅ V28 AMBO HIT H1' if won else '❌ V28 AMBO MISS H1'}"
                               f" | {closed['tier']} | {pair[0]}-{pair[1]}"
                               f" | origine {origin} | esito {nxt['key']}")
                self.pending = None
            elif i is None and order_key(latest) and order_key(origin) and order_key(latest) > order_key(origin):
                # Manca l'estrazione target; non inventare un esito.
                return out
        origin_signal = v27.pending
        if not origin_signal:
            return out
        origin = str(origin_signal.get('origin_key') or '')
        if not origin or origin != latest:
            return out
        if (not self.start_key or not order_key(origin) or not order_key(self.start_key)
                or order_key(origin) <= order_key(self.start_key)):
            return out
        if any(x.get('origin_key') == origin for x in self.signals):
            return out
        if any(x.get('origin_key') == origin for x in self.closed):
            return out
        if self.pending:
            return out
        main = int(origin_signal['number'])
        choice = v28_select_partner(history, main)
        if not choice:
            return out
        pred = {'origin_key': origin, 'tier': str(origin_signal['tier']),
                'main': main, 'partner': choice['partner'],
                'momentum': choice['momentum']}
        self.pending = pred
        self.signals.append(pred)
        self.last_evaluated_origin = origin
        out.append(f"🔗 V28 AMBO H1 — {pred['tier']}\n"
                   f"Coppia: {pred['main']} - {pred['partner']}\n"
                   f"Origine: {origin}\n"
                   f"Momentum partner: {pred['momentum']:+.3f}\n"
                   "1 solo colpo dopo l'origine · simulazione €1 · nessuna progressione.")
        return out

    def report(self, history):
        rows = sorted(self.closed, key=lambda x: order_key(x.get('origin_key')) or (-1,-1))
        n = len(rows)
        hits = sum(bool(x.get('hit')) for x in rows)
        gain = sum(float(x.get('prize', V28_PRIZE_H1 if x.get('hit') else 0.0)) for x in rows)
        stake = sum(float(x.get('stake', V28_STAKE_H1)) for x in rows)
        balance = peak = max_dd = 0.0
        miss = max_miss = 0
        for x in rows:
            won = bool(x.get('hit'))
            miss = 0 if won else miss+1
            max_miss = max(max_miss, miss)
            balance += (V28_PRIZE_H1 if won else 0.0) - V28_STAKE_H1
            peak = max(peak, balance)
            max_dd = max(max_dd, peak-balance)
        def tier_stats(tier):
            sub = [x for x in rows if x.get('tier') == tier]
            won = sum(bool(x.get('hit')) for x in sub)
            return f"{won}/{len(sub)} (ROI {safe_pct(14*won,len(sub)):.2f}%)"
        pending = (f"{self.pending['main']}-{self.pending['partner']} ({self.pending['tier']})"
                   if self.pending else '-')
        return (f"🔗 V28 AMBO H1 — PARTNER MOMENTUM 70-79\n"
                f"Warmup {len(history)}/{V27_HISTORY_REQUIRED} (min {V27_MIN_HISTORY})\n"
                f"Inizio forward V28: {self.start_key or '-'}\n"
                f"Segnali {len(self.signals)} | chiusi {n} | HIT {hits} | MISS {n-hits}\n"
                f"H1 {safe_pct(hits,n):.2f}% | ROI {safe_pct(gain,stake):.2f}% | netto €{gain-stake:+.0f}\n"
                f"Max MISS {max_miss} | max DD €{max_dd:.0f}\n"
                f"ELITE: {tier_stats('ELITE_70')} | STANDARD: {tier_stats('STANDARD_ORO1')}\n"
                f"Pending: {pending}\n"
                "Solo forward, €1/ambo H1; nessun backfill o martingala.")


async def cmd_v28(update: Update, context: ContextTypes.DEFAULT_TYPE):
    en = context.application.bot_data['engine']
    await reply(update, en.v28.report(en.multichannel.history))

# ============================================================
# V38 DAILY — SOLO SIMULAZIONE: PRIME A FAST + A2 BASE1/BASE2 + V28.
# Politiche CONTROL (max 6) e ACTIVE (max 8) identiche salvo il limite.
# Una coppia = 1€ simulato, H1; STOP quando il saldo giornaliero e' >0.
# Non modifica i segnali operativi PRIME/V27/V28 o i loro risultati.
# ============================================================
class V38Tracker:
    def __init__(self, data=None):
        d = data if isinstance(data,dict) else {}
        self.start_key = str(d.get('start_key') or '')
        self.last_evaluated_origin = str(d.get('last_evaluated_origin') or '')
        self.plays = list(d.get('plays') or [])[-12000:]

    def dump(self):
        return {'start_key': self.start_key,
                'last_evaluated_origin': self.last_evaluated_origin,
                'plays': self.plays[-12000:]}

    def initialize(self, history):
        # Forward puro: nessun recupero retroattivo dei segnali gia' emessi.
        if not self.start_key and history:
            self.start_key = str(history[-1]['key'])
            self.last_evaluated_origin = self.start_key
            return True
        return False

    @staticmethod
    def _date(origin_key):
        return str(origin_key).split('#')[0]

    def _day_rows(self, policy, date):
        return [r for r in self.plays if r.get('policy') == policy and r.get('day') == date]

    def _day_stats(self, policy, date):
        rows = self._day_rows(policy, date)
        cost = sum(float(r.get('stake',1)) for r in rows)
        won = sum(float(r.get('prize',0)) for r in rows)
        pending = sum(1 for r in rows if r.get('status') == 'PENDING')
        missing = sum(1 for r in rows if r.get('status') == 'MISSING')
        return len(rows), cost, won-cost, pending, missing

    @staticmethod
    def _next_sequential(previous, newest, previous_time=None):
        if not previous or not isinstance(newest,dict):
            return False
        p=order_key(previous); n=order_key(newest.get('key'))
        if not p or not n: return False
        if p[0] == n[0]: return n[1] == p[1]+1
        # Trasferimento di giorno: deve iniziare dal #1; non inventare
        # un risultato se si e' perso un concorso intermedio.
        if n[1] != 1: return False
        return (str(previous_time or '').startswith('00:00') and str(newest.get('time') or '').startswith('00:05') and str(newest.get('day') or '') > str(previous).split('#')[0])

    def close_with_draw(self, newest, prev_origin, prev_time=None):
        """Chiude solo una H1 con draw consecutivo effettivamente presente.
        Se manca la H1, segna MISSING anziche' un falso MISS.
        """
        out=[]
        actual=set(int(n) for n in newest.get('nums',[]))
        latest=str(newest.get('key') or '')
        for q in self.plays:
            if q.get('status') != 'PENDING': continue
            origin=str(q.get('origin_key') or '')
            if origin == prev_origin and self._next_sequential(prev_origin,newest,prev_time):
                w=all(int(n) in actual for n in q['pair'])
                q['status']='CLOSED';q['result_key']=latest
                q['hit']=bool(w);q['prize']=V38_PRIZE_H1 if w else 0.0
                if w:
                    out.append(f"✅ V38 {q['policy']} AMBO H1 | {q['pair'][0]}-{q['pair'][1]} | {q['method']} | {origin} → {latest}")
            elif origin != latest and order_key(latest) and order_key(origin) and order_key(latest)>order_key(origin):
                q['status']='MISSING';q['result_key']=latest;q['prize']=0.0;q['hit']=None
                out.append(f"⚠️ V38 {q['policy']} H1 NON VERIFICABILE | {origin} (estrazione successiva assente)")
        return out

    @staticmethod
    def _candidates(origin, mc, v28):
        candidates=[]
        for p in mc.ambo_pending:
            if str(p.get('origin_key')) != origin: continue
            tier=str(p.get('tier') or '')
            slot=str(p.get('slot') or '')
            method=("A_BASE2" if tier=='A' and slot=='BASE2' else
                    f"A2_{slot}" if tier=='A2' and slot in ('BASE1','BASE2') else None)
            if method and method in V38_METHODS:
                pair=sorted(int(n) for n in (p.get('pair') or []))
                if len(pair)==2 and pair[0]!=pair[1]:
                    candidates.append((method,pair))
        p=v28.pending
        if isinstance(p,dict) and str(p.get('origin_key'))==origin:
            method={'ELITE_70':'V28_ELITE','STANDARD_ORO1':'V28_STANDARD'}.get(p.get('tier'))
            if method:
                candidates.append((method,sorted([int(p['main']),int(p['partner'])])))
        priority={m:i for i,m in enumerate(V38_METHODS)}
        candidates.sort(key=lambda c:(priority.get(c[0],999), c[1]))
        return candidates

    def arm(self, history, mc, v28):
        if not history:return []
        if self.initialize(history):return []
        origin=str(history[-1]['key'])
        if not order_key(origin) or not order_key(self.start_key) or order_key(origin)<=order_key(self.start_key): return []
        if self.last_evaluated_origin and order_key(self.last_evaluated_origin) and order_key(origin)<=order_key(self.last_evaluated_origin):return []
        self.last_evaluated_origin=origin
        date=self._date(origin)
        candidates=self._candidates(origin,mc,v28)
        out=[]
        for policy,limit in V38_CAPS.items():
            n,cost,balance,pending,missing=self._day_stats(policy,date)
            if n>=limit or balance>0: continue
            selected=[]
            for method,pair in candidates:
                if n>=limit: break
                ident=f"{policy}|{origin}|{method}|{pair[0]:02d}-{pair[1]:02d}"
                if any(x.get('id')==ident for x in self.plays):continue
                row={"id":ident,"policy":policy,"origin_key":origin,"day":date,
                     "method":method,"pair":pair,"stake":V38_STAKE_H1,
                     "status":"PENDING","hit":None,"prize":0.0,"result_key":None}
                self.plays.append(row)
                n+=1;cost+=V38_STAKE_H1;balance-=V38_STAKE_H1
                selected.append(f"{pair[0]:02d}-{pair[1]:02d} ({method})")
            if selected:
                out.append(f"🎯 V38 {policy} — AMBI H1 SHADOW | origine {origin}\n"
                           f"{'; '.join(selected)}\n"
                           f"Giocate virtuali: {n}/{limit} | saldo provvisorio €{balance:+.0f}\n"
                           "1€ per coppia, nessuna martingala. Stop dopo saldo positivo.")
        self.plays=self.plays[-12000:]
        return out

    def report(self, history):
        lines=["🎯 V38 AMBI DAILY — CONTROL + ACTIVE (solo SHADOW)",
               f"Warmup: {len(history)}/{MULTI_HISTORY_MAX}",
               f"Inizio forward: {self.start_key or '-'} | ultima origine {self.last_evaluated_origin or '-'}",
               "Selezione: PRIME A AMBO2 FAST + A2 BASE1/BASE2 + V28",
               "H1, €1 virtuale per coppia, STOP al saldo giornaliero positivo."]
        today = self._date(history[-1]['key']) if history else now_dt().date().isoformat()
        # Calendario forward, include i giorni senza alcun segnale (non solo quelli giocati).
        try:
            elapsed_days = max(0, (datetime.fromisoformat(today).date() - datetime.fromisoformat(self._date(self.start_key)).date()).days)
        except Exception:
            elapsed_days = 0
        for policy,cap in V38_CAPS.items():
            rows=sorted((r for r in self.plays if r.get('policy')==policy),
                        key=lambda x:(order_key(x.get('origin_key')) or (-1,-1), str(x.get('id'))))
            closed=[r for r in rows if r.get('status')=='CLOSED']
            stakes=sum(float(r.get('stake',1)) for r in rows)
            prizes=sum(float(r.get('prize',0)) for r in rows)
            missing=sum(r.get('status')=='MISSING' for r in rows)
            pending=sum(r.get('status')=='PENDING' for r in rows)
            byday={self._date(r.get('origin_key')) for r in rows}
            finished_days=[]
            for date in sorted(byday):
                dayrows=[r for r in rows if r.get('day')==date]
                if date==today: continue  # giorno ancora aperto, mostrato nella sezione Oggi
                if any(r.get('status')=='MISSING' for r in dayrows):continue
                dnet=sum(float(r.get('prize',0))-float(r.get('stake',1)) for r in dayrows)
                finished_days.append(dnet)
            positives=sum(v>0 for v in finished_days)
            running=peak=dd=0.0
            for r in rows:
                if r.get('status')=='MISSING':continue
                running += float(r.get('prize',0))-float(r.get('stake',1))
                peak=max(peak,running);dd=max(dd,peak-running)
            dn,dc,db,dp,dm=self._day_stats(policy,today)
            lines.append(f"\n{policy}: massimo {cap} ambi/giorno | segnali {len(rows)} | HIT {sum(x.get('hit') is True for x in closed)}/{len(closed)}")
            lines.append(f"Giornate positive {positives}/{elapsed_days} trascorse ({len(finished_days)} con giocate verificabili) | netto simulato €{prizes-stakes:+.0f} | max DD €{dd:.0f}")
            lines.append(f"Oggi: {dn}/{cap} puntate virtuali | saldo provv. €{db:+.0f} | pending {dp} | non verificati {missing}")
        lines.append("⚠️ Il risultato passato non garantisce una giornata positiva. Nessuna puntata automatica.")
        return "\n".join(lines)


async def cmd_v38(update: Update, context: ContextTypes.DEFAULT_TYPE):
    en=context.application.bot_data['engine']
    await reply(update,en.v38.report(en.multichannel.history))


# ============================================================
# STATE WRAPPER — preserva TUTTE le chiavi legacy + anti-regressione runner
# ============================================================
class MultiOnlyEngine:
    def __init__(self):
        self.raw_state = {}
        self.processed = []
        self.processed_set = set()
        self.last_draw_key = None
        self.multichannel = MultiPrimeV1()
        self.v27 = V27Tracker()
        self.v28 = V28Tracker()
        self.v38 = V38Tracker()
        self.v52 = V52LiveTracker()
        self.v55 = V55LiveTracker()
        self.v56 = V56SuperCoreTracker()
        self.v67 = V67DailyTracker()
        self.v70 = V70DailyTracker()
        self.v72 = V72DailyTracker()
        self.state_revision = 0
        self.state_load_info = {"loaded": False, "path": None, "reason": "not-run", "source": "-"}
        self.load_state()

    def load_state(self):
        # HARD LOCK 1/3 — leggi e congela le copie LOCALI prima di qualsiasi fetch/merge Git.
        local_path_pre = STATE_FILE if os.path.exists(STATE_FILE) else (LEGACY_STATE_FILE if os.path.exists(LEGACY_STATE_FILE) else None)
        local_pre = _read_json_file(local_path_pre) if local_path_pre else None
        hard_pre = _read_json_file(STATE_HARDLOCK_FILE)
        pre_anchor, pre_labels = _merge_state_candidates([("LOCAL_PRE_GIT", local_pre), ("HARDLOCK_PRE_GIT", hard_pre)])
        anchor_key = _state_last_key(pre_anchor)

        # Solo DOPO aver congelato pre_anchor è consentito aggiornare il checkout.
        ff_status = _fast_forward_repo_to_remote()

        local_path = STATE_FILE if os.path.exists(STATE_FILE) else (LEGACY_STATE_FILE if os.path.exists(LEGACY_STATE_FILE) else None)
        local_post = _read_json_file(local_path) if local_path else None
        hard_post = _read_json_file(STATE_HARDLOCK_FILE)
        remote_data, remote_src = _fetch_remote_state()
        remote_hard, remote_hard_src = _fetch_remote_hardlock_state()
        history_candidates, history_info = _fetch_state_history_candidates()

        candidates = [
            ("PRE_GIT_ANCHOR", pre_anchor),
            ("LOCAL_POST_FF", local_post),
            ("HARDLOCK_POST_FF", hard_post),
            ("REMOTE_HEAD", remote_data),
            ("REMOTE_HARDLOCK", remote_hard),
        ]
        candidates.extend((f"GIT:{sha[:8]}", d) for sha, d in history_candidates)
        data, used_sources = _merge_state_candidates(candidates)

        # Diagnostica: quali copie avrebbero fatto tornare indietro lo state rispetto
        # a ciò che era presente localmente PRIMA del fast-forward?
        blocked_sources = []
        if isinstance(pre_anchor, dict):
            for label, cand in (("LOCAL_POST_FF", local_post), ("REMOTE_HEAD", remote_data), ("REMOTE_HARDLOCK", remote_hard)):
                regs = _detect_state_regressions(cand, pre_anchor)
                if regs:
                    blocked_sources.append(f"{label}[{','.join(regs[:3])}]")

        data, floor_applied, floor_regs = _apply_hardlock_floor(data, pre_anchor)
        if not isinstance(data, dict):
            self.state_load_info = {
                "loaded": False, "path": local_path_pre, "reason": "state assente/non leggibile", "source": "NONE",
                "hardlock": "NO-STATE",
            }
            return False
        try:
            # HARD LOCK 2/3 — materializza SEMPRE entrambe le copie prima di caricare il motore.
            atomic_write_json(STATE_FILE, data)
            atomic_write_json(STATE_HARDLOCK_FILE, data)
            local_path = STATE_FILE

            self.raw_state = data
            self.v27 = V27Tracker(data.get(V27_KEY))
            self.v28 = V28Tracker(data.get(V28_KEY))
            self.v38 = V38Tracker(data.get(V38_KEY))
            self.v52 = V52LiveTracker(data.get(V52_KEY))
            self.v55 = V55LiveTracker(data.get(V55_KEY))
            self.v56 = V56SuperCoreTracker(data.get(V56_KEY))
            self.v67 = V67DailyTracker(data.get(V67_KEY))
            self.v70 = V70DailyTracker(data.get(V70_KEY))
            self.v72 = V72DailyTracker(data.get(V72_KEY))
            self.state_revision = max(0, int(data.get("multi_state_revision", 0) or 0))
            self.processed = [str(x) for x in data.get("processed", []) if isinstance(x, str)][-PROCESSED_MAX:]
            self.processed_set = set(self.processed)
            self.last_draw_key = data.get("last_draw_key") if isinstance(data.get("last_draw_key"), str) else None
            loaded_multi = self.multichannel.load(data.get("multichannel_bd12_ed12_o2f12_v1"))
            final_key = self.multichannel.history[-1].get("key") if self.multichannel.history else self.last_draw_key
            self.state_load_info = {
                "loaded": bool(loaded_multi),
                "path": local_path,
                "reason": "OK" if loaded_multi else "MULTI state assente/incompatibile",
                "source": "HARDLOCK_MERGE_LOCAL_REMOTE_HISTORY",
                "remote": remote_src, "remote_hard": remote_hard_src, "ff": ff_status,
                "history_status": history_info.get("status"),
                "history_count": int(history_info.get("count", 0) or 0),
                "history_max_rev": int(history_info.get("max_rev", 0) or 0),
                "used_sources": used_sources,
                "pre_git_sources": pre_labels,
                "hardlock_anchor_key": anchor_key,
                "hardlock_final_key": final_key,
                "hardlock_blocked": blocked_sources,
                "hardlock_floor_applied": bool(floor_applied or blocked_sources),
                "hardlock_floor_regs": floor_regs,
                "hardlock_backup_ok": os.path.exists(STATE_HARDLOCK_FILE),
            }
            console_log(
                f"STATE HARD LOCK CARICATO | ff={ff_status} | anchor={anchor_key or '-'} | final={final_key or '-'} | "
                f"rev={self.state_revision} | blocked={len(blocked_sources)} | backup={'OK' if os.path.exists(STATE_HARDLOCK_FILE) else 'NO'} | "
                f"MULTI history={len(self.multichannel.history)}"
            )
            return bool(loaded_multi)
        except Exception as exc:
            self.state_load_info = {
                "loaded": False, "path": local_path, "reason": f"{type(exc).__name__}: {exc}",
                "source": "HARDLOCK_FAIL", "hardlock_anchor_key": anchor_key,
            }
            console_log(f"STATE HARD LOCK LOAD FAIL | {self.state_load_info['reason']}")
            return False

    def save_state(self, git=True, force_git=False):
        # Snapshot corrente del motore.
        data = dict(self.raw_state) if isinstance(self.raw_state, dict) else {}
        data["saved_at"] = now_dt().isoformat(timespec="seconds")
        data["processed"] = self.processed[-PROCESSED_MAX:]
        data["last_draw_key"] = self.last_draw_key
        data["multichannel_bd12_ed12_o2f12_v1"] = self.multichannel.dump()
        data[V27_KEY] = self.v27.dump()
        data[V28_KEY] = self.v28.dump()
        data[V38_KEY] = self.v38.dump()
        data[V52_KEY] = self.v52.dump()
        data[V55_KEY] = self.v55.dump()
        data[V56_KEY] = self.v56.dump()
        data[V67_KEY] = self.v67.dump()
        data[V70_KEY] = self.v70.dump()
        data[V72_KEY] = self.v72.dump()
        data["active_mode"] = "MULTI_PRIME_A_A2_D_X_QUAD_FAST7_9_V52_MULTI_V55_V56_CORE_LIVE_V67_DAILY_V70_SHADOW_v20.9.2_HARD_LOCK"
        data["state_guard_schema"] = STATE_GUARD_SCHEMA

        # HARD LOCK 3/3 — il backup già presente è il pavimento locale.
        hard_floor = _read_json_file(STATE_HARDLOCK_FILE)
        local_anchor, _ = _merge_state_data(data, hard_floor)
        local_anchor, _, _ = _apply_hardlock_floor(local_anchor, hard_floor)
        if isinstance(local_anchor, dict):
            data = local_anchor

        # Fonde entrambe le copie remote, ma non può scendere sotto il pavimento locale.
        if git and PERSIST_GIT_STATE:
            remote_data, _ = _fetch_remote_state()
            remote_hard, _ = _fetch_remote_hardlock_state()
            remote_merged, _ = _merge_state_data(remote_data, remote_hard)
            merged, _ = _merge_state_data(data, remote_merged)
            merged, _, _ = _apply_hardlock_floor(merged, data)
            if isinstance(merged, dict):
                data = merged

        remote_rev = int(data.get("multi_state_revision", 0) or 0)
        self.state_revision = max(int(self.state_revision), remote_rev) + 1
        data["multi_state_revision"] = int(self.state_revision)
        data["saved_at"] = now_dt().isoformat(timespec="seconds")
        data["active_mode"] = "MULTI_PRIME_A_A2_D_X_QUAD_FAST7_9_V52_MULTI_V55_V56_CORE_LIVE_V67_DAILY_V70_SHADOW_v20.9.2_HARD_LOCK"
        data["state_guard_schema"] = STATE_GUARD_SCHEMA
        # Il ramo forward viene fuso anche se un runner remoto porta uno state vecchio.
        data[V27_KEY] = _merge_forward_tracker_state(data.get(V27_KEY), self.v27.dump())
        data[V28_KEY] = _merge_forward_tracker_state(data.get(V28_KEY), self.v28.dump())
        data[V38_KEY] = _merge_v38_state(data.get(V38_KEY), self.v38.dump())
        data[V52_KEY] = _merge_v52_state(data.get(V52_KEY), self.v52.dump())
        data[V55_KEY] = _merge_v55_state(data.get(V55_KEY), self.v55.dump())
        data[V56_KEY] = _merge_v56_state(data.get(V56_KEY), self.v56.dump())
        data[V67_KEY] = _merge_v67_state(data.get(V67_KEY), self.v67.dump())
        data[V70_KEY] = _merge_v70_state(data.get(V70_KEY), self.v70.dump())
        data[V72_KEY] = _merge_v72_state(data.get(V72_KEY), self.v72.dump())
        self.v27 = V27Tracker(data[V27_KEY])
        self.v28 = V28Tracker(data[V28_KEY])
        self.v38 = V38Tracker(data[V38_KEY])
        self.v52 = V52LiveTracker(data[V52_KEY])
        self.v55 = V55LiveTracker(data[V55_KEY])
        self.v56 = V56SuperCoreTracker(data[V56_KEY])
        self.v67 = V67DailyTracker(data[V67_KEY])
        self.v70 = V70DailyTracker(data[V70_KEY])
        self.v72 = V72DailyTracker(data[V72_KEY])

        # Ricarica il merge prima della scrittura per mantenere record/pending monotoni.
        self.multichannel.load(data.get("multichannel_bd12_ed12_o2f12_v1"))
        self.processed = [str(x) for x in data.get("processed", []) if isinstance(x, str)][-PROCESSED_MAX:]
        self.processed_set = set(self.processed)
        if isinstance(data.get("last_draw_key"), str):
            self.last_draw_key = data.get("last_draw_key")

        atomic_write_json(STATE_FILE, data)
        atomic_write_json(STATE_HARDLOCK_FILE, data)
        self.raw_state = data
        if git:
            st = git_commit_state_if_needed(force=force_git)
            if not st.get("ok", False):
                console_log(f"STATE HARD LOCK GIT WARNING | {st.get('action')} | {st.get('detail','')}")
            return st
        return {"ok": True, "action": "local-hardlock", "detail": "state + hardlock scritti"}

    async def tg(self, app, text):
        if not app or CHAT_ID is None or not text:
            return
        try:
            for chunk in split_telegram_text(text):
                await app.bot.send_message(chat_id=CHAT_ID, text=chunk)
        except Exception as exc:
            console_log(f"TELEGRAM FAIL | {type(exc).__name__}: {exc}")

    def status_text(self):
        mc = self.multichannel
        return (
            "📡 STATUS v20.9.2 MULTI PRIME + QUATERNA + SETTINA FAST + NOVINA + V52 MULTI LIVE — HARD LOCK\n\n"
            f"Ultimo MULTI: {mc.history[-1]['key'] if mc.history else '-'}\n"
            f"State: {'OK' if self.state_load_info.get('loaded') else 'NUOVO'} | {self.state_load_info.get('reason')}\n"
            f"State source: {self.state_load_info.get('source','-')} | ff {self.state_load_info.get('ff','-')} | rev {self.state_revision}\n"
            f"Git history guard: {self.state_load_info.get('history_count',0)} snapshot | max rev trovato {self.state_load_info.get('history_max_rev',0)}\n"
            f"HARD LOCK: {'ON' if self.state_load_info.get('hardlock_backup_ok') else 'WARN'} | anchor PRE-GIT {self.state_load_info.get('hardlock_anchor_key') or '-'} | final {self.state_load_info.get('hardlock_final_key') or '-'} | regressioni bloccate {len(self.state_load_info.get('hardlock_blocked') or [])}\n"
            f"History MULTI: {len(mc.history)}/{MULTI_HISTORY_MAX}\n"
            f"V27: {len(self.v27.signals)} segnali, {len(self.v27.closed)} chiusi | V28: {len(self.v28.signals)} segnali, {len(self.v28.closed)} chiusi\n"
            f"V52 MULTI LIVE: {len(self.v52.plays)} segnali | /v52\n"
            f"V55 INCROCI LIVE: {len(self.v55.plays)} segnali | /v55\n"
            f"V56 SUPER CORE LIVE: {len(self.v56.plays)} selezioni | /v56\n"
            f"V67 DAILY {V67_MODE}: {len(self.v67.plays)} giornate | /v67\n"
            f"V70 DAILY {V70_MODE}: {len(self.v70.plays)} giornate | /v70\n"
            f"V72 DAILY SHADOW: {len(self.v72.plays)} giornate | /v72\n"
            f"V38 DAILY SHADOW: CONTROL {len([r for r in self.v38.plays if r.get('policy')=='CONTROL'])} coppie | ACTIVE {len([r for r in self.v38.plays if r.get('policy')=='ACTIVE'])} coppie | /v38\n"
            f"v20.7.1 forward base: {mc.v2071_started_from_key or '-'} | scan da fix {max(0, mc.scans-mc.v2071_scans_base)} | STD da fix {max(0, mc.signals-mc.v2071_signals_base)}\n"
            f"PRIME A start: {mc.prime_a_started_from_key or '-'}\n"
            f"PRIME A2 start: {mc.prime_a2_started_from_key or '-'}\n"
            f"PRIME D ELITE start: {mc.prime_d_elite_started_from_key or '-'}\n"
            f"PRIME D WIDE start: {mc.prime_d_wide_started_from_key or '-'}\n"
            f"PRIME X start: {mc.prime_x_started_from_key or '-'}\n"
            f"PRIME C legacy start: {mc.prime_c_started_from_key or '-'}\n"
            f"B legacy start: {mc.prime_b_started_from_key or '-'}\n"
            f"TRIANGLE start: {mc.triangle_started_from_key or '-'}\n"
            f"QUATERNA v20.8 start: {mc.quad_started_from_key or '-'}\n"
            f"SISTEMI 7/9 base start: {mc.big_started_from_key or '-'}\n"
            f"SETTINA PROFIT FAST v20.9.2 start: {mc.big7_fast_started_from_key or '-'}\n\n"
            "✅ Attivo: MULTI + PRIME A + A2 + D ELITE/WIDE + QUATERNA PLUS/ELITE + SETTINA PROFIT FAST + NOVINA LIVE; X/C shadow\n"
            "🎯 V27 ambata ELITE+STANDARD H1 | 🔗 V28 ambo H1 collegato a V27.\n"
            "🟠 PRIME B: congelato, solo eventuali pending legacy.\n"
            "⏸️ FOCUS / INCROCIO / CORE / legacy: congelati nello state.\n\n"
            + mc.text()
        )

    @staticmethod
    def menu_text():
        return (
            "🎯 10eLOTTO v20.9.2 — MULTI PRIME + QUATERNA + SETTINA PROFIT FAST + NOVINA — HARD LOCK\n\n"
            "ATTIVO:\n"
            "• STANDARD BD12∩ED12∩O2F12 shadow/control\n"
            f"• 🔥 PRIME A: BD11-12 + O2 rank {PRIME_A_O2_RANK_MIN}-{PRIME_A_O2_RANK_MAX}\n"
            f"• 💎 PRIME A2: BD11-12 + O2 rank {PRIME_A2_O2_RANK_MIN}-{PRIME_A2_O2_RANK_MAX} + fascia Elite\n"
            "• 💠 D ELITE: BD1-4 + >16:00 + intersezione unica\n"
            "• 🔥 D WIDE: BD5-8 + >16:00 + intersezione unica\n"
            "• 🧬 X ULTRA: D + ED9-12 + >17:00 + Extra margin13≥1 — SHADOW\n"
            "• D: ambata operativa; tutti gli ambi D shadow\n"
            "• 🔷 QUATERNA PLUS: A2+D ELITE, consenso MAX-MIN Jaccard900 TOP10/11/12 ≥2/3\n"
            "• 💎 QUATERNA ELITE: stessa quaterna scelta da TOP10=TOP11=TOP12\n"
            "• 💶 Q: 1€/colpo, STOP al primo 2/4+, shadow fino H5\n"
            "• 🎯 SETTINA PROFIT FAST: gate A2/DE selettivi, COOC900; 1€/colpo H1-H2, H3-H5 shadow\n"
            "• 💥 NOVINA LIVE: A2+D ELITE+D WIDE, M+8 O2F12 Jaccard900; 1€/colpo, STOP al primo premio\n"
            "• 🎯 V27 ELITE+STANDARD: ambata H1, warmup 900\n"
            "• 🔗 V28 ELITE+STANDARD: ambo H1, partner momentum Base20-320, €1/ambo\n"
            "• 🚀 V52 MULTI LIVE: tutti i segnali 80-86/38-39/60-61/02-09/71-78, senza limite al giorno, H1\n"
            "• 🎯 V38 DAILY SHADOW: CONTROL max6 / ACTIVE max8, A FAST+A2+V28, H1 e saldo giornaliero\n"
            "• 🏆 V56 SUPER CORE LIVE: primo V52/giorno + primo V28 ELITE/giorno, 2 H1 max, nessuna seconda puntata\n"
            "• 🎯 V67 DAILY SHADOW: V66 alle 16:00; dopo MISS primo V52 successivo diverso, 1 H1\n"
            "• 🔢 V70 DAILY SHADOW: prima ripetizione resto90 (12 draw) dopo 08:00; terna V69 e ambo V59 SEPARATI H1\n"
            "• 🎯 V72 DAILY SHADOW: ambo CROSS da coppie nella stessa decina, 1 segnale giornaliero H1\n"
            "• C legacy shadow; B legacy congelato\n"
            f"• SUPER operativo solo A/A2 se support_sum≥{MULTI_SUPER_GATE}; TRIANGLE OFF shadow\n\n"
            "PAUSATI (state conservato): FOCUS, INCROCIO, CORE e tutti i legacy.\n\n"
            "/multi — statistiche complete A/A2/D/X + QUATERNA + 7/9 LIVE\n"
            "/v27 — report ambata ELITE e STANDARD\n"
            "/v28 — report ambo H1 ELITE e STANDARD\n"
            "/v38 — simulazione giornaliera ambi CONTROL/ACTIVE\n"
            "/v52 — V52 MULTI LIVE: segnali/HIT/MISS/saldo\n"
            "/v55 — V55 INCROCI LIVE: segnali/HIT/MISS/saldo\n"
            "/v56 — SUPER CORE LIVE: segnali scelti/HIT/MISS/saldo virtuale\n"
            "/v67 — V66 16:00 e 2° V52 dopo MISS (SHADOW)\n"
            "/v70 — V69 tripla somma + V59 ambo stesso concorso (SHADOW)\n"
            "/v72 — AMBO CROSS coppie stessa decina H1 (SHADOW)\n"
            "/status — feed + state + statistiche\n"
            "/verificatutto — audit completo\n"
            "/menu — comandi"
        )



# ============================================================
# SYNC / TELEGRAM
# ============================================================
async def reply(update, text):
    if update and update.message:
        for chunk in split_telegram_text(text):
            await update.message.reply_text(chunk)


async def cmd_multi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].multichannel.text())


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].status_text())


async def cmd_verificatutto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].status_text())


async def cmd_v52(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data['engine']
    await reply(update, engine.v52.report(engine.multichannel.history))


async def cmd_v55(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data['engine']
    await reply(update, engine.v55.report(engine.multichannel.history))


async def cmd_v56(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data['engine']
    await reply(update, engine.v56.report(engine.multichannel.history))


async def cmd_v67(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.v67.report(engine.multichannel.history))


async def cmd_v70(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.v70.report(engine.multichannel.history))


async def cmd_v72(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine=context.application.bot_data["engine"]
    await reply(update,engine.v72.report(engine.multichannel.history))


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].menu_text())


async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("multi", "MULTI + PRIME + Q + 7/9 LIVE"),
        BotCommand("v27", "Stato V27 ELITE + STANDARD"),
        BotCommand("v28", "Stato V28 AMBO H1"),
        BotCommand("v38", "Simulazioni V38 CONTROL/ACTIVE"),
        BotCommand("v52", "V52 MULTI LIVE H1"),
        BotCommand("v55", "V55 incroci LIVE H1"),
        BotCommand("v56", "V56 SUPER CORE LIVE H1"),
        BotCommand("v67", "V67 due ambi H1 condizionati SHADOW"),
        BotCommand("v70", "V70 tripla+ambo somma H1 SHADOW"),
        BotCommand("v72", "V72 ambo CROSS decine H1 SHADOW"),
        BotCommand("status", "Stato MULTI + Q + 7/9 LIVE + state"),
        BotCommand("verificatutto", "Audit MULTI/PRIME/Q/7/9 LIVE"),
        BotCommand("menu", "Comandi attivi"),
    ])


async def sync_multichannel(engine, app, notify=True, bootstrap_if_empty=False, days=1, prefetched_rows=None):
    rows = list(prefetched_rows) if prefetched_rows is not None else fetch_multichannel_recent(days=days)
    if not rows:
        return {"rows": 0, "unseen": 0, "signal": None, "events": []}

    mc = engine.multichannel
    events = []

    if bootstrap_if_empty and not mc.history:
        mc.bootstrap(rows)
        mc.ensure_start()
        mc.ensure_v2071_forward_base()
        mc.ensure_quad_forward_base()
        mc.ensure_big_forward_base()
        mc.ensure_big7_fast_forward_base()
        # Forward V38, senza segnali retroattivi.
        engine.v38.initialize(mc.history)
        engine.v52.initialize(mc.history)
        engine.v55.initialize(mc.history)
        engine.v56.initialize(mc.history, engine.v52, engine.v28)
        engine.v67.initialize(mc.history)
        engine.v70.initialize(mc.history)
        engine.v72.initialize(mc.history)
        # Warmup bootstrap: arma solo una previsione sulla prossima estrazione.
        await v27_notify_latest(engine, app, notify=notify)
        engine.save_state(git=True, force_git=True)
        return {"rows": len(rows), "unseen": 0, "signal": None, "events": [], "bootstrapped": True}

    unseen = [r for r in rows if not mc.seen(r.get("key"))]
    unseen.sort(key=lambda r: order_key(r.get("key")) or (-1, -1))

    # Catch-up: incorporiamo tutti i draw già avvenuti senza inventare segnali retroattivi.
    # Solo dopo l'ultimo draw noto armiamo un segnale realmente futuro.
    for r in unseen:
        previous = str(mc.history[-1]['key']) if mc.history else None
        prev_time = str(mc.history[-1].get('time') or '') if mc.history else None
        evs = mc.ingest(r)
        v38_results = engine.v38.close_with_draw(r, previous, prev_time)
        previous_row = mc.history[-2] if len(mc.history)>=2 else None
        v52_results = engine.v52.close_with_draw(r, previous_row, prev_time)
        v55_results = engine.v55.close_with_draw(r, previous_row)
        v56_results = engine.v56.close_with_draw(r, previous_row)
        v67_results = engine.v67.close_with_draw(r, previous_row)
        v70_results = engine.v70.close_with_draw(r, previous_row)
        v72_results = engine.v72.close_with_draw(r, previous_row)
        # Avanza l'indice dello storico V72 su ogni estrazione, anche nel catch-up.
        if r is not unseen[-1]:
            engine.v72.observe(r)
        events.extend(evs)
        if v52_results or v55_results or v56_results or v67_results or v70_results or v72_results:
            # Gli esiti sono fissati sul disco prima di qualsiasi invio Telegram.
            engine.save_state(git=False)
        if notify and V52_LIVE_NOTIFY and v52_results:
            await engine.tg(app, '\n\n'.join(v52_results))
        if notify and V55_LIVE_NOTIFY and v55_results:
            await engine.tg(app, '\n\n'.join(v55_results))
        if notify and V56_LIVE_NOTIFY and v56_results:
            await engine.tg(app, '\n\n'.join(v56_results))
        if notify and V67_NOTIFY and v67_results:
            await engine.tg(app, '\n\n'.join(v67_results))
        if notify and V70_NOTIFY and v70_results:
            await engine.tg(app, '\n\n'.join(v70_results))
        if notify and V72_NOTIFY and v72_results:
            await engine.tg(app, '\n\n'.join(v72_results))
        if notify and V38_NOTIFY and v38_results:
            await engine.tg(app, '\n'.join(v38_results))
        if notify:
            for ev in evs:
                if mc.should_notify_event(ev):
                    msg = mc.result_text(ev)
                    if msg:
                        await engine.tg(app, msg)

    mc.ensure_start()
    mc.ensure_v2071_forward_base()
    mc.ensure_quad_forward_base()
    mc.ensure_big_forward_base()
    mc.ensure_big7_fast_forward_base()
    v38_initialized = engine.v38.initialize(mc.history)
    v52_initialized = engine.v52.initialize(mc.history)
    v55_initialized = engine.v55.initialize(mc.history)
    v56_initialized = engine.v56.initialize(mc.history, engine.v52, engine.v28)
    v67_initialized = engine.v67.initialize(mc.history)
    v70_initialized = engine.v70.initialize(mc.history)
    v72_initialized = engine.v72.initialize(mc.history)
    sig = mc.arm() if mc.history else None
    v27_updated = await v27_notify_latest(engine, app, notify=notify)
    v38_messages = engine.v38.arm(mc.history, mc, engine.v28)
    v52_messages = engine.v52.arm(mc.history)
    v55_messages = engine.v55.arm(mc.history, engine.v52)
    v56_messages = engine.v56.arm(mc.history, engine.v52, engine.v28)
    v67_messages = engine.v67.arm(mc.history, engine.v52)
    v70_messages = engine.v70.arm(mc.history)
    v72_messages = engine.v72.arm(mc.history)
    if mc.history and not v72_messages:
        engine.v72.observe(mc.history[-1])
    if v52_messages or v55_messages or v56_messages or v67_messages or v70_messages or v72_messages:
        # Salvataggio del doppio tracker prima di qualsiasi notifica LIVE.
        engine.save_state(git=False)
    if notify and V52_LIVE_NOTIFY and v52_messages:
        await engine.tg(app, '\n\n'.join(v52_messages))
    if notify and V55_LIVE_NOTIFY and v55_messages:
        await engine.tg(app, '\n\n'.join(v55_messages))
    if notify and V56_LIVE_NOTIFY and v56_messages:
        await engine.tg(app, '\n\n'.join(v56_messages))
    if notify and V67_NOTIFY and v67_messages:
        await engine.tg(app, '\n\n'.join(v67_messages))
    if notify and V70_NOTIFY and v70_messages:
        await engine.tg(app, '\n\n'.join(v70_messages))
    if notify and V72_NOTIFY and v72_messages:
        await engine.tg(app, '\n\n'.join(v72_messages))
    if notify and V38_NOTIFY and v38_messages:
        await engine.tg(app, '\n\n'.join(v38_messages))
    if sig and notify and mc.should_notify_signal(sig):
        msg = mc.signal_text(sig)
        if msg:
            await engine.tg(app, msg)

    if unseen or sig or events or v27_updated or v38_initialized or v38_messages or v52_initialized or v52_messages or v55_initialized or v55_messages or v56_initialized or v56_messages or v67_initialized or v67_messages or v70_initialized or v70_messages or v72_initialized or v72_messages:
        engine.last_draw_key = mc.history[-1]["key"] if mc.history else engine.last_draw_key
        engine.save_state(git=True)

    return {
        "rows": len(rows),
        "unseen": len(unseen),
        "signal": sig,
        "events": events,
        "bootstrapped": False,
    }


async def startup(engine, app):
    try:
        rows = fetch_multichannel_recent(days=5)
    except Exception as exc:
        console_log(f"STARTUP MULTI fetch fail | {type(exc).__name__}: {exc}")
        return False

    if not rows:
        console_log("STARTUP MULTI: nessun record")
        return False

    mc = engine.multichannel
    if not mc.history:
        mc.bootstrap(rows)
        mc.ensure_start()
    else:
        # Recupera eventuali draw persi senza notifiche; nessun backfill di nuovi segnali.
        unseen = [r for r in rows if not mc.seen(r.get("key"))]
        unseen.sort(key=lambda r: order_key(r.get("key")) or (-1, -1))
        for r in unseen:
            previous = str(mc.history[-1]['key']) if mc.history else None
            prev_time = str(mc.history[-1].get('time') or '') if mc.history else None
            mc.ingest(r)
            engine.v38.close_with_draw(r, previous, prev_time)  # recupera SOLO l'esito di pending veri
            prevrow = mc.history[-2] if len(mc.history)>=2 else None
            engine.v52.close_with_draw(r, prevrow, prev_time)
            engine.v55.close_with_draw(r, prevrow)
            engine.v56.close_with_draw(r, prevrow)
        mc.ensure_start()

    # v20.7.1: solo DOPO il catch-up fissiamo la base reale dei nuovi tracker.
    mc.ensure_v2071_forward_base()
    mc.ensure_quad_forward_base()
    mc.ensure_big_forward_base()
    mc.ensure_big7_fast_forward_base()

    # Congela SOLO ora il segnale sulla più recente estrazione disponibile.
    engine.v38.initialize(mc.history)
    engine.v52.initialize(mc.history)
    engine.v55.initialize(mc.history)
    engine.v56.initialize(mc.history, engine.v52, engine.v28)
    sig = mc.arm() if mc.history else None
    await v27_notify_latest(engine, app, notify=True)
    v38_messages = engine.v38.arm(mc.history, mc, engine.v28)
    if V38_NOTIFY and v38_messages:
        await engine.tg(app, '\n\n'.join(v38_messages))
    engine.last_draw_key = mc.history[-1]["key"] if mc.history else engine.last_draw_key
    engine.save_state(git=True, force_git=True)

    await engine.tg(
        app,
        "🚀 MULTI BD12+ED12+O2F12 — v20.9.2 + V27 + V28 AMBO H1 AUTO WARMUP PRIME + Q + 7/9 — HARD LOCK AVVIATO\n\n"
        "🧪 STANDARD: BD12 ∩ ED12 ∩ O2F12 W80, cooldown 5 — SHADOW/control.\n"
        f"🔥 PRIME A: BD rank 11-12 + O2 rank {PRIME_A_O2_RANK_MIN}-{PRIME_A_O2_RANK_MAX} — invariato, qualità massima.\n"
        f"💎 PRIME A2 ELITE: BD rank 11-12 + O2 rank {PRIME_A2_O2_RANK_MIN}-{PRIME_A2_O2_RANK_MAX} + ora ≤08:00 oppure >16:00.\n"
        "💠 PRIME D ELITE: BD rank 1-4 + ora >16:00 + intersezione unica — AMBATA operativa.\n"
        "🔥 PRIME D WIDE: BD rank 5-8 + ora >16:00 + intersezione unica — AMBATA operativa.\n"
        "🧬 PRIME X ULTRA: D + ED rank 9-12 + ora >17:00 + Extra margin13≥1 — SHADOW.\n"
        "🔗 A/A2: ambi operativi; D: ambi solo shadow; C legacy shadow.\n"
        f"🔥 SUPER operativo solo A/A2 se support_sum≥{MULTI_SUPER_GATE}; 🔺 TRIANGLE OFF shadow.\n"
        "🛡️ HARD LOCK: snapshot PRE-GIT + backup doppio + LOCAL/REMOTE/STORIA GIT; regressioni bloccate.\n"
        f"🔒 State ereditato: {engine.state_load_info.get('hardlock_final_key') or engine.last_draw_key or '-'} | backup {'OK' if engine.state_load_info.get('hardlock_backup_ok') else 'WARN'}.\n"
        "🔷 QUATERNA PLUS/ELITE: A2+D ELITE, MAX-MIN Jaccard900, consenso TOP10/11/12.\n"
        "🎯 SETTINA PROFIT FAST: A2 O2rank=3+support6≥7 oppure DE BDrank1-3+O2rank10-12; H1-H2 operativo, H3-H5 shadow.\n"
        "💥 NOVINA LIVE invariata: A2+D ELITE/WIDE, Jaccard900_M, H1-H5.\n"
        "🎯 V27 ELITE+STANDARD AMBATA H1 LIVE: AUTO WARMUP 900, /v27.\n"
        "🔗 V28 AMBO H1 LIVE: M V27 + partner momentum 70-79, €1/ambo, ELITE e STANDARD, /v28.\n"
        "🚀 V52 MULTI LIVE: tutti gli ambi delle 5 regole, ripetizioni comprese, H1, /v52.\n"
        "🧬 V55 INCROCI LIVE: ambata H1 precedente + seconda coppia V52 entro 60 min, singolo incrocio H1, /v55.\n"
        "🏆 V56 SUPER CORE LIVE: primo V52/giorno + primo V28 ELITE/giorno; nessuna puntata duplicata, /v56.\n"
        "🎯 V67 DAILY SHADOW: V66 alle 16:00, poi primo V52 diverso dopo MISS, /v67.\n"
        "🔢 V70 DAILY SHADOW: primo resto90 ripetuto entro12 dopo 08:00 → terna V69 + ambo V59 H1 separati, /v70.\n"
        "🎯 V38 DAILY SHADOW: PRIME A FAST + A2 BASE1/BASE2 + V28, CONTROL max6, ACTIVE max8, /v38.\n"
        "💶 QUATERNA: 1€/colpo H1-H5, STOP al primo 2/4+; shadow fino H5.\n\n"
        "⏸️ FOCUS / INCROCIO / CORE / ENGINE / SOSIA / legacy: PAUSATI.\n"
        "✅ Il loro state viene conservato ma NON aggiornato.\n"
        "🚫 Nessun backfill QUATERNA/7/9/D/X; A/A2 invariati; C/B legacy preservati.\n\n"
        "Comandi: /multi /v27 /v28 /v38 /v52 /v55 /v56 /v67 /v70 /v72 /status /verificatutto /menu"
    )

    if sig and mc.should_notify_signal(sig):
        msg = mc.signal_text(sig)
        if msg:
            await engine.tg(app, msg)
    return True


async def startup_until_ready(engine, app):
    while True:
        if await startup(engine, app):
            return
        await asyncio.sleep(max(30, WARMUP_RETRY_SEC))


async def live_loop(engine, app):
    console_log(
        f"MULTI PRIME + Q + 7/9 LIVE | poll={LOOP_SEC}s | rotation={BOT_MAX_RUNTIME_SECONDS}s"
    )
    started = time.monotonic()
    last_error = ""
    last_error_ts = 0.0

    while True:
        if BOT_MAX_RUNTIME_SECONDS > 0 and time.monotonic() - started >= BOT_MAX_RUNTIME_SECONDS:
            try:
                st = engine.save_state(git=True, force_git=True)
                console_log(f"ROTATION save | {st.get('action')} | {st.get('detail','')}")
            except Exception as exc:
                st = {"ok": False, "action": "exception", "detail": f"{type(exc).__name__}: {exc}"}
                console_log(f"ROTATION save fail | {exc}")
            if BOT_ROTATION_NOTIFY:
                ok = bool(st.get("ok", False)) if isinstance(st, dict) else False
                detail = f"{st.get('action')} | {st.get('detail','')}" if isinstance(st, dict) else "save-status assente"
                await engine.tg(
                    app,
                    "♻️ MULTI PRIME + Q + SETTINA FAST + NOVINA v20.9.2 HARD LOCK — ROTAZIONE RUNNER\n"
                    + ("✅ State salvato e pubblicato sul branch.\n" if ok else "⚠️ State NON confermato sul branch.\n")
                    + f"{detail}\nAvvio successivo automatico.",
                )
            return "rotation"

        try:
            rows = fetch_multichannel_recent(days=1)
            await sync_multichannel(
                engine,
                app,
                notify=True,
                bootstrap_if_empty=True,
                days=1,
                prefetched_rows=rows,
            )
            await asyncio.sleep(LOOP_SEC)
        except Exception as exc:
            txt = f"{type(exc).__name__}: {exc}"
            console_log(f"LOOP ERROR | {txt}")
            now = time.time()
            if txt != last_error or now - last_error_ts >= 900:
                await engine.tg(
                    app,
                    "⚠️ MULTI PRIME + Q + 7/9 — ERRORE\n"
                    + txt
                    + "\nRiprovo automaticamente.",
                )
                last_error = txt
                last_error_ts = now
            await asyncio.sleep(max(30, LOOP_SEC))


# ============================================================
# SINGLE INSTANCE
# ============================================================
_LOCK_HANDLE = None


def acquire_single_instance_lock():
    global _LOCK_HANDLE
    if fcntl is None:
        return
    _LOCK_HANDLE = open(LOCK_FILE, "w")
    try:
        fcntl.flock(_LOCK_HANDLE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("Un'altra istanza MULTI PRIME è già attiva")


def _release_lock():
    global _LOCK_HANDLE
    if _LOCK_HANDLE and fcntl is not None:
        try:
            fcntl.flock(_LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
            _LOCK_HANDLE.close()
        except Exception:
            pass
        _LOCK_HANDLE = None


atexit.register(_release_lock)


# ============================================================
# SELF TEST
# ============================================================
def _selftest_seed_mc():
    mc = MultiPrimeV1()
    rows = []
    for i in range(1, 901):
        did = ((i - 1) % 288) + 1
        day_off = (i - 1) // 288
        d = (datetime(2099, 12, 1) + timedelta(days=day_off)).strftime("%Y-%m-%d")
        shift = (i - 1) % 90
        nums = [((shift + j) % 90) + 1 for j in range(20)]
        oro = nums[0]
        doppio = nums[1]
        extra = [n for n in range(1, 91) if n not in set(nums)][:15]
        rows.append({"key": draw_key(d, did), "day": d, "draw_id": did, "nums": nums,
                     "oro": oro, "doppio_oro": doppio, "extra": extra})
    mc.bootstrap(rows)
    mc.ensure_start()
    return mc


def run_self_test():
    # --- PRIME A invariato ---
    mc = _selftest_seed_mc()
    mc.history[-1]["time"] = "12:00"
    bd = [1,2,3,4,5,6,7,8,9,10,42,43]
    ed = [42,12,13,14,15,16,17,18,19,20,21,22]
    o2 = [50,51,52,53,54,42,55,56,57,58,59,60]  # 42 O2 rank 6 => A
    mc._rankings = lambda: {
        "base_gap": {n:(100-n if n!=42 else 30) for n in range(1,91)},
        "extra_gap": {n:(100-n if n!=42 else 25) for n in range(1,91)},
        "o2_freq": {n:(20 if n in o2 else 0) for n in range(1,91)},
        "top_base_delay": bd, "top_extra_delay": ed, "top_o2": o2, "extra_rank13_gap": 5,
    }
    mc._partner_plan = lambda main, ranks: {
        "main":int(main),
        "p1":{"num":50,"cooc":30,"support":1,"in_bd12":False,"in_ed12":False,"o2_freq80":20},
        "p2":{"num":51,"cooc":28,"support":2,"in_bd12":True,"in_ed12":False,"o2_freq80":20},
        "support_sum":3,"super_enabled":False,"cooc_window":900,
    }
    sig=mc.arm()
    assert sig and sig["prime_a_numbers"]==[42] and not sig["prime_a2_numbers"], sig
    assert mc.prime_a_signals==1 and len(mc.ambo_pending)==3

    # --- A2 ELITE: rank 3, mattina ---
    me=_selftest_seed_mc(); me.history[-1]["time"]="07:30"
    bd2=[1,2,3,4,5,6,7,8,9,10,11,43]
    ed2=[43,12,13,14,15,16,17,18,19,20,21,22]
    o22=[60,61,43,62,63,64,65,66,67,68,69,70]
    me._rankings=lambda:{
        "base_gap":{n:(100-n if n!=43 else 29) for n in range(1,91)},
        "extra_gap":{n:(100-n if n!=43 else 24) for n in range(1,91)},
        "o2_freq":{n:(20 if n in o22 else 0) for n in range(1,91)},
        "top_base_delay":bd2,"top_extra_delay":ed2,"top_o2":o22,"extra_rank13_gap":5,
    }
    me._partner_plan=lambda main,ranks:{
        "main":int(main),"p1":{"num":60,"cooc":31,"support":1,"in_bd12":False,"in_ed12":False,"o2_freq80":20},
        "p2":{"num":61,"cooc":27,"support":1,"in_bd12":False,"in_ed12":False,"o2_freq80":20},
        "support_sum":2,"super_enabled":False,"cooc_window":900,
    }
    sige=me.arm()
    assert sige and sige["prime_a2_numbers"]==[43] and not sige["prime_a_numbers"], sige
    assert me.prime_a2_signals==1 and len(me.ambo_pending)==3 and all(x.get("tier")=="A2" for x in me.ambo_pending)

    # Stesso ranking A2 ma fascia centrale => resta STANDARD e NON arma ambi.
    mx=_selftest_seed_mc(); mx.history[-1]["time"]="12:30"; mx._rankings=me._rankings; mx._partner_plan=me._partner_plan
    before=len(mx.ambo_pending); sx=mx.arm()
    assert sx and sx["numbers"]==[43] and not sx["prime_a2_numbers"] and len(mx.ambo_pending)==before

    # --- C SHADOW: BD rank 4 + O2 rank 8, dopo le 16 ---
    mc3=_selftest_seed_mc(); mc3.history[-1]["time"]="17:30"
    bd3=[1,2,3,44,45,6,7,8,9,10,11,12]
    ed3=[44,45,21,22,23,24,25,26,27,28,29,30]
    o23=[41,42,43,46,47,48,49,44,45,50,51,52]
    mc3._rankings=lambda:{
        "base_gap":{n:(30 if n==44 else 1) for n in range(1,91)},
        "extra_gap":{n:(30 if n==44 else 1) for n in range(1,91)},
        "o2_freq":{n:(10 if n in o23 else 0) for n in range(1,91)},
        "top_base_delay":bd3,"top_extra_delay":ed3,"top_o2":o23,"extra_rank13_gap":5,
    }
    mc3._partner_plan=lambda main,ranks:{
        "main":int(main),"p1":{"num":41,"cooc":20,"support":1,"in_bd12":False,"in_ed12":False,"o2_freq80":10},
        "p2":{"num":42,"cooc":19,"support":1,"in_bd12":False,"in_ed12":False,"o2_freq80":10},
        "support_sum":2,"super_enabled":False,"cooc_window":900,
    }
    sc=mc3.arm()
    assert sc and 44 in sc["prime_c_numbers"] and mc3.prime_c_signals>=1
    assert len(mc3.ambo_pending)>=3 and all(x.get("tier")=="C" for x in mc3.ambo_pending)
    assert not mc3.should_notify_signal(sc)

    # --- D ELITE + X ULTRA: intersezione unica, sera ---
    md=_selftest_seed_mc(); md.history[-1]["time"]="18:30"
    bd4=[46,2,3,4,5,6,7,8,9,10,11,12]
    ed4=[21,22,23,24,25,26,27,28,46,30,31,32]  # 46 ED rank 9
    o24=[46,61,62,63,64,65,66,67,68,69,70,71]
    md._rankings=lambda:{
        "base_gap":{n:(30 if n==46 else 1) for n in range(1,91)},
        "extra_gap":{n:(12 if n==46 else 1) for n in range(1,91)},
        "o2_freq":{n:(10 if n in o24 else 0) for n in range(1,91)},
        "top_base_delay":bd4,"top_extra_delay":ed4,"top_o2":o24,"extra_rank13_gap":10,
    }
    md._partner_plan=mc3._partner_plan
    sd=md.arm()
    assert sd and sd["prime_d_elite_numbers"]==[46] and sd["prime_x_numbers"]==[46], sd
    assert md.prime_d_elite_signals==1 and md.prime_x_signals==1
    assert md.should_notify_signal(sd) and all(x.get("tier")=="DE" for x in md.ambo_pending)
    # Gli ambi D sono shadow: un loro evento non va notificato.
    fake={"kind":"ambo","row":dict(md.ambo_pending[0]),"hit_now":True,"closed":True}
    assert not md.should_notify_event(fake)

    # D WIDE: BD rank 6, non X se ED rank fuori 9-12.
    mw=_selftest_seed_mc(); mw.history[-1]["time"]="16:05"
    bdw=[1,2,3,4,5,47,7,8,9,10,11,12]
    edw=[47,22,23,24,25,26,27,28,29,30,31,32]
    o2w=[47,61,62,63,64,65,66,67,68,69,70,71]
    mw._rankings=lambda:{
        "base_gap":{n:(25 if n==47 else 1) for n in range(1,91)},
        "extra_gap":{n:(20 if n==47 else 1) for n in range(1,91)},
        "o2_freq":{n:(10 if n in o2w else 0) for n in range(1,91)},
        "top_base_delay":bdw,"top_extra_delay":edw,"top_o2":o2w,"extra_rank13_gap":5,
    }
    mw._partner_plan=mc3._partner_plan
    sw=mw.arm()
    assert sw and sw["prime_d_wide_numbers"]==[47] and not sw["prime_x_numbers"], sw

    # Dump/load preserva A/A2/C/D/X e marker.
    rt=MultiPrimeV1(); assert rt.load(me.dump()) and rt.prime_a2_signals==1 and rt.prime_a2_started_from_key
    rc=MultiPrimeV1(); assert rc.load(mc3.dump()) and rc.prime_c_signals>=1 and rc.prime_c_started_from_key
    rd=MultiPrimeV1(); assert rd.load(md.dump()) and rd.prime_d_elite_signals==1 and rd.prime_x_signals==1 and rd.prime_d_elite_started_from_key

    # Merge state: i contatori nuovi devono essere monotoni.
    la={"multichannel_bd12_ed12_o2f12_v1":mc.dump(),"processed":[],"multi_state_revision":3}
    rb=me.dump(); rb["prime_a2_signals"]=5; rb["prime_c_signals"]=2; rb["prime_d_elite_signals"]=4; rb["prime_d_wide_signals"]=3; rb["prime_x_signals"]=2
    rr={"multichannel_bd12_ed12_o2f12_v1":rb,"processed":[],"multi_state_revision":4}
    mm,_=_merge_state_data(la,rr); mcm=mm["multichannel_bd12_ed12_o2f12_v1"]
    assert int(mcm.get("prime_a_signals",0))>=1 and int(mcm.get("prime_a2_signals",0))>=5 and int(mcm.get("prime_c_signals",0))>=2
    assert int(mcm.get("prime_d_elite_signals",0))>=4 and int(mcm.get("prime_d_wide_signals",0))>=3 and int(mcm.get("prime_x_signals",0))>=2

    # v20.7.1 marker: se A2/D/X sono vuoti, il marker vecchio viene riallineato
    # UNA SOLA VOLTA alla base forward corrente; A storico resta intatto.
    mf=_selftest_seed_mc()
    old_a = mf.prime_a_started_from_key
    mf.prime_a2_started_from_key="2026-10-06#127"
    mf.prime_d_elite_started_from_key="2026-10-06#127"
    mf.prime_d_wide_started_from_key="2026-10-06#127"
    mf.prime_x_started_from_key="2026-10-06#127"
    mf.v2071_started_from_key=None
    current=mf.history[-1]["key"]
    assert mf.ensure_v2071_forward_base()
    assert mf.v2071_started_from_key==current
    assert mf.prime_a2_started_from_key==current and mf.prime_d_elite_started_from_key==current and mf.prime_x_started_from_key==current
    assert mf.prime_a_started_from_key==old_a
    once=mf.v2071_started_from_key
    assert not mf.ensure_v2071_forward_base() and mf.v2071_started_from_key==once

    # QUATERNA unit: tracking economico chiude sul primo 2/4 e continua shadow.
    mq=_selftest_seed_mc(); mq.ensure_v2071_forward_base(); mq.ensure_quad_forward_base()
    qp={"quartet":[1,2,3,4],"quad_level":"ELITE","consensus":3,"min_jaccard":0.1,"mean_jaccard":0.2,"min_cooc":1,"window":900,"picks":[]}
    mq._arm_quad(mq.history[-1]["key"],1,qp,"A2",11,3)
    rr=dict(mq.history[-1]); rr["key"]="2100-01-01#001"; rr["day"]="2100-01-01"; rr["draw_id"]=1; rr["nums"]=[1,2]+[n for n in range(5,23)]; rr["oro"]=1; rr["doppio_oro"]=2
    evq=mq.advance(rr); assert any(e.get("kind")=="quad_stop" and int(e.get("matches",0))==2 for e in evq)
    assert mq.quad_pending and mq.quad_pending[0].get("operational_stopped") and float(mq.quad_pending[0].get("payout",0))==1.0
    # v20.9 SISTEMI 7/9: creazione LIVE + premi/stop + shadow.
    mb=_selftest_seed_mc(); mb.ensure_v2071_forward_base(); mb.ensure_quad_forward_base(); mb.ensure_big_forward_base()
    # SETTINA: 0/7 è già premio €1 e deve chiudere operativo a H1.
    p7={"system_size":7,"numbers":[1,2,3,4,5,6,7],"selector":"COOC900","scores":[],"window":900}
    mb._arm_big(mb.history[-1]["key"],1,p7,"A2",11,3)
    r7=dict(mb.history[-1]); r7["key"]="2100-01-02#001"; r7["day"]="2100-01-02"; r7["draw_id"]=1
    r7["nums"]=[n for n in range(20,40)]; r7["oro"]=20; r7["doppio_oro"]=21
    e7=mb.advance(r7); assert any(e.get("kind")=="big_stop" and int(e.get("matches",-1))==0 and float(e.get("prize",0))==1.0 for e in e7), e7
    assert mb.big_pending and mb.big_pending[0].get("operational_stopped") and float(mb.big_pending[0].get("payout",0))==1.0
    # NOVINA: 7/9 = €400 e stop.
    p9={"system_size":9,"numbers":[1,2,3,4,5,6,7,8,9],"selector":"JACCARD900_M","scores":[],"window":900}
    mb._arm_big(mb.history[-1]["key"],1,p9,"DE",3,8)
    r9=dict(mb.history[-1]); r9["key"]="2100-01-02#002"; r9["day"]="2100-01-02"; r9["draw_id"]=2
    r9["nums"]=[1,2,3,4,5,6,7]+[n for n in range(20,33)]; r9["oro"]=1; r9["doppio_oro"]=2
    e9=mb.advance(r9); assert any(e.get("kind")=="big_stop" and int(e.get("matches",-1))==7 and float(e.get("prize",0))==400.0 for e in e9), e9
    # Dump/load e merge preservano i sistemi.
    bd=mb.dump(); br=MultiPrimeV1(); assert br.load(bd) and br.big7_signals>=1 and br.big9_signals>=1 and br.big_started_from_key
    m1={"multichannel_bd12_ed12_o2f12_v1":bd,"processed":[],"multi_state_revision":7}
    m2={"multichannel_bd12_ed12_o2f12_v1":br.dump(),"processed":[],"multi_state_revision":8}
    bm,_=_merge_state_data(m1,m2); assert int(bm["multichannel_bd12_ed12_o2f12_v1"].get("big7_signals",0))>=1 and int(bm["multichannel_bd12_ed12_o2f12_v1"].get("big9_signals",0))>=1

    # v20.9.1 HARD LOCK: uno state remoto vecchio NON può far arretrare draw/scans/base forward.
    floor_mc=mb.dump(); floor_mc["history"]=[dict(x) for x in floor_mc.get("history",[])]; floor_mc["history"][-1]["key"]="2100-01-03#218"; floor_mc["history"][-1]["day"]="2100-01-03"; floor_mc["history"][-1]["draw_id"]=218
    floor_mc["scans"]=452; floor_mc["signals"]=18; floor_mc["v2071_started_from_key"]="2100-01-03#196"; floor_mc["v2071_scans_base"]=429; floor_mc["v2071_signals_base"]=18
    old_mc=dict(floor_mc); old_mc["history"]=[dict(x) for x in floor_mc["history"]]; old_mc["history"][-1]["key"]="2100-01-03#196"; old_mc["history"][-1]["draw_id"]=196; old_mc["scans"]=430; old_mc["v2071_started_from_key"]="2026-10-10#162"; old_mc["v2071_scans_base"]=429
    floor_state={"last_draw_key":"2100-01-03#218","multichannel_bd12_ed12_o2f12_v1":floor_mc,"multi_state_revision":23,"processed":[]}
    old_state={"last_draw_key":"2100-01-03#196","multichannel_bd12_ed12_o2f12_v1":old_mc,"multi_state_revision":1,"processed":[]}
    assert _detect_state_regressions(old_state,floor_state), "regressione non rilevata"
    locked, blocked, regs=_apply_hardlock_floor(old_state,floor_state)
    lmc=locked["multichannel_bd12_ed12_o2f12_v1"]
    assert blocked and _state_last_key(locked)=="2100-01-03#218" and int(lmc.get("scans",0))>=452, (blocked,regs,_state_last_key(locked),lmc.get("scans"))
    assert lmc.get("v2071_started_from_key")=="2100-01-03#196" and int(lmc.get("v2071_scans_base",0))==429
    # V28: selettore privo di informazione futura, scelta stabile e senza duplicati.
    pv = v28_select_partner(mb.history, 70)
    assert pv and 70 <= pv['partner'] <= 79 and pv['partner'] != 70
    v27t=V27Tracker()
    v28t=V28Tracker({'start_key':mb.history[-2]['key']})
    pv27={'number':70,'origin_key':mb.history[-1]['key'],'tier':'ELITE_70','oro1_z':1.0}
    v27t.pending=pv27
    messages=v28t.refresh(mb.history,v27t)
    assert len(messages)==1 and len(v28t.signals)==1 and v28t.pending
    assert not v28t.refresh(mb.history,v27t)  # idempotente su stesso draw
    rr=dict(mb.history[-1]); rr['key']='2100-01-02#003'; rr['nums']=[70,pv['partner']]+[n for n in range(1,91) if n not in (70,pv['partner'])][:18]
    assert len(v28t.refresh(mb.history+[rr],v27t))==1
    assert len(v28t.closed)==1 and v28t.closed[0]['hit'] and not v28t.pending
    older={'start_key':v28t.start_key,'pending':dict(v28t.signals[0]),'signals':v28t.signals,'closed':[]}
    mrg=_merge_forward_tracker_state(older,v28t.dump())
    assert not mrg['pending'] and len(mrg['closed'])==1
    # V38: A2 BASE1/BASE2 nello stesso origin sono due puntate distinte; reset day e STOP.
    tv=V38Tracker({'start_key':'2099-12-31#288'})
    class _MC:
        ambo_pending=[{'origin_key':'2100-01-01#001','tier':'A2','slot':'BASE1','pair':[3,7]},
                      {'origin_key':'2100-01-01#001','tier':'A2','slot':'BASE2','pair':[3,8]},
                      {'origin_key':'2100-01-01#001','tier':'A','slot':'BASE2','pair':[5,9]}]
    class _V28: pending=None
    hh=[{'key':'2100-01-01#001','nums':list(range(1,21)),'time':'00:05','day':'2100-01-01'}]
    assert len(tv.arm(hh,_MC(),_V28()))==2
    assert len(tv.plays)==6 and not tv.arm(hh,_MC(),_V28())
    newdraw={'key':'2100-01-01#002','nums':[3,7,8]+list(range(20,37)),'time':'00:10','day':'2100-01-01'}
    assert tv.close_with_draw(newdraw,'2100-01-01#001')
    assert sum(q.get('hit') is True for q in tv.plays)==4
    # Saldo positivo: non arma altre puntate lo stesso giorno.
    _MC.ambo_pending=[{'origin_key':'2100-01-01#002','tier':'A','slot':'BASE2','pair':[11,18]}]
    assert not tv.arm(hh+[newdraw],_MC(),_V28())
    older=tv.dump();older['plays']=[dict(x, status='PENDING', hit=None, prize=0) for x in older['plays']]
    merged=_merge_v38_state(older,tv.dump())
    assert len(merged['plays'])==6 and all(x['status']=='CLOSED' for x in merged['plays'])
    assert tv._day_stats('ACTIVE','2100-01-01')[2]>0
    # --- V52 MULTI LIVE: nessun backfill, doppia spia, ripetizioni nello stesso giorno, H1 e merge ---
    seed = []
    for i in range(901):
        day = (datetime(2025, 1, 1) + timedelta(days=i//288)).strftime('%Y-%m-%d')
        draw = 1 + i%288
        minutes = (draw*5) % (24*60)
        time_str = f"{minutes//60:02d}:{minutes%60:02d}"
        numbers = list(range(10,29)) + [33]
        if i == 900: numbers = [80,86] + list(range(10,28))
        seed.append({'day':day,'draw_id':draw,'key':draw_key(day,draw),
                     'time':time_str,'nums':numbers,'oro':(33 if i==896 else 10),
                     'doppio_oro':numbers[1], 'extra':list(range(1,10))+list(range(40,46))})
    tracker = V52LiveTracker()
    assert tracker.initialize(seed[:899])
    msg = tracker.arm(seed[:900],check_freshness=False)
    assert len(msg)==1 and '80-86' in msg[0]
    assert not tracker.arm(seed[:900],check_freshness=False)  # idempotenza
    assert tracker.close_with_draw(seed[900],seed[899])
    assert tracker.plays[0]['status']=='CLOSED' and tracker.plays[0]['hit'] is True
    older=tracker.dump()
    wrong=dict(older);wrong['plays']=[dict(older['plays'][0],status='PENDING',hit=None,prize=0)]
    merged=_merge_v52_state(wrong,older)
    assert len(merged['plays'])==1 and merged['plays'][0]['status']=='CLOSED'
    assert not V52LiveTracker(merged).arm(seed[:900],check_freshness=False)
    # Seconda previsione della stessa coppia nello STESSO giorno, senza limite giornaliero.
    # Dopo il draw 900, il draw 901 puo' innescare un nuovo segnale con oro t-4 nel draw 897.
    seed[897]['oro'] = 33
    # Trigger consecutivo sul draw 900: t-4 e' draw 897, che ora e' 33.
    follow = tracker.arm(seed[:901], check_freshness=False)
    assert len(follow) == 1 and '80-86' in follow[0], follow
    assert len(tracker.plays) == 2 and len({r['origin_key'] for r in tracker.plays}) == 2
    assert tracker.plays[0]['day'] == tracker.plays[1]['day']
    assert not tracker.arm(seed[:901], check_freshness=False)
    # Due coppie nello stesso concorso devono sopravvivere al merge e chiudersi entrambe.
    shadow = [dict(tracker.plays[1], id='V52|'+tracker.plays[1]['origin_key']+'|38-39', pair=[38,39])]
    both = _merge_v52_state(tracker.dump(), {'plays': shadow})
    assert len(both['plays']) == 3 and len({(r['origin_key'],tuple(r['pair'])) for r in both['plays']}) == 3
    v55 = V55LiveTracker({'start_key': '2100-01-01#001'})
    assert not v55.arm(seed[:901], tracker, check_freshness=False)
    assert _merge_v55_state({'start_key': '2100-01-01#001'}, {'start_key': '2100-01-01#002'})['start_key'] == '2100-01-01#001'
    # V56: no backfill, primo V52 + primo V28 ELITE al giorno,
    # nessuna doppia selezione, esito H1 verificato con contiguita' temporale.
    v56=V56SuperCoreTracker({'start_key':'2100-01-01#001'})
    p={'origin_key':'2100-01-01#002','target_key':'2100-01-01#003',
       'pair':[80,86],'status':'PENDING'}
    class _T52: plays=[p]
    class _T28:
        pending={'origin_key':'2100-01-01#002','tier':'ELITE_70','main':71,'partner':78}
        signals=[pending]
    r0={'key':'2100-01-01#002','day':'2100-01-01','draw_id':2,'time':'00:10',
        'nums':list(range(1,21))}
    assert len(v56.arm([r0],_T52(),_T28(),check_freshness=False))==2
    assert len(v56.plays)==2 and not v56.arm([r0],_T52(),_T28(),check_freshness=False)
    r1={'key':'2100-01-01#003','day':'2100-01-01','draw_id':3,'time':'00:15',
        'nums':[80,86,71,78]+list(range(1,17))}
    assert len(v56.close_with_draw(r1,r0))==2
    assert len([x for x in v56.plays if x.get('hit')])==2
    assert not v56.close_with_draw(r1,r0)
    r2={'key':'2100-01-01#004','day':'2100-01-01','draw_id':4,'time':'00:20','nums':list(range(1,21))}
    _T52.plays=[{'origin_key':r2['key'],'target_key':'2100-01-01#005','pair':[38,39], 'status':'PENDING'}]
    _T28.pending={'origin_key':r2['key'],'tier':'ELITE_70','main':70,'partner':72}
    _T28.signals=[_T28.pending]
    assert not v56.arm([r0,r1,r2],_T52(),_T28(),check_freshness=False)
    d=v56.dump()
    assert len(_merge_v56_state(d,{'start_key':'2100-01-01#002','plays':d['plays']})['plays'])==2
    # H1 mancante: nessun HIT se il target non e' contiguo.
    missing=V56SuperCoreTracker({'start_key':'2100-01-01#001','plays':[dict(v56.plays[0],status='PENDING',hit=None)]})
    r4={'key':'2100-01-01#004','day':'2100-01-01','draw_id':4,'time':'00:20','nums':list(range(1,21))}
    assert missing.close_with_draw(r4,r0) and missing.plays[0]['status']=='MISSING'
    prior = V56SuperCoreTracker()
    _T28.signals=[{'origin_key':r0['key'],'tier':'ELITE_70','main':70,'partner':72}]
    assert prior.initialize([r0], _T52(), _T28())
    assert '2100-01-01|V28_ELITE' in prior.blocked
    assert '2100-01-01|V52_DAILY' in prior.blocked
    # --- V70: somma 1009, tripla 19-71-72 e ambo 36-58 ---
    v70_nums=[12,15,19,24,26,34,35,36,45,54,59,61,62,63,65,69,76,79,87,88]
    v70_formula=V70DailyTracker.formula(v70_nums)
    assert v70_formula and v70_formula['sum']==1009
    assert v70_formula['last_digit']==9 and v70_formula['reduced']==19
    assert v70_formula['ambo']==[36,58] and v70_formula['triplet']==[19,71,72]
    assert V70DailyTracker.formula([1]*20) is None  # duplicati vietati
    assert V70DailyTracker.formula([]) is None
    v70_row={'day':'2100-01-01','key':'2100-01-01#100','draw_id':100,'time':'08:20','nums':v70_nums}
    v70_future={'day':'2100-01-01','key':'2100-01-01#101','draw_id':101,'time':'08:25',
                'nums':list(range(1,21))}
    v70_tracker=V70DailyTracker({'start_key':'2100-01-01#001',
        'plays':[{'day':'2100-01-01','origin_key':v70_row['key'],
                  'target_key':v70_future['key'],'status':'PENDING',
                  'ambo':[36,58],'triplet':[19,71,72]}]})
    assert v70_tracker.close_with_draw(v70_future,v70_row)
    assert v70_tracker.plays[0]['status']=='CLOSED'
    assert v70_tracker.plays[0]['triplet_hits']==1
    assert v70_tracker.plays[0]['ambo_hit'] is False
    assert not v70_tracker.close_with_draw(v70_future,v70_row)  # duplicate ignored
    snapshot=_merge_v70_state({'start_key':'2100-01-01#001','plays':[dict(v70_tracker.plays[0],status='PENDING')]},
                              {'start_key':'2100-01-01#001','plays':v70_tracker.plays})
    assert snapshot['plays'][0]['status']=='CLOSED'
    print("SELF-TEST OK: v20.9.2 + V27 + V28 + V38 + V52 MULTI + V55 + V56 + V67 + V70 + HARD LOCK")


# ============================================================
# MAIN
# ============================================================
async def main():
    if "--self-test" in sys.argv:
        run_self_test()
        return

    acquire_single_instance_lock()
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN mancante")
    if CHAT_ID is None:
        raise RuntimeError("CHAT_ID mancante/non valido")

    app = ApplicationBuilder().token(TOKEN).build()
    engine = MultiOnlyEngine()
    app.bot_data["engine"] = engine

    app.add_handler(CommandHandler("multi", cmd_multi))
    app.add_handler(CommandHandler("v27", cmd_v27))
    app.add_handler(CommandHandler("v28", cmd_v28))
    app.add_handler(CommandHandler("v38", cmd_v38))
    app.add_handler(CommandHandler("v52", cmd_v52))
    app.add_handler(CommandHandler("v55", cmd_v55))
    app.add_handler(CommandHandler("v56", cmd_v56))
    app.add_handler(CommandHandler("v67", cmd_v67))
    app.add_handler(CommandHandler("v70", cmd_v70))
    app.add_handler(CommandHandler("v72", cmd_v72))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("verificatutto", cmd_verificatutto))
    app.add_handler(CommandHandler("menu", cmd_menu))

    await app.initialize()
    await app.start()
    await setup_commands(app)
    await app.updater.start_polling(drop_pending_updates=True)
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
