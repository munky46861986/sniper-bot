# ============================================================
# 🚀 SNIPER v28.4 PRO FINAL (NO FREEZE)
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

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TARGET = [5,10,15,50]

LOOP_SEC = 60

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

# ===================== BOT ===============================

class SNIPER:

    def __init__(self):
        self.last_draws = []
        self.max_e = 0
        self.cooldown = 0
        self.last_fp = None

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

    # ===================== FEATURES ==========================

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
        weights = [5,4,3,2,1]
        score = 0
        for i,w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            c = len([x for x in self.last_draws[-(i+1)] if x in TARGET])
            score += c*w
        return score

    # ===================== LOGIC =============================

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

    # ===================== MAIN ==============================

    async def on_new(self, app, e, nums):

        fp = hashlib.md5(f"{e}-{nums}".encode()).hexdigest()

        if fp == self.last_fp:
            return

        self.last_fp = fp

        self.last_draws.append(nums)
        if len(self.last_draws) > 160:
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

        await self.tg(app, f"🎯 PLAY {a}-{b}")

        self.cooldown = 1

# ===================== LOOP ================================

bot = SNIPER()

async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    # warmup SENZA bloccare l'ultima
    for e, nums in es[:-1]:
        bot.last_draws.append(nums)

    # IMPORTANTISSIMO
    bot.max_e = es[-2][0] if len(es) >= 2 else 0

    await bot.tg(app, "🚀 BOT AVVIATO (NO FREEZE)")

    while True:
        try:
            es = parse_site()

            if es:
                print("Ultima:", es[-1][0], "| max_e:", bot.max_e)

            for e, nums in es:
                if e <= bot.max_e:
                    continue

                bot.max_e = e
                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ {ex}")

        await asyncio.sleep(LOOP_SEC)

asyncio.run(live())
