# ============================================================
# 🚀 SNIPER v28.3 LITE — DIRECT PLAY ENGINE
# semplice, fluido, una estrazione alla volta
# NO SETUP
# NO FOLLOWUP SETUP
# SOLO:
# - profile
# - candidate
# - play diretto
# - hit / stop
# ============================================================

import asyncio
import requests
import re
import csv
import os
import json
import hashlib
from datetime import datetime
from collections import defaultdict
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

# ===================== CONFIG ===============================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN mancante")

if not CHAT_ID_RAW:
    raise RuntimeError("CHAT_ID mancante")

CHAT_ID = int(CHAT_ID_RAW)

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TARGET = [5, 10, 15, 50]

LOOP_SEC = 60
HISTORY_MAX = 160
WARMUP_WINDOW = 60
PROFILE_UPDATE_EVERY = 10
PLAY_HORIZON_COLPI = 3

LOG_DIR = "logs"
PLAY_LOG_CSV = os.path.join(LOG_DIR, "sniper_play_log_lite.csv")
STATE_FILE = os.path.join(LOG_DIR, "sniper_v283_lite_state.json")

MAX_RECENT_DRAW_IDS = 50
SEND_PROFILE_UPDATES = True

# ===================== WEIGHTS ==============================

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
LOW_PRESSURE_BLOCK = 4.0

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

MIN_LIFE_BIAS_15 = 2.2
MIN_LIFE_BIAS_50 = 3.0

ALIVE_HEAT_MIN = 2
ALIVE_LAG_MAX = 6
ALIVE_DOM_MIN = 1

REAL_ALIVE_MIN_SCORE = 5.2
FAKE_ALIVE_MIN_SCORE = 2.4

REAL_HEAT_MIN = 2
REAL_LAG_MAX = 6
REAL_DOM_MIN = 1

FAKE_SB_ADVANTAGE = 2.5
DEAD_HEAT_MAX = 1
DEAD_LAG_MIN = 8

MIN_PRESSURE_15_FAKE = 11.0

# ============================================================

def parse_site():
    r = requests.get(URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
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

def draw_fingerprint(e: int, nums: list[int]) -> str:
    raw = f"{e}-{'-'.join(map(str, nums))}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

# ============================================================

class SNIPER283LITE:
    def __init__(self):
        self.max_e = 0
        self.last_draws = []

        self.profile = {}
        self.draws_since_profile_update = 0
        self.leader_presence_history = []
        self.leader_conversion_history = []

        self.recent_results = []
        self.last_signal_numbers = []

        self.recent_extraction_ids = []
        self.recent_fingerprints = []

        self.last_stop_number = None
        self.last_stop_count_same = 0
        self.last_hit_number = None
        self.last_hit_extraction = None

        self.play_id = 0
        self.active_play = None

        os.makedirs(LOG_DIR, exist_ok=True)
        self._init_csv_logs()

    # ===================== STATE ============================

    def _save_state(self):
        data = {
            "max_e": self.max_e,
            "last_draws": self.last_draws[-HISTORY_MAX:],
            "draws_since_profile_update": self.draws_since_profile_update,
            "leader_presence_history": self.leader_presence_history[-6:],
            "leader_conversion_history": self.leader_conversion_history[-6:],
            "recent_results": self.recent_results[-8:],
            "last_signal_numbers": self.last_signal_numbers[-6:],
            "recent_extraction_ids": self.recent_extraction_ids[-MAX_RECENT_DRAW_IDS:],
            "recent_fingerprints": self.recent_fingerprints[-MAX_RECENT_DRAW_IDS:],
            "last_stop_number": self.last_stop_number,
            "last_stop_count_same": self.last_stop_count_same,
            "last_hit_number": self.last_hit_number,
            "last_hit_extraction": self.last_hit_extraction,
            "play_id": self.play_id,
            "active_play": self.active_play,
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_state(self):
        if not os.path.exists(STATE_FILE):
            return

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.max_e = data.get("max_e", 0)
            self.last_draws = data.get("last_draws", [])[-HISTORY_MAX:]
            self.draws_since_profile_update = data.get("draws_since_profile_update", 0)
            self.leader_presence_history = data.get("leader_presence_history", [])[-6:]
            self.leader_conversion_history = data.get("leader_conversion_history", [])[-6:]
            self.recent_results = data.get("recent_results", [])[-8:]
            self.last_signal_numbers = data.get("last_signal_numbers", [])[-6:]
            self.recent_extraction_ids = data.get("recent_extraction_ids", [])[-MAX_RECENT_DRAW_IDS:]
            self.recent_fingerprints = data.get("recent_fingerprints", [])[-MAX_RECENT_DRAW_IDS:]
            self.last_stop_number = data.get("last_stop_number", None)
            self.last_stop_count_same = data.get("last_stop_count_same", 0)
            self.last_hit_number = data.get("last_hit_number", None)
            self.last_hit_extraction = data.get("last_hit_extraction", None)
            self.play_id = data.get("play_id", 0)
            self.active_play = data.get("active_play", None)
        except Exception:
            pass

    # ===================== LOGS =============================

    def _init_csv_logs(self):
        if not os.path.exists(PLAY_LOG_CSV):
            with open(PLAY_LOG_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "ts", "play_id", "open_extraction", "start_extraction",
                    "candidate", "support1", "support2",
                    "support_quality", "state", "pressure", "gap",
                    "life_bias", "structure_bias",
                    "eval_extraction", "colpo",
                    "hit_ambata", "hit_ambo1", "hit_ambo2",
                    "result"
                ])

    def _now_str(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ===================== TELEGRAM =========================

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)
        await asyncio.sleep(0.15)

    # ===================== HISTORY ==========================

    def update_history(self, nums):
        self.last_draws.append(nums)
        if len(self.last_draws) > HISTORY_MAX:
            self.last_draws.pop(0)

    def push_result(self, result):
        self.recent_results.append(result)
        if len(self.recent_results) > 8:
            self.recent_results.pop(0)

    def push_signal_number(self, n):
        self.last_signal_numbers.append(n)
        if len(self.last_signal_numbers) > 6:
            self.last_signal_numbers.pop(0)

    def remember_draw(self, e, nums):
        self.recent_extraction_ids.append(e)
        self.recent_extraction_ids = self.recent_extraction_ids[-MAX_RECENT_DRAW_IDS:]

        fp = draw_fingerprint(e, nums)
        self.recent_fingerprints.append(fp)
        self.recent_fingerprints = self.recent_fingerprints[-MAX_RECENT_DRAW_IDS:]

    def is_duplicate_draw(self, e, nums):
        if e in self.recent_extraction_ids:
            return True
        fp = draw_fingerprint(e, nums)
        return fp in self.recent_fingerprints

    # ===================== FEATURES =========================

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

        same_n = sum(1 for x in self.last_signal_numbers[-3:] if x == n)
        if same_n >= 2:
            pen += 1.5

        if n == 50:
            same_50 = sum(1 for x in self.last_signal_numbers[-2:] if x == 50)
            if same_50 >= 1:
                pen += 1.8

        return -pen

    # ===================== PROFILE ENGINE ===================

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
            "ranked_presence": ranked_presence,
            "leader_presence": leader_presence,
            "second_presence": second_presence,
            "weak_presence": weak_presence,
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

    # ===================== SUPPORT QUALITY ==================

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

    def support_structure_bias(self, ambata, n):
        if n is None:
            return -999.0
        pair_component = self.pair_score(ambata, n)
        rot_component = self.transition_score(ambata, n) + self.transition_score(n, ambata)
        return round(pair_component * 0.9 + rot_component * 0.25, 2)

    def support_life_bias(self, n):
        if n is None:
            return -999.0
        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance_count(n, 6)
        return round((h * 1.2) - (l * 0.35) + (d * 1.2), 2)

    def support_state_label(self, ambata, n):
        if n is None:
            return "DEAD"

        h = self.heat(n)
        l = self.lag(n)
        d = self.dominance_count(n, 6)

        life = self.support_life_bias(n)
        struct = self.support_structure_bias(ambata, n)
        total = self.support_score(ambata, n)

        if h <= DEAD_HEAT_MAX and l >= DEAD_LAG_MIN and d == 0:
            return "DEAD"

        if (
            life >= 2.2
            and h >= REAL_HEAT_MIN
            and l <= REAL_LAG_MAX
            and d >= REAL_DOM_MIN
            and total >= REAL_ALIVE_MIN_SCORE
        ):
            return "REAL_ALIVE"

        if struct >= life + FAKE_SB_ADVANTAGE and total >= FAKE_ALIVE_MIN_SCORE:
            return "FAKE_ALIVE"

        if total >= REAL_ALIVE_MIN_SCORE and h >= 1 and l <= 7:
            return "REAL_ALIVE"

        if total >= FAKE_ALIVE_MIN_SCORE:
            return "FAKE_ALIVE"

        return "DEAD"

    def support_state_details(self, ambata, n):
        if n is None:
            return {
                "label": "DEAD",
                "score": -999.0,
                "life": -999.0,
                "struct": -999.0,
                "heat": 0,
                "lag": 99,
                "dom": 0,
            }

        return {
            "label": self.support_state_label(ambata, n),
            "score": self.support_score(ambata, n),
            "life": self.support_life_bias(n),
            "struct": self.support_structure_bias(ambata, n),
            "heat": self.heat(n),
            "lag": self.lag(n),
            "dom": self.dominance_count(n, 6),
        }

    def support_quality_label(self, ambata, s1, s2):
        labels = []
        for s in [s1, s2]:
            if s is not None:
                labels.append(self.support_state_label(ambata, s))

        if not labels:
            return "DEAD"

        real_count = sum(1 for x in labels if x == "REAL_ALIVE")
        fake_count = sum(1 for x in labels if x == "FAKE_ALIVE")

        if ambata == 15:
            real_strong = 0
            for s in [s1, s2]:
                if s is None:
                    continue
                d = self.support_state_details(ambata, s)
                if d["label"] == "REAL_ALIVE" and d["life"] >= 4.0:
                    real_strong += 1

            if real_strong >= 1:
                return "REAL_ALIVE"
            if fake_count >= 1:
                return "FAKE_ALIVE"
            return "DEAD"

        if real_count >= 1:
            return "REAL_ALIVE"
        if fake_count >= 1:
            return "FAKE_ALIVE"
        return "DEAD"

    def support_quality_debug_text(self, ambata, s1, s2):
        parts = []
        for s in [s1, s2]:
            if s is None:
                continue
            d = self.support_state_details(ambata, s)
            parts.append(
                f"{s}: {d['label']} score={d['score']} life={d['life']} struct={d['struct']} "
                f"heat={d['heat']} lag={d['lag']} dom={d['dom']}"
            )
        return "\n".join(parts) if parts else "no_supports"

    # ===================== SUPPORTS =========================

    def supports_for_candidate(self, a):
        pressure = self.cluster_pressure()

        if a == 15:
            d50 = self.support_state_details(15, 50)
            d5 = self.support_state_details(15, 5)

            if d50["label"] == "DEAD" and d5["label"] == "DEAD":
                return None, None

            if d50["label"] == "REAL_ALIVE" and d5["label"] == "REAL_ALIVE":
                if d50["life"] >= d5["life"] + 1.0 or pressure >= 14:
                    return 50, 5 if d5["life"] >= 4.0 else None
                return 5, 50 if d50["life"] >= 4.0 and pressure >= 15 else None

            if d50["label"] == "REAL_ALIVE" and d5["label"] != "REAL_ALIVE":
                return 50, None

            if d5["label"] == "REAL_ALIVE" and d50["label"] != "REAL_ALIVE":
                return 5, None

            if d50["label"] == "FAKE_ALIVE" and pressure >= 13 and d50["struct"] >= 6.0:
                return 50, None

            if d5["label"] == "FAKE_ALIVE" and pressure >= 12 and d5["struct"] >= 5.0:
                return 5, None

            return None, None

        if a == 50:
            d15 = self.support_state_details(50, 15)
            d5 = self.support_state_details(50, 5)

            if d5["label"] == "REAL_ALIVE" and d5["life"] >= d15["life"] - 0.5:
                s1 = 5
            elif d15["label"] == "REAL_ALIVE":
                s1 = 15
            else:
                s1 = 5 if d5["score"] >= d15["score"] else 15

            s2 = None
            if s1 == 5 and d15["label"] == "REAL_ALIVE" and pressure >= 11:
                s2 = 15
            elif s1 == 15 and d5["label"] == "REAL_ALIVE" and pressure >= 11:
                s2 = 5

            return s1, s2

        if a == 5:
            d10 = self.support_state_details(5, 10)
            d15 = self.support_state_details(5, 15)
            d50 = self.support_state_details(5, 50)

            if d10["label"] == "REAL_ALIVE" and d10["life"] >= d15["life"] - 0.5:
                s1 = 10
            elif d15["label"] == "REAL_ALIVE":
                s1 = 15
            elif d10["label"] == "FAKE_ALIVE" and d15["label"] != "REAL_ALIVE":
                s1 = 10
            else:
                s1 = 15 if d15["score"] >= d10["score"] else 10

            s2 = None
            if d50["label"] == "REAL_ALIVE" and pressure >= 11:
                s2 = 50
            elif d50["label"] == "FAKE_ALIVE" and d50["struct"] >= 5.5 and pressure >= 13:
                s2 = 50

            if s2 == s1:
                s2 = None

            return s1, s2

        if a == 10:
            return 15, None

        return None, None

    # ===================== SCORING ==========================

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

    def pair_bonus_for_candidate(self, n):
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

    def candidate_block_reason(self, candidate, rows):
        top = rows[0]
        s1, s2 = self.supports_for_candidate(candidate)
        sq = self.support_quality_label(candidate, s1, s2)

        if candidate == 15 and sq == "DEAD":
            return "15_DEAD_SUPPORTS"
        if candidate == 15 and sq == "FAKE_ALIVE" and top["pressure"] < MIN_PRESSURE_15_FAKE:
            return "15_FAKE_SUPPORTS"
        if candidate == 15 and top["life_bias"] < MIN_LIFE_BIAS_15 and top["structure_bias"] > top["life_bias"]:
            return "15_STRUCTURAL_ONLY"
        if candidate == 50 and top["life_bias"] < MIN_LIFE_BIAS_50 and top["state"] != "RESTART":
            return "50_WEAK_LIFE"
        return None

    def choose_candidate_normal(self):
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
            pairb = self.pair_bonus_for_candidate(n)

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

            score += rot + reg + pairb + over

            structure_bias = round(rot + reg + pairb, 2)
            life_bias = round((h * W_HEAT) - (l * W_LAG) + (W_DOMINANCE if dom >= 3 else 0), 2)

            if n == 5:
                recent_same_5 = sum(1 for x in self.last_signal_numbers[-3:] if x == 5)
                if recent_same_5 >= 2 and life_bias < 8.5:
                    score -= 1.8
                if self.last_stop_number == 5 and self.last_stop_count_same >= 1 and life_bias < 8.0:
                    score -= 1.6
                if self.last_hit_number == 5 and life_bias < 8.2:
                    score -= 1.2

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

        block_reason = self.candidate_block_reason(rows[0]["n"], rows)
        if block_reason:
            return None, rows, block_reason

        return rows[0]["n"], rows, "OK"

    # ===================== PLAY ENGINE ======================

    def open_play(self, open_extraction, candidate, support1, support2, top_row):
        self.play_id += 1
        sq = self.support_quality_label(candidate, support1, support2)

        self.active_play = {
            "play_id": self.play_id,
            "open_extraction": open_extraction,
            "start_extraction": open_extraction + 1,
            "candidate": candidate,
            "support1": support1,
            "support2": support2,
            "support_quality": sq,
            "state": top_row["state"],
            "pressure": top_row["pressure"],
            "gap": top_row["gap"],
            "life_bias": top_row["life_bias"],
            "structure_bias": top_row["structure_bias"],
            "colpi_done": 0,
            "max_colpi": PLAY_HORIZON_COLPI,
        }

    def _write_play_log(self, result, eval_extraction=None, colpo=None, hit_ambata=0, hit_ambo1=0, hit_ambo2=0):
        if not self.active_play:
            return

        p = self.active_play
        with open(PLAY_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                self._now_str(),
                p["play_id"],
                p["open_extraction"],
                p["start_extraction"],
                p["candidate"],
                p["support1"],
                p["support2"],
                p["support_quality"],
                p["state"],
                p["pressure"],
                p["gap"],
                p["life_bias"],
                p["structure_bias"],
                eval_extraction,
                colpo,
                int(hit_ambata),
                int(hit_ambo1),
                int(hit_ambo2),
                result
            ])

    async def process_active_play(self, app, e, nums):
        if not self.active_play:
            return

        p = self.active_play
        if e < p["start_extraction"]:
            return

        s = set(nums)
        p["colpi_done"] += 1
        colpo = p["colpi_done"]

        candidate = p["candidate"]
        s1 = p["support1"]
        s2 = p["support2"]

        hit_ambata = candidate in s
        hit_ambo1 = hit_ambata and (s1 in s if s1 is not None else False)
        hit_ambo2 = hit_ambata and (s2 in s if s2 is not None else False)

        self._write_play_log("SHOT", e, colpo, hit_ambata, hit_ambo1, hit_ambo2)

        if hit_ambo1:
            await self.tg(app, f"💥 HIT AMBO {candidate}-{s1}")

        if hit_ambo2:
            await self.tg(app, f"💥 HIT AMBO {candidate}-{s2}")

        if hit_ambata:
            await self.tg(
                app,
                "🔥 HIT AMBATA\n"
                f"• play_id = {p['play_id']}\n"
                f"• candidate = {candidate}\n"
                f"• colpo = {colpo}"
            )

            self._write_play_log("HIT", e, colpo, hit_ambata, hit_ambo1, hit_ambo2)
            self.last_hit_number = candidate
            self.last_hit_extraction = e
            self.last_stop_number = None
            self.last_stop_count_same = 0
            self.push_result("HIT")
            self.active_play = None
            return

        if colpo >= p["max_colpi"]:
            await self.tg(
                app,
                "🛑 STOP PLAY\n"
                f"• play_id = {p['play_id']}\n"
                f"• candidate = {candidate}\n"
                f"• colpi = {colpo}"
            )

            self._write_play_log("STOP", e, colpo, hit_ambata, hit_ambo1, hit_ambo2)
            if self.last_stop_number == candidate:
                self.last_stop_count_same += 1
            else:
                self.last_stop_number = candidate
                self.last_stop_count_same = 1

            self.push_result("STOP")
            self.active_play = None

    # ===================== PROFILE MESSAGE ==================

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

    # ===================== MAIN =============================

    async def on_new(self, app, e, nums):
        if self.is_duplicate_draw(e, nums):
            return

        self.remember_draw(e, nums)
        self.update_history(nums)
        self.draws_since_profile_update += 1

        if self.draws_since_profile_update >= PROFILE_UPDATE_EVERY:
            self.profile = self.analyze_cluster_profile()
            self.draws_since_profile_update = 0
            if SEND_PROFILE_UPDATES:
                await self.send_profile(app, "🔄 CLUSTER PROFILE UPDATE")

        await self.tg(
            app,
            f"📌 Estrazione {e}\n"
            f"🎱 {', '.join(f'{x:02d}' for x in nums)}"
        )

        # prima chiude o aggiorna eventuale play attivo
        await self.process_active_play(app, e, nums)

        # se c'è ancora un play attivo, non apre altro
        if self.active_play is not None:
            self._save_state()
            return

        if len(self.last_draws) < 10:
            self._save_state()
            return

        candidate, debug_rows, reason = self.choose_candidate_normal()

        if candidate is None:
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
                    "⏸ NO PLAY\n"
                    f"• reason={reason}\n\n"
                    f"📊 DEBUG\n{debug_txt}"
                )
            else:
                await self.tg(app, f"⏸ NO PLAY\n• reason={reason}")

            self._save_state()
            return

        top = debug_rows[0]
        s1, s2 = self.supports_for_candidate(candidate)
        sq = self.support_quality_label(candidate, s1, s2)

        self.push_signal_number(candidate)
        self.open_play(e, candidate, s1, s2, top)

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
            "🎯 PLAY\n"
            f"• candidate = {candidate}\n"
            f"• support1 = {candidate}-{s1}\n"
            + (f"• support2 = {candidate}-{s2}\n" if s2 is not None else "")
            + f"• supports_quality = {sq}\n"
            + f"• da estrazione {self.active_play['start_extraction']} per {self.active_play['max_colpi']} colpi\n\n"
            + f"🧩 SUPPORTS\n{self.support_quality_debug_text(candidate, s1, s2)}\n\n"
            + f"📊 DEBUG\n{debug_txt}"
        )

        self._save_state()


# ===================== LOOP ================================

bot = SNIPER283LITE()

async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    bot._load_state()

    if not bot.last_draws:
        es = parse_site()
        for e, nums in es:
            bot.update_history(nums)
            bot.max_e = max(bot.max_e, e)
    else:
        es = parse_site()
        for e, nums in es:
            bot.max_e = max(bot.max_e, e)

    bot.profile = bot.analyze_cluster_profile()

    await bot.tg(app, "🚀 SNIPER v28.3 LITE AVVIATO")
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
