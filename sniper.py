# ============================================================
# 🚀 SNIPER v29.5 PURE 15 + LEARNING PARTNERS
# ============================================================

import asyncio
import requests
import re
import os
import hashlib
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

# ============================================================

class SNIPER:

    def __init__(self):
        self.max_e = 0
        self.last_draws = []
        self.last_fp = None

        self.active = False
        self.colpi = 0
        self.cooldown = 0

        # 🔥 LEARNING PARTNERS
        self.partner_total = defaultdict(int)
        self.partner_recent = []

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

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

    def life15(self):
        return self.heat(15)*1.8 - self.lag(15)*0.6

    def pressure(self):
        weights = [5,4,3,2,1]
        score = 0
        for i,w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            c = len([x for x in self.last_draws[-(i+1)] if x in TARGET])
            score += c*w
        return score

    # ===================== LEARNING ==========================

    def update_partners(self, nums):

        partners = [x for x in nums if x != 15]

        for n in partners:
            self.partner_total[n] += 1

        self.partner_recent.append(partners)
        if len(self.partner_recent) > 20:
            self.partner_recent.pop(0)

    def top_partners(self):

        # globali
        global_top = sorted(self.partner_total.items(), key=lambda x: x[1], reverse=True)[:5]

        # recenti
        recent_count = defaultdict(int)
        for block in self.partner_recent:
            for n in block:
                recent_count[n] += 1

        recent_top = sorted(recent_count.items(), key=lambda x: x[1], reverse=True)[:5]

        return global_top, recent_top

    # ===================== LOGICA ============================

    def should_play(self):

        if self.cooldown > 0:
            return False

        if self.life15() < 3:
            return False

        if self.pressure() < 9:
            return False

        return True

    # ===================== MAIN ==============================

    async def on_new(self, app, e, nums):

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

            if 15 in s:

                await self.tg(app, f"🔥 HIT AMBATA 15 (colpo {self.colpi})")

                # 🔥 LEARNING PARTNERS
                self.update_partners(nums)
                global_top, recent_top = self.top_partners()

                await self.tg(
                    app,
                    "📎 PARTNER HIT15\n"
                    f"• estrazione = {', '.join(map(str, [x for x in nums if x != 15][:6]))}\n"
                    f"• top globale = {global_top}\n"
                    f"• top recente = {recent_top}"
                )

                self.active = False
                self.colpi = 0
                self.cooldown = 1
                return

            if self.colpi >= MAX_COLPI:
                await self.tg(app, "🛑 STOP 15")
                self.active = False
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

        if not self.should_play():
            await self.tg(app, "⏸ NO PLAY")
            return

        self.active = True
        self.colpi = 0

        await self.tg(app, "🎯 PLAY 15 (3 colpi)")

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

    await bot.tg(app, "🚀 SNIPER v29.5 PURE 15 AVVIATO")

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
