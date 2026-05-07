# ============================================================
# 🚀 SNIPER v31.1 — AMBATA LAB STRICT
# meno play + filtro forte + solo ambata + 2 colpi
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib
import subprocess
from datetime import datetime
from collections import defaultdict
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STATE_FILE = "sniper_ambata_lab_strict_state.json"

LOOP_SEC = 60
HISTORY_MAX = 180
PROCESSED_MAX = 700

MAX_COLPI = 2
COOLDOWN_AFTER_PLAY = 1

MIN_HISTORY = 12

# ===================== FILTRO STRICT ========================

MIN_HEAT = 10
MIN_LIFE = 17
MIN_LAG = 2
MAX_LAG = 3
MIN_DOMINANCE = 3
MAX_DOMINANCE = 4
MIN_PRESSURE = 9

RECENT_HIT_BLOCK = 4


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


class SNIPER_AMBATA_STRICT:

    def __init__(self):
        self.version = "v31.1_ambata_lab_strict"

        self.day = day_key()
        self.max_e = 0
        self.last_fp = None
        self.last_draws = []

        self.processed_ids = []
        self.processed_fps = []

        self.active = False
        self.active_n = None
        self.active_snapshot = None
        self.colpi = 0
        self.cooldown = 0

        self.recent_results = []
        self.recent_hit_numbers = []

        self.play_log = []
        self.total_play = 0
        self.total_hit = 0
        self.total_stop = 0
        self.hit_colpo_1 = 0
        self.hit_colpo_2 = 0

        self.number_stats = defaultdict(lambda: {
            "play": 0,
            "hit": 0,
            "stop": 0,
            "hit1": 0,
            "hit2": 0
        })

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
            "active_n": self.active_n,
            "active_snapshot": self.active_snapshot,
            "colpi": self.colpi,
            "cooldown": self.cooldown,

            "recent_results": self.recent_results[-50:],
            "recent_hit_numbers": self.recent_hit_numbers[-50:],

            "play_log": self.play_log[-800:],

            "total_play": self.total_play,
            "total_hit": self.total_hit,
            "total_stop": self.total_stop,
            "hit_colpo_1": self.hit_colpo_1,
            "hit_colpo_2": self.hit_colpo_2,

            "number_stats": dict(self.number_stats)
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
            self.active_n = data.get("active_n")
            if self.active_n is not None:
                self.active_n = int(self.active_n)

            self.active_snapshot = data.get("active_snapshot")
            self.colpi = int(data.get("colpi", 0))
            self.cooldown = int(data.get("cooldown", 0))

            self.recent_results = data.get("recent_results", [])[-50:]
            self.recent_hit_numbers = data.get("recent_hit_numbers", [])[-50:]

            self.play_log = data.get("play_log", [])[-800:]

            self.total_play = int(data.get("total_play", 0))
            self.total_hit = int(data.get("total_hit", 0))
            self.total_stop = int(data.get("total_stop", 0))
            self.hit_colpo_1 = int(data.get("hit_colpo_1", 0))
            self.hit_colpo_2 = int(data.get("hit_colpo_2", 0))

            raw_stats = data.get("number_stats", {})
            for k, v in raw_stats.items():
                self.number_stats[int(k)] = {
                    "play": int(v.get("play", 0)),
                    "hit": int(v.get("hit", 0)),
                    "stop": int(v.get("stop", 0)),
                    "hit1": int(v.get("hit1", 0)),
                    "hit2": int(v.get("hit2", 0))
                }

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

            subprocess.run(["git", "commit", "-m", "update ambata strict state"], check=False)
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

    def number_pressure(self, n):
        weights = [5, 4, 3, 2, 1]
        score = 0

        for i, w in enumerate(weights):
            if i >= len(self.last_draws):
                break

            if n in self.last_draws[-(i + 1)]:
                score += w

        return score

    # ===================== AMBATA STRICT ======================

    def should_play_ambata(self, n):
        life = self.life(n)
        heat = self.heat(n)
        lag = self.lag(n)
        dom = self.dominance(n, 6)
        pressure = self.number_pressure(n)

        if n in self.recent_hit_numbers[-RECENT_HIT_BLOCK:]:
            return False, "RECENT_HIT_BLOCK"

        if lag < MIN_LAG:
            return False, "TOO_RECENT"

        if lag > MAX_LAG:
            return False, "LAG_TOO_LATE"

        if heat < MIN_HEAT:
            return False, "LOW_HEAT"

        if heat == 9:
            return False, "HEAT9_TRAP"

        if dom < MIN_DOMINANCE:
            return False, "LOW_DOMINANCE"

        if dom > MAX_DOMINANCE:
            return False, "OVER_DOMINANT"

        if life < MIN_LIFE:
            return False, "LOW_LIFE"

        if pressure < MIN_PRESSURE:
            return False, "LOW_PRESSURE"

        return True, "AMBATA_STRICT_ZONE"

    def choose_ambata_candidate(self):
        ranked = []

        for n in range(1, 91):
            ok, reason = self.should_play_ambata(n)
            if not ok:
                continue

            life = self.life(n)
            heat = self.heat(n)
            lag = self.lag(n)
            dom = self.dominance(n, 6)
            pressure = self.number_pressure(n)

            score = (
                life * 1.15
                + heat * 0.90
                + dom * 2.00
                + pressure * 0.60
                - lag * 0.90
            )

            # bonus zona migliore vista dai log
            if lag == 3:
                score += 1.8

            if dom == 4:
                score += 2.2

            if heat >= 10:
                score += 1.5

            ranked.append({
                "n": n,
                "score": round(score, 2),
                "reason": reason,
                "life": life,
                "heat": heat,
                "lag": lag,
                "dominance": dom,
                "pressure": pressure
            })

        ranked.sort(key=lambda x: x["score"], reverse=True)

        if not ranked:
            return None, []

        return ranked[0], ranked[:10]

    # ===================== STATS ==============================

    def hitrate(self):
        if self.total_play == 0:
            return 0.0
        return round((self.total_hit / self.total_play) * 100, 2)

    def top_numbers_report(self, limit=10):
        rows = []

        for n, st in self.number_stats.items():
            play = st["play"]
            hit = st["hit"]

            if play <= 0:
                continue

            rows.append((
                n,
                play,
                hit,
                st["stop"],
                round((hit / play) * 100, 2),
                st["hit1"],
                st["hit2"]
            ))

        rows.sort(key=lambda x: (x[4], x[2], -x[1]), reverse=True)
        return rows[:limit]

    def register_play(self, candidate):
        n = candidate["n"]

        self.total_play += 1
        self.number_stats[n]["play"] += 1

        self.play_log.append({
            "event": "PLAY",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **candidate
        })

        self.play_log = self.play_log[-800:]

    def register_hit(self, n, colpo, nums):
        self.total_hit += 1
        self.number_stats[n]["hit"] += 1

        if colpo == 1:
            self.hit_colpo_1 += 1
            self.number_stats[n]["hit1"] += 1

        if colpo == 2:
            self.hit_colpo_2 += 1
            self.number_stats[n]["hit2"] += 1

        self.recent_results.append("HIT")
        self.recent_results = self.recent_results[-50:]

        self.recent_hit_numbers.append(n)
        self.recent_hit_numbers = self.recent_hit_numbers[-50:]

        self.play_log.append({
            "event": "HIT",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "n": n,
            "colpo": colpo,
            "draw": nums,
            "snapshot": self.active_snapshot
        })

        self.play_log = self.play_log[-800:]

    def register_stop(self, n):
        self.total_stop += 1
        self.number_stats[n]["stop"] += 1

        self.recent_results.append("STOP")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "STOP",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "n": n,
            "colpi": MAX_COLPI,
            "snapshot": self.active_snapshot
        })

        self.play_log = self.play_log[-800:]

    # ===================== MAIN ==============================

    async def on_new(self, app, e, nums):
        if len(set(nums)) != 20:
            await self.tg(app, f"⚠️ Parser scarta estrazione {e}")
            return

        if self.already_processed(e, nums):
            return

        self.remember_processed(e, nums)

        self.last_draws.append(nums)
        self.last_draws = self.last_draws[-HISTORY_MAX:]

        s = set(nums)

        await self.tg(app, f"📌 Estrazione {e}\n🎱 {', '.join(map(str, nums))}")

        # ===================== PLAY ATTIVO =====================

        if self.active:
            self.colpi += 1

            n = self.active_n
            hit = n in s

            if hit:
                self.register_hit(n, self.colpi, nums)

                await self.tg(
                    app,
                    f"🔥 HIT AMBATA {n} | colpo {self.colpi}\n"
                    f"📊 STATS STRICT\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• hit colpo 1 = {self.hit_colpo_1}\n"
                    f"• hit colpo 2 = {self.hit_colpo_2}"
                )

                self.active = False
                self.active_n = None
                self.active_snapshot = None
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.save_state()
                return

            if self.colpi >= MAX_COLPI:
                self.register_stop(n)

                await self.tg(
                    app,
                    f"🛑 STOP AMBATA {n} | {MAX_COLPI} colpi\n"
                    f"📊 STATS STRICT\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%"
                )

                self.active = False
                self.active_n = None
                self.active_snapshot = None
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.save_state()
                return

            self.save_state()
            return

        # ===================== COOLDOWN =======================

        if self.cooldown > 0:
            self.cooldown -= 1
            await self.tg(app, "⏸ cooldown")
            self.save_state()
            return

        # ===================== NUOVO PLAY =====================

        if len(self.last_draws) < MIN_HISTORY:
            self.save_state()
            return

        candidate, ranking = self.choose_ambata_candidate()

        if not candidate:
            await self.tg(
                app,
                "⏸ NO PLAY STRICT\n"
                "• nessun numero in AMBATA_STRICT_ZONE"
            )
            self.save_state()
            return

        n = candidate["n"]

        self.active = True
        self.active_n = n
        self.active_snapshot = candidate
        self.colpi = 0

        self.register_play(candidate)

        await self.tg(
            app,
            "🎯 PLAY AMBATA STRICT v31.1\n"
            f"• AMBATA = {n}\n"
            f"• max_colpi = {MAX_COLPI}\n"
            f"• motivo = {candidate['reason']}\n"
            f"• score = {candidate['score']}\n"
            f"• life = {candidate['life']}\n"
            f"• heat = {candidate['heat']}\n"
            f"• lag = {candidate['lag']}\n"
            f"• dominance = {candidate['dominance']}\n"
            f"• pressure = {candidate['pressure']}\n"
            f"• candidati top = {ranking}\n"
            f"\n📊 STATS STRICT\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%"
        )

        self.save_state()

    async def send_report(self, app):
        top = self.top_numbers_report(10)

        await self.tg(
            app,
            "📊 REPORT AMBATA STRICT v31.1\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%\n"
            f"• hit colpo 1 = {self.hit_colpo_1}\n"
            f"• hit colpo 2 = {self.hit_colpo_2}\n"
            f"• top numeri = {top}"
        )


# ===================== LOOP ================================

bot = SNIPER_AMBATA_STRICT()


async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    if not bot.last_draws:
        for e, nums in es[:-1]:
            bot.last_draws.append(nums)

        bot.last_draws = bot.last_draws[-HISTORY_MAX:]

        if len(es) >= 2:
            bot.max_e = es[-2][0]

        bot.save_state()

    await bot.tg(app, "🚀 SNIPER v31.1 AMBATA LAB STRICT AVVIATO")

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore loop: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
