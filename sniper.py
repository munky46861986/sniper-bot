# ============================================================
# 🚀 SNIPER v48 — FINAL RESEARCH
#
# CORE v48: INVARIATO
#   - Hot Confirmed
#   - costruzione 3 ambi
#   - ambata
#   - score
#   - cluster reuse
#   - cooldown
#   - massimo 7 colpi
#   - chiusura al primo HIT AMBO
#
# LAB PARALLELO (non modifica il CORE v48):
#   - OP3 PRIMARY: miglior score fuori cluster
#   - OP9 CONTROL: mix score + ritardo + frequenza
#   - OP6 CONTROL: stessa decina ambata
#   - OP7 CONTROL: stessa decina dinamica per ambo
#   - TERNI LAB indipendente per 7 colpi anche dopo HIT AMBO
#   - AMBATA RAFFICA 2 indipendente per 2 colpi
#   - DECINA LAB 10-19 BASE: TOP 3 Heat ultime 5, soglia totale >= 8
#     sessione indipendente per 2 colpi, target statistici K1/K2/K3
#   - MONITOR HEAT STRATA: Heat=8 / Heat=9 / Heat>=10
#     statistiche K1/K2/K3 separate + simulazione economica K3 a 45x
#   - DECINA CORE TOP2 LAB: Heat >= 9, 3 terni A-B-C/A-B-D/A-B-E
#   - DECINA PIVOT LAB: Heat >= 9, 6 terni tutti contenenti il pivot A
#     CORE/PIVOT indipendenti per 2 colpi, stop al primo colpo vincente
#     bilancio teorico separato a payout 45x per unita' puntata
#   - AMBO-JOLLY AJ1 LAB (solo ricerca): 1° ambo v48 + jolly OP3 globale
#     un solo terno, osservato in parallelo a 2/3/4/7 colpi
#     ma censurato alla chiusura del PLAY v48 (HIT AMBO o STOP),
#     esattamente come nel backtest di conversione ambo->terno
#     bilancio teorico separato a payout 45x per unita' puntata
#   - NUMERI SPIA LAB (solo ricerca): candidati robusti dal backtest
#     storico, condizioni C2_exact/C3plus, TOP3 accompagnatori,
#     osservazione sul solo colpo successivo, K1/K2/K3 + ROI K3 45x
#   - SPY NETWORK SCORE: classifica ogni segnale spia per rete numerica
#     CATENA_5 / PONTE_55 / ZONA_40 / LATERALE_23 e livello
#     NORMALE / FORTE / MULTIPLA quando piu' spie collegate sono attive
#
# PATCH OPERATIVE:
#   - lock globale anti doppia istanza
#   - startup senza replay
#   - reset operativo cambio giorno
#   - monitor rank degli ambi v48 vincenti (rank 1/2/3)
#   - CSV eventi in formato lungo/pulito
#   - stato persistente anche per sessioni LAB indipendenti
# ============================================================

import asyncio
import atexit
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from itertools import combinations

import requests
from bs4 import BeautifulSoup
from telegram.ext import ApplicationBuilder

import nest_asyncio

try:
    import fcntl
except ImportError:
    fcntl = None

nest_asyncio.apply()


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# File nuovi: non mischiano stato/statistiche delle versioni precedenti.
STATE_FILE = os.path.join(BASE_DIR, "sniper_v48_final_spy_network_h123_lab_state.json")
CSV_FILE = os.path.join(BASE_DIR, "sniper_v48_final_spy_network_h123_lab_events.csv")

# Stesso lock globale delle versioni Lab precedenti: impedisce di lasciare
# accidentalmente attivo un vecchio bot insieme a questo.
LOCK_FILE = "/tmp/sniper_v48_terni_lab.lock"

LOOP_SEC = 60

HISTORY_MAX = 240
PROCESSED_MAX = 1000

TOP_RITARDATARI = 10
PLAY_POSITIONS = [6, 7, 8, 9, 10]

WATCH_WINDOW = 12
HOT_TTL = 45
MIN_HOT_ACTIVE = 3

MAX_AMBI_PER_PLAY = 3
MAX_COLPI = 7
COOLDOWN_AFTER_PLAY = 5
CLUSTER_REUSE_AFTER = 12

# LAB indipendenti
TERNI_LAB_MAX_COLPI = 7
AMBATA_RAFFICA_MAX_COLPI = 2

# DECINA LAB 10-19 — regola congelata dal backtest storico.
DECINA_LAB_NUMBERS = tuple(range(10, 20))
DECINA_LAB_WINDOW = 5
DECINA_LAB_TOP_N = 3
DECINA_LAB_HEAT_THRESHOLD = 8
DECINA_LAB_MAX_COLPI = 2

# Nuovi pacchetti multi-terno emersi dal backtest:
# - CORE TOP2: A-B-C / A-B-D / A-B-E (3 terni)
# - PIVOT: tutti i terni del TOP5 che contengono A (6 terni)
# Si aprono solo con Heat totale TOP3 >= 9.
DECINA_MULTI_HEAT_THRESHOLD = 9
DECINA_MULTI_TOP_N = 5
DECINA_MULTI_MAX_COLPI = 2
DECINA_TERNO_PAYOUT = 45.0

# Monitor economico del singolo terno TOP3 della Decina Base.
# Simulazione: 1 unita' per colpo, massimo 2 colpi, stop economico sul K3.
DECINA_BASE_K3_PAYOUT = 45.0

# Fasce monitorate separatamente, senza cambiare la regola di ingresso.
# H8 = Heat esattamente 8; H9 = Heat esattamente 9; H10P = Heat >= 10.
DECINA_HEAT_BUCKETS = ("H8", "H9", "H10P")

# AMBO-JOLLY AJ1 — candidato emerso dal backtest storico.
# Un solo terno: 1° ambo v48 (rank 1 per score pair) + jolly OP3 globale.
# Le quattro strategie 2/3/4/7 colpi vengono seguite in parallelo e
# contabilizzate separatamente, senza scegliere a posteriori l'orizzonte.
# Ogni orizzonte si ferma anche se il PLAY v48 chiude prima per un altro ambo.
AMBO_JOLLY_HORIZONS = (2, 3, 4, 7)
AMBO_JOLLY_PAYOUT = 45.0

# L'utente ha scelto notifiche Telegram permanenti.
# Per silenziarle in futuro basta impostare queste costanti a False.
DECINA_LAB_NOTIFY = True
DECINA_MULTI_NOTIFY = True
AMBO_JOLLY_NOTIFY = True

# NUMERI SPIA LAB — candidati emersi dal test storico.
# Osservazione parallela: prossimo 1 / 2 / 3 colpi.
# K3 economico: 1 unita' per colpo sul terno TOP3, payout 45x,
# con stop economico sull'orizzonte appena arriva il 3/3.
SPY_LAB_NOTIFY = True
SPY_LAB_HORIZONS = (1, 2, 3)
SPY_LAB_MAX_COLPI = max(SPY_LAB_HORIZONS)
SPY_LAB_PAYOUT = 45.0
SPY_LAB_CANDIDATES = [
    # CATENA_5: rete 30 → 25 → 20 → 15 → 10 → 5
    {"spy": 25, "condition": "C2_exact", "followers": (20, 15, 10), "label": "25 C2 → 20-15-10", "network": "CATENA_5"},
    {"spy": 30, "condition": "C3plus",  "followers": (20, 25, 10), "label": "30 C3 → 20-25-10", "network": "CATENA_5"},
    {"spy": 20, "condition": "C2_exact", "followers": (15, 10, 5),  "label": "20 C2 → 15-10-5",  "network": "CATENA_5"},

    # ZONA_40: scala 50 → 45 → 40 con ponte verso 18.
    {"spy": 50, "condition": "C2_exact", "followers": (45, 40, 18), "label": "50 C2 → 45-40-18", "network": "ZONA_40"},

    # PONTE_55: 5/15 che scaricano verso 55 e area 4/14/28/56.
    {"spy": 15, "condition": "C3plus", "followers": (14, 28, 55), "label": "15 C3 → 14-28-55", "network": "PONTE_55"},
    {"spy": 5,  "condition": "C3plus", "followers": (4, 55, 56),  "label": "5 C3 → 4-55-56",  "network": "PONTE_55"},

    # LATERALE_23: meno integrata, ma collegata alla zona 40 tramite 39/42.
    {"spy": 23, "condition": "C3plus", "followers": (22, 42, 39), "label": "23 C3 → 22-42-39", "network": "LATERALE_23"},
]

SPY_NETWORK_DEFS = {
    "CATENA_5": {
        "label": "CATENA 5",
        "nodes": (5, 10, 15, 20, 25, 30),
        "note": "rete principale 30→25→20→15→10→5",
    },
    "PONTE_55": {
        "label": "PONTE 55",
        "nodes": (4, 5, 14, 15, 28, 55, 56),
        "note": "ponte 5/15 verso 55-56",
    },
    "ZONA_40": {
        "label": "ZONA 40/50",
        "nodes": (18, 40, 45, 50),
        "note": "scala 50→45→40 con ponte 18",
    },
    "LATERALE_23": {
        "label": "LATERALE 23",
        "nodes": (22, 23, 39, 42),
        "note": "laterale 23 verso 22-39-42",
    },
    "ALTRO": {"label": "ALTRO", "nodes": (), "note": "fuori rete"},
}
SPY_NETWORK_BUCKETS = tuple(SPY_NETWORK_DEFS.keys())
SPY_NETWORK_LEVELS = ("NORMALE", "FORTE", "MULTIPLA")

# Strategie mantenute dopo il backtest storico.
LAB_STRATEGIES = ("op3", "op9", "op6", "op7")
LAB_LABELS = {
    "op3": "OP3 PRIMARY — SCORE FUORI CLUSTER",
    "op9": "OP9 CONTROL — MIX SCORE+RITARDO",
    "op6": "OP6 CONTROL — STESSA DECINA AMBATA",
    "op7": "OP7 CONTROL — STESSA DECINA DINAMICA",
}


# ============================================================
# UTILS
# ============================================================

def validate_env():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN non impostato nell'ambiente")

    if not CHAT_ID_RAW:
        raise RuntimeError("CHAT_ID non impostato nell'ambiente")

    try:
        return int(CHAT_ID_RAW)
    except ValueError as exc:
        raise RuntimeError("CHAT_ID deve essere un intero") from exc


def parse_site():
    r = requests.get(URL, headers=HEADERS, timeout=20)
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
    return hashlib.md5(
        f"{e}-{'-'.join(map(str, nums))}".encode()
    ).hexdigest()


def day_key():
    return datetime.now().strftime("%Y-%m-%d")


def now_txt():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_nums(nums):
    return "-".join(map(str, nums or []))


def fmt_ambi(ambi):
    parts = []
    for item in ambi or []:
        a, b = item["ambo"]
        parts.append(f"{a}-{b}")
    return ", ".join(parts)


def fmt_terni(terni):
    return ", ".join("-".join(map(str, t)) for t in (terni or []))


def fmt_jolly(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "-".join(map(str, value))
    return str(value)


def normalize_terni(terni):
    out = []
    for t in terni or []:
        if len(t) == 3:
            out.append(tuple(sorted(map(int, t))))
    return sorted(set(out))


# ============================================================
# CSV — FORMATO LUNGO/PULITO
# ============================================================

CSV_FIELDS = [
    "time",
    "day",
    "event",
    "play_id",
    "estrazione",
    "colpo",
    "session_type",
    "strategy",
    "ambata",
    "ambi",
    "cluster",
    "jolly",
    "terni",
    "hit_list",
    "outcome",
    "v48_total_play",
    "v48_hit_ambata_events",
    "v48_hit_ambo",
    "v48_stop",
    "v48_rank1_hit_events",
    "v48_rank2_hit_events",
    "v48_rank3_hit_events",
    "v48_multi_ambo_hit_draws",
    "op3_sessions",
    "op3_hit_sessions",
    "op9_sessions",
    "op9_hit_sessions",
    "op6_sessions",
    "op6_hit_sessions",
    "op7_sessions",
    "op7_hit_sessions",
    "ambata_r2_sessions",
    "ambata_r2_hits",
    "ambata_r2_misses",
    "ambata_r2_hit_colpo1",
    "ambata_r2_hit_colpo2",
    "decina_signal_id",
    "decina_top3",
    "decina_heat_total",
    "decina_hit_numbers",
    "decina_sessions",
    "decina_closed",
    "decina_k1_hits",
    "decina_k2_hits",
    "decina_k3_hits",
    "decina_k2_colpo1",
    "decina_k2_colpo2",
    "decina_k3_colpo1",
    "decina_k3_colpo2",
    "decina_k3_cost_units",
    "decina_k3_gross_units",
    "decina_k3_net_units",
    "decina_k3_roi_pct",
    "decina_multi_signal_id",
    "decina_multi_package",
    "decina_top5",
    "decina_package_terni",
    "decina_terni_hit_count",
    "core_sessions",
    "core_closed",
    "core_winning_sessions",
    "core_losing_sessions",
    "core_hit_colpo1",
    "core_hit_colpo2",
    "core_winning_terni",
    "core_multi_2plus_sessions",
    "core_max_terni_same_draw",
    "core_cost_units",
    "core_gross_units",
    "core_net_units",
    "core_roi_pct",
    "pivot_sessions",
    "pivot_closed",
    "pivot_winning_sessions",
    "pivot_losing_sessions",
    "pivot_hit_colpo1",
    "pivot_hit_colpo2",
    "pivot_winning_terni",
    "pivot_multi_2plus_sessions",
    "pivot_max_terni_same_draw",
    "pivot_cost_units",
    "pivot_gross_units",
    "pivot_net_units",
    "pivot_roi_pct",
    "ambo_jolly_terno",
    "ambo_jolly_rank1_ambo",
    "ambo_jolly_op3",
    "ambo_jolly_horizon",
    "spy_signal_id",
    "spy_number",
    "spy_condition",
    "spy_network",
    "spy_network_level",
    "spy_active_related",
    "spy_active_total",
    "spy_followers",
    "spy_hit_numbers",
    "spy_k_hit",
    "spy_sessions",
    "spy_closed",
    "spy_k1_hits",
    "spy_k2_hits",
    "spy_k3_hits",
    "spy_k3_cost_units",
    "spy_k3_gross_units",
    "spy_k3_net_units",
    "spy_k3_roi_pct",
    # Nuovi campi: statistiche Num. Spia separate per orizzonte H1/H2/H3.
    "spy_h1_sessions", "spy_h1_closed", "spy_h1_k1_hits", "spy_h1_k2_hits", "spy_h1_k3_hits",
    "spy_h1_k3_cost_units", "spy_h1_k3_gross_units", "spy_h1_k3_net_units", "spy_h1_k3_roi_pct",
    "spy_h2_sessions", "spy_h2_closed", "spy_h2_k1_hits", "spy_h2_k2_hits", "spy_h2_k3_hits",
    "spy_h2_k3_cost_units", "spy_h2_k3_gross_units", "spy_h2_k3_net_units", "spy_h2_k3_roi_pct",
    "spy_h3_sessions", "spy_h3_closed", "spy_h3_k1_hits", "spy_h3_k2_hits", "spy_h3_k3_hits",
    "spy_h3_k3_cost_units", "spy_h3_k3_gross_units", "spy_h3_k3_net_units", "spy_h3_k3_roi_pct",
]

for _bucket in DECINA_HEAT_BUCKETS:
    _p = _bucket.lower()
    CSV_FIELDS.extend([
        f"decina_{_p}_sessions",
        f"decina_{_p}_closed",
        f"decina_{_p}_k1_hits",
        f"decina_{_p}_k2_hits",
        f"decina_{_p}_k3_hits",
        f"decina_{_p}_k2_colpo1",
        f"decina_{_p}_k2_colpo2",
        f"decina_{_p}_k3_colpo1",
        f"decina_{_p}_k3_colpo2",
        f"decina_{_p}_k3_cost_units",
        f"decina_{_p}_k3_gross_units",
        f"decina_{_p}_k3_net_units",
        f"decina_{_p}_k3_roi_pct",
    ])


for _h in AMBO_JOLLY_HORIZONS:
    CSV_FIELDS.extend([
        f"aj{_h}_sessions",
        f"aj{_h}_closed",
        f"aj{_h}_hits",
        f"aj{_h}_misses",
        f"aj{_h}_cost_units",
        f"aj{_h}_gross_units",
        f"aj{_h}_net_units",
        f"aj{_h}_roi_pct",
    ])


def ensure_csv():
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, "r", encoding="utf-8", newline="") as f:
                header = next(csv.reader(f), [])

            if header == CSV_FIELDS:
                return

            backup = CSV_FILE.replace(
                ".csv",
                f"_old_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            os.replace(CSV_FILE, backup)
        except Exception:
            backup = CSV_FILE.replace(
                ".csv",
                f"_old_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            try:
                os.replace(CSV_FILE, backup)
            except Exception:
                pass

    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()


# ============================================================
# BOT
# ============================================================

class SNIPER_V48:

    def __init__(self):
        self.version = "v48_final_research_spy_network_h123_lab"

        self.day = day_key()

        self.max_e = 0
        self.last_fp = None
        self.last_draws = []
        self.processed_ids = []
        self.processed_fps = []

        self.watch = {}
        self.hot_confirmed = {}

        # CORE v48
        self.active = False
        self.colpi = 0
        self.cooldown = 0
        self.active_snapshot = None

        self.last_cluster_numbers = []
        self.last_cluster_e = 0

        self.total_play = 0
        self.total_hit_ambata = 0  # mantiene semantica v48: eventi di uscita durante play
        self.total_hit_ambo = 0
        self.total_stop = 0

        # Monitor diagnostico: quale posizione dei 3 ambi v48 partecipa
        # al colpo vincente. Non modifica in alcun modo il CORE.
        self.v48_ambo_rank_hits = {"1": 0, "2": 0, "3": 0}
        self.v48_multi_ambo_hit_draws = 0

        self.play_uid = 0

        # TERNI LAB indipendente: lista per robustezza futura.
        self.terni_sessions = []
        self.terni_stats = {
            key: {"sessions": 0, "hit_sessions": 0}
            for key in LAB_STRATEGIES
        }

        # AMBATA RAFFICA 2 indipendente.
        self.ambata_r2_sessions = []
        self.ambata_r2_stats = {
            "sessions": 0,
            "hits": 0,
            "misses": 0,
            "hit_colpo1": 0,
            "hit_colpo2": 0,
        }

        # DECINA LAB 10-19 indipendente. Le sessioni possono sovrapporsi:
        # è intenzionale e replica il backtest cronologico per-ogni-segnale.
        self.decina_lab_uid = 0
        self.decina_lab_sessions = []
        self.decina_lab_stats = {
            "sessions": 0,
            "closed": 0,
            "k1_hits": 0,
            "k2_hits": 0,
            "k3_hits": 0,
            "k2_colpo1": 0,
            "k2_colpo2": 0,
            "k3_colpo1": 0,
            "k3_colpo2": 0,
            "k3_cost_units": 0.0,
            "k3_gross_units": 0.0,
        }
        self.decina_heat_stats = {
            bucket: self.new_decina_heat_stats()
            for bucket in DECINA_HEAT_BUCKETS
        }

        # DECINA MULTI-TERNO LAB indipendente.
        # Le sessioni CORE/PIVOT possono sovrapporsi e si fermano al primo
        # colpo vincente oppure al secondo colpo in caso di miss.
        self.decina_multi_uid = 0
        self.decina_multi_sessions = []
        self.decina_multi_stats = {
            "core": self.new_decina_multi_stats(),
            "pivot": self.new_decina_multi_stats(),
        }

        # AMBO-JOLLY AJ1: un solo terno = 1° ambo v48 + OP3.
        # Ogni orizzonte 2/3/4/7 ha contabilità autonoma ma viene
        # censurato quando il relativo PLAY v48 chiude.
        self.ambo_jolly_sessions = []
        self.ambo_jolly_stats = {
            str(h): self.new_ambo_jolly_stats(h)
            for h in AMBO_JOLLY_HORIZONS
        }

        # NUMERI SPIA LAB: sessioni indipendenti su orizzonti 1/2/3 colpi.
        self.spy_lab_uid = 0
        self.spy_lab_sessions = []
        self.spy_horizon_stats = {
            str(h): self.new_spy_lab_stats()
            for h in SPY_LAB_HORIZONS
        }
        self.spy_candidate_horizon_stats = {
            self.spy_candidate_key(c): {str(h): self.new_spy_lab_stats() for h in SPY_LAB_HORIZONS}
            for c in SPY_LAB_CANDIDATES
        }
        self.spy_network_horizon_stats = {
            network: {str(h): self.new_spy_lab_stats() for h in SPY_LAB_HORIZONS}
            for network in SPY_NETWORK_BUCKETS
        }
        self.spy_network_level_horizon_stats = {
            level: {str(h): self.new_spy_lab_stats() for h in SPY_LAB_HORIZONS}
            for level in SPY_NETWORK_LEVELS
        }

        # Alias legacy: i vecchi campi CSV mostrano l'orizzonte H1.
        self.spy_lab_stats = self.spy_horizon_stats["1"]
        self.spy_candidate_stats = {
            ckey: hstats["1"] for ckey, hstats in self.spy_candidate_horizon_stats.items()
        }
        self.spy_network_stats = {
            network: hstats["1"] for network, hstats in self.spy_network_horizon_stats.items()
        }
        self.spy_network_level_stats = {
            level: hstats["1"] for level, hstats in self.spy_network_level_horizon_stats.items()
        }

        self.load_state()
        ensure_csv()

    # ========================================================
    # TELEGRAM
    # ========================================================

    async def tg(self, app, msg):
        if not msg:
            return

        max_len = 3000
        chunks = [msg[i:i + max_len] for i in range(0, len(msg), max_len)]

        for chunk in chunks:
            for attempt in range(3):
                try:
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        text=chunk,
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=30,
                        pool_timeout=30,
                    )
                    break
                except Exception as ex:
                    print(f"Telegram send error attempt {attempt + 1}: {ex}")
                    await asyncio.sleep(5)

    # ========================================================
    # STATE
    # ========================================================

    @staticmethod
    def decina_heat_bucket(heat_total):
        heat_total = int(heat_total)
        if heat_total == 8:
            return "H8"
        if heat_total == 9:
            return "H9"
        return "H10P"

    @staticmethod
    def new_decina_heat_stats():
        return {
            "sessions": 0,
            "closed": 0,
            "k1_hits": 0,
            "k2_hits": 0,
            "k3_hits": 0,
            "k2_colpo1": 0,
            "k2_colpo2": 0,
            "k3_colpo1": 0,
            "k3_colpo2": 0,
            "k3_cost_units": 0.0,
            "k3_gross_units": 0.0,
        }

    @staticmethod
    def new_decina_multi_stats():
        return {
            "sessions": 0,
            "closed": 0,
            "winning_sessions": 0,
            "losing_sessions": 0,
            "hit_colpo1": 0,
            "hit_colpo2": 0,
            "winning_terni": 0,
            "multi_2plus_sessions": 0,
            "max_terni_same_draw": 0,
            "cost_units": 0.0,
            "gross_units": 0.0,
        }

    @staticmethod
    def new_ambo_jolly_stats(horizon):
        return {
            "horizon": int(horizon),
            "sessions": 0,
            "closed": 0,
            "hits": 0,
            "misses": 0,
            "cost_units": 0.0,
            "gross_units": 0.0,
            "hit_by_colpo": {str(i): 0 for i in range(1, int(horizon) + 1)},
        }

    @staticmethod
    def new_spy_lab_stats():
        return {
            "sessions": 0,
            "closed": 0,
            "k1_hits": 0,
            "k2_hits": 0,
            "k3_hits": 0,
            "k3_cost_units": 0.0,
            "k3_gross_units": 0.0,
        }

    @staticmethod
    def spy_candidate_key(candidate):
        return f"{int(candidate['spy'])}_{candidate['condition']}_{'-'.join(map(str, candidate['followers']))}"

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
            "cooldown": self.cooldown,
            "active_snapshot": self.active_snapshot,
            "last_cluster_numbers": self.last_cluster_numbers,
            "last_cluster_e": self.last_cluster_e,
            "total_play": self.total_play,
            "total_hit_ambata": self.total_hit_ambata,
            "total_hit_ambo": self.total_hit_ambo,
            "total_stop": self.total_stop,
            "v48_ambo_rank_hits": self.v48_ambo_rank_hits,
            "v48_multi_ambo_hit_draws": self.v48_multi_ambo_hit_draws,
            "play_uid": self.play_uid,
            "terni_sessions": self.terni_sessions,
            "terni_stats": self.terni_stats,
            "ambata_r2_sessions": self.ambata_r2_sessions,
            "ambata_r2_stats": self.ambata_r2_stats,
            "decina_lab_uid": self.decina_lab_uid,
            "decina_lab_sessions": self.decina_lab_sessions,
            "decina_lab_stats": self.decina_lab_stats,
            "decina_heat_stats": self.decina_heat_stats,
            "decina_multi_uid": self.decina_multi_uid,
            "decina_multi_sessions": self.decina_multi_sessions,
            "decina_multi_stats": self.decina_multi_stats,
            "ambo_jolly_sessions": self.ambo_jolly_sessions,
            "ambo_jolly_stats": self.ambo_jolly_stats,
            "spy_lab_uid": self.spy_lab_uid,
            "spy_lab_sessions": self.spy_lab_sessions,
            "spy_lab_stats": self.spy_lab_stats,
            "spy_candidate_stats": self.spy_candidate_stats,
            "spy_network_stats": self.spy_network_stats,
            "spy_network_level_stats": self.spy_network_level_stats,
            "spy_horizon_stats": self.spy_horizon_stats,
            "spy_candidate_horizon_stats": self.spy_candidate_horizon_stats,
            "spy_network_horizon_stats": self.spy_network_horizon_stats,
            "spy_network_level_horizon_stats": self.spy_network_level_horizon_stats,
        }

        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            return

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

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
            self.cooldown = int(data.get("cooldown", 0))
            self.active_snapshot = data.get("active_snapshot")

            self.last_cluster_numbers = data.get("last_cluster_numbers", [])
            self.last_cluster_e = int(data.get("last_cluster_e", 0))

            self.total_play = int(data.get("total_play", 0))
            self.total_hit_ambata = int(data.get("total_hit_ambata", 0))
            self.total_hit_ambo = int(data.get("total_hit_ambo", 0))
            self.total_stop = int(data.get("total_stop", 0))
            loaded_rank_hits = data.get("v48_ambo_rank_hits", {})
            self.v48_ambo_rank_hits = {
                str(i): int(loaded_rank_hits.get(str(i), 0))
                for i in (1, 2, 3)
            }
            self.v48_multi_ambo_hit_draws = int(data.get("v48_multi_ambo_hit_draws", 0))
            self.play_uid = int(data.get("play_uid", self.total_play))

            self.terni_sessions = data.get("terni_sessions", [])
            loaded_terni_stats = data.get("terni_stats", {})
            for key in LAB_STRATEGIES:
                src = loaded_terni_stats.get(key, {})
                self.terni_stats[key] = {
                    "sessions": int(src.get("sessions", 0)),
                    "hit_sessions": int(src.get("hit_sessions", 0)),
                }

            self.ambata_r2_sessions = data.get("ambata_r2_sessions", [])
            loaded_r2 = data.get("ambata_r2_stats", {})
            for key in self.ambata_r2_stats:
                self.ambata_r2_stats[key] = int(loaded_r2.get(key, 0))

            self.decina_lab_uid = int(data.get("decina_lab_uid", 0))
            self.decina_lab_sessions = data.get("decina_lab_sessions", [])
            loaded_decina = data.get("decina_lab_stats", {})
            for key in self.decina_lab_stats:
                value = loaded_decina.get(key, self.decina_lab_stats[key])
                self.decina_lab_stats[key] = (
                    float(value) if key in {"k3_cost_units", "k3_gross_units"}
                    else int(value)
                )

            loaded_heat = data.get("decina_heat_stats", {})
            for bucket in DECINA_HEAT_BUCKETS:
                src = loaded_heat.get(bucket, {})
                fresh = self.new_decina_heat_stats()
                for key, default in fresh.items():
                    value = src.get(key, default)
                    fresh[key] = (
                        float(value) if key in {"k3_cost_units", "k3_gross_units"}
                        else int(value)
                    )
                self.decina_heat_stats[bucket] = fresh

            self.decina_multi_uid = int(data.get("decina_multi_uid", 0))
            self.decina_multi_sessions = data.get("decina_multi_sessions", [])
            loaded_multi = data.get("decina_multi_stats", {})
            for package in ("core", "pivot"):
                src = loaded_multi.get(package, {})
                fresh = self.new_decina_multi_stats()
                for key, default in fresh.items():
                    value = src.get(key, default)
                    fresh[key] = float(value) if key in {"cost_units", "gross_units"} else int(value)
                self.decina_multi_stats[package] = fresh

            self.ambo_jolly_sessions = data.get("ambo_jolly_sessions", [])
            loaded_aj = data.get("ambo_jolly_stats", {})
            for horizon in AMBO_JOLLY_HORIZONS:
                hkey = str(horizon)
                src = loaded_aj.get(hkey, {})
                fresh = self.new_ambo_jolly_stats(horizon)
                for key in ("sessions", "closed", "hits", "misses"):
                    fresh[key] = int(src.get(key, fresh[key]))
                for key in ("cost_units", "gross_units"):
                    fresh[key] = float(src.get(key, fresh[key]))
                loaded_hits = src.get("hit_by_colpo", {})
                fresh["hit_by_colpo"] = {
                    str(i): int(loaded_hits.get(str(i), 0))
                    for i in range(1, horizon + 1)
                }
                self.ambo_jolly_stats[hkey] = fresh

            def _load_spy_stat(src):
                fresh = self.new_spy_lab_stats()
                src = src or {}
                for key, default in fresh.items():
                    value = src.get(key, default)
                    fresh[key] = float(value) if key in {"k3_cost_units", "k3_gross_units"} else int(value)
                return fresh

            self.spy_lab_uid = int(data.get("spy_lab_uid", 0))
            self.spy_lab_sessions = data.get("spy_lab_sessions", [])

            loaded_horizons = data.get("spy_horizon_stats", {})
            for h in SPY_LAB_HORIZONS:
                hkey = str(h)
                # compatibilita': se manca il nuovo formato, H1 prova dai vecchi campi.
                fallback = data.get("spy_lab_stats", {}) if hkey == "1" else {}
                self.spy_horizon_stats[hkey] = _load_spy_stat(loaded_horizons.get(hkey, fallback))
            self.spy_lab_stats = self.spy_horizon_stats["1"]

            loaded_candidate_h = data.get("spy_candidate_horizon_stats", {})
            loaded_candidate_legacy = data.get("spy_candidate_stats", {})
            for candidate in SPY_LAB_CANDIDATES:
                ckey = self.spy_candidate_key(candidate)
                self.spy_candidate_horizon_stats[ckey] = {}
                for h in SPY_LAB_HORIZONS:
                    hkey = str(h)
                    fallback = loaded_candidate_legacy.get(ckey, {}) if hkey == "1" else {}
                    self.spy_candidate_horizon_stats[ckey][hkey] = _load_spy_stat(
                        loaded_candidate_h.get(ckey, {}).get(hkey, fallback)
                    )
            self.spy_candidate_stats = {
                ckey: hstats["1"] for ckey, hstats in self.spy_candidate_horizon_stats.items()
            }

            loaded_network_h = data.get("spy_network_horizon_stats", {})
            loaded_network_legacy = data.get("spy_network_stats", {})
            for network in SPY_NETWORK_BUCKETS:
                self.spy_network_horizon_stats[network] = {}
                for h in SPY_LAB_HORIZONS:
                    hkey = str(h)
                    fallback = loaded_network_legacy.get(network, {}) if hkey == "1" else {}
                    self.spy_network_horizon_stats[network][hkey] = _load_spy_stat(
                        loaded_network_h.get(network, {}).get(hkey, fallback)
                    )
            self.spy_network_stats = {
                network: hstats["1"] for network, hstats in self.spy_network_horizon_stats.items()
            }

            loaded_level_h = data.get("spy_network_level_horizon_stats", {})
            loaded_level_legacy = data.get("spy_network_level_stats", {})
            for level in SPY_NETWORK_LEVELS:
                self.spy_network_level_horizon_stats[level] = {}
                for h in SPY_LAB_HORIZONS:
                    hkey = str(h)
                    fallback = loaded_level_legacy.get(level, {}) if hkey == "1" else {}
                    self.spy_network_level_horizon_stats[level][hkey] = _load_spy_stat(
                        loaded_level_h.get(level, {}).get(hkey, fallback)
                    )
            self.spy_network_level_stats = {
                level: hstats["1"] for level, hstats in self.spy_network_level_horizon_stats.items()
            }
        except Exception as ex:
            print(f"⚠️ Stato non caricato: {ex}")

    def reset_for_new_day(self, new_day):
        """
        Stessa filosofia operativa della versione precedente:
        reset dedup/watch/hot e play attivo; storico numerico conservato.
        Le sessioni LAB del giorno precedente vengono chiuse operativamente.
        """
        self.day = new_day

        self.max_e = 0
        self.last_fp = None
        self.processed_ids = []
        self.processed_fps = []

        self.watch = {}
        self.hot_confirmed = {}

        self.active = False
        self.colpi = 0
        self.cooldown = 0
        self.active_snapshot = None

        self.last_cluster_numbers = []
        self.last_cluster_e = 0

        # Non attraversiamo il cambio giorno con sessioni aperte.
        self.terni_sessions = []
        self.ambata_r2_sessions = []
        self.decina_lab_sessions = []
        self.decina_multi_sessions = []
        self.ambo_jolly_sessions = []
        self.spy_lab_sessions = []

        self.save_state()

    # ========================================================
    # CSV EVENTS
    # ========================================================

    def append_csv_event(
        self,
        event,
        *,
        play=None,
        play_id=None,
        e=None,
        colpo=None,
        session_type="",
        strategy="",
        jolly=None,
        terni=None,
        hit_list=None,
        outcome="",
        decina_signal_id=None,
        decina_top3=None,
        decina_heat_total=None,
        decina_hit_numbers=None,
        decina_multi_signal_id=None,
        decina_multi_package="",
        decina_top5=None,
        decina_package_terni=None,
        decina_terni_hit_count=None,
        ambo_jolly_terno=None,
        ambo_jolly_rank1_ambo=None,
        ambo_jolly_op3=None,
        ambo_jolly_horizon=None,
        spy_signal_id=None,
        spy_number=None,
        spy_condition="",
        spy_network="",
        spy_network_level="",
        spy_active_related=None,
        spy_active_total=None,
        spy_followers=None,
        spy_hit_numbers=None,
        spy_k_hit=None,
    ):
        ensure_csv()

        snap = play or self.active_snapshot or {}

        row = {
            "time": now_txt(),
            "day": self.day,
            "event": event,
            "play_id": play_id if play_id is not None else snap.get("play_id", ""),
            "estrazione": e if e is not None else "",
            "colpo": colpo if colpo is not None else "",
            "session_type": session_type,
            "strategy": strategy,
            "ambata": snap.get("ambata", ""),
            "ambi": fmt_ambi(snap.get("ambi", [])),
            "cluster": fmt_nums(snap.get("cluster_numbers", [])),
            "jolly": fmt_jolly(jolly),
            "terni": fmt_terni(terni),
            "hit_list": fmt_terni(hit_list),
            "outcome": outcome,
            "v48_total_play": self.total_play,
            "v48_hit_ambata_events": self.total_hit_ambata,
            "v48_hit_ambo": self.total_hit_ambo,
            "v48_stop": self.total_stop,
            "v48_rank1_hit_events": self.v48_ambo_rank_hits["1"],
            "v48_rank2_hit_events": self.v48_ambo_rank_hits["2"],
            "v48_rank3_hit_events": self.v48_ambo_rank_hits["3"],
            "v48_multi_ambo_hit_draws": self.v48_multi_ambo_hit_draws,
            "op3_sessions": self.terni_stats["op3"]["sessions"],
            "op3_hit_sessions": self.terni_stats["op3"]["hit_sessions"],
            "op9_sessions": self.terni_stats["op9"]["sessions"],
            "op9_hit_sessions": self.terni_stats["op9"]["hit_sessions"],
            "op6_sessions": self.terni_stats["op6"]["sessions"],
            "op6_hit_sessions": self.terni_stats["op6"]["hit_sessions"],
            "op7_sessions": self.terni_stats["op7"]["sessions"],
            "op7_hit_sessions": self.terni_stats["op7"]["hit_sessions"],
            "ambata_r2_sessions": self.ambata_r2_stats["sessions"],
            "ambata_r2_hits": self.ambata_r2_stats["hits"],
            "ambata_r2_misses": self.ambata_r2_stats["misses"],
            "ambata_r2_hit_colpo1": self.ambata_r2_stats["hit_colpo1"],
            "ambata_r2_hit_colpo2": self.ambata_r2_stats["hit_colpo2"],
            "decina_signal_id": decina_signal_id if decina_signal_id is not None else "",
            "decina_top3": fmt_nums(decina_top3),
            "decina_heat_total": decina_heat_total if decina_heat_total is not None else "",
            "decina_hit_numbers": fmt_nums(decina_hit_numbers),
            "decina_sessions": self.decina_lab_stats["sessions"],
            "decina_closed": self.decina_lab_stats["closed"],
            "decina_k1_hits": self.decina_lab_stats["k1_hits"],
            "decina_k2_hits": self.decina_lab_stats["k2_hits"],
            "decina_k3_hits": self.decina_lab_stats["k3_hits"],
            "decina_k2_colpo1": self.decina_lab_stats["k2_colpo1"],
            "decina_k2_colpo2": self.decina_lab_stats["k2_colpo2"],
            "decina_k3_colpo1": self.decina_lab_stats["k3_colpo1"],
            "decina_k3_colpo2": self.decina_lab_stats["k3_colpo2"],
            "decina_k3_cost_units": f"{float(self.decina_lab_stats['k3_cost_units']):.2f}",
            "decina_k3_gross_units": f"{float(self.decina_lab_stats['k3_gross_units']):.2f}",
            "decina_k3_net_units": f"{float(self.decina_lab_stats['k3_gross_units']) - float(self.decina_lab_stats['k3_cost_units']):.2f}",
            "decina_k3_roi_pct": f"{(((float(self.decina_lab_stats['k3_gross_units']) - float(self.decina_lab_stats['k3_cost_units'])) / float(self.decina_lab_stats['k3_cost_units']) * 100.0) if float(self.decina_lab_stats['k3_cost_units']) else 0.0):.4f}",
            "decina_multi_signal_id": decina_multi_signal_id if decina_multi_signal_id is not None else "",
            "decina_multi_package": decina_multi_package,
            "decina_top5": fmt_nums(decina_top5),
            "decina_package_terni": fmt_terni(decina_package_terni),
            "decina_terni_hit_count": decina_terni_hit_count if decina_terni_hit_count is not None else "",
            "ambo_jolly_terno": fmt_terni([ambo_jolly_terno]) if ambo_jolly_terno else "",
            "ambo_jolly_rank1_ambo": fmt_nums(ambo_jolly_rank1_ambo),
            "ambo_jolly_op3": ambo_jolly_op3 if ambo_jolly_op3 is not None else "",
            "ambo_jolly_horizon": ambo_jolly_horizon if ambo_jolly_horizon is not None else "",
            "spy_signal_id": spy_signal_id if spy_signal_id is not None else "",
            "spy_number": spy_number if spy_number is not None else "",
            "spy_condition": spy_condition,
            "spy_network": spy_network,
            "spy_network_level": spy_network_level,
            "spy_active_related": spy_active_related if spy_active_related is not None else "",
            "spy_active_total": spy_active_total if spy_active_total is not None else "",
            "spy_followers": fmt_nums(spy_followers),
            "spy_hit_numbers": fmt_nums(spy_hit_numbers),
            "spy_k_hit": spy_k_hit if spy_k_hit is not None else "",
            "spy_sessions": self.spy_lab_stats["sessions"],
            "spy_closed": self.spy_lab_stats["closed"],
            "spy_k1_hits": self.spy_lab_stats["k1_hits"],
            "spy_k2_hits": self.spy_lab_stats["k2_hits"],
            "spy_k3_hits": self.spy_lab_stats["k3_hits"],
            "spy_k3_cost_units": f"{float(self.spy_lab_stats['k3_cost_units']):.2f}",
            "spy_k3_gross_units": f"{float(self.spy_lab_stats['k3_gross_units']):.2f}",
            "spy_k3_net_units": f"{float(self.spy_lab_stats['k3_gross_units']) - float(self.spy_lab_stats['k3_cost_units']):.2f}",
            "spy_k3_roi_pct": f"{(((float(self.spy_lab_stats['k3_gross_units']) - float(self.spy_lab_stats['k3_cost_units'])) / float(self.spy_lab_stats['k3_cost_units']) * 100.0) if float(self.spy_lab_stats['k3_cost_units']) else 0.0):.4f}",
        }

        # Campi cumulativi horizon-specific per NUMERI SPIA LAB.
        for _h in SPY_LAB_HORIZONS:
            _hkey = str(_h)
            _st = self.spy_horizon_stats.get(_hkey, self.new_spy_lab_stats())
            _cost = float(_st.get("k3_cost_units", 0.0))
            _gross = float(_st.get("k3_gross_units", 0.0))
            _net = _gross - _cost
            _roi = (_net / _cost * 100.0) if _cost else 0.0
            row.update({
                f"spy_h{_h}_sessions": _st.get("sessions", 0),
                f"spy_h{_h}_closed": _st.get("closed", 0),
                f"spy_h{_h}_k1_hits": _st.get("k1_hits", 0),
                f"spy_h{_h}_k2_hits": _st.get("k2_hits", 0),
                f"spy_h{_h}_k3_hits": _st.get("k3_hits", 0),
                f"spy_h{_h}_k3_cost_units": f"{_cost:.2f}",
                f"spy_h{_h}_k3_gross_units": f"{_gross:.2f}",
                f"spy_h{_h}_k3_net_units": f"{_net:.2f}",
                f"spy_h{_h}_k3_roi_pct": f"{_roi:.4f}",
            })

        for bucket in DECINA_HEAT_BUCKETS:
            st = self.decina_heat_stats[bucket]
            p = bucket.lower()
            cost = float(st["k3_cost_units"])
            gross = float(st["k3_gross_units"])
            net = gross - cost
            roi = (net / cost * 100.0) if cost else 0.0
            row.update({
                f"decina_{p}_sessions": st["sessions"],
                f"decina_{p}_closed": st["closed"],
                f"decina_{p}_k1_hits": st["k1_hits"],
                f"decina_{p}_k2_hits": st["k2_hits"],
                f"decina_{p}_k3_hits": st["k3_hits"],
                f"decina_{p}_k2_colpo1": st["k2_colpo1"],
                f"decina_{p}_k2_colpo2": st["k2_colpo2"],
                f"decina_{p}_k3_colpo1": st["k3_colpo1"],
                f"decina_{p}_k3_colpo2": st["k3_colpo2"],
                f"decina_{p}_k3_cost_units": f"{cost:.2f}",
                f"decina_{p}_k3_gross_units": f"{gross:.2f}",
                f"decina_{p}_k3_net_units": f"{net:.2f}",
                f"decina_{p}_k3_roi_pct": f"{roi:.4f}",
            })

        for package in ("core", "pivot"):
            st = self.decina_multi_stats[package]
            cost = float(st["cost_units"])
            gross = float(st["gross_units"])
            net = gross - cost
            roi = (net / cost * 100.0) if cost else 0.0
            row.update({
                f"{package}_sessions": st["sessions"],
                f"{package}_closed": st["closed"],
                f"{package}_winning_sessions": st["winning_sessions"],
                f"{package}_losing_sessions": st["losing_sessions"],
                f"{package}_hit_colpo1": st["hit_colpo1"],
                f"{package}_hit_colpo2": st["hit_colpo2"],
                f"{package}_winning_terni": st["winning_terni"],
                f"{package}_multi_2plus_sessions": st["multi_2plus_sessions"],
                f"{package}_max_terni_same_draw": st["max_terni_same_draw"],
                f"{package}_cost_units": f"{cost:.2f}",
                f"{package}_gross_units": f"{gross:.2f}",
                f"{package}_net_units": f"{net:.2f}",
                f"{package}_roi_pct": f"{roi:.4f}",
            })

        for horizon in AMBO_JOLLY_HORIZONS:
            hkey = str(horizon)
            st = self.ambo_jolly_stats[hkey]
            cost = float(st["cost_units"])
            gross = float(st["gross_units"])
            net = gross - cost
            roi = (net / cost * 100.0) if cost else 0.0
            row.update({
                f"aj{horizon}_sessions": st["sessions"],
                f"aj{horizon}_closed": st["closed"],
                f"aj{horizon}_hits": st["hits"],
                f"aj{horizon}_misses": st["misses"],
                f"aj{horizon}_cost_units": f"{cost:.2f}",
                f"aj{horizon}_gross_units": f"{gross:.2f}",
                f"aj{horizon}_net_units": f"{net:.2f}",
                f"aj{horizon}_roi_pct": f"{roi:.4f}",
            })

        with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow(row)

    # ========================================================
    # DEDUP / STARTUP
    # ========================================================

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

    def preload_today_as_processed(self, es):
        """Carica lo storico visibile e marca TUTTO come processato."""
        for e, nums in es:
            if len(set(nums)) != 20:
                continue

            self.last_draws.append(nums)
            self.processed_ids.append(e)
            self.processed_fps.append(fingerprint(e, nums))

        self.last_draws = self.last_draws[-HISTORY_MAX:]
        self.processed_ids = self.processed_ids[-PROCESSED_MAX:]
        self.processed_fps = self.processed_fps[-PROCESSED_MAX:]

        if es:
            last_e, last_nums = es[-1]
            self.max_e = last_e
            self.last_fp = fingerprint(last_e, last_nums)

        self.save_state()

    # ========================================================
    # FEATURES — STESSE DEL CODICE v48/LAB PRECEDENTE
    # ========================================================

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
            if i < len(self.last_draws)
            and n in self.last_draws[-(i + 1)]
        )

    def dominance(self, n, window=6):
        return sum(1 for d in self.last_draws[-window:] if n in d)

    def pressure(self, n):
        weights = [5, 4, 3, 2, 1]
        return sum(
            w for i, w in enumerate(weights)
            if i < len(self.last_draws)
            and n in self.last_draws[-(i + 1)]
        )

    def recent_frequency(self, n, window=20):
        return sum(1 for d in self.last_draws[-window:] if n in d)

    def decina_numbers(self, n):
        start = ((int(n) - 1) // 10) * 10 + 1
        end = min(start + 9, 90)
        return list(range(start, end + 1))

    def build_terni_single_jolly(self, ambi, jolly):
        terni = []

        if not jolly:
            return terni

        for item in ambi:
            a, b = item["ambo"]
            if jolly not in (a, b):
                terni.append(tuple(sorted((a, b, int(jolly)))))

        return sorted(set(terni))

    def best_by_score(self, candidates, e):
        clean = [int(n) for n in candidates if 1 <= int(n) <= 90]

        if not clean:
            return None

        clean = sorted(set(clean))
        clean.sort(
            key=lambda n: (
                -self.number_score(n, e),
                -self.recent_frequency(n, 20),
                self.lag(n),
                n,
            )
        )
        return clean[0]

    # ========================================================
    # TOP RITARDATARI — CORE v48
    # ========================================================

    def top_ritardatari(self):
        data = []

        for n in range(1, 91):
            data.append({"number": n, "lag": self.lag(n)})

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
                    "lag": top10[idx]["lag"],
                })

        return top10, selected

    # ========================================================
    # CLEAN WATCH/HOT — CORE v48
    # ========================================================

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

    def update_watch_and_confirmed(self, e, nums, selected):
        s = set(nums)

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
                    "initial_lag": item["lag"],
                }
            else:
                self.watch[key]["hits"] += 1
                self.watch[key]["last_e"] = e

                if self.watch[key]["hits"] >= 2:
                    self.hot_confirmed[key] = {
                        **self.watch[key],
                        "confirmed_e": e,
                    }
                    self.watch.pop(key, None)

        self.clean_old_watch(e)
        self.clean_old_hot(e)

    # ========================================================
    # SCORE — INVARIATO
    # ========================================================

    def confirmed_score(self, item, e):
        n = int(item["number"])
        age = e - int(item["confirmed_e"])

        return (
            item["hits"] * 20
            - age * 2
            + item["initial_lag"]
            + self.heat(n)
            + self.dominance(n, 6) * 3
            + self.pressure(n)
        )

    def number_score(self, n, e):
        hot = self.hot_confirmed.get(str(n))
        hot_score = 0

        if hot:
            hot_score = self.confirmed_score(hot, e)

        return (
            hot_score
            + self.heat(n) * 2
            + self.dominance(n, 6) * 3
            + self.pressure(n)
            - self.lag(n)
        )

    # ========================================================
    # DUPLICATE CLUSTER — CORE v48
    # ========================================================

    def duplicate_cluster(self, cluster_numbers, e):
        if not self.last_cluster_numbers:
            return False

        if e - self.last_cluster_e >= CLUSTER_REUSE_AFTER:
            return False

        overlap = len(set(cluster_numbers) & set(self.last_cluster_numbers))
        return overlap >= 2

    # ========================================================
    # BUILD PLAY
    # ========================================================

    def build_play(self, e):
        hot_items = [
            x for x in self.hot_confirmed.values()
            if 0 <= e - int(x["confirmed_e"]) <= HOT_TTL
        ]

        if len(hot_items) < MIN_HOT_ACTIVE:
            return None

        pair_candidates = []

        # ==================================================
        # MOTORE v48 ORIGINALE: NON MODIFICARE
        # ==================================================
        for a, b in combinations(hot_items, 2):
            pair = tuple(sorted((int(a["number"]), int(b["number"]))))
            score = self.confirmed_score(a, e) + self.confirmed_score(b, e)

            pair_candidates.append({
                "ambo": pair,
                "score": round(score, 2),
            })

        pair_candidates.sort(key=lambda x: -x["score"])
        ambi = pair_candidates[:MAX_AMBI_PER_PLAY]

        if not ambi:
            return None

        all_numbers = []
        for item in ambi:
            all_numbers.extend(item["ambo"])

        cluster_numbers = sorted(set(all_numbers))

        if self.duplicate_cluster(cluster_numbers, e):
            return None

        freq = Counter(all_numbers)
        ambata = freq.most_common(1)[0][0]

        # ==================================================
        # DA QUI IN POI: SOLO LAB PARALLELO
        # ==================================================
        outside_cluster = [n for n in range(1, 91) if n not in cluster_numbers]

        # OP3 — miglior score assoluto fuori cluster (PRIMARY)
        all_scores = [(n, self.number_score(n, e)) for n in outside_cluster]
        all_scores.sort(key=lambda x: -x[1])
        terno_num_3 = all_scores[0][0] if all_scores else None

        # OP6 — miglior numero stessa decina ambata
        decina_ambata = [
            n for n in self.decina_numbers(ambata)
            if n not in cluster_numbers
        ]
        terno_num_6 = self.best_by_score(decina_ambata, e)

        # OP7 — stessa decina dinamica per singolo ambo
        terni_op7 = []
        terno_num_7 = []

        for item in ambi:
            a, b = item["ambo"]
            decina_candidates = set(self.decina_numbers(a)) | set(self.decina_numbers(b))
            decina_candidates = [
                n for n in decina_candidates
                if n not in cluster_numbers
            ]

            jolly = self.best_by_score(decina_candidates, e)
            if jolly:
                terno_num_7.append(jolly)
                terni_op7.append(tuple(sorted((a, b, jolly))))

        terno_num_7 = sorted(set(terno_num_7))
        terni_op7 = sorted(set(terni_op7))

        # OP9 — mix score + ritardo + frequenza recente (CONTROL)
        mix_candidates = []

        for n in outside_cluster:
            mix = (
                self.number_score(n, e)
                + self.lag(n) * 0.60
                + self.recent_frequency(n, 20) * 2.00
                + self.recent_frequency(n, 60) * 0.50
            )
            mix_candidates.append((n, mix))

        mix_candidates.sort(key=lambda x: (-x[1], x[0]))
        terno_num_9 = mix_candidates[0][0] if mix_candidates else None

        terni_op3 = self.build_terni_single_jolly(ambi, terno_num_3)
        terni_op6 = self.build_terni_single_jolly(ambi, terno_num_6)
        terni_op9 = self.build_terni_single_jolly(ambi, terno_num_9)

        return {
            "ambata": ambata,
            "ambi": ambi,
            "cluster_numbers": cluster_numbers,
            "terno_num_3": terno_num_3,
            "terni_op3": terni_op3,
            "terno_num_9": terno_num_9,
            "terni_op9": terni_op9,
            "terno_num_6": terno_num_6,
            "terni_op6": terni_op6,
            "terno_num_7": terno_num_7,
            "terni_op7": terni_op7,
        }

    # ========================================================
    # CHECK CORE v48
    # ========================================================

    def check_v48_hit(self, nums):
        s = set(nums)
        snap = self.active_snapshot

        ambata_hit = snap["ambata"] in s
        ambi_hit = []

        for item in snap["ambi"]:
            a, b = item["ambo"]
            if a in s and b in s:
                ambi_hit.append(item)

        return {
            "ambata_hit": ambata_hit,
            "ambi_hit": ambi_hit,
        }

    # ========================================================
    # DECINA LAB 10-19 — HEAT 5 / TOP 3 / SOGLIA >= 8
    # ========================================================

    def build_decina_10_19_signal(self):
        """Costruisce un segnale solo dal passato già noto.

        Regola identica al backtest:
        - ultime 5 estrazioni
        - per 10..19 conta presenze
        - tie-break: conteggio, poi recenza pesata 1..5, poi numero minore
        - TOP 3
        - segnale solo se somma conteggi TOP 3 >= 8

        La sessione aperta DOPO l'estrazione corrente viene verificata
        esclusivamente sulle 2 estrazioni future successive.
        """
        if len(self.last_draws) < DECINA_LAB_WINDOW:
            return None

        hist = self.last_draws[-DECINA_LAB_WINDOW:]
        ranked = []

        for n in DECINA_LAB_NUMBERS:
            count = sum(1 for draw in hist if n in draw)
            recency_weighted = sum(
                weight
                for weight, draw in enumerate(hist, start=1)
                if n in draw
            )
            ranked.append((n, count, recency_weighted))

        ranked.sort(key=lambda x: (-x[1], -x[2], x[0]))
        top = ranked[:DECINA_LAB_TOP_N]
        top5_rows = ranked[:DECINA_MULTI_TOP_N]
        top3 = [int(x[0]) for x in top]
        top5 = [int(x[0]) for x in top5_rows]
        heat_counts = [int(x[1]) for x in top]
        top5_heat_counts = [int(x[1]) for x in top5_rows]
        heat_total = sum(heat_counts)

        if heat_total < DECINA_LAB_HEAT_THRESHOLD:
            return None

        return {
            "top3": top3,
            "top5": top5,
            "heat_counts": heat_counts,
            "top5_heat_counts": top5_heat_counts,
            "heat_total": int(heat_total),
        }

    async def maybe_open_decina_10_19_session(self, app, e):
        signal = self.build_decina_10_19_signal()
        if not signal:
            return

        self.decina_lab_uid += 1
        session = {
            "signal_id": self.decina_lab_uid,
            "day": self.day,
            "origin_e": e,
            "colpi": 0,
            "max_colpi": DECINA_LAB_MAX_COLPI,
            "top3": signal["top3"],
            "top5": signal.get("top5", signal["top3"]),
            "heat_counts": signal["heat_counts"],
            "heat_total": signal["heat_total"],
            "heat_bucket": self.decina_heat_bucket(signal["heat_total"]),
            "k3_bet_closed": False,
            "k1_hit": False,
            "k2_hit": False,
            "k3_hit": False,
            "k1_first_colpo": None,
            "k2_first_colpo": None,
            "k3_first_colpo": None,
        }
        self.decina_lab_sessions.append(session)
        self.decina_lab_stats["sessions"] += 1
        self.decina_heat_stats[session["heat_bucket"]]["sessions"] += 1

        self.append_csv_event(
            "DECINA_10_19_OPEN",
            e=e,
            colpo=0,
            session_type="DECINA_10_19_H5_T2",
            strategy="DECINA_10_19_TOP3_HEAT5",
            outcome="OPEN",
            decina_signal_id=session["signal_id"],
            decina_top3=session["top3"],
            decina_heat_total=session["heat_total"],
        )

        if DECINA_LAB_NOTIFY:
            await self.tg(
                app,
                "🔥 DECINA LAB 10-19 — SEGNALE\n"
                f"• signal_id = {session['signal_id']}\n"
                f"• TOP 3 Heat 5 = {fmt_nums(session['top3'])}\n"
                f"• conteggi = {fmt_nums(session['heat_counts'])}\n"
                f"• Heat totale = {session['heat_total']}\n"
                f"• fascia monitor = {session['heat_bucket']}" + (" ⭐ PRIORITARIA" if session["heat_bucket"] == "H9" else "") + "\n"
                f"• soglia = {DECINA_LAB_HEAT_THRESHOLD}\n"
                f"• osservazione = prossimi {DECINA_LAB_MAX_COLPI} colpi\n"
                "• target principale = almeno 2 dei 3 insieme"
            )

        # CORE/PIVOT si aprono solo nella fascia Heat >= 9.
        if signal["heat_total"] >= DECINA_MULTI_HEAT_THRESHOLD:
            await self.open_decina_multi_sessions(app, e, signal)

    @staticmethod
    def build_decina_multi_packages(top5):
        if len(top5) < 5:
            return {}

        a, b, c, d, e = map(int, top5[:5])
        core = normalize_terni([
            (a, b, c),
            (a, b, d),
            (a, b, e),
        ])
        pivot = normalize_terni(
            (a, x, y)
            for x, y in combinations((b, c, d, e), 2)
        )
        return {"core": core, "pivot": pivot}

    async def open_decina_multi_sessions(self, app, e, signal):
        top5 = [int(n) for n in signal.get("top5", [])]
        packages = self.build_decina_multi_packages(top5)
        if not packages:
            return

        self.decina_multi_uid += 1
        multi_signal_id = self.decina_multi_uid

        for package in ("core", "pivot"):
            terni = packages[package]
            session = {
                "multi_signal_id": multi_signal_id,
                "package": package,
                "day": self.day,
                "origin_e": e,
                "colpi": 0,
                "max_colpi": DECINA_MULTI_MAX_COLPI,
                "top5": top5,
                "heat_total": int(signal["heat_total"]),
                "terni": [list(t) for t in terni],
            }
            self.decina_multi_sessions.append(session)
            self.decina_multi_stats[package]["sessions"] += 1

            self.append_csv_event(
                f"DECINA_MULTI_{package.upper()}_OPEN",
                e=e,
                colpo=0,
                session_type=f"DECINA_MULTI_{package.upper()}_H5_T2",
                strategy=f"DECINA_{package.upper()}_HEAT5",
                terni=terni,
                outcome="OPEN",
                decina_multi_signal_id=multi_signal_id,
                decina_multi_package=package,
                decina_top5=top5,
                decina_package_terni=terni,
                decina_heat_total=signal["heat_total"],
            )

        if DECINA_MULTI_NOTIFY:
            core = packages["core"]
            pivot = packages["pivot"]
            await self.tg(
                app,
                "🧪 DECINA MULTI-TERNO 10-19 — SEGNALE\n"
                f"• multi_signal_id = {multi_signal_id}\n"
                f"• TOP 5 Heat = {fmt_nums(top5)}\n"
                f"• Heat TOP3 = {signal['heat_total']} (soglia >= {DECINA_MULTI_HEAT_THRESHOLD})\n\n"
                f"🔷 CORE TOP2 — {len(core)} terni\n"
                f"{fmt_terni(core)}\n\n"
                f"🔶 PIVOT — {len(pivot)} terni\n"
                f"{fmt_terni(pivot)}\n\n"
                f"• osservazione = prossimi {DECINA_MULTI_MAX_COLPI} colpi\n"
                "• stop pacchetto = primo colpo vincente"
            )

    async def process_decina_multi_sessions(self, app, e, nums):
        if not self.decina_multi_sessions:
            return

        draw_set = set(nums)
        survivors = []

        for session in self.decina_multi_sessions:
            package = session["package"]
            st = self.decina_multi_stats[package]
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = session["colpi"]
            terni = normalize_terni(session.get("terni", []))

            # Una unita' per ogni terno del pacchetto a ogni colpo giocato.
            st["cost_units"] += float(len(terni))

            hits = [t for t in terni if set(t).issubset(draw_set)]
            hit_count = len(hits)

            if hit_count > 0:
                st["closed"] += 1
                st["winning_sessions"] += 1
                st["winning_terni"] += hit_count
                st["max_terni_same_draw"] = max(st["max_terni_same_draw"], hit_count)
                if hit_count >= 2:
                    st["multi_2plus_sessions"] += 1
                if colpo == 1:
                    st["hit_colpo1"] += 1
                elif colpo == 2:
                    st["hit_colpo2"] += 1
                st["gross_units"] += float(hit_count) * DECINA_TERNO_PAYOUT

                self.append_csv_event(
                    f"DECINA_MULTI_{package.upper()}_HIT",
                    e=e,
                    colpo=colpo,
                    session_type=f"DECINA_MULTI_{package.upper()}_H5_T2",
                    strategy=f"DECINA_{package.upper()}_HEAT5",
                    terni=terni,
                    hit_list=hits,
                    outcome=f"HIT_{hit_count}_TERNI",
                    decina_multi_signal_id=session["multi_signal_id"],
                    decina_multi_package=package,
                    decina_top5=session.get("top5", []),
                    decina_package_terni=terni,
                    decina_terni_hit_count=hit_count,
                    decina_heat_total=session.get("heat_total"),
                )

                if DECINA_MULTI_NOTIFY:
                    label = "CORE TOP2" if package == "core" else "PIVOT"
                    await self.tg(
                        app,
                        f"💥 DECINA {label} — HIT TERNO\n"
                        f"• multi_signal_id = {session['multi_signal_id']}\n"
                        f"• colpo = {colpo}\n"
                        f"• Heat origine = {session.get('heat_total')}\n"
                        f"• terni presi insieme = {hit_count}\n"
                        f"• hit = {fmt_terni(hits)}"
                    )
                # Stop al primo colpo vincente: non sopravvive.
                continue

            if colpo >= int(session.get("max_colpi", DECINA_MULTI_MAX_COLPI)):
                st["closed"] += 1
                st["losing_sessions"] += 1
                self.append_csv_event(
                    f"DECINA_MULTI_{package.upper()}_MISS",
                    e=e,
                    colpo=colpo,
                    session_type=f"DECINA_MULTI_{package.upper()}_H5_T2",
                    strategy=f"DECINA_{package.upper()}_HEAT5",
                    terni=terni,
                    outcome="MISS",
                    decina_multi_signal_id=session["multi_signal_id"],
                    decina_multi_package=package,
                    decina_top5=session.get("top5", []),
                    decina_package_terni=terni,
                    decina_terni_hit_count=0,
                    decina_heat_total=session.get("heat_total"),
                )
                continue

            survivors.append(session)

        self.decina_multi_sessions = survivors

    async def process_decina_10_19_sessions(self, app, e, nums):
        if not self.decina_lab_sessions:
            return

        draw_set = set(nums)
        survivors = []

        for session in self.decina_lab_sessions:
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = session["colpi"]
            top3 = [int(n) for n in session.get("top3", [])]
            hit_numbers = [n for n in top3 if n in draw_set]
            count = len(hit_numbers)
            bucket = session.get("heat_bucket") or self.decina_heat_bucket(session.get("heat_total", 8))
            session["heat_bucket"] = bucket
            bst = self.decina_heat_stats[bucket]

            # Simulazione economica del singolo terno TOP3:
            # 1 unita' per colpo, massimo 2, stop economico sul primo K3.
            if not session.get("k3_bet_closed", False):
                self.decina_lab_stats["k3_cost_units"] += 1.0
                bst["k3_cost_units"] += 1.0

            newly_hit = []
            for k, flag_key, first_key, stat_key in (
                (1, "k1_hit", "k1_first_colpo", "k1_hits"),
                (2, "k2_hit", "k2_first_colpo", "k2_hits"),
                (3, "k3_hit", "k3_first_colpo", "k3_hits"),
            ):
                if count >= k and not session.get(flag_key, False):
                    session[flag_key] = True
                    session[first_key] = colpo
                    self.decina_lab_stats[stat_key] += 1
                    bst[stat_key] += 1
                    newly_hit.append(k)

                    if k == 2:
                        if colpo == 1:
                            self.decina_lab_stats["k2_colpo1"] += 1
                            bst["k2_colpo1"] += 1
                        elif colpo == 2:
                            self.decina_lab_stats["k2_colpo2"] += 1
                            bst["k2_colpo2"] += 1

                    if k == 3:
                        if colpo == 1:
                            self.decina_lab_stats["k3_colpo1"] += 1
                            bst["k3_colpo1"] += 1
                        elif colpo == 2:
                            self.decina_lab_stats["k3_colpo2"] += 1
                            bst["k3_colpo2"] += 1

                        if not session.get("k3_bet_closed", False):
                            self.decina_lab_stats["k3_gross_units"] += DECINA_BASE_K3_PAYOUT
                            bst["k3_gross_units"] += DECINA_BASE_K3_PAYOUT
                            session["k3_bet_closed"] = True

                    self.append_csv_event(
                        f"DECINA_10_19_FIRST_HIT_K{k}",
                        e=e,
                        colpo=colpo,
                        session_type="DECINA_10_19_H5_T2",
                        strategy=f"DECINA_K{k}_{bucket}",
                        outcome="HIT",
                        decina_signal_id=session["signal_id"],
                        decina_top3=top3,
                        decina_heat_total=session.get("heat_total"),
                        decina_hit_numbers=hit_numbers,
                    )

            # Telegram: K2/K3; H9 viene marcata come fascia prioritaria.
            if DECINA_LAB_NOTIFY and (2 in newly_hit or 3 in newly_hit):
                label = "TRIS 3/3" if count == 3 else "ALMENO 2/3"
                priority = " ⭐ HEAT 9" if bucket == "H9" else ""
                await self.tg(
                    app,
                    f"💥 DECINA LAB 10-19 — {label}{priority}\n"
                    f"• signal_id = {session['signal_id']}\n"
                    f"• colpo = {colpo}\n"
                    f"• TOP 3 = {fmt_nums(top3)}\n"
                    f"• usciti insieme = {fmt_nums(hit_numbers)}\n"
                    f"• Heat origine = {session.get('heat_total')} ({bucket})"
                )

            if colpo >= int(session.get("max_colpi", DECINA_LAB_MAX_COLPI)):
                self.decina_lab_stats["closed"] += 1
                bst["closed"] += 1
                outcome = (
                    f"K1={'HIT' if session.get('k1_hit') else 'MISS'};"
                    f"K2={'HIT' if session.get('k2_hit') else 'MISS'};"
                    f"K3={'HIT' if session.get('k3_hit') else 'MISS'};"
                    f"BUCKET={bucket}"
                )
                self.append_csv_event(
                    "DECINA_10_19_CLOSE",
                    e=e,
                    colpo=colpo,
                    session_type="DECINA_10_19_H5_T2",
                    strategy=f"DECINA_10_19_TOP3_HEAT5_{bucket}",
                    outcome=outcome,
                    decina_signal_id=session["signal_id"],
                    decina_top3=top3,
                    decina_heat_total=session.get("heat_total"),
                    decina_hit_numbers=hit_numbers,
                )
            else:
                survivors.append(session)

        self.decina_lab_sessions = survivors

    # ========================================================
    # NUMERI SPIA LAB
    # ========================================================

    def spy_condition_met(self, spy, condition):
        """Valuta la condizione sullo storico incluso il colpo corrente.

        C2_exact: spy presente negli ultimi 2 colpi e assente nel terzo precedente.
        C3plus: spy presente negli ultimi 3 colpi consecutivi.
        C1_exact: spy presente solo nell'ultimo colpo, non nel precedente.
        """
        spy = int(spy)
        if condition == "C1_exact":
            if len(self.last_draws) < 2:
                return False
            return spy in self.last_draws[-1] and spy not in self.last_draws[-2]
        if condition == "C2_exact":
            if len(self.last_draws) < 3:
                return False
            return (
                spy in self.last_draws[-1]
                and spy in self.last_draws[-2]
                and spy not in self.last_draws[-3]
            )
        if condition == "C3plus":
            if len(self.last_draws) < 3:
                return False
            return all(spy in draw for draw in self.last_draws[-3:])
        return False

    def active_spy_candidates_now(self):
        """Restituisce i candidati spia attivi sullo stesso colpo corrente."""
        active = []
        for candidate in SPY_LAB_CANDIDATES:
            if self.spy_condition_met(int(candidate["spy"]), candidate["condition"]):
                active.append(candidate)
        return active

    def spy_network_level(self, candidate, active_candidates):
        """Classifica il segnale come NORMALE/FORTE/MULTIPLA.

        MULTIPLA: almeno due spie della stessa rete attive nello stesso colpo.
        FORTE: singola spia appartenente alla CATENA_5 o al PONTE_55.
        NORMALE: resto dei casi.
        """
        network = candidate.get("network", "ALTRO")
        same_network = [c for c in active_candidates if c.get("network", "ALTRO") == network]
        if len(same_network) >= 2:
            return "MULTIPLA", len(same_network), len(active_candidates)
        if network in {"CATENA_5", "PONTE_55"}:
            return "FORTE", len(same_network), len(active_candidates)
        return "NORMALE", len(same_network), len(active_candidates)

    def _spy_stats_targets(self, ckey, network, network_level, horizon):
        """Restituisce i quattro contenitori statistici per un orizzonte."""
        hkey = str(horizon)
        self.spy_horizon_stats.setdefault(hkey, self.new_spy_lab_stats())
        self.spy_candidate_horizon_stats.setdefault(ckey, {})
        self.spy_candidate_horizon_stats[ckey].setdefault(hkey, self.new_spy_lab_stats())
        self.spy_network_horizon_stats.setdefault(network, {})
        self.spy_network_horizon_stats[network].setdefault(hkey, self.new_spy_lab_stats())
        self.spy_network_level_horizon_stats.setdefault(network_level, {})
        self.spy_network_level_horizon_stats[network_level].setdefault(hkey, self.new_spy_lab_stats())

        # Mantieni gli alias legacy puntati a H1 per CSV/report compatibili.
        if hkey == "1":
            self.spy_lab_stats = self.spy_horizon_stats["1"]
            self.spy_candidate_stats[ckey] = self.spy_candidate_horizon_stats[ckey]["1"]
            self.spy_network_stats[network] = self.spy_network_horizon_stats[network]["1"]
            self.spy_network_level_stats[network_level] = self.spy_network_level_horizon_stats[network_level]["1"]

        return (
            self.spy_horizon_stats[hkey],
            self.spy_candidate_horizon_stats[ckey][hkey],
            self.spy_network_horizon_stats[network][hkey],
            self.spy_network_level_horizon_stats[network_level][hkey],
        )

    async def maybe_open_spy_lab_sessions(self, app, e):
        """Apre i segnali spia candidati dal backtest.

        Ogni segnale viene valutato in parallelo a 1 / 2 / 3 colpi. Il
        NETWORK SCORE non modifica il segnale: classifica soltanto il
        contesto in cui nasce.
        """
        opened = []
        active_candidates = self.active_spy_candidates_now()

        for candidate in active_candidates:
            spy = int(candidate["spy"])
            condition = candidate["condition"]
            followers = tuple(sorted(map(int, candidate["followers"])))
            network = candidate.get("network", "ALTRO")
            network_level, active_related, active_total = self.spy_network_level(candidate, active_candidates)

            self.spy_lab_uid += 1
            signal_id = self.spy_lab_uid
            ckey = self.spy_candidate_key(candidate)
            horizon_state = {
                str(h): {"closed": False, "k1_hit": False, "k2_hit": False, "k3_hit": False}
                for h in SPY_LAB_HORIZONS
            }
            session = {
                "signal_id": signal_id,
                "open_e": e,
                "colpi": 0,
                "max_colpi": SPY_LAB_MAX_COLPI,
                "horizons": horizon_state,
                "spy": spy,
                "condition": condition,
                "followers": list(followers),
                "candidate_key": ckey,
                "label": candidate.get("label", f"{spy} {condition}"),
                "network": network,
                "network_level": network_level,
                "active_related": active_related,
                "active_total": active_total,
            }
            self.spy_lab_sessions.append(session)

            for h in SPY_LAB_HORIZONS:
                for stx in self._spy_stats_targets(ckey, network, network_level, h):
                    stx["sessions"] += 1
            opened.append(session)

            self.append_csv_event(
                "SPY_LAB_OPEN",
                e=e,
                colpo=0,
                session_type="SPY_LAB_H1_H2_H3",
                strategy=f"SPY_{spy}_{condition}_{network}_{network_level}",
                terni=[followers],
                outcome="OPEN_H1_H2_H3",
                spy_signal_id=signal_id,
                spy_number=spy,
                spy_condition=condition,
                spy_network=network,
                spy_network_level=network_level,
                spy_active_related=active_related,
                spy_active_total=active_total,
                spy_followers=followers,
            )

        if SPY_LAB_NOTIFY and opened:
            lines = ["🕵️ NUMERI SPIA LAB — SEGNALE"]
            for session in opened:
                net_label = SPY_NETWORK_DEFS.get(session["network"], SPY_NETWORK_DEFS["ALTRO"])["label"]
                lines.append(
                    f"• id {session['signal_id']} | spia {session['spy']} | {session['condition']} "
                    f"→ {fmt_nums(session['followers'])}"
                )
                lines.append(
                    f"  🧬 rete = {net_label} | livello = {session['network_level']} "
                    f"| attive rete/tot = {session['active_related']}/{session['active_total']}"
                )
            lines.append("• osservazione parallela = prossimi 1 / 2 / 3 colpi")
            lines.append("• target = K2 statistico / K3 terno 45x")
            await self.tg(app, "\n".join(lines))

    async def process_spy_lab_sessions(self, app, e, nums):
        if not self.spy_lab_sessions:
            return

        draw_set = set(nums)
        survivors = []

        for session in self.spy_lab_sessions:
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = int(session["colpi"])
            followers = [int(n) for n in session.get("followers", [])]
            hit_numbers = [n for n in followers if n in draw_set]
            hit_count = len(hit_numbers)
            ckey = session.get("candidate_key")
            network = session.get("network", "ALTRO")
            network_level = session.get("network_level", "NORMALE")
            horizons = session.setdefault("horizons", {})

            hit_horizons = []
            close_events = []

            for horizon in SPY_LAB_HORIZONS:
                hkey = str(horizon)
                hstate = horizons.setdefault(
                    hkey,
                    {"closed": False, "k1_hit": False, "k2_hit": False, "k3_hit": False},
                )
                if hstate.get("closed", False):
                    continue

                # Ogni orizzonte simula 1 unita' sul terno TOP3 per ogni colpo
                # ancora aperto. Se arriva K3, quell'orizzonte si ferma.
                for stx in self._spy_stats_targets(ckey, network, network_level, horizon):
                    stx["k3_cost_units"] += 1.0

                if hit_count >= 1 and not hstate.get("k1_hit", False):
                    hstate["k1_hit"] = True
                    for stx in self._spy_stats_targets(ckey, network, network_level, horizon):
                        stx["k1_hits"] += 1
                if hit_count >= 2 and not hstate.get("k2_hit", False):
                    hstate["k2_hit"] = True
                    for stx in self._spy_stats_targets(ckey, network, network_level, horizon):
                        stx["k2_hits"] += 1
                if hit_count >= 3 and not hstate.get("k3_hit", False):
                    hstate["k3_hit"] = True
                    hstate["closed"] = True
                    hit_horizons.append(horizon)
                    for stx in self._spy_stats_targets(ckey, network, network_level, horizon):
                        stx["k3_hits"] += 1
                        stx["k3_gross_units"] += SPY_LAB_PAYOUT
                        stx["closed"] += 1
                    close_events.append((horizon, f"K3_COLPO_{colpo}"))
                elif colpo >= int(horizon):
                    hstate["closed"] = True
                    for stx in self._spy_stats_targets(ckey, network, network_level, horizon):
                        stx["closed"] += 1
                    close_events.append((horizon, f"K{hit_count}" if hit_count else "MISS"))

            # CSV: una riga di avanzamento per colpo, più le chiusure orizzonte.
            self.append_csv_event(
                "SPY_LAB_STEP",
                e=e,
                colpo=colpo,
                session_type="SPY_LAB_H1_H2_H3",
                strategy=f"SPY_{session.get('spy')}_{session.get('condition')}",
                terni=[followers],
                hit_list=[tuple(hit_numbers)] if hit_numbers else [],
                outcome=f"K{hit_count}" if hit_count else "MISS",
                spy_signal_id=session.get("signal_id"),
                spy_number=session.get("spy"),
                spy_condition=session.get("condition", ""),
                spy_network=network,
                spy_network_level=network_level,
                spy_active_related=session.get("active_related"),
                spy_active_total=session.get("active_total"),
                spy_followers=followers,
                spy_hit_numbers=hit_numbers,
                spy_k_hit=hit_count,
            )

            for horizon, outcome in close_events:
                self.append_csv_event(
                    "SPY_LAB_CLOSE_HORIZON",
                    e=e,
                    colpo=colpo,
                    session_type=f"SPY_LAB_H{horizon}",
                    strategy=f"SPY_{session.get('spy')}_{session.get('condition')}_H{horizon}",
                    terni=[followers],
                    hit_list=[tuple(hit_numbers)] if hit_numbers else [],
                    outcome=outcome,
                    spy_signal_id=session.get("signal_id"),
                    spy_number=session.get("spy"),
                    spy_condition=session.get("condition", ""),
                    spy_network=network,
                    spy_network_level=network_level,
                    spy_active_related=session.get("active_related"),
                    spy_active_total=session.get("active_total"),
                    spy_followers=followers,
                    spy_hit_numbers=hit_numbers,
                    spy_k_hit=hit_count,
                )

            if SPY_LAB_NOTIFY and hit_count >= 2:
                label = "TRIS 3/3" if hit_count == 3 else "ALMENO 2/3"
                extra = ""
                if hit_horizons:
                    extra = f"\n• orizzonti K3 vinti = {fmt_nums(hit_horizons)}"
                await self.tg(
                    app,
                    f"💥 NUMERI SPIA LAB — {label}\n"
                    f"• signal_id = {session.get('signal_id')}\n"
                    f"• spia = {session.get('spy')} | condizione = {session.get('condition')}\n"
                    f"• rete = {network} | livello = {network_level}\n"
                    f"• TOP3 accompagnatori = {fmt_nums(followers)}\n"
                    f"• usciti = {fmt_nums(hit_numbers)}\n"
                    f"• colpo = {colpo}{extra}"
                )

            if not all(horizons.get(str(h), {}).get("closed", False) for h in SPY_LAB_HORIZONS):
                survivors.append(session)

        self.spy_lab_sessions = survivors

    @staticmethod
    def _pct_txt(num, den):
        den = int(den or 0)
        return f"{(float(num) / den * 100.0):.2f}%" if den else "0.00%"

    def _spy_stat_line(self, prefix, st):
        closed = int(st.get("closed", 0))
        cost = float(st.get("k3_cost_units", 0.0))
        gross = float(st.get("k3_gross_units", 0.0))
        net = gross - cost
        roi = (net / cost * 100.0) if cost else 0.0
        return (
            f"{prefix}: sess={st.get('sessions', 0)} chiuse={closed} "
            f"K1={st.get('k1_hits', 0)} ({self._pct_txt(st.get('k1_hits', 0), closed)}) "
            f"K2={st.get('k2_hits', 0)} ({self._pct_txt(st.get('k2_hits', 0), closed)}) "
            f"K3={st.get('k3_hits', 0)} ({self._pct_txt(st.get('k3_hits', 0), closed)}) "
            f"ROI={roi:+.1f}%"
        )

    def spy_lab_stats_text(self):
        lines = [
            "📊 NUMERI SPIA NETWORK LAB — CANDIDATI ROBUSTI / 1-2-3 COLPI",
            f"• candidati monitorati = {len(SPY_LAB_CANDIDATES)}",
            f"• payout teorico K3 = {SPY_LAB_PAYOUT:.0f}x",
            f"• sessioni aperte ora = {len(self.spy_lab_sessions)}",
        ]

        lines.append("\n⏱️ Orizzonti globali")
        for horizon in SPY_LAB_HORIZONS:
            hkey = str(horizon)
            st = self.spy_horizon_stats.get(hkey, self.new_spy_lab_stats())
            lines.append(self._spy_stat_line(f"• H{horizon}", st))
            cost = float(st.get("k3_cost_units", 0.0))
            gross = float(st.get("k3_gross_units", 0.0))
            net = gross - cost
            lines.append(f"  costo={cost:.2f}u lordo={gross:.2f}u netto={net:+.2f}u")

        rows = []
        for candidate in SPY_LAB_CANDIDATES:
            ckey = self.spy_candidate_key(candidate)
            hstats = self.spy_candidate_horizon_stats.get(ckey, {})
            if not any(hstats.get(str(h), {}).get("sessions", 0) for h in SPY_LAB_HORIZONS):
                continue
            parts = [f"• {candidate['label']}"]
            for horizon in SPY_LAB_HORIZONS:
                st = hstats.get(str(horizon), self.new_spy_lab_stats())
                closed = int(st.get("closed", 0))
                cost = float(st.get("k3_cost_units", 0.0))
                gross = float(st.get("k3_gross_units", 0.0))
                roi = ((gross - cost) / cost * 100.0) if cost else 0.0
                parts.append(
                    f"H{horizon}:K2={st.get('k2_hits', 0)}({self._pct_txt(st.get('k2_hits', 0), closed)}) "
                    f"K3={st.get('k3_hits', 0)}({self._pct_txt(st.get('k3_hits', 0), closed)}) ROI={roi:+.0f}%"
                )
            rows.append(" | ".join(parts))
        if rows:
            lines.append("\n📌 Dettaglio candidati")
            lines.extend(rows[:12])

        network_rows = []
        for network in SPY_NETWORK_BUCKETS:
            hstats = self.spy_network_horizon_stats.get(network, {})
            if not any(hstats.get(str(h), {}).get("sessions", 0) for h in SPY_LAB_HORIZONS):
                continue
            label = SPY_NETWORK_DEFS.get(network, SPY_NETWORK_DEFS["ALTRO"])["label"]
            network_rows.append(f"• {label}")
            for horizon in SPY_LAB_HORIZONS:
                network_rows.append("  " + self._spy_stat_line(f"H{horizon}", hstats.get(str(horizon), self.new_spy_lab_stats())))
        if network_rows:
            lines.append("\n🧬 Network score")
            lines.extend(network_rows)

        level_rows = []
        for level in SPY_NETWORK_LEVELS:
            hstats = self.spy_network_level_horizon_stats.get(level, {})
            if not any(hstats.get(str(h), {}).get("sessions", 0) for h in SPY_LAB_HORIZONS):
                continue
            level_rows.append(f"• {level}")
            for horizon in SPY_LAB_HORIZONS:
                level_rows.append("  " + self._spy_stat_line(f"H{horizon}", hstats.get(str(horizon), self.new_spy_lab_stats())))
        if level_rows:
            lines.append("\n📶 Livello rete")
            lines.extend(level_rows)
        return "\n".join(lines)

    # ========================================================
    # LAB SESSION CREATION
    # ========================================================

    def create_terni_session(self, play, e):
        strategies = {}

        for key in LAB_STRATEGIES:
            suffix = key.replace("op", "")
            terni = normalize_terni(play.get(f"terni_op{suffix}", []))
            jolly = play.get(f"terno_num_{suffix}")

            strategies[key] = {
                "jolly": jolly,
                "terni": terni,
                "hit": False,
                "first_hit_colpo": None,
                "first_hit_list": [],
            }

            if terni:
                self.terni_stats[key]["sessions"] += 1

        session = {
            "play_id": play["play_id"],
            "day": self.day,
            "start_e": e,
            "colpi": 0,
            "max_colpi": TERNI_LAB_MAX_COLPI,
            "ambata": play["ambata"],
            "ambi": play["ambi"],
            "cluster_numbers": play["cluster_numbers"],
            "strategies": strategies,
        }

        self.terni_sessions.append(session)

    def create_ambata_r2_session(self, play, e):
        session = {
            "play_id": play["play_id"],
            "day": self.day,
            "start_e": e,
            "colpi": 0,
            "max_colpi": AMBATA_RAFFICA_MAX_COLPI,
            "ambata": play["ambata"],
            "ambi": play["ambi"],
            "cluster_numbers": play["cluster_numbers"],
        }

        self.ambata_r2_sessions.append(session)
        self.ambata_r2_stats["sessions"] += 1

    def create_ambo_jolly_session(self, play, e):
        """Apre AJ1 usando solo dati congelati al momento del PLAY.

        Terno = primo ambo v48 (rank 1 del pair score) + jolly OP3 globale.
        La sessione vive nel ciclo del PLAY v48: ogni orizzonte 2/3/4/7
        chiude al proprio limite oppure prima se il PLAY v48 termina.
        """
        ambi = play.get("ambi", [])
        jolly = play.get("terno_num_3")
        if not ambi or not jolly:
            return None

        a, b = map(int, ambi[0]["ambo"])
        jolly = int(jolly)
        if jolly in (a, b):
            return None

        terno = tuple(sorted((a, b, jolly)))
        horizon_state = {str(h): {"closed": False} for h in AMBO_JOLLY_HORIZONS}

        session = {
            "play_id": play["play_id"],
            "day": self.day,
            "start_e": e,
            "colpi": 0,
            "max_colpi": max(AMBO_JOLLY_HORIZONS),
            "rank1_ambo": [a, b],
            "op3": jolly,
            "terno": list(terno),
            "horizons": horizon_state,
        }
        self.ambo_jolly_sessions.append(session)

        for horizon in AMBO_JOLLY_HORIZONS:
            self.ambo_jolly_stats[str(horizon)]["sessions"] += 1

        return session

    def close_ambo_jolly_for_play(self, play_id, e, colpo, reason):
        """Chiude come MISS gli orizzonti AJ1 ancora aperti quando v48 termina.

        Non aggiunge costo: il costo del colpo corrente è già stato contato da
        process_ambo_jolly_sessions(), eseguito prima del controllo core v48.
        """
        survivors = []

        for session in self.ambo_jolly_sessions:
            if int(session.get("play_id", -1)) != int(play_id):
                survivors.append(session)
                continue

            terno = tuple(sorted(map(int, session.get("terno", []))))
            for horizon in AMBO_JOLLY_HORIZONS:
                hkey = str(horizon)
                hstate = session.setdefault("horizons", {}).setdefault(hkey, {"closed": False})
                if hstate.get("closed", False):
                    continue

                hstate["closed"] = True
                st = self.ambo_jolly_stats[hkey]
                st["closed"] += 1
                st["misses"] += 1

                self.append_csv_event(
                    "AMBO_JOLLY_MISS_V48_CLOSE",
                    play_id=session["play_id"],
                    e=e,
                    colpo=colpo,
                    session_type=f"AMBO_JOLLY_AJ1_H{horizon}",
                    strategy="AJ1_RANK1_AMBO_PLUS_OP3",
                    terni=[terno],
                    outcome=f"MISS_{reason}",
                    ambo_jolly_terno=terno,
                    ambo_jolly_rank1_ambo=session.get("rank1_ambo", []),
                    ambo_jolly_op3=session.get("op3"),
                    ambo_jolly_horizon=horizon,
                )

        self.ambo_jolly_sessions = survivors

    async def process_ambo_jolly_sessions(self, app, e, nums):
        if not self.ambo_jolly_sessions:
            return

        draw_set = set(nums)
        survivors = []

        for session in self.ambo_jolly_sessions:
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = session["colpi"]
            terno = tuple(sorted(map(int, session.get("terno", []))))
            is_hit = len(terno) == 3 and set(terno).issubset(draw_set)

            newly_hit = []
            newly_missed = []

            for horizon in AMBO_JOLLY_HORIZONS:
                hkey = str(horizon)
                hstate = session.setdefault("horizons", {}).setdefault(hkey, {"closed": False})
                if hstate.get("closed", False):
                    continue

                st = self.ambo_jolly_stats[hkey]
                st["cost_units"] += 1.0

                if is_hit:
                    hstate["closed"] = True
                    st["closed"] += 1
                    st["hits"] += 1
                    st["gross_units"] += AMBO_JOLLY_PAYOUT
                    st["hit_by_colpo"][str(colpo)] = st["hit_by_colpo"].get(str(colpo), 0) + 1
                    newly_hit.append(horizon)

                    self.append_csv_event(
                        "AMBO_JOLLY_HIT",
                        play_id=session["play_id"],
                        e=e,
                        colpo=colpo,
                        session_type=f"AMBO_JOLLY_AJ1_H{horizon}",
                        strategy="AJ1_RANK1_AMBO_PLUS_OP3",
                        terni=[terno],
                        hit_list=[terno],
                        outcome="HIT",
                        ambo_jolly_terno=terno,
                        ambo_jolly_rank1_ambo=session.get("rank1_ambo", []),
                        ambo_jolly_op3=session.get("op3"),
                        ambo_jolly_horizon=horizon,
                    )
                elif colpo >= horizon:
                    hstate["closed"] = True
                    st["closed"] += 1
                    st["misses"] += 1
                    newly_missed.append(horizon)

                    self.append_csv_event(
                        "AMBO_JOLLY_MISS",
                        play_id=session["play_id"],
                        e=e,
                        colpo=colpo,
                        session_type=f"AMBO_JOLLY_AJ1_H{horizon}",
                        strategy="AJ1_RANK1_AMBO_PLUS_OP3",
                        terni=[terno],
                        outcome="MISS",
                        ambo_jolly_terno=terno,
                        ambo_jolly_rank1_ambo=session.get("rank1_ambo", []),
                        ambo_jolly_op3=session.get("op3"),
                        ambo_jolly_horizon=horizon,
                    )

            if newly_hit and AMBO_JOLLY_NOTIFY:
                await self.tg(
                    app,
                    "💥 AMBO-JOLLY AJ1 — HIT TERNO\n"
                    f"• play_id = {session['play_id']}\n"
                    f"• colpo = {colpo}\n"
                    f"• 1° ambo v48 = {fmt_nums(session.get('rank1_ambo', []))}\n"
                    f"• jolly OP3 = {session.get('op3')}\n"
                    f"• TERNO = {fmt_nums(terno)}\n"
                    f"• orizzonti vinti = {', '.join(map(str, newly_hit))} colpi\n\n"
                    f"{self.ambo_jolly_stats_text()}"
                )

            any_open = any(
                not session.get("horizons", {}).get(str(h), {}).get("closed", False)
                for h in AMBO_JOLLY_HORIZONS
            )
            if any_open:
                survivors.append(session)

        self.ambo_jolly_sessions = survivors

    # ========================================================
    # LAB SESSION PROCESSING — INDIPENDENTE DAL CORE v48
    # ========================================================

    async def process_terni_sessions(self, app, e, nums):
        if not self.terni_sessions:
            return

        s = set(nums)
        survivors = []

        for session in self.terni_sessions:
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = session["colpi"]

            new_hit_lines = []

            for key in LAB_STRATEGIES:
                data = session["strategies"].get(key, {})
                terni = normalize_terni(data.get("terni", []))
                hits = [t for t in terni if all(x in s for x in t)]

                # Contatore principale = sessioni vincenti, una volta sola per strategia.
                if hits and not data.get("hit", False):
                    data["hit"] = True
                    data["first_hit_colpo"] = colpo
                    data["first_hit_list"] = hits
                    self.terni_stats[key]["hit_sessions"] += 1

                    new_hit_lines.append(
                        f"• {LAB_LABELS[key]} = {fmt_terni(hits)}"
                    )

                    play_stub = {
                        "play_id": session["play_id"],
                        "ambata": session["ambata"],
                        "ambi": session["ambi"],
                        "cluster_numbers": session["cluster_numbers"],
                    }
                    self.append_csv_event(
                        "TERNI_FIRST_HIT",
                        play=play_stub,
                        play_id=session["play_id"],
                        e=e,
                        colpo=colpo,
                        session_type="TERNI_7",
                        strategy=key.upper(),
                        jolly=data.get("jolly"),
                        terni=terni,
                        hit_list=hits,
                        outcome="HIT",
                    )

            if new_hit_lines:
                await self.tg(
                    app,
                    f"💥 TERNI LAB 7 COLPI | play_id {session['play_id']} | colpo {colpo}\n"
                    + "\n".join(new_hit_lines)
                    + "\n\n"
                    + self.terni_lab_stats_text()
                )

            if colpo >= int(session.get("max_colpi", TERNI_LAB_MAX_COLPI)):
                play_stub = {
                    "play_id": session["play_id"],
                    "ambata": session["ambata"],
                    "ambi": session["ambi"],
                    "cluster_numbers": session["cluster_numbers"],
                }

                outcomes = []
                for key in LAB_STRATEGIES:
                    d = session["strategies"].get(key, {})
                    outcomes.append(f"{key.upper()}={'HIT' if d.get('hit') else 'MISS'}")

                self.append_csv_event(
                    "TERNI_SESSION_CLOSE",
                    play=play_stub,
                    play_id=session["play_id"],
                    e=e,
                    colpo=colpo,
                    session_type="TERNI_7",
                    outcome=";".join(outcomes),
                )
            else:
                survivors.append(session)

        self.terni_sessions = survivors

    async def process_ambata_r2_sessions(self, app, e, nums):
        if not self.ambata_r2_sessions:
            return

        s = set(nums)
        survivors = []

        for session in self.ambata_r2_sessions:
            session["colpi"] = int(session.get("colpi", 0)) + 1
            colpo = session["colpi"]
            hit = int(session["ambata"]) in s

            play_stub = {
                "play_id": session["play_id"],
                "ambata": session["ambata"],
                "ambi": session["ambi"],
                "cluster_numbers": session["cluster_numbers"],
            }

            if hit:
                self.ambata_r2_stats["hits"] += 1
                if colpo == 1:
                    self.ambata_r2_stats["hit_colpo1"] += 1
                elif colpo == 2:
                    self.ambata_r2_stats["hit_colpo2"] += 1

                self.append_csv_event(
                    "AMBATA_R2_HIT",
                    play=play_stub,
                    play_id=session["play_id"],
                    e=e,
                    colpo=colpo,
                    session_type="AMBATA_R2",
                    strategy="AMBATA_R2",
                    jolly=session["ambata"],
                    outcome="HIT",
                )

                await self.tg(
                    app,
                    f"🎯 AMBATA RAFFICA 2 | HIT colpo {colpo}\n"
                    f"• play_id = {session['play_id']}\n"
                    f"• ambata = {session['ambata']}\n\n"
                    f"{self.ambata_r2_stats_text()}\n\n"
                    f"{self.decina_lab_stats_text()}\n\n"
                    f"{self.decina_heat_stats_text()}\n\n"
                    f"{self.decina_multi_stats_text()}\n\n"
                    f"{self.ambo_jolly_stats_text()}"
                )
                continue

            if colpo >= int(session.get("max_colpi", AMBATA_RAFFICA_MAX_COLPI)):
                self.ambata_r2_stats["misses"] += 1

                self.append_csv_event(
                    "AMBATA_R2_MISS",
                    play=play_stub,
                    play_id=session["play_id"],
                    e=e,
                    colpo=colpo,
                    session_type="AMBATA_R2",
                    strategy="AMBATA_R2",
                    jolly=session["ambata"],
                    outcome="MISS",
                )
            else:
                survivors.append(session)

        self.ambata_r2_sessions = survivors

    # ========================================================
    # REPORT TEXT
    # ========================================================

    def v48_ambo_rank_stats_text(self):
        total_rank_events = sum(self.v48_ambo_rank_hits.values())
        return (
            "📊 V48 — POSIZIONE AMBO VINCENTE\n"
            f"• rank 1 = {self.v48_ambo_rank_hits['1']}\n"
            f"• rank 2 = {self.v48_ambo_rank_hits['2']}\n"
            f"• rank 3 = {self.v48_ambo_rank_hits['3']}\n"
            f"• eventi rank totali = {total_rank_events}\n"
            f"• colpi con 2+ ambi v48 insieme = {self.v48_multi_ambo_hit_draws}"
        )

    def terni_lab_stats_text(self):
        lines = ["📊 TERNI LAB — SESSIONI VINCENTI / SESSIONI"]

        for key in LAB_STRATEGIES:
            st = self.terni_stats[key]
            sessions = st["sessions"]
            hits = st["hit_sessions"]
            pct = (hits / sessions * 100) if sessions else 0.0
            prefix = "⭐" if key == "op3" else "•"
            lines.append(
                f"{prefix} {key.upper()} = {hits}/{sessions} ({pct:.2f}%)"
            )

        return "\n".join(lines)

    def ambata_r2_stats_text(self):
        st = self.ambata_r2_stats
        sessions = st["sessions"]
        hits = st["hits"]
        closed = hits + st["misses"]
        pct = (hits / closed * 100) if closed else 0.0

        return (
            "📊 AMBATA RAFFICA 2\n"
            f"• sessioni create = {sessions}\n"
            f"• sessioni chiuse = {closed}\n"
            f"• hit = {hits}\n"
            f"• miss = {st['misses']}\n"
            f"• hit rate chiuse = {pct:.2f}%\n"
            f"• hit colpo 1 = {st['hit_colpo1']}\n"
            f"• hit colpo 2 = {st['hit_colpo2']}"
        )

    def decina_lab_stats_text(self):
        st = self.decina_lab_stats
        closed = st["closed"]
        k1_pct = (st["k1_hits"] / closed * 100) if closed else 0.0
        k2_pct = (st["k2_hits"] / closed * 100) if closed else 0.0
        k3_pct = (st["k3_hits"] / closed * 100) if closed else 0.0
        cost = float(st["k3_cost_units"])
        gross = float(st["k3_gross_units"])
        net = gross - cost
        roi = (net / cost * 100.0) if cost else 0.0

        return (
            "📊 DECINA LAB 10-19 — HEAT 5 / TOP 3 / 2 COLPI\n"
            f"• soglia Heat totale = {DECINA_LAB_HEAT_THRESHOLD}\n"
            f"• sessioni create = {st['sessions']}\n"
            f"• sessioni chiuse = {closed}\n"
            f"• almeno 1/3 = {st['k1_hits']} ({k1_pct:.2f}%)\n"
            f"• almeno 2/3 = {st['k2_hits']} ({k2_pct:.2f}%)\n"
            f"• tutti 3/3 = {st['k3_hits']} ({k3_pct:.2f}%)\n"
            f"• K2 colpo 1 = {st['k2_colpo1']} | colpo 2 = {st['k2_colpo2']}\n"
            f"• K3 colpo 1 = {st['k3_colpo1']} | colpo 2 = {st['k3_colpo2']}\n"
            f"• K3 teorico {DECINA_BASE_K3_PAYOUT:.0f}x: costo = {cost:.2f}u | lordo = {gross:.2f}u\n"
            f"• K3 netto = {net:+.2f}u | ROI = {roi:+.2f}%\n"
            f"• sessioni aperte ora = {len(self.decina_lab_sessions)}"
        )

    def decina_heat_stats_text(self):
        labels = {
            "H8": "HEAT = 8",
            "H9": "HEAT = 9 ⭐ PRIORITARIA",
            "H10P": "HEAT >= 10",
        }
        lines = [
            "📊 DECINA BASE — MONITOR FASCE HEAT",
            "• stessa regola TOP3 / 2 colpi; solo statistiche separate",
        ]

        # Campi cumulativi horizon-specific per NUMERI SPIA LAB.
        for _h in SPY_LAB_HORIZONS:
            _hkey = str(_h)
            _st = self.spy_horizon_stats.get(_hkey, self.new_spy_lab_stats())
            _cost = float(_st.get("k3_cost_units", 0.0))
            _gross = float(_st.get("k3_gross_units", 0.0))
            _net = _gross - _cost
            _roi = (_net / _cost * 100.0) if _cost else 0.0
            row.update({
                f"spy_h{_h}_sessions": _st.get("sessions", 0),
                f"spy_h{_h}_closed": _st.get("closed", 0),
                f"spy_h{_h}_k1_hits": _st.get("k1_hits", 0),
                f"spy_h{_h}_k2_hits": _st.get("k2_hits", 0),
                f"spy_h{_h}_k3_hits": _st.get("k3_hits", 0),
                f"spy_h{_h}_k3_cost_units": f"{_cost:.2f}",
                f"spy_h{_h}_k3_gross_units": f"{_gross:.2f}",
                f"spy_h{_h}_k3_net_units": f"{_net:.2f}",
                f"spy_h{_h}_k3_roi_pct": f"{_roi:.4f}",
            })

        for bucket in DECINA_HEAT_BUCKETS:
            st = self.decina_heat_stats[bucket]
            closed = st["closed"]
            k2_pct = (st["k2_hits"] / closed * 100.0) if closed else 0.0
            k3_pct = (st["k3_hits"] / closed * 100.0) if closed else 0.0
            cost = float(st["k3_cost_units"])
            gross = float(st["k3_gross_units"])
            net = gross - cost
            roi = (net / cost * 100.0) if cost else 0.0
            lines.extend([
                "",
                f"{'⭐' if bucket == 'H9' else '•'} {labels[bucket]}",
                f"• sessioni = {st['sessions']} | chiuse = {closed}",
                f"• K1 = {st['k1_hits']} | K2 = {st['k2_hits']} ({k2_pct:.2f}%) | K3 = {st['k3_hits']} ({k3_pct:.2f}%)",
                f"• K2 C1/C2 = {st['k2_colpo1']}/{st['k2_colpo2']}",
                f"• K3 C1/C2 = {st['k3_colpo1']}/{st['k3_colpo2']}",
                f"• K3 costo = {cost:.2f}u | lordo = {gross:.2f}u | netto = {net:+.2f}u | ROI = {roi:+.2f}%",
            ])

        return "\n".join(lines)

    def decina_multi_stats_text(self):
        lines = [
            "📊 DECINA MULTI-TERNO 10-19 — HEAT 5 / 2 COLPI",
            f"• soglia apertura = Heat TOP3 >= {DECINA_MULTI_HEAT_THRESHOLD}",
            f"• payout teorico = {DECINA_TERNO_PAYOUT:.0f}x per terno vincente",
        ]

        for package, label in (("core", "CORE TOP2 (3 terni)"), ("pivot", "PIVOT (6 terni)")):
            st = self.decina_multi_stats[package]
            closed = st["closed"]
            win_rate = (st["winning_sessions"] / closed * 100.0) if closed else 0.0
            cost = float(st["cost_units"])
            gross = float(st["gross_units"])
            net = gross - cost
            roi = (net / cost * 100.0) if cost else 0.0
            lines.extend([
                "",
                f"{'🔷' if package == 'core' else '🔶'} {label}",
                f"• sessioni = {st['sessions']} | chiuse = {closed}",
                f"• vincenti = {st['winning_sessions']} ({win_rate:.2f}%) | miss = {st['losing_sessions']}",
                f"• hit colpo 1 = {st['hit_colpo1']} | colpo 2 = {st['hit_colpo2']}",
                f"• terni vincenti totali = {st['winning_terni']}",
                f"• sessioni con 2+ terni insieme = {st['multi_2plus_sessions']}",
                f"• max terni nello stesso colpo = {st['max_terni_same_draw']}",
                f"• costo teorico = {cost:.2f}u | lordo = {gross:.2f}u",
                f"• netto = {net:+.2f}u | ROI = {roi:+.2f}%",
            ])

        lines.append(f"\n• sessioni multi aperte ora = {len(self.decina_multi_sessions)}")
        return "\n".join(lines)

    def ambo_jolly_stats_text(self):
        lines = [
            "📊 AMBO-JOLLY AJ1 — SOLO LAB / 1° AMBO v48 + OP3",
            f"• payout teorico = {AMBO_JOLLY_PAYOUT:.0f}x",
            "• un solo terno per PLAY",
            "• stop anticipato se il PLAY v48 chiude",
        ]

        for horizon in AMBO_JOLLY_HORIZONS:
            st = self.ambo_jolly_stats[str(horizon)]
            closed = st["closed"]
            hit_rate = (st["hits"] / closed * 100.0) if closed else 0.0
            cost = float(st["cost_units"])
            gross = float(st["gross_units"])
            net = gross - cost
            roi = (net / cost * 100.0) if cost else 0.0
            by_colpo = ", ".join(
                f"C{i}={st['hit_by_colpo'].get(str(i), 0)}"
                for i in range(1, horizon + 1)
            )
            lines.extend([
                "",
                f"⭐ AJ1 max {horizon} colpi",
                f"• sessioni = {st['sessions']} | chiuse = {closed}",
                f"• hit = {st['hits']} ({hit_rate:.2f}%) | miss = {st['misses']}",
                f"• distribuzione hit = {by_colpo}",
                f"• costo = {cost:.2f}u | lordo = {gross:.2f}u",
                f"• netto = {net:+.2f}u | ROI = {roi:+.2f}%",
            ])

        lines.append(f"\n• sessioni AJ1 aperte ora = {len(self.ambo_jolly_sessions)}")
        return "\n".join(lines)

    def play_lab_text(self, play):
        blocks = []

        for key in LAB_STRATEGIES:
            suffix = key.replace("op", "")
            jolly = play.get(f"terno_num_{suffix}")
            terni = play.get(f"terni_op{suffix}", [])
            blocks.append(
                f"{'⭐' if key == 'op3' else '🧪'} {LAB_LABELS[key]} | "
                f"jolly = {fmt_jolly(jolly) or 'None'}\n"
                f"{fmt_terni(terni) or 'nessuno'}"
            )

        return "\n\n".join(blocks)

    # ========================================================
    # MAIN
    # ========================================================

    async def on_new(self, app, e, nums):
        if len(set(nums)) != 20:
            return

        if self.already_processed(e, nums):
            return

        self.remember_processed(e, nums)

        self.last_draws.append(nums)
        self.last_draws = self.last_draws[-HISTORY_MAX:]

        await self.tg(
            app,
            f"📌 Estrazione {e}\n"
            f"🎱 {', '.join(map(str, nums))}"
        )

        # ====================================================
        # LAB INDIPENDENTI: vengono aggiornati SEMPRE,
        # anche se il CORE v48 ha già chiuso l'ambo.
        # ====================================================
        await self.process_terni_sessions(app, e, nums)
        await self.process_ambata_r2_sessions(app, e, nums)
        await self.process_decina_10_19_sessions(app, e, nums)
        await self.process_decina_multi_sessions(app, e, nums)
        await self.process_ambo_jolly_sessions(app, e, nums)
        await self.process_spy_lab_sessions(app, e, nums)

        # Il nuovo segnale usa le ultime 5 estrazioni già note (inclusa questa)
        # e viene verificato SOLO sulle future 2 estrazioni successive.
        await self.maybe_open_decina_10_19_session(app, e)

        # Numeri spia: condizioni sul colpo corrente, verifica parallela sui prossimi 1/2/3 colpi.
        await self.maybe_open_spy_lab_sessions(app, e)

        # ====================================================
        # CORE v48 ATTIVO — LOGICA INVARIATA
        # ====================================================
        if self.active:
            self.colpi += 1
            hit_data = self.check_v48_hit(nums)

            if hit_data["ambata_hit"]:
                self.total_hit_ambata += 1
                self.append_csv_event(
                    "V48_HIT_AMBATA",
                    e=e,
                    colpo=self.colpi,
                    session_type="V48",
                    outcome="HIT",
                )

                await self.tg(
                    app,
                    f"🎯 AMBATA PRESA v48 | colpo {self.colpi}\n"
                    f"• ambata = {self.active_snapshot['ambata']}"
                )

            if hit_data["ambi_hit"]:
                self.total_hit_ambo += 1

                # Diagnostica pura: conta quali posizioni dei 3 ambi v48
                # hanno partecipato al colpo vincente. Il CORE resta invariato.
                hit_ranks = []
                active_ambi = self.active_snapshot.get("ambi", [])
                for hit_item in hit_data["ambi_hit"]:
                    hit_pair = tuple(map(int, hit_item["ambo"]))
                    for idx, item in enumerate(active_ambi, start=1):
                        if tuple(map(int, item["ambo"])) == hit_pair:
                            rank_key = str(idx)
                            if rank_key in self.v48_ambo_rank_hits:
                                self.v48_ambo_rank_hits[rank_key] += 1
                                hit_ranks.append(idx)
                            break
                if len(set(hit_ranks)) >= 2:
                    self.v48_multi_ambo_hit_draws += 1

                ambi_txt = ", ".join(
                    f"{a}-{b}"
                    for h in hit_data["ambi_hit"]
                    for a, b in [h["ambo"]]
                )

                self.append_csv_event(
                    "V48_HIT_AMBO",
                    e=e,
                    colpo=self.colpi,
                    session_type="V48",
                    outcome="HIT",
                    hit_list=[],
                )

                await self.tg(
                    app,
                    f"🔥 HIT AMBO v48 | colpo {self.colpi}\n"
                    f"• ambi = {ambi_txt}\n"
                    f"• rank vincenti = {', '.join(map(str, sorted(set(hit_ranks)))) or 'n/d'}\n\n"
                    f"📊 STATS v48\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata eventi = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}\n\n"
                    f"{self.v48_ambo_rank_stats_text()}\n\n"
                    f"{self.terni_lab_stats_text()}\n\n"
                    f"{self.ambata_r2_stats_text()}\n\n"
                    f"{self.decina_lab_stats_text()}\n\n"
                    f"{self.decina_heat_stats_text()}\n\n"
                    f"{self.decina_multi_stats_text()}\n\n"
                    f"{self.ambo_jolly_stats_text()}"
                )

                self.last_cluster_numbers = self.active_snapshot["cluster_numbers"]
                self.last_cluster_e = e

                # AJ1 replica il backtest: si ferma quando il PLAY v48 chiude.
                self.close_ambo_jolly_for_play(
                    self.active_snapshot["play_id"], e, self.colpi, "V48_HIT_AMBO"
                )

                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None

                self.save_state()
                return

            if self.colpi >= MAX_COLPI:
                self.total_stop += 1

                self.append_csv_event(
                    "V48_STOP",
                    e=e,
                    colpo=self.colpi,
                    session_type="V48",
                    outcome="STOP",
                )

                await self.tg(
                    app,
                    f"🛑 STOP v48 | {MAX_COLPI} colpi\n\n"
                    f"📊 STATS v48\n"
                    f"• play = {self.total_play}\n"
                    f"• hit ambata eventi = {self.total_hit_ambata}\n"
                    f"• hit ambo = {self.total_hit_ambo}\n"
                    f"• stop = {self.total_stop}\n\n"
                    f"{self.v48_ambo_rank_stats_text()}\n\n"
                    f"{self.terni_lab_stats_text()}\n\n"
                    f"{self.ambata_r2_stats_text()}\n\n"
                    f"{self.decina_lab_stats_text()}\n\n"
                    f"{self.decina_heat_stats_text()}\n\n"
                    f"{self.decina_multi_stats_text()}\n\n"
                    f"{self.ambo_jolly_stats_text()}"
                )

                self.last_cluster_numbers = self.active_snapshot["cluster_numbers"]
                self.last_cluster_e = e

                # AJ1 replica il backtest: si ferma quando il PLAY v48 chiude.
                self.close_ambo_jolly_for_play(
                    self.active_snapshot["play_id"], e, self.colpi, "V48_STOP"
                )

                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None

                self.save_state()
                return

            self.save_state()
            return

        # ====================================================
        # COOLDOWN — CORE v48
        # ====================================================
        if self.cooldown > 0:
            self.cooldown -= 1
            self.save_state()
            return

        # ====================================================
        # HISTORY MINIMO
        # ====================================================
        if len(self.last_draws) < 30:
            self.save_state()
            return

        # ====================================================
        # HOT UPDATE — CORE v48
        # ====================================================
        _, selected = self.selected_ritardatari()
        self.update_watch_and_confirmed(e, nums, selected)

        # ====================================================
        # BUILD PLAY — CORE v48 + LAB PARALLELO
        # ====================================================
        play = self.build_play(e)

        if play and not self.active:
            self.active = True
            self.colpi = 0
            self.play_uid += 1
            play["play_id"] = self.play_uid
            self.active_snapshot = play
            self.total_play += 1

            # Sessioni parallele indipendenti.
            self.create_terni_session(play, e)
            self.create_ambata_r2_session(play, e)
            aj_session = self.create_ambo_jolly_session(play, e)

            self.append_csv_event(
                "PLAY",
                play=play,
                play_id=play["play_id"],
                e=e,
                colpo=0,
                session_type="V48",
                outcome="OPEN",
            )

            # Una riga CSV per strategia rende il file facile da analizzare.
            for key in LAB_STRATEGIES:
                suffix = key.replace("op", "")
                self.append_csv_event(
                    "TERNI_SESSION_OPEN",
                    play=play,
                    play_id=play["play_id"],
                    e=e,
                    colpo=0,
                    session_type="TERNI_7",
                    strategy=key.upper(),
                    jolly=play.get(f"terno_num_{suffix}"),
                    terni=play.get(f"terni_op{suffix}", []),
                    outcome="OPEN",
                )

            self.append_csv_event(
                "AMBATA_R2_OPEN",
                play=play,
                play_id=play["play_id"],
                e=e,
                colpo=0,
                session_type="AMBATA_R2",
                strategy="AMBATA_R2",
                jolly=play["ambata"],
                outcome="OPEN",
            )

            if aj_session:
                aj_terno = tuple(sorted(map(int, aj_session["terno"])))
                self.append_csv_event(
                    "AMBO_JOLLY_OPEN",
                    play=play,
                    play_id=play["play_id"],
                    e=e,
                    colpo=0,
                    session_type="AMBO_JOLLY_AJ1",
                    strategy="AJ1_RANK1_AMBO_PLUS_OP3",
                    jolly=aj_session["op3"],
                    terni=[aj_terno],
                    outcome="OPEN",
                    ambo_jolly_terno=aj_terno,
                    ambo_jolly_rank1_ambo=aj_session["rank1_ambo"],
                    ambo_jolly_op3=aj_session["op3"],
                )

            await self.tg(
                app,
                "🎯 PLAY v48 + FINAL RESEARCH\n"
                f"🔥 AMBATA = {play['ambata']}\n"
                f"✅ AMBI = {fmt_ambi(play['ambi'])}\n"
                f"• cluster = {', '.join(map(str, play['cluster_numbers']))}\n"
                f"• max_colpi v48 = {MAX_COLPI}\n"
                f"• terni lab indipendente = {TERNI_LAB_MAX_COLPI} colpi\n"
                f"• ambata raffica = {AMBATA_RAFFICA_MAX_COLPI} colpi\n"
                f"• play_id = {play['play_id']}\n\n"
                + (
                    "⭐ AMBO-JOLLY AJ1\n"
                    f"• 1° ambo v48 = {fmt_nums(aj_session['rank1_ambo'])}\n"
                    f"• jolly OP3 = {aj_session['op3']}\n"
                    f"• TERNO = {fmt_nums(aj_session['terno'])}\n"
                    f"• orizzonti paralleli = {', '.join(map(str, AMBO_JOLLY_HORIZONS))} colpi\n"
                    "• stop anticipato = chiusura PLAY v48\n\n"
                    if aj_session else ""
                )
                + f"{self.play_lab_text(play)}"
            )

        self.save_state()

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT SNIPER v48 + FINAL RESEARCH + DECINA MULTI + AJ1 + SPIA\n"
            f"• play v48 = {self.total_play}\n"
            f"• hit ambata eventi = {self.total_hit_ambata}\n"
            f"• hit ambo = {self.total_hit_ambo}\n"
            f"• stop = {self.total_stop}\n"
            f"• rank ambo hit = R1:{self.v48_ambo_rank_hits['1']} R2:{self.v48_ambo_rank_hits['2']} R3:{self.v48_ambo_rank_hits['3']}\n"
            f"• sessioni terni aperte ora = {len(self.terni_sessions)}\n"
            f"• sessioni ambata R2 aperte ora = {len(self.ambata_r2_sessions)}\n"
            f"• sessioni decina base aperte ora = {len(self.decina_lab_sessions)}\n"
            f"• sessioni decina multi aperte ora = {len(self.decina_multi_sessions)}\n"
            f"• sessioni AJ1 aperte ora = {len(self.ambo_jolly_sessions)}\n\n"
            f"{self.terni_lab_stats_text()}\n\n"
            f"{self.ambata_r2_stats_text()}\n\n"
            f"{self.decina_lab_stats_text()}\n\n"
            f"{self.decina_heat_stats_text()}\n\n"
            f"{self.decina_multi_stats_text()}\n\n"
            f"{self.ambo_jolly_stats_text()}\n\n"
            f"🧾 CSV = {CSV_FILE}"
        )


# ============================================================
# LOCK ANTI-DOPPIA ISTANZA
# ============================================================

_LOCK_HANDLE = None


def acquire_single_instance_lock():
    global _LOCK_HANDLE

    _LOCK_HANDLE = open(LOCK_FILE, "a+", encoding="utf-8")

    if fcntl is not None:
        try:
            fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("⚠️ Un'altra istanza SNIPER v48/LAB è già attiva. Avvio bloccato.")
            sys.exit(1)
    else:
        # Fallback: PID best-effort per sistemi senza fcntl.
        _LOCK_HANDLE.seek(0)
        old = _LOCK_HANDLE.read().strip()

        if old.isdigit():
            try:
                os.kill(int(old), 0)
                print("⚠️ Un'altra istanza sembra già attiva. Avvio bloccato.")
                sys.exit(1)
            except OSError:
                pass

    _LOCK_HANDLE.seek(0)
    _LOCK_HANDLE.truncate()
    _LOCK_HANDLE.write(str(os.getpid()))
    _LOCK_HANDLE.flush()

    def cleanup_lock():
        try:
            if fcntl is not None:
                fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_UN)
            _LOCK_HANDLE.close()
        except Exception:
            pass

    atexit.register(cleanup_lock)


# ============================================================
# LOOP
# ============================================================

CHAT_ID = validate_env()
acquire_single_instance_lock()
bot = SNIPER_V48()


async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    current_day = day_key()

    if bot.day != current_day:
        bot.reset_for_new_day(current_day)
        await bot.tg(
            app,
            "🗓️ Nuovo giorno rilevato: reset operativo dedup/watch/hot. "
            "Storico numerico conservato; sessioni LAB precedenti chiuse."
        )

    es = parse_site()

    if not es:
        await bot.tg(app, "⚠️ parser vuoto")
        return

    # Primo avvio pulito: storico sì, replay no.
    if not bot.last_draws:
        bot.preload_today_as_processed(es)

        await bot.tg(
            app,
            "🚀 SNIPER v48 + DECINA HEAT MONITOR + MULTI + AJ1 + SPIA LAB AVVIATO\n"
            "✅ core v48 invariato\n"
            "✅ OP3 primary + OP9/OP6/OP7 control\n"
            "✅ Terni Lab indipendente 7 colpi\n"
            "✅ Ambata Raffica 2 indipendente\n"
            "✅ Decina Base 10-19 Heat5 TOP3 soglia>=8, 2 colpi\n✅ monitor separato Heat=8 / Heat=9 / Heat>=10 + economia K3 45x\n"
            "✅ Decina CORE TOP2 3 terni soglia>=9, 2 colpi\n"
            "✅ Decina PIVOT 6 terni soglia>=9, 2 colpi\n"
            "✅ AMBO-JOLLY AJ1 = solo LAB, 1° ambo v48 + OP3, orizzonti 2/3/4/7\n✅ monitor rank ambo v48 vincente = 1/2/3\n✅ Numeri Spia Network Lab = candidati robusti, orizzonti 1/2/3 colpi\n"
            f"✅ notifiche Decina Base = {'ON' if DECINA_LAB_NOTIFY else 'OFF'}\n"
            f"✅ notifiche Decina Multi = {'ON' if DECINA_MULTI_NOTIFY else 'OFF'}\n"
            f"✅ notifiche AMBO-JOLLY AJ1 = {'ON' if AMBO_JOLLY_NOTIFY else 'OFF'}\n"
            f"✅ notifiche Numeri Spia = {'ON' if SPY_LAB_NOTIFY else 'OFF'}\n"
            "✅ storico iniziale marcato come processato\n"
            "✅ niente replay iniziale"
        )

    while True:
        try:
            current_day = day_key()

            if bot.day != current_day:
                bot.reset_for_new_day(current_day)

                await bot.tg(
                    app,
                    "🗓️ Nuovo giorno rilevato: reset operativo dedup/watch/hot. "
                    "Storico numerico conservato; sessioni LAB precedenti chiuse."
                )

                es = parse_site()
                if es:
                    bot.preload_today_as_processed(es)
                    await bot.tg(
                        app,
                        "🚀 SNIPER v48 + FINAL RESEARCH\n"
                        "✅ nuovo giorno inizializzato\n"
                        "✅ estrazioni già uscite oggi marcate come storico/processate"
                    )

                await asyncio.sleep(LOOP_SEC)
                continue

            es = parse_site()

            for e, nums in es:
                if bot.already_processed(e, nums):
                    continue

                await bot.on_new(app, e, nums)

        except Exception as ex:
            print(f"Errore loop: {ex}")
            try:
                await bot.tg(app, f"⚠️ errore v48 final research: {ex}")
            except Exception:
                pass

        await asyncio.sleep(LOOP_SEC)


if __name__ == "__main__":
    asyncio.run(live())
