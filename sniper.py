# ============================================================
# 🚀 SNIPER v27.1c — CONVERSION FLOW ENGINE ULTRA PATCHED
# v27.1b + patch profonde dai log reali
# PATCH TECH: dedup / supporti più severi / filtro 15 isolato
# / anti-stop seriale / early stop play deboli
# ============================================================

import asyncio
import requests
import re
import csv
import os
from datetime import datetime
from collections import defaultdict
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

# ===================== CONFIG ===============================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN mancante")

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TARGET = [5, 10, 15, 50]

MAX_COLPI_NORMAL = 3
MAX_COLPI_SUPER = 2
MAX_COLPI_RESTART = 2

LOOP_SEC = 60
HISTORY_MAX = 160

WARMUP_WINDOW = 60
PROFILE_UPDATE_EVERY = 10

LOG_DIR = "logs"
PLAY_LOG_CSV = os.path.join(LOG_DIR, "sniper_play_log.csv")
SHOT_LOG_CSV = os.path.join(LOG_DIR, "sniper_shot_log.csv")

# ===================== BASE WEIGHTS =========================

W_HEAT = 1.8
W_LAG = 0.6
W_DOMINANCE = 2.8

W_GAP_ACTIVE = 1.2
W_GAP_RISK = -3.0
W_GAP_RESTART = 3.0

W_PENALTY_10 = -3.0
W_OVERPLAY = -2.0

MIN_SCORE_NORMAL = 5.8
MIN_DIFF_SCORE = 1.5
MIN_SCORE_RESTART = 4.8

LOW_PRESSURE_BLOCK = 4.0

# core logic
W_CORE_5_TO_15 = 2.6
W_CORE_15_TO_5 = 1.9
W_SIDE_15_TO_50 = 1.0
W_SIDE_5_TO_10 = 0.8
W_SIDE_10_TO_15 = 1.6

W_PRESENCE_LEADER = 1.2
W_PRESENCE_SECOND = 0.5
W_PRESENCE_WEAK = -1.0

W_CONVERSION_LEADER = 2.4
W_CONVERSION_SECOND = 1.0
W_CONVERSION_WEAK = -1.2

W_PERSISTENCE = 1.0

W_STATE_DENSE_15 = 1.7
W_STATE_DENSE_5 = 0.9
W_STATE_FLOW_15 = 1.6
W_STATE_FLOW_5 = 0.5
W_STATE_THIN_50 = 0.5
W_STATE_RESTART_50 = 2.8
W_STATE_RESTART_15 = 1.2

W_BONUS_5_LIVE = 1.1
W_BONUS_15_CONVERT = 1.5

W_PENALTY_50_ACTIVE = -2.2
W_PENALTY_50_THIN = -0.8

PAIR_WEIGHT = 0.4

# nuovi filtri
MIN_LIFE_BIAS_15 = 2.2
MIN_LIFE_BIAS_50 = 3.0
MIN_SUPER_SUPPORT = 4.5

# patch segnali / anti-stop
ALIVE_HEAT_MIN = 2
ALIVE_LAG_MAX = 6
ALIVE_DOM_MIN = 1

STRONG_ALIVE_HEAT = 3
STRONG_ALIVE_LAG = 5

ISOLATED_15_SCORE_PENALTY = 4.2
STRUCTURAL_ONLY_15_PENALTY = 3.2
REENTRY_15_AFTER_STOP_BLOCK = 2

SECOND_SHOT_EARLY_STOP_PRESSURE = 9.0
SECOND_SHOT_WEAK_LIFE_MAX = 3.8

MAX_RECENT_DRAWS_IDS = 20

# ============================================================

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

# ============================================================

class SNIPER271:

    def __init__(self):
        self.max_e = 0
        self.last_draws = []

        self.A = None
        self.S1 = None
        self.S2 = None
        self.start = None
        self.colpi = 0
        self.max_colpi_cycle = MAX_COLPI_NORMAL
        self.mode = None

        self.recent_results = []
        self.last_play_numbers = []

        self.profile = {}
        self.draws_since_profile_update = 0
        self.leader_presence_history = []
        self.leader_conversion_history = []

        self.play_id = 0
        self.active_play_id = None
        self.active_play_meta = {}

        self.recent_extraction_ids = []
        self.last_stop_number = None
        self.last_stop_count_same = 0

        os.makedirs(LOG_DIR, exist_ok=True)
        self._init_csv_logs()

    # ===================== DIAGNOSTICA =======================

    def _init_csv_logs(self):
        if not os.path.exists(PLAY_LOG_CSV):
            with open(PLAY_LOG_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "ts", "play_id", "open_extraction", "mode",
                    "ambata", "ambo1", "ambo2",
                    "state", "pressure", "gap",
                    "heat_5", "heat_10", "heat_15", "heat_50",
                    "lag_5", "lag_10", "lag_15", "lag_50",
                    "dom_5", "dom_10", "dom_15", "dom_50",
                    "leader_presence", "leader_conversion",
                    "support_quality", "result"
                ])

        if not os.path.exists(SHOT_LOG_CSV):
            with open(SHOT_LOG_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "ts", "play_id", "eval_extraction", "colpo",
                    "ambata", "ambo1", "ambo2",
                    "hit_ambata", "hit_ambo1", "hit_ambo2"
                ])

    def _now_str(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _current_metrics(self):
        return {
            "pressure": round(self.cluster_pressure(), 2),
            "gap": self.cluster_gap(),
            "state": self.profile.get("state", "n/a") if self.profile else "n/a",
            "leader_presence": self.profile.get("leader_presence", "n/a") if self.profile else "n/a",
            "leader_conversion": self.profile.get("leader_conversion", "n/a") if self.profile else "n/a",
            "heat_5": self.heat(5),
            "heat_10": self.heat(10),
            "heat_15": self.heat(15),
            "heat_50": self.heat(50),
            "lag_5": self.lag(5),
            "lag_10": self.lag(10),
            "lag_15": self.lag(15),
            "lag_50": self.lag(50),
            "dom_5": self.dominance_count(5, 6),
            "dom_10": self.dominance_count(10, 6),
            "dom_15": self.dominance_count(15, 6),
            "dom_50": self.dominance_count(50, 6),
        }

    def support_score(self, ambata, n):
        if n is None:
            return -999.0

        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance_count(n, 6)

        pair_component = self.pair_score(ambata, n)
        rot_component = self.transition_score(ambata, n) + self.transition_score(n, ambata)

        score = 0.0
        score += h * 1.2
        score -= l * 0.35
        score += d * 1.2
        score += pair_component * 0.9
        score += rot_component * 0.25

        return round(score, 2)

    def support_quality_label(self, ambata, s1, s2):
        if s1 is None and s2 is None:
            return "NO_SUPPORTS"

        scores = []
        supports = []

        for s in [s1, s2]:
            if s is None:
                continue
            supports.append(s)
            scores.append(self.support_alive_score(ambata, s))

        if not scores:
            return "NO_SUPPORTS"

        strong = sum(1 for x in scores if x >= 5.8)
        medium = sum(1 for x in scores if x >= 3.8)
        weak = sum(1 for x in scores if x < 2.2)

        if ambata == 15:
            alive_supports = sum(1 for s in supports if self.is_semi_alive(s))

            if alive_supports >= 2 and strong >= 1:
                return "SUPPORTS_GOOD"
            if alive_supports >= 1 and (medium >= 1 or strong >= 1):
                return "SUPPORTS_MIXED"
            return "SUPPORTS_WEAK"

        if strong >= 2:
            return "SUPPORTS_GOOD"
        if strong >= 1 or medium >= 2:
            return "SUPPORTS_MIXED"
        if weak == len(scores):
            return "SUPPORTS_WEAK"
        return "SUPPORTS_MIXED"

    def open_play_log(self, extraction_open, mode, ambata, ambo1, ambo2):
        self.play_id += 1
        self.active_play_id = self.play_id

        m = self._current_metrics()
        support_quality = self.support_quality_label(ambata, ambo1, ambo2)

        self.active_play_meta = {
            "open_extraction": extraction_open,
            "mode": mode,
            "ambata": ambata,
            "ambo1": ambo1,
            "ambo2": ambo2,
            "support_quality": support_quality,
            **m
        }

        with open(PLAY_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                self._now_str(),
                self.active_play_id,
                extraction_open,
                mode,
                ambata,
                ambo1,
                ambo2,
                m["state"],
                m["pressure"],
                m["gap"],
                m["heat_5"], m["heat_10"], m["heat_15"], m["heat_50"],
                m["lag_5"], m["lag_10"], m["lag_15"], m["lag_50"],
                m["dom_5"], m["dom_10"], m["dom_15"], m["dom_50"],
                m["leader_presence"], m["leader_conversion"],
                support_quality,
                "OPEN"
            ])

    def log_shot(self, eval_extraction, colpo, hit_ambata, hit_ambo1, hit_ambo2):
        if self.active_play_id is None:
            return

        with open(SHOT_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                self._now_str(),
                self.active_play_id,
                eval_extraction,
                colpo,
                self.A,
                self.S1,
                self.S2,
                int(hit_ambata),
                int(hit_ambo1),
                int(hit_ambo2)
            ])

    def close_play_log(self, result):
        if self.active_play_id is None:
            return

        m = self.active_play_meta

        with open(PLAY_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                self._now_str(),
                self.active_play_id,
                m.get("open_extraction"),
                m.get("mode"),
                m.get("ambata"),
                m.get("ambo1"),
                m.get("ambo2"),
                m.get("state"),
                m.get("pressure"),
                m.get("gap"),
                m.get("heat_5"), m.get("heat_10"), m.get("heat_15"), m.get("heat_50"),
                m.get("lag_5"), m.get("lag_10"), m.get("lag_15"), m.get("lag_50"),
                m.get("dom_5"), m.get("dom_10"), m.get("dom_15"), m.get("dom_50"),
                m.get("leader_presence"), m.get("leader_conversion"),
                m.get("support_quality"),
                result
            ])

        self.update_stop_memory(result)
        self.active_play_id = None
        self.active_play_meta = {}

    # ===================== TELEGRAM ==========================

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)
        await asyncio.sleep(0.15)

    # ===================== HISTORY ===========================

    def update_history(self, nums):
        self.last_draws.append(nums)
        if len(self.last_draws) > HISTORY_MAX:
            self.last_draws.pop(0)

    def push_result(self, result):
        self.recent_results.append(result)
        if len(self.recent_results) > 8:
            self.recent_results.pop(0)

    def push_play_number(self, n):
        self.last_play_numbers.append(n)
        if len(self.last_play_numbers) > 6:
            self.last_play_numbers.pop(0)

    # ===================== FEATURES ==========================

    def heat(self, n, draws=None):
        if draws is None:
            draws = self.last_draws

        weights = [5, 4, 3, 2, 1]
        h = 0
        for i, w in enumerate(weights):
            if i >= len(draws):
                break
            if n in draws[-(i + 1)]:
                h += w
        return h

    def lag(self, n, draws=None):
        if draws is None:
            draws = self.last_draws

        lag = 0
        for d in reversed(draws[:-1]):
            lag += 1
            if n in d:
                return lag
        return lag

    def cluster_gap(self, draws=None):
        if draws is None:
            draws = self.last_draws

        gap = 0
        for d in reversed(draws):
            if any(x in d for x in TARGET):
                return gap
            gap += 1
        return gap

    def dominance_count(self, n, window=6, draws=None):
        if draws is None:
            draws = self.last_draws
        recent = draws[-window:]
        return sum(1 for d in recent if n in d)

    def cluster_count_in_draw(self, nums):
        return len([x for x in nums if x in TARGET])

    def last_cluster_nums(self, draws=None):
        if draws is None:
            draws = self.last_draws
        if not draws:
            return []
        return [x for x in draws[-1] if x in TARGET]

    def cluster_pressure(self, draws=None):
        if draws is None:
            draws = self.last_draws

        if not draws:
            return 0.0

        weights = [5, 4, 3, 2, 1]
        score = 0.0
        for i, w in enumerate(weights):
            if i >= len(draws):
                break
            c = self.cluster_count_in_draw(draws[-(i + 1)])
            score += c * w
        return score

    def overplay_penalty(self, n):
        pen = 0.0

        if len(self.recent_results) >= 2 and self.recent_results[-2:] == ["STOP", "STOP"]:
            pen += abs(W_OVERPLAY)

        same_n = sum(1 for x in self.last_play_numbers[-3:] if x == n)
        if same_n >= 2:
            pen += 1.5

        if n == 50:
            same_50 = sum(1 for x in self.last_play_numbers[-2:] if x == 50)
            if same_50 >= 1:
                pen += 1.8

        return -pen

    def consecutive_stops(self):
        c = 0
        for r in reversed(self.recent_results):
            if r == "STOP":
                c += 1
            else:
                break
        return c

    def remember_extraction_id(self, e):
        self.recent_extraction_ids.append(e)
        if len(self.recent_extraction_ids) > MAX_RECENT_DRAWS_IDS:
            self.recent_extraction_ids.pop(0)

    def is_duplicate_extraction(self, e):
        return e in self.recent_extraction_ids

    def is_alive(self, n):
        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance_count(n, 6)
        return h >= ALIVE_HEAT_MIN and l <= ALIVE_LAG_MAX and d >= ALIVE_DOM_MIN

    def is_semi_alive(self, n):
        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance_count(n, 6)
        return (h >= ALIVE_HEAT_MIN and l <= ALIVE_LAG_MAX) or d >= 2

    def is_strong_alive(self, n):
        h = self.heat(n)
        l = self.lag(n)
        return h >= STRONG_ALIVE_HEAT and l <= STRONG_ALIVE_LAG

    def support_alive_score(self, ambata, n):
        if n is None:
            return -999.0

        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance_count(n, 6)
        ps = self.pair_score(ambata, n)
        ts = self.transition_score(ambata, n) + self.transition_score(n, ambata)

        score = 0.0
        score += h * 1.5
        score -= l * 0.45
        score += d * 1.1
        score += ps * 0.6
        score += ts * 0.18

        return round(score, 2)

    def should_block_15_isolated(self):
        h5 = self.heat(5)
        h50 = self.heat(50)
        l5 = self.lag(5)
        l50 = self.lag(50)
        d5 = self.dominance_count(5, 6)
        d50 = self.dominance_count(50, 6)
        p15_5 = self.pair_score(15, 5)
        p15_50 = self.pair_score(15, 50)

        alive_5 = (h5 >= 2 and l5 <= 6) or d5 >= 2 or (p15_5 >= 4 and h5 >= 1)
        alive_50 = (h50 >= 2 and l50 <= 6) or d50 >= 2 or (p15_50 >= 4 and h50 >= 1)

        return not (alive_5 or alive_50)

    def update_stop_memory(self, result):
        if self.A is None:
            return

        if result == "STOP":
            if self.last_stop_number == self.A:
                self.last_stop_count_same += 1
            else:
                self.last_stop_number = self.A
                self.last_stop_count_same = 1
        else:
            self.last_stop_number = None
            self.last_stop_count_same = 0

    # ===================== PROFILE ENGINE ====================

    def pair_score_raw(self, pair_counts, a, b):
        key = tuple(sorted((a, b)))
        return pair_counts.get(key, 0)

    def analyze_cluster_profile(self, draws=None):
        if draws is None:
            draws = self.last_draws

        window = draws[-WARMUP_WINDOW:] if len(draws) > WARMUP_WINDOW else draws[:]
        if not window:
            return {}

        freq = {n: 0.0 for n in TARGET}
        recent_tail = window[-20:] if len(window) >= 20 else window

        for d in window:
            w = 1.5 if d in recent_tail else 1.0
            for n in TARGET:
                if n in d:
                    freq[n] += w

        ranked_presence = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        leader_presence = ranked_presence[0][0]
        second_presence = ranked_presence[1][0]
        weak_presence = ranked_presence[-1][0]

        pressure_values = [self.cluster_count_in_draw(d) for d in window]
        avg_pressure = sum(pressure_values) / max(1, len(pressure_values))
        gap_now = self.cluster_gap(window)

        if gap_now >= 5:
            state = "RESTART"
        elif avg_pressure >= 1.55:
            state = "DENSE"
        elif avg_pressure >= 0.75:
            state = "FLOW"
        else:
            state = "THIN"

        transitions = defaultdict(int)
        prev_clusters = None
        for d in window:
            curr = [x for x in d if x in TARGET]
            if prev_clusters:
                for a in prev_clusters:
                    for b in curr:
                        if a != b:
                            transitions[(a, b)] += 1
            prev_clusters = curr if curr else prev_clusters

        top_transitions = sorted(transitions.items(), key=lambda x: x[1], reverse=True)[:8]

        pair_counts = defaultdict(int)
        for d in window:
            present = sorted([x for x in TARGET if x in d])
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    pair_counts[(present[i], present[j])] += 1

        top_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:6]
        best_pair = top_pairs[0][0] if top_pairs else None

        conversion_scores = {}
        recent_for_conversion = window[-25:] if len(window) >= 25 else window[:]

        for n in TARGET:
            h = self.heat(n, recent_for_conversion)
            dom = self.dominance_count(n, 6, recent_for_conversion)
            pair_component = 0.0
            for m in TARGET:
                if m != n:
                    ps = self.pair_score_raw(pair_counts, n, m)
                    if n == 15 or m == 15:
                        ps *= 1.4
                    pair_component += ps * PAIR_WEIGHT
            conversion_scores[n] = round(h + dom + pair_component, 2)

        ranked_conversion = sorted(conversion_scores.items(), key=lambda x: x[1], reverse=True)
        leader_conversion = ranked_conversion[0][0]
        second_conversion = ranked_conversion[1][0]
        weak_conversion = ranked_conversion[-1][0]

        self.leader_presence_history.append(leader_presence)
        self.leader_conversion_history.append(leader_conversion)

        if len(self.leader_presence_history) > 6:
            self.leader_presence_history.pop(0)
        if len(self.leader_conversion_history) > 6:
            self.leader_conversion_history.pop(0)

        presence_persistence = sum(1 for x in self.leader_presence_history if x == leader_presence)
        conversion_persistence = sum(1 for x in self.leader_conversion_history if x == leader_conversion)

        return {
            "window": len(window),
            "freq": freq,
            "ranked_presence": ranked_presence,
            "leader_presence": leader_presence,
            "second_presence": second_presence,
            "weak_presence": weak_presence,
            "conversion_scores": conversion_scores,
            "ranked_conversion": ranked_conversion,
            "leader_conversion": leader_conversion,
            "second_conversion": second_conversion,
            "weak_conversion": weak_conversion,
            "avg_pressure": round(avg_pressure, 2),
            "gap_now": gap_now,
            "state": state,
            "transitions": transitions,
            "top_transitions": top_transitions,
            "pair_counts": pair_counts,
            "top_pairs": top_pairs,
            "best_pair": best_pair,
            "presence_persistence": presence_persistence,
            "conversion_persistence": conversion_persistence,
        }

    def transition_score(self, a, b):
        if not self.profile or "transitions" not in self.profile:
            return 0
        return self.profile["transitions"].get((a, b), 0)

    def pair_score(self, a, b):
        if not self.profile or "pair_counts" not in self.profile:
            return 0
        key = tuple(sorted((a, b)))
        return self.profile["pair_counts"].get(key, 0)

    def regime_bonus(self, n):
        if not self.profile:
            return 0.0

        lp = self.profile["leader_presence"]
        sp = self.profile["second_presence"]
        wp = self.profile["weak_presence"]

        lc = self.profile["leader_conversion"]
        sc = self.profile["second_conversion"]
        wc = self.profile["weak_conversion"]

        state = self.profile["state"]
        conversion_persistence = self.profile.get("conversion_persistence", 1)

        bonus = 0.0

        if n == lp:
            bonus += W_PRESENCE_LEADER
        elif n == sp:
            bonus += W_PRESENCE_SECOND
        if n == wp:
            bonus += W_PRESENCE_WEAK

        conv_leader_bonus = W_CONVERSION_LEADER
        conv_second_bonus = W_CONVERSION_SECOND
        conv_weak_bonus = W_CONVERSION_WEAK

        if lc == 10:
            conv_leader_bonus = 1.4
            conv_second_bonus = 1.2

        if n == lc:
            bonus += conv_leader_bonus
        elif n == sc:
            bonus += conv_second_bonus

        if n == wc:
            bonus += conv_weak_bonus

        if conversion_persistence >= 3 and n == lc:
            bonus += W_PERSISTENCE

        if state == "DENSE":
            if n == 15:
                bonus += W_STATE_DENSE_15
            if n == 5:
                bonus += W_STATE_DENSE_5
            if n == 50:
                bonus -= 1.0

        elif state == "FLOW":
            if n == 15:
                bonus += W_STATE_FLOW_15
            if n == 5:
                bonus += W_STATE_FLOW_5

        elif state == "THIN":
            if n == 50:
                bonus += W_STATE_THIN_50
            if n == 10:
                bonus -= 0.8

        elif state == "RESTART":
            if n == 50:
                bonus += W_STATE_RESTART_50
            if n == 15:
                bonus += W_STATE_RESTART_15

        return bonus

    # ===================== ROTATION ENGINE ===================

    def core_rotation_bonus(self, n):
        if not self.last_draws:
            return 0.0

        last_cluster = self.last_cluster_nums()
        bonus = 0.0

        if 5 in last_cluster and n == 15:
            bonus += W_CORE_5_TO_15
        if 15 in last_cluster and n == 5:
            bonus += W_CORE_15_TO_5

        if 15 in last_cluster and n == 50:
            bonus += W_SIDE_15_TO_50
        if 5 in last_cluster and n == 10:
            bonus += W_SIDE_5_TO_10
        if 10 in last_cluster and n == 15:
            bonus += W_SIDE_10_TO_15

        for a in last_cluster:
            ts = self.transition_score(a, n)
            if ts >= 7:
                bonus += 1.5
            elif ts >= 4:
                bonus += 0.7

        return bonus

    def pair_bonus_for_ambata(self, n):
        if not self.profile:
            return 0.0

        pair_sum = 0.0
        for m in TARGET:
            if m != n:
                ps = self.pair_score(n, m)
                if n == 15 or m == 15:
                    ps *= 1.4
                pair_sum += ps

        return round(pair_sum * PAIR_WEIGHT / 10.0, 2)

    # ===================== SUPPORTS ==========================

    def supports_for_ambata(self, a):
        pressure = self.cluster_pressure()

        if a == 15:
            score_50 = self.support_alive_score(15, 50)
            score_5 = self.support_alive_score(15, 5)

            alive_50 = self.is_semi_alive(50)
            alive_5 = self.is_semi_alive(5)

            if pressure >= 16 and alive_50 and alive_5 and score_50 >= 4.0 and score_5 >= 4.0:
                if score_50 >= score_5:
                    return 50, 5
                return 5, 50

            if alive_50 and not alive_5:
                return 50, None

            if alive_5 and not alive_50:
                return 5, None

            if alive_50 and alive_5:
                if score_50 >= score_5 + 1.0:
                    return 50, 5 if pressure >= 14 and score_5 >= 4.0 else None
                if score_5 >= score_50 + 1.0:
                    return 5, 50 if pressure >= 14 and score_50 >= 4.0 else None

                if self.heat(50) > self.heat(5):
                    return 50, 5 if pressure >= 15 else None
                return 5, 50 if pressure >= 15 else None

            return None, None

        if a == 50:
            s15 = self.support_alive_score(50, 15)
            s5 = self.support_alive_score(50, 5)

            if s5 >= s15:
                s1 = 5
                s2 = 15 if s15 >= 3.8 and pressure >= 11 else None
            else:
                s1 = 15
                s2 = 5 if s5 >= 3.8 and pressure >= 11 else None
            return s1, s2

        if a == 5:
            s10 = self.support_alive_score(5, 10)
            s15 = self.support_alive_score(5, 15)
            s50 = self.support_alive_score(5, 50)

            s1 = 10 if s10 >= s15 else 15
            s2 = 50 if s50 >= 4.2 and pressure >= 11 else None
            return s1, s2

        if a == 10:
            return 15, None

        return None, None

    # ===================== MOMENTUM ==========================

    def super_momentum_target_smart(self, cluster_nums):
        s = set(cluster_nums)
        if len(s) < 3:
            return None, "NO_TRIGGER"

        missing = [x for x in TARGET if x not in s]
        if len(missing) != 1:
            return None, "INVALID_MISSING"

        missing = missing[0]
        pressure = self.cluster_pressure()
        state = self.profile.get("state", "FLOW") if self.profile else "FLOW"
        leader_conv = self.profile.get("leader_conversion", missing) if self.profile else missing

        pair_support = sum(self.pair_score(missing, a) for a in s)

        s1, _ = self.supports_for_ambata(missing)
        support_ok = s1 is not None and self.support_alive_score(missing, s1) >= MIN_SUPER_SUPPORT

        if missing == 15 and self.should_block_15_isolated():
            return None, "MISSING_15_ISOLATED"

        if pressure >= 6 and state != "THIN" and pair_support >= 3 and support_ok:
            return missing, "MISSING_OK"

        if leader_conv == 10 and pressure < 8:
            return None, "CONV10_NOT_STRONG_ENOUGH"

        if leader_conv != missing and leader_conv in TARGET:
            if leader_conv == 15 and self.should_block_15_isolated():
                return None, "LEADER_15_ISOLATED"

            if leader_conv in s and pressure < 9:
                return None, "LEADER_INSIDE_TRIGGER"

            s1, _ = self.supports_for_ambata(leader_conv)
            if s1 is not None and self.support_alive_score(leader_conv, s1) >= MIN_SUPER_SUPPORT:
                return leader_conv, "CONVERSION_FALLBACK"

        return None, "NO_SUPER_PLAY"

    # ===================== RESTART MODE ======================

    def choose_restart_play(self):
        gap = self.cluster_gap()
        pressure = self.cluster_pressure()
        state = self.profile.get("state", "FLOW") if self.profile else "FLOW"

        if state != "RESTART" or gap < 5:
            return None, [], "NOT_RESTART"

        rows = []
        priority = {50: 3.0, 15: 2.0, 5: 1.0, 10: 0.0}

        if self.pair_score(15, 50) >= 5:
            priority[15] = 3.2
            priority[50] = 2.6

        for n in TARGET:
            h = self.heat(n)
            l = self.lag(n)
            dom = self.dominance_count(n, 6)
            reg = self.regime_bonus(n)
            pairb = self.pair_bonus_for_ambata(n)
            over = self.overplay_penalty(n)

            if l <= 1:
                continue

            score = 0.0
            score += priority[n]
            score += h * 1.2
            score -= l * 0.35
            score += reg
            score += pairb
            score += over

            if dom >= 2:
                score += 1.0

            if n == 50:
                score += 2.0
            elif n == 15:
                score += 1.2

            rows.append({
                "n": n,
                "score": round(score, 2),
                "heat": h,
                "lag": l,
                "dom": dom,
                "gap": gap,
                "pressure": round(pressure, 2),
                "reg": round(reg, 2),
                "pair": round(pairb, 2),
                "over": round(over, 2),
                "state": state,
                "structure_bias": round(reg + pairb, 2),
                "life_bias": round((h * 1.2) - (l * 0.35) + (1.0 if dom >= 2 else 0.0), 2),
            })

        rows = sorted(rows, key=lambda x: x["score"], reverse=True)

        if not rows:
            return None, rows, "NO_ROWS"

        if rows[0]["score"] < MIN_SCORE_RESTART:
            return None, rows, "LOW_RESTART_SCORE"

        if rows[0]["n"] == 50 and rows[0]["life_bias"] < 2.5:
            return None, rows, "RESTART_50_WEAK_LIFE"

        return rows[0]["n"], rows, "OK"

    # ===================== PROFILE MESSAGES ==================

    async def send_profile(self, app, title="🧠 WARMUP ANALYSIS"):
        if not self.profile:
            return

        presence_txt = "\n".join([f"{n} = {round(c,1)}" for n, c in self.profile["ranked_presence"]])
        conv_txt = "\n".join([f"{n} = {c}" for n, c in self.profile["ranked_conversion"]])

        trans_txt = "\n".join(
            [f"{a} → {b} = {c}" for (a, b), c in self.profile["top_transitions"][:5]]
        ) if self.profile["top_transitions"] else "n/a"

        pair_txt = "\n".join(
            [f"{a}-{b} = {c}" for (a, b), c in self.profile["top_pairs"][:5]]
        ) if self.profile["top_pairs"] else "n/a"

        await self.tg(
            app,
            f"{title}\n\n"
            f"• draws analyzed = {self.profile['window']}\n"
            f"• leader_presence = {self.profile['leader_presence']}\n"
            f"• leader_conversion = {self.profile['leader_conversion']}\n"
            f"• weak_presence = {self.profile['weak_presence']}\n"
            f"• weak_conversion = {self.profile['weak_conversion']}\n"
            f"• state = {self.profile['state']}\n"
            f"• avg_pressure = {self.profile['avg_pressure']}\n"
            f"• conv_persistence = {self.profile['conversion_persistence']}\n\n"
            f"📊 PRESENCE\n{presence_txt}\n\n"
            f"🎯 CONVERSION\n{conv_txt}\n\n"
            f"🔄 TOP ROTATIONS\n{trans_txt}\n\n"
            f"💥 TOP PAIRS\n{pair_txt}"
        )

    # ===================== NORMAL SCORING ====================

    def choose_ambata_normal(self):
        gap = self.cluster_gap()
        pressure = self.cluster_pressure()
        state = self.profile.get("state", "FLOW") if self.profile else "FLOW"

        if gap == 2:
            return None, [], "GAP_2_BLOCK"

        if pressure < LOW_PRESSURE_BLOCK and state != "RESTART":
            return None, [], "LOW_PRESSURE"

        rows = []

        for n in TARGET:
            h = self.heat(n)
            l = self.lag(n)
            dom = self.dominance_count(n, 6)
            rot = self.core_rotation_bonus(n)
            over = self.overplay_penalty(n)
            reg = self.regime_bonus(n)
            pairb = self.pair_bonus_for_ambata(n)

            if l <= 1:
                continue

            score = (h * W_HEAT) - (l * W_LAG)

            if gap <= 1:
                score += W_GAP_ACTIVE
            elif gap in (3, 4):
                score += W_GAP_RISK
            elif gap >= 6:
                score += W_GAP_RESTART

            if dom >= 3:
                score += W_DOMINANCE

            if pressure >= 10:
                if n == 15:
                    score += 1.8 + W_BONUS_15_CONVERT
                elif n == 5:
                    score += 1.0
                elif n == 10:
                    score += 0.7
            elif pressure >= 6:
                if n == 15:
                    score += 1.0 + W_BONUS_15_CONVERT * 0.6
                elif n == 5:
                    score += 0.7

            if n == 5 and gap <= 1 and dom >= 2:
                score += W_BONUS_5_LIVE

            if n == 15 and any(x in self.last_cluster_nums() for x in [5, 10]):
                score += W_BONUS_15_CONVERT

            if n == 15:
                score += 1.0

                if any(x in self.last_cluster_nums() for x in [5, 10]):
                    score += 1.2

                pair15_5 = self.pair_score(15, 5)
                pair15_50 = self.pair_score(15, 50)

                if pair15_5 >= 4 or pair15_50 >= 4:
                    score += 1.0

                alive_5 = self.is_semi_alive(5)
                alive_50 = self.is_semi_alive(50)

                if not alive_5 and not alive_50:
                    score -= ISOLATED_15_SCORE_PENALTY

                if self.should_block_15_isolated():
                    score -= ISOLATED_15_SCORE_PENALTY

                if h <= 1 and dom == 0 and rot >= 3.0 and reg >= 3.0:
                    if not alive_5 and not alive_50:
                        score -= STRUCTURAL_ONLY_15_PENALTY

                if self.last_stop_number == 15 and self.last_stop_count_same >= REENTRY_15_AFTER_STOP_BLOCK:
                    if not (self.is_alive(5) or self.is_alive(50)):
                        score -= 3.5

            if n == 10:
                score += W_PENALTY_10

                ok_heat = h >= 5
                ok_dom = dom >= 2
                ok_rot = rot >= 1.5

                if ok_heat and ok_dom and ok_rot:
                    score += 2.2
                else:
                    score -= 1.8

            if n == 50:
                if gap <= 1:
                    score += W_PENALTY_50_ACTIVE
                elif state == "RESTART":
                    score += 2.6
                elif gap >= 3:
                    score += 0.8
                elif state == "THIN":
                    score += W_PENALTY_50_THIN
                else:
                    score -= 0.8

                if h >= 5 and l <= 4:
                    score += 1.4

                if dom >= 2:
                    score += 0.7

                if self.profile and self.profile.get("leader_conversion") == 50:
                    score += 0.8

                if self.profile and self.profile.get("leader_presence") == 50:
                    score += 0.5

            score += rot
            score += reg
            score += pairb
            score += over

            structure_bias = round(rot + reg + pairb, 2)
            life_bias = round((h * W_HEAT) - (l * W_LAG) + (W_DOMINANCE if dom >= 3 else 0), 2)

            if n == 15 and self.should_block_15_isolated():
                score -= 2.8

            if n == 15 and structure_bias > life_bias + 3.0 and life_bias < 3.2:
                score -= 2.6

            if n == 15 and self.last_stop_number == 15 and self.last_stop_count_same >= REENTRY_15_AFTER_STOP_BLOCK:
                if life_bias < 4.6:
                    score -= 2.8

            # filtro anti-stop di fila: dopo 2 stop, niente play "di struttura"
            if self.consecutive_stops() >= 2:
                if life_bias < 4.5:
                    score -= 2.5
                if n == 15 and structure_bias > life_bias:
                    score -= 2.0

            if n == 15 and life_bias < MIN_LIFE_BIAS_15 and structure_bias > 7.0:
                score -= 2.2

            if n == 50 and life_bias < MIN_LIFE_BIAS_50 and state != "RESTART":
                score -= 1.8

            rows.append({
                "n": n,
                "score": round(score, 2),
                "heat": h,
                "lag": l,
                "dom": dom,
                "gap": gap,
                "pressure": round(pressure, 2),
                "rot": round(rot, 2),
                "reg": round(reg, 2),
                "pair": round(pairb, 2),
                "over": round(over, 2),
                "state": state,
                "structure_bias": structure_bias,
                "life_bias": life_bias,
            })

        rows = sorted(rows, key=lambda x: x["score"], reverse=True)

        if not rows:
            return None, rows, "NO_ROWS"

        if rows[0]["score"] < MIN_SCORE_NORMAL:
            return None, rows, "LOW_SCORE"

        if len(rows) >= 2:
            diff_needed = MIN_DIFF_SCORE
            if rows[0]["n"] == 10:
                diff_needed = 2.2

            if (rows[0]["score"] - rows[1]["score"]) < diff_needed:
                return None, rows, "LOW_DIFF"

        if rows[0]["gap"] == 1 and rows[0]["score"] < 6.3:
            return None, rows, "GAP1_WEAK"

        if rows[0]["n"] == 15 and rows[0]["life_bias"] < MIN_LIFE_BIAS_15 and rows[0]["structure_bias"] > rows[0]["life_bias"]:
            return None, rows, "15_STRUCTURAL_ONLY"

        if rows[0]["n"] == 50 and rows[0]["life_bias"] < MIN_LIFE_BIAS_50 and rows[0]["state"] != "RESTART":
            return None, rows, "50_WEAK_LIFE"

        if rows[0]["n"] == 15 and self.should_block_15_isolated():
            return None, rows, "15_ISOLATED"

        if rows[0]["n"] == 15 and self.last_stop_number == 15 and self.last_stop_count_same >= REENTRY_15_AFTER_STOP_BLOCK:
            if rows[0]["life_bias"] < 4.6:
                return None, rows, "15_REENTRY_BLOCK"

        if rows[0]["n"] == 15 and rows[0]["structure_bias"] > rows[0]["life_bias"] + 3.0 and rows[0]["life_bias"] < 3.2:
            return None, rows, "15_FAKE_STRUCTURE"

        return rows[0]["n"], rows, "OK"

    # ===================== RESET =============================

    def reset_cycle(self):
        self.A = None
        self.S1 = None
        self.S2 = None
        self.start = None
        self.colpi = 0
        self.max_colpi_cycle = MAX_COLPI_NORMAL
        self.mode = None

    # ===================== MAIN ==============================

    async def on_new(self, app, e, nums):
        if self.is_duplicate_extraction(e):
            return
        self.remember_extraction_id(e)

        gap_before = self.cluster_gap()
        self.update_history(nums)
        self.draws_since_profile_update += 1

        if self.draws_since_profile_update >= PROFILE_UPDATE_EVERY:
            self.profile = self.analyze_cluster_profile()
            self.draws_since_profile_update = 0
            await self.send_profile(app, "🔄 CLUSTER PROFILE UPDATE")

        await self.tg(
            app,
            f"📌 Estrazione {e}\n"
            f"🎱 {', '.join(f'{x:02d}' for x in nums)}"
        )

        s = set(nums)

        if self.A is not None:
            if e >= self.start:
                self.colpi += 1

                hitA = self.A in s
                hit1 = self.S1 in s if self.S1 is not None else False
                hit2 = self.S2 in s if self.S2 is not None else False

                self.log_shot(e, self.colpi, hitA, hitA and hit1, hitA and hit2)

                if hitA and hit1:
                    await self.tg(app, f"💥 HIT AMBO {self.A}-{self.S1}")

                if hitA and hit2:
                    await self.tg(app, f"💥 HIT AMBO {self.A}-{self.S2}")

                if hitA:
                    await self.tg(app, f"🔥 HIT AMBATA {self.A} ({self.mode})")
                    self.push_result("HIT")
                    self.close_play_log("HIT")
                    self.reset_cycle()
                    return

                early_stop = False

                if self.colpi == 2 and self.mode == "NORMAL":
                    pressure_now = self.cluster_pressure()

                    target_life_bias = {
                        5: (self.heat(5) * W_HEAT) - (self.lag(5) * W_LAG),
                        10: (self.heat(10) * W_HEAT) - (self.lag(10) * W_LAG),
                        15: (self.heat(15) * W_HEAT) - (self.lag(15) * W_LAG),
                        50: (self.heat(50) * W_HEAT) - (self.lag(50) * W_LAG),
                    }[self.A]

                    sq = self.support_quality_label(self.A, self.S1, self.S2)

                    if pressure_now < SECOND_SHOT_EARLY_STOP_PRESSURE and target_life_bias <= SECOND_SHOT_WEAK_LIFE_MAX:
                        early_stop = True

                    if self.A == 15 and sq == "SUPPORTS_WEAK":
                        early_stop = True

                if early_stop or self.colpi >= self.max_colpi_cycle:
                    await self.tg(app, f"🛑 STOP {self.A} ({self.mode})")
                    self.push_result("STOP")
                    self.close_play_log("STOP")
                    self.reset_cycle()
                    return
            return

        cluster_nums = [x for x in nums if x in TARGET]
        cluster_count = len(cluster_nums)

        if cluster_count >= 3:
            A, reason_super = self.super_momentum_target_smart(cluster_nums)
            if A is not None:
                self.A = A
                self.S1, self.S2 = self.supports_for_ambata(A)
                self.start = e + 1
                self.colpi = 0
                self.max_colpi_cycle = MAX_COLPI_SUPER
                self.mode = "SUPER_MOMENTUM"
                self.push_play_number(A)
                self.open_play_log(self.start, self.mode, self.A, self.S1, self.S2)

                await self.tg(
                    app,
                    "🚀 SUPER MOMENTUM PLAY\n"
                    f"• trigger={sorted(cluster_nums)}\n"
                    f"• gap_before={gap_before}\n"
                    f"• profile_state={self.profile.get('state', 'n/a') if self.profile else 'n/a'}\n"
                    f"• leader_conversion={self.profile.get('leader_conversion', 'n/a') if self.profile else 'n/a'}\n"
                    f"• reason={reason_super}\n"
                    f"• AMBATA {A}\n"
                    f"• AMBO1 {A}-{self.S1}" +
                    (f"\n• AMBO2 {A}-{self.S2}" if self.S2 is not None else "") +
                    f"\n• supports_quality={self.support_quality_label(A, self.S1, self.S2)}" +
                    f"\n• da {self.start} per {self.max_colpi_cycle} colpi"
                )
                return
            else:
                await self.tg(
                    app,
                    "⏸ NO SUPER MOMENTUM\n"
                    f"• trigger={sorted(cluster_nums)}\n"
                    f"• reason={reason_super}"
                )

        A_restart, debug_restart, reason_restart = self.choose_restart_play()
        if A_restart is not None:
            self.A = A_restart
            self.S1, self.S2 = self.supports_for_ambata(A_restart)
            self.start = e + 1
            self.colpi = 0
            self.max_colpi_cycle = MAX_COLPI_RESTART
            self.mode = "RESTART"
            self.push_play_number(A_restart)
            self.open_play_log(self.start, self.mode, self.A, self.S1, self.S2)

            debug_txt = "\n".join(
                [
                    f"{r['n']}: score={r['score']} heat={r['heat']} lag={r['lag']} dom={r['dom']} "
                    f"gap={r['gap']} pressure={r['pressure']} reg={r['reg']} pair={r['pair']} "
                    f"over={r['over']} state={r['state']} sb={r['structure_bias']} lb={r['life_bias']}"
                    for r in debug_restart
                ]
            )

            await self.tg(
                app,
                "🔁 RESTART PLAY\n"
                f"• reason={reason_restart}\n"
                f"• AMBATA {A_restart}\n"
                f"• AMBO1 {A_restart}-{self.S1}" +
                (f"\n• AMBO2 {A_restart}-{self.S2}" if self.S2 is not None else "") +
                f"\n• supports_quality={self.support_quality_label(A_restart, self.S1, self.S2)}" +
                f"\n• da {self.start} per {self.max_colpi_cycle} colpi\n\n"
                f"📊 DEBUG\n{debug_txt}"
            )
            return

        if len(self.last_draws) < 10:
            return

        A, debug_rows, reason = self.choose_ambata_normal()

        if A is None:
            if debug_rows:
                debug_txt = "\n".join(
                    [
                        f"{r['n']}: score={r['score']} heat={r['heat']} lag={r['lag']} dom={r['dom']} "
                        f"gap={r['gap']} pressure={r['pressure']} rot={r['rot']} reg={r['reg']} "
                        f"pair={r['pair']} over={r['over']} state={r['state']} "
                        f"sb={r['structure_bias']} lb={r['life_bias']}"
                        for r in debug_rows
                    ]
                )
                await self.tg(
                    app,
                    "⏸ NO PLAY NORMAL\n"
                    f"• reason={reason}\n\n"
                    f"📊 DEBUG\n{debug_txt}"
                )
            else:
                await self.tg(
                    app,
                    "⏸ NO PLAY NORMAL\n"
                    f"• reason={reason}"
                )
            return

        self.A = A
        self.S1, self.S2 = self.supports_for_ambata(A)
        self.start = e + 1
        self.colpi = 0
        self.max_colpi_cycle = MAX_COLPI_NORMAL
        self.mode = "NORMAL"
        self.push_play_number(A)
        self.open_play_log(self.start, self.mode, self.A, self.S1, self.S2)

        debug_txt = "\n".join(
            [
                f"{r['n']}: score={r['score']} heat={r['heat']} lag={r['lag']} dom={r['dom']} "
                f"gap={r['gap']} pressure={r['pressure']} rot={r['rot']} reg={r['reg']} "
                f"pair={r['pair']} over={r['over']} state={r['state']} "
                f"sb={r['structure_bias']} lb={r['life_bias']}"
                for r in debug_rows
            ]
        )

        await self.tg(
            app,
            "🎯 PLAY NORMAL\n"
            f"• AMBATA {A}\n"
            f"• AMBO1 {A}-{self.S1}" +
            (f"\n• AMBO2 {A}-{self.S2}" if self.S2 is not None else "") +
            f"\n• supports_quality={self.support_quality_label(A, self.S1, self.S2)}" +
            f"\n• da {self.start} per {self.max_colpi_cycle} colpi\n\n"
            f"📊 DEBUG\n{debug_txt}"
        )

# ===================== LOOP ================================

bot = SNIPER271()

async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    es = parse_site()
    for e, nums in es:
        bot.update_history(nums)
        bot.max_e = max(bot.max_e, e)

    bot.profile = bot.analyze_cluster_profile()
    await bot.tg(app, "🚀 SNIPER v27.1c AVVIATO — Ultra Patched")
    await bot.send_profile(app)

    while True:
        try:
            es = parse_site()
            for e, nums in es:
                if e <= bot.max_e:
                    continue
                bot.max_e = e
                await bot.on_new(app, e, nums)
        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore loop: {ex}")

        await asyncio.sleep(LOOP_SEC)

asyncio.run(live())
