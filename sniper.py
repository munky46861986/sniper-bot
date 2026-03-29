# ============================================================
# 🚀 SNIPER v27.1b-final TEST — SMART AMBO PATCH
# Base v27.1 + ambi intelligenti su ambata 15
# ============================================================



import asyncio
import requests
import re
from collections import defaultdict
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

# ===================== CONFIG ===============================

import os

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN mancante")

if not CHAT_ID:
    raise RuntimeError("CHAT_ID mancante")

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

# v27 core logic
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
        self.mode = None  # NORMAL / SUPER_MOMENTUM / RESTART

        self.recent_results = []
        self.last_play_numbers = []

        self.profile = {}
        self.draws_since_profile_update = 0
        self.leader_presence_history = []
        self.leader_conversion_history = []

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

        # 50 non va rincorso troppo vicino
        if n == 50:
            same_50 = sum(1 for x in self.last_play_numbers[-2:] if x == 50)
            if same_50 >= 1:
                pen += 1.8

        return -pen

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

        for i, d in enumerate(window):
            w = 1.0
            if d in recent_tail:
                w = 1.5
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

    # ===================== SUPPORTS PATCH ====================

    def supports_for_ambata(self, a):
        pressure = self.cluster_pressure()

        # ===================== AMBATA 15 =====================
        if a == 15:
            p50 = self.pair_score(15, 50)
            p5 = self.pair_score(15, 5)

            h50 = self.heat(50)
            h5 = self.heat(5)

            l50 = self.lag(50)
            l5 = self.lag(5)

            # 1) cluster forte -> entrambi
            if (
                pressure >= 14 and
                p50 >= 3 and p5 >= 3 and
                h50 > 0 and h5 > 0
            ):
                return 50, 5

            # 2) 50 dominante -> solo 15-50
            if (
                p50 >= p5 and
                (h50 >= h5 or l50 <= l5) and
                pressure >= 10
            ):
                return 50, None

            # 3) 5 dominante -> solo 15-5
            if (
                p5 > p50 or
                (h5 > h50 and l5 <= l50)
            ):
                return 5, None

            # 4) fallback
            if pressure >= 12:
                return 50, None
            return 5, None

        # ===================== AMBATA 50 =====================
        if a == 50:
            p15 = self.pair_score(50, 15)
            p5 = self.pair_score(50, 5)

            if p15 >= p5:
                s1 = 15
                s2 = 5 if (p5 >= 4 and pressure >= 10) else None
            else:
                s1 = 5
                s2 = 15 if (p15 >= 4 and pressure >= 10) else None

            return s1, s2

        # ===================== AMBATA 5 ======================
        if a == 5:
            p15 = self.pair_score(5, 15)
            p50 = self.pair_score(5, 50)

            s1 = 15
            s2 = 50 if (p50 >= 4 and pressure >= 10) else None
            return s1, s2

        # ===================== AMBATA 10 =====================
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

        pair_support = 0
        for a in s:
            pair_support += self.pair_score(missing, a)

        if pressure >= 6 and state != "THIN" and pair_support >= 3:
            return missing, "MISSING_OK"

        if leader_conv == 10 and pressure < 8:
            return None, "CONV10_NOT_STRONG_ENOUGH"

        if leader_conv != missing and leader_conv in TARGET:
            if leader_conv in s and pressure < 9:
                return None, "LEADER_INSIDE_TRIGGER"
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
            })

        rows = sorted(rows, key=lambda x: x["score"], reverse=True)

        if not rows:
            return None, rows, "NO_ROWS"

        if rows[0]["score"] < MIN_SCORE_RESTART:
            return None, rows, "LOW_RESTART_SCORE"

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
                    score += 2.4
                elif gap >= 3:
                    score += 0.8
                elif state == "THIN":
                    score += W_PENALTY_50_THIN
                else:
                    score -= 0.8

            score += rot
            score += reg
            score += pairb
            score += over

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

                if hitA and hit1:
                    await self.tg(app, f"💥 HIT AMBO {self.A}-{self.S1}")

                if hitA and hit2:
                    await self.tg(app, f"💥 HIT AMBO {self.A}-{self.S2}")

                if hitA:
                    await self.tg(app, f"🔥 HIT AMBATA {self.A} ({self.mode})")
                    self.push_result("HIT")
                    self.reset_cycle()
                    return

                if self.colpi >= self.max_colpi_cycle:
                    await self.tg(app, f"🛑 STOP {self.A} ({self.mode})")
                    self.push_result("STOP")
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

            debug_txt = "\n".join(
                [
                    f"{r['n']}: score={r['score']} heat={r['heat']} lag={r['lag']} dom={r['dom']} "
                    f"gap={r['gap']} pressure={r['pressure']} reg={r['reg']} pair={r['pair']} "
                    f"over={r['over']} state={r['state']}"
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
                        f"pair={r['pair']} over={r['over']} state={r['state']}"
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

        debug_txt = "\n".join(
            [
                f"{r['n']}: score={r['score']} heat={r['heat']} lag={r['lag']} dom={r['dom']} "
                f"gap={r['gap']} pressure={r['pressure']} rot={r['rot']} reg={r['reg']} "
                f"pair={r['pair']} over={r['over']} state={r['state']}"
                for r in debug_rows
            ]
        )

        await self.tg(
            app,
            "🎯 PLAY NORMAL\n"
            f"• AMBATA {A}\n"
            f"• AMBO1 {A}-{self.S1}" +
            (f"\n• AMBO2 {A}-{self.S2}" if self.S2 is not None else "") +
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
    await bot.tg(app, "🚀 SNIPER v27.1b-final TEST AVVIATO — Smart Ambo Patch")
    await bot.send_profile(app, "🧠 WARMUP ANALYSIS")

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
