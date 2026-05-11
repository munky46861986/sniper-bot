# ============================================================
# 🚀 SNIPER v37 — RIGA 10 TOP FREQUENTI + HOT-LAG
# Ogni 12 estrazioni:
# - calcola top 10 frequenti dell'ora appena chiusa
# - calcola score HOT-LAG
# - manda su Telegram la riga da 10 numeri già ordinata
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

STATE_FILE = "sniper_v37_riga10_top_hotlag_state.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

BLOCK_SIZE = 12
TOP_N = 10
CORE_SIZE = 4


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


class SNIPER_RIGA10_TOP_HOTLAG:

    def __init__(self):
        self.version = "v37_riga10_top_hotlag"

        self.day = day_key()
        self.max_e = 0
        self.last_fp = None
        self.last_draws = []

        self.processed_ids = []
        self.processed_fps = []

        self.last_signal_block = None
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
            "last_signal_block": self.last_signal_block,
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
            self.last_signal_block = data.get("last_signal_block")
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

            subprocess.run(["git", "commit", "-m", "update sniper v37 riga10 state"], check=False)
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

    # ===================== RIGA 10 ENGINE =====================

    def is_block_end(self, e):
        return e % BLOCK_SIZE == 0

    def calculate_riga10(self, e):
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

        riga10 = [x["number"] for x in scored]
        core = riga10[:CORE_SIZE]
        support = riga10[CORE_SIZE:]

        return {
            "reason": "RIGA10_TOP_FREQUENTI_PLUS_HOTLAG",
            "block_end": e,
            "valid_from": e + 1,
            "valid_to": e + BLOCK_SIZE,
            "top10_raw": [
                {
                    "position": i + 1,
                    "number": n,
                    "freq": freq
                }
                for i, (n, freq) in enumerate(top10_raw)
            ],
            "scored": scored,
            "core": core,
            "support": support,
            "riga10": riga10
        }

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

        if len(self.last_draws) < BLOCK_SIZE:
            self.save_state()
            return

        if not self.is_block_end(e):
            self.save_state()
            return

        data = self.calculate_riga10(e)

        if not data:
            self.save_state()
            return

        self.last_signal_block = e

        self.play_log.append({
            "event": "RIGA10",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **data
        })
        self.play_log = self.play_log[-800:]

        core_txt = ", ".join(map(str, data["core"]))
        support_txt = ", ".join(map(str, data["support"]))
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
            "🎯 RIGA 10 NUMERI v37 TOP+HOTLAG\n"
            f"• blocco analizzato = fino estrazione {data['block_end']}\n"
            f"• valida da estrazione = {data['valid_from']}\n"
            f"• valida fino circa = {data['valid_to']}\n\n"
            f"🔥 CORE 4:\n{core_txt}\n\n"
            f"➕ SUPPORT 6:\n{support_txt}\n\n"
            f"🎱 RIGA COMPLETA:\n{riga_txt}\n\n"
            f"📌 Top10 frequenti grezzi:\n{top10_txt}\n\n"
            f"📊 Ranking score:\n{scored_txt}"
        )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v37 RIGA10 TOP+HOTLAG\n"
            f"• blocco = {BLOCK_SIZE} estrazioni\n"
            f"• top numeri = {TOP_N}\n"
            f"• core = {CORE_SIZE}\n"
            f"• ultimo blocco segnalato = {self.last_signal_block}"
        )


# ===================== LOOP ================================

bot = SNIPER_RIGA10_TOP_HOTLAG()


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
            "🚀 SNIPER v37 RIGA10 TOP+HOTLAG AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• attendo prossima estrazione reale"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v37 RIGA10 TOP+HOTLAG RIAVVIATO\n"
            f"• max_e state = {bot.max_e}\n"
            f"• ultimo blocco segnalato = {bot.last_signal_block}"
        )

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore loop v37: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
