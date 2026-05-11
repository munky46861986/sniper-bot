# ============================================================
# 🚀 SNIPER v40 — CORE4 TOP FREQUENTI + HOT-LAG
# Ogni 12 estrazioni:
# - calcola top 10 frequenti
# - ordina con score HOT-LAG
# - prende SOLO i migliori 4 numeri
# - controlla 2/4, 3/4, 4/4
# - chiude HIT quando prende almeno 3/4
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
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STATE_FILE = "sniper_v40_core4_top_hotlag_state.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

BLOCK_SIZE = 12
TOP_N = 10
CORE_SIZE = 4
MAX_COLPI = 6

MIN_CLOSE_HIT = 3


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


class SNIPER_V40_CORE4:

    def __init__(self):
        self.version = "v40_core4_top_hotlag"

        self.day = day_key()
        self.max_e = 0
        self.last_fp = None
        self.last_draws = []

        self.processed_ids = []
        self.processed_fps = []

        self.active = False
        self.colpi = 0
        self.active_snapshot = None
        self.last_signal_block = None

        self.total_play = 0
        self.total_hit = 0
        self.total_stop = 0

        self.hit_2su4 = 0
        self.hit_3su4 = 0
        self.hit_4su4 = 0

        self.play_log = []
        self.recent_results = []

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
            "active_snapshot": self.active_snapshot,
            "last_signal_block": self.last_signal_block,
            "total_play": self.total_play,
            "total_hit": self.total_hit,
            "total_stop": self.total_stop,
            "hit_2su4": self.hit_2su4,
            "hit_3su4": self.hit_3su4,
            "hit_4su4": self.hit_4su4,
            "play_log": self.play_log[-800:],
            "recent_results": self.recent_results[-50:]
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

            if data.get("day", day_key()) != day_key():
                self.day = day_key()
                return

            self.day = data.get("day", day_key())
            self.max_e = int(data.get("max_e", 0))
            self.last_fp = data.get("last_fp")
            self.last_draws = data.get("last_draws", [])[-HISTORY_MAX:]
            self.processed_ids = data.get("processed_ids", [])[-PROCESSED_MAX:]
            self.processed_fps = data.get("processed_fps", [])[-PROCESSED_MAX:]

            self.active = bool(data.get("active", False))
            self.colpi = int(data.get("colpi", 0))
            self.active_snapshot = data.get("active_snapshot")
            self.last_signal_block = data.get("last_signal_block")

            self.total_play = int(data.get("total_play", 0))
            self.total_hit = int(data.get("total_hit", 0))
            self.total_stop = int(data.get("total_stop", 0))

            self.hit_2su4 = int(data.get("hit_2su4", 0))
            self.hit_3su4 = int(data.get("hit_3su4", 0))
            self.hit_4su4 = int(data.get("hit_4su4", 0))

            self.play_log = data.get("play_log", [])[-800:]
            self.recent_results = data.get("recent_results", [])[-50:]

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

            subprocess.run(["git", "commit", "-m", "update sniper v40 core4 state"], check=False)
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

    def pressure(self, n):
        weights = [5, 4, 3, 2, 1]
        score = 0

        for i, w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            if n in self.last_draws[-(i + 1)]:
                score += w

        return score

    def score_number(self, n, freq):
        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance(n, 6)
        p = self.pressure(n)

        score = (freq * 4) + (h * 2) + (d * 3) + p - l

        return {
            "number": n,
            "freq": freq,
            "heat": h,
            "lag": l,
            "dominance": d,
            "pressure": p,
            "score": score
        }

    # ===================== ENGINE ============================

    def is_block_end(self, e):
        return e % BLOCK_SIZE == 0

    def calculate_play(self, e):
        if len(self.last_draws) < BLOCK_SIZE:
            return None

        if self.last_signal_block == e:
            return None

        block = self.last_draws[-BLOCK_SIZE:]

        counter = Counter()
        for draw in block:
            counter.update(draw)

        top10_raw = sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:TOP_N]

        scored = [self.score_number(n, freq) for n, freq in top10_raw]
        scored.sort(key=lambda x: (-x["score"], -x["freq"], x["number"]))

        core4 = [x["number"] for x in scored[:CORE_SIZE]]
        riga10 = [x["number"] for x in scored]

        return {
            "reason": "CORE4_TOP_FREQUENTI_PLUS_HOTLAG",
            "block_end": e,
            "valid_from": e + 1,
            "valid_to": e + MAX_COLPI,
            "core4": core4,
            "riga10": riga10,
            "scored": scored,
            "top10_raw": [
                {"position": i + 1, "number": n, "freq": freq}
                for i, (n, freq) in enumerate(top10_raw)
            ]
        }

    def check_hits(self, nums):
        s = set(nums)
        core4 = self.active_snapshot["core4"]

        usciti_core = [n for n in core4 if n in s]

        return {
            "usciti_core": usciti_core,
            "count_core": len(usciti_core)
        }

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
            "event": "PLAY_CORE4",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **snapshot
        })
        self.play_log = self.play_log[-800:]

    def register_hit_result(self, colpo, nums, hit_data):
        c = hit_data["count_core"]

        if c < MIN_CLOSE_HIT:
            return False

        self.total_hit += 1

        if c == 3:
            self.hit_3su4 += 1
        elif c >= 4:
            self.hit_4su4 += 1

        self.recent_results.append("HIT")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "HIT_CORE4",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "colpo": colpo,
            "draw": nums,
            "hit_data": hit_data,
            "snapshot": self.active_snapshot
        })
        self.play_log = self.play_log[-800:]

        return True

    def register_soft_2su4(self):
        self.hit_2su4 += 1

    def register_stop(self):
        self.total_stop += 1
        self.recent_results.append("STOP")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "STOP_CORE4",
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

        # ===================== CONTROLLO PLAY ATTIVO ===========

        if self.active:
            self.colpi += 1

            hit_data = self.check_hits(nums)

            core_txt = ", ".join(map(str, hit_data["usciti_core"])) or "nessuno"

            if hit_data["count_core"] == 2:
                self.register_soft_2su4()

            await self.tg(
                app,
                f"🔎 CHECK CORE4 v40 | colpo {self.colpi}/{MAX_COLPI}\n"
                f"• usciti core = {hit_data['count_core']}/4 → {core_txt}"
            )

            if hit_data["count_core"] >= MIN_CLOSE_HIT:
                self.register_hit_result(self.colpi, nums, hit_data)

                await self.tg(
                    app,
                    f"🔥 HIT CORE4 v40 | colpo {self.colpi}\n"
                    f"🎯 Risultato = {hit_data['count_core']}/4\n"
                    f"✅ Numeri usciti = {core_txt}\n\n"
                    f"📊 STATS v40\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit 3/4+ = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• 2/4 osservati = {self.hit_2su4}\n"
                    f"• 3/4 = {self.hit_3su4}\n"
                    f"• 4/4 = {self.hit_4su4}"
                )

                self.active = False
                self.colpi = 0
                self.active_snapshot = None
                self.save_state()
                return

            if self.colpi >= MAX_COLPI:
                self.register_stop()

                await self.tg(
                    app,
                    f"🛑 STOP CORE4 v40 | {MAX_COLPI} colpi\n"
                    f"📊 STATS v40\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit 3/4+ = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• stop streak = {self.consecutive_stops()}"
                )

                self.active = False
                self.colpi = 0
                self.active_snapshot = None
                self.save_state()
                return

            self.save_state()
            return

        # ===================== NUOVO PLAY ======================

        if len(self.last_draws) < BLOCK_SIZE:
            self.save_state()
            return

        if not self.is_block_end(e):
            self.save_state()
            return

        data = self.calculate_play(e)

        if not data:
            self.save_state()
            return

        self.active = True
        self.colpi = 0
        self.active_snapshot = data
        self.last_signal_block = e

        self.register_play(data)

        core_txt = ", ".join(map(str, data["core4"]))
        riga_txt = ", ".join(map(str, data["riga10"]))

        scored_txt = "\n".join(
            f"{i+1}) {x['number']} | score={x['score']} | "
            f"freq={x['freq']} heat={x['heat']} lag={x['lag']} "
            f"dom={x['dominance']} pressure={x['pressure']}"
            for i, x in enumerate(data["scored"])
        )

        top10_txt = ", ".join(
            f"{x['position']}:{x['number']}({x['freq']})"
            for x in data["top10_raw"]
        )

        await self.tg(
            app,
            "🎯 PLAY CORE4 v40 TOP+HOTLAG\n"
            f"• blocco analizzato = fino estrazione {data['block_end']}\n"
            f"• valido da = {data['valid_from']}\n"
            f"• max_colpi = {MAX_COLPI}\n\n"
            f"💎 GIOCA CORE 4:\n{core_txt}\n\n"
            f"👀 RIGA 10 osservazione:\n{riga_txt}\n\n"
            f"📌 Top10 grezzi:\n{top10_txt}\n\n"
            f"📊 Ranking:\n{scored_txt}"
        )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v40 CORE4\n"
            f"• play totali = {self.total_play}\n"
            f"• hit 3/4+ = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%\n"
            f"• 2/4 osservati = {self.hit_2su4}\n"
            f"• 3/4 = {self.hit_3su4}\n"
            f"• 4/4 = {self.hit_4su4}\n"
            f"• stop streak = {self.consecutive_stops()}"
        )


# ===================== LOOP ================================

bot = SNIPER_V40_CORE4()


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
            "🚀 SNIPER v40 CORE4 AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• attendo prossima estrazione reale"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v40 CORE4 RIAVVIATO\n"
            f"• max_e state = {bot.max_e}\n"
            f"• active = {bot.active}\n"
            f"• ultimo blocco = {bot.last_signal_block}"
        )

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore loop v40: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
