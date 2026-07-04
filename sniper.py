# ============================================================
# 🚀 SNIPER v48 — FINAL RESEARCH
#
# CORE v48: INVARIATO
#   - Hot Confirmed
#   - costruzione 3 ambi
#   - ambata
#   - score
#   - cluster reuse
#   - cooldown
#   - massimo 7 colpi
#   - chiusura al primo HIT AMBO
#
# LAB PARALLELO (non modifica il CORE v48):
#   - OP3 PRIMARY: miglior score fuori cluster
#   - OP9 CONTROL: mix score + ritardo + frequenza
#   - OP6 CONTROL: stessa decina ambata
#   - OP7 CONTROL: stessa decina dinamica per ambo
#   - TERNI LAB indipendente per 7 colpi anche dopo HIT AMBO
#   - AMBATA RAFFICA 2 indipendente per 2 colpi
#   - DECINA LAB 10-19: TOP 3 Heat ultime 5, soglia totale >= 8
#     sessione indipendente per 2 colpi, target statistici K1/K2/K3
#
# PATCH OPERATIVE:
#   - lock globale anti doppia istanza
#   - startup senza replay
#   - reset operativo cambio giorno
#   - CSV eventi in formato lungo/pulito
#   - stato persistente anche per sessioni LAB indipendenti
# ============================================================

import asyncio
import atexit
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from itertools import combinations

import requests
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder

import nest_asyncio

try:
    import fcntl
except ImportError:
    fcntl = None

nest_asyncio.apply()


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# File nuovi: non mischiano stato/statistiche delle versioni precedenti.
STATE_FILE = os.path.join(BASE_DIR, "sniper_v48_final_decina_state.json")
CSV_FILE = os.path.join(BASE_DIR, "sniper_v48_final_decina_events.csv")

# Stesso lock globale delle versioni Lab precedenti: impedisce di lasciare
# accidentalmente attivo un vecchio bot insieme a questo.
LOCK_FILE = "/tmp/sniper_v48_terni_lab.lock"

LOOP_SEC = 60

HISTORY_MAX = 240
PROCESSED_MAX = 1000

TOP_RITARDATARI = 10
PLAY_POSITIONS = [6, 7, 8, 9, 10]

WATCH_WINDOW = 12
HOT_TTL = 45
MIN_HOT_ACTIVE = 3

MAX_AMBI_PER_PLAY = 3
MAX_COLPI = 7
COOLDOWN_AFTER_PLAY = 5
CLUSTER_REUSE_AFTER = 12

# LAB indipendenti
TERNI_LAB_MAX_COLPI = 7
AMBATA_RAFFICA_MAX_COLPI = 2

# DECINA LAB 10-19 — regola congelata dal backtest storico.
DECINA_LAB_NUMBERS = tuple(range(10, 20))
DECINA_LAB_WINDOW = 5
DECINA_LAB_TOP_N = 3
DECINA_LAB_HEAT_THRESHOLD = 8
DECINA_LAB_MAX_COLPI = 2

# Il segnale storico scatta spesso (~48% delle occasioni nel file testato).
# Per evitare spam Telegram, il Lab resta sempre attivo e registra tutto nel CSV,
# mentre le notifiche sono opzionali via variabile ambiente DECINA_LAB_NOTIFY=1.
DECINA_LAB_NOTIFY = os.getenv("DECINA_LAB_NOTIFY", "0").strip().lower() in {
    "1", "true", "yes", "on"
}

# Strategie mantenute dopo il backtest storico.
LAB_STRATEGIES = ("op3", "op9", "op6", "op7")
LAB_LABELS = {
    "op3": "OP3 PRIMARY — SCORE FUORI CLUSTER",
    "op9": "OP9 CONTROL — MIX SCORE+RITARDO",
    "op6": "OP6 CONTROL — STESSA DECINA AMBATA",
    "op7": "OP7 CONTROL — STESSA DECINA DINAMICA",
}


# ============================================================
# UTILS
# ============================================================

def validate_env():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN non impostato nell'ambiente")

    if not CHAT_ID_RAW:
        raise RuntimeError("CHAT_ID non impostato nell'ambiente")

    try:
        return int(CHAT_ID_RAW)
    except ValueError as exc:
        raise RuntimeError("CHAT_ID deve essere un intero") from exc


def parse_site():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)
    lines = [x.strip() for x in text.splitlines() if x.strip()]

    out = {}
    i = 0

    while i < len(lines):
        m = re.search(r"Estrazione\s+.*?\bn\.\s*(\d+)", lines[i], re.IGNORECASE)

        if not m:
            i += 1
            continue

        e = int(m.group(1))
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
            if len(set(clean)) == 20:
                out[e] = clean

    return sorted(out.items())


def fingerprint(e, nums):
    return hashlib.md5(
        f"{e}-{'-'.join(map(str, nums))}".encode()
    ).hexdigest()


def day_key():
    return datetime.now().strftime("%Y-%m-%d")


def now_txt():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_nums(nums):
    return "-".join(map(str, nums or []))


def fmt_ambi(ambi):
    parts = []
    for item in ambi or []:
        a, b = item["ambo"]
        parts.append(f"{a}-{b}")
    return ", ".join(parts)


def fmt_terni(terni):
    return ", ".join("-".join(map(str, t)) for t in (terni or []))


def fmt_jolly(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "-".join(map(str, value))
    return str(value)


def normalize_terni(terni):
    out = []
    for t in terni or []:
        if len(t) == 3:
            out.append(tuple(sorted(map(int, t))))
    return sorted(set(out))


# ============================================================
# CSV — FORMATO LUNGO/PULITO
# ============================================================

CSV_FIELDS = [
    "time",
    "day",
    "event",
    "play_id",
    "estrazione",
    "colpo",
    "session_type",
    "strategy",
    "ambata",
    "ambi",
    "cluster",
    "jolly",
    "terni",
    "hit_list",
    "outcome",
    "v48_total_play",
    "v48_hit_ambata_events",
    "v48_hit_ambo",
    "v48_stop",
    "op3_sessions",
    "op3_hit_sessions",
    "op9_sessions",
    "op9_hit_sessions",
    "op6_sessions",
    "op6_hit_sessions",
    "op7_sessions",
    "op7_hit_sessions",
    "ambata_r2_sessions",
    "ambata_r2_hits",
    "ambata_r2_misses",
    "ambata_r2_hit_colpo1",
    "ambata_r2_hit_colpo2",
    "decina_signal_id",
    "decina_top3",
    "decina_heat_total",
    "decina_hit_numbers",
    "decina_sessions",
    "decina_closed",
    "decina_k1_hits",
    "decina_k2_hits",
    "decina_k3_hits",
    "decina_k2_colpo1",
    "decina_k2_colpo2",
]


def ensure_csv():
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, "r", encoding="utf-8", newline="") as f:
                header = next(csv.reader(f), [])

            if header == CSV_FIELDS:
                return

            backup = CSV_FILE.replace(
                ".csv",
                f"_old_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            os.replace(CSV_FILE, backup)
        except Exception:
            backup = CSV_FILE.replace(
                ".csv",
                f"_old_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            try:
                os.replace(CSV_FILE, backup)
            except Exception:
                pass

    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()


# ============================================================
# BOT
# ============================================================

class SNIPER_V48:

    def __init__(self):
        self.version = "v48_final_research_op3_r2_decina10_19"

        self.day = day_key()

        self.max_e = 0
        self.last_fp = None
        self.last_draws = []
        self.processed_ids = []
        self.processed_fps = []

        self.watch = {}
        self.hot_confirmed = {}

        # CORE v48
        self.active = False
        self.colpi = 0
        self.cooldown = 0
        self.active_snapshot = None

        self.last_cluster_numbers = []
        self.last_cluster_e = 0

        self.total_play = 0
        self.total_hit_ambata = 0  # mantiene semantica v48: eventi di uscita durante play
        self.total_hit_ambo = 0
        self.total_stop = 0

        self.play_uid = 0

        # TERNI LAB indipendente: lista per robustezza futura.
        self.terni_sessions = []
        self.terni_stats = {
            key: {"sessions": 0, "hit_sessions": 0}
            for key in LAB_STRATEGIES
        }

        # AMBATA RAFFICA 2 indipendente.
        self.ambata_r2_sessions = []
        self.ambata_r2_stats = {
            "sessions": 0,
            "hits": 0,
            "misses": 0,
            "hit_colpo1": 0,
            "hit_colpo2": 0,
        }

        # DECINA LAB 10-19 indipendente. Le sessioni possono sovrapporsi:
        # è intenzionale e replica il backtest cronologico per-ogni-segnale.
        self.decina_lab_uid = 0
        self.decina_lab_sessions = []
        self.decina_lab_stats = {
            "sessions": 0,
            "closed": 0,
            "k1_hits": 0,
            "k2_hits": 0,
            "k3_hits": 0,
            "k2_colpo1": 0,
            "k2_colpo2": 0,
        }

        self.load_state()
        ensure_csv()

    # ========================================================
    # TELEGRAM
    # ========================================================

    async def tg(self, app, msg):
        if not msg:
            return

        max_len = 3000
        chunks = [msg[i:i + max_len] for i in range(0, len(msg), max_len)]

        for chunk in chunks:
            for attempt in range(3):
                try:
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        text=chunk,
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=30,
                        pool_timeout=30,
                    )
                    break
                except Exception as ex:
                    print(f"Telegram send error attempt {attempt + 1}: {ex}")
                    await asyncio.sleep(5)

    # ========================================================
    # STATE
    # ========================================================

    def save_state(self):
        data = {
            "version": self.version,
            "day": self.day,
            "max_e": self.max_e,
            "last_fp": self.last_fp,
            "last_draws": self.last_draws[-HISTORY_MAX:],
            "processed_ids": self.processed_ids[-PROCESSED_MAX:],
            "processed_fps": self.processed_fps[-PROCESSED_MAX:],
            "watch": self.watch,
            "hot_confirmed": self.hot_confirmed,
            "active": self.active,
            "colpi": self.colpi,
            "cooldown": self.cooldown,
            "active_snapshot": self.active_snapshot,
            "last_cluster_numbers": self.last_cluster_numbers,
            "last_cluster_e": self.last_cluster_e,
            "total_play": self.total_play,
            "total_hit_ambata": self.total_hit_ambata,
            "total_hit_ambo": self.total_hit_ambo,
            "total_stop": self.total_stop,
            "play_uid": self.play_uid,
            "terni_sessions": self.terni_sessions,
            "terni_stats": self.terni_stats,
            "ambata_r2_sessions": self.ambata_r2_sessions,
            "ambata_r2_stats": self.ambata_r2_stats,
            "decina_lab_uid": self.decina_lab_uid,
            "decina_lab_sessions": self.decina_lab_sessions,
            "decina_lab_stats": self.decina_lab_stats,
        }

        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            return

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.day = data.get("day", day_key())
            self.max_e = int(data.get("max_e", 0))
            self.last_fp = data.get("last_fp")
            self.last_draws = data.get("last_draws", [])[-HISTORY_MAX:]
            self.processed_ids = data.get("processed_ids", [])[-PROCESSED_MAX:]
            self.processed_fps = data.get("processed_fps", [])[-PROCESSED_MAX:]
            self.watch = data.get("watch", {})
            self.hot_confirmed = data.get("hot_confirmed", {})

            self.active = bool(data.get("active", False))
            self.colpi = int(data.get("colpi", 0))
            self.cooldown = int(data.get("cooldown", 0))
            self.active_snapshot = data.get("active_snapshot")

            self.last_cluster_numbers = data.get("last_cluster_numbers", [])
            self.last_cluster_e = int(data.get("last_cluster_e", 0))

            self.total_play = int(data.get("total_play", 0))
            self.total_hit_ambata = int(data.get("total_hit_ambata", 0))
            self.total_hit_ambo = int(data.get("total_hit_ambo", 0))
            self.total_stop = int(data.get("total_stop", 0))
            self.play_uid = int(data.get("play_uid", self.total_play))

            self.terni_sessions = data.get("terni_sessions", [])
            loaded_terni_stats = data.get("terni_stats", {})
            for key in LAB_STRATEGIES:
                src = loaded_terni_stats.get(key, {})
                self.terni_stats[key] = {
                    "sessions": int(src.get("sessions", 0)),
                    "hit_sessions": int(src.get("hit_sessions", 0)),
                }

            self.ambata_r2_sessions = data.get("ambata_r2_sessions", [])
            loaded_r2 = data.get("ambata_r2_stats", {})
            for key in self.ambata_r2_stats:
                self.ambata_r2_stats[key] = int(loaded_r2.get(key, 0))

            self.decina_lab_uid = int(data.get("decina_lab_uid", 0))
            self.decina_lab_sessions = data.get("decina_lab_sessions", [])
            loaded_decina = data.get("decina_lab_stats", {})
            for key in self.decina_lab_stats:
                self.decina_lab_stats[key] = int(loaded_decina.get(key, 0))

        except Exception as ex:
            print(f"⚠️ Stato non caricato: {ex}")

    def reset_for_new_day(self, new_day):
        """
        Stessa filosofia operativa della versione precedente:
        reset dedup/watch/hot e play attivo; storico numerico conservato.
        Le sessioni LAB del giorno precedente vengono chiuse operativamente.
        """
        self.day = new_day

        self.max_e = 0
        self.last_fp = None
        self.processed_ids = []
        self.processed_fps = []

        self.watch = {}
        self.hot_confirmed = {}

        self.active = False
        self.colpi = 0
        self.cooldown = 0
        self.active_snapshot = None

        self.last_cluster_numbers = []
        self.last_cluster_e = 0

        # Non attraversiamo il cambio giorno con sessioni aperte.
        self.terni_sessions = []
        self.ambata_r2_sessions = []
        self.decina_lab_sessions = []

        self.save_state()

    # ========================================================
    # CSV EVENTS
    # ========================================================

    def append_csv_event(
        self,
        event,
        *,
        play=None,
        play_id=None,
        e=None,
        colpo=None,
        session_type="",
        strategy="",
        jolly=None,
        terni=None,
        hit_list=None,
        outcome="",
        decina_signal_id=None,
        decina_top3=None,
        decina_heat_total=None,
        decina_hit_numbers=None,
    ):
        ensure_csv()

        snap = play or self.active_snapshot or {}

        row = {
            "time": now_txt(),
            "day": self.day,
            "event": event,
            "play_id": play_id if play_id is not None else snap.get("play_id", ""),
            "estrazione": e if e is not None else "",
            "colpo": colpo if colpo is not None else "",
            "session_type": session_type,
            "strategy": strategy,
            "ambata": snap.get("ambata", ""),
            "ambi": fmt_ambi(snap.get("ambi", [])),
            "cluster": fmt_nums(snap.get("cluster_numbers", [])),
            "jolly": fmt_jolly(jolly),
            "terni": fmt_terni(terni),
            "hit_list": fmt_terni(hit_list),
            "outcome": outcome,
            "v48_total_play": self.total_play,
            "v48_hit_ambata_events": self.total_hit_ambata,
            "v48_hit_ambo": self.total_hit_ambo,
            "v48_stop": self.total_stop,
            "op3_sessions": self.terni_stats["op3"]["sessions"],
            "op3_hit_sessions": self.terni_stats["op3"]["hit_sessions"],
            "op9_sessions": self.terni_stats["op9"]["sessions"],
            "op9_hit_sessions": self.terni_stats["op9"]["hit_sessions"],
            "op6_sessions": self.terni_stats["op6"]["sessions"],
            "op6_hit_sessions": self.terni_stats["op6"]["hit_sessions"],
            "op7_sessions": self.terni_stats["op7"]["sessions"],
            "op7_hit_sessions": self.terni_stats["op7"]["hit_sessions"],
            "ambata_r2_sessions": self.ambata_r2_stats["sessions"],
            "ambata_r2_hits": self.ambata_r2_stats["hits"],
            "ambata_r2_misses": self.ambata_r2_stats["misses"],
            "ambata_r2_hit_colpo1": self.ambata_r2_stats["hit_colpo1"],
            "ambata_r2_hit_colpo2": self.ambata_r2_stats["hit_colpo2"],
            "decina_signal_id": decina_signal_id if decina_signal_id is not None else "",
            "decina_top3": fmt_nums(decina_top3),
            "decina_heat_total": decina_heat_total if decina_heat_total is not None else "",
            "decina_hit_numbers": fmt_nums(decina_hit_numbers),
            "decina_sessions": self.decina_lab_stats["sessions"],
            "decina_closed": self.decina_lab_stats["closed"],
            "decina_k1_hits": self.decina_lab_stats["k1_hits"],
            "decina_k2_hits": self.decina_lab_stats["k2_hits"],
            "decina_k3_hits": self.decina_lab_stats["k3_hits"],
            "decina_k2_colpo1": self.decina_lab_stats["k2_colpo1"],
            "decina_k2_colpo2": self.decina_lab_stats["k2_colpo2"],
        }

        with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow(row)

    # ========================================================
    # DEDUP / STARTUP
    # ========================================================

    def already_processed(self, e, nums):
        fp = fingerprint(e, nums)

        if fp == self.last_fp:
            return True
        if fp in self.processed_fps:
            return True
        if e <= self.max_e and e in self.processed_ids:
            return True

        return False

    def remember_processed(self, e, nums):
        fp = fingerprint(e, nums)

        self.max_e = max(self.max_e, e)
        self.last_fp = fp

        self.processed_ids.append(e)
        self.processed_fps.append(fp)

        self.processed_ids = self.processed_ids[-PROCESSED_MAX:]
        self.processed_fps = self.processed_fps[-PROCESSED_MAX:]

    def preload_today_as_processed(self, es):
        """Carica lo storico visibile e marca TUTTO come processato."""
        for e, nums in es:
            if len(set(nums)) != 20:
                continue

            self.last_draws.append(nums)
            self.processed_ids.append(e)
            self.processed_fps.append(fingerprint(e, nums))

        self.last_draws = self.last_draws[-HISTORY_MAX:]
        self.processed_ids = self.processed_ids[-PROCESSED_MAX:]
        self.processed_fps = self.processed_fps[-PROCESSED_MAX:]

        if es:
            last_e, last_nums = es[-1]
            self.max_e = last_e
            self.last_fp = fingerprint(last_e, last_nums)

        self.save_state()

    # ========================================================
    # FEATURES — STESSE DEL CODICE v48/LAB PRECEDENTE
    # ========================================================

    def lag(self, n):
        lag = 0

        for d in reversed(self.last_draws[:-1]):
            lag += 1
            if n in d:
                return lag

        return lag

    def heat(self, n):
        weights = [5, 4, 3, 2, 1]
        return sum(
            w for i, w in enumerate(weights)
            if i < len(self.last_draws)
            and n in self.last_draws[-(i + 1)]
        )

    def dominance(self, n, window=6):
        return sum(1 for d in self.last_draws[-window:] if n in d)

    def pressure(self, n):
        weights = [5, 4, 3, 2, 1]
        return sum(
            w for i, w in enumerate(weights)
            if i < len(self.last_draws)
            and n in self.last_draws[-(i + 1)]
        )

    def recent_frequency(self, n, window=20):
        return sum(1 for d in self.last_draws[-window:] if n in d)

    def decina_numbers(self, n):
        start = ((int(n) - 1) // 10) * 10 + 1
        end = min(start + 9, 90)
        return list(range(start, end + 1))

    def build_terni_single_jolly(self, ambi, jolly):
        terni = []

        if not jolly:
            return terni

        for item in ambi:
            a, b = item["ambo"]
            if jolly not in (a, b):
                terni.append(tuple(sorted((a, b, int(jolly)))))

        return sorted(set(terni))

    def best_by_score(self, candidates, e):
        clean = [int(n) for n in candidates if 1 <= int(n) <= 90]

        if not clean:
            return None

        clean = sorted(set(clean))
        clean.sort(
            key=lambda n: (
                -self.number_score(n, e),
                -self.recent_frequency(n, 20),
                self.lag(n),
                n,
            )
        )
        return clean[0]

    # ========================================================
    # TOP RITARDATARI — CORE v48
    # ========================================================

    def top_ritardatari(self):
        data = []

        for n in range(1, 91):
            data.append({"number": n, "lag": self.lag(n)})

        data.sort(key=lambda x: (-x["lag"], x["number"]))
        return data[:TOP_RITARDATARI]

    def selected_ritardatari(self):
        top10 = self.top_ritardatari()
        selected = []

        for pos in PLAY_POSITIONS:
            idx = pos - 1
            if idx < len(top10):
                selected.append({
                    "position": pos,
                    "number": top10[idx]["number"],
                    "lag": top10[idx]["lag"],
                })

        return top10, selected

    # ========================================================
    # CLEAN WATCH/HOT — CORE v48
    # ========================================================

    def clean_old_watch(self, current_e):
        remove = []

        for key, data in self.watch.items():
            if current_e - int(data["first_e"]) > WATCH_WINDOW:
                remove.append(key)

        for key in remove:
            self.watch.pop(key, None)

    def clean_old_hot(self, current_e):
        remove = []

        for key, data in self.hot_confirmed.items():
            if current_e - int(data["confirmed_e"]) > HOT_TTL:
                remove.append(key)

        for key in remove:
            self.hot_confirmed.pop(key, None)

    def update_watch_and_confirmed(self, e, nums, selected):
        s = set(nums)

        for item in selected:
            n = int(item["number"])
            key = str(n)

            if n not in s:
                continue

            if key not in self.watch:
                self.watch[key] = {
                    "number": n,
                    "first_e": e,
                    "last_e": e,
                    "hits": 1,
                    "position": item["position"],
                    "initial_lag": item["lag"],
                }
            else:
                self.watch[key]["hits"] += 1
                self.watch[key]["last_e"] = e

                if self.watch[key]["hits"] >= 2:
                    self.hot_confirmed[key] = {
                        **self.watch[key],
                        "confirmed_e": e,
                    }
                    self.watch.pop(key, None)

        self.clean_old_watch(e)
        self.clean_old_hot(e)

    # ========================================================
    # SCORE — INVARIATO
    # ========================================================

    def confirmed_score(self, item, e):
        n = int(item["number"])
        age = e - int(item["confirmed_e"])

        return (
            item["hits"] * 20
            - age * 2
            + item["initial_lag"]
            + self.heat(n)
            + self.dominance(n, 6) * 3
            + self.pressure(n)
        )

    def number_score(self, n, e):
        hot = self.hot_confirmed.get(str(n))
        hot_score = 0

        if hot:
            hot_score = self.confirmed_score(hot, e)

        return (
            hot_score
            + self.heat(n) * 2
            + self.dominance(n, 6) * 3
            + self.pressure(n)
            - self.lag(n)
        )

    # ========================================================
    # DUPLICATE CLUSTER — CORE v48
    # ========================================================

    def duplicate_cluster(self, cluster_numbers, e):
        if not self.last_cluster_numbers:
            return False

        if e - self.last_cluster_e >= CLUSTER_REUSE_AFTER:
            return False

        overlap = len(set(cluster_numbers) & set(self.last_cluster_numbers))
        return overlap >= 2

    # ========================================================
    # BUILD PLAY
    # ========================================================

    def build_play(self, e):
        hot_items = [
            x for x in self.hot_confirmed.values()
            if 0 <= e - int(x["confirmed_e"]) <= HOT_TTL
        ]

        if len(hot_items) < MIN_HOT_ACTIVE:
            return None

        pair_candidates = []

        # ==================================================
        # MOTORE v48 ORIGINALE: NON MODIFICARE
        # ==================================================
        for a, b in combinations(hot_items, 2):
            pair = tuple(sorted((int(a["number"]), int(b["number"]))))
            score = self.confirmed_score(a, e) + self.confirmed_score(b, e)

            pair_candidates.append({
                "ambo": pair,
                "score": round(score, 2),
            })

        pair_candidates.sort(key=lambda x: -x["score"])
        ambi = pair_candidates[:MAX_AMBI_PER_PLAY]

        if not ambi:
            return None

        all_numbers = []
        for item in ambi:
            all_numbers.extend(item["ambo"])

        cluster_numbers = sorted(set(all_numbers))

        if self.duplicate_cluster(cluster_numbers, e):
            return None

        freq = Counter(all_numbers)
        ambata = freq.most_common(1)[0][0]

        # ==================================================
        # DA QUI IN POI: SOLO LAB PARALLELO
        # ==================================================
        outside_cluster = [n for n in range(1, 91) if n not in cluster_numbers]

        # OP3 — miglior score assoluto fuori cluster (PRIMARY)
        all_scores = [(n, self.number_score(n, e)) for n in outside_cluster]
        all_scores.sort(key=lambda x: -x[1])
        terno_num_3 = all_scores[0][0] if all_scores else None

        # OP6 — miglior numero stessa decina ambata
        decina_ambata = [
            n for n in self.decina_numbers(ambata)
            if n not in cluster_numbers
        ]
        terno_num_6 = self.best_by_score(decina_ambata, e)

        # OP7 — stessa decina dinamica per singolo ambo
        terni_op7 = []
        terno_num_7 = []

        for item in ambi:
            a, b = item["ambo"]
            decina_candidates = set(self.decina_numbers(a)) | set(self.decina_numbers(b))
            decina_candidates = [
                n for n in decina_candidates
                if n not in cluster_numbers
            ]

            jolly = self.best_by_score(decina_candidates, e)
            if jolly:
                terno_num_7.append(jolly)
                terni_op7.append(tuple(sorted((a, b, jolly))))

        terno_num_7 = sorted(set(terno_num_7))
        terni_op7 = sorted(set(terni_op7))

        # OP9 — mix score + ritardo + frequenza recente (CONTROL)
        mix_candidates = []

        for n in outside_cluster:
            mix = (
                self.number_score(n, e)
                + self.lag(n) * 0.60
                + self.recent_frequency(n, 20) * 2.00
                + self.recent_frequency(n, 60) * 0.50
            )
            mix_candidates.append((n, mix))

        mix_candidates.sort(key=lambda x: (-x[1], x[0]))
        terno_num_9 = mix_candidates[0][0] if mix_candidates else None

        terni_op3 = self.build_terni_single_jolly(ambi, terno_num_3)
        terni_op6 = self.build_terni_single_jolly(ambi, terno_num_6)
        terni_op9 = self.build_terni_single_jolly(ambi, terno_num_9)

        return {
            "ambata": ambata,
            "ambi": ambi,
            "cluster_numbers": cluster_numbers,
            "terno_num_3": terno_num_3,
            "terni_op3": terni_op3,
            "terno_num_9": terno_num_9,
            "terni_op9": terni_op9,
            "terno_num_6": terno_num_6,
            "terni_op6": terni_op6,
            "terno_num_7": terno_num_7,
            "terni_op7": terni_op7,
        }

    # ========================================================
    # CHECK CORE v48
    # ========================================================

    def check_v48_hit(self, nums):
        s = set(nums)
        snap = self.active_snapshot

        ambata_hit = snap["ambata"] in s
        ambi_hit = []

        for item in snap["ambi"]:
            a, b = item["ambo"]
            if a in s and b in s:
                ambi_hit.append(item)

        return {
            "ambata_hit": ambata_hit,
            "ambi_hit": ambi_hit,
        }

    # ========================================================
    # DECINA LAB 10-19 — HEAT 5 / TOP 3 / SOGLIA >= 8
    # ========================================================

    def build_decina_10_19_signal(self):
        """Costruisce un segnale solo dal passato già noto.

        Regola identica al backtest:
        - ultime 5 estrazioni
        - per 10..19 conta presenze
        - tie-break: conteggio, poi recenza pesata 1..5, poi numero minore
        - TOP 3
        - segnale solo se somma conteggi TOP 3 >= 8

        La sessione aperta DOPO l'estrazione corrente viene verificata
        esclusivamente sulle 2 estrazioni future successive.
        """
        if len(self.last_draws) < DECINA_LAB_WINDOW:
            return None

        hist = self.last_draws[-DECINA_LAB_WINDOW:]
        ranked = []

        for n in DECINA_LAB_NUMBERS:
            count = sum(1 for draw in hist if n in draw)
            recency_weighted = sum(
                weight
                for weight, draw in enumerate(hist, start=1)
                if n in draw
            )
            ranked.append((n, count, recency_weighted))

        ranked.sort(key=lambda x: (-x[1], -x[2], x[0]))
        top = ranked[:DECINA_LAB_TOP_N]
        top3 = [int(x[0]) for x in top]
        heat_counts = [int(x[1]) for x in top]
        heat_total = sum(heat_counts)

        if heat_total < DECINA_LAB_HEAT_THRESHOLD:
            return None

        return {
            "top3": top3,
            "heat_counts": heat_counts,
            "heat_total": int(heat_total),
        }

    async def maybe_open_decina_10_19_session(self, app, e):
        signal = self.build_decina_10_19_signal()
        if not signal:
            return

        self.decina_lab_uid += 1
        session = {
            "signal_id": self.decina_lab_uid,
            "day": self.day,
            "origin_e": e,
            "colpi": 0,
            "max_colpi": DECINA_LAB_MAX_COLPI,
            "top3": signal["top3"],
            "heat_counts": signal["heat_counts"],
            "heat_total": signal["heat_total"],
            "k1_hit": False,
            "k2_hit": False,
            "k3_hit": False,
            "k1_first_colpo": None,
            "k2_first_colpo": None,
            "k3_first_colpo": None,
        }
        self.decina_lab_sessions.append(session)
        self.decina_lab_stats["sessions"] += 1

        self.append_csv_event(
            "DECINA_10_19_OPEN",
            e=e,
            colpo=0,
            session_type="DECINA_10_19_H5_T2",
            strategy="DECINA_10_19_TOP3_HEAT5",
            outcome="OPEN",
            decina_signal_id=session["signal_id"],
            decina_top3=session["top3"],
            decina_heat_total=session["heat_total"],
        )

        if DECINA_LAB_NOTIFY:
            await self.tg(
                app,
                "🔥 DECINA LAB 10-19 — SEGNALE\n"
                f"• signal_id = {session['signal_id']}\n"
                f"• TOP 3 Heat 5 = {fmt_nums(session['top3'])}\n"
                f"• conteggi = {fmt_nums(session['heat_counts'])}\n"
                f"• Heat totale = {session['heat_total']}\n"
                f"• soglia = {DECINA_LAB_HEAT_THRESHOLD}\n"
                f"• osservazione = prossimi {DECINA_LAB_MAX_COLPI} colpi\n"
                "• target principale = almeno 2 dei 3 insieme"
            )

    async def process_decina_10_19_sessions(self, app, e, nums):
        if not self.decina_lab_sessions:
            return

        draw_set = set(nums)
        survivors = []

        for session in self.decina_lab_sessions:
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = session["colpi"]
            top3 = [int(n) for n in session.get("top3", [])]
            hit_numbers = [n for n in top3 if n in draw_set]
            count = len(hit_numbers)

            newly_hit = []
            for k, flag_key, first_key, stat_key in (
                (1, "k1_hit", "k1_first_colpo", "k1_hits"),
                (2, "k2_hit", "k2_first_colpo", "k2_hits"),
                (3, "k3_hit", "k3_first_colpo", "k3_hits"),
            ):
                if count >= k and not session.get(flag_key, False):
                    session[flag_key] = True
                    session[first_key] = colpo
                    self.decina_lab_stats[stat_key] += 1
                    newly_hit.append(k)

                    if k == 2:
                        if colpo == 1:
                            self.decina_lab_stats["k2_colpo1"] += 1
                        elif colpo == 2:
                            self.decina_lab_stats["k2_colpo2"] += 1

                    self.append_csv_event(
                        f"DECINA_10_19_FIRST_HIT_K{k}",
                        e=e,
                        colpo=colpo,
                        session_type="DECINA_10_19_H5_T2",
                        strategy=f"DECINA_K{k}",
                        outcome="HIT",
                        decina_signal_id=session["signal_id"],
                        decina_top3=top3,
                        decina_heat_total=session.get("heat_total"),
                        decina_hit_numbers=hit_numbers,
                    )

            # Telegram opzionale: invia soprattutto il target K2 e l'eventuale K3.
            if DECINA_LAB_NOTIFY and (2 in newly_hit or 3 in newly_hit):
                label = "TRIS 3/3" if count == 3 else "ALMENO 2/3"
                await self.tg(
                    app,
                    f"💥 DECINA LAB 10-19 — {label}\n"
                    f"• signal_id = {session['signal_id']}\n"
                    f"• colpo = {colpo}\n"
                    f"• TOP 3 = {fmt_nums(top3)}\n"
                    f"• usciti insieme = {fmt_nums(hit_numbers)}\n"
                    f"• Heat origine = {session.get('heat_total')}"
                )

            if colpo >= int(session.get("max_colpi", DECINA_LAB_MAX_COLPI)):
                self.decina_lab_stats["closed"] += 1
                outcome = (
                    f"K1={'HIT' if session.get('k1_hit') else 'MISS'};"
                    f"K2={'HIT' if session.get('k2_hit') else 'MISS'};"
                    f"K3={'HIT' if session.get('k3_hit') else 'MISS'}"
                )
                self.append_csv_event(
                    "DECINA_10_19_CLOSE",
                    e=e,
                    colpo=colpo,
                    session_type="DECINA_10_19_H5_T2",
                    strategy="DECINA_10_19_TOP3_HEAT5",
                    outcome=outcome,
                    decina_signal_id=session["signal_id"],
                    decina_top3=top3,
                    decina_heat_total=session.get("heat_total"),
                    decina_hit_numbers=hit_numbers,
                )
            else:
                survivors.append(session)

        self.decina_lab_sessions = survivors

    # ========================================================
    # LAB SESSION CREATION
    # ========================================================

    def create_terni_session(self, play, e):
        strategies = {}

        for key in LAB_STRATEGIES:
            suffix = key.replace("op", "")
            terni = normalize_terni(play.get(f"terni_op{suffix}", []))
            jolly = play.get(f"terno_num_{suffix}")

            strategies[key] = {
                "jolly": jolly,
                "terni": terni,
                "hit": False,
                "first_hit_colpo": None,
                "first_hit_list": [],
            }

            if terni:
                self.terni_stats[key]["sessions"] += 1

        session = {
            "play_id": play["play_id"],
            "day": self.day,
            "start_e": e,
            "colpi": 0,
            "max_colpi": TERNI_LAB_MAX_COLPI,
            "ambata": play["ambata"],
            "ambi": play["ambi"],
            "cluster_numbers": play["cluster_numbers"],
            "strategies": strategies,
        }

        self.terni_sessions.append(session)

    def create_ambata_r2_session(self, play, e):
        session = {
            "play_id": play["play_id"],
            "day": self.day,
            "start_e": e,
            "colpi": 0,
            "max_colpi": AMBATA_RAFFICA_MAX_COLPI,
            "ambata": play["ambata"],
            "ambi": play["ambi"],
            "cluster_numbers": play["cluster_numbers"],
        }

        self.ambata_r2_sessions.append(session)
        self.ambata_r2_stats["sessions"] += 1

    # ========================================================
    # LAB SESSION PROCESSING — INDIPENDENTE DAL CORE v48
    # ========================================================

    async def process_terni_sessions(self, app, e, nums):
        if not self.terni_sessions:
            return

        s = set(nums)
        survivors = []

        for session in self.terni_sessions:
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = session["colpi"]

            new_hit_lines = []

            for key in LAB_STRATEGIES:
                data = session["strategies"].get(key, {})
                terni = normalize_terni(data.get("terni", []))
                hits = [t for t in terni if all(x in s for x in t)]

                # Contatore principale = sessioni vincenti, una volta sola per strategia.
                if hits and not data.get("hit", False):
                    data["hit"] = True
                    data["first_hit_colpo"] = colpo
                    data["first_hit_list"] = hits
                    self.terni_stats[key]["hit_sessions"] += 1

                    new_hit_lines.append(
                        f"• {LAB_LABELS[key]} = {fmt_terni(hits)}"
                    )

                    play_stub = {
                        "play_id": session["play_id"],
                        "ambata": session["ambata"],
                        "ambi": session["ambi"],
                        "cluster_numbers": session["cluster_numbers"],
                    }
                    self.append_csv_event(
                        "TERNI_FIRST_HIT",
                        play=play_stub,
                        play_id=session["play_id"],
                        e=e,
                        colpo=colpo,
                        session_type="TERNI_7",
                        strategy=key.upper(),
                        jolly=data.get("jolly"),
                        terni=terni,
                        hit_list=hits,
                        outcome="HIT",
                    )

            if new_hit_lines:
                await self.tg(
                    app,
                    f"💥 TERNI LAB 7 COLPI | play_id {session['play_id']} | colpo {colpo}\n"
                    + "\n".join(new_hit_lines)
                    + "\n\n"
                    + self.terni_lab_stats_text()
                )

            if colpo >= int(session.get("max_colpi", TERNI_LAB_MAX_COLPI)):
                play_stub = {
                    "play_id": session["play_id"],
                    "ambata": session["ambata"],
                    "ambi": session["ambi"],
                    "cluster_numbers": session["cluster_numbers"],
                }

                outcomes = []
                for key in LAB_STRATEGIES:
                    d = session["strategies"].get(key, {})
                    outcomes.append(f"{key.upper()}={'HIT' if d.get('hit') else 'MISS'}")

                self.append_csv_event(
                    "TERNI_SESSION_CLOSE",
                    play=play_stub,
                    play_id=session["play_id"],
                    e=e,
                    colpo=colpo,
                    session_type="TERNI_7",
                    outcome=";".join(outcomes),
                )
            else:
                survivors.append(session)

        self.terni_sessions = survivors

    async def process_ambata_r2_sessions(self, app, e, nums):
        if not self.ambata_r2_sessions:
            return

        s = set(nums)
        survivors = []

        for session in self.ambata_r2_sessions:
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = session["colpi"]
            hit = int(session["ambata"]) in s

            play_stub = {
                "play_id": session["play_id"],
                "ambata": session["ambata"],
                "ambi": session["ambi"],
                "cluster_numbers": session["cluster_numbers"],
            }

            if hit:
                self.ambata_r2_stats["hits"] += 1
                if colpo == 1:
                    self.ambata_r2_stats["hit_colpo1"] += 1
                elif colpo == 2:
                    self.ambata_r2_stats["hit_colpo2"] += 1

                self.append_csv_event(
                    "AMBATA_R2_HIT",
                    play=play_stub,
                    play_id=session["play_id"],
                    e=e,
                    colpo=colpo,
                    session_type="AMBATA_R2",
                    strategy="AMBATA_R2",
                    jolly=session["ambata"],
                    outcome="HIT",
                )

                await self.tg(
                    app,
                    f"🎯 AMBATA RAFFICA 2 | HIT colpo {colpo}\n"
                    f"• play_id = {session['play_id']}\n"
                    f"• ambata = {session['ambata']}\n\n"
                    f"{self.ambata_r2_stats_text()}\n\n"
                    f"{self.decina_lab_stats_text()}"
                )
                continue

            if colpo >= int(session.get("max_colpi", AMBATA_RAFFICA_MAX_COLPI)):
                self.ambata_r2_stats["misses"] += 1

                self.append_csv_event(
                    "AMBATA_R2_MISS",
                    play=play_stub,
                    play_id=session["play_id"],
                    e=e,
                    colpo=colpo,
                    session_type="AMBATA_R2",
                    strategy="AMBATA_R2",
                    jolly=session["ambata"],
                    outcome="MISS",
                )
            else:
                survivors.append(session)

        self.ambata_r2_sessions = survivors

    # ========================================================
    # REPORT TEXT
    # ========================================================

    def terni_lab_stats_text(self):
        lines = ["📊 TERNI LAB — SESSIONI VINCENTI / SESSIONI"]

        for key in LAB_STRATEGIES:
            st = self.terni_stats[key]
            sessions = st["sessions"]
            hits = st["hit_sessions"]
            pct = (hits / sessions * 100) if sessions else 0.0
            prefix = "⭐" if key == "op3" else "•"
            lines.append(
                f"{prefix} {key.upper()} = {hits}/{sessions} ({pct:.2f}%)"
            )

        return "\n".join(lines)

    def ambata_r2_stats_text(self):
        st = self.ambata_r2_stats
        sessions = st["sessions"]
        hits = st["hits"]
        closed = hits + st["misses"]
        pct = (hits / closed * 100) if closed else 0.0

        return (
            "📊 AMBATA RAFFICA 2\n"
            f"• sessioni create = {sessions}\n"
            f"• sessioni chiuse = {closed}\n"
            f"• hit = {hits}\n"
            f"• miss = {st['misses']}\n"
            f"• hit rate chiuse = {pct:.2f}%\n"
            f"• hit colpo 1 = {st['hit_colpo1']}\n"
            f"• hit colpo 2 = {st['hit_colpo2']}"
        )

    def decina_lab_stats_text(self):
        st = self.decina_lab_stats
        closed = st["closed"]
        k1_pct = (st["k1_hits"] / closed * 100) if closed else 0.0
        k2_pct = (st["k2_hits"] / closed * 100) if closed else 0.0
        k3_pct = (st["k3_hits"] / closed * 100) if closed else 0.0

        return (
            "📊 DECINA LAB 10-19 — HEAT 5 / TOP 3 / 2 COLPI\n"
            f"• soglia Heat totale = {DECINA_LAB_HEAT_THRESHOLD}\n"
            f"• sessioni create = {st['sessions']}\n"
            f"• sessioni chiuse = {closed}\n"
            f"• almeno 1/3 = {st['k1_hits']} ({k1_pct:.2f}%)\n"
            f"• almeno 2/3 = {st['k2_hits']} ({k2_pct:.2f}%)\n"
            f"• tutti 3/3 = {st['k3_hits']} ({k3_pct:.2f}%)\n"
            f"• K2 colpo 1 = {st['k2_colpo1']}\n"
            f"• K2 colpo 2 = {st['k2_colpo2']}\n"
            f"• sessioni aperte ora = {len(self.decina_lab_sessions)}"
        )

    def play_lab_text(self, play):
        blocks = []

        for key in LAB_STRATEGIES:
            suffix = key.replace("op", "")
            jolly = play.get(f"terno_num_{suffix}")
            terni = play.get(f"terni_op{suffix}", [])
            blocks.append(
                f"{'⭐' if key == 'op3' else '🧪'} {LAB_LABELS[key]} | "
                f"jolly = {fmt_jolly(jolly) or 'None'}\n"
                f"{fmt_terni(terni) or 'nessuno'}"
            )

        return "\n\n".join(blocks)

    # ========================================================
    # MAIN
    # ========================================================

    async def on_new(self, app, e, nums):
        if len(set(nums)) != 20:
            return

        if self.already_processed(e, nums):
            return

        self.remember_processed(e, nums)

        self.last_draws.append(nums)
        self.last_draws = self.last_draws[-HISTORY_MAX:]

        await self.tg(
            app,
            f"📌 Estrazione {e}\n"
            f"🎱 {', '.join(map(str, nums))}"
        )

        # ====================================================
        # LAB INDIPENDENTI: vengono aggiornati SEMPRE,
        # anche se il CORE v48 ha già chiuso l'ambo.
        # ====================================================
        await self.process_terni_sessions(app, e, nums)
        await self.process_ambata_r2_sessions(app, e, nums)
        await self.process_decina_10_19_sessions(app, e, nums)

        # Il nuovo segnale usa le ultime 5 estrazioni già note (inclusa questa)
        # e viene verificato SOLO sulle future 2 estrazioni successive.
        await self.maybe_open_decina_10_19_session(app, e)

        # ====================================================
        # CORE v48 ATTIVO — LOGICA INVARIATA
        # ====================================================
        if self.active:
            self.colpi += 1
            hit_data = self.check_v48_hit(nums)

            if hit_data["ambata_hit"]:
                self.total_hit_ambata += 1
                self.append_csv_event(
                    "V48_HIT_AMBATA",
                    e=e,
                    colpo=self.colpi,
                    session_type="V48",
                    outcome="HIT",
                )

                await self.tg(
                    app,
                    f"🎯 AMBATA PRESA v48 | colpo {self.colpi}\n"
                    f"• ambata = {self.active_snapshot['ambata']}"
                )

            if hit_data["ambi_hit"]:
                self.total_hit_ambo += 1

                ambi_txt = ", ".join(
                    f"{a}-{b}"
                    for h in hit_data["ambi_hit"]
                    for a, b in [h["ambo"]]
                )

                self.append_csv_event(
                    "V48_HIT_AMBO",
                    e=e,
                    colpo=self.colpi,
                    session_type="V48",
                    outcome="HIT",
                    hit_list=[],
                )

                await self.tg(
                    app,
                    f"🔥 HIT AMBO v48 | colpo {self.colpi}\n"
                    f"• ambi = {ambi_txt}\n\n"
                    f"📊 STATS v48\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata eventi = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}\n\n"
                    f"{self.terni_lab_stats_text()}\n\n"
                    f"{self.ambata_r2_stats_text()}\n\n"
                    f"{self.decina_lab_stats_text()}"
                )

                self.last_cluster_numbers = self.active_snapshot["cluster_numbers"]
                self.last_cluster_e = e

                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None

                self.save_state()
                return

            if self.colpi >= MAX_COLPI:
                self.total_stop += 1

                self.append_csv_event(
                    "V48_STOP",
                    e=e,
                    colpo=self.colpi,
                    session_type="V48",
                    outcome="STOP",
                )

                await self.tg(
                    app,
                    f"🛑 STOP v48 | {MAX_COLPI} colpi\n\n"
                    f"📊 STATS v48\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata eventi = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}\n\n"
                    f"{self.terni_lab_stats_text()}\n\n"
                    f"{self.ambata_r2_stats_text()}\n\n"
                    f"{self.decina_lab_stats_text()}"
                )

                self.last_cluster_numbers = self.active_snapshot["cluster_numbers"]
                self.last_cluster_e = e

                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None

                self.save_state()
                return

            self.save_state()
            return

        # ====================================================
        # COOLDOWN — CORE v48
        # ====================================================
        if self.cooldown > 0:
            self.cooldown -= 1
            self.save_state()
            return

        # ====================================================
        # HISTORY MINIMO
        # ====================================================
        if len(self.last_draws) < 30:
            self.save_state()
            return

        # ====================================================
        # HOT UPDATE — CORE v48
        # ====================================================
        _, selected = self.selected_ritardatari()
        self.update_watch_and_confirmed(e, nums, selected)

        # ====================================================
        # BUILD PLAY — CORE v48 + LAB PARALLELO
        # ====================================================
        play = self.build_play(e)

        if play and not self.active:
            self.active = True
            self.colpi = 0
            self.play_uid += 1
            play["play_id"] = self.play_uid
            self.active_snapshot = play
            self.total_play += 1

            # Sessioni parallele indipendenti.
            self.create_terni_session(play, e)
            self.create_ambata_r2_session(play, e)

            self.append_csv_event(
                "PLAY",
                play=play,
                play_id=play["play_id"],
                e=e,
                colpo=0,
                session_type="V48",
                outcome="OPEN",
            )

            # Una riga CSV per strategia rende il file facile da analizzare.
            for key in LAB_STRATEGIES:
                suffix = key.replace("op", "")
                self.append_csv_event(
                    "TERNI_SESSION_OPEN",
                    play=play,
                    play_id=play["play_id"],
                    e=e,
                    colpo=0,
                    session_type="TERNI_7",
                    strategy=key.upper(),
                    jolly=play.get(f"terno_num_{suffix}"),
                    terni=play.get(f"terni_op{suffix}", []),
                    outcome="OPEN",
                )

            self.append_csv_event(
                "AMBATA_R2_OPEN",
                play=play,
                play_id=play["play_id"],
                e=e,
                colpo=0,
                session_type="AMBATA_R2",
                strategy="AMBATA_R2",
                jolly=play["ambata"],
                outcome="OPEN",
            )

            await self.tg(
                app,
                "🎯 PLAY v48 + FINAL RESEARCH\n"
                f"🔥 AMBATA = {play['ambata']}\n"
                f"✅ AMBI = {fmt_ambi(play['ambi'])}\n"
                f"• cluster = {', '.join(map(str, play['cluster_numbers']))}\n"
                f"• max_colpi v48 = {MAX_COLPI}\n"
                f"• terni lab indipendente = {TERNI_LAB_MAX_COLPI} colpi\n"
                f"• ambata raffica = {AMBATA_RAFFICA_MAX_COLPI} colpi\n"
                f"• play_id = {play['play_id']}\n\n"
                f"{self.play_lab_text(play)}"
            )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT SNIPER v48 + FINAL RESEARCH\n"
            f"• play v48 = {self.total_play}\n"
            f"• hit ambata eventi = {self.total_hit_ambata}\n"
            f"• hit ambo = {self.total_hit_ambo}\n"
            f"• stop = {self.total_stop}\n"
            f"• sessioni terni aperte ora = {len(self.terni_sessions)}\n"
            f"• sessioni ambata R2 aperte ora = {len(self.ambata_r2_sessions)}\n"
            f"• sessioni decina aperte ora = {len(self.decina_lab_sessions)}\n\n"
            f"{self.terni_lab_stats_text()}\n\n"
            f"{self.ambata_r2_stats_text()}\n\n"
            f"{self.decina_lab_stats_text()}\n\n"
            f"🧾 CSV = {CSV_FILE}"
        )


# ============================================================
# LOCK ANTI-DOPPIA ISTANZA
# ============================================================

_LOCK_HANDLE = None


def acquire_single_instance_lock():
    global _LOCK_HANDLE

    _LOCK_HANDLE = open(LOCK_FILE, "a+", encoding="utf-8")

    if fcntl is not None:
        try:
            fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("⚠️ Un'altra istanza SNIPER v48/LAB è già attiva. Avvio bloccato.")
            sys.exit(1)
    else:
        # Fallback: PID best-effort per sistemi senza fcntl.
        _LOCK_HANDLE.seek(0)
        old = _LOCK_HANDLE.read().strip()

        if old.isdigit():
            try:
                os.kill(int(old), 0)
                print("⚠️ Un'altra istanza sembra già attiva. Avvio bloccato.")
                sys.exit(1)
            except OSError:
                pass

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
# LOOP
# ============================================================

CHAT_ID = validate_env()
acquire_single_instance_lock()
bot = SNIPER_V48()


async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    current_day = day_key()

    if bot.day != current_day:
        bot.reset_for_new_day(current_day)
        await bot.tg(
            app,
            "🗓️ Nuovo giorno rilevato: reset operativo dedup/watch/hot. "
            "Storico numerico conservato; sessioni LAB precedenti chiuse."
        )

    es = parse_site()

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    # Primo avvio pulito: storico sì, replay no.
    if not bot.last_draws:
        bot.preload_today_as_processed(es)

        await bot.tg(
            app,
            "🚀 SNIPER v48 + FINAL RESEARCH + DECINA LAB AVVIATO\n"
            "✅ core v48 invariato\n"
            "✅ OP3 primary + OP9/OP6/OP7 control\n"
            "✅ Terni Lab indipendente 7 colpi\n"
            "✅ Ambata Raffica 2 indipendente\n"
            "✅ Decina Lab 10-19 Heat5 TOP3 soglia>=8, 2 colpi\n"
            f"✅ notifiche Decina Lab = {'ON' if DECINA_LAB_NOTIFY else 'OFF (CSV/statistiche attive)'}\n"
            "✅ storico iniziale marcato come processato\n"
            "✅ niente replay iniziale"
        )

    while True:
        try:
            current_day = day_key()

            if bot.day != current_day:
                bot.reset_for_new_day(current_day)

                await bot.tg(
                    app,
                    "🗓️ Nuovo giorno rilevato: reset operativo dedup/watch/hot. "
                    "Storico numerico conservato; sessioni LAB precedenti chiuse."
                )

                es = parse_site()
                if es:
                    bot.preload_today_as_processed(es)
                    await bot.tg(
                        app,
                        "🚀 SNIPER v48 + FINAL RESEARCH\n"
                        "✅ nuovo giorno inizializzato\n"
                        "✅ estrazioni già uscite oggi marcate come storico/processate"
                    )

                await asyncio.sleep(LOOP_SEC)
                continue

            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            print(f"Errore loop: {ex}")
            try:
                await bot.tg(app, f"⚠️ errore v48 final research: {ex}")
            except Exception:
                pass

        await asyncio.sleep(LOOP_SEC)


if __name__ == "__main__":
    asyncio.run(live())
