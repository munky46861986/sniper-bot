# ============================================================
# 🚀 SNIPER v41 — RITARDATARI → RIENTRO → FREQUENTE
# Logica:
# 1) calcola top 10 ritardatari
# 2) osserva posizioni 6-7-8-9-10
# 3) se un numero rientra = WATCH
# 4) se rientra ancora entro 10 colpi = diventa FREQUENTE
# 5) manda PLAY CORE ritardatari-frequenti
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

STATE_FILE = "sniper_v41_ritardatari_frequenti_state.json"

LOOP_SEC = 60
HISTORY_MAX = 240
PROCESSED_MAX = 1000

TOP_RITARDATARI = 10
PLAY_POSITIONS = [6, 7, 8, 9, 10]

WATCH_WINDOW = 10
MAX_COLPI = 10

MIN_PLAY_NUMBERS = 3
MAX_PLAY_NUMBERS = 5


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


class SNIPER_V41_RITARDATARI:

    def __init__(self):
        self.version = "v41_ritardatari_rientro_frequente"

        self.day = day_key()
        self.max_e = 0
        self.last_fp = None
        self.last_draws = []

        self.processed_ids = []
        self.processed_fps = []

        self.watch = {}
        self.frequenti = {}

        self.active = False
        self.colpi = 0
        self.active_snapshot = None

        self.total_play = 0
        self.total_hit = 0
        self.total_stop = 0

        self.hit_2 = 0
        self.hit_3 = 0
        self.hit_4 = 0
        self.hit_5 = 0

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
            "frequenti": self.frequenti,
            "active": self.active,
            "colpi": self.colpi,
            "active_snapshot": self.active_snapshot,
            "total_play": self.total_play,
            "total_hit": self.total_hit,
            "total_stop": self.total_stop,
            "hit_2": self.hit_2,
            "hit_3": self.hit_3,
            "hit_4": self.hit_4,
            "hit_5": self.hit_5,
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
            self.frequenti = data.get("frequenti", {})

            self.active = bool(data.get("active", False))
            self.colpi = int(data.get("colpi", 0))
            self.active_snapshot = data.get("active_snapshot")

            self.total_play = int(data.get("total_play", 0))
            self.total_hit = int(data.get("total_hit", 0))
            self.total_stop = int(data.get("total_stop", 0))

            self.hit_2 = int(data.get("hit_2", 0))
            self.hit_3 = int(data.get("hit_3", 0))
            self.hit_4 = int(data.get("hit_4", 0))
            self.hit_5 = int(data.get("hit_5", 0))

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

            subprocess.run(["git", "commit", "-m", "update sniper v41 ritardatari state"], check=False)
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

    # ===================== RITARDI ============================

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

    # ===================== WATCH / FREQUENTE ==================

    def clean_old_watch(self, current_e):
        remove = []

        for n, data in self.watch.items():
            age = current_e - int(data["first_e"])
            if age > WATCH_WINDOW:
                remove.append(n)

        for n in remove:
            self.watch.pop(n, None)

    def update_watch(self, e, nums, selected):
        s = set(nums)
        selected_numbers = [x["number"] for x in selected]

        new_frequenti = []

        for item in selected:
            n = item["number"]
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
                    self.frequenti[key] = {
                        **self.watch[key],
                        "confirmed_e": e
                    }

                    new_frequenti.append({
                        "number": n,
                        "position": self.watch[key]["position"],
                        "initial_lag": self.watch[key]["initial_lag"],
                        "hits": self.watch[key]["hits"],
                        "first_e": self.watch[key]["first_e"],
                        "confirmed_e": e
                    })

        self.clean_old_watch(e)
        return new_frequenti

    def build_play_from_frequenti(self, e):
        if len(self.frequenti) < MIN_PLAY_NUMBERS:
            return None

        items = list(self.frequenti.values())

        items.sort(
            key=lambda x: (
                -int(x.get("hits", 0)),
                int(x.get("position", 99)),
                -int(x.get("initial_lag", 0))
            )
        )

        chosen = items[:MAX_PLAY_NUMBERS]
        numbers = [int(x["number"]) for x in chosen]

        if len(numbers) < MIN_PLAY_NUMBERS:
            return None

        return {
            "reason": "RITARDATARI_RIENTRO_CONFERMA_FREQUENTE",
            "start_e": e + 1,
            "valid_to": e + MAX_COLPI,
            "numbers": numbers,
            "details": chosen
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

    def check_hit(self, nums):
        s = set(nums)
        play_nums = self.active_snapshot["numbers"]
        usciti = [n for n in play_nums if n in s]

        return {
            "usciti": usciti,
            "count": len(usciti)
        }

    def register_hit(self, colpo, nums, hit_data):
        self.total_hit += 1

        c = hit_data["count"]

        if c == 2:
            self.hit_2 += 1
        elif c == 3:
            self.hit_3 += 1
        elif c == 4:
            self.hit_4 += 1
        elif c >= 5:
            self.hit_5 += 1

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

        # ===================== PLAY ATTIVO =====================

        if self.active:
            self.colpi += 1

            hit_data = self.check_hit(nums)
            usciti_txt = ", ".join(map(str, hit_data["usciti"])) or "nessuno"

            await self.tg(
                app,
                f"🔎 CHECK v41 RITARDATARI | colpo {self.colpi}/{MAX_COLPI}\n"
                f"• numeri giocati = {', '.join(map(str, self.active_snapshot['numbers']))}\n"
                f"• usciti = {hit_data['count']}/{len(self.active_snapshot['numbers'])} → {usciti_txt}"
            )

            if hit_data["count"] >= 3:
                self.register_hit(self.colpi, nums, hit_data)

                await self.tg(
                    app,
                    f"🔥 HIT v41 RITARDATARI-FREQUENTI | colpo {self.colpi}\n"
                    f"🎯 Risultato = {hit_data['count']}/{len(self.active_snapshot['numbers'])}\n"
                    f"✅ Usciti = {usciti_txt}\n\n"
                    f"📊 STATS v41\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• 2 = {self.hit_2}\n"
                    f"• 3 = {self.hit_3}\n"
                    f"• 4 = {self.hit_4}\n"
                    f"• 5 = {self.hit_5}"
                )

                self.active = False
                self.colpi = 0
                self.active_snapshot = None
                self.frequenti = {}
                self.watch = {}
                self.save_state()
                return

            if self.colpi >= MAX_COLPI:
                self.register_stop()

                await self.tg(
                    app,
                    f"🛑 STOP v41 RITARDATARI | {MAX_COLPI} colpi\n"
                    f"📊 STATS v41\n"
                    f"• play totali = {self.total_play}\n"
                    f"• hit = {self.total_hit}\n"
                    f"• stop = {self.total_stop}\n"
                    f"• hitrate = {self.hitrate()}%\n"
                    f"• stop streak = {self.consecutive_stops()}"
                )

                self.active = False
                self.colpi = 0
                self.active_snapshot = None
                self.frequenti = {}
                self.watch = {}
                self.save_state()
                return

            self.save_state()
            return

        # ===================== OSSERVAZIONE RITARDATARI ========

        if len(self.last_draws) < 30:
            self.save_state()
            return

        top10, selected = self.selected_ritardatari()
        nuovi_frequenti = self.update_watch(e, nums, selected)

        top10_txt = ", ".join(
            f"{i+1}:{x['number']}({x['lag']})"
            for i, x in enumerate(top10)
        )

        selected_txt = ", ".join(
            f"pos{x['position']}={x['number']} lag{x['lag']}"
            for x in selected
        )

        if nuovi_frequenti:
            nf_txt = ", ".join(
                f"{x['number']} pos{x['position']} lag{x['initial_lag']} hits{x['hits']}"
                for x in nuovi_frequenti
            )

            await self.tg(
                app,
                f"🔥 RIENTRO CONFERMATO v41\n"
                f"• nuovi frequenti = {nf_txt}\n"
                f"• top10 ritardatari = {top10_txt}\n"
                f"• zona osservata = {selected_txt}"
            )

        play = self.build_play_from_frequenti(e)

        if not play:
            self.save_state()
            return

        self.active = True
        self.colpi = 0
        self.active_snapshot = play

        self.register_play(play)

        details_txt = ", ".join(
            f"{x['number']}[pos{x['position']}/lag{x['initial_lag']}/hits{x['hits']}]"
            for x in play["details"]
        )

        await self.tg(
            app,
            "🎯 PLAY v41 RITARDATARI → FREQUENTI\n"
            f"• logica = rientro + conferma entro {WATCH_WINDOW} colpi\n"
            f"• numeri = {', '.join(map(str, play['numbers']))}\n"
            f"• valido da = {play['start_e']}\n"
            f"• max_colpi = {MAX_COLPI}\n"
            f"• dettagli = {details_txt}\n\n"
            f"📊 STATS v41\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%"
        )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT v41 RITARDATARI-FREQUENTI\n"
            f"• play totali = {self.total_play}\n"
            f"• hit = {self.total_hit}\n"
            f"• stop = {self.total_stop}\n"
            f"• hitrate = {self.hitrate()}%\n"
            f"• 2 = {self.hit_2}\n"
            f"• 3 = {self.hit_3}\n"
            f"• 4 = {self.hit_4}\n"
            f"• 5 = {self.hit_5}\n"
            f"• watch attivi = {len(self.watch)}\n"
            f"• frequenti attivi = {len(self.frequenti)}"
        )


# ===================== LOOP ================================

bot = SNIPER_V41_RITARDATARI()


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
            "🚀 SNIPER v41 RITARDATARI-FREQUENTI AVVIATO | LIVE_ONLY\n"
            f"• storico caricato fino estrazione {bot.max_e}\n"
            "• osservo prossime estrazioni reali"
        )
    else:
        await bot.tg(
            app,
            "🚀 SNIPER v41 RITARDATARI-FREQUENTI RIAVVIATO\n"
            f"• max_e state = {bot.max_e}\n"
            f"• active = {bot.active}\n"
            f"• watch attivi = {len(bot.watch)}\n"
            f"• frequenti attivi = {len(bot.frequenti)}"
        )

    while True:
        try:
            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore loop v41: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
