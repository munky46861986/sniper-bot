# ============================================================
# 🚀 SNIPER v30 — AMBO INTELLIGENTE + FULL STATE JSON
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib
import subprocess
from datetime import datetime
from collections import defaultdict, Counter
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TARGET = [5, 10, 15, 50]
HISTORIC_PARTNERS = [5, 50, 40, 55, 10, 20]
LIVE_POOL = [28, 83, 19, 16, 30, 41, 36, 90, 34, 67]

LOOP_SEC = 60
HISTORY_MAX = 160
STATE_FILE = "sniper_state.json"

BASE_MAX_COLPI = 2
STRONG_MAX_COLPI = 3

LIFE15_MIN = 4.0
PRESSURE_MIN = 9
STRONG_LIFE15 = 7.0
STRONG_PRESSURE = 14

# ===================== PARSER ===============================

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
    return hashlib.md5(f"{e}-{nums}".encode()).hexdigest()


def day_key():
    return datetime.now().strftime("%Y-%m-%d")


# ============================================================

class SNIPER:

    def __init__(self):
        self.day = day_key()
        self.max_e = 0
        self.last_fp = None
        self.last_draws = []

        self.active = False
        self.colpi = 0
        self.max_colpi_active = BASE_MAX_COLPI
        self.active_ambata = 15
        self.active_s1 = None
        self.active_s2 = None

        self.cooldown = 0
        self.recent_results = []

        self.partner_total = defaultdict(int)
        self.partner_recent = []
        self.hit15_count = 0

        self.load_state()

    # ===================== TELEGRAM ==========================

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

    # ===================== STATE =============================

    def save_state(self):
        data = {
            "version": "v30_AMBO_INTELLIGENTE",
            "day": self.day,
            "max_e": self.max_e,
            "last_fp": self.last_fp,
            "last_draws": self.last_draws[-HISTORY_MAX:],

            "active": self.active,
            "colpi": self.colpi,
            "max_colpi_active": self.max_colpi_active,
            "active_ambata": self.active_ambata,
            "active_s1": self.active_s1,
            "active_s2": self.active_s2,

            "cooldown": self.cooldown,
            "recent_results": self.recent_results[-10:],

            "partner_total": dict(self.partner_total),
            "partner_recent": self.partner_recent[-20:],
            "hit15_count": self.hit15_count
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

            self.partner_total = defaultdict(
                int,
                {int(k): int(v) for k, v in data.get("partner_total", {}).items()}
            )
            self.partner_recent = data.get("partner_recent", [])[-20:]
            self.hit15_count = int(data.get("hit15_count", 0))

            saved_day = data.get("day", day_key())

            if saved_day != day_key():
                self.day = day_key()
                self.max_e = 0
                self.last_fp = None
                self.last_draws = []
                self.active = False
                self.colpi = 0
                self.cooldown = 0
                self.recent_results = []
                return

            self.day = saved_day
            self.max_e = int(data.get("max_e", 0))
            self.last_fp = data.get("last_fp", None)
            self.last_draws = data.get("last_draws", [])[-HISTORY_MAX:]

            self.active = bool(data.get("active", False))
            self.colpi = int(data.get("colpi", 0))
            self.max_colpi_active = int(data.get("max_colpi_active", BASE_MAX_COLPI))
            self.active_ambata = int(data.get("active_ambata", 15))
            self.active_s1 = data.get("active_s1", None)
            self.active_s2 = data.get("active_s2", None)

            if self.active_s1 is not None:
                self.active_s1 = int(self.active_s1)
            if self.active_s2 is not None:
                self.active_s2 = int(self.active_s2)

            self.cooldown = int(data.get("cooldown", 0))
            self.recent_results = data.get("recent_results", [])[-10:]

        except Exception:
            pass

    def git_commit_state(self):
        if os.getenv("GITHUB_ACTIONS") != "true":
            return

        try:
            subprocess.run(["git", "config", "user.name", "github-actions"], check=False)
            subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=False)
            subprocess.run(["git", "add", STATE_FILE], check=False)

            diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
            if diff.returncode == 0:
                return

            subprocess.run(["git", "commit", "-m", "update sniper state"], check=False)
            subprocess.run(["git", "push"], check=False)

        except Exception:
            pass

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

    def pressure(self):
        weights = [5, 4, 3, 2, 1]
        score = 0

        for i, w in enumerate(weights):
            if i >= len(self.last_draws):
                break

            c = len([x for x in self.last_draws[-(i + 1)] if x in TARGET])
            score += c * w

        return score

    def push_result(self, result):
        self.recent_results.append(result)
        if len(self.recent_results) > 10:
            self.recent_results.pop(0)

    def consecutive_stops(self):
        c = 0
        for r in reversed(self.recent_results):
            if r == "STOP":
                c += 1
            else:
                break
        return c

    # ===================== PARTNER LEARNING ==================

    def update_partners(self, nums):
        partners = [x for x in nums if x != 15]

        for n in partners:
            self.partner_total[n] += 1

        self.partner_recent.append(partners)
        if len(self.partner_recent) > 20:
            self.partner_recent.pop(0)

    def top_partners(self):
        global_top = sorted(self.partner_total.items(), key=lambda x: x[1], reverse=True)[:10]

        recent_count = defaultdict(int)
        for block in self.partner_recent:
            for n in block:
                recent_count[n] += 1

        recent_top = sorted(recent_count.items(), key=lambda x: x[1], reverse=True)[:10]
        return global_top, recent_top

    def recent_partner_count(self):
        c = Counter()
        for block in self.partner_recent:
            for n in block:
                c[n] += 1
        return c

    def partner_score(self, n):
        total = self.partner_total.get(n, 0)
        recent = self.recent_partner_count().get(n, 0)
        life = self.life(n)
        h = self.heat(n)
        d = self.dominance(n, 6)

        score = 0.0
        score += total * 0.45
        score += recent * 1.15
        score += life * 0.75
        score += h * 0.6
        score += d * 0.9

        if n in HISTORIC_PARTNERS:
            score += 2.0

        if n in LIVE_POOL:
            score += 1.3

        return round(score, 2)

    def choose_dynamic_partner(self):
        candidates = list(dict.fromkeys(HISTORIC_PARTNERS + LIVE_POOL))
        candidates = [x for x in candidates if x != 5 and x != 15]

        ranked = sorted(
            [(n, self.partner_score(n)) for n in candidates],
            key=lambda x: x[1],
            reverse=True
        )

        return ranked[0][0], ranked[:8]

    # ===================== FILTER ============================

    def should_play(self):
        life15 = self.life(15)
        pressure = self.pressure()
        h15 = self.heat(15)
        l15 = self.lag(15)
        d15 = self.dominance(15, 6)

        if self.consecutive_stops() >= 2:
            if life15 < 7.0 or pressure < 13:
                return False, "ANTI_STOP_FILTER"

        if life15 < LIFE15_MIN:
            return False, "15_WEAK_LIFE"

        if pressure < PRESSURE_MIN:
            return False, "LOW_PRESSURE"

        if h15 < 2 and d15 == 0:
            return False, "15_NOT_PRESENT_ENOUGH"

        if l15 > 8 and pressure < 14:
            return False, "15_TOO_DELAYED_WEAK_CONTEXT"

        return True, "OK"

    def choose_max_colpi(self):
        if self.life(15) >= STRONG_LIFE15 or self.pressure() >= STRONG_PRESSURE:
            return STRONG_MAX_COLPI
        return BASE_MAX_COLPI

    # ===================== MAIN ==============================

    async def on_new(self, app, e, nums):
        fp = fingerprint(e, nums)

        if fp == self.last_fp:
            return

        self.last_fp = fp

        if len(set(nums)) != 20:
            await self.tg(app, f"⚠️ Parser scarta estrazione {e}")
            return

        self.max_e = max(self.max_e, e)
        self.last_draws.append(nums)

        if len(self.last_draws) > HISTORY_MAX:
            self.last_draws.pop(0)

        s = set(nums)

        await self.tg(app, f"📌 Estrazione {e}\n🎱 {', '.join(map(str, nums))}")

        # ===================== PLAY ATTIVO =====================

        if self.active:
            self.colpi += 1

            A = self.active_ambata
            S1 = self.active_s1
            S2 = self.active_s2

            hitA = A in s
            hit1 = hitA and S1 in s if S1 is not None else False
            hit2 = hitA and S2 in s if S2 is not None else False

            if hit1:
                await self.tg(app, f"💥 HIT AMBO {A}-{S1}")

            if hit2:
                await self.tg(app, f"💥 HIT AMBO {A}-{S2}")

            if hitA:
                await self.tg(app, f"🔥 HIT AMBATA {A} (colpo {self.colpi})")

                self.update_partners(nums)
                self.hit15_count += 1
                self.push_result("HIT")

                global_top, recent_top = self.top_partners()
                partners_now = [x for x in nums if x != 15]

                await self.tg(
                    app,
                    "📎 PARTNER HIT15\n"
                    f"• hit15 salvati = {self.hit15_count}\n"
                    f"• partner estrazione = {', '.join(map(str, partners_now))}\n"
                    f"• top globale = {global_top[:5]}\n"
                    f"• top recente = {recent_top[:5]}"
                )

                if self.hit15_count % 5 == 0:
                    await self.tg(
                        app,
                        "📊 REPORT PARTNER 15\n"
                        f"• hit15 salvati = {self.hit15_count}\n"
                        f"• TOP GLOBALE = {global_top}\n"
                        f"• TOP RECENTE = {recent_top}"
                    )

                self.active = False
                self.colpi = 0
                self.cooldown = 1
                self.save_state()
                return

            if self.colpi >= self.max_colpi_active:
                await self.tg(
                    app,
                    f"🛑 STOP 15 ({self.max_colpi_active} colpi)\n"
                    f"• ambo1 = 15-{S1}\n"
                    f"• ambo2 = 15-{S2}"
                )

                self.active = False
                self.colpi = 0
                self.cooldown = 1
                self.push_result("STOP")
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

        if len(self.last_draws) < 10:
            self.save_state()
            return

        ok, reason = self.should_play()

        if not ok:
            await self.tg(
                app,
                "⏸ NO PLAY\n"
                f"• reason = {reason}\n"
                f"• life15 = {self.life(15)}\n"
                f"• pressure = {self.pressure()}\n"
                f"• heat15 = {self.heat(15)}\n"
                f"• lag15 = {self.lag(15)}"
            )
            self.save_state()
            return

        dyn, dyn_rank = self.choose_dynamic_partner()

        self.active = True
        self.colpi = 0
        self.max_colpi_active = self.choose_max_colpi()
        self.active_ambata = 15
        self.active_s1 = 5
        self.active_s2 = dyn

        if self.active_s2 == self.active_s1:
            self.active_s2 = 50

        await self.tg(
            app,
            "🎯 PLAY AMBO INTELLIGENTE v30\n"
            f"• AMBATA = 15\n"
            f"• AMBO1 storico = 15-{self.active_s1}\n"
            f"• AMBO2 dinamico = 15-{self.active_s2}\n"
            f"• max_colpi = {self.max_colpi_active}\n"
            f"• life15 = {self.life(15)}\n"
            f"• pressure = {self.pressure()}\n"
            f"• heat15 = {self.heat(15)}\n"
            f"• lag15 = {self.lag(15)}\n"
            f"• ranking dinamico = {dyn_rank[:5]}"
        )

        self.save_state()


# ===================== LOOP ================================

bot = SNIPER()

async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    if not bot.last_draws:
        for e, nums in es[:-1]:
            bot.last_draws.append(nums)

        bot.max_e = es[-2][0] if len(es) >= 2 else 0
        bot.save_state()

    await bot.tg(app, "🚀 SNIPER v30 AMBO INTELLIGENTE AVVIATO")

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if e <= bot.max_e:
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore loop: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
