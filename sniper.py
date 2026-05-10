# ============================================================
# 🚀 SNIPER v34 — MULTI HOT-LAG AMBI
# Motore multi-numero con abbinamenti migliori testati
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib
import subprocess
from datetime import datetime
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STATE_FILE = "sniper_v34_multi_hotlag_ambi_state.json"

LOOP_SEC = 60
HISTORY_MAX = 180
PROCESSED_MAX = 800

MAX_COLPI = 5
COOLDOWN_AFTER_PLAY = 1
MIN_HISTORY = 12



MIN_HEAT = 10
MIN_LAG = 1
MAX_LAG = 3
MIN_DOMINANCE = 3
MAX_DOMINANCE = 6

STRATEGIE = {
    6: [5, 10, 30],
    11: [10, 5, 25],
    16: [15, 20, 5],
    21: [20, 15, 25],
    18: [5, 15, 20],
    15: [14, 5, 20],
    20: [21, 15, 10],
    10: [11, 5, 6],
    5: [6, 10, 15],
    19: [20, 15, 18],
    23: [20, 25, 21],
    4: [5, 6, 10],
}


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


class SNIPER_MULTI_HOTLAG_AMBI:

    def __init__(self):
        self.version = "v34_multi_hotlag_ambi"

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

            subprocess.run(["git", "commit", "-m", "update sniper v34 multi hotlag ambi state"], check=False)
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

    # ===================== FEATURES ==========================

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

    def life(self, n):
        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance(n, 6)

        score = h * 1.8 - l * 0.6

        if d >= 2:
            score += 1.2
        if d >= 3:
            score += 1.6

        return round(score, 2)

    def pressure(self, n):
        weights = [5, 4, 3, 2, 1]
        score = 0

        for i, w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            if n in self.last_draws[-(i + 1)]:
                score += w

        return score

    # ===================== ENGINE =============================

    def should_play(self):
        candidates = []

        for base, partners in STRATEGIE.items():
            h = self.heat(base)
            l = self.lag(base)
            d = self.dominance(base, 6)
            life = self.life(base)
            pressure = self.pressure(base)

            if l < MIN_LAG:
                continue

            if l > MAX_LAG:
                continue

            if h < MIN_HEAT:
                continue

            if d < MIN_DOMINANCE:
                continue

            if d > MAX_DOMINANCE:
                continue

            score = (h * 2) + (d * 3) + pressure - l

            ambi = [(base, x) for x in partners]

            candidates.append({
                "reason": "MULTI_HOT_LAG_AMBI",
                "base": base,
                "partners": partners,
                "ambi": ambi,
                "heat": h,
                "lag": l,
                "dominance": d,
                "life": life,
                "pressure": pressure,
                "score": score
            })

        if not candidates:
            return False, None

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return True, candidates[0]

    def check_ambo_hit(self, nums):
        if not self.active_snapshot:
            return []

        s = set(nums)
        base = self.active_snapshot["base"]
        partners = self.active_snapshot["partners"]

        if base not in s:
            return []

        hits = []

        for p in partners:
            if p in s:
                hits.append((base, p))

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
                    f"🔥 HIT AMBO v34 | colpo {self.colpi}\n"
                    f"🎯 Ambi usciti = {ambi_txt}\n"
                    f"📊 STATS v34\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• hit colpo 1 = {self.hit_colpo_1}\n"
                    f"• hit colpo 2 = {self.hit_colpo_2}\n"
                    f"• hit colpo 3 = {self.hit_colpo_3}\n"
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
                    f"🛑 STOP AMBO v34 | {MAX_COLPI} colpi\n"
                    f"📊 STATS v34\n"
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
            await self.tg(app, f"⏸ cooldown v34 | restano = {self.cooldown}")
            self.save_state()
            return

        # ===================== NUOVO PLAY ======================

        if len(self.last_draws) < MIN_HISTORY:
            self.save_state()
            return

        ok, data = self.should_play()

        if not ok:
            self.save_state()
            return

        self.active = True
        self.colpi = 0
        self.active_snapshot = data

        self.register_play(data)

        ambi_txt = ", ".join(f"{a}-{b}" for a, b in data["ambi"])

        await self.tg(
            app,
            "🎯 PLAY AMBI v34 MULTI HOT-LAG\n"
            f"• base = {data['base']}\n"
            f"• ambi = {ambi_txt}\n"
            f"• max_colpi = {MAX_COLPI}\n"
            f"• motivo = {data['reason']}\n"
            f"• heat = {data['heat']}\n"
            f"• lag = {data['lag']}\n"
            f"• dominance = {data['dominance']}\n"
            f"• life = {data['life']}\n"
            f"• pressure = {data['pressure']}\n"
            f"• score = {data['score']}\n"
            f"\n📊 STATS v34\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%"
        )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v34 MULTI HOT-LAG AMBI\n"
            f"• strategie = {STRATEGIE}\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%\n"
            f"• hit colpo 1 = {self.hit_colpo_1}\n"
            f"• hit colpo 2 = {self.hit_colpo_2}\n"
            f"• hit colpo 3 = {self.hit_colpo_3}\n"
            f"• stop streak = {self.consecutive_stops()}"
        )


# ===================== LOOP ================================

bot = SNIPER_MULTI_HOTLAG_AMBI()


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
            "🚀 SNIPER v34 MULTI HOT-LAG AMBI AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• attendo prossima estrazione reale"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v34 MULTI HOT-LAG AMBI RIAVVIATO\n"
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
            await bot.tg(app, f"⚠️ Errore loop v34: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
