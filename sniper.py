# ============================================================
# 🚀 SNIPER v53 — PLAY UFFICIALE: 2 AMBATE + 3 AMBI
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
HEADERS = {"User-Agent": "Mozilla/5.0"}

STATE_FILE = "sniper_v53_play_ufficiale.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

TOP_RITARDATARI = 10
PLAY_POSITIONS = [6, 7, 8, 9, 10]

WATCH_WINDOW = 12
HOT_TTL = 45

MIN_HOT_ACTIVE = 3
MAX_AMBI_PER_PLAY = 3
MAX_COLPI = 6
COOLDOWN_AFTER_PLAY = 4

SWITCH_THRESHOLD = 25


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
    return hashlib.md5(f"{e}-{'-'.join(map(str, nums))}".encode()).hexdigest()


def day_key():
    return datetime.now().strftime("%Y-%m-%d")


class SNIPER_V53:

    def __init__(self):
        self.version = "v53_play_ufficiale"

        self.day = day_key()
        self.max_e = 0
        self.last_fp = None

        self.last_draws = []
        self.processed_ids = []
        self.processed_fps = []

        self.watch = {}
        self.hot_confirmed = {}

        self.radar_dual = []
        self.radar_score = 0

        self.active = False
        self.colpi = 0
        self.cooldown = 0
        self.active_snapshot = None

        self.total_play = 0
        self.total_hit_ambata = 0
        self.total_hit_ambo = 0
        self.total_stop = 0

        self.load_state()

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
                        pool_timeout=30
                    )
                    break
                except Exception as ex:
                    print(f"Telegram error attempt {attempt + 1}: {ex}")
                    await asyncio.sleep(5)

    # ===================== STATE =============================

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
            "radar_dual": self.radar_dual,
            "radar_score": self.radar_score,
            "active": self.active,
            "colpi": self.colpi,
            "cooldown": self.cooldown,
            "active_snapshot": self.active_snapshot,
            "total_play": self.total_play,
            "total_hit_ambata": self.total_hit_ambata,
            "total_hit_ambo": self.total_hit_ambo,
            "total_stop": self.total_stop
        }

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            return

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            saved_day = data.get("day", day_key())

            if saved_day != day_key():
                self.day = day_key()
                return

            self.day = saved_day
            self.max_e = int(data.get("max_e", 0))
            self.last_fp = data.get("last_fp")

            self.last_draws = data.get("last_draws", [])[-HISTORY_MAX:]
            self.processed_ids = data.get("processed_ids", [])[-PROCESSED_MAX:]
            self.processed_fps = data.get("processed_fps", [])[-PROCESSED_MAX:]

            self.watch = data.get("watch", {})
            self.hot_confirmed = data.get("hot_confirmed", {})

            self.radar_dual = data.get("radar_dual", [])
            self.radar_score = float(data.get("radar_score", 0))

            self.active = bool(data.get("active", False))
            self.colpi = int(data.get("colpi", 0))
            self.cooldown = int(data.get("cooldown", 0))
            self.active_snapshot = data.get("active_snapshot")

            self.total_play = int(data.get("total_play", 0))
            self.total_hit_ambata = int(data.get("total_hit_ambata", 0))
            self.total_hit_ambo = int(data.get("total_hit_ambo", 0))
            self.total_stop = int(data.get("total_stop", 0))

        except Exception:
            pass

    # ===================== DEDUP =============================

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

    # ===================== FEATURES ==========================

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

    # ===================== RITARDATARI =======================

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

        return selected

    # ===================== CLEAN =============================

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

    # ===================== UPDATE HOT ========================

    def update_watch(self, e, nums):
        selected = self.selected_ritardatari()
        s = set(nums)

        for item in selected:
            n = int(item["number"])
            key = str(n)

            if n not in s:
                continue

            if key not in self.watch:
                self.watch[key] = {
                    "number": n,
                    "hits": 1,
                    "first_e": e,
                    "last_e": e,
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

    # ===================== SCORE =============================

    def super_score(self, n, e):
        hot = self.hot_confirmed.get(str(n))
        hot_bonus = 0

        if hot:
            age = e - int(hot["confirmed_e"])
            hot_bonus = (
                int(hot.get("hits", 0)) * 22
                - age * 2
                + int(hot.get("initial_lag", 0))
                - int(hot.get("position", 99))
            )

        return (
            hot_bonus
            + self.heat(n) * 3
            + self.dominance(n, 6) * 4
            + self.pressure(n) * 2
            - self.lag(n)
        )

    def build_scores(self, e):
        scores = []

        for item in self.hot_confirmed.values():
            n = int(item["number"])

            scores.append({
                "number": n,
                "score": round(self.super_score(n, e), 2),
                "heat": self.heat(n),
                "lag": self.lag(n),
                "dominance": self.dominance(n, 6),
                "pressure": self.pressure(n)
            })

        scores.sort(key=lambda x: -x["score"])
        return scores

    # ===================== RADAR DUAL ========================

    def update_radar_dual(self, e):
        scores = self.build_scores(e)

        if len(scores) < 2:
            return

        new_dual = [scores[0]["number"], scores[1]["number"]]
        new_score = scores[0]["score"] + scores[1]["score"]

        if not self.radar_dual:
            self.radar_dual = new_dual
            self.radar_score = new_score
            return

        old_set = set(self.radar_dual)
        new_set = set(new_dual)

        if old_set != new_set and new_score > self.radar_score + SWITCH_THRESHOLD:
            self.radar_dual = new_dual
            self.radar_score = new_score
        else:
            self.radar_score = max(self.radar_score, new_score)

    # ===================== BUILD PLAY ========================

    def build_play(self, e):
        hot_items = [
            x for x in self.hot_confirmed.values()
            if 0 <= e - int(x["confirmed_e"]) <= HOT_TTL
        ]

        if len(hot_items) < MIN_HOT_ACTIVE:
            return None

        if len(self.radar_dual) < 2:
            return None

        pairs = []

        for a, b in combinations(hot_items, 2):
            na = int(a["number"])
            nb = int(b["number"])

            score = self.super_score(na, e) + self.super_score(nb, e)

            pairs.append({
                "ambo": tuple(sorted((na, nb))),
                "score": round(score, 2)
            })

        pairs.sort(key=lambda x: -x["score"])
        ambi = pairs[:MAX_AMBI_PER_PLAY]

        if not ambi:
            return None

        return {
            "ambate": self.radar_dual[:2],
            "ambi": ambi
        }

    # ===================== CHECK =============================

    def check_hit(self, nums):
        s = set(nums)
        snap = self.active_snapshot

        ambate_hit = [n for n in snap["ambate"] if n in s]

        ambi_hit = []

        for item in snap["ambi"]:
            a, b = item["ambo"]

            if a in s and b in s:
                ambi_hit.append(item)

        return {
            "ambate_hit": ambate_hit,
            "ambi_hit": ambi_hit
        }

    # ===================== MAIN ==============================

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

        if len(self.last_draws) >= 30:
            self.update_watch(e, nums)
            self.update_radar_dual(e)

        # ================= PLAY ATTIVO =================

        if self.active:
            self.colpi += 1
            hit_data = self.check_hit(nums)

            ambate_txt = ", ".join(map(str, hit_data["ambate_hit"])) or "nessuna"

            ambi_txt = ", ".join(
                f"{a}-{b}"
                for item in hit_data["ambi_hit"]
                for a, b in [item["ambo"]]
            ) or "nessuno"

            if hit_data["ambate_hit"]:
                self.total_hit_ambata += 1

            await self.tg(
                app,
                f"🔎 CHECK v53 | colpo {self.colpi}/{MAX_COLPI}\n"
                f"• ambate uscite = {ambate_txt}\n"
                f"• ambi usciti = {ambi_txt}"
            )

            if hit_data["ambi_hit"]:
                self.total_hit_ambo += 1

                await self.tg(
                    app,
                    f"🔥 HIT PLAY v53 | colpo {self.colpi}\n"
                    f"• ambate uscite = {ambate_txt}\n"
                    f"• ambi = {ambi_txt}\n\n"
                    f"📊 STATS\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}"
                )

                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None
                self.save_state()
                return

            if self.colpi >= MAX_COLPI:
                self.total_stop += 1

                await self.tg(
                    app,
                    f"🛑 STOP PLAY v53 | {MAX_COLPI} colpi\n"
                    f"📊 STATS\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}"
                )

                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None
                self.save_state()
                return

            self.save_state()
            return

        # ================= COOLDOWN =================

        if self.cooldown > 0:
            self.cooldown -= 1
            self.save_state()
            return

        # ================= NUOVO PLAY =================

        play = self.build_play(e)

        if play and not self.active:
            self.active = True
            self.colpi = 0
            self.active_snapshot = play
            self.total_play += 1

            ambate_txt = ", ".join(map(str, play["ambate"]))

            ambi_txt = ", ".join(
                f"{a}-{b}"
                for item in play["ambi"]
                for a, b in [item["ambo"]]
            )

            await self.tg(
                app,
                "🎯 PLAY UFFICIALE v53\n"
                f"🔥 AMBATE = {ambate_txt}\n"
                f"✅ AMBI = {ambi_txt}\n"
                f"• max_colpi = {MAX_COLPI}"
            )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v53\n"
            f"• radar dual = {', '.join(map(str, self.radar_dual)) if self.radar_dual else 'nessuno'}\n"
            f"• play = {self.total_play}\n"
            f"• hit ambata = {self.total_hit_ambata}\n"
            f"• hit ambo = {self.total_hit_ambo}\n"
            f"• stop = {self.total_stop}"
        )


# ===================== LOOP ================================

bot = SNIPER_V53()


async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    if not bot.last_draws:
        for e, nums in es:
            bot.last_draws.append(nums)

        bot.last_draws = bot.last_draws[-HISTORY_MAX:]

        bot.max_e = es[-1][0]
        bot.last_fp = fingerprint(es[-1][0], es[-1][1])

        bot.processed_ids.append(es[-1][0])
        bot.processed_fps.append(bot.last_fp)

        bot.save_state()

        await bot.tg(app, "🚀 SNIPER v53 AVVIATO | LIVE_ONLY")

    else:
        await bot.tg(app, "🚀 SNIPER v53 RIAVVIATO")

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ errore v53: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
