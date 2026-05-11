# ============================================================
# 🚀 SNIPER v36 — ORA TOP FREQUENTI + HOT-LAG TERNI
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib
import subprocess
from datetime import datetime
from collections import Counter
from itertools import combinations
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STATE_FILE = "sniper_v36_ora_top_hotlag_terni_state.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

BLOCK_SIZE = 12
TOP_N = 10
PLAY_POSITIONS = [1, 2, 3, 6]

MAX_COLPI = 6
COOLDOWN_AFTER_PLAY = 0
MIN_HISTORY = 12

MIN_HEAT = 10
MIN_LAG = 1
MAX_LAG = 3
MIN_DOMINANCE = 3
MAX_DOMINANCE = 6

MIN_HOT_IN_TERNO = 1


def parse_site():
    r = requests.get(URL, headers=HEADERS, timeout=15)
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


class SNIPER_V36_TOP_HOTLAG_TERNI:

    def __init__(self):
        self.version = "v36_ora_top_hotlag_terni"

        self.day = day_key()
        self.max_e = 0
        self.last_fp = None
        self.last_draws = []

        self.processed_ids = []
        self.processed_fps = []

        self.active = False
        self.colpi = 0
        self.cooldown = 0
        self.active_snapshot = None

        self.total_play = 0
        self.total_hit = 0
        self.total_stop = 0

        self.hit_colpo_1 = 0
        self.hit_colpo_2 = 0
        self.hit_colpo_3 = 0
        self.hit_colpo_4 = 0
        self.hit_colpo_5 = 0
        self.hit_colpo_6 = 0

        self.recent_results = []
        self.play_log = []

        self.load_state()

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

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
            "active": self.active,
            "colpi": self.colpi,
            "cooldown": self.cooldown,
            "active_snapshot": self.active_snapshot,
            "total_play": self.total_play,
            "total_hit": self.total_hit,
            "total_stop": self.total_stop,
            "hit_colpo_1": self.hit_colpo_1,
            "hit_colpo_2": self.hit_colpo_2,
            "hit_colpo_3": self.hit_colpo_3,
            "hit_colpo_4": self.hit_colpo_4,
            "hit_colpo_5": self.hit_colpo_5,
            "hit_colpo_6": self.hit_colpo_6,
            "recent_results": self.recent_results[-50:],
            "play_log": self.play_log[-800:]
        }

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.git_commit_state()

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

            self.active = bool(data.get("active", False))
            self.colpi = int(data.get("colpi", 0))
            self.cooldown = int(data.get("cooldown", 0))
            self.active_snapshot = data.get("active_snapshot")

            self.total_play = int(data.get("total_play", 0))
            self.total_hit = int(data.get("total_hit", 0))
            self.total_stop = int(data.get("total_stop", 0))

            self.hit_colpo_1 = int(data.get("hit_colpo_1", 0))
            self.hit_colpo_2 = int(data.get("hit_colpo_2", 0))
            self.hit_colpo_3 = int(data.get("hit_colpo_3", 0))
            self.hit_colpo_4 = int(data.get("hit_colpo_4", 0))
            self.hit_colpo_5 = int(data.get("hit_colpo_5", 0))
            self.hit_colpo_6 = int(data.get("hit_colpo_6", 0))

            self.recent_results = data.get("recent_results", [])[-50:]
            self.play_log = data.get("play_log", [])[-800:]

        except Exception:
            pass

    def git_commit_state(self):
        if os.getenv("GITHUB_ACTIONS") != "true":
            return

        try:
            subprocess.run(["git", "config", "user.name", "github-actions"], check=False)
            subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=False)
            subprocess.run(["git", "pull", "--rebase"], check=False)
            subprocess.run(["git", "add", STATE_FILE], check=False)

            diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
            if diff.returncode == 0:
                return

            subprocess.run(["git", "commit", "-m", "update sniper v36 terni state"], check=False)
            subprocess.run(["git", "push"], check=False)

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

    # ===================== HOT-LAG ============================

    def heat(self, n):
        weights = [5, 4, 3, 2, 1]
        return sum(
            w for i, w in enumerate(weights)
            if i < len(self.last_draws) and n in self.last_draws[-(i + 1)]
        )

    def lag(self, n):
        lag = 0
        for d in reversed(self.last_draws[:-1]):
            lag += 1
            if n in d:
                return lag
        return lag

    def dominance(self, n, window=6):
        return sum(1 for d in self.last_draws[-window:] if n in d)

    def is_hotlag(self, n):
        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance(n, 6)

        ok = (
            h >= MIN_HEAT and
            MIN_LAG <= l <= MAX_LAG and
            MIN_DOMINANCE <= d <= MAX_DOMINANCE
        )

        return ok, {
            "number": n,
            "heat": h,
            "lag": l,
            "dominance": d
        }

    # ===================== STRATEGIA ==========================

    def is_block_end(self, e):
        return e % BLOCK_SIZE == 0

    def calculate_strategy(self, e):
        if len(self.last_draws) < BLOCK_SIZE:
            return None

        block = self.last_draws[-BLOCK_SIZE:]

        counter = Counter()
        for draw in block:
            counter.update(draw)

        top10 = sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:TOP_N]

        selected = []
        for pos in PLAY_POSITIONS:
            idx = pos - 1
            if idx < len(top10):
                num, freq = top10[idx]
                selected.append({
                    "position": pos,
                    "number": num,
                    "frequency": freq
                })

        numbers = [x["number"] for x in selected]

        if len(numbers) < 3:
            return None

        hot_details = []
        hot_numbers = []

        for n in numbers:
            ok, detail = self.is_hotlag(n)
            if ok:
                hot_numbers.append(n)
            hot_details.append(detail)

        terni_all = list(combinations(numbers, 3))

        terni = []
        for t in terni_all:
            hot_count = sum(1 for n in t if n in hot_numbers)
            if hot_count >= MIN_HOT_IN_TERNO:
                terni.append(t)

        if not terni:
            return None

        return {
            "reason": "ORA_TOP_FREQUENTI_PLUS_HOTLAG_TERNI",
            "block_end": e,
            "next_block_from": e + 1,
            "next_block_to": e + BLOCK_SIZE,
            "top10": [
                {
                    "position": i + 1,
                    "number": num,
                    "frequency": freq
                }
                for i, (num, freq) in enumerate(top10)
            ],
            "selected": selected,
            "numbers": numbers,
            "hot_numbers": hot_numbers,
            "hot_details": hot_details,
            "terni": terni
        }

    def check_terno_hit(self, nums):
        if not self.active_snapshot:
            return []

        s = set(nums)
        hits = []

        for t in self.active_snapshot["terni"]:
            if all(n in s for n in t):
                hits.append(t)

        return hits

    # ===================== STATS ==============================

    def hitrate(self):
        if self.total_play == 0:
            return 0.0
        return round((self.total_hit / self.total_play) * 100, 2)

    def consecutive_stops(self):
        c = 0
        for r in reversed(self.recent_results):
            if r == "STOP":
                c += 1
            else:
                break
        return c

    def register_play(self, snapshot):
        self.total_play += 1
        self.play_log.append({
            "event": "PLAY_TERNI",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **snapshot
        })
        self.play_log = self.play_log[-800:]

    def register_hit(self, colpo, nums, terni_hit):
        self.total_hit += 1

        if colpo == 1:
            self.hit_colpo_1 += 1
        elif colpo == 2:
            self.hit_colpo_2 += 1
        elif colpo == 3:
            self.hit_colpo_3 += 1
        elif colpo == 4:
            self.hit_colpo_4 += 1
        elif colpo == 5:
            self.hit_colpo_5 += 1
        elif colpo == 6:
            self.hit_colpo_6 += 1

        self.recent_results.append("HIT")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "HIT_TERNO",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "terni_hit": terni_hit,
            "colpo": colpo,
            "draw": nums,
            "snapshot": self.active_snapshot
        })
        self.play_log = self.play_log[-800:]

    def register_stop(self):
        self.total_stop += 1
        self.recent_results.append("STOP")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "STOP_TERNI",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "colpi": MAX_COLPI,
            "snapshot": self.active_snapshot
        })
        self.play_log = self.play_log[-800:]

    # ===================== MAIN ===============================

    async def on_new(self, app, e, nums):
        if len(set(nums)) != 20:
            await self.tg(app, f"⚠️ Parser scarta estrazione {e}")
            return

        if self.already_processed(e, nums):
            return

        self.remember_processed(e, nums)

        self.last_draws.append(nums)
        self.last_draws = self.last_draws[-HISTORY_MAX:]

        await self.tg(app, f"📌 Estrazione {e}\n🎱 {', '.join(map(str, nums))}")

        # ===================== PLAY ATTIVO =====================

        if self.active:
            self.colpi += 1

            terni_hit = self.check_terno_hit(nums)

            if terni_hit:
                self.register_hit(self.colpi, nums, terni_hit)

                terni_txt = ", ".join("-".join(map(str, t)) for t in terni_hit)

                await self.tg(
                    app,
                    f"🔥 HIT TERNO v36 | colpo {self.colpi}\n"
                    f"🎯 Terni usciti = {terni_txt}\n"
                    f"📊 STATS v36\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• hit colpo 1 = {self.hit_colpo_1}\n"
                    f"• hit colpo 2 = {self.hit_colpo_2}\n"
                    f"• hit colpo 3 = {self.hit_colpo_3}\n"
                    f"• hit colpo 4 = {self.hit_colpo_4}\n"
                    f"• hit colpo 5 = {self.hit_colpo_5}\n"
                    f"• hit colpo 6 = {self.hit_colpo_6}\n"
                    f"• stop streak = {self.consecutive_stops()}"
                )

                self.active = False
                self.colpi = 0
                self.active_snapshot = None
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.save_state()
                return

            if self.colpi >= MAX_COLPI:
                self.register_stop()

                await self.tg(
                    app,
                    f"🛑 STOP TERNI v36 | {MAX_COLPI} colpi\n"
                    f"📊 STATS v36\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• stop streak = {self.consecutive_stops()}"
                )

                self.active = False
                self.colpi = 0
                self.active_snapshot = None
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.save_state()
                return

            self.save_state()
            return

        # ===================== COOLDOWN ========================

        if self.cooldown > 0:
            self.cooldown -= 1
            await self.tg(app, f"⏸ cooldown v36 | restano = {self.cooldown}")
            self.save_state()
            return

        # ===================== NUOVO PLAY ======================

        if len(self.last_draws) < MIN_HISTORY:
            self.save_state()
            return

        if not self.is_block_end(e):
            self.save_state()
            return

        data = self.calculate_strategy(e)

        if not data:
            self.save_state()
            return

        self.active = True
        self.colpi = 0
        self.active_snapshot = data

        self.register_play(data)

        selected_txt = ", ".join(
            f"pos{x['position']}={x['number']}({x['frequency']})"
            for x in data["selected"]
        )

        hot_txt = ", ".join(map(str, data["hot_numbers"]))

        terni_txt = ", ".join(
            "-".join(map(str, t)) for t in data["terni"]
        )

        top10_txt = ", ".join(
            f"{x['position']}:{x['number']}({x['frequency']})"
            for x in data["top10"]
        )

        hot_details_txt = ", ".join(
            f"{x['number']}[h{x['heat']}/l{x['lag']}/d{x['dominance']}]"
            for x in data["hot_details"]
        )

        await self.tg(
            app,
            "🎯 PLAY TERNI v36 TOP+HOTLAG\n"
            f"• blocco analizzato = fino estrazione {data['block_end']}\n"
            f"• valido da estrazione = {data['next_block_from']}\n"
            f"• valido fino circa = {data['next_block_to']}\n"
            f"• posizioni usate = 1,2,3,6\n"
            f"• numeri scelti = {selected_txt}\n"
            f"• numeri HOT-LAG = {hot_txt}\n"
            f"• dettagli HOT = {hot_details_txt}\n"
            f"• terni = {terni_txt}\n"
            f"• max_colpi = {MAX_COLPI}\n"
            f"• top10 ora = {top10_txt}\n"
            f"\n📊 STATS v36\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%"
        )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v36 TOP+HOTLAG TERNI\n"
            f"• blocco = {BLOCK_SIZE} estrazioni\n"
            f"• posizioni = {PLAY_POSITIONS}\n"
            f"• min hot nel terno = {MIN_HOT_IN_TERNO}\n"
            f"• max_colpi = {MAX_COLPI}\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%\n"
            f"• hit colpo 1 = {self.hit_colpo_1}\n"
            f"• hit colpo 2 = {self.hit_colpo_2}\n"
            f"• hit colpo 3 = {self.hit_colpo_3}\n"
            f"• hit colpo 4 = {self.hit_colpo_4}\n"
            f"• hit colpo 5 = {self.hit_colpo_5}\n"
            f"• hit colpo 6 = {self.hit_colpo_6}\n"
            f"• stop streak = {self.consecutive_stops()}"
        )


# ===================== LOOP ================================

bot = SNIPER_V36_TOP_HOTLAG_TERNI()


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

        await bot.tg(
            app,
            "🚀 SNIPER v36 TOP+HOTLAG TERNI AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• attendo prossima estrazione reale"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v36 TOP+HOTLAG TERNI RIAVVIATO\n"
            f"• max_e state = {bot.max_e}\n"
            f"• active = {bot.active}\n"
            f"• cooldown = {bot.cooldown}"
        )

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore loop v36: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
