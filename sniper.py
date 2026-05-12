# ============================================================
# 🚀 SNIPER v42 — RIENTRI CONFERMATI AMBO
# Logica:
# 1) calcola top 10 ritardatari
# 2) osserva posizioni 6-7-8-9-10
# 3) quando un numero rientra 2 volte entro WATCH_WINDOW = confermato
# 4) mantiene i confermati caldi per HOT_TTL estrazioni
# 5) quando arriva un nuovo confermato, lo abbina ai confermati precedenti
# 6) gioca ambi per MAX_COLPI
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib
import subprocess
from datetime import datetime
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STATE_FILE = "sniper_v42_rientri_confermati_ambo_state.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

TOP_RITARDATARI = 10
PLAY_POSITIONS = [6, 7, 8, 9, 10]

WATCH_WINDOW = 10
HOT_TTL = 60

MAX_COLPI = 20
MAX_AMBI_PER_PLAY = 3


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


class SNIPER_V42_RIENTRI_AMBO:

    def __init__(self):
        self.version = "v42_rientri_confermati_ambo"

        self.day = day_key()
        self.max_e = 0
        self.last_fp = None
        self.last_draws = []

        self.processed_ids = []
        self.processed_fps = []

        self.watch = {}
        self.hot_confirmed = {}

        self.active = False
        self.colpi = 0
        self.active_snapshot = None

        self.total_play = 0
        self.total_hit = 0
        self.total_stop = 0

        self.hit_colpo_1 = 0
        self.hit_colpo_2_5 = 0
        self.hit_colpo_6_10 = 0
        self.hit_colpo_11_20 = 0

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
            "watch": self.watch,
            "hot_confirmed": self.hot_confirmed,
            "active": self.active,
            "colpi": self.colpi,
            "active_snapshot": self.active_snapshot,
            "total_play": self.total_play,
            "total_hit": self.total_hit,
            "total_stop": self.total_stop,
            "hit_colpo_1": self.hit_colpo_1,
            "hit_colpo_2_5": self.hit_colpo_2_5,
            "hit_colpo_6_10": self.hit_colpo_6_10,
            "hit_colpo_11_20": self.hit_colpo_11_20,
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

            self.watch = data.get("watch", {})
            self.hot_confirmed = data.get("hot_confirmed", {})

            self.active = bool(data.get("active", False))
            self.colpi = int(data.get("colpi", 0))
            self.active_snapshot = data.get("active_snapshot")

            self.total_play = int(data.get("total_play", 0))
            self.total_hit = int(data.get("total_hit", 0))
            self.total_stop = int(data.get("total_stop", 0))

            self.hit_colpo_1 = int(data.get("hit_colpo_1", 0))
            self.hit_colpo_2_5 = int(data.get("hit_colpo_2_5", 0))
            self.hit_colpo_6_10 = int(data.get("hit_colpo_6_10", 0))
            self.hit_colpo_11_20 = int(data.get("hit_colpo_11_20", 0))

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

            subprocess.run(["git", "commit", "-m", "update sniper v42 rientri ambo state"], check=False)
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

    # ===================== RITARDATARI ========================

    def lag(self, n):
        lag = 0
        for d in reversed(self.last_draws[:-1]):
            lag += 1
            if n in d:
                return lag
        return lag

    def top_ritardatari(self):
        data = []

        for n in range(1, 91):
            data.append({
                "number": n,
                "lag": self.lag(n)
            })

        data.sort(key=lambda x: (-x["lag"], x["number"]))
        return data[:TOP_RITARDATARI]

    def selected_ritardatari(self):
        top10 = self.top_ritardatari()
        selected = []

        for pos in PLAY_POSITIONS:
            idx = pos - 1
            if idx < len(top10):
                selected.append({
                    "position": pos,
                    "number": top10[idx]["number"],
                    "lag": top10[idx]["lag"]
                })

        return top10, selected

    # ===================== CLEAN ==============================

    def clean_old_watch(self, current_e):
        remove = []

        for key, data in self.watch.items():
            if current_e - int(data["first_e"]) > WATCH_WINDOW:
                remove.append(key)

        for key in remove:
            self.watch.pop(key, None)

    def clean_old_hot(self, current_e):
        remove = []

        for key, data in self.hot_confirmed.items():
            if current_e - int(data["confirmed_e"]) > HOT_TTL:
                remove.append(key)

        for key in remove:
            self.hot_confirmed.pop(key, None)

    # ===================== WATCH / CONFIRMED ==================

    def update_watch_and_confirmed(self, e, nums, selected):
        s = set(nums)
        new_confirmed = []

        for item in selected:
            n = int(item["number"])
            key = str(n)

            if n not in s:
                continue

            if key not in self.watch:
                self.watch[key] = {
                    "number": n,
                    "first_e": e,
                    "last_e": e,
                    "hits": 1,
                    "position": item["position"],
                    "initial_lag": item["lag"]
                }
            else:
                self.watch[key]["hits"] += 1
                self.watch[key]["last_e"] = e

                if self.watch[key]["hits"] >= 2:
                    confirmed = {
                        **self.watch[key],
                        "confirmed_e": e
                    }

                    self.hot_confirmed[key] = confirmed
                    new_confirmed.append(confirmed)

                    self.watch.pop(key, None)

        self.clean_old_watch(e)
        self.clean_old_hot(e)

        return new_confirmed

    # ===================== PLAY BUILDER =======================

    def build_ambo_play(self, e, new_confirmed):
        if not new_confirmed:
            return None

        ambi = []
        used = set()

        hot_items = list(self.hot_confirmed.values())

        for new_item in new_confirmed:
            new_n = int(new_item["number"])

            partners = []

            for old in hot_items:
                old_n = int(old["number"])

                if old_n == new_n:
                    continue

                age = e - int(old["confirmed_e"])

                if age < 0 or age > HOT_TTL:
                    continue

                partners.append({
                    "number": old_n,
                    "age": age,
                    "hits": int(old.get("hits", 0)),
                    "position": int(old.get("position", 99)),
                    "initial_lag": int(old.get("initial_lag", 0)),
                    "confirmed_e": int(old.get("confirmed_e", 0))
                })

            partners.sort(
                key=lambda x: (
                    x["age"],
                    -x["hits"],
                    x["position"],
                    -x["initial_lag"]
                )
            )

            for p in partners:
                pair = tuple(sorted((new_n, p["number"])))

                if pair in used:
                    continue

                used.add(pair)
                ambi.append({
                    "ambo": pair,
                    "new_number": new_n,
                    "partner": p["number"],
                    "partner_age": p["age"],
                    "new_detail": new_item,
                    "partner_detail": p
                })

                if len(ambi) >= MAX_AMBI_PER_PLAY:
                    break

        if not ambi:
            return None

        return {
            "reason": "RIENTRI_CONFERMATI_AMBO",
            "start_e": e + 1,
            "valid_to": e + MAX_COLPI,
            "max_colpi": MAX_COLPI,
            "ambi": ambi
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
            "event": "PLAY_AMBO",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **snapshot
        })

        self.play_log = self.play_log[-800:]

    def check_hit(self, nums):
        s = set(nums)
        hits = []

        for item in self.active_snapshot["ambi"]:
            a, b = item["ambo"]
            if a in s and b in s:
                hits.append(item)

        return hits

    def register_hit(self, colpo, nums, hits):
        self.total_hit += 1

        if colpo == 1:
            self.hit_colpo_1 += 1
        elif 2 <= colpo <= 5:
            self.hit_colpo_2_5 += 1
        elif 6 <= colpo <= 10:
            self.hit_colpo_6_10 += 1
        else:
            self.hit_colpo_11_20 += 1

        self.recent_results.append("HIT")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "HIT_AMBO",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "colpo": colpo,
            "draw": nums,
            "hits": hits,
            "snapshot": self.active_snapshot
        })

        self.play_log = self.play_log[-800:]

    def register_stop(self):
        self.total_stop += 1

        self.recent_results.append("STOP")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "STOP_AMBO",
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

        # ===================== PLAY ATTIVO =====================

        if self.active:
            self.colpi += 1

            hits = self.check_hit(nums)

            ambi_txt = ", ".join(
                f"{a}-{b}" for h in hits for a, b in [h["ambo"]]
            ) or "nessuno"

            await self.tg(
                app,
                f"🔎 CHECK v42 AMBI | colpo {self.colpi}/{MAX_COLPI}\n"
                f"• ambi usciti = {ambi_txt}"
            )

            if hits:
                self.register_hit(self.colpi, nums, hits)

                await self.tg(
                    app,
                    f"🔥 HIT AMBO v42 | colpo {self.colpi}\n"
                    f"🎯 Ambi usciti = {ambi_txt}\n\n"
                    f"📊 STATS v42\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• hit colpo 1 = {self.hit_colpo_1}\n"
                    f"• hit colpo 2-5 = {self.hit_colpo_2_5}\n"
                    f"• hit colpo 6-10 = {self.hit_colpo_6_10}\n"
                    f"• hit colpo 11-20 = {self.hit_colpo_11_20}"
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
                    f"🛑 STOP AMBO v42 | {MAX_COLPI} colpi\n"
                    f"📊 STATS v42\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
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

        # ===================== OSSERVAZIONE ====================

        if len(self.last_draws) < 30:
            self.save_state()
            return

        top10, selected = self.selected_ritardatari()
        new_confirmed = self.update_watch_and_confirmed(e, nums, selected)

        top10_txt = ", ".join(
            f"{i+1}:{x['number']}({x['lag']})"
            for i, x in enumerate(top10)
        )

        selected_txt = ", ".join(
            f"pos{x['position']}={x['number']} lag{x['lag']}"
            for x in selected
        )

        if new_confirmed:
            nc_txt = ", ".join(
                f"{x['number']} pos{x['position']} lag{x['initial_lag']} hits{x['hits']}"
                for x in new_confirmed
            )

            hot_txt = ", ".join(
                f"{x['number']}@{x['confirmed_e']}"
                for x in self.hot_confirmed.values()
            )

            await self.tg(
                app,
                f"🔥 RIENTRO CONFERMATO v42\n"
                f"• nuovi confermati = {nc_txt}\n"
                f"• hot confermati attivi = {hot_txt}\n"
                f"• top10 ritardatari = {top10_txt}\n"
                f"• zona osservata = {selected_txt}"
            )

            play = self.build_ambo_play(e, new_confirmed)

            if play:
                self.active = True
                self.colpi = 0
                self.active_snapshot = play

                self.register_play(play)

                ambi_txt = ", ".join(
                    f"{a}-{b}"
                    for item in play["ambi"]
                    for a, b in [item["ambo"]]
                )

                dettagli_txt = "\n".join(
                    f"• {a}-{b} | nuovo={item['new_number']} partner={item['partner']} "
                    f"age_partner={item['partner_age']}"
                    for item in play["ambi"]
                    for a, b in [item["ambo"]]
                )

                await self.tg(
                    app,
                    "🎯 PLAY AMBO v42 RIENTRI CONFERMATI\n"
                    f"• ambi = {ambi_txt}\n"
                    f"• valido da = {play['start_e']}\n"
                    f"• max_colpi = {MAX_COLPI}\n"
                    f"• logica = nuovo confermato + confermato caldo precedente\n\n"
                    f"{dettagli_txt}\n\n"
                    f"📊 STATS v42\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%"
                )

        self.save_state()

    async def send_report(self, app):
        hot_txt = ", ".join(
            f"{x['number']}@{x['confirmed_e']}"
            for x in self.hot_confirmed.values()
        ) or "nessuno"

        await self.tg(
            app,
            "📊 REPORT v42 RIENTRI CONFERMATI AMBO\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%\n"
            f"• hit colpo 1 = {self.hit_colpo_1}\n"
            f"• hit colpo 2-5 = {self.hit_colpo_2_5}\n"
            f"• hit colpo 6-10 = {self.hit_colpo_6_10}\n"
            f"• hit colpo 11-20 = {self.hit_colpo_11_20}\n"
            f"• hot confermati attivi = {hot_txt}"
        )


# ===================== LOOP ================================

bot = SNIPER_V42_RIENTRI_AMBO()


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
            "🚀 SNIPER v42 RIENTRI CONFERMATI AMBO AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• osservo prossime estrazioni reali"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v42 RIENTRI CONFERMATI AMBO RIAVVIATO\n"
            f"• max_e state = {bot.max_e}\n"
            f"• active = {bot.active}\n"
            f"• watch attivi = {len(bot.watch)}\n"
            f"• hot confermati = {len(bot.hot_confirmed)}"
        )

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore loop v42: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
