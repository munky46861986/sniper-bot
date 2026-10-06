# ============================================================
# 🎯 10eLOTTO MULTI BD12+ED12+O2F12 — v20.4 MULTI PRIME ONLY
# ============================================================
# UNICO METODO ATTIVO:
#   STANDARD (shadow/control): BD12 ∩ ED12 ∩ O2F12, W80, cooldown 5
#   PRIME v1: STANDARD + BD rank 11-12 + O2 rank 6-12
#
# AMBI:
#   P1/P2 = 2 partner O2F12 con maggiore co-occorrenza Base nei 900 draw precedenti
#   AMBO1 = M-P1 (shadow H1-H5)
#   AMBO2 = M-P2 (PRIME FAST: focus H1; continua shadow H1-H5 per confronto)
#   SUPER = P1-P2 solo support_sum >= 4
#
# FORWARD TEST:
#   - nessun backfill PRIME
#   - vecchio MULTI standard preservato e continua solo come controllo statistico
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

# PRIME v1 — ipotesi congelata dal test storico Jan-Sep 2025.
PRIME_VERSION = 1
PRIME_BD_RANK_MIN = 11
PRIME_BD_RANK_MAX = 12
PRIME_O2_RANK_MIN = 6
PRIME_O2_RANK_MAX = 12

# Notifiche: di default STANDARD resta shadow/silenzioso; PRIME è operativo.
NOTIFY_PRIME_SIGNAL = os.getenv("MULTI_PRIME_NOTIFY_SIGNAL", "1").lower() not in {"0", "false", "no", "off"}
NOTIFY_PRIME_RESULT = os.getenv("MULTI_PRIME_NOTIFY_RESULT", "1").lower() not in {"0", "false", "no", "off"}
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

    p = _run_git(["push"])
    if p.returncode != 0:
        return {"ok": False, "action": "push-fail", "detail": p.stderr.strip()[-500:]}

    _LAST_GIT_COMMIT_TS = now
    return {"ok": True, "action": "pushed", "detail": msg}


# ============================================================
# MULTI BD12 + ED12 + O2F12 + PRIME v1
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

        # PRIME: parte solo dal primo nuovo segnale dopo upgrade v20.4.
        self.prime_version = PRIME_VERSION
        self.prime_started_from_key = None
        self.prime_started_at = None
        self.prime_signals = 0

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
            "key": key,
            "day": day,
            "draw_id": draw_id,
            "nums": nums,
            "oro": oro,
            "doppio_oro": doppio,
            "extra": extra,
        }

    @staticmethod
    def _sanitize_ambo_row(row):
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
        q["prime"] = bool(q.get("prime", False))
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
        changed = False
        if not self.start_from_key:
            self.start_from_key = str(self.history[-1]["key"])
            self.started_at = now_dt().isoformat(timespec="seconds")
            changed = True
        if not self.ambo_started_from_key:
            self.ambo_started_from_key = str(self.history[-1]["key"])
            self.ambo_started_at = now_dt().isoformat(timespec="seconds")
            changed = True
        if not self.prime_started_from_key:
            # CRITICO: impedisce qualunque ricostruzione PRIME sul passato.
            self.prime_started_from_key = str(self.history[-1]["key"])
            self.prime_started_at = now_dt().isoformat(timespec="seconds")
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
        self.pending = [dict(x) for x in obj.get("pending", []) if isinstance(x, dict) and x.get("origin_key")][-200:]
        self.records = [dict(x) for x in obj.get("records", []) if isinstance(x, dict) and x.get("origin_key")][-MULTI_RECORD_MAX:]
        self.draw_seq = max(int(obj.get("draw_seq", 0) or 0), len(self.history))

        raw = obj.get("last_signal_seq", {})
        self.last_signal_seq = {
            int(k): int(v)
            for k, v in raw.items()
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
        self.ambo_pending = [q for x in obj.get("ambo_pending", []) if (q := self._sanitize_ambo_row(x))][-600:]
        self.ambo_records = [q for x in obj.get("ambo_records", []) if (q := self._sanitize_ambo_row(x))][-MULTI_AMBO_RECORD_MAX:]
        self.ambo_origins = max(0, int(obj.get("ambo_origins", 0) or 0))
        self.ambo_super_signals = max(0, int(obj.get("ambo_super_signals", 0) or 0))
        self.last_ambo_signal = obj.get("last_ambo_signal") if isinstance(obj.get("last_ambo_signal"), dict) else None
        self.last_ambo_result = obj.get("last_ambo_result") if isinstance(obj.get("last_ambo_result"), dict) else None

        # Nuovi campi PRIME. Se mancanti: marker adesso, ZERO backfill.
        psk = obj.get("prime_started_from_key")
        self.prime_started_from_key = str(psk) if order_key(psk) is not None else None
        self.prime_started_at = obj.get("prime_started_at") if isinstance(obj.get("prime_started_at"), str) else None
        self.prime_signals = max(0, int(obj.get("prime_signals", 0) or 0))
        if not self.prime_started_from_key and self.history:
            self.prime_started_from_key = str(self.history[-1]["key"])
            self.prime_started_at = now_dt().isoformat(timespec="seconds")
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
            "ambo_version": 1,
            "ambo_started_from_key": self.ambo_started_from_key,
            "ambo_started_at": self.ambo_started_at,
            "ambo_pending": self.ambo_pending[-600:],
            "ambo_records": self.ambo_records[-MULTI_AMBO_RECORD_MAX:],
            "ambo_origins": self.ambo_origins,
            "ambo_super_signals": self.ambo_super_signals,
            "last_ambo_signal": self.last_ambo_signal,
            "last_ambo_result": self.last_ambo_result,
            "prime_version": PRIME_VERSION,
            "prime_started_from_key": self.prime_started_from_key,
            "prime_started_at": self.prime_started_at,
            "prime_signals": self.prime_signals,
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
            "base_gap": base_gap,
            "extra_gap": extra_gap,
            "o2_freq": o2_freq,
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
    def _is_prime(bd_rank, o2_rank):
        return (
            bd_rank is not None
            and o2_rank is not None
            and PRIME_BD_RANK_MIN <= int(bd_rank) <= PRIME_BD_RANK_MAX
            and PRIME_O2_RANK_MIN <= int(o2_rank) <= PRIME_O2_RANK_MAX
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
                "num": p,
                "cooc": int(cooc),
                "support": int(support),
                "in_bd12": bool(p in bset),
                "in_ed12": bool(p in eset),
                "o2_freq80": int(ranks["o2_freq"].get(p, 0)),
            })
        scored.sort(key=lambda x: (-x["cooc"], x["num"]))
        p1, p2 = scored[0], scored[1]
        support_sum = int(p1["support"] + p2["support"])
        return {
            "main": int(main),
            "p1": p1,
            "p2": p2,
            "support_sum": support_sum,
            "super_enabled": bool(support_sum >= MULTI_SUPER_GATE),
            "cooc_window": min(len(hw), MULTI_COOC_WINDOW),
        }

    def _arm_ambo(self, origin_key, main, plan, prime=False, bd_rank=None, o2_rank=None):
        if not plan:
            return []
        origin_id = f"{origin_key}|M{int(main):02d}"
        p1 = int(plan["p1"]["num"])
        p2 = int(plan["p2"]["num"])
        specs = [("BASE1", sorted([int(main), p1])), ("BASE2", sorted([int(main), p2]))]
        if plan.get("super_enabled"):
            specs.append(("SUPER", sorted([p1, p2])))

        created = []
        for slot, pair in specs:
            q = {
                "origin_key": str(origin_key),
                "origin_id": origin_id,
                "main": int(main),
                "slot": slot,
                "pair": pair,
                "age": 0,
                "hit": False,
                "hit_colpo": None,
                "created_at": now_txt(),
                "p1": p1,
                "p2": p2,
                "p1_cooc": int(plan["p1"]["cooc"]),
                "p2_cooc": int(plan["p2"]["cooc"]),
                "p1_support": int(plan["p1"]["support"]),
                "p2_support": int(plan["p2"]["support"]),
                "support_sum": int(plan["support_sum"]),
                "cooc_window": int(plan["cooc_window"]),
                "prime": bool(prime),
                "bd_rank": bd_rank,
                "o2_rank": o2_rank,
            }
            self.ambo_pending.append(q)
            created.append(dict(q))

        self.ambo_pending = self.ambo_pending[-600:]
        self.ambo_origins += 1
        if plan.get("super_enabled"):
            self.ambo_super_signals += 1
        self.last_ambo_signal = {
            "origin_key": str(origin_key),
            "origin_id": origin_id,
            "main": int(main),
            "p1": dict(plan["p1"]),
            "p2": dict(plan["p2"]),
            "support_sum": int(plan["support_sum"]),
            "super_enabled": bool(plan.get("super_enabled")),
            "prime": bool(prime),
            "bd_rank": bd_rank,
            "o2_rank": o2_rank,
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
            age = int(q.get("age", 0) or 0) + 1
            q["age"] = age
            q["last_key"] = r["key"]
            pair = [int(x) for x in q.get("pair", [])]
            hit_now = (
                (not q.get("hit"))
                and len(pair) == 2
                and pair[0] in actual
                and pair[1] in actual
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
        selected = []
        blocked = []
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

        details = []
        ambo_plans = []
        prime_numbers = []
        for n in selected:
            bd_rank = self._rank_of(n, ranks["top_base_delay"])
            ed_rank = self._rank_of(n, ranks["top_extra_delay"])
            o2_rank = self._rank_of(n, ranks["top_o2"])
            is_prime = self._is_prime(bd_rank, o2_rank)
            if is_prime:
                prime_numbers.append(int(n))
                self.prime_signals += 1

            d = {
                "num": n,
                "base_gap": int(ranks["base_gap"][n]),
                "extra_gap": int(ranks["extra_gap"][n]),
                "o2_freq80": int(ranks["o2_freq"][n]),
                "bd_rank": bd_rank,
                "ed_rank": ed_rank,
                "o2_rank": o2_rank,
                "prime": bool(is_prime),
            }
            plan = self._partner_plan(n, ranks)
            if plan:
                d["ambo"] = {
                    "p1": dict(plan["p1"]),
                    "p2": dict(plan["p2"]),
                    "support_sum": int(plan["support_sum"]),
                    "super_enabled": bool(plan["super_enabled"]),
                    "cooc_window": int(plan["cooc_window"]),
                }
                self._arm_ambo(
                    origin_key, n, plan,
                    prime=is_prime,
                    bd_rank=bd_rank,
                    o2_rank=o2_rank,
                )
                ambo_plans.append({"main": n, "prime": bool(is_prime), **d["ambo"]})

            details.append(d)
            self.pending.append({
                "origin_key": origin_key,
                "num": n,
                "age": 0,
                "hit": False,
                "hit_colpo": None,
                "created_at": now_txt(),
                "base_gap": d["base_gap"],
                "extra_gap": d["extra_gap"],
                "o2_freq80": d["o2_freq80"],
                "bd_rank": bd_rank,
                "ed_rank": ed_rank,
                "o2_rank": o2_rank,
                "prime": bool(is_prime),
            })
            self.last_signal_seq[n] = self.draw_seq

        self.pending = self.pending[-200:]
        self.signals += len(selected)
        out = {
            "origin_key": origin_key,
            "numbers": selected,
            "prime_numbers": prime_numbers,
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
    def has_prime(sig):
        return bool(sig and sig.get("prime_numbers"))

    def should_notify_signal(self, sig):
        if not sig:
            return False
        return (self.has_prime(sig) and NOTIFY_PRIME_SIGNAL) or NOTIFY_STANDARD_SIGNAL

    @staticmethod
    def signal_text(sig):
        if not sig:
            return None
        prime_nums = {int(x) for x in sig.get("prime_numbers", [])}
        lines = [
            "🧪 MULTI BD12+ED12+O2F12 — v20.4",
            "Origine: " + str(sig.get("origin_key")),
            "STANDARD: Base RIT12 ∩ Extra RIT12 ∩ Oro2 FREQ12 (W80)",
            f"Segnali standard: {' '.join(f'{int(n):02d}' for n in sig.get('numbers', []))}",
        ]
        if prime_nums:
            lines += [
                "",
                "🔥 MULTI PRIME v1 — SEGNALE FORWARD",
                f"🎯 PRIME H1: {' '.join(f'{n:02d}' for n in sorted(prime_nums))}",
                f"Gate congelato: BD rank {PRIME_BD_RANK_MIN}-{PRIME_BD_RANK_MAX} + O2 rank {PRIME_O2_RANK_MIN}-{PRIME_O2_RANK_MAX}",
            ]
        else:
            lines += ["", "🌑 Nessun PRIME in questa origine; STANDARD registrato in shadow."]

        lines.append("")
        for d in sig.get("details", []):
            n = int(d["num"])
            tag = "🔥 PRIME" if d.get("prime") else "• STD"
            lines.append(
                f"{tag} {n:02d}: BD rank={d.get('bd_rank')} rit={d.get('base_gap')} | "
                f"ED rank={d.get('ed_rank')} rit={d.get('extra_gap')} | "
                f"O2 rank={d.get('o2_rank')} freq80={d.get('o2_freq80')}"
            )
            a = d.get("ambo") or {}
            if a:
                p1 = a.get("p1") or {}
                p2 = a.get("p2") or {}
                n1 = int(p1.get("num", 0))
                n2 = int(p2.get("num", 0))
                lines.append(
                    f"  🔗 AMBO1 {n:02d}-{n1:02d} | "
                    f"⚡ AMBO2 {'FAST H1 ' if d.get('prime') else ''}{n:02d}-{n2:02d} | "
                    f"COOC900 {p1.get('cooc',0)}/{p2.get('cooc',0)}"
                )
                if a.get("super_enabled"):
                    lines.append(
                        f"  🔥 SUPER {n1:02d}-{n2:02d} ATTIVO | "
                        f"support_sum={int(a.get('support_sum',0))} ≥ {MULTI_SUPER_GATE}"
                    )
                else:
                    lines.append(
                        f"  💤 SUPER {n1:02d}-{n2:02d} OFF | "
                        f"support_sum={int(a.get('support_sum',0))} < {MULTI_SUPER_GATE}"
                    )

        lines += [
            "",
            "🧪 STANDARD continua in shadow come controllo; PRIME parte senza backfill.",
            "⚡ PRIME AMBO2 FAST: focus operativo H1; H2-H5 restano registrati solo per confronto.",
            "⏸️ FOCUS / INCROCIO / CORE / legacy non vengono aggiornati.",
        ]
        return "\n".join(lines)

    @staticmethod
    def result_text(ev):
        if not ev or not isinstance(ev.get("row"), dict):
            return None
        r = ev["row"]
        age = int(r.get("age", 0) or 0)
        prime = bool(r.get("prime", False))

        if ev.get("kind") == "ambo":
            pair = [int(x) for x in r.get("pair", [])]
            slot = str(r.get("slot") or "AMBO")
            if len(pair) != 2:
                return None
            if slot == "SUPER":
                tag = "🔥 SUPER"
            elif slot == "BASE1":
                tag = "🔗 AMBO1"
            else:
                tag = "⚡ AMBO2 FAST" if prime else "🔗 AMBO2"
            status = f"✅ HIT al colpo H{age}" if ev.get("hit_now") else "🛑 STOP H5"
            prime_line = (
                f"\n🔥 PRIME | BD rank={r.get('bd_rank')} | O2 rank={r.get('o2_rank')}"
                if prime else ""
            )
            fast_note = "\n🎯 FAST H1 centrato." if prime and slot == "BASE2" and age == 1 and ev.get("hit_now") else ""
            return (
                f"🧾 MULTI v20.4 — {tag}\n\n"
                f"Origine {r.get('origin_key')} | M {int(r.get('main',0)):02d}\n"
                f"Coppia {pair[0]:02d}-{pair[1]:02d} | {status}"
                f"{prime_line}{fast_note}\n"
                f"support_sum={r.get('support_sum')} | COOC900 P1/P2={r.get('p1_cooc')}/{r.get('p2_cooc')}"
            )

        n = int(r.get("num", 0))
        status = (
            f"✅ HIT al colpo H{age}"
            if ev.get("hit_now")
            else ("❌ H1 MISS — shadow fino a H5" if age == 1 else "🛑 STOP H5")
        )
        title = "🔥 MULTI PRIME — ESITO AMBATA" if prime else "🧾 MULTI STANDARD — ESITO AMBATA"
        return (
            f"{title}\n\n"
            f"Origine {r.get('origin_key')} | numero {n:02d}\n"
            f"{status}\n"
            f"BD rank={r.get('bd_rank')} | ED rank={r.get('ed_rank')} | O2 rank={r.get('o2_rank')}\n"
            f"Base rit={r.get('base_gap')} | Extra rit={r.get('extra_gap')} | Oro2 freq80={r.get('o2_freq80')}"
        )

    def should_notify_event(self, ev):
        if not ev or not isinstance(ev.get("row"), dict):
            return False
        r = ev["row"]
        prime = bool(r.get("prime", False))
        if prime:
            # PRIME ambata: H1 è il focus, ma notifico anche eventuale HIT H2-H5
            # perché è utile per il confronto forward. AMBO2 FAST viene evidenziato a H1.
            return NOTIFY_PRIME_RESULT
        if ev.get("kind") == "ambo" and str(r.get("slot")) == "SUPER":
            return NOTIFY_SUPER_RESULT
        return NOTIFY_STANDARD_RESULT

    def _stats(self, prime_only=False):
        rows = [r for r in self.records if (bool(r.get("prime", False)) if prime_only else True)]
        n = len(rows)
        h1 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 1)
        h3 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 3)
        h5 = sum(1 for r in rows if bool(r.get("hit")))
        return n, h1, h3, h5

    def _ambo_stats(self, slots=None, prime_only=False):
        slots = set(slots) if slots is not None else None
        rows = [
            r for r in self.ambo_records
            if (slots is None or str(r.get("slot")) in slots)
            and (bool(r.get("prime", False)) if prime_only else True)
        ]
        n = len(rows)
        h1 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 1)
        h3 = sum(1 for r in rows if int(r.get("hit_colpo") or 99) <= 3)
        h5 = sum(1 for r in rows if bool(r.get("hit")))
        return n, h1, h3, h5

    def _prime_pending_counts(self):
        pa = sum(1 for r in self.pending if bool(r.get("prime", False)))
        pam = sum(1 for r in self.ambo_pending if bool(r.get("prime", False)))
        return pa, pam

    def text(self):
        n, h1, h3, h5 = self._stats(False)
        pn, ph1, ph3, ph5 = self._stats(True)
        b1n, b1h1, b1h3, b1h5 = self._ambo_stats({"BASE1"}, True)
        b2n, b2h1, b2h3, b2h5 = self._ambo_stats({"BASE2"}, True)
        sn, sh1, sh3, sh5 = self._ambo_stats({"SUPER"}, False)
        pa, pam = self._prime_pending_counts()

        lines = [
            "🧪 MULTI PRIME v1 — v20.4 MULTI-ONLY",
            "STANDARD shadow: BD12 ∩ ED12 ∩ O2F12",
            f"PRIME gate: BD rank {PRIME_BD_RANK_MIN}-{PRIME_BD_RANK_MAX} + O2 rank {PRIME_O2_RANK_MIN}-{PRIME_O2_RANK_MAX}",
            f"Oro2 W{MULTI_WINDOW} | cooldown {MULTI_COOLDOWN} | COOC partner W{MULTI_COOC_WINDOW} | horizon shadow H{MULTI_HORIZON}",
            "",
            f"📚 Storico MULTI: {len(self.history)} | scan {self.scans} | segnali STD {self.signals} | cooldown skip {self.cooldown_skips}",
            f"STANDARD chiusi: {n} | H1 {h1}/{n} ({safe_pct(h1,n):.2f}%) | H3 {h3}/{n} ({safe_pct(h3,n):.2f}%) | H5 {h5}/{n} ({safe_pct(h5,n):.2f}%)",
            "",
            "🔥 PRIME FORWARD — nessun backfill",
            f"Partenza PRIME: {self.prime_started_from_key or '-'} | segnali creati {self.prime_signals} | pending ambate {pa}",
            f"AMBATA PRIME: chiusi {pn} | H1 {ph1}/{pn} ({safe_pct(ph1,pn):.2f}%) | H3 {ph3}/{pn} ({safe_pct(ph3,pn):.2f}%) | H5 {ph5}/{pn} ({safe_pct(ph5,pn):.2f}%)",
            "Baseline ambata H1: 22.22%.",
            "",
            f"🔗 PRIME AMBO1 M-P1: H1 {b1h1}/{b1n} ({safe_pct(b1h1,b1n):.2f}%) | H3 {b1h3}/{b1n} ({safe_pct(b1h3,b1n):.2f}%) | H5 {b1h5}/{b1n} ({safe_pct(b1h5,b1n):.2f}%)",
            f"⚡ PRIME AMBO2 FAST M-P2: H1 {b2h1}/{b2n} ({safe_pct(b2h1,b2n):.2f}%) | shadow H3 {b2h3}/{b2n} ({safe_pct(b2h3,b2n):.2f}%) | H5 {b2h5}/{b2n} ({safe_pct(b2h5,b2n):.2f}%)",
            f"🔥 SUPER (gate≥{MULTI_SUPER_GATE}) tutti: H1 {sh1}/{sn} ({safe_pct(sh1,sn):.2f}%) | H3 {sh3}/{sn} ({safe_pct(sh3,sn):.2f}%) | H5 {sh5}/{sn} ({safe_pct(sh5,sn):.2f}%)",
            f"Pending ambi PRIME: {pam}",
            "Baseline ambo fisso: H1 ≈4.74% | H3 ≈13.57% | H5 ≈21.57%.",
            "",
            "⏸️ FOCUS / INCROCIO / CORE / legacy: PAUSATI; state conservato e non aggiornato.",
        ]
        if self.pending:
            lines.append(
                "Pending ambate: "
                + ", ".join(
                    f"{'P' if x.get('prime') else 'S'}:{int(x['num']):02d}@H{int(x.get('age',0))+1}"
                    for x in self.pending[-12:]
                )
            )
        if self.last_signal:
            lines.append(
                "Ultimo segnale: "
                + str(self.last_signal.get("origin_key"))
                + " → "
                + " ".join(f"{int(n):02d}" for n in self.last_signal.get("numbers", []))
            )
        return "\n".join(lines)


# ============================================================
# STATE WRAPPER — preserva TUTTE le chiavi legacy
# ============================================================
class MultiOnlyEngine:
    def __init__(self):
        self.raw_state = {}
        self.processed = []
        self.processed_set = set()
        self.last_draw_key = None
        self.multichannel = MultiPrimeV1()
        self.state_load_info = {"loaded": False, "path": None, "reason": "not-run"}
        self.load_state()

    def load_state(self):
        path = STATE_FILE if os.path.exists(STATE_FILE) else (LEGACY_STATE_FILE if os.path.exists(LEGACY_STATE_FILE) else None)
        if not path:
            self.state_load_info = {"loaded": False, "path": None, "reason": "state assente"}
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("state root non-dict")
            self.raw_state = data
            self.processed = [str(x) for x in data.get("processed", []) if isinstance(x, str)][-PROCESSED_MAX:]
            self.processed_set = set(self.processed)
            self.last_draw_key = data.get("last_draw_key") if isinstance(data.get("last_draw_key"), str) else None
            self.multichannel.load(data.get("multichannel_bd12_ed12_o2f12_v1"))
            self.state_load_info = {"loaded": True, "path": path, "reason": "OK"}
            console_log(
                f"STATE CARICATO | path={os.path.basename(path)} | "
                f"MULTI history={len(self.multichannel.history)} | PRIME start={self.multichannel.prime_started_from_key or '-'}"
            )
            return True
        except Exception as exc:
            self.state_load_info = {"loaded": False, "path": path, "reason": f"{type(exc).__name__}: {exc}"}
            console_log(f"STATE LOAD FAIL | {self.state_load_info['reason']}")
            return False

    def save_state(self, git=True, force_git=False):
        # Preserva integralmente ogni chiave legacy già presente.
        data = dict(self.raw_state) if isinstance(self.raw_state, dict) else {}
        data["saved_at"] = now_dt().isoformat(timespec="seconds")
        data["processed"] = self.processed[-PROCESSED_MAX:]
        data["last_draw_key"] = self.last_draw_key
        data["multichannel_bd12_ed12_o2f12_v1"] = self.multichannel.dump()
        data["active_mode"] = "MULTI_PRIME_ONLY_v20.4"
        atomic_write_json(STATE_FILE, data)
        self.raw_state = data
        if git:
            return git_commit_state_if_needed(force=force_git)
        return {"ok": True, "action": "local-only", "detail": "state scritto"}

    async def tg(self, app, text):
        if not app or CHAT_ID is None or not text:
            return
        try:
            await app.bot.send_message(chat_id=CHAT_ID, text=str(text))
        except Exception as exc:
            console_log(f"TELEGRAM FAIL | {type(exc).__name__}: {exc}")

    def status_text(self):
        return (
            "📡 STATUS v20.4 MULTI PRIME ONLY\n\n"
            f"Ultimo MULTI: {self.multichannel.history[-1]['key'] if self.multichannel.history else '-'}\n"
            f"State: {'OK' if self.state_load_info.get('loaded') else 'NUOVO'} | {self.state_load_info.get('reason')}\n"
            f"History MULTI: {len(self.multichannel.history)}/{MULTI_HISTORY_MAX}\n"
            f"PRIME partenza: {self.multichannel.prime_started_from_key or '-'}\n\n"
            "✅ Attivo: MULTI BD/ED/O2 + PRIME v1\n"
            "⏸️ FOCUS / INCROCIO / CORE / legacy: congelati nello state.\n\n"
            + self.multichannel.text()
        )

    @staticmethod
    def menu_text():
        return (
            "🎯 10eLOTTO v20.4 — MULTI PRIME ONLY\n\n"
            "ATTIVO:\n"
            "• STANDARD BD12∩ED12∩O2F12 in shadow/control\n"
            "• PRIME: BD rank 11-12 + O2 rank 6-12\n"
            "• AMBO1 COOC900\n"
            "• AMBO2 PRIME FAST H1\n"
            f"• SUPER P1-P2 gate≥{MULTI_SUPER_GATE}\n\n"
            "PAUSATI (state conservato): FOCUS, INCROCIO, CORE e tutti i legacy.\n\n"
            "/multi — statistiche complete MULTI/PRIME\n"
            "/status — feed + state + statistiche\n"
            "/verificatutto — alias di /status\n"
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
        BotCommand("multi", "MULTI BD/ED/O2 + PRIME v1"),
        BotCommand("status", "Stato MULTI PRIME + feed"),
        BotCommand("verificatutto", "Audit MULTI PRIME"),
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
        "🚀 MULTI BD12+ED12+O2F12 — v20.4 PRIME ONLY AVVIATO\n\n"
        "🧪 STANDARD: BD12 ∩ ED12 ∩ O2F12 W80, cooldown 5 — SHADOW/control.\n"
        f"🔥 PRIME v1: BD rank {PRIME_BD_RANK_MIN}-{PRIME_BD_RANK_MAX} + O2 rank {PRIME_O2_RANK_MIN}-{PRIME_O2_RANK_MAX} — focus AMBATA H1.\n"
        "🔗 AMBO1 M-P1 COOC900 — shadow H1-H5.\n"
        "⚡ AMBO2 M-P2 COOC900 — PRIME FAST H1 + shadow H1-H5.\n"
        f"🔥 SUPER P1-P2 solo support_sum≥{MULTI_SUPER_GATE}.\n\n"
        "⏸️ FOCUS / INCROCIO / CORE / ENGINE / SOSIA / legacy: PAUSATI.\n"
        "✅ Il loro state viene conservato ma NON aggiornato.\n"
        "🚫 Nessun backfill PRIME.\n\n"
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
        f"MULTI PRIME ONLY LIVE | poll={LOOP_SEC}s | rotation={BOT_MAX_RUNTIME_SECONDS}s"
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
                console_log(f"ROTATION save fail | {exc}")
            if BOT_ROTATION_NOTIFY:
                await engine.tg(
                    app,
                    "♻️ MULTI PRIME ONLY — ROTAZIONE RUNNER\n"
                    "State salvato; avvio successivo automatico.",
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
                    "⚠️ MULTI PRIME ONLY — ERRORE\n"
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
def run_self_test():
    mc = MultiPrimeV1()
    rows = []
    # 900 righe sintetiche valide per bootstrap/cooc.
    for i in range(1, 901):
        day = "2099-12-01"
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

    # Forziamo ranking con M=42 esattamente BD rank 11 e O2 rank 6 => PRIME.
    bd = [1,2,3,4,5,6,7,8,9,10,42,43]
    ed = [42,12,13,14,15,16,17,18,19,20,21,22]
    o2 = [50,51,52,53,54,42,55,56,57,58,59,60]
    mc._rankings = lambda: {
        "base_gap": {n: (100-n if n != 42 else 30) for n in range(1,91)},
        "extra_gap": {n: (100-n if n != 42 else 25) for n in range(1,91)},
        "o2_freq": {n: (20 if n in o2 else 0) for n in range(1,91)},
        "top_base_delay": bd,
        "top_extra_delay": ed,
        "top_o2": o2,
    }
    mc._partner_plan = lambda main, ranks: {
        "main": int(main),
        "p1": {"num": 50, "cooc": 30, "support": 2, "in_bd12": True, "in_ed12": False, "o2_freq80": 20},
        "p2": {"num": 51, "cooc": 28, "support": 2, "in_bd12": True, "in_ed12": False, "o2_freq80": 20},
        "support_sum": 4,
        "super_enabled": True,
        "cooc_window": 900,
    }
    sig = mc.arm()
    assert sig and sig["prime_numbers"] == [42], sig
    assert mc.prime_signals == 1
    assert len(mc.ambo_pending) == 3
    assert all(x.get("prime") for x in mc.ambo_pending)

    next_day = mc.history[-1]["day"]
    next_id = mc.history[-1]["draw_id"] + 1
    nums = [42, 50, 51] + [n for n in range(1, 91) if n not in {42,50,51}][:17]
    extra = [n for n in range(1,91) if n not in set(nums)][:15]
    evs = mc.ingest({"key": draw_key(next_day, next_id), "day": next_day, "draw_id": next_id,
                     "nums": nums, "oro": 42, "doppio_oro": 50, "extra": extra})
    assert any(e["kind"] == "ambata" and e["hit_now"] and e["row"].get("prime") for e in evs)
    assert sum(1 for e in evs if e["kind"] == "ambo" and e["hit_now"]) == 3
    pn, ph1, _, _ = mc._stats(True)
    assert (pn, ph1) == (1, 1)
    b2n, b2h1, _, _ = mc._ambo_stats({"BASE2"}, True)
    assert (b2n, b2h1) == (1, 1)

    # Dump/load preserva PRIME.
    rt = MultiPrimeV1()
    assert rt.load(mc.dump())
    assert rt.prime_signals == 1
    assert len(rt.records) == 1
    print("SELF-TEST OK: v20.4 MULTI PRIME ONLY")


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
