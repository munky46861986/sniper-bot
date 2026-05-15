# ============================================================
# 🚀 SNIPER v45 — CLUSTER PLUS
# Più play:
# - MIN_HOT_ACTIVE = 2
# - WATCH_WINDOW = 8
# - HOT_TTL = 35
#
# Output:
# - 1 AMBATA forte
# - 3 AMBI cluster
# - 1 JOLLY forte
# - 3 TERNI = ogni ambo + jolly
# ============================================================

import asyncio
import requests
import re
import os
import json
import hashlib
import subprocess
from datetime import datetime
from itertools import combinations
from collections import Counter
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

STATE_FILE = "sniper_v45_cluster_plus_state.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

TOP_RITARDATARI = 10
PLAY_POSITIONS = [6, 7, 8, 9, 10]

WATCH_WINDOW = 8
HOT_TTL = 35

MIN_HOT_ACTIVE = 2
MAX_AMBI_PER_PLAY = 3
MAX_COLPI = 7


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


class SNIPER_V45_CLUSTER_PLUS:

    def __init__(self):
        self.version = "v45_cluster_plus"

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
        self.total_hit_ambo = 0
        self.total_hit_terno = 0
        self.total_hit_ambata = 0
        self.total_stop = 0

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
            "total_hit_ambo": self.total_hit_ambo,
            "total_hit_terno": self.total_hit_terno,
            "total_hit_ambata": self.total_hit_ambata,
            "total_stop": self.total_stop,
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
            self.total_hit_ambo = int(data.get("total_hit_ambo", 0))
            self.total_hit_terno = int(data.get("total_hit_terno", 0))
            self.total_hit_ambata = int(data.get("total_hit_ambata", 0))
            self.total_stop = int(data.get("total_stop", 0))

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

            subprocess.run(["git", "commit", "-m", "update sniper v45 cluster plus"], check=False)
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

    # ===================== FEATURES ===========================

    def lag(self, n):
        lag = 0
        for d in reversed(self.last_draws[:-1]):
            lag += 1
            if n in d:
                return lag
        return lag

    def heat(self, n):
        weights = [5, 4, 3, 2, 1]
        return sum(
            w for i, w in enumerate(weights)
            if i < len(self.last_draws) and n in self.last_draws[-(i + 1)]
        )

    def dominance(self, n, window=6):
        return sum(1 for d in self.last_draws[-window:] if n in d)

    def pressure(self, n):
        weights = [5, 4, 3, 2, 1]
        return sum(
            w for i, w in enumerate(weights)
            if i < len(self.last_draws) and n in self.last_draws[-(i + 1)]
        )

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

    # ===================== SCORE ==============================

    def confirmed_score(self, item, e):
        n = int(item["number"])
        age = e - int(item["confirmed_e"])

        return (
            int(item.get("hits", 0)) * 20
            - age * 2
            - int(item.get("position", 99)) * 2
            + int(item.get("initial_lag", 0))
            + self.heat(n)
            + self.dominance(n, 6) * 3
            + self.pressure(n)
        )

    def pick_ambata(self, hot_items, e):
        ranked = sorted(
            hot_items,
            key=lambda x: self.confirmed_score(x, e),
            reverse=True
        )

        return int(ranked[0]["number"]) if ranked else None

    def pick_jolly(self, used_numbers):
        candidates = []

        for n in range(1, 91):
            if n in used_numbers:
                continue

            score = (
                self.heat(n) * 2
                + self.dominance(n, 6) * 3
                + self.pressure(n)
                - self.lag(n)
            )

            candidates.append({
                "number": n,
                "score": score,
                "heat": self.heat(n),
                "lag": self.lag(n),
                "dominance": self.dominance(n, 6),
                "pressure": self.pressure(n)
            })

        candidates.sort(key=lambda x: (-x["score"], x["lag"], x["number"]))
        return candidates[0]

    # ===================== PLAY BUILDER =======================

    def build_cluster_plus_play(self, e):
        hot_items = [
            x for x in self.hot_confirmed.values()
            if 0 <= e - int(x["confirmed_e"]) <= HOT_TTL
        ]

        if len(hot_items) < MIN_HOT_ACTIVE:
            return None

        pair_candidates = []

        for a, b in combinations(hot_items, 2):
            age_a = e - int(a["confirmed_e"])
            age_b = e - int(b["confirmed_e"])
            age_gap = abs(int(a["confirmed_e"]) - int(b["confirmed_e"]))
            avg_age = (age_a + age_b) / 2

            pair = tuple(sorted((int(a["number"]), int(b["number"]))))

            score = (
                self.confirmed_score(a, e)
                + self.confirmed_score(b, e)
                - age_gap * 3
                - avg_age
            )

            pair_candidates.append({
                "ambo": pair,
                "score": round(score, 2),
                "age_gap": age_gap,
                "avg_age": round(avg_age, 2),
                "a": a,
                "b": b
            })

        pair_candidates.sort(key=lambda x: (-x["score"], x["age_gap"], x["avg_age"]))

        ambi = []
        used_pairs = set()

        for p in pair_candidates:
            if p["ambo"] in used_pairs:
                continue

            used_pairs.add(p["ambo"])
            ambi.append(p)

            if len(ambi) >= MAX_AMBI_PER_PLAY:
                break

        if not ambi:
            return None

        used_numbers = set()
        for item in ambi:
            used_numbers.update(item["ambo"])

        ambata = self.pick_ambata(hot_items, e)
        jolly = self.pick_jolly(used_numbers)

        terni = []
        for item in ambi:
            a, b = item["ambo"]
            terni.append(tuple(sorted((a, b, int(jolly["number"])))))

        return {
            "reason": "CLUSTER_PLUS_AMBATA_AMBI_TERNI",
            "start_e": e + 1,
            "valid_to": e + MAX_COLPI,
            "max_colpi": MAX_COLPI,
            "ambata": ambata,
            "jolly": jolly,
            "ambi": ambi,
            "terni": terni,
            "hot_count": len(hot_items),
            "hot_numbers": [
                {
                    "number": int(x["number"]),
                    "confirmed_e": int(x["confirmed_e"]),
                    "age": e - int(x["confirmed_e"]),
                    "hits": int(x.get("hits", 0)),
                    "position": int(x.get("position", 99)),
                    "initial_lag": int(x.get("initial_lag", 0)),
                    "score": round(self.confirmed_score(x, e), 2)
                }
                for x in hot_items
            ]
        }

    # ===================== CHECK ==============================

    def check_hit(self, nums):
        s = set(nums)
        snap = self.active_snapshot

        ambata_hit = snap["ambata"] in s

        ambi_hit = []
        for item in snap["ambi"]:
            a, b = item["ambo"]
            if a in s and b in s:
                ambi_hit.append(item)

        terni_hit = []
        for t in snap["terni"]:
            if all(n in s for n in t):
                terni_hit.append(t)

        return {
            "ambata_hit": ambata_hit,
            "ambi_hit": ambi_hit,
            "terni_hit": terni_hit
        }

    # ===================== STATS ==============================

    def ambo_hitrate(self):
        if self.total_play == 0:
            return 0.0
        return round((self.total_hit_ambo / self.total_play) * 100, 2)

    def register_play(self, snapshot):
        self.total_play += 1
        self.play_log.append({
            "event": "PLAY_CLUSTER_PLUS",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **snapshot
        })
        self.play_log = self.play_log[-800:]

    def register_hit(self, colpo, nums, hit_data):
        if hit_data["ambata_hit"]:
            self.total_hit_ambata += 1

        if hit_data["ambi_hit"]:
            self.total_hit_ambo += 1

        if hit_data["terni_hit"]:
            self.total_hit_terno += 1

        self.recent_results.append("HIT")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "HIT_CLUSTER_PLUS",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "colpo": colpo,
            "draw": nums,
            "hit_data": hit_data,
            "snapshot": self.active_snapshot
        })
        self.play_log = self.play_log[-800:]

    def register_stop(self):
        self.total_stop += 1
        self.recent_results.append("STOP")
        self.recent_results = self.recent_results[-50:]

        self.play_log.append({
            "event": "STOP_CLUSTER_PLUS",
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
            hit_data = self.check_hit(nums)

            ambi_txt = ", ".join(
                f"{a}-{b}" for h in hit_data["ambi_hit"] for a, b in [h["ambo"]]
            ) or "nessuno"

            terni_txt = ", ".join(
                "-".join(map(str, t)) for t in hit_data["terni_hit"]
            ) or "nessuno"

            await self.tg(
                app,
                f"🔎 CHECK v45 | colpo {self.colpi}/{MAX_COLPI}\n"
                f"• ambata {self.active_snapshot['ambata']} = {'SI' if hit_data['ambata_hit'] else 'NO'}\n"
                f"• ambi usciti = {ambi_txt}\n"
                f"• terni usciti = {terni_txt}"
            )

            if hit_data["ambata_hit"] or hit_data["ambi_hit"] or hit_data["terni_hit"]:
                self.register_hit(self.colpi, nums, hit_data)

                await self.tg(
                    app,
                    f"🔥 HIT v45 CLUSTER PLUS | colpo {self.colpi}\n"
                    f"• ambata = {'SI' if hit_data['ambata_hit'] else 'NO'}\n"
                    f"• ambi = {ambi_txt}\n"
                    f"• terni = {terni_txt}\n\n"
                    f"📊 STATS v45\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit ambata = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• hit terno = {self.total_hit_terno}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• ambo hitrate = {self.ambo_hitrate()}%"
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
                    f"🛑 STOP v45 | {MAX_COLPI} colpi\n"
                    f"📊 STATS v45\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit ambata = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• hit terno = {self.total_hit_terno}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• ambo hitrate = {self.ambo_hitrate()}%"
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

        if new_confirmed:
            nc_txt = ", ".join(
                f"{x['number']} pos{x['position']} lag{x['initial_lag']} hits{x['hits']}"
                for x in new_confirmed
            )

            await self.tg(
                app,
                f"🔥 RIENTRO CONFERMATO v45\n"
                f"• nuovi confermati = {nc_txt}\n"
                f"• hot attivi = {len(self.hot_confirmed)}"
            )

            play = self.build_cluster_plus_play(e)

            if play:
                self.active = True
                self.colpi = 0
                self.active_snapshot = play
                self.register_play(play)

                ambi_txt = ", ".join(
                    f"{a}-{b}" for item in play["ambi"] for a, b in [item["ambo"]]
                )

                terni_txt = ", ".join(
                    "-".join(map(str, t)) for t in play["terni"]
                )

                hot_txt = ", ".join(
                    f"{x['number']}@age{x['age']}/score{x['score']}"
                    for x in play["hot_numbers"]
                )

                await self.tg(
                    app,
                    "🎯 PLAY v45 CLUSTER PLUS\n"
                    f"🔥 AMBATA FORTE = {play['ambata']}\n"
                    f"✅ AMBI = {ambi_txt}\n"
                    f"🎲 JOLLY TERNO = {play['jolly']['number']} "
                    f"(score {play['jolly']['score']})\n"
                    f"💥 TERNI = {terni_txt}\n"
                    f"• hot attivi = {play['hot_count']}\n"
                    f"• hot list = {hot_txt}\n"
                    f"• max_colpi = {MAX_COLPI}\n"
                    f"• valido da = {play['start_e']}"
                )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v45 CLUSTER PLUS\n"
            f"• play totali = {self.total_play}\n"
            f"• hit ambata = {self.total_hit_ambata}\n"
            f"• hit ambo = {self.total_hit_ambo}\n"
            f"• hit terno = {self.total_hit_terno}\n"
            f"• stop = {self.total_stop}\n"
            f"• ambo hitrate = {self.ambo_hitrate()}%"
        )


# ===================== LOOP ================================

bot = SNIPER_V45_CLUSTER_PLUS()


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
            "🚀 SNIPER v45 CLUSTER PLUS AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• osservo prossime estrazioni reali"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v45 CLUSTER PLUS RIAVVIATO\n"
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
            await bot.tg(app, f"⚠️ Errore loop v45: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
