# ============================================================
# 🚀 SNIPER v48 — AMBATA + 3 AMBI CLEAN + TERNI LAB ESPANSO + AMBATA LAB
# PATCH: dedup/startup pulito + cambio giorno + CSV eventi + lock anti doppia istanza globale
# NUOVO: OP8A/OP8B/OP8C + Ambata Lab statistico
# NOTA: motore v48 invariato; tutto il Lab è solo test statistico
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib
import csv
import sys
import atexit

try:
    import fcntl
except ImportError:
    fcntl = None

from datetime import datetime
from itertools import combinations
from collections import Counter

from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder

import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STATE_FILE = os.path.join(BASE_DIR, "sniper_v48_state.json")
CSV_FILE = os.path.join(BASE_DIR, "sniper_v48_terni_lab_events.csv")

# Lock globale in /tmp: blocca doppie istanze anche se il bot viene lanciato da cartelle diverse.
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

# ============================================================
# AMBATA LAB - SOLO STATISTICA, NON MODIFICA LA v48
# ============================================================

AMBATA_LAB_MAX_COLPI = 4
AMBATA_HOT_MAX_COLPO = 2
AMBATA_REPEAT_WINDOW = 3


# ============================================================
# PARSER
# ============================================================

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
    if not nums:
        return ""
    return "-".join(map(str, nums))


def fmt_ambi(ambi):
    if not ambi:
        return ""

    parts = []
    for item in ambi:
        a, b = item["ambo"]
        parts.append(f"{a}-{b}")

    return ", ".join(parts)


def fmt_terni(terni):
    if not terni:
        return ""
    return ", ".join("-".join(map(str, t)) for t in terni)


def fmt_jolly(value):
    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return "-".join(map(str, value))

    return str(value)


CSV_FIELDS = [
    "time",
    "day",
    "event",
    "play_id",
    "estrazione",
    "colpo",
    "ambata",
    "ambi",
    "cluster",
    "op1_jolly",
    "op1_terni",
    "op2_jolly",
    "op2_terni",
    "op3_jolly",
    "op3_terni",
    "op4_jolly",
    "op4_terni",
    "op5_jolly",
    "op5_terni",
    "op6_jolly",
    "op6_terni",
    "op7_jolly",
    "op7_terni",
    "op8_jolly",
    "op8_terni",
    "op8a_jolly",
    "op8a_terni",
    "op8b_jolly",
    "op8b_terni",
    "op8c_jolly",
    "op8c_terni",
    "op9_jolly",
    "op9_terni",
    "hit_ambata",
    "hit_ambo",
    "hit_ambo_list",
    "hit_op1",
    "hit_op1_list",
    "hit_op2",
    "hit_op2_list",
    "hit_op3",
    "hit_op3_list",
    "hit_op4",
    "hit_op4_list",
    "hit_op5",
    "hit_op5_list",
    "hit_op6",
    "hit_op6_list",
    "hit_op7",
    "hit_op7_list",
    "hit_op8",
    "hit_op8_list",
    "hit_op8a",
    "hit_op8a_list",
    "hit_op8b",
    "hit_op8b_list",
    "hit_op8c",
    "hit_op8c_list",
    "hit_op9",
    "hit_op9_list",
    "total_play",
    "total_hit_ambata",
    "total_hit_ambo",
    "total_stop",
    "total_hit_op1",
    "total_hit_op2",
    "total_hit_op3",
    "total_hit_op4",
    "total_hit_op5",
    "total_hit_op6",
    "total_hit_op7",
    "total_hit_op8",
    "total_hit_op8a",
    "total_hit_op8b",
    "total_hit_op8c",
    "total_hit_op9",
    "ambata_lab_first_hit_colpo",
    "ambata_lab_hit_count_play",
    "ambata_lab_hit_colpi",
    "ambata_lab_hot",
    "ambata_lab_repeat",
    "total_ambata_first_hit_play",
    "total_ambata_within_1",
    "total_ambata_within_2",
    "total_ambata_within_3",
    "total_ambata_within_4",
    "total_ambata_within_7",
    "total_ambata_hot",
    "total_ambata_hot_to_ambo",
    "total_ambata_hot_to_stop",
    "total_ambata_repeat",
    "total_ambata_repeat_within_3",
    "total_ambata_first_hit_to_ambo",
    "total_ambata_first_hit_to_stop",
    "total_ambo_without_ambata",
    "total_stop_without_ambata"
]

def ensure_csv():
    """
    Crea il CSV. Se esiste già un CSV con vecchie colonne, lo archivia
    e ne crea uno nuovo compatibile con il Terni Lab espanso.
    """
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, "r", encoding="utf-8", newline="") as f:
                header = f.readline().strip().split(",")

            if header == CSV_FIELDS:
                return

            backup = CSV_FILE.replace(".csv", f"_old_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            os.replace(CSV_FILE, backup)

        except Exception:
            backup = CSV_FILE.replace(".csv", f"_old_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
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
        self.version = "v48_terni_lab_expanded_ambata_lab_op8_split"

        self.day = day_key()

        self.max_e = 0
        self.last_fp = None

        self.last_draws = []

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

        self.total_play = 0
        self.total_hit_ambata = 0
        self.total_hit_ambo = 0
        self.total_stop = 0

        self.hit_terno_op1 = 0
        self.hit_terno_op2 = 0
        self.hit_terno_op3 = 0
        self.hit_terno_op4 = 0
        self.hit_terno_op5 = 0
        self.hit_terno_op6 = 0
        self.hit_terno_op7 = 0
        self.hit_terno_op8 = 0
        self.hit_terno_op8a = 0
        self.hit_terno_op8b = 0
        self.hit_terno_op8c = 0
        self.hit_terno_op9 = 0

        # AMBATA LAB - statistiche per play, non per singola uscita Telegram
        self.ambata_first_hit_play = 0
        self.ambata_within_1 = 0
        self.ambata_within_2 = 0
        self.ambata_within_3 = 0
        self.ambata_within_4 = 0
        self.ambata_within_7 = 0
        self.ambata_hot = 0
        self.ambata_hot_to_ambo = 0
        self.ambata_hot_to_stop = 0
        self.ambata_repeat = 0
        self.ambata_repeat_within_3 = 0
        self.ambata_first_hit_to_ambo = 0
        self.ambata_first_hit_to_stop = 0
        self.ambo_without_ambata = 0
        self.stop_without_ambata = 0

        self.play_uid = 0

        self.load_state()
        ensure_csv()

    async def tg(self, app, msg):
        max_len = 3000

        if not msg:
            return

        chunks = [
            msg[i:i + max_len]
            for i in range(0, len(msg), max_len)
        ]

        for chunk in chunks:
            for attempt in range(3):
                try:
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        text=chunk,
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=30,
                        pool_timeout=30
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

            "hit_terno_op1": self.hit_terno_op1,
            "hit_terno_op2": self.hit_terno_op2,
            "hit_terno_op3": self.hit_terno_op3,
            "hit_terno_op4": self.hit_terno_op4,
            "hit_terno_op5": self.hit_terno_op5,
            "hit_terno_op6": self.hit_terno_op6,
            "hit_terno_op7": self.hit_terno_op7,
            "hit_terno_op8": self.hit_terno_op8,
            "hit_terno_op8a": self.hit_terno_op8a,
            "hit_terno_op8b": self.hit_terno_op8b,
            "hit_terno_op8c": self.hit_terno_op8c,
            "hit_terno_op9": self.hit_terno_op9,

            "ambata_first_hit_play": self.ambata_first_hit_play,
            "ambata_within_1": self.ambata_within_1,
            "ambata_within_2": self.ambata_within_2,
            "ambata_within_3": self.ambata_within_3,
            "ambata_within_4": self.ambata_within_4,
            "ambata_within_7": self.ambata_within_7,
            "ambata_hot": self.ambata_hot,
            "ambata_hot_to_ambo": self.ambata_hot_to_ambo,
            "ambata_hot_to_stop": self.ambata_hot_to_stop,
            "ambata_repeat": self.ambata_repeat,
            "ambata_repeat_within_3": self.ambata_repeat_within_3,
            "ambata_first_hit_to_ambo": self.ambata_first_hit_to_ambo,
            "ambata_first_hit_to_stop": self.ambata_first_hit_to_stop,
            "ambo_without_ambata": self.ambo_without_ambata,
            "stop_without_ambata": self.stop_without_ambata,

            "play_uid": self.play_uid
        }

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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

            self.hit_terno_op1 = int(data.get("hit_terno_op1", 0))
            self.hit_terno_op2 = int(data.get("hit_terno_op2", 0))
            self.hit_terno_op3 = int(data.get("hit_terno_op3", 0))
            self.hit_terno_op4 = int(data.get("hit_terno_op4", 0))
            self.hit_terno_op5 = int(data.get("hit_terno_op5", 0))
            self.hit_terno_op6 = int(data.get("hit_terno_op6", 0))
            self.hit_terno_op7 = int(data.get("hit_terno_op7", 0))
            self.hit_terno_op8 = int(data.get("hit_terno_op8", 0))
            self.hit_terno_op8a = int(data.get("hit_terno_op8a", 0))
            self.hit_terno_op8b = int(data.get("hit_terno_op8b", 0))
            self.hit_terno_op8c = int(data.get("hit_terno_op8c", 0))
            self.hit_terno_op9 = int(data.get("hit_terno_op9", 0))

            self.ambata_first_hit_play = int(data.get("ambata_first_hit_play", 0))
            self.ambata_within_1 = int(data.get("ambata_within_1", 0))
            self.ambata_within_2 = int(data.get("ambata_within_2", 0))
            self.ambata_within_3 = int(data.get("ambata_within_3", 0))
            self.ambata_within_4 = int(data.get("ambata_within_4", 0))
            self.ambata_within_7 = int(data.get("ambata_within_7", 0))
            self.ambata_hot = int(data.get("ambata_hot", 0))
            self.ambata_hot_to_ambo = int(data.get("ambata_hot_to_ambo", 0))
            self.ambata_hot_to_stop = int(data.get("ambata_hot_to_stop", 0))
            self.ambata_repeat = int(data.get("ambata_repeat", 0))
            self.ambata_repeat_within_3 = int(data.get("ambata_repeat_within_3", 0))
            self.ambata_first_hit_to_ambo = int(data.get("ambata_first_hit_to_ambo", 0))
            self.ambata_first_hit_to_stop = int(data.get("ambata_first_hit_to_stop", 0))
            self.ambo_without_ambata = int(data.get("ambo_without_ambata", 0))
            self.stop_without_ambata = int(data.get("stop_without_ambata", 0))

            self.play_uid = int(data.get("play_uid", self.total_play))

        except Exception:
            pass

    def reset_for_new_day(self, new_day):
        """
        Reset operativo per cambio giorno.
        Le estrazioni ripartono da 1, quindi non si possono riusare max_e,
        processed_ids, watch e hot_confirmed del giorno precedente.
        Lo storico last_draws resta per dare continuità a lag/heat/pressure.
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

        self.save_state()

    # ========================================================
    # CSV EVENTS
    # ========================================================

    def append_csv_event(self, event, e=None, hit_data=None):
        ensure_csv()

        snap = self.active_snapshot or {}

        lab = snap.get("ambata_lab", {}) or {}

        row = {
            "time": now_txt(),
            "day": self.day,
            "event": event,
            "play_id": snap.get("play_id", ""),
            "estrazione": e if e is not None else "",
            "colpo": self.colpi if self.active or event in ["HIT_AMBO", "STOP", "HIT_TERNO", "HIT_AMBATA"] else "",
            "ambata": snap.get("ambata", ""),
            "ambi": fmt_ambi(snap.get("ambi", [])),
            "cluster": fmt_nums(snap.get("cluster_numbers", [])),
            "hit_ambata": False,
            "hit_ambo": False,
            "hit_ambo_list": "",
            "total_play": self.total_play,
            "total_hit_ambata": self.total_hit_ambata,
            "total_hit_ambo": self.total_hit_ambo,
            "total_stop": self.total_stop,

            "op8a_jolly": fmt_jolly(snap.get("terno_num_8a", "")),
            "op8a_terni": fmt_terni(snap.get("terni_op8a", [])),
            "op8b_jolly": fmt_jolly(snap.get("terno_num_8b", "")),
            "op8b_terni": fmt_terni(snap.get("terni_op8b", [])),
            "op8c_jolly": fmt_jolly(snap.get("terno_num_8c", "")),
            "op8c_terni": fmt_terni(snap.get("terni_op8c", [])),
            "hit_op8a": False,
            "hit_op8a_list": "",
            "hit_op8b": False,
            "hit_op8b_list": "",
            "hit_op8c": False,
            "hit_op8c_list": "",
            "total_hit_op8a": self.hit_terno_op8a,
            "total_hit_op8b": self.hit_terno_op8b,
            "total_hit_op8c": self.hit_terno_op8c,

            "ambata_lab_first_hit_colpo": lab.get("first_hit_colpo", ""),
            "ambata_lab_hit_count_play": lab.get("hit_count", 0),
            "ambata_lab_hit_colpi": fmt_jolly(lab.get("hit_colpi", [])),
            "ambata_lab_hot": bool(lab.get("hot", False)),
            "ambata_lab_repeat": bool(lab.get("repeat_counted", False)),
            "total_ambata_first_hit_play": self.ambata_first_hit_play,
            "total_ambata_within_1": self.ambata_within_1,
            "total_ambata_within_2": self.ambata_within_2,
            "total_ambata_within_3": self.ambata_within_3,
            "total_ambata_within_4": self.ambata_within_4,
            "total_ambata_within_7": self.ambata_within_7,
            "total_ambata_hot": self.ambata_hot,
            "total_ambata_hot_to_ambo": self.ambata_hot_to_ambo,
            "total_ambata_hot_to_stop": self.ambata_hot_to_stop,
            "total_ambata_repeat": self.ambata_repeat,
            "total_ambata_repeat_within_3": self.ambata_repeat_within_3,
            "total_ambata_first_hit_to_ambo": self.ambata_first_hit_to_ambo,
            "total_ambata_first_hit_to_stop": self.ambata_first_hit_to_stop,
            "total_ambo_without_ambata": self.ambo_without_ambata,
            "total_stop_without_ambata": self.stop_without_ambata,
        }

        for idx in range(1, 10):
            row[f"op{idx}_jolly"] = fmt_jolly(snap.get(f"terno_num_{idx}", ""))
            row[f"op{idx}_terni"] = fmt_terni(snap.get(f"terni_op{idx}", []))
            row[f"hit_op{idx}"] = False
            row[f"hit_op{idx}_list"] = ""
            row[f"total_hit_op{idx}"] = getattr(self, f"hit_terno_op{idx}", 0)

        if hit_data:
            row["hit_ambata"] = bool(hit_data.get("ambata_hit"))
            row["hit_ambo"] = bool(hit_data.get("ambi_hit"))
            row["hit_ambo_list"] = fmt_ambi(hit_data.get("ambi_hit", []))

            for idx in range(1, 10):
                hits = hit_data.get(f"terni_op{idx}_hit", [])
                row[f"hit_op{idx}"] = bool(hits)
                row[f"hit_op{idx}_list"] = fmt_terni(hits)

            for sub in ["8a", "8b", "8c"]:
                hits = hit_data.get(f"terni_op{sub}_hit", [])
                row[f"hit_op{sub}"] = bool(hits)
                row[f"hit_op{sub}_list"] = fmt_terni(hits)

        with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow(row)

    def terni_stats_text(self):
        lines = []

        for i in range(1, 10):
            lines.append(f"• op{i} = {getattr(self, f'hit_terno_op{i}', 0)}")

            if i == 8:
                lines.append(f"  - op8A = {self.hit_terno_op8a}")
                lines.append(f"  - op8B = {self.hit_terno_op8b}")
                lines.append(f"  - op8C = {self.hit_terno_op8c}")

        return "\n".join(lines)

    def ambata_lab_stats_text(self):
        return (
            "📊 AMBATA LAB\n"
            f"• play con ambata uscita = {self.ambata_first_hit_play}\n"
            f"• entro colpo 1 = {self.ambata_within_1}\n"
            f"• entro colpo 2 = {self.ambata_within_2}\n"
            f"• entro colpo 3 = {self.ambata_within_3}\n"
            f"• entro colpo 4 = {self.ambata_within_4}\n"
            f"• entro colpo 7 = {self.ambata_within_7}\n"
            f"• ambata hot <= {AMBATA_HOT_MAX_COLPO} colpi = {self.ambata_hot}\n"
            f"• hot -> ambo = {self.ambata_hot_to_ambo}\n"
            f"• hot -> stop = {self.ambata_hot_to_stop}\n"
            f"• repeat ambata = {self.ambata_repeat}\n"
            f"• repeat entro {AMBATA_REPEAT_WINDOW} colpi = {self.ambata_repeat_within_3}\n"
            f"• ambo senza ambata = {self.ambo_without_ambata}\n"
            f"• stop senza ambata = {self.stop_without_ambata}"
        )

    def new_ambata_lab_snapshot(self):
        return {
            "first_hit_colpo": None,
            "hit_count": 0,
            "hit_colpi": [],
            "hot": False,
            "repeat_counted": False,
            "closed": False
        }

    def update_ambata_lab_on_draw(self, hit_data):
        """
        Statistica parallela: studia come esce l'ambata del play v48.
        Non modifica colpi, ambi, stop o costruzione play.
        """
        if not self.active_snapshot:
            return

        lab = self.active_snapshot.setdefault(
            "ambata_lab",
            self.new_ambata_lab_snapshot()
        )

        if not hit_data.get("ambata_hit"):
            return

        lab["hit_count"] = int(lab.get("hit_count", 0)) + 1
        lab.setdefault("hit_colpi", []).append(self.colpi)

        if lab.get("first_hit_colpo") is None:
            lab["first_hit_colpo"] = self.colpi
            self.ambata_first_hit_play += 1

            if self.colpi <= 1:
                self.ambata_within_1 += 1
            if self.colpi <= 2:
                self.ambata_within_2 += 1
            if self.colpi <= 3:
                self.ambata_within_3 += 1
            if self.colpi <= AMBATA_LAB_MAX_COLPI:
                self.ambata_within_4 += 1
            if self.colpi <= MAX_COLPI:
                self.ambata_within_7 += 1

            if self.colpi <= AMBATA_HOT_MAX_COLPO:
                lab["hot"] = True
                self.ambata_hot += 1

            return

        if not lab.get("repeat_counted"):
            lab["repeat_counted"] = True
            self.ambata_repeat += 1

            first = int(lab.get("first_hit_colpo") or self.colpi)
            if self.colpi - first <= AMBATA_REPEAT_WINDOW:
                self.ambata_repeat_within_3 += 1

    def finalize_ambata_lab_on_close(self, close_event):
        """
        Chiude il conteggio Ambata Lab quando il play finisce con HIT_AMBO o STOP.
        """
        if not self.active_snapshot:
            return

        lab = self.active_snapshot.setdefault(
            "ambata_lab",
            self.new_ambata_lab_snapshot()
        )

        if lab.get("closed"):
            return

        lab["closed"] = True

        has_first = lab.get("first_hit_colpo") is not None
        is_hot = bool(lab.get("hot"))

        if close_event == "HIT_AMBO":
            if has_first:
                self.ambata_first_hit_to_ambo += 1
            else:
                self.ambo_without_ambata += 1

            if is_hot:
                self.ambata_hot_to_ambo += 1

        elif close_event == "STOP":
            if has_first:
                self.ambata_first_hit_to_stop += 1
            else:
                self.stop_without_ambata += 1

            if is_hot:
                self.ambata_hot_to_stop += 1

    def terni_play_blocks_text(self, play):
        labels = {
            1: "HOT CONFERMATO",
            2: "RITARDATARIO TOP 1",
            3: "SCORE FUORI CLUSTER",
            4: "SUPER FREQUENTE 20",
            5: "SUPER FREQUENTE 60",
            6: "STESSA DECINA AMBATA",
            7: "STESSA DECINA DINAMICA",
            8: "RITARDATARI TOP 3",
            9: "MIX SCORE+RITARDO",
        }

        blocks = []

        for idx in range(1, 10):
            jolly = fmt_jolly(play.get(f"terno_num_{idx}")) or "None"

            if idx == 8:
                a_txt = fmt_terni(play.get("terni_op8a", [])) or "nessuno"
                b_txt = fmt_terni(play.get("terni_op8b", [])) or "nessuno"
                c_txt = fmt_terni(play.get("terni_op8c", [])) or "nessuno"

                blocks.append(
                    f"🧪 OP8 {labels[idx]} | jolly = {jolly}\n"
                    f"OP8A primo ritardatario = {fmt_jolly(play.get('terno_num_8a')) or 'None'}\n{a_txt}\n"
                    f"OP8B secondo ritardatario = {fmt_jolly(play.get('terno_num_8b')) or 'None'}\n{b_txt}\n"
                    f"OP8C terzo ritardatario = {fmt_jolly(play.get('terno_num_8c')) or 'None'}\n{c_txt}"
                )
                continue

            terni = play.get(f"terni_op{idx}", [])
            txt = fmt_terni(terni) or "nessuno"
            blocks.append(f"🧪 OP{idx} {labels[idx]} | jolly = {jolly}\n{txt}")

        return "\n\n".join(blocks)

    # ========================================================
    # DEDUP
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
        """
        Usa le estrazioni già presenti sul sito solo come storico iniziale.
        Importantissimo: le marca tutte come processate, non solo l'ultima.
        Così il bot non ristampa e non rigioca vecchie estrazioni dopo l'avvio.
        """
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
    # FEATURES
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
        return sum(
            1 for d in self.last_draws[-window:]
            if n in d
        )

    def pressure(self, n):
        weights = [5, 4, 3, 2, 1]

        return sum(
            w for i, w in enumerate(weights)
            if i < len(self.last_draws)
            and n in self.last_draws[-(i + 1)]
        )

    def recent_frequency(self, n, window=20):
        return sum(
            1 for d in self.last_draws[-window:]
            if n in d
        )

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
                n
            )
        )

        return clean[0]

    # ========================================================
    # TOP RITARDATARI
    # ========================================================

    def top_ritardatari(self):
        data = []

        for n in range(1, 91):
            data.append({
                "number": n,
                "lag": self.lag(n)
            })

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
                    "lag": top10[idx]["lag"]
                })

        return top10, selected

    # ========================================================
    # CLEAN
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

    # ========================================================
    # UPDATE HOT
    # ========================================================

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
                    "initial_lag": item["lag"]
                }

            else:
                self.watch[key]["hits"] += 1
                self.watch[key]["last_e"] = e

                if self.watch[key]["hits"] >= 2:
                    self.hot_confirmed[key] = {
                        **self.watch[key],
                        "confirmed_e": e
                    }

                    self.watch.pop(key, None)

        self.clean_old_watch(e)
        self.clean_old_hot(e)

    # ========================================================
    # SCORE
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
    # DUPLICATE CLUSTER
    # ========================================================

    def duplicate_cluster(self, cluster_numbers, e):
        if not self.last_cluster_numbers:
            return False

        if e - self.last_cluster_e >= CLUSTER_REUSE_AFTER:
            return False

        overlap = len(
            set(cluster_numbers)
            &
            set(self.last_cluster_numbers)
        )

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
            pair = tuple(sorted((
                int(a["number"]),
                int(b["number"])
            )))

            score = self.confirmed_score(a, e) + self.confirmed_score(b, e)

            pair_candidates.append({
                "ambo": pair,
                "score": round(score, 2)
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
        # DA QUI IN POI: SOLO TERNI LAB, NON TOCCA GLI AMBI
        # ==================================================

        outside_cluster = [n for n in range(1, 91) if n not in cluster_numbers]

        # OP1 - miglior hot confermato fuori cluster
        hot_outside = []

        for item in hot_items:
            n = int(item["number"])

            if n in cluster_numbers:
                continue

            hot_outside.append((n, self.number_score(n, e)))

        hot_outside.sort(key=lambda x: -x[1])
        terno_num_1 = hot_outside[0][0] if hot_outside else None

        # OP2 - miglior ritardatario fuori cluster
        top10 = self.top_ritardatari()
        ritardatari_outside = [
            int(r["number"])
            for r in top10
            if int(r["number"]) not in cluster_numbers
        ]

        terno_num_2 = ritardatari_outside[0] if ritardatari_outside else None

        # OP3 - miglior score assoluto fuori cluster
        all_scores = []

        for n in outside_cluster:
            all_scores.append((n, self.number_score(n, e)))

        all_scores.sort(key=lambda x: -x[1])
        terno_num_3 = all_scores[0][0] if all_scores else None

        # OP4 - numero super frequente nelle ultime 20 estrazioni
        freq20 = []

        for n in outside_cluster:
            freq20.append((
                n,
                self.recent_frequency(n, 20),
                self.recent_frequency(n, 60),
                self.number_score(n, e)
            ))

        freq20.sort(key=lambda x: (-x[1], -x[2], -x[3], x[0]))
        terno_num_4 = freq20[0][0] if freq20 else None

        # OP5 - numero super frequente nelle ultime 60 estrazioni
        freq60 = []

        for n in outside_cluster:
            freq60.append((
                n,
                self.recent_frequency(n, 60),
                self.recent_frequency(n, 20),
                self.number_score(n, e)
            ))

        freq60.sort(key=lambda x: (-x[1], -x[2], -x[3], x[0]))
        terno_num_5 = freq60[0][0] if freq60 else None

        # OP6 - miglior numero della stessa decina dell'ambata
        decina_ambata = [
            n for n in self.decina_numbers(ambata)
            if n not in cluster_numbers
        ]

        terno_num_6 = self.best_by_score(decina_ambata, e)

        # OP7 - stessa decina dinamica: un jolly diverso per ogni ambo
        # Per ogni ambo cerca il miglior numero nella stessa decina di uno
        # dei due numeri dell'ambo, escluso il cluster.
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

        # OP8 - primi 3 ritardatari fuori cluster
        # OP8 totale resta la somma; OP8A/B/C servono solo a capire
        # quale posizione del ritardatario prende di più.
        terno_num_8 = ritardatari_outside[:3]
        terno_num_8a = terno_num_8[0] if len(terno_num_8) >= 1 else None
        terno_num_8b = terno_num_8[1] if len(terno_num_8) >= 2 else None
        terno_num_8c = terno_num_8[2] if len(terno_num_8) >= 3 else None

        # OP9 - mix score + ritardo + frequenza recente
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

        terni_op1 = self.build_terni_single_jolly(ambi, terno_num_1)
        terni_op2 = self.build_terni_single_jolly(ambi, terno_num_2)
        terni_op3 = self.build_terni_single_jolly(ambi, terno_num_3)
        terni_op4 = self.build_terni_single_jolly(ambi, terno_num_4)
        terni_op5 = self.build_terni_single_jolly(ambi, terno_num_5)
        terni_op6 = self.build_terni_single_jolly(ambi, terno_num_6)

        terni_op8a = self.build_terni_single_jolly(ambi, terno_num_8a)
        terni_op8b = self.build_terni_single_jolly(ambi, terno_num_8b)
        terni_op8c = self.build_terni_single_jolly(ambi, terno_num_8c)

        terni_op8 = sorted(set(terni_op8a + terni_op8b + terni_op8c))

        terni_op9 = self.build_terni_single_jolly(ambi, terno_num_9)

        return {
            "ambata": ambata,
            "ambi": ambi,
            "cluster_numbers": cluster_numbers,

            "terno_num_1": terno_num_1,
            "terno_num_2": terno_num_2,
            "terno_num_3": terno_num_3,
            "terno_num_4": terno_num_4,
            "terno_num_5": terno_num_5,
            "terno_num_6": terno_num_6,
            "terno_num_7": terno_num_7,
            "terno_num_8": terno_num_8,
            "terno_num_8a": terno_num_8a,
            "terno_num_8b": terno_num_8b,
            "terno_num_8c": terno_num_8c,
            "terno_num_9": terno_num_9,

            "ambata_lab": self.new_ambata_lab_snapshot(),

            "terni_op1": terni_op1,
            "terni_op2": terni_op2,
            "terni_op3": terni_op3,
            "terni_op4": terni_op4,
            "terni_op5": terni_op5,
            "terni_op6": terni_op6,
            "terni_op7": terni_op7,
            "terni_op8": terni_op8,
            "terni_op8a": terni_op8a,
            "terni_op8b": terni_op8b,
            "terni_op8c": terni_op8c,
            "terni_op9": terni_op9
        }

    # ========================================================
    # CHECK HIT
    # ========================================================

    def check_hit(self, nums):
        s = set(nums)
        snap = self.active_snapshot

        ambata_hit = snap["ambata"] in s

        ambi_hit = []

        for item in snap["ambi"]:
            a, b = item["ambo"]

            if a in s and b in s:
                ambi_hit.append(item)

        out = {
            "ambata_hit": ambata_hit,
            "ambi_hit": ambi_hit
        }

        for idx in range(1, 10):
            hits = []

            for t in snap.get(f"terni_op{idx}", []):
                if all(x in s for x in t):
                    hits.append(t)

            out[f"terni_op{idx}_hit"] = hits

        for sub in ["8a", "8b", "8c"]:
            hits = []

            for t in snap.get(f"terni_op{sub}", []):
                if all(x in s for x in t):
                    hits.append(t)

            out[f"terni_op{sub}_hit"] = hits

        return out

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
        # PLAY ATTIVO
        # ====================================================

        if self.active:
            self.colpi += 1

            hit_data = self.check_hit(nums)
            self.update_ambata_lab_on_draw(hit_data)

            ambi_txt = ", ".join(
                f"{a}-{b}"
                for h in hit_data["ambi_hit"]
                for a, b in [h["ambo"]]
            ) or "nessuno"

            terni_hit_lines = []

            for idx in range(1, 10):
                hits = hit_data.get(f"terni_op{idx}_hit", [])

                if hits:
                    terni_hit_lines.append(
                        f"• OP{idx} = {fmt_terni(hits)}"
                    )

                    if idx == 8:
                        for sub_label, sub_key in [
                            ("OP8A", "8a"),
                            ("OP8B", "8b"),
                            ("OP8C", "8c"),
                        ]:
                            sub_hits = hit_data.get(f"terni_op{sub_key}_hit", [])
                            if sub_hits:
                                terni_hit_lines.append(
                                    f"  - {sub_label} = {fmt_terni(sub_hits)}"
                                )

            terni_hit_txt = "\n".join(terni_hit_lines) or "• nessun terno"

            # ================= AMBATA =================

            if hit_data["ambata_hit"]:
                self.total_hit_ambata += 1
                self.append_csv_event("HIT_AMBATA", e, hit_data)

                await self.tg(
                    app,
                    f"🎯 AMBATA PRESA v48 | colpo {self.colpi}\n"
                    f"• ambata = {self.active_snapshot['ambata']}"
                )

            # ================= TERNI TEST =================

            any_terno_hit = False

            for idx in range(1, 10):
                if hit_data.get(f"terni_op{idx}_hit", []):
                    setattr(
                        self,
                        f"hit_terno_op{idx}",
                        getattr(self, f"hit_terno_op{idx}", 0) + 1
                    )
                    any_terno_hit = True

            for sub in ["8a", "8b", "8c"]:
                if hit_data.get(f"terni_op{sub}_hit", []):
                    setattr(
                        self,
                        f"hit_terno_op{sub}",
                        getattr(self, f"hit_terno_op{sub}", 0) + 1
                    )
                    any_terno_hit = True

            if any_terno_hit:
                self.append_csv_event("HIT_TERNO", e, hit_data)

                await self.tg(
                    app,
                    f"💥 HIT TERNO TEST v48 | colpo {self.colpi}\n"
                    f"{terni_hit_txt}\n\n"
                    f"📊 TERNI TEST\n"
                    f"{self.terni_stats_text()}\n\n"
                    f"{self.ambata_lab_stats_text()}"
                )

            # ================= HIT AMBO =================

            if hit_data["ambi_hit"]:
                self.total_hit_ambo += 1
                self.finalize_ambata_lab_on_close("HIT_AMBO")
                self.append_csv_event("HIT_AMBO", e, hit_data)

                await self.tg(
                    app,
                    f"🔥 HIT AMBO v48 | colpo {self.colpi}\n"
                    f"• ambi = {ambi_txt}\n\n"
                    f"📊 STATS\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}\n\n"
                    f"📊 TERNI TEST\n"
                    f"{self.terni_stats_text()}\n\n"
                    f"{self.ambata_lab_stats_text()}"
                )

                self.last_cluster_numbers = self.active_snapshot["cluster_numbers"]
                self.last_cluster_e = e

                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None

                self.save_state()
                return

            # ================= STOP =================

            if self.colpi >= MAX_COLPI:
                self.total_stop += 1
                self.finalize_ambata_lab_on_close("STOP")
                self.append_csv_event("STOP", e, hit_data)

                await self.tg(
                    app,
                    f"🛑 STOP v48 | {MAX_COLPI} colpi\n\n"
                    f"📊 STATS\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}\n\n"
                    f"📊 TERNI TEST\n"
                    f"{self.terni_stats_text()}\n\n"
                    f"{self.ambata_lab_stats_text()}"
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
        # COOLDOWN
        # ====================================================

        if self.cooldown > 0:
            self.cooldown -= 1
            self.save_state()
            return

        # ====================================================
        # HISTORY
        # ====================================================

        if len(self.last_draws) < 30:
            return

        # ====================================================
        # HOT UPDATE
        # ====================================================

        top10, selected = self.selected_ritardatari()

        self.update_watch_and_confirmed(
            e,
            nums,
            selected
        )

        # ====================================================
        # BUILD PLAY
        # ====================================================

        play = self.build_play(e)

        if play and not self.active:
            self.active = True
            self.colpi = 0
            self.play_uid += 1
            play["play_id"] = self.play_uid
            self.active_snapshot = play
            self.total_play += 1

            self.append_csv_event("PLAY", e)

            ambi_txt = ", ".join(
                f"{a}-{b}"
                for item in play["ambi"]
                for a, b in [item["ambo"]]
            )

            cluster_txt = ", ".join(
                map(str, play["cluster_numbers"])
            )

            await self.tg(
                app,
                "🎯 PLAY v48 + TERNI LAB ESPANSO + AMBATA LAB\n"
                f"🔥 AMBATA = {play['ambata']}\n"
                f"✅ AMBI = {ambi_txt}\n"
                f"• cluster = {cluster_txt}\n"
                f"• max_colpi = {MAX_COLPI}\n"
                f"• play_id = {play['play_id']}\n\n"
                f"{self.terni_play_blocks_text(play)}"
            )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v48 + TERNI LAB ESPANSO + AMBATA LAB\n"
            f"• play = {self.total_play}\n"
            f"• hit ambata = {self.total_hit_ambata}\n"
            f"• hit ambo = {self.total_hit_ambo}\n"
            f"• stop = {self.total_stop}\n\n"
            f"📊 TERNI TEST\n"
            f"{self.terni_stats_text()}\n\n"
            f"{self.ambata_lab_stats_text()}\n\n"
            f"🧾 CSV = {CSV_FILE}"
        )


# ============================================================
# LOCK ANTI-DOPPIA ISTANZA
# ============================================================

_LOCK_HANDLE = None


def acquire_single_instance_lock():
    """
    Evita che due copie del bot girino insieme.
    È la patch più importante per non avere doppioni Telegram e CSV falsati.
    """
    global _LOCK_HANDLE

    _LOCK_HANDLE = open(LOCK_FILE, "w", encoding="utf-8")

    if fcntl is None:
        _LOCK_HANDLE.write(str(os.getpid()))
        _LOCK_HANDLE.flush()
        return

    try:
        fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("⚠️ Bot già attivo: seconda istanza bloccata.")
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
# LOOP
# ============================================================

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
            "Storico numerico conservato."
        )

    es = parse_site()

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    if not bot.last_draws:
        bot.preload_today_as_processed(es)

        await bot.tg(
            app,
            "🚀 SNIPER v48 + TERNI LAB ESPANSO + AMBATA LAB AVVIATO\n"
            "✅ storico iniziale caricato\n"
            "✅ tutte le estrazioni già presenti sono marcate come processate\n"
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
                    "Storico numerico conservato."
                )

                es = parse_site()

                if es:
                    bot.preload_today_as_processed(es)
                    await bot.tg(
                        app,
                        "🚀 SNIPER v48 + TERNI LAB ESPANSO + AMBATA LAB AVVIATO\n"
                        "✅ nuovo giorno inizializzato\n"
                        "✅ estrazioni già uscite oggi marcate come storico/processate"
                    )

                await asyncio.sleep(LOOP_SEC)
                continue

            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(
                    app,
                    e,
                    nums
                )

        except Exception as ex:
            await bot.tg(
                app,
                f"⚠️ errore v48: {ex}"
            )

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
