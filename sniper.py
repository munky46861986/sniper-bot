# ============================================================
# 🚀 SNIPER v48 — AMBATA + 3 AMBI CLEAN + TEST 9 TERNI
# PATCH: dedup/startup pulito + cambio giorno + CSV eventi
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib
import csv

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

STATE_FILE = "sniper_v48_state.json"
CSV_FILE = "sniper_v48_terni_lab_events.csv"

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
    "hit_ambata",
    "hit_ambo",
    "hit_ambo_list",
    "hit_op1",
    "hit_op1_list",
    "hit_op2",
    "hit_op2_list",
    "hit_op3",
    "hit_op3_list",
    "total_play",
    "total_hit_ambata",
    "total_hit_ambo",
    "total_stop",
    "total_hit_op1",
    "total_hit_op2",
    "total_hit_op3"
]


def ensure_csv():
    if os.path.exists(CSV_FILE):
        return

    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()


# ============================================================
# BOT
# ============================================================

class SNIPER_V48:

    def __init__(self):
        self.version = "v48_test_9_terni_cleanlog"

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
            "op1_jolly": snap.get("terno_num_1", ""),
            "op1_terni": fmt_terni(snap.get("terni_op1", [])),
            "op2_jolly": snap.get("terno_num_2", ""),
            "op2_terni": fmt_terni(snap.get("terni_op2", [])),
            "op3_jolly": snap.get("terno_num_3", ""),
            "op3_terni": fmt_terni(snap.get("terni_op3", [])),
            "hit_ambata": False,
            "hit_ambo": False,
            "hit_ambo_list": "",
            "hit_op1": False,
            "hit_op1_list": "",
            "hit_op2": False,
            "hit_op2_list": "",
            "hit_op3": False,
            "hit_op3_list": "",
            "total_play": self.total_play,
            "total_hit_ambata": self.total_hit_ambata,
            "total_hit_ambo": self.total_hit_ambo,
            "total_stop": self.total_stop,
            "total_hit_op1": self.hit_terno_op1,
            "total_hit_op2": self.hit_terno_op2,
            "total_hit_op3": self.hit_terno_op3
        }

        if hit_data:
            row["hit_ambata"] = bool(hit_data.get("ambata_hit"))
            row["hit_ambo"] = bool(hit_data.get("ambi_hit"))
            row["hit_ambo_list"] = fmt_ambi(hit_data.get("ambi_hit", []))

            row["hit_op1"] = bool(hit_data.get("terni_op1_hit"))
            row["hit_op1_list"] = fmt_terni(hit_data.get("terni_op1_hit", []))

            row["hit_op2"] = bool(hit_data.get("terni_op2_hit"))
            row["hit_op2_list"] = fmt_terni(hit_data.get("terni_op2_hit", []))

            row["hit_op3"] = bool(hit_data.get("terni_op3_hit"))
            row["hit_op3_list"] = fmt_terni(hit_data.get("terni_op3_hit", []))

        with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow(row)

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
        # TEST TERNI - OPZIONE 1
        # miglior hot confermato fuori cluster
        # ==================================================

        hot_outside = []

        for item in hot_items:
            n = int(item["number"])

            if n in cluster_numbers:
                continue

            hot_outside.append((n, self.number_score(n, e)))

        hot_outside.sort(key=lambda x: -x[1])

        terno_num_1 = hot_outside[0][0] if hot_outside else None

        # ==================================================
        # TEST TERNI - OPZIONE 2
        # miglior ritardatario fuori cluster
        # ==================================================

        top10 = self.top_ritardatari()

        terno_num_2 = None

        for r in top10:
            n = int(r["number"])

            if n not in cluster_numbers:
                terno_num_2 = n
                break

        # ==================================================
        # TEST TERNI - OPZIONE 3
        # miglior score assoluto fuori cluster
        # ==================================================

        all_scores = []

        for n in range(1, 91):
            if n in cluster_numbers:
                continue

            all_scores.append((n, self.number_score(n, e)))

        all_scores.sort(key=lambda x: -x[1])

        terno_num_3 = all_scores[0][0] if all_scores else None

        terni_op1 = []
        terni_op2 = []
        terni_op3 = []

        for item in ambi:
            a, b = item["ambo"]

            if terno_num_1:
                terni_op1.append(tuple(sorted((a, b, terno_num_1))))

            if terno_num_2:
                terni_op2.append(tuple(sorted((a, b, terno_num_2))))

            if terno_num_3:
                terni_op3.append(tuple(sorted((a, b, terno_num_3))))

        return {
            "ambata": ambata,
            "ambi": ambi,
            "cluster_numbers": cluster_numbers,

            "terno_num_1": terno_num_1,
            "terno_num_2": terno_num_2,
            "terno_num_3": terno_num_3,

            "terni_op1": terni_op1,
            "terni_op2": terni_op2,
            "terni_op3": terni_op3
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

        terni_op1_hit = []
        terni_op2_hit = []
        terni_op3_hit = []

        for t in snap.get("terni_op1", []):
            if all(x in s for x in t):
                terni_op1_hit.append(t)

        for t in snap.get("terni_op2", []):
            if all(x in s for x in t):
                terni_op2_hit.append(t)

        for t in snap.get("terni_op3", []):
            if all(x in s for x in t):
                terni_op3_hit.append(t)

        return {
            "ambata_hit": ambata_hit,
            "ambi_hit": ambi_hit,
            "terni_op1_hit": terni_op1_hit,
            "terni_op2_hit": terni_op2_hit,
            "terni_op3_hit": terni_op3_hit
        }

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

            ambi_txt = ", ".join(
                f"{a}-{b}"
                for h in hit_data["ambi_hit"]
                for a, b in [h["ambo"]]
            ) or "nessuno"

            op1_txt = ", ".join(
                "-".join(map(str, t))
                for t in hit_data["terni_op1_hit"]
            ) or "nessuno"

            op2_txt = ", ".join(
                "-".join(map(str, t))
                for t in hit_data["terni_op2_hit"]
            ) or "nessuno"

            op3_txt = ", ".join(
                "-".join(map(str, t))
                for t in hit_data["terni_op3_hit"]
            ) or "nessuno"

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

            if hit_data["terni_op1_hit"]:
                self.hit_terno_op1 += 1

            if hit_data["terni_op2_hit"]:
                self.hit_terno_op2 += 1

            if hit_data["terni_op3_hit"]:
                self.hit_terno_op3 += 1

            if (
                hit_data["terni_op1_hit"]
                or hit_data["terni_op2_hit"]
                or hit_data["terni_op3_hit"]
            ):
                self.append_csv_event("HIT_TERNO", e, hit_data)

                await self.tg(
                    app,
                    f"💥 HIT TERNO TEST v48 | colpo {self.colpi}\n"
                    f"• OP1 = {op1_txt}\n"
                    f"• OP2 = {op2_txt}\n"
                    f"• OP3 = {op3_txt}\n\n"
                    f"📊 TERNI TEST\n"
                    f"• op1 = {self.hit_terno_op1}\n"
                    f"• op2 = {self.hit_terno_op2}\n"
                    f"• op3 = {self.hit_terno_op3}"
                )

            # ================= HIT AMBO =================

            if hit_data["ambi_hit"]:
                self.total_hit_ambo += 1
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
                    f"• op1 = {self.hit_terno_op1}\n"
                    f"• op2 = {self.hit_terno_op2}\n"
                    f"• op3 = {self.hit_terno_op3}"
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
                    f"• op1 = {self.hit_terno_op1}\n"
                    f"• op2 = {self.hit_terno_op2}\n"
                    f"• op3 = {self.hit_terno_op3}"
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

            op1_txt = ", ".join(
                "-".join(map(str, t))
                for t in play["terni_op1"]
            ) or "nessuno"

            op2_txt = ", ".join(
                "-".join(map(str, t))
                for t in play["terni_op2"]
            ) or "nessuno"

            op3_txt = ", ".join(
                "-".join(map(str, t))
                for t in play["terni_op3"]
            ) or "nessuno"

            await self.tg(
                app,
                "🎯 PLAY v48 + TEST 9 TERNI\n"
                f"🔥 AMBATA = {play['ambata']}\n"
                f"✅ AMBI = {ambi_txt}\n"
                f"• cluster = {cluster_txt}\n"
                f"• max_colpi = {MAX_COLPI}\n"
                f"• play_id = {play['play_id']}\n\n"
                f"🧪 OP1 HOT CONFERMATO | jolly = {play['terno_num_1']}\n"
                f"{op1_txt}\n\n"
                f"🧪 OP2 RITARDATARIO | jolly = {play['terno_num_2']}\n"
                f"{op2_txt}\n\n"
                f"🧪 OP3 SCORE FUORI CLUSTER | jolly = {play['terno_num_3']}\n"
                f"{op3_txt}"
            )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v48 + TEST TERNI\n"
            f"• play = {self.total_play}\n"
            f"• hit ambata = {self.total_hit_ambata}\n"
            f"• hit ambo = {self.total_hit_ambo}\n"
            f"• stop = {self.total_stop}\n\n"
            f"📊 TERNI TEST\n"
            f"• op1 = {self.hit_terno_op1}\n"
            f"• op2 = {self.hit_terno_op2}\n"
            f"• op3 = {self.hit_terno_op3}\n\n"
            f"🧾 CSV = {CSV_FILE}"
        )


# ============================================================
# LOOP
# ============================================================

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
            "🚀 SNIPER v48 + TEST 9 TERNI AVVIATO\n"
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
                        "🚀 SNIPER v48 + TEST 9 TERNI AVVIATO\n"
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
