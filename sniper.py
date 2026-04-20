# ============================================================
# 🚀 SNIPER v29 CORE — AMBO FOCUS
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
HISTORY_MAX = 160
MAX_COLPI = 3

# ===================== PARSER ===============================

def parse_site():
    r = requests.get(URL, headers=HEADERS, timeout=15)
    r.raise_for_status()

    text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    out = {}
    i = 0

    while i < len(lines):
        line = lines[i]

        m = re.search(r"Estrazione\s+.*?\bn\.\s*(\d+)", line, re.IGNORECASE)
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
            if "EXTRA" in row.upper():
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

        continue

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

        self.active = None
        self.colpi = 0
        self.cooldown = 0

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

    def reset_day(self):
        if day_key() != self.day:
            self.day = day_key()
            self.max_e = 0
            self.last_fp = None
            self.active = None
            self.cooldown = 0

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

    def life(self, n):
        return self.heat(n)*1.8 - self.lag(n)*0.6

    def pressure(self):
        weights = [5,4,3,2,1]
        score = 0
        for i,w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            c = len([x for x in self.last_draws[-(i+1)] if x in TARGET])
            score += c*w
        return score

    def seen_recent(self, n, k=2):
        return any(n in d for d in self.last_draws[-k:])

    # ===================== LOGICA ============================

    def choose(self):

        if self.cooldown > 0:
            return None

        life15 = self.life(15)
        if life15 < 3:
            return None

        if self.pressure() < 9:
            return None

        life50 = self.life(50)
        life5 = self.life(5)

        # ===================== 15-50 STRONG =====================

        if life50 >= 5 and life50 >= life5 + 1:
            return (15, 50)

        # ===================== 15-5 EXPLOSIVE ==================

        if life5 >= 4 or self.seen_recent(5,2):
            return (15, 5)

        return None

    # ===================== MAIN ==============================

    async def on_new(self, app, e, nums):

        self.reset_day()

        fp = fingerprint(e, nums)
        if fp == self.last_fp:
            return
        self.last_fp = fp

        if len(set(nums)) != 20:
            return

        self.last_draws.append(nums)
        if len(self.last_draws) > HISTORY_MAX:
            self.last_draws.pop(0)

        s = set(nums)

        await self.tg(app, f"📌 Estrazione {e}\n🎱 {', '.join(map(str, nums))}")

        # ===================== PLAY ATTIVO =====================

        if self.active:

            self.colpi += 1
            A, S = self.active

            if A in s and S in s:
                await self.tg(app, f"💥 HIT AMBO {A}-{S}")

            if A in s:
                await self.tg(app, f"🔥 HIT AMBATA {A} (colpo {self.colpi})")
                self.active = None
                self.colpi = 0
                self.cooldown = 1
                return

            if self.colpi >= MAX_COLPI:
                await self.tg(app, f"🛑 STOP {A}")
                self.active = None
                self.colpi = 0
                self.cooldown = 1
                return

            return

        # ===================== COOLDOWN =======================

        if self.cooldown > 0:
            self.cooldown -= 1
            await self.tg(app, "⏸ cooldown")
            return

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

    await bot.tg(app, "🚀 SNIPER v29 CORE AVVIATO")

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
