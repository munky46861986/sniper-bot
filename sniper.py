# ============================================================
# 🚀 SNIPER v28.5 PRO — FINAL STABLE (TEXT PARSER FIXED)
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

TARGET = [5, 10, 15, 50]

LOOP_SEC = 60
HISTORY_MAX = 160

# ===================== PARSER ===============================

def parse_site():
    r = requests.get(URL, headers=HEADERS, timeout=15)
    r.raise_for_status()

    text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)

    # blocchi reali del sito:
    # Estrazione Martedi, 14 Aprile 2026, ore 13:10 n. 158
    # ... 20 numeri ...
    # EXTRA E NUMERI ORO
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
        self.cooldown = 0
        self.day = day_key()

    # ===================== TELEGRAM ==========================

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

    # ===================== RESET GIORNO ======================

    def reset_day_if_needed(self):
        today = day_key()
        if today != self.day:
            print("RESET GIORNO")
            self.day = today
            self.max_e = 0
            self.last_fp = None

    # ===================== FEATURES ==========================

    def heat(self, n):
        weights = [5, 4, 3, 2, 1]
        h = 0
        for i, w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            if n in self.last_draws[-(i + 1)]:
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
        weights = [5, 4, 3, 2, 1]
        score = 0
        for i, w in enumerate(weights):
            if i >= len(self.last_draws):
                break
            c = len([x for x in self.last_draws[-(i + 1)] if x in TARGET])
            score += c * w
        return score

    # ===================== SUPPORT ===========================

    def choose_support(self):
        s50 = self.heat(50) - self.lag(50) * 0.5
        s5 = self.heat(5) - self.lag(5) * 0.5
        return 50 if s50 > s5 else 5

    # ===================== AI FILTER =========================

    def ai_filter(self, support):
        p = self.pressure()
        life15 = self.heat(15) * 1.8 - self.lag(15) * 0.6

        score = 0.0

        if p >= 14:
            score += 2.0
        elif p >= 10:
            score += 1.0
        else:
            score -= 2.0

        if life15 >= 8:
            score += 2.0
        elif life15 >= 5:
            score += 1.0
        else:
            score -= 2.0

        life_s = self.heat(support) - self.lag(support) * 0.5

        if life_s >= 5:
            score += 1.5
        elif life_s < 2:
            score -= 1.5

        return score

    # ===================== LOGICA ============================

    def choose(self):
        p = self.pressure()
        h = self.heat(15)
        l = self.lag(15)

        life15 = h * 1.8 - l * 0.6

        if life15 < 3:
            return None, "15 morto"

        if p < 9:
            return None, "pressione bassa"

        support = self.choose_support()
        ai = self.ai_filter(support)

        if ai < 1:
            return None, "AI blocca"

        return (15, support), "OK"

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

        await self.tg(app, f"📌 Estrazione {e}\n🎱 {', '.join(f'{x:02d}' for x in nums)}")

        if self.cooldown > 0:
            self.cooldown -= 1
            return

        play, reason = self.choose()

        if not play:
            await self.tg(app, f"⏸ {reason}")
            return

        a, b = play
        await self.tg(app, f"🎯 PLAY {a}-{b}")
        self.cooldown = 1

# ===================== LOOP ================================

bot = SNIPER()

async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    print("DEBUG estrazioni lette:", len(es))
    if es:
        print("DEBUG prima:", es[0][0], "ultima:", es[-1][0])
    else:
        print("DEBUG parser vuoto")

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    # warmup senza bloccare l'ultima
    for e, nums in es[:-1]:
        bot.last_draws.append(nums)

    bot.max_e = es[-2][0] if len(es) >= 2 else 0

    await bot.tg(app, "🚀 SNIPER v28.5 PRO AVVIATO")

    while True:
        try:
            es = parse_site()

            print("DEBUG estrazioni lette:", len(es))
            if es:
                print("DEBUG prima:", es[0][0], "ultima:", es[-1][0], "| max_e:", bot.max_e)
            else:
                print("DEBUG parser vuoto nel loop")

            for e, nums in es:
                if e <= bot.max_e:
                    continue

                bot.max_e = e
                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ {ex}")

        await asyncio.sleep(LOOP_SEC)

asyncio.run(live())
