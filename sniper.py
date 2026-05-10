# ============================================================
# 🚀 SNIPER v35 — ORA TOP FREQUENTI AMBI
# Blocchi da 12 estrazioni:
# - calcola top 10 frequenti dell'ora appena chiusa
# - prende posizioni 1,2,3,6
# - gioca tutti gli ambi tra questi numeri nell'ora successiva
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

STATE_FILE = "sniper_v35_ora_top_frequenti_ambi_state.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

BLOCK_SIZE = 12
TOP_N = 10
PLAY_POSITIONS = [1, 2, 3, 6]

MAX_COLPI = 6
COOLDOWN_AFTER_PLAY = 0
MIN_HISTORY = 12


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


class SNIPER_ORA_TOP_FREQUENTI_AMBI:

    def __init__(self):
        self.version = "v35_ora_top_frequenti_ambi"

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

            subprocess.run(["git", "commit", "-m", "update sniper v35 ora top frequenti state"], check=False)
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

    # ===================== STRATEGIA ORARIA ===================

    def is_block_end(self, e):
        return e % BLOCK_SIZE == 0

    def calculate_hour_strategy(self, e):
        if len(self.last_draws) < BLOCK_SIZE:
            return None

        block = self.last_draws[-BLOCK_SIZE:]

        counter = Counter()
        for draw in block:
            counter.update(draw)

        top10 = sorted(
            counter.items(),
            key=lambda x: (-x[1], x[0])
        )[:TOP_N]

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

        if len(numbers) < 2:
            return None

        ambi = list(combinations(numbers, 2))

        return {
            "reason": "ORA_TOP_FREQUENTI_POS_1_2_3_6",
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
            "ambi": ambi
        }

    def check_ambo_hit(self, nums):
        if not self.active_snapshot:
            return []

        s = set(nums)
        hits = []

        for a, b in self.active_snapshot["ambi"]:
            if a in s and b in s:
                hits.append((a, b))

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
            "event": "PLAY",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **snapshot
        })

        self.play_log = self.play_log[-800:]

    def register_hit(self, colpo, nums, ambi_hit):
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
            "event": "HIT_AMBO",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ambi_hit": ambi_hit,
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
            "event": "STOP",
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

            ambi_hit = self.check_ambo_hit(nums)

            if ambi_hit:
                self.register_hit(self.colpi, nums, ambi_hit)

                ambi_txt = ", ".join(f"{a}-{b}" for a, b in ambi_hit)

                await self.tg(
                    app,
                    f"🔥 HIT AMBO v35 | colpo {self.colpi}\n"
                    f"🎯 Ambi usciti = {ambi_txt}\n"
                    f"📊 STATS v35\n"
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
                    f"🛑 STOP AMBO v35 | {MAX_COLPI} colpi\n"
                    f"📊 STATS v35\n"
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
            await self.tg(app, f"⏸ cooldown v35 | restano = {self.cooldown}")
            self.save_state()
            return

        # ===================== NUOVO PLAY ORARIO ===============

        if len(self.last_draws) < MIN_HISTORY:
            self.save_state()
            return

        if not self.is_block_end(e):
            self.save_state()
            return

        data = self.calculate_hour_strategy(e)

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

        ambi_txt = ", ".join(f"{a}-{b}" for a, b in data["ambi"])

        top10_txt = ", ".join(
            f"{x['position']}:{x['number']}({x['frequency']})"
            for x in data["top10"]
        )

        await self.tg(
            app,
            "🎯 PLAY AMBI v35 ORA TOP FREQUENTI\n"
            f"• blocco analizzato = fino estrazione {data['block_end']}\n"
            f"• valido da estrazione = {data['next_block_from']}\n"
            f"• valido fino circa = {data['next_block_to']}\n"
            f"• posizioni usate = 1,2,3,6\n"
            f"• numeri scelti = {selected_txt}\n"
            f"• ambi = {ambi_txt}\n"
            f"• max_colpi = {MAX_COLPI}\n"
            f"• top10 ora = {top10_txt}\n"
            f"\n📊 STATS v35\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%"
        )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v35 ORA TOP FREQUENTI AMBI\n"
            f"• blocco = {BLOCK_SIZE} estrazioni\n"
            f"• posizioni giocate = {PLAY_POSITIONS}\n"
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

bot = SNIPER_ORA_TOP_FREQUENTI_AMBI()


async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    # LIVE_ONLY: carica storico già uscito oggi, ma non gioca il passato
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
            "🚀 SNIPER v35 ORA TOP FREQUENTI AMBI AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• attendo prossima estrazione reale"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v35 ORA TOP FREQUENTI AMBI RIAVVIATO\n"
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
            await bot.tg(app, f"⚠️ Errore loop v35: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
