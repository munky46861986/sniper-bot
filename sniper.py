# ============================================================
# 🎯 10eLOTTO MULTI BD12+ED12+O2F12 — v20.5.1 MULTI PRIME A+B + TRIANGLE FIX
# ============================================================
# UNICO RAMO ATTIVO: MULTI
#   STANDARD (shadow/control): BD12 ∩ ED12 ∩ O2F12, W80, cooldown 5
#   PRIME A: STANDARD + BD rank 11-12 + O2 rank 6-12 (INVARIATO da v20.4)
#   PRIME B: STANDARD + BD rank 11-12 + O2 rank 1-5 (espansione controllata)
#
# AMBI:
#   P1/P2 = 2 partner O2F12 con maggiore co-occorrenza Base nei 900 draw precedenti
#   A: AMBO1 M-P1 + AMBO2 M-P2 FAST + terzo lato sempre monitorato
#   B: tutti gli ambi restano shadow; l'ambata B viene notificata
#   SUPER = P1-P2 se support_sum >= 4
#   TRIANGLE_OFF = P1-P2 se support_sum < 4, sempre shadow su A/B
#
# FORWARD TEST:
#   - nessun backfill PRIME B / TRIANGLE OFF
#   - PRIME A migra dalla v20.4 senza reset
#   - state anti-regressione fra rotazioni GitHub runner
#   - v20.5.1: merge conservativo LOCAL+REMOTE + push esplicito sul branch
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
LEGACY_STATE_FILE = os.path.join(BASE_DIR, "superambo_gap4_core_fast_h1_state.json")
LOCK_FILE = "/tmp/10elotto_multi_prime_only.lock"

LOOP_SEC = int(os.getenv("LOOP_SEC", "60"))
BOT_MAX_RUNTIME_SECONDS = int(os.getenv("BOT_MAX_RUNTIME_SECONDS", "19800"))
BOT_ROTATION_NOTIFY = os.getenv("BOT_ROTATION_NOTIFY", "1") != "0"
WARMUP_RETRY_SEC = int(os.getenv("WARMUP_RETRY_SEC", "300"))
PERSIST_GIT_STATE = os.getenv("PERSIST_GIT_STATE", "1") != "0"
GIT_COMMIT_MIN_SECONDS = int(os.getenv("GIT_COMMIT_MIN_SECONDS", "300"))
PROCESSED_MAX = int(os.getenv("PROCESSED_MAX", "12000"))

MULTI_VERSION = 1  # compatibile con state v20.2/v20.3
MULTI_WINDOW = max(20, int(os.getenv("MULTI_BD_ED_O2_WINDOW", "80")))
MULTI_TOP_N = max(3, min(30, int(os.getenv("MULTI_BD_ED_O2_TOP_N", "12"))))
MULTI_COOLDOWN = max(0, int(os.getenv("MULTI_BD_ED_O2_COOLDOWN", "5")))
MULTI_HORIZON = max(1, int(os.getenv("MULTI_BD_ED_O2_HORIZON", "5")))
MULTI_COOC_WINDOW = max(80, int(os.getenv("MULTI_BD_ED_O2_AMBO_COOC_WINDOW", "900")))
MULTI_SUPER_GATE = max(2, int(os.getenv("MULTI_BD_ED_O2_AMBO_SUPER_GATE", "4")))
MULTI_HISTORY_MAX = max(MULTI_COOC_WINDOW, int(os.getenv("MULTI_BD_ED_O2_HISTORY_MAX", "900")))
MULTI_RECORD_MAX = max(500, int(os.getenv("MULTI_BD_ED_O2_RECORD_MAX", "8000")))
MULTI_AMBO_RECORD_MAX = max(1500, int(os.getenv("MULTI_BD_ED_O2_AMBO_RECORD_MAX", "24000")))

# PRIME A/B — regole congelate dal test storico Jan-Sep 2025.
# A = massima selettività: BD rank 11-12 + O2 rank 6-12.
# B = espansione controllata: BD rank 11-12 + O2 rank 1-5.
# A e B sono DISGIUNTI; insieme formano il CORE BD11-12.
PRIME_VERSION = 2
PRIME_BD_RANK_MIN = 11
PRIME_BD_RANK_MAX = 12
PRIME_A_O2_RANK_MIN = 6
PRIME_A_O2_RANK_MAX = 12
PRIME_B_O2_RANK_MIN = 1
PRIME_B_O2_RANK_MAX = 5

# Notifiche. STANDARD resta shadow. A è pienamente operativo.
# B notifica segnale/ambata, mentre i suoi ambi restano shadow.
NOTIFY_PRIME_A_SIGNAL = os.getenv("MULTI_PRIME_A_NOTIFY_SIGNAL", os.getenv("MULTI_PRIME_NOTIFY_SIGNAL", "1")).lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_A_RESULT = os.getenv("MULTI_PRIME_A_NOTIFY_RESULT", os.getenv("MULTI_PRIME_NOTIFY_RESULT", "1")).lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_B_SIGNAL = os.getenv("MULTI_PRIME_B_NOTIFY_SIGNAL", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_B_RESULT = os.getenv("MULTI_PRIME_B_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_TRIANGLE_OFF_HIT = os.getenv("MULTI_TRIANGLE_OFF_NOTIFY_HIT", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_STANDARD_SIGNAL = os.getenv("MULTI_STANDARD_NOTIFY_SIGNAL", "0").lower() not in {"0", "false", "no", "off"}
NOTIFY_STANDARD_RESULT = os.getenv("MULTI_STANDARD_NOTIFY_RESULT", "0").lower() not in {"0", "false", "no", "off"}
NOTIFY_SUPER_RESULT = os.getenv("MULTI_SUPER_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}

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
    global _LAST_GIT_COMMIT_TS
    if not PERSIST_GIT_STATE:
        return {"ok": True, "action": "disabled", "detail": "PERSIST_GIT_STATE=0"}
    if not os.path.exists(os.path.join(BASE_DIR, ".git")):
        return {"ok": True, "action": "no-git", "detail": "repository .git non presente"}

    now = time.time()
    if not force and now - _LAST_GIT_COMMIT_TS < GIT_COMMIT_MIN_SECONDS:
        return {"ok": True, "action": "throttled", "detail": "commit rimandato"}

    rel = os.path.relpath(STATE_FILE, BASE_DIR)
    a = _run_git(["add", rel])
    if a.returncode != 0:
        return {"ok": False, "action": "add-fail", "detail": a.stderr.strip()[-500:]}

    diff = _run_git(["diff", "--cached", "--quiet", "--", rel])
    if diff.returncode == 0:
        _LAST_GIT_COMMIT_TS = now
        return {"ok": True, "action": "no-change", "detail": "state invariato"}

    msg = f"state: MULTI PRIME {now_txt()}"
    c = _run_git(["commit", "-m", msg, "--", rel])
    if c.returncode != 0:
        return {"ok": False, "action": "commit-fail", "detail": c.stderr.strip()[-500:]}

    # GitHub Actions usa spesso un detached HEAD: push esplicito sul branch.
    branch = _git_remote_branch()
    p = _run_git(["push", "origin", f"HEAD:{branch}"], timeout=45)
    if p.returncode != 0:
        # Recovery: fondi lo state col remoto, riallinea il checkout, ricommetti e riprova.
        local_snapshot = _read_json_file(STATE_FILE)
        f = _run_git(["fetch", "--quiet", "origin", branch], timeout=45)
        if f.returncode != 0:
            return {"ok": False, "action": "push-fail-fetch-fail", "detail": p.stderr.strip()[-500:]}
        remote_snapshot, _ = _fetch_remote_state()
        merged_snapshot, _ = _merge_state_data(local_snapshot, remote_snapshot)
        if not isinstance(merged_snapshot, dict):
            return {"ok": False, "action": "push-fail-merge-fail", "detail": p.stderr.strip()[-500:]}
        rr = _run_git(["reset", "--hard", f"origin/{branch}"], timeout=45)
        if rr.returncode != 0:
            return {"ok": False, "action": "push-fail-reset-fail", "detail": rr.stderr.strip()[-500:]}
        atomic_write_json(STATE_FILE, merged_snapshot)
        a2 = _run_git(["add", rel])
        if a2.returncode != 0:
            return {"ok": False, "action": "retry-add-fail", "detail": a2.stderr.strip()[-500:]}
        d2 = _run_git(["diff", "--cached", "--quiet", "--", rel])
        if d2.returncode == 0:
            _LAST_GIT_COMMIT_TS = now
            return {"ok": True, "action": "remote-already-current", "detail": "state fuso gia presente sul remoto"}
        c2 = _run_git(["commit", "-m", msg + " [retry]", "--", rel])
        if c2.returncode != 0:
            return {"ok": False, "action": "retry-commit-fail", "detail": c2.stderr.strip()[-500:]}
        p2 = _run_git(["push", "origin", f"HEAD:{branch}"], timeout=45)
        if p2.returncode != 0:
            return {"ok": False, "action": "retry-push-fail", "detail": p2.stderr.strip()[-500:]}
        _LAST_GIT_COMMIT_TS = now
        return {"ok": True, "action": "pushed-after-merge", "detail": msg}

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
    closed = len(mc.get("records") or []) + len(mc.get("ambo_records") or [])
    counters = (
        int(mc.get("scans", 0) or 0)
        + int(mc.get("signals", 0) or 0)
        + int(mc.get("prime_a_signals", mc.get("prime_signals", 0)) or 0)
        + int(mc.get("prime_b_signals", 0) or 0)
    )
    pending = len(mc.get("pending") or []) + len(mc.get("ambo_pending") or [])
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


def _fetch_remote_state():
    """Legge SOLO lo state dal branch remoto; non cambia il codice in esecuzione."""
    if not os.path.exists(os.path.join(BASE_DIR, ".git")):
        return None, "no-git"
    branch = _git_remote_branch()
    f = _run_git(["fetch", "--quiet", "origin", branch], timeout=45)
    if f.returncode != 0:
        return None, "fetch-fail"
    rel = os.path.relpath(STATE_FILE, BASE_DIR).replace(os.sep, "/")
    g = _run_git(["show", f"origin/{branch}:{rel}"], timeout=20)
    if g.returncode != 0 or not g.stdout.strip():
        return None, "remote-state-missing"
    try:
        data = json.loads(g.stdout)
        if not isinstance(data, dict):
            return None, "remote-state-invalid"
        return data, f"origin/{branch}"
    except Exception as exc:
        return None, f"remote-json-{type(exc).__name__}"


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
    base.update({"history":hist,"records":rec,"pending":pen,"ambo_records":arec,"ambo_pending":apen})
    base["draw_seq"] = max(int(a.get("draw_seq",0) or 0), int(b.get("draw_seq",0) or 0), len(hist))
    for k in ("scans","signals","no_signal","cooldown_skips","ambo_origins","ambo_super_signals"):
        base[k]=max(int(a.get(k,0) or 0),int(b.get(k,0) or 0))
    sigrows=rec+pen
    def tier(r):
        t=str(r.get("tier") or "").upper()
        if t in {"A","B","STD"}: return t
        return "A" if bool(r.get("prime")) else "STD"
    ac=len({_signal_id(r) for r in sigrows if tier(r)=="A"}); bc=len({_signal_id(r) for r in sigrows if tier(r)=="B"})
    base["prime_a_signals"]=max(int(a.get("prime_a_signals",a.get("prime_signals",0)) or 0),int(b.get("prime_a_signals",b.get("prime_signals",0)) or 0),ac)
    base["prime_signals"]=base["prime_a_signals"]
    base["prime_b_signals"]=max(int(a.get("prime_b_signals",0) or 0),int(b.get("prime_b_signals",0) or 0),bc)
    lss={}
    for src in (a.get("last_signal_seq"),b.get("last_signal_seq")):
        if isinstance(src,dict):
            for k,v in src.items():
                try: ik,iv=int(k),int(v)
                except Exception: continue
                lss[str(ik)]=max(int(lss.get(str(ik),0) or 0),iv)
    base["last_signal_seq"]=lss
    for k in ("start_from_key","ambo_started_from_key","prime_started_from_key","prime_a_started_from_key","prime_b_started_from_key","triangle_started_from_key"):
        base[k]=_key_min(a.get(k),b.get(k))
    for k in ("started_at","ambo_started_at","prime_started_at","prime_a_started_at","prime_b_started_at","triangle_started_at"):
        vals=[x for x in (a.get(k),b.get(k)) if isinstance(x,str) and x]; base[k]=min(vals) if vals else None
    base["last_armed_key"]=_key_max(a.get("last_armed_key"),b.get("last_armed_key"))
    base["last_signal"]=_latest_obj(a.get("last_signal"),b.get("last_signal"),("origin_key","key"))
    base["last_result"]=_latest_obj(a.get("last_result"),b.get("last_result"))
    base["last_ambo_signal"]=_latest_obj(a.get("last_ambo_signal"),b.get("last_ambo_signal"),("origin_key","key"))
    base["last_ambo_result"]=_latest_obj(a.get("last_ambo_result"),b.get("last_ambo_result"))
    return base


def _merge_state_data(local_data, remote_data):
    if not isinstance(local_data, dict): return (dict(remote_data),"REMOTE") if isinstance(remote_data,dict) else (None,"NONE")
    if not isinstance(remote_data, dict): return dict(local_data),"LOCAL"
    lp,rp=_state_progress(local_data),_state_progress(remote_data)
    base=dict(local_data if lp>=rp else remote_data)
    mm=_merge_multichannel_state(local_data.get("multichannel_bd12_ed12_o2f12_v1"),remote_data.get("multichannel_bd12_ed12_o2f12_v1"))
    if mm is not None: base["multichannel_bd12_ed12_o2f12_v1"]=mm
    vals=[]; seen=set()
    for x in list(local_data.get("processed") or [])+list(remote_data.get("processed") or []):
        if isinstance(x,str) and x not in seen: seen.add(x); vals.append(x)
    vals.sort(key=lambda x:order_key(x) or (-1,-1)); base["processed"]=vals[-PROCESSED_MAX:]
    base["last_draw_key"]=_key_max(local_data.get("last_draw_key"),remote_data.get("last_draw_key"))
    base["multi_state_revision"]=max(int(local_data.get("multi_state_revision",0) or 0),int(remote_data.get("multi_state_revision",0) or 0))
    ss=[x for x in (local_data.get("saved_at"),remote_data.get("saved_at")) if isinstance(x,str) and x]
    if ss: base["saved_at"]=max(ss)
    return base,"MERGED_LOCAL_REMOTE"


def _best_available_state(local_data, remote_data):
    return _merge_state_data(local_data, remote_data)


# ============================================================
# MULTI BD12 + ED12 + O2F12 + PRIME A/B + TRIANGLE SHADOW
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
        self.prime_b_started_from_key = None
        self.prime_b_started_at = None
        self.prime_b_signals = 0
        self.triangle_started_from_key = None
        self.triangle_started_at = None

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
        return {
            "key": key, "day": day, "draw_id": draw_id, "nums": nums,
            "oro": oro, "doppio_oro": doppio, "extra": extra,
        }

    @staticmethod
    def _tier_from_obj(row):
        if not isinstance(row, dict):
            return "STD"
        tier = str(row.get("tier") or "").upper()
        if tier in {"A", "B", "STD"}:
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
        q["prime"] = q["tier"] == "A"  # alias legacy, NON usare per B
        return q

    @classmethod
    def _sanitize_signal_row(cls, row):
        if not isinstance(row, dict) or not row.get("origin_key"):
            return None
        q = dict(row)
        q["tier"] = cls._tier_from_obj(q)
        q["prime"] = q["tier"] == "A"
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
            # v20.5: B nasce qui, senza ricostruire segnali precedenti.
            self.prime_b_started_from_key = current
            self.prime_b_started_at = now_iso
            changed = True
        if not self.triangle_started_from_key:
            # v20.5: il terzo lato OFF viene tracciato solo da qui in avanti.
            self.triangle_started_from_key = current
            self.triangle_started_at = now_iso
            changed = True
        return changed

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

        bsk = obj.get("prime_b_started_from_key")
        self.prime_b_started_from_key = str(bsk) if order_key(bsk) is not None else None
        self.prime_b_started_at = obj.get("prime_b_started_at") if isinstance(obj.get("prime_b_started_at"), str) else None
        self.prime_b_signals = max(0, int(obj.get("prime_b_signals", 0) or 0))

        tsk = obj.get("triangle_started_from_key")
        self.triangle_started_from_key = str(tsk) if order_key(tsk) is not None else None
        self.triangle_started_at = obj.get("triangle_started_at") if isinstance(obj.get("triangle_started_at"), str) else None

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
            "prime_b_started_from_key": self.prime_b_started_from_key,
            "prime_b_started_at": self.prime_b_started_at,
            "prime_b_signals": self.prime_b_signals,
            "triangle_started_from_key": self.triangle_started_from_key,
            "triangle_started_at": self.triangle_started_at,
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
        top_base_delay = sorted(range(1, 91), key=lambda n: (-base_gap[n], n))[:MULTI_TOP_N]
        top_extra_delay = sorted(range(1, 91), key=lambda n: (-extra_gap[n], n))[:MULTI_TOP_N]
        top_o2 = sorted(range(1, 91), key=lambda n: (-o2_freq[n], n))[:MULTI_TOP_N]
        return {
            "base_gap": base_gap, "extra_gap": extra_gap, "o2_freq": o2_freq,
            "top_base_delay": top_base_delay,
            "top_extra_delay": top_extra_delay,
            "top_o2": top_o2,
        }

    @staticmethod
    def _rank_of(n, ordered):
        try:
            return int(ordered.index(int(n)) + 1)
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _tier(bd_rank, o2_rank):
        if bd_rank is None or o2_rank is None:
            return "STD"
        bd_rank, o2_rank = int(bd_rank), int(o2_rank)
        if not (PRIME_BD_RANK_MIN <= bd_rank <= PRIME_BD_RANK_MAX):
            return "STD"
        if PRIME_A_O2_RANK_MIN <= o2_rank <= PRIME_A_O2_RANK_MAX:
            return "A"
        if PRIME_B_O2_RANK_MIN <= o2_rank <= PRIME_B_O2_RANK_MAX:
            return "B"
        return "STD"

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

    def _arm_ambo(self, origin_key, main, plan, tier="STD", bd_rank=None, o2_rank=None):
        if not plan:
            return []
        tier = str(tier or "STD").upper()
        origin_id = f"{origin_key}|M{int(main):02d}"
        p1 = int(plan["p1"]["num"])
        p2 = int(plan["p2"]["num"])
        specs = [("BASE1", sorted([int(main), p1])), ("BASE2", sorted([int(main), p2]))]
        if plan.get("super_enabled"):
            specs.append(("SUPER", sorted([p1, p2])))
        elif tier in {"A", "B"}:
            # Novità v20.5: per PRIME A/B seguiamo SEMPRE il terzo lato,
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

        details, ambo_plans = [], []
        a_numbers, b_numbers = [], []
        for n in selected:
            bd_rank = self._rank_of(n, ranks["top_base_delay"])
            ed_rank = self._rank_of(n, ranks["top_extra_delay"])
            o2_rank = self._rank_of(n, ranks["top_o2"])
            tier = self._tier(bd_rank, o2_rank)
            if tier == "A":
                a_numbers.append(int(n))
                self.prime_a_signals += 1
            elif tier == "B":
                b_numbers.append(int(n))
                self.prime_b_signals += 1

            d = {
                "num": n,
                "base_gap": int(ranks["base_gap"][n]),
                "extra_gap": int(ranks["extra_gap"][n]),
                "o2_freq80": int(ranks["o2_freq"][n]),
                "bd_rank": bd_rank, "ed_rank": ed_rank, "o2_rank": o2_rank,
                "tier": tier, "prime": tier == "A",
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
                if tier in {"A", "B"}:
                    self._arm_ambo(origin_key, n, plan, tier=tier, bd_rank=bd_rank, o2_rank=o2_rank)
                    ambo_plans.append({"main": n, "tier": tier, **d["ambo"]})

            details.append(d)
            self.pending.append({
                "origin_key": origin_key, "num": n, "age": 0,
                "hit": False, "hit_colpo": None, "created_at": now_txt(),
                "base_gap": d["base_gap"], "extra_gap": d["extra_gap"],
                "o2_freq80": d["o2_freq80"],
                "bd_rank": bd_rank, "ed_rank": ed_rank, "o2_rank": o2_rank,
                "tier": tier, "prime": tier == "A",
            })
            self.last_signal_seq[n] = self.draw_seq

        self.pending = self.pending[-200:]
        self.signals += len(selected)
        out = {
            "origin_key": origin_key,
            "numbers": selected,
            "prime_a_numbers": a_numbers,
            "prime_b_numbers": b_numbers,
            # alias v20.4
            "prime_numbers": a_numbers,
            "details": details,
            "ambo_plans": ambo_plans,
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
        if sig.get("prime_b_numbers") and NOTIFY_PRIME_B_SIGNAL:
            return True
        return NOTIFY_STANDARD_SIGNAL

    @staticmethod
    def signal_text(sig):
        if not sig:
            return None
        a_nums = {int(x) for x in sig.get("prime_a_numbers", [])}
        b_nums = {int(x) for x in sig.get("prime_b_numbers", [])}
        lines = [
            "🧪 MULTI BD12+ED12+O2F12 — v20.5",
            "Origine: " + str(sig.get("origin_key")),
            "STANDARD: Base RIT12 ∩ Extra RIT12 ∩ Oro2 FREQ12 (W80)",
            f"Segnali standard: {' '.join(f'{int(n):02d}' for n in sig.get('numbers', []))}",
        ]
        if a_nums:
            lines += [
                "", "🔥 PRIME A — QUALITÀ MASSIMA",
                f"🎯 A H1: {' '.join(f'{n:02d}' for n in sorted(a_nums))}",
                f"Gate A: BD rank 11-12 + O2 rank {PRIME_A_O2_RANK_MIN}-{PRIME_A_O2_RANK_MAX}",
            ]
        if b_nums:
            lines += [
                "", "🟠 PRIME B — ESPANSIONE CONTROLLATA",
                f"🎯 B H1: {' '.join(f'{n:02d}' for n in sorted(b_nums))}",
                f"Gate B: BD rank 11-12 + O2 rank {PRIME_B_O2_RANK_MIN}-{PRIME_B_O2_RANK_MAX}",
            ]
        if not a_nums and not b_nums:
            lines += ["", "🌑 Nessun PRIME A/B; STANDARD registrato in shadow."]

        lines.append("")
        for d in sig.get("details", []):
            n = int(d["num"])
            tier = str(d.get("tier") or "STD")
            tag = "🔥 A" if tier == "A" else ("🟠 B" if tier == "B" else "• STD")
            lines.append(
                f"{tag} {n:02d}: BD rank={d.get('bd_rank')} rit={d.get('base_gap')} | "
                f"ED rank={d.get('ed_rank')} rit={d.get('extra_gap')} | "
                f"O2 rank={d.get('o2_rank')} freq80={d.get('o2_freq80')}"
            )
            a = d.get("ambo") or {}
            if a:
                p1, p2 = a.get("p1") or {}, a.get("p2") or {}
                n1, n2 = int(p1.get("num", 0)), int(p2.get("num", 0))
                if tier == "A":
                    lines.append(
                        f"  🔗 AMBO1 {n:02d}-{n1:02d} | ⚡ AMBO2 FAST H1 {n:02d}-{n2:02d} | "
                        f"COOC900 {p1.get('cooc',0)}/{p2.get('cooc',0)}"
                    )
                elif tier == "B":
                    lines.append(
                        f"  👁️ AMBI B shadow: {n:02d}-{n1:02d} / {n:02d}-{n2:02d} | "
                        f"COOC900 {p1.get('cooc',0)}/{p2.get('cooc',0)}"
                    )
                if tier in {"A", "B"}:
                    if a.get("super_enabled"):
                        lines.append(
                            f"  🔥 TERZO {n1:02d}-{n2:02d} SUPER ON | support_sum={int(a.get('support_sum',0))} ≥ {MULTI_SUPER_GATE}"
                        )
                    else:
                        lines.append(
                            f"  🔺 TERZO {n1:02d}-{n2:02d} TRIANGLE SHADOW | support_sum={int(a.get('support_sum',0))} < {MULTI_SUPER_GATE}"
                        )

        lines += [
            "",
            "🧪 STANDARD resta shadow/control e NON arma ambi/SUPER.",
            "🔥 A invariato; 🟠 B aggiunge segnali senza modificare A.",
            "🔺 TRIANGLE: terzo lato sempre seguito su A/B; OFF-gate resta shadow.",
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
                tag = "⚡ AMBO2 FAST" if tier == "A" else "🔗 AMBO2"
            status = f"✅ HIT al colpo H{age}" if ev.get("hit_now") else "🛑 STOP H5"
            tier_line = "\n🔥 PRIME A" if tier == "A" else ("\n🟠 PRIME B" if tier == "B" else "")
            fast_note = "\n🎯 FAST H1 centrato." if tier == "A" and slot == "BASE2" and age == 1 and ev.get("hit_now") else ""
            off_note = "\n👁️ Era OFF-gate: hit registrato solo come TRIANGLE SHADOW." if slot == "TRIANGLE_OFF" and ev.get("hit_now") else ""
            return (
                f"🧾 MULTI v20.5.1 — {tag}\n\n"
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
        elif tier == "B":
            title = "🟠 MULTI PRIME B — ESITO AMBATA"
        else:
            title = "🧾 MULTI STANDARD — ESITO AMBATA"
        return (
            f"{title}\n\n"
            f"Origine {r.get('origin_key')} | numero {n:02d}\n{status}\n"
            f"BD rank={r.get('bd_rank')} | ED rank={r.get('ed_rank')} | O2 rank={r.get('o2_rank')}\n"
            f"Base rit={r.get('base_gap')} | Extra rit={r.get('extra_gap')} | Oro2 freq80={r.get('o2_freq80')}"
        )

    def should_notify_event(self, ev):
        if not ev or not isinstance(ev.get("row"), dict):
            return False
        r = ev["row"]
        tier = self._tier_from_obj(r)
        kind = str(ev.get("kind") or "")
        slot = str(r.get("slot") or "")

        if tier == "A":
            if kind == "ambata":
                return NOTIFY_PRIME_A_RESULT
            if slot in {"BASE1", "BASE2", "SUPER"}:
                return NOTIFY_PRIME_A_RESULT
            if slot == "TRIANGLE_OFF":
                return bool(ev.get("hit_now")) and NOTIFY_TRIANGLE_OFF_HIT
        elif tier == "B":
            # B: notifico l'ambata; tutti gli ambi B restano shadow per ora.
            return kind == "ambata" and NOTIFY_PRIME_B_RESULT
        else:
            # STANDARD completamente silenzioso.
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

    def text(self):
        n, h1, h3, h5 = self._stats(None)
        an, ah1, ah3, ah5 = self._stats("A")
        bn, bh1, bh3, bh5 = self._stats("B")
        a1n, a1h1, a1h3, a1h5 = self._ambo_stats({"BASE1"}, "A")
        a2n, a2h1, a2h3, a2h5 = self._ambo_stats({"BASE2"}, "A")
        b1n, b1h1, b1h3, b1h5 = self._ambo_stats({"BASE1"}, "B")
        b2n, b2h1, b2h3, b2h5 = self._ambo_stats({"BASE2"}, "B")
        asn, ash1, ash3, ash5 = self._ambo_stats({"SUPER"}, "A")
        bsn, bsh1, bsh3, bsh5 = self._ambo_stats({"SUPER"}, "B")
        ton, toh1, toh3, toh5 = asn+bsn, ash1+bsh1, ash3+bsh3, ash5+bsh5
        aoffn, aoffh1, aoffh3, aoffh5 = self._ambo_stats({"TRIANGLE_OFF"}, "A")
        boffn, boffh1, boffh3, boffh5 = self._ambo_stats({"TRIANGLE_OFF"}, "B")
        acov = self._origin_coverage("A")
        bcov = self._origin_coverage("B")
        apa, apam = self._pending_counts("A")
        bpa, bpam = self._pending_counts("B")

        lines = [
            "🧪 MULTI PRIME A+B — v20.5.1 MULTI-ONLY",
            "STANDARD shadow: BD12 ∩ ED12 ∩ O2F12",
            f"🔥 A: BD rank 11-12 + O2 rank {PRIME_A_O2_RANK_MIN}-{PRIME_A_O2_RANK_MAX}",
            f"🟠 B: BD rank 11-12 + O2 rank {PRIME_B_O2_RANK_MIN}-{PRIME_B_O2_RANK_MAX}",
            f"Oro2 W{MULTI_WINDOW} | cooldown {MULTI_COOLDOWN} | COOC W{MULTI_COOC_WINDOW} | H{MULTI_HORIZON}",
            "",
            f"📚 Storico MULTI {len(self.history)} | scan {self.scans} | STD {self.signals} | cooldown skip {self.cooldown_skips}",
            f"STANDARD chiusi {n} | H1 {h1}/{n} ({safe_pct(h1,n):.2f}%) | H3 {h3}/{n} ({safe_pct(h3,n):.2f}%) | H5 {h5}/{n} ({safe_pct(h5,n):.2f}%)",
            "",
            f"🔥 PRIME A — start {self.prime_a_started_from_key or '-'} | creati {self.prime_a_signals} | pending {apa}",
            f"AMBATA A: H1 {ah1}/{an} ({safe_pct(ah1,an):.2f}%) | H3 {ah3}/{an} ({safe_pct(ah3,an):.2f}%) | H5 {ah5}/{an} ({safe_pct(ah5,an):.2f}%)",
            f"A AMBO1: H1 {a1h1}/{a1n} ({safe_pct(a1h1,a1n):.2f}%) | H5 {a1h5}/{a1n} ({safe_pct(a1h5,a1n):.2f}%)",
            f"A AMBO2 FAST: H1 {a2h1}/{a2n} ({safe_pct(a2h1,a2n):.2f}%) | H5 {a2h5}/{a2n} ({safe_pct(a2h5,a2n):.2f}%)",
            f"A origini ≥1 BASE: {acov['base_hit']}/{acov['base_n']} ({safe_pct(acov['base_hit'],acov['base_n']):.2f}%) | ≥1 dei 3 lati: {acov['all3_hit']}/{acov['tri_n']} ({safe_pct(acov['all3_hit'],acov['tri_n']):.2f}%) | rescue terzo {acov['rescue']}",
            f"A TRIANGLE OFF: H1 {aoffh1}/{aoffn} ({safe_pct(aoffh1,aoffn):.2f}%) | H5 {aoffh5}/{aoffn} ({safe_pct(aoffh5,aoffn):.2f}%) | pending ambi {apam}",
            "",
            f"🟠 PRIME B — start {self.prime_b_started_from_key or '-'} | creati {self.prime_b_signals} | pending {bpa}",
            f"AMBATA B: H1 {bh1}/{bn} ({safe_pct(bh1,bn):.2f}%) | H3 {bh3}/{bn} ({safe_pct(bh3,bn):.2f}%) | H5 {bh5}/{bn} ({safe_pct(bh5,bn):.2f}%)",
            f"B AMBO1 shadow: H1 {b1h1}/{b1n} ({safe_pct(b1h1,b1n):.2f}%) | H5 {b1h5}/{b1n} ({safe_pct(b1h5,b1n):.2f}%)",
            f"B AMBO2 shadow: H1 {b2h1}/{b2n} ({safe_pct(b2h1,b2n):.2f}%) | H5 {b2h5}/{b2n} ({safe_pct(b2h5,b2n):.2f}%)",
            f"B origini ≥1 BASE: {bcov['base_hit']}/{bcov['base_n']} ({safe_pct(bcov['base_hit'],bcov['base_n']):.2f}%) | ≥1 dei 3 lati: {bcov['all3_hit']}/{bcov['tri_n']} ({safe_pct(bcov['all3_hit'],bcov['tri_n']):.2f}%) | rescue terzo {bcov['rescue']}",
            f"B TRIANGLE OFF: H1 {boffh1}/{boffn} ({safe_pct(boffh1,boffn):.2f}%) | H5 {boffh5}/{boffn} ({safe_pct(boffh5,boffn):.2f}%) | pending ambi {bpam}",
            "",
            f"🔥 SUPER ON (solo PRIME A+B): H1 {toh1}/{ton} ({safe_pct(toh1,ton):.2f}%) | H3 {toh3}/{ton} ({safe_pct(toh3,ton):.2f}%) | H5 {toh5}/{ton} ({safe_pct(toh5,ton):.2f}%)",
            f"🔺 TRIANGLE tracking da {self.triangle_started_from_key or '-'} — nessun backfill OFF.",
            "Baseline: ambata H1 22.22% | ambo H1 ≈4.74% | ambo H5 ≈21.57%.",
            "",
            "⏸️ FOCUS / INCROCIO / CORE / legacy: PAUSATI; state conservato.",
        ]
        if self.pending:
            lines.append(
                "Pending ambate: " + ", ".join(
                    f"{self._tier_from_obj(x)}:{int(x['num']):02d}@H{int(x.get('age',0))+1}"
                    for x in self.pending[-12:]
                )
            )
        if self.last_signal:
            lines.append(
                "Ultimo segnale: " + str(self.last_signal.get("origin_key")) + " → "
                + " ".join(f"{int(n):02d}" for n in self.last_signal.get("numbers", []))
            )
        return "\n".join(lines)


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
        self.state_revision = 0
        self.state_load_info = {"loaded": False, "path": None, "reason": "not-run", "source": "-"}
        self.load_state()

    def load_state(self):
        ff_status = _fast_forward_repo_to_remote()
        local_path = STATE_FILE if os.path.exists(STATE_FILE) else (LEGACY_STATE_FILE if os.path.exists(LEGACY_STATE_FILE) else None)
        local_data = _read_json_file(local_path) if local_path else None
        remote_data, remote_src = _fetch_remote_state()
        data, source = _best_available_state(local_data, remote_data)

        if not isinstance(data, dict):
            self.state_load_info = {
                "loaded": False, "path": local_path, "reason": "state assente/non leggibile", "source": source,
            }
            return False
        try:
            # v20.5.1: materializza sempre la fusione LOCAL+REMOTE.
            atomic_write_json(STATE_FILE, data)
            local_path = STATE_FILE

            self.raw_state = data
            self.state_revision = max(0, int(data.get("multi_state_revision", 0) or 0))
            self.processed = [str(x) for x in data.get("processed", []) if isinstance(x, str)][-PROCESSED_MAX:]
            self.processed_set = set(self.processed)
            self.last_draw_key = data.get("last_draw_key") if isinstance(data.get("last_draw_key"), str) else None
            loaded_multi = self.multichannel.load(data.get("multichannel_bd12_ed12_o2f12_v1"))
            self.state_load_info = {
                "loaded": bool(loaded_multi),
                "path": local_path or remote_src,
                "reason": "OK" if loaded_multi else "MULTI state assente/incompatibile",
                "source": source,
                "remote": remote_src, "ff": ff_status,
            }
            console_log(
                f"STATE CARICATO | ff={ff_status} | source={source} | rev={self.state_revision} | "
                f"MULTI history={len(self.multichannel.history)} | "
                f"A start={self.multichannel.prime_a_started_from_key or '-'} | "
                f"B start={self.multichannel.prime_b_started_from_key or '-'}"
            )
            return bool(loaded_multi)
        except Exception as exc:
            self.state_load_info = {
                "loaded": False, "path": local_path, "reason": f"{type(exc).__name__}: {exc}", "source": source,
            }
            console_log(f"STATE LOAD FAIL | {self.state_load_info['reason']}")
            return False

    def save_state(self, git=True, force_git=False):
        data = dict(self.raw_state) if isinstance(self.raw_state, dict) else {}
        self.state_revision += 1
        data["saved_at"] = now_dt().isoformat(timespec="seconds")
        data["multi_state_revision"] = int(self.state_revision)
        data["processed"] = self.processed[-PROCESSED_MAX:]
        data["last_draw_key"] = self.last_draw_key
        data["multichannel_bd12_ed12_o2f12_v1"] = self.multichannel.dump()
        data["active_mode"] = "MULTI_PRIME_AB_TRIANGLE_v20.5.1"
        remote_data, _ = _fetch_remote_state() if git and PERSIST_GIT_STATE else (None, "disabled")
        merged, _ = _merge_state_data(data, remote_data)
        if isinstance(merged, dict):
            data = merged
            self.state_revision = max(self.state_revision, int(data.get("multi_state_revision", 0) or 0))
            self.multichannel.load(data.get("multichannel_bd12_ed12_o2f12_v1"))
            self.processed = [str(x) for x in data.get("processed", []) if isinstance(x, str)][-PROCESSED_MAX:]
            self.processed_set = set(self.processed)
            if isinstance(data.get("last_draw_key"), str): self.last_draw_key = data.get("last_draw_key")
        atomic_write_json(STATE_FILE, data)
        self.raw_state = data
        if git:
            st = git_commit_state_if_needed(force=force_git)
            if not st.get("ok", False): console_log(f"STATE GIT WARNING | {st.get('action')} | {st.get('detail','')}")
            return st
        return {"ok": True, "action": "local-only", "detail": "state scritto"}

    async def tg(self, app, text):
        if not app or CHAT_ID is None or not text:
            return
        try:
            await app.bot.send_message(chat_id=CHAT_ID, text=str(text))
        except Exception as exc:
            console_log(f"TELEGRAM FAIL | {type(exc).__name__}: {exc}")

    def status_text(self):
        mc = self.multichannel
        return (
            "📡 STATUS v20.5.1 MULTI PRIME A+B FIX\n\n"
            f"Ultimo MULTI: {mc.history[-1]['key'] if mc.history else '-'}\n"
            f"State: {'OK' if self.state_load_info.get('loaded') else 'NUOVO'} | {self.state_load_info.get('reason')}\n"
            f"State source: {self.state_load_info.get('source','-')} | ff {self.state_load_info.get('ff','-')} | rev {self.state_revision}\n"
            f"History MULTI: {len(mc.history)}/{MULTI_HISTORY_MAX}\n"
            f"PRIME A start: {mc.prime_a_started_from_key or '-'}\n"
            f"PRIME B start: {mc.prime_b_started_from_key or '-'}\n"
            f"TRIANGLE start: {mc.triangle_started_from_key or '-'}\n\n"
            "✅ Attivo: MULTI BD/ED/O2 + PRIME A + PRIME B + TRIANGLE SHADOW\n"
            "⏸️ FOCUS / INCROCIO / CORE / legacy: congelati nello state.\n\n"
            + mc.text()
        )

    @staticmethod
    def menu_text():
        return (
            "🎯 10eLOTTO v20.5 — MULTI PRIME A+B\n\n"
            "ATTIVO:\n"
            "• STANDARD BD12∩ED12∩O2F12 shadow/control\n"
            f"• 🔥 PRIME A: BD11-12 + O2 rank {PRIME_A_O2_RANK_MIN}-{PRIME_A_O2_RANK_MAX}\n"
            f"• 🟠 PRIME B: BD11-12 + O2 rank {PRIME_B_O2_RANK_MIN}-{PRIME_B_O2_RANK_MAX}\n"
            "• A: AMBO1 + AMBO2 FAST monitorati\n"
            "• B: ambi solo shadow\n"
            f"• SUPER ON se support_sum≥{MULTI_SUPER_GATE}\n"
            "• TRIANGLE OFF-gate sempre shadow su A/B\n\n"
            "PAUSATI (state conservato): FOCUS, INCROCIO, CORE e tutti i legacy.\n\n"
            "/multi — statistiche complete A/B/TRIANGLE\n"
            "/status — feed + state + statistiche\n"
            "/verificatutto — audit completo\n"
            "/menu — comandi"
        )


# ============================================================
# SYNC / TELEGRAM
# ============================================================
async def reply(update, text):
    if update and update.message:
        await update.message.reply_text(text)


async def cmd_multi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].multichannel.text())


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].status_text())


async def cmd_verificatutto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].status_text())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, context.application.bot_data["engine"].menu_text())


async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("multi", "MULTI BD/ED/O2 + PRIME A/B + TRIANGLE"),
        BotCommand("status", "Stato MULTI A/B + feed/state"),
        BotCommand("verificatutto", "Audit MULTI A/B/TRIANGLE"),
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
        # Nessun segnale sui draw già noti al bootstrap: il prossimo draw sarà il primo forward reale.
        engine.save_state(git=True, force_git=True)
        return {"rows": len(rows), "unseen": 0, "signal": None, "events": [], "bootstrapped": True}

    unseen = [r for r in rows if not mc.seen(r.get("key"))]
    unseen.sort(key=lambda r: order_key(r.get("key")) or (-1, -1))

    # Catch-up: incorporiamo tutti i draw già avvenuti senza inventare segnali retroattivi.
    # Solo dopo l'ultimo draw noto armiamo un segnale realmente futuro.
    for r in unseen:
        evs = mc.ingest(r)
        events.extend(evs)
        if notify:
            for ev in evs:
                if mc.should_notify_event(ev):
                    msg = mc.result_text(ev)
                    if msg:
                        await engine.tg(app, msg)

    mc.ensure_start()
    sig = mc.arm() if mc.history else None
    if sig and notify and mc.should_notify_signal(sig):
        msg = mc.signal_text(sig)
        if msg:
            await engine.tg(app, msg)

    if unseen or sig or events:
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
            mc.ingest(r)
        mc.ensure_start()

    # Congela SOLO ora il segnale sulla più recente estrazione disponibile.
    sig = mc.arm() if mc.history else None
    engine.last_draw_key = mc.history[-1]["key"] if mc.history else engine.last_draw_key
    engine.save_state(git=True, force_git=True)

    await engine.tg(
        app,
        "🚀 MULTI BD12+ED12+O2F12 — v20.5.1 PRIME A+B FIX AVVIATO\n\n"
        "🧪 STANDARD: BD12 ∩ ED12 ∩ O2F12 W80, cooldown 5 — SHADOW/control.\n"
        f"🔥 PRIME A: BD rank 11-12 + O2 rank {PRIME_A_O2_RANK_MIN}-{PRIME_A_O2_RANK_MAX} — invariato, qualità massima.\n"
        f"🟠 PRIME B: BD rank 11-12 + O2 rank {PRIME_B_O2_RANK_MIN}-{PRIME_B_O2_RANK_MAX} — più segnali, ambata H1.\n"
        "🔗 A: AMBO1 + AMBO2 FAST; B: ambi solo shadow.\n"
        f"🔥 SUPER ON se support_sum≥{MULTI_SUPER_GATE}; 🔺 TRIANGLE OFF sempre shadow su A/B.\n"
        "🛡️ State v20.5.1: merge LOCAL+REMOTE + push esplicito sul branch; contatori monotoni.\n\n"
        "⏸️ FOCUS / INCROCIO / CORE / ENGINE / SOSIA / legacy: PAUSATI.\n"
        "✅ Il loro state viene conservato ma NON aggiornato.\n"
        "🚫 Nessun backfill PRIME B/TRIANGLE.\n\n"
        "Comandi: /multi /status /verificatutto /menu"
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
        f"MULTI PRIME A+B FIX LIVE | poll={LOOP_SEC}s | rotation={BOT_MAX_RUNTIME_SECONDS}s"
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
                    "♻️ MULTI PRIME A+B FIX — ROTAZIONE RUNNER\n"
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
                    "⚠️ MULTI PRIME A+B — ERRORE\n"
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
    # --- PRIME A + TRIANGLE OFF rescue ---
    mc = _selftest_seed_mc()
    bd = [1,2,3,4,5,6,7,8,9,10,42,43]
    ed = [42,12,13,14,15,16,17,18,19,20,21,22]
    o2 = [50,51,52,53,54,42,55,56,57,58,59,60]  # 42 = O2 rank 6 => A
    mc._rankings = lambda: {
        "base_gap": {n: (100-n if n != 42 else 30) for n in range(1,91)},
        "extra_gap": {n: (100-n if n != 42 else 25) for n in range(1,91)},
        "o2_freq": {n: (20 if n in o2 else 0) for n in range(1,91)},
        "top_base_delay": bd, "top_extra_delay": ed, "top_o2": o2,
    }
    mc._partner_plan = lambda main, ranks: {
        "main": int(main),
        "p1": {"num": 50, "cooc": 30, "support": 1, "in_bd12": False, "in_ed12": False, "o2_freq80": 20},
        "p2": {"num": 51, "cooc": 28, "support": 2, "in_bd12": True, "in_ed12": False, "o2_freq80": 20},
        "support_sum": 3, "super_enabled": False, "cooc_window": 900,
    }
    sig = mc.arm()
    assert sig and sig["prime_a_numbers"] == [42] and not sig["prime_b_numbers"], sig
    assert mc.prime_a_signals == 1
    assert len(mc.ambo_pending) == 3
    assert {x["slot"] for x in mc.ambo_pending} == {"BASE1", "BASE2", "TRIANGLE_OFF"}
    assert all(x.get("tier") == "A" for x in mc.ambo_pending)

    next_day = mc.history[-1]["day"]
    next_id = mc.history[-1]["draw_id"] + 1
    # 50-51 insieme, ma senza 42: il terzo lato OFF centra H1 e salva la terna.
    nums = [50, 51] + [n for n in range(1, 91) if n not in {42,50,51}][:18]
    extra = [n for n in range(1,91) if n not in set(nums)][:15]
    evs = mc.ingest({"key": draw_key(next_day, next_id), "day": next_day, "draw_id": next_id,
                     "nums": nums, "oro": 50, "doppio_oro": 51, "extra": extra})
    tev = [e for e in evs if e["kind"] == "ambo" and e["row"].get("slot") == "TRIANGLE_OFF"]
    assert tev and tev[0]["hit_now"] and int(tev[0]["row"]["hit_colpo"]) == 1

    # --- PRIME B disgiunto da A ---
    mb = _selftest_seed_mc()
    bd2 = [1,2,3,4,5,6,7,8,9,10,11,43]       # 43 = BD rank 12
    ed2 = [43,12,13,14,15,16,17,18,19,20,21,22]
    o22 = [60,61,43,62,63,64,65,66,67,68,69,70]  # 43 = O2 rank 3 => B
    mb._rankings = lambda: {
        "base_gap": {n: (100-n if n != 43 else 29) for n in range(1,91)},
        "extra_gap": {n: (100-n if n != 43 else 24) for n in range(1,91)},
        "o2_freq": {n: (20 if n in o22 else 0) for n in range(1,91)},
        "top_base_delay": bd2, "top_extra_delay": ed2, "top_o2": o22,
    }
    mb._partner_plan = lambda main, ranks: {
        "main": int(main),
        "p1": {"num": 60, "cooc": 31, "support": 1, "in_bd12": False, "in_ed12": False, "o2_freq80": 20},
        "p2": {"num": 61, "cooc": 27, "support": 1, "in_bd12": False, "in_ed12": False, "o2_freq80": 20},
        "support_sum": 2, "super_enabled": False, "cooc_window": 900,
    }
    sigb = mb.arm()
    assert sigb and sigb["prime_b_numbers"] == [43] and not sigb["prime_a_numbers"], sigb
    assert mb.prime_b_signals == 1
    assert len(mb.ambo_pending) == 3 and all(x.get("tier") == "B" for x in mb.ambo_pending)

    # Dump/load preserva A/B/TRIANGLE e migrazione legacy A.
    rt = MultiPrimeV1()
    assert rt.load(mc.dump())
    assert rt.prime_a_signals == 1
    assert rt.triangle_started_from_key

    legacy = mc.dump()
    legacy.pop("prime_a_started_from_key", None)
    legacy.pop("prime_a_started_at", None)
    legacy.pop("prime_a_signals", None)
    legacy["prime_started_from_key"] = mc.prime_a_started_from_key
    legacy["prime_started_at"] = mc.prime_a_started_at
    legacy["prime_signals"] = 7
    mig = MultiPrimeV1()
    assert mig.load(legacy) and mig.prime_a_signals == 7

    ms=MultiPrimeV1(); ms.history=list(mc.history); ms._refresh_keys(); ms.draw_seq=mc.draw_seq; ms.ensure_start()
    ms._rankings=lambda:{"base_gap":{n:(30 if n==44 else 1) for n in range(1,91)},"extra_gap":{n:(30 if n==44 else 1) for n in range(1,91)},"o2_freq":{n:(10 if n in (44,11,12) else 0) for n in range(1,91)},"top_base_delay":[1,2,3,4,5,6,7,8,9,44,10,11],"top_extra_delay":[44,21,22,23,24,25,26,27,28,29,30,31],"top_o2":[41,42,43,45,46,47,48,49,50,51,44,52]}
    before=len(ms.ambo_pending); ss=ms.arm()
    assert ss and ss["numbers"] == [44] and not ss["prime_a_numbers"] and not ss["prime_b_numbers"]
    assert len(ms.ambo_pending)==before

    la={"multichannel_bd12_ed12_o2f12_v1":mc.dump(),"processed":[],"multi_state_revision":3}
    rb=mb.dump(); rb["prime_b_signals"]=5
    rr={"multichannel_bd12_ed12_o2f12_v1":rb,"processed":[],"multi_state_revision":4}
    mm,_=_merge_state_data(la,rr); mcm=mm["multichannel_bd12_ed12_o2f12_v1"]
    assert int(mcm.get("prime_a_signals",0))>=1 and int(mcm.get("prime_b_signals",0))>=5

    print("SELF-TEST OK: v20.5.1 PRIME A/B + TRIANGLE + state merge + STANDARD pure shadow")


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
