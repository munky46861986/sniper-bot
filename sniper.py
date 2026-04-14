# ============================================================
# 🚀 SNIPER v28.6 CORE — TRACKING FIX
# semplice + stabile + HIT/STOP corretti
# ============================================================

import asyncio
import requests
import re
import os
import hashlib
from datetime import datetime
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

# ===================== CONFIG ===============================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TARGET = [5,10,15,50]

LOOP_SEC = 60
HISTORY_MAX = 160
MAX_COLPI = 3

# ===================== PARSER ===============================

def parse_site():
    r = requests.get(URL, headers=HEADERS, timeout=15)
    r.raise_for_status()

    text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)

    pattern = re.compile(
        r"Estrazione\s+.*?ore\s+\d{1,2}:\d{2}\s+n\.\s*(\d+)\s*"
        r"(.*?)"
        r"EXTRA E NUMERI ORO",
        re.IGNORECASE | re.DOTALL
    )

    out = {}

    for m in pattern.finditer(text):
        e = int(m.group(1))
        block = m.group(2)

        nums_raw = re.findall(r"\b\d{1,2}\b", block)
        nums = [int(x) for x in nums_raw if 1 <= int(x) <= 90]

        if len(nums) >= 20:
            out[e] = nums[:20]

    return sorted(out.items())

def fingerprint(e, nums):
    return hashlib.md5(f"{e}-{nums}".encode()).hexdigest()

def day_key():
    return datetime.now().strftime("%Y-%m-%d")

# ============================================================

class SNIPER:

    def __init__(self):
        self.max_e = 0
        self.last_draws = []
        self.last_fp = None
        self.day = day_key()

        # TRACKING PLAY
        self.active = None
        self.colpi = 0

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

    def reset_day_if_needed(self):
        if day_key() != self.day:
            print("RESET GIORNO")
            self.day = day_key()
            self.max_e = 0
            self.last_fp = None
            self.active = None

    # ===================== FEATURES ==========================

    def heat(self, n):
        weights = [5,4,3,2,1]
        return sum(w for i,w in enumerate(weights) if i < len(self.last_draws) and n in self.last_draws[-(i+1)])

    def lag(self, n):
        lag = 0
        for d in reversed(self.last_draws[:-1]):
            lag += 1
            if n in d:
                return lag
        return lag

    def pressure(self):
        weights = [5,4,3,2,1]
        score = 0
        for i,w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            c = len([x for x in self.last_draws[-(i+1)] if x in TARGET])
            score += c*w
        return score

    # ===================== LOGICA ============================

    def choose(self):
        p = self.pressure()
        h = self.heat(15)
        l = self.lag(15)

        life15 = h*1.8 - l*0.6

        if life15 < 3:
            return None

        if p < 9:
            return None

        s50 = self.heat(50) - self.lag(50)*0.5
        s5 = self.heat(5) - self.lag(5)*0.5

        return (15, 50 if s50 > s5 else 5)

    # ===================== MAIN ==============================

    async def on_new(self, app, e, nums):

        self.reset_day_if_needed()

        fp = fingerprint(e, nums)
        if fp == self.last_fp:
            return
        self.last_fp = fp

        self.last_draws.append(nums)
        if len(self.last_draws) > HISTORY_MAX:
            self.last_draws.pop(0)

        s = set(nums)

        await self.tg(app, f"📌 Estrazione {e}\n🎱 {', '.join(map(str, nums))}")

        # ===================== PLAY ATTIVO =====================

        if self.active is not None:

            self.colpi += 1

            A, S = self.active

            hitA = A in s
            hitS = S in s

            if hitA and hitS:
                await self.tg(app, f"💥 HIT AMBO {A}-{S}")

            if hitA:
                await self.tg(app, f"🔥 HIT AMBATA {A} (colpo {self.colpi})")
                self.active = None
                self.colpi = 0
                return

            if self.colpi >= MAX_COLPI:
                await self.tg(app, f"🛑 STOP {A}")
                self.active = None
                self.colpi = 0
                return

            return  # NON apre nuovo play

        # ===================== NUOVO PLAY =====================

        if len(self.last_draws) < 10:
            return

        play = self.choose()

        if not play:
            await self.tg(app, "⏸ NO PLAY")
            return

        self.active = play
        self.colpi = 0

        A, S = play

        await self.tg(app, f"🎯 PLAY {A}-{S} (3 colpi)")

# ===================== LOOP ================================

bot = SNIPER()

async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    for e, nums in es[:-1]:
        bot.last_draws.append(nums)

    bot.max_e = es[-2][0] if len(es) >= 2 else 0

    await bot.tg(app, "🚀 SNIPER v28.6 CORE AVVIATO")

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

        await asyncio.sleep(LOOP_SEC)

asyncio.run(live())
