# ============================================================
# 🚀 SNIPER v28.4 PRO + AI FILTER FIXED (DAY SAFE)
# ============================================================

import asyncio
import requests
import re
import csv
import os
import json
import hashlib
from datetime import datetime
from collections import defaultdict
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

# ===================== CONFIG ===============================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TARGET = [5, 10, 15, 50]

LOOP_SEC = 60
HISTORY_MAX = 160

LOG_DIR = "logs"
STATE_FILE = os.path.join(LOG_DIR, "state.json")

# ===================== UTILS ===============================

def today_key():
    return datetime.now().strftime("%Y-%m-%d")

def fingerprint(e, nums):
    return hashlib.md5(f"{e}-{nums}".encode()).hexdigest()

# ===================== PARSER ===============================

def parse_site():
    r = requests.get(URL, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")

    out = {}

    for t in soup.find_all("table"):
        m = re.search(r"[Nn]\.?\s*(\d+)", t.get_text(" ", strip=True))
        if not m:
            continue

        e = int(m.group(1))
        nums = []

        for td in t.find_all("td"):
            v = td.get_text(strip=True)
            if v.isdigit():
                n = int(v)
                if 1 <= n <= 90:
                    nums.append(n)

        if len(nums) >= 20:
            out[e] = nums[:20]

    return sorted(out.items())

# ============================================================

class SNIPER:

    def __init__(self):
        self.max_e = 0
        self.last_draws = []

        self.day = today_key()

        self.recent_fp = []
        self.last_processed_e = None

        self.cooldown = 0

        os.makedirs(LOG_DIR, exist_ok=True)
        self.load()

    # ===================== STATE ============================

    def load(self):
        if not os.path.exists(STATE_FILE):
            return

        try:
            data = json.load(open(STATE_FILE))

            # RESET AUTOMATICO SE CAMBIA GIORNO
            if data.get("day") != today_key():
                print("🔄 NUOVO GIORNO → RESET")
                return

            self.max_e = data.get("max_e", 0)
            self.last_draws = data.get("last_draws", [])[-HISTORY_MAX:]
            self.recent_fp = data.get("recent_fp", [])
            self.cooldown = data.get("cooldown", 0)

        except:
            pass

    def save(self):
        json.dump({
            "day": today_key(),
            "max_e": self.max_e,
            "last_draws": self.last_draws[-HISTORY_MAX:],
            "recent_fp": self.recent_fp[-50:],
            "cooldown": self.cooldown
        }, open(STATE_FILE, "w"))

    # ===================== TELEGRAM =========================

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

    # ===================== FEATURES =========================

    def heat(self, n):
        weights = [5,4,3,2,1]
        h = 0
        for i,w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            if n in self.last_draws[-(i+1)]:
                h += w
        return h

    def lag(self, n):
        lag = 0
        for d in reversed(self.last_draws[:-1]):
            lag += 1
            if n in d:
                return lag
        return lag

    def pressure(self):
        score = 0
        weights = [5,4,3,2,1]
        for i,w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            c = len([x for x in self.last_draws[-(i+1)] if x in TARGET])
            score += c*w
        return score

    # ===================== LOGIC ============================

    def choose(self):
        p = self.pressure()
        h = self.heat(15)
        l = self.lag(15)

        life15 = h*1.8 - l*0.6

        if life15 < 3:
            return None, "15 morto"

        if p < 9:
            return None, "pressione bassa"

        s50 = self.heat(50) - self.lag(50)*0.5
        s5 = self.heat(5) - self.lag(5)*0.5

        if s50 > s5:
            return (15,50), "15-50"
        else:
            return (15,5), "15-5"

    # ===================== MAIN =============================

    async def on_new(self, app, e, nums):

        fp = fingerprint(e, nums)

        if fp in self.recent_fp:
            return

        if self.last_processed_e == e:
            return

        self.last_processed_e = e
        self.recent_fp.append(fp)

        self.last_draws.append(nums)
        if len(self.last_draws) > HISTORY_MAX:
            self.last_draws.pop(0)

        await self.tg(app, f"📌 Estrazione {e}")

        if self.cooldown > 0:
            self.cooldown -= 1
            return

        play, reason = self.choose()

        if not play:
            await self.tg(app, f"⏸ {reason}")
            return

        a,b = play

        await self.tg(app,
            f"🎯 PLAY\n"
            f"{a}-{b}"
        )

        self.cooldown = 1

# ===================== LOOP ================================

bot = SNIPER()

async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    for e, nums in es:
        bot.last_draws.append(nums)
        bot.max_e = max(bot.max_e, e)

    await bot.tg(app, "🚀 BOT AVVIATO")

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if e <= bot.max_e:
                    continue

                bot.max_e = e
                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ {ex}")

        bot.save()
        await asyncio.sleep(LOOP_SEC)

asyncio.run(live())
