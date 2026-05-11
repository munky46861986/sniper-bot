# ============================================================
# 🚀 SNIPER v39 — CINQUINA + AMBI/TERNI CORE + HIT TRACKING
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
from itertools import combinations
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STATE_FILE = "sniper_v39_combo_top_hotlag_state.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

BLOCK_SIZE = 12
TOP_N = 10
PLAY_SIZE = 5
CORE_SIZE = 4
MAX_COLPI = 6


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


class SNIPER_V39:

    def __init__(self):
        self.version = "v39_combo_top_hotlag"

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

        self.hit_2su5 = 0
        self.hit_3su5 = 0
        self.hit_4su5 = 0
        self.hit_5su5 = 0
        self.hit_ambo_core = 0
        self.hit_terno_core = 0

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
            "hit_2su5": self.hit_2su5,
            "hit_3su5": self.hit_3su5,
            "hit_4su5": self.hit_4su5,
            "hit_5su5": self.hit_5su5,
            "hit_ambo_core": self.hit_ambo_core,
            "hit_terno_core": self.hit_terno_core,
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

            self.hit_2su5 = int(data.get("hit_2su5", 0))
            self.hit_3su5 = int(data.get("hit_3su5", 0))
            self.hit_4su5 = int(data.get("hit_4su5", 0))
            self.hit_5su5 = int(data.get("hit_5su5", 0))
            self.hit_ambo_core = int(data.get("hit_ambo_core", 0))
            self.hit_terno_core = int(data.get("hit_terno_core", 0))

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

            subprocess.run(["git", "commit", "-m", "update sniper v39 combo state"], check=False)
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

        riga10 = [x["number"] for x in scored]
        cinquina = riga10[:PLAY_SIZE]
        core4 = riga10[:CORE_SIZE]

        ambi_core = list(combinations(core4, 2))
        terni_core = list(combinations(core4, 3))

        return {
            "reason": "CINQUINA5_PLUS_AMBI_TERNI_CORE",
            "block_end": e,
            "valid_from": e + 1,
            "valid_to": e + MAX_COLPI,
            "top10_raw": [
                {"position": i + 1, "number": n, "freq": freq}
                for i, (n, freq) in enumerate(top10_raw)
            ],
            "scored": scored,
            "riga10": riga10,
            "cinquina": cinquina,
            "core4": core4,
            "ambi_core": ambi_core,
            "terni_core": terni_core
        }

    def check_hits(self, nums):
        s = set(nums)
        snap = self.active_snapshot

        cinquina = snap["cinquina"]
        core4 = snap["core4"]
        ambi_core = snap["ambi_core"]
        terni_core = snap["terni_core"]

        usciti_cinquina = [n for n in cinquina if n in s]
        usciti_core = [n for n in core4 if n in s]

        ambi_hit = [a for a in ambi_core if a[0] in s and a[1] in s]
        terni_hit = [t for t in terni_core if all(n in s for n in t)]

        return {
            "usciti_cinquina": usciti_cinquina,
            "count_cinquina": len(usciti_cinquina),
            "usciti_core": usciti_core,
            "count_core": len(usciti_core),
            "ambi_hit": ambi_hit,
            "terni_hit": terni_hit
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
            "event": "PLAY",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **snapshot
        })
        self.play_log = self.play_log[-800:]

    def register_hit_result(self, colpo, nums, hit_data):
        has_real_hit = (
            hit_data["count_cinquina"] >= 2 or
            len(hit_data["ambi_hit"]) > 0 or
            len(hit_data["terni_hit"]) > 0
        )

        if not has_real_hit:
            return False

        self.total_hit += 1

        c = hit_data["count_cinquina"]

        if c == 2:
            self.hit_2su5 += 1
        elif c == 3:
            self.hit_3su5 += 1
        elif c == 4:
            self.hit_4su5 += 1
        elif c >= 5:
            self.hit_5su5 += 1

        if hit_data["ambi_hit"]:
            self.hit_ambo_core += 1

        if hit_data["terni_hit"]:
            self.hit_terno_core += 1

        self.recent_results.append("HIT")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "HIT",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "colpo": colpo,
            "draw": nums,
            "hit_data": hit_data,
            "snapshot": self.active_snapshot
        })
        self.play_log = self.play_log[-800:]

        return True

    def register_stop(self):
        self.total_stop += 1
        self.recent_results.append("STOP")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "STOP",
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

            cinquina_txt = ", ".join(map(str, hit_data["usciti_cinquina"])) or "nessuno"
            core_txt = ", ".join(map(str, hit_data["usciti_core"])) or "nessuno"
            ambi_txt = ", ".join(f"{a}-{b}" for a, b in hit_data["ambi_hit"]) or "nessuno"
            terni_txt = ", ".join("-".join(map(str, t)) for t in hit_data["terni_hit"]) or "nessuno"

            # manda sempre aggiornamento colpo
            await self.tg(
                app,
                f"🔎 CHECK v39 | colpo {self.colpi}/{MAX_COLPI}\n"
                f"• cinquina usciti = {hit_data['count_cinquina']}/5 → {cinquina_txt}\n"
                f"• core usciti = {hit_data['count_core']}/4 → {core_txt}\n"
                f"• ambi core = {ambi_txt}\n"
                f"• terni core = {terni_txt}"
            )

            # chiude il play solo se fa almeno 3/5 o terno core
            close_hit = (
                hit_data["count_cinquina"] >= 3 or
                len(hit_data["terni_hit"]) > 0
            )

            if close_hit:
                self.register_hit_result(self.colpi, nums, hit_data)

                await self.tg(
                    app,
                    f"🔥 HIT v39 | colpo {self.colpi}\n"
                    f"🎯 Cinquina: {hit_data['count_cinquina']}/5 → {cinquina_txt}\n"
                    f"💎 Core: {hit_data['count_core']}/4 → {core_txt}\n"
                    f"✅ Ambi core: {ambi_txt}\n"
                    f"✅ Terni core: {terni_txt}\n\n"
                    f"📊 STATS v39\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit chiusi = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• 2/5 = {self.hit_2su5}\n"
                    f"• 3/5 = {self.hit_3su5}\n"
                    f"• 4/5 = {self.hit_4su5}\n"
                    f"• 5/5 = {self.hit_5su5}\n"
                    f"• ambi core = {self.hit_ambo_core}\n"
                    f"• terni core = {self.hit_terno_core}"
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
                    f"🛑 STOP v39 | {MAX_COLPI} colpi\n"
                    f"📊 STATS v39\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit chiusi = {self.total_hit}\n"
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

        cinquina_txt = ", ".join(map(str, data["cinquina"]))
        core_txt = ", ".join(map(str, data["core4"]))
        riga_txt = ", ".join(map(str, data["riga10"]))
        ambi_txt = ", ".join(f"{a}-{b}" for a, b in data["ambi_core"])
        terni_txt = ", ".join("-".join(map(str, t)) for t in data["terni_core"])

        scored_txt = "\n".join(
            f"{i+1}) {x['number']} | score={x['score']} | "
            f"freq={x['freq']} heat={x['heat']} lag={x['lag']} "
            f"dom={x['dominance']} pressure={x['pressure']}"
            for i, x in enumerate(data["scored"])
        )

        await self.tg(
            app,
            "🎯 PLAY v39 CINQUINA + CORE\n"
            f"• blocco analizzato = fino estrazione {data['block_end']}\n"
            f"• valido da = {data['valid_from']}\n"
            f"• max_colpi = {MAX_COLPI}\n\n"
            f"🔥 CINQUINA 5:\n{cinquina_txt}\n\n"
            f"💎 CORE 4:\n{core_txt}\n\n"
            f"✅ AMBI CORE:\n{ambi_txt}\n\n"
            f"🎲 TERNI CORE:\n{terni_txt}\n\n"
            f"👀 RIGA 10:\n{riga_txt}\n\n"
            f"📊 Ranking:\n{scored_txt}"
        )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v39\n"
            f"• play totali = {self.total_play}\n"
            f"• hit chiusi = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%\n"
            f"• 2/5 = {self.hit_2su5}\n"
            f"• 3/5 = {self.hit_3su5}\n"
            f"• 4/5 = {self.hit_4su5}\n"
            f"• 5/5 = {self.hit_5su5}\n"
            f"• ambi core = {self.hit_ambo_core}\n"
            f"• terni core = {self.hit_terno_core}"
        )


# ===================== LOOP ================================

bot = SNIPER_V39()


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
            "🚀 SNIPER v39 AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• attendo prossima estrazione reale"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v39 RIAVVIATO\n"
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
            await bot.tg(app, f"⚠️ Errore loop v39: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
