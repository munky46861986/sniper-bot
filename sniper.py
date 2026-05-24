# ============================================================
# 🚀 SNIPER v51 — DOPPIA AMBATA + EVENTI AMBO
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib

from datetime import datetime
from itertools import combinations

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

STATE_FILE = "sniper_v51_double_ambata.json"

LOOP_SEC = 60

HISTORY_MAX = 240
PROCESSED_MAX = 1000

TOP_RITARDATARI = 10
PLAY_POSITIONS = [6, 7, 8, 9, 10]

WATCH_WINDOW = 12
HOT_TTL = 45

MIN_HOT_ACTIVE = 3

MAX_AMBI_PER_EVENT = 3
MAX_COLPI_EVENTO = 6

COOLDOWN_EVENTO = 4

CLUSTER_REUSE_AFTER = 10

SWITCH_THRESHOLD = 35


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

class SNIPER_V51:

    def __init__(self):

        self.version = "v51_double_ambata"

        self.day = day_key()

        self.max_e = 0
        self.last_fp = None

        self.last_draws = []

        self.processed_ids = []
        self.processed_fps = []

        self.watch = {}
        self.hot_confirmed = {}

        # ================= MAIN AMBATA =================

        self.current_super_ambata = None
        self.current_super_score = 0

        # ================= SHADOW =================

        self.shadow_ambata = None
        self.shadow_score = 0

        # ================= EVENTI =================

        self.active_event = False
        self.event_colpi = 0
        self.event_snapshot = None
        self.cooldown_event = 0

        self.last_cluster_numbers = []
        self.last_cluster_e = 0

        # ================= STATS =================

        self.total_ambata_hit = 0
        self.total_shadow_hit = 0
        self.total_ambata_switch = 0

        self.total_event_play = 0
        self.total_event_hit = 0
        self.total_event_stop = 0

        self.load_state()

    # ========================================================
    # TELEGRAM
    # ========================================================

    async def tg(self, app, msg):

        if not msg:
            return

        try:

            await app.bot.send_message(
                chat_id=CHAT_ID,
                text=msg
            )

        except Exception as ex:

            print(ex)

    # ========================================================
    # SAVE
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

            "current_super_ambata": self.current_super_ambata,
            "current_super_score": self.current_super_score,

            "shadow_ambata": self.shadow_ambata,
            "shadow_score": self.shadow_score,

            "active_event": self.active_event,
            "event_colpi": self.event_colpi,
            "event_snapshot": self.event_snapshot,
            "cooldown_event": self.cooldown_event,

            "last_cluster_numbers": self.last_cluster_numbers,
            "last_cluster_e": self.last_cluster_e,

            "total_ambata_hit": self.total_ambata_hit,
            "total_shadow_hit": self.total_shadow_hit,
            "total_ambata_switch": self.total_ambata_switch,

            "total_event_play": self.total_event_play,
            "total_event_hit": self.total_event_hit,
            "total_event_stop": self.total_event_stop
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

    # ========================================================
    # LOAD
    # ========================================================

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

            self.day = data.get("day", day_key())

            self.max_e = data.get("max_e", 0)
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

            self.current_super_ambata = data.get("current_super_ambata")
            self.current_super_score = data.get("current_super_score", 0)

            self.shadow_ambata = data.get("shadow_ambata")
            self.shadow_score = data.get("shadow_score", 0)

            self.active_event = data.get("active_event", False)
            self.event_colpi = data.get("event_colpi", 0)
            self.event_snapshot = data.get("event_snapshot")
            self.cooldown_event = data.get("cooldown_event", 0)

            self.last_cluster_numbers = data.get(
                "last_cluster_numbers",
                []
            )

            self.last_cluster_e = data.get(
                "last_cluster_e",
                0
            )

            self.total_ambata_hit = data.get(
                "total_ambata_hit",
                0
            )

            self.total_shadow_hit = data.get(
                "total_shadow_hit",
                0
            )

            self.total_ambata_switch = data.get(
                "total_ambata_switch",
                0
            )

            self.total_event_play = data.get(
                "total_event_play",
                0
            )

            self.total_event_hit = data.get(
                "total_event_hit",
                0
            )

            self.total_event_stop = data.get(
                "total_event_stop",
                0
            )

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

        return selected

    # ========================================================
    # UPDATE HOT
    # ========================================================

    def update_watch(self, e, nums):

        selected = self.selected_ritardatari()

        s = set(nums)

        for item in selected:

            n = item["number"]

            key = str(n)

            if n not in s:
                continue

            if key not in self.watch:

                self.watch[key] = {

                    "number": n,
                    "hits": 1,
                    "first_e": e,
                    "last_e": e,
                    "lag": item["lag"]
                }

            else:

                self.watch[key]["hits"] += 1
                self.watch[key]["last_e"] = e

                if self.watch[key]["hits"] >= 2:

                    self.hot_confirmed[key] = {

                        **self.watch[key],
                        "confirmed_e": e
                    }

    # ========================================================
    # SCORE
    # ========================================================

    def super_score(self, n, e):

        hot = self.hot_confirmed.get(str(n))

        hot_bonus = 0

        if hot:

            age = e - hot["confirmed_e"]

            hot_bonus = (
                hot["hits"] * 20
                - age * 2
            )

        return (

            hot_bonus

            + self.heat(n) * 3

            + self.dominance(n, 6) * 4

            + self.pressure(n) * 2

            - self.lag(n)
        )

    # ========================================================
    # BUILD SCORES
    # ========================================================

    def build_scores(self, e):

        scores = []

        for item in self.hot_confirmed.values():

            n = item["number"]

            scores.append({

                "number": n,

                "score": round(
                    self.super_score(n, e),
                    2
                )
            })

        scores.sort(
            key=lambda x: -x["score"]
        )

        return scores

    # ========================================================
    # EVENTI
    # ========================================================

    def build_event(self, e):

        hot_items = list(
            self.hot_confirmed.values()
        )

        if len(hot_items) < MIN_HOT_ACTIVE:
            return None

        pairs = []

        for a, b in combinations(hot_items, 2):

            na = a["number"]
            nb = b["number"]

            score = (
                self.super_score(na, e)
                +
                self.super_score(nb, e)
            )

            pairs.append({

                "ambo": (na, nb),
                "score": round(score, 2)
            })

        pairs.sort(
            key=lambda x: -x["score"]
        )

        ambi = pairs[:MAX_AMBI_PER_EVENT]

        if not ambi:
            return None

        return {
            "ambi": ambi
        }

    # ========================================================
    # CHECK EVENT
    # ========================================================

    def check_event_hit(self, nums):

        s = set(nums)

        hits = []

        for item in self.event_snapshot["ambi"]:

            a, b = item["ambo"]

            if a in s and b in s:
                hits.append(item)

        return hits

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

        s = set(nums)

        await self.tg(
            app,
            f"📌 Estrazione {e}\n"
            f"🎱 {', '.join(map(str, nums))}"
        )

        # ====================================================
        # UPDATE WATCH
        # ====================================================

        if len(self.last_draws) >= 30:
            self.update_watch(e, nums)

        # ====================================================
        # BUILD MAIN + SHADOW
        # ====================================================

        scores = self.build_scores(e)

        if len(scores) >= 2:

            main = scores[0]
            shadow = scores[1]

            main_n = main["number"]
            main_score = main["score"]

            shadow_n = shadow["number"]
            shadow_score = shadow["score"]

            # ================================================
            # INIT
            # ================================================

            if self.current_super_ambata is None:

                self.current_super_ambata = main_n
                self.current_super_score = main_score

                self.shadow_ambata = shadow_n
                self.shadow_score = shadow_score

                await self.tg(
                    app,
                    "🔥 DOPPIA AMBATA ATTIVA v51\n"
                    f"• MAIN = {main_n}\n"
                    f"• SHADOW = {shadow_n}"
                )

            # ================================================
            # SWITCH
            # ================================================

            else:

                if (

                    main_n != self.current_super_ambata

                    and

                    main_score >
                    self.current_super_score + SWITCH_THRESHOLD
                ):

                    old_main = self.current_super_ambata

                    self.shadow_ambata = old_main
                    self.shadow_score = self.current_super_score

                    self.current_super_ambata = main_n
                    self.current_super_score = main_score

                    self.total_ambata_switch += 1

                    await self.tg(
                        app,
                        "🔁 SWITCH MAIN v51\n"
                        f"• {old_main} → {main_n}\n"
                        f"• nuova shadow = {old_main}"
                    )

                else:

                    self.current_super_score = main_score

                    if shadow_n != self.current_super_ambata:

                        self.shadow_ambata = shadow_n
                        self.shadow_score = shadow_score

            # ================================================
            # HIT MAIN
            # ================================================

            if self.current_super_ambata in s:

                self.total_ambata_hit += 1

                await self.tg(
                    app,
                    "🎯 HIT MAIN AMBATA v51\n"
                    f"• numero = {self.current_super_ambata}\n\n"
                    f"📊 STATS\n"
                    f"• hit main = {self.total_ambata_hit}\n"
                    f"• hit shadow = {self.total_shadow_hit}\n"
                    f"• switch = {self.total_ambata_switch}"
                )

            # ================================================
            # HIT SHADOW
            # ================================================

            if (

                self.shadow_ambata

                and

                self.shadow_ambata in s
            ):

                self.total_shadow_hit += 1

                await self.tg(
                    app,
                    "🌑 HIT SHADOW v51\n"
                    f"• numero = {self.shadow_ambata}\n\n"
                    f"📊 STATS\n"
                    f"• hit main = {self.total_ambata_hit}\n"
                    f"• hit shadow = {self.total_shadow_hit}"
                )

        # ====================================================
        # EVENTI
        # ====================================================

        if self.active_event:

            self.event_colpi += 1

            hits = self.check_event_hit(nums)

            if hits:

                self.total_event_hit += 1

                ambi_txt = ", ".join(

                    f"{a}-{b}"

                    for item in hits

                    for a, b in [item["ambo"]]
                )

                await self.tg(
                    app,
                    "🔥 HIT EVENTO AMBO v51\n"
                    f"• colpo = {self.event_colpi}\n"
                    f"• ambi = {ambi_txt}"
                )

                self.active_event = False
                self.event_colpi = 0
                self.event_snapshot = None
                self.cooldown_event = COOLDOWN_EVENTO

            elif self.event_colpi >= MAX_COLPI_EVENTO:

                self.total_event_stop += 1

                await self.tg(
                    app,
                    "🛑 STOP EVENTO v51"
                )

                self.active_event = False
                self.event_colpi = 0
                self.event_snapshot = None
                self.cooldown_event = COOLDOWN_EVENTO

        else:

            if self.cooldown_event > 0:

                self.cooldown_event -= 1

            else:

                evento = self.build_event(e)

                if evento:

                    self.active_event = True
                    self.event_colpi = 0
                    self.event_snapshot = evento

                    self.total_event_play += 1

                    ambi_txt = ", ".join(

                        f"{a}-{b}"

                        for item in evento["ambi"]

                        for a, b in [item["ambo"]]
                    )

                    await self.tg(
                        app,
                        "🚀 EVENTO AMBI v51\n"
                        f"• ambi = {ambi_txt}"
                    )

        self.save_state()

    # ========================================================
    # REPORT
    # ========================================================

    async def send_report(self, app):

        await self.tg(
            app,
            "📊 REPORT v51\n\n"

            f"🔥 MAIN\n"
            f"• numero = {self.current_super_ambata}\n"
            f"• hit = {self.total_ambata_hit}\n\n"

            f"🌑 SHADOW\n"
            f"• numero = {self.shadow_ambata}\n"
            f"• hit = {self.total_shadow_hit}\n\n"

            f"🔁 switch = {self.total_ambata_switch}\n\n"

            f"🔥 EVENTI\n"
            f"• play = {self.total_event_play}\n"
            f"• hit = {self.total_event_hit}\n"
            f"• stop = {self.total_event_stop}"
        )


# ============================================================
# LOOP
# ============================================================

bot = SNIPER_V51()


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
            "🚀 SNIPER v51 AVVIATO"
        )

    else:

        await bot.tg(
            app,
            "🚀 SNIPER v51 RIAVVIATO"
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
                f"⚠️ errore v51: {ex}"
            )

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
