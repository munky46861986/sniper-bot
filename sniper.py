# ============================================================
# 🚀 SNIPER v48 — AMBATA + 3 AMBI CLEAN
#
# FILOSOFIA:
# ✅ focus profitto reale
# ✅ ambata forte
# ✅ 3 ambi principali
# ✅ terni solo osservazione
# ✅ anti-spam cluster
# ✅ cluster riutilizzabile dopo 12 estrazioni
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib

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

    r = requests.get(
        URL,
        headers=HEADERS,
        timeout=20
    )

    r.raise_for_status()

    text = BeautifulSoup(
        r.text,
        "html.parser"
    ).get_text("\n", strip=True)

    lines = [
        x.strip()
        for x in text.splitlines()
        if x.strip()
    ]

    out = {}

    i = 0

    while i < len(lines):

        m = re.search(
            r"Estrazione\s+.*?\bn\.\s*(\d+)",
            lines[i],
            re.IGNORECASE
        )

        if not m:
            i += 1
            continue

        e = int(m.group(1))

        nums = []

        i += 1

        while i < len(lines):

            row = lines[i]

            if re.search(
                r"Estrazione\s+.*?\bn\.\s*\d+",
                row,
                re.IGNORECASE
            ):
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


# ============================================================
# UTILS
# ============================================================

def fingerprint(e, nums):

    return hashlib.md5(
        f"{e}-{'-'.join(map(str, nums))}".encode()
    ).hexdigest()


def day_key():

    return datetime.now().strftime("%Y-%m-%d")


# ============================================================
# BOT
# ============================================================

class SNIPER_V48:

    def __init__(self):

        self.version = "v48"

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

        self.load_state()

    # ========================================================
    # TELEGRAM SAFE
    # ========================================================

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

                    print(
                        f"Telegram send error "
                        f"attempt {attempt + 1}: {ex}"
                    )

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
            "total_stop": self.total_stop
        }

        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

    def load_state(self):

        if not os.path.exists(STATE_FILE):
            return

        try:

            with open(
                STATE_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            self.day = data.get(
                "day",
                day_key()
            )

            self.max_e = int(data.get("max_e", 0))
            self.last_fp = data.get("last_fp")

            self.last_draws = data.get(
                "last_draws",
                []
            )[-HISTORY_MAX:]

            self.processed_ids = data.get(
                "processed_ids",
                []
            )[-PROCESSED_MAX:]

            self.processed_fps = data.get(
                "processed_fps",
                []
            )[-PROCESSED_MAX:]

            self.watch = data.get("watch", {})
            self.hot_confirmed = data.get("hot_confirmed", {})

            self.active = bool(data.get("active", False))
            self.colpi = int(data.get("colpi", 0))
            self.cooldown = int(data.get("cooldown", 0))

            self.active_snapshot = data.get("active_snapshot")

            self.last_cluster_numbers = data.get(
                "last_cluster_numbers",
                []
            )

            self.last_cluster_e = int(
                data.get("last_cluster_e", 0)
            )

            self.total_play = int(data.get("total_play", 0))
            self.total_hit_ambata = int(data.get("total_hit_ambata", 0))
            self.total_hit_ambo = int(data.get("total_hit_ambo", 0))
            self.total_stop = int(data.get("total_stop", 0))

        except Exception:
            pass

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

        data.sort(
            key=lambda x: (-x["lag"], x["number"])
        )

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

    def update_watch_and_confirmed(
        self,
        e,
        nums,
        selected
    ):

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

            score = (
                self.confirmed_score(a, e)
                + self.confirmed_score(b, e)
            )

            pair_candidates.append({

                "ambo": pair,
                "score": round(score, 2)
            })

        pair_candidates.sort(
            key=lambda x: -x["score"]
        )

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

        return {

            "ambata": ambata,
            "ambi": ambi,
            "cluster_numbers": cluster_numbers
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

        return {

            "ambata_hit": ambata_hit,
            "ambi_hit": ambi_hit
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

            # ================= AMBATA =================

            if hit_data["ambata_hit"]:

                self.total_hit_ambata += 1

                await self.tg(
                    app,
                    f"🎯 AMBATA PRESA v48 | "
                    f"colpo {self.colpi}\n"
                    f"• ambata = "
                    f"{self.active_snapshot['ambata']}"
                )

            # ================= HIT AMBO =================

            if hit_data["ambi_hit"]:

                self.total_hit_ambo += 1

                await self.tg(
                    app,
                    f"🔥 HIT AMBO v48 | "
                    f"colpo {self.colpi}\n"
                    f"• ambi = {ambi_txt}\n\n"
                    f"📊 STATS\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}"
                )

                self.last_cluster_numbers = self.active_snapshot[
                    "cluster_numbers"
                ]

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

                await self.tg(
                    app,
                    f"🛑 STOP v48 | "
                    f"{MAX_COLPI} colpi"
                )

                self.last_cluster_numbers = self.active_snapshot[
                    "cluster_numbers"
                ]

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

            self.active_snapshot = play

            self.total_play += 1

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
                "🎯 PLAY v48\n"
                f"🔥 AMBATA = {play['ambata']}\n"
                f"✅ AMBI = {ambi_txt}\n"
                f"• cluster = {cluster_txt}\n"
                f"• max_colpi = {MAX_COLPI}"
            )

        self.save_state()


# ============================================================
# LOOP
# ============================================================

bot = SNIPER_V48()


async def live():

    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    if not es:

        await bot.tg(
            app,
            "⚠️ parser vuoto"
        )

        return

    if not bot.last_draws:

        for e, nums in es:
            bot.last_draws.append(nums)

        bot.last_draws = bot.last_draws[-HISTORY_MAX:]

        bot.max_e = es[-1][0]

        bot.last_fp = fingerprint(
            es[-1][0],
            es[-1][1]
        )

        bot.processed_ids.append(es[-1][0])
        bot.processed_fps.append(bot.last_fp)

        bot.save_state()

        await bot.tg(
            app,
            "🚀 SNIPER v48 AVVIATO"
        )

    while True:

        try:

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
