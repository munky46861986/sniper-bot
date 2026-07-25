# ============================================================
# 🚀 SNIPER v48 BASE + FULL NUMERI SPIA LAB — v6 PLAY AMBATA/AMBI
#
# VERSIONE PULITA
#   ✅ v48 base invariata: ambata + 3 ambi classici, max 7 colpi
#   ✅ monitor rank ambo vincente 1/2/3
#   ✅ economia teorica v48: ambo 14x, 1 unita' per ambo/colpo
#   ✅ Numeri Spia Lab su modello storico multi-numero
#   ✅ condizioni: C1_exact, C2_exact, C3plus, NC2_W3_gap, NC2_W5, NC3_W5_gap
#   ✅ orizzonti paralleli H1/H2/H3
#   ✅ K1/K2/K3 + economia terno 45x
#   ✅ report Telegram cliccabili: /report /play /v48 /spie /spie_elite /spie_play /spie_top /spie_network /menu
#   ✅ sezione SPIE ELITE STORICHE — LIVE per confrontare storico vs live
#
# NOTA
#   Questo bot non predice le estrazioni: registra e confronta segnali statistici.
# ============================================================

import asyncio
import atexit
import csv
import hashlib
import json
import os
import re
import sys
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from itertools import combinations

import requests
from bs4 import BeautifulSoup
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

try:
    import fcntl
except ImportError:
    fcntl = None


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")
CHAT_ID = None

URL = "https://10elotto5minuti.com/estrazioni-di-oggi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "sniper_v48_playable_ambata_ambi_v6_state.json")
CSV_FILE = os.path.join(BASE_DIR, "sniper_v48_playable_ambata_ambi_v6_events.csv")
LOCK_FILE = "/tmp/sniper_v48_playable_ambata_ambi_v6.lock"

# Orario bot/report: GitHub gira spesso in UTC, qui forziamo Italia.
BOT_TZ_NAME = os.getenv("BOT_TZ", "Europe/Rome")
BOT_TZ = ZoneInfo(BOT_TZ_NAME)

# Persistenza GitHub Actions: salva state/csv nel repository per non spezzare la giornata
# tra una run programmata e la successiva. Richiede permissions: contents: write.
PERSIST_GIT_STATE = os.getenv("PERSIST_GIT_STATE", "1") != "0"
GIT_COMMIT_MIN_SECONDS = int(os.getenv("GIT_COMMIT_MIN_SECONDS", "300"))
_LAST_GIT_COMMIT_TS = 0.0

LOOP_SEC = 60
HISTORY_MAX = 320
PROCESSED_MAX = 1200

# v48 — core invariato
TOP_RITARDATARI = 10
PLAY_POSITIONS = [6, 7, 8, 9, 10]
WATCH_WINDOW = 12
HOT_TTL = 45
MIN_HOT_ACTIVE = 3
MAX_AMBI_PER_PLAY = 3
MAX_COLPI = 7
COOLDOWN_AFTER_PLAY = 5
CLUSTER_REUSE_AFTER = 12

# Economia teorica
AMBO_PAYOUT = 14.0
TERNO_PAYOUT = 45.0

# Numeri Spia Lab
SPY_HORIZONS = (1, 2, 3)
SPY_MAX_COLPI = max(SPY_HORIZONS)

# Modalità pulita: il bot calcola tutto, ma non intasa Telegram.
# Modalità REPORT ONLY: il bot calcola tutto, ma Telegram non riceve singoli segnali spia.
# I TRIS 3/3 entrano solo nei report aggregati.
DRAW_NOTIFY = False
SPY_NOTIFY_OPEN = False
SPY_NOTIFY_HIT_K2 = False
SPY_NOTIFY_HIT_K3 = False
SPY_OPEN_NOTIFY_MAX_LINES = 8
SPY_MIN_MODEL_EVENTS = 80
SPY_TOP_MIN_CLOSED = 20

# Filtro giocabilita' DECINA/MULTIPLA: non apre giocate automatiche,
# ma mostra in report/comando i numeri e gli ambi piu' supportati dai segnali aperti.
PLAYABLE_NETWORK = "DECINA"
PLAYABLE_LEVEL = "MULTIPLA"
PLAYABLE_MIN_PAIR_SUPPORT = 4
PLAYABLE_MAX_SIGNALS = 8
PLAYABLE_MAX_PAIRS = 6
PLAYABLE_MAX_NUMBERS = 7

# Giocata automatica/pratica: solo ambata + max 2 ambi, massimo 3 colpi.
# v48 resta come struttura/conferma, ma non apre piu' da sola la giocata operativa.
V48_NOTIFY_EVENTS = False
PLAYABLE_AUTO_ENABLED = True
PLAYABLE_NOTIFY_OPEN = True
PLAYABLE_NOTIFY_HIT = True
PLAYABLE_NOTIFY_STOP = True
PLAYABLE_MAX_COLPI = 3
PLAYABLE_MAX_AMBI = 2
PLAYABLE_MIN_SIGNALS = 6
PLAYABLE_MIN_DECINA_EXTRA = 15.0
PLAYABLE_MIN_MULTIPLA_EXTRA = 5.0
PLAYABLE_TOP_NUMBERS_FOR_CONFIRM = 5
PLAYABLE_REQUIRE_V48_CONFIRM = True


# Spie Elite Storiche — selezionate dal backtest H3 sullo storico gennaio-settembre.
# TOP3 = nucleo più pulito qualità/quantità; WATCH = estensione utile per confronto live.
SPY_ELITE_HISTORIC = {
    "5_C3plus": {
        "tier": "TOP3", "rank": 1,
        "label": "5 C3plus → 4-55-56", "network": "PONTE_55",
        "hist_closed": 2121, "hist_k2_pct": 52.90, "hist_k3_pct": 10.23, "hist_roi_pct": 58.75,
    },
    "10_C3plus": {
        "tier": "TOP3", "rank": 2,
        "label": "10 C3plus → 9-5-55", "network": "MOD5",
        "hist_closed": 2086, "hist_k2_pct": 58.10, "hist_k3_pct": 9.88, "hist_roi_pct": 52.97,
    },
    "20_C2_exact": {
        "tier": "TOP3", "rank": 3,
        "label": "20 C2_exact → 15-10-5", "network": "CATENA_5",
        "hist_closed": 3010, "hist_k2_pct": 54.39, "hist_k3_pct": 9.27, "hist_roi_pct": 43.72,
    },
    "15_C3plus": {
        "tier": "WATCH", "rank": 4,
        "label": "15 C3plus → 14-28-55", "network": "PONTE_55",
        "hist_closed": 2092, "hist_k2_pct": 55.02, "hist_k3_pct": 9.03, "hist_roi_pct": 39.70,
    },
    "9_C3plus": {
        "tier": "WATCH", "rank": 5,
        "label": "9 C3plus → 8-25-67", "network": "ALTRO",
        "hist_closed": 1795, "hist_k2_pct": 55.21, "hist_k3_pct": 8.91, "hist_roi_pct": 37.72,
    },
    "25_C2_exact": {
        "tier": "WATCH", "rank": 6,
        "label": "25 C2_exact → 20-15-10", "network": "CATENA_5",
        "hist_closed": 2816, "hist_k2_pct": 54.83, "hist_k3_pct": 8.31, "hist_roi_pct": 29.00,
    },
    "23_C3plus": {
        "tier": "WATCH", "rank": 7,
        "label": "23 C3plus → 22-42-39", "network": "LATERALE_23",
        "hist_closed": 1797, "hist_k2_pct": 51.75, "hist_k3_pct": 7.57, "hist_roi_pct": 16.50,
    },
}
SPY_ELITE_TOP3_KEYS = tuple(k for k, v in sorted(SPY_ELITE_HISTORIC.items(), key=lambda kv: kv[1]["rank"]) if v["tier"] == "TOP3")
SPY_ELITE_ALL_KEYS = tuple(k for k, v in sorted(SPY_ELITE_HISTORIC.items(), key=lambda kv: kv[1]["rank"]))
SPY_ELITE_MIN_CLOSED = 20

# Report automatici: due tranche giornaliere + fallback a cambio giorno.
AUTO_REPORT_ENABLED = True
AUTO_REPORT_TIMES = ("14:00", "23:50")
AUTO_REPORT_WINDOW_MINUTES = 8
SPY_REPORT_EVERY_DRAWS = 0

# Report automatici severi:
# evita report vuoti/giovani prodotti da istanze appena avviate o stati separati.
# I comandi manuali /report /spie restano sempre disponibili.
AUTO_REPORT_MIN_H3_CLOSED = 50
AUTO_REPORT_ALLOW_ACTIVE_V48_AFTER_COLPO = 1

# Menu Telegram cliccabile
MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        ["/report", "/play"],
        ["/v48", "/spie"],
        ["/spie_elite", "/spie_play"],
        ["/spie_top", "/spie_network"],
        ["/menu"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    input_field_placeholder="Tocca un comando",
)

# Pulsanti inline: utili anche quando non vuoi digitare nulla.
# Su alcuni canali/gruppi Telegram la tastiera fissa puo' non comparire;
# questi bottoni sotto al messaggio /menu restano cliccabili.
INLINE_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 Report", callback_data="report"), InlineKeyboardButton("🎲 Play", callback_data="play")],
    [InlineKeyboardButton("🎯 v48", callback_data="v48"), InlineKeyboardButton("🕵️ Spie", callback_data="spie")],
    [InlineKeyboardButton("⭐ Elite", callback_data="spie_elite"), InlineKeyboardButton("🎲 Giocabilità", callback_data="spie_play")],
    [InlineKeyboardButton("🏆 Top spie", callback_data="spie_top"), InlineKeyboardButton("🧬 Network", callback_data="spie_network")],
    [InlineKeyboardButton("🧭 Menu", callback_data="menu")],
])

# Modello storico spie incorporato.
# Ogni riga: numero spia + condizione + TOP3 accompagnatori + benchmark storico 1-colpo.
SPY_MODEL_EMBEDDED_JSON = r'[{"spy":1,"condition":"C1_exact","followers":[86,90,85],"events":8995,"k2_pct":0.032685,"base_k2_pct":0.030866,"k3_pct":0.002112,"base_k3_pct":0.00193,"k2_extra_pp":0.001819,"label":"1 C1_exact → 86-90-85"},{"spy":1,"condition":"NC2_W3_gap","followers":[90,85,73],"events":2295,"k2_pct":0.051416,"base_k2_pct":0.035273,"k3_pct":0.002179,"base_k3_pct":0.00156,"k2_extra_pp":0.016143,"label":"1 NC2_W3_gap → 90-85-73"},{"spy":1,"condition":"NC3_W5_gap","followers":[29,8,89],"events":2883,"k2_pct":0.08845,"base_k2_pct":0.073763,"k3_pct":0.001387,"base_k3_pct":0.001852,"k2_extra_pp":0.014687,"label":"1 NC3_W5_gap → 29-8-89"},{"spy":2,"condition":"NC2_W3_gap","followers":[90,89,87],"events":2219,"k2_pct":0.036503,"base_k2_pct":0.022638,"k3_pct":0.001803,"base_k3_pct":0.001755,"k2_extra_pp":0.013865,"label":"2 NC2_W3_gap → 90-89-87"},{"spy":3,"condition":"C1_exact","followers":[90,89,9],"events":8929,"k2_pct":0.026879,"base_k2_pct":0.02254,"k3_pct":0.002576,"base_k3_pct":0.00195,"k2_extra_pp":0.004338,"label":"3 C1_exact → 90-89-9"},{"spy":3,"condition":"C2_exact","followers":[2,30,45],"events":2133,"k2_pct":0.198781,"base_k2_pct":0.175311,"k3_pct":0.018284,"base_k3_pct":0.017802,"k2_extra_pp":0.02347,"label":"3 C2_exact → 2-30-45"},{"spy":3,"condition":"C3plus","followers":[2,56,63],"events":1745,"k2_pct":0.194269,"base_k2_pct":0.137211,"k3_pct":0.016619,"base_k3_pct":0.010724,"k2_extra_pp":0.057058,"label":"3 C3plus → 2-56-63"},{"spy":3,"condition":"NC2_W3_gap","followers":[90,89,88],"events":2178,"k2_pct":0.037649,"base_k2_pct":0.022501,"k3_pct":0.004132,"base_k3_pct":0.001774,"k2_extra_pp":0.015148,"label":"3 NC2_W3_gap → 90-89-88"},{"spy":4,"condition":"C1_exact","followers":[88,89,90],"events":9033,"k2_pct":0.027344,"base_k2_pct":0.022501,"k3_pct":0.002546,"base_k3_pct":0.001774,"k2_extra_pp":0.004843,"label":"4 C1_exact → 88-89-90"},{"spy":4,"condition":"C2_exact","followers":[60,40,66],"events":2172,"k2_pct":0.166667,"base_k2_pct":0.143821,"k3_pct":0.021639,"base_k3_pct":0.012928,"k2_extra_pp":0.022846,"label":"4 C2_exact → 60-40-66"},{"spy":4,"condition":"NC2_W3_gap","followers":[90,88,89],"events":2331,"k2_pct":0.032175,"base_k2_pct":0.022501,"k3_pct":0.003432,"base_k3_pct":0.001774,"k2_extra_pp":0.009674,"label":"4 NC2_W3_gap → 90-88-89"},{"spy":5,"condition":"C1_exact","followers":[88,87,89],"events":10466,"k2_pct":0.033537,"base_k2_pct":0.027376,"k3_pct":0.003535,"base_k3_pct":0.002184,"k2_extra_pp":0.006161,"label":"5 C1_exact → 88-87-89"},{"spy":5,"condition":"C2_exact","followers":[55,50,72],"events":2874,"k2_pct":0.20007,"base_k2_pct":0.163495,"k3_pct":0.019137,"base_k3_pct":0.014936,"k2_extra_pp":0.036575,"label":"5 C2_exact → 55-50-72"},{"spy":5,"condition":"C3plus","followers":[4,55,56],"events":2121,"k2_pct":0.219708,"base_k2_pct":0.15901,"k3_pct":0.03206,"base_k3_pct":0.016047,"k2_extra_pp":0.060697,"label":"5 C3plus → 4-55-56"},{"spy":5,"condition":"NC2_W3_gap","followers":[90,89,88],"events":3052,"k2_pct":0.033093,"base_k2_pct":0.022501,"k3_pct":0.001311,"base_k3_pct":0.001774,"k2_extra_pp":0.010592,"label":"5 NC2_W3_gap → 90-89-88"},{"spy":5,"condition":"NC3_W5_gap","followers":[88,86,87],"events":4004,"k2_pct":0.043207,"base_k2_pct":0.034317,"k3_pct":0.003247,"base_k3_pct":0.002437,"k2_extra_pp":0.008889,"label":"5 NC3_W5_gap → 88-86-87"},{"spy":6,"condition":"NC2_W3_gap","followers":[90,87,88],"events":2239,"k2_pct":0.042876,"base_k2_pct":0.025056,"k3_pct":0.00402,"base_k3_pct":0.001813,"k2_extra_pp":0.017821,"label":"6 NC2_W3_gap → 90-87-88"},{"spy":6,"condition":"NC3_W5_gap","followers":[90,9,36],"events":2713,"k2_pct":0.087357,"base_k2_pct":0.066958,"k3_pct":0.004423,"base_k3_pct":0.001989,"k2_extra_pp":0.020399,"label":"6 NC3_W5_gap → 90-9-36"},{"spy":7,"condition":"C1_exact","followers":[69,89,4],"events":8992,"k2_pct":0.077625,"base_k2_pct":0.068518,"k3_pct":0.002002,"base_k3_pct":0.001716,"k2_extra_pp":0.009107,"label":"7 C1_exact → 69-89-4"},{"spy":7,"condition":"NC2_W3_gap","followers":[88,90,85],"events":2252,"k2_pct":0.038188,"base_k2_pct":0.024373,"k3_pct":0.000888,"base_k3_pct":0.001501,"k2_extra_pp":0.013815,"label":"7 NC2_W3_gap → 88-90-85"},{"spy":7,"condition":"NC2_W5","followers":[8,15,25],"events":7283,"k2_pct":0.206371,"base_k2_pct":0.187712,"k3_pct":0.022793,"base_k3_pct":0.019167,"k2_extra_pp":0.018659,"label":"7 NC2_W5 → 8-15-25"},{"spy":7,"condition":"NC3_W5_gap","followers":[88,90,85],"events":2811,"k2_pct":0.03095,"base_k2_pct":0.024373,"k3_pct":0.000356,"base_k3_pct":0.001501,"k2_extra_pp":0.006577,"label":"7 NC3_W5_gap → 88-90-85"},{"spy":8,"condition":"C1_exact","followers":[87,90,89],"events":9169,"k2_pct":0.027593,"base_k2_pct":0.022638,"k3_pct":0.002181,"base_k3_pct":0.001755,"k2_extra_pp":0.004955,"label":"8 C1_exact → 87-90-89"},{"spy":8,"condition":"C2_exact","followers":[29,64,46],"events":2217,"k2_pct":0.156518,"base_k2_pct":0.128183,"k3_pct":0.016689,"base_k3_pct":0.010003,"k2_extra_pp":0.028335,"label":"8 C2_exact → 29-64-46"},{"spy":8,"condition":"NC2_W3_gap","followers":[90,89,83],"events":2298,"k2_pct":0.032202,"base_k2_pct":0.021624,"k3_pct":0.002176,"base_k3_pct":0.00156,"k2_extra_pp":0.010578,"label":"8 NC2_W3_gap → 90-89-83"},{"spy":9,"condition":"C1_exact","followers":[90,62,89],"events":8983,"k2_pct":0.025938,"base_k2_pct":0.023301,"k3_pct":0.001558,"base_k3_pct":0.001677,"k2_extra_pp":0.002637,"label":"9 C1_exact → 90-62-89"},{"spy":9,"condition":"C3plus","followers":[8,25,67],"events":1795,"k2_pct":0.222284,"base_k2_pct":0.159147,"k3_pct":0.028969,"base_k3_pct":0.014994,"k2_extra_pp":0.063137,"label":"9 C3plus → 8-25-67"},{"spy":9,"condition":"NC2_W3_gap","followers":[88,90,89],"events":2245,"k2_pct":0.035189,"base_k2_pct":0.022501,"k3_pct":0.002673,"base_k3_pct":0.001774,"k2_extra_pp":0.012688,"label":"9 NC2_W3_gap → 88-90-89"},{"spy":9,"condition":"NC3_W5_gap","followers":[28,35,8],"events":2869,"k2_pct":0.189265,"base_k2_pct":0.157801,"k3_pct":0.016731,"base_k3_pct":0.014487,"k2_extra_pp":0.031463,"label":"9 NC3_W5_gap → 28-35-8"},{"spy":10,"condition":"C1_exact","followers":[5,90,89],"events":10367,"k2_pct":0.028649,"base_k2_pct":0.022228,"k3_pct":0.002797,"base_k3_pct":0.001813,"k2_extra_pp":0.00642,"label":"10 C1_exact → 5-90-89"},{"spy":10,"condition":"C2_exact","followers":[5,87,77],"events":2912,"k2_pct":0.103022,"base_k2_pct":0.080724,"k3_pct":0.004808,"base_k3_pct":0.003315,"k2_extra_pp":0.022298,"label":"10 C2_exact → 5-87-77"},{"spy":10,"condition":"C3plus","followers":[9,5,55],"events":2086,"k2_pct":0.243528,"base_k2_pct":0.186094,"k3_pct":0.03164,"base_k3_pct":0.019245,"k2_extra_pp":0.057435,"label":"10 C3plus → 9-5-55"},{"spy":10,"condition":"NC2_W3_gap","followers":[90,89,50],"events":2946,"k2_pct":0.035302,"base_k2_pct":0.023164,"k3_pct":0.002037,"base_k3_pct":0.001833,"k2_extra_pp":0.012138,"label":"10 NC2_W3_gap → 90-89-50"},{"spy":10,"condition":"NC2_W5","followers":[5,1,23],"events":8968,"k2_pct":0.191793,"base_k2_pct":0.173244,"k3_pct":0.021521,"base_k3_pct":0.017256,"k2_extra_pp":0.018549,"label":"10 NC2_W5 → 5-1-23"},{"spy":10,"condition":"NC3_W5_gap","followers":[11,78,77],"events":4066,"k2_pct":0.132563,"base_k2_pct":0.11471,"k3_pct":0.012051,"base_k3_pct":0.009847,"k2_extra_pp":0.017853,"label":"10 NC3_W5_gap → 11-78-77"},{"spy":11,"condition":"C1_exact","followers":[90,88,86],"events":8954,"k2_pct":0.030601,"base_k2_pct":0.024763,"k3_pct":0.001899,"base_k3_pct":0.001599,"k2_extra_pp":0.005838,"label":"11 C1_exact → 90-88-86"},{"spy":11,"condition":"NC2_W3_gap","followers":[90,88,87],"events":2245,"k2_pct":0.035189,"base_k2_pct":0.025056,"k3_pct":0.003118,"base_k3_pct":0.001813,"k2_extra_pp":0.010134,"label":"11 NC2_W3_gap → 90-88-87"},{"spy":12,"condition":"C1_exact","followers":[89,86,90],"events":9030,"k2_pct":0.027353,"base_k2_pct":0.022521,"k3_pct":0.002658,"base_k3_pct":0.001911,"k2_extra_pp":0.004833,"label":"12 C1_exact → 89-86-90"},{"spy":12,"condition":"NC2_W3_gap","followers":[89,90,87],"events":2331,"k2_pct":0.031317,"base_k2_pct":0.022638,"k3_pct":0.002145,"base_k3_pct":0.001755,"k2_extra_pp":0.008679,"label":"12 NC2_W3_gap → 89-90-87"},{"spy":12,"condition":"NC2_W5","followers":[14,17,59],"events":7340,"k2_pct":0.16049,"base_k2_pct":0.147233,"k3_pct":0.013624,"base_k3_pct":0.012869,"k2_extra_pp":0.013257,"label":"12 NC2_W5 → 14-17-59"},{"spy":12,"condition":"NC3_W5_gap","followers":[89,90,86],"events":2897,"k2_pct":0.032447,"base_k2_pct":0.022521,"k3_pct":0.002761,"base_k3_pct":0.001911,"k2_extra_pp":0.009927,"label":"12 NC3_W5_gap → 89-90-86"},{"spy":13,"condition":"C1_exact","followers":[89,90,50],"events":9033,"k2_pct":0.027787,"base_k2_pct":0.023164,"k3_pct":0.00155,"base_k3_pct":0.001833,"k2_extra_pp":0.004623,"label":"13 C1_exact → 89-90-50"},{"spy":13,"condition":"C2_exact","followers":[43,61,70],"events":2104,"k2_pct":0.154468,"base_k2_pct":0.124537,"k3_pct":0.015684,"base_k3_pct":0.010295,"k2_extra_pp":0.029931,"label":"13 C2_exact → 43-61-70"},{"spy":13,"condition":"NC2_W3_gap","followers":[89,90,86],"events":2275,"k2_pct":0.037363,"base_k2_pct":0.022521,"k3_pct":0.005714,"base_k3_pct":0.001911,"k2_extra_pp":0.014842,"label":"13 NC2_W3_gap → 89-90-86"},{"spy":13,"condition":"NC3_W5_gap","followers":[89,86,82],"events":2748,"k2_pct":0.045488,"base_k2_pct":0.033693,"k3_pct":0.003639,"base_k3_pct":0.002008,"k2_extra_pp":0.011794,"label":"13 NC3_W5_gap → 89-86-82"},{"spy":14,"condition":"C1_exact","followers":[90,89,88],"events":9055,"k2_pct":0.024406,"base_k2_pct":0.022501,"k3_pct":0.001877,"base_k3_pct":0.001774,"k2_extra_pp":0.001905,"label":"14 C1_exact → 90-89-88"},{"spy":14,"condition":"C2_exact","followers":[2,40,76],"events":2201,"k2_pct":0.170831,"base_k2_pct":0.144952,"k3_pct":0.015902,"base_k3_pct":0.012538,"k2_extra_pp":0.02588,"label":"14 C2_exact → 2-40-76"},{"spy":14,"condition":"NC2_W3_gap","followers":[89,90,88],"events":2325,"k2_pct":0.034839,"base_k2_pct":0.022501,"k3_pct":0.003441,"base_k3_pct":0.001774,"k2_extra_pp":0.012337,"label":"14 NC2_W3_gap → 89-90-88"},{"spy":14,"condition":"NC3_W5_gap","followers":[89,90,76],"events":2996,"k2_pct":0.03271,"base_k2_pct":0.022638,"k3_pct":0.00267,"base_k3_pct":0.001794,"k2_extra_pp":0.010073,"label":"14 NC3_W5_gap → 89-90-76"},{"spy":15,"condition":"C1_exact","followers":[10,89,88],"events":10366,"k2_pct":0.035597,"base_k2_pct":0.02917,"k3_pct":0.004148,"base_k3_pct":0.002476,"k2_extra_pp":0.006427,"label":"15 C1_exact → 10-89-88"},{"spy":15,"condition":"C2_exact","followers":[10,5,52],"events":2961,"k2_pct":0.229314,"base_k2_pct":0.182233,"k3_pct":0.029044,"base_k3_pct":0.02059,"k2_extra_pp":0.047081,"label":"15 C2_exact → 10-5-52"},{"spy":15,"condition":"C3plus","followers":[14,28,55],"events":2092,"k2_pct":0.228489,"base_k2_pct":0.158152,"k3_pct":0.030593,"base_k3_pct":0.014273,"k2_extra_pp":0.070337,"label":"15 C3plus → 14-28-55"},{"spy":15,"condition":"NC2_W3_gap","followers":[89,10,90],"events":3041,"k2_pct":0.031897,"base_k2_pct":0.023398,"k3_pct":0.001644,"base_k3_pct":0.00156,"k2_extra_pp":0.008499,"label":"15 NC2_W3_gap → 89-10-90"},{"spy":15,"condition":"NC2_W5","followers":[10,16,82],"events":8903,"k2_pct":0.146018,"base_k2_pct":0.133779,"k3_pct":0.011681,"base_k3_pct":0.009769,"k2_extra_pp":0.012239,"label":"15 NC2_W5 → 10-16-82"},{"spy":15,"condition":"NC3_W5_gap","followers":[10,58,68],"events":4150,"k2_pct":0.173012,"base_k2_pct":0.154155,"k3_pct":0.020241,"base_k3_pct":0.014019,"k2_extra_pp":0.018857,"label":"15 NC3_W5_gap → 10-58-68"},{"spy":16,"condition":"C1_exact","followers":[88,90,59],"events":8991,"k2_pct":0.028362,"base_k2_pct":0.02451,"k3_pct":0.001891,"base_k3_pct":0.001638,"k2_extra_pp":0.003852,"label":"16 C1_exact → 88-90-59"},{"spy":16,"condition":"C3plus","followers":[15,10,54],"events":1905,"k2_pct":0.24252,"base_k2_pct":0.181473,"k3_pct":0.025197,"base_k3_pct":0.017646,"k2_extra_pp":0.061047,"label":"16 C3plus → 15-10-54"},{"spy":16,"condition":"NC2_W3_gap","followers":[89,90,88],"events":2264,"k2_pct":0.038869,"base_k2_pct":0.022501,"k3_pct":0.003092,"base_k3_pct":0.001774,"k2_extra_pp":0.016368,"label":"16 NC2_W3_gap → 89-90-88"},{"spy":16,"condition":"NC3_W5_gap","followers":[89,90,75],"events":2827,"k2_pct":0.034312,"base_k2_pct":0.022852,"k3_pct":0.003891,"base_k3_pct":0.002164,"k2_extra_pp":0.01146,"label":"16 NC3_W5_gap → 89-90-75"},{"spy":17,"condition":"C1_exact","followers":[90,86,88],"events":9072,"k2_pct":0.030093,"base_k2_pct":0.024763,"k3_pct":0.002315,"base_k3_pct":0.001599,"k2_extra_pp":0.005329,"label":"17 C1_exact → 90-86-88"},{"spy":17,"condition":"NC2_W3_gap","followers":[90,87,89],"events":2335,"k2_pct":0.035546,"base_k2_pct":0.022638,"k3_pct":0.003854,"base_k3_pct":0.001755,"k2_extra_pp":0.012908,"label":"17 NC2_W3_gap → 90-87-89"},{"spy":17,"condition":"NC3_W5_gap","followers":[87,76,89],"events":2823,"k2_pct":0.043216,"base_k2_pct":0.031178,"k3_pct":0.003188,"base_k3_pct":0.001969,"k2_extra_pp":0.012038,"label":"17 NC3_W5_gap → 87-76-89"},{"spy":18,"condition":"C1_exact","followers":[90,86,87],"events":8855,"k2_pct":0.033315,"base_k2_pct":0.027707,"k3_pct":0.001694,"base_k3_pct":0.001735,"k2_extra_pp":0.005607,"label":"18 C1_exact → 90-86-87"},{"spy":18,"condition":"NC2_W3_gap","followers":[90,88,89],"events":2203,"k2_pct":0.03586,"base_k2_pct":0.022501,"k3_pct":0.002724,"base_k3_pct":0.001774,"k2_extra_pp":0.013359,"label":"18 NC2_W3_gap → 90-88-89"},{"spy":18,"condition":"NC2_W5","followers":[16,11,44],"events":7007,"k2_pct":0.165121,"base_k2_pct":0.147955,"k3_pct":0.015413,"base_k3_pct":0.013395,"k2_extra_pp":0.017166,"label":"18 NC2_W5 → 16-11-44"},{"spy":18,"condition":"NC3_W5_gap","followers":[90,89,84],"events":2698,"k2_pct":0.032987,"base_k2_pct":0.022462,"k3_pct":0.002595,"base_k3_pct":0.00156,"k2_extra_pp":0.010525,"label":"18 NC3_W5_gap → 90-89-84"},{"spy":19,"condition":"C1_exact","followers":[89,85,90],"events":9037,"k2_pct":0.028771,"base_k2_pct":0.02215,"k3_pct":0.002434,"base_k3_pct":0.001618,"k2_extra_pp":0.00662,"label":"19 C1_exact → 89-85-90"},{"spy":19,"condition":"C2_exact","followers":[40,35,47],"events":2217,"k2_pct":0.198917,"base_k2_pct":0.165991,"k3_pct":0.023906,"base_k3_pct":0.01554,"k2_extra_pp":0.032927,"label":"19 C2_exact → 40-35-47"},{"spy":19,"condition":"NC2_W3_gap","followers":[89,90,86],"events":2243,"k2_pct":0.041016,"base_k2_pct":0.022521,"k3_pct":0.002675,"base_k3_pct":0.001911,"k2_extra_pp":0.018496,"label":"19 NC2_W3_gap → 89-90-86"},{"spy":19,"condition":"NC2_W5","followers":[2,17,23],"events":7202,"k2_pct":0.173007,"base_k2_pct":0.156163,"k3_pct":0.014996,"base_k3_pct":0.01439,"k2_extra_pp":0.016844,"label":"19 NC2_W5 → 2-17-23"},{"spy":19,"condition":"NC3_W5_gap","followers":[89,85,82],"events":2830,"k2_pct":0.044876,"base_k2_pct":0.036872,"k3_pct":0.004594,"base_k3_pct":0.001657,"k2_extra_pp":0.008005,"label":"19 NC3_W5_gap → 89-85-82"},{"spy":20,"condition":"C1_exact","followers":[15,90,87],"events":10384,"k2_pct":0.038424,"base_k2_pct":0.030028,"k3_pct":0.00183,"base_k3_pct":0.001618,"k2_extra_pp":0.008397,"label":"20 C1_exact → 15-90-87"},{"spy":20,"condition":"C2_exact","followers":[15,10,5],"events":3011,"k2_pct":0.272335,"base_k2_pct":0.212397,"k3_pct":0.034208,"base_k3_pct":0.024432,"k2_extra_pp":0.059938,"label":"20 C2_exact → 15-10-5"},{"spy":20,"condition":"C3plus","followers":[19,32,5],"events":2081,"k2_pct":0.219125,"base_k2_pct":0.166673,"k3_pct":0.027871,"base_k3_pct":0.016008,"k2_extra_pp":0.052452,"label":"20 C3plus → 19-32-5"},{"spy":20,"condition":"NC2_W3_gap","followers":[90,87,88],"events":3025,"k2_pct":0.035372,"base_k2_pct":0.025056,"k3_pct":0.004628,"base_k3_pct":0.001813,"k2_extra_pp":0.010316,"label":"20 NC2_W3_gap → 90-87-88"},{"spy":20,"condition":"NC3_W5_gap","followers":[10,5,15],"events":4194,"k2_pct":0.242012,"base_k2_pct":0.212397,"k3_pct":0.033143,"base_k3_pct":0.024432,"k2_extra_pp":0.029615,"label":"20 NC3_W5_gap → 10-5-15"},{"spy":21,"condition":"C1_exact","followers":[51,88,84],"events":8986,"k2_pct":0.051858,"base_k2_pct":0.04471,"k3_pct":0.003116,"base_k3_pct":0.002164,"k2_extra_pp":0.007148,"label":"21 C1_exact → 51-88-84"},{"spy":21,"condition":"C2_exact","followers":[40,12,25],"events":2145,"k2_pct":0.207925,"base_k2_pct":0.175428,"k3_pct":0.017249,"base_k3_pct":0.016593,"k2_extra_pp":0.032497,"label":"21 C2_exact → 40-12-25"},{"spy":21,"condition":"NC2_W3_gap","followers":[89,88,90],"events":2225,"k2_pct":0.034157,"base_k2_pct":0.022501,"k3_pct":0.003596,"base_k3_pct":0.001774,"k2_extra_pp":0.011656,"label":"21 NC2_W3_gap → 89-88-90"},{"spy":21,"condition":"NC3_W5_gap","followers":[89,87,90],"events":2761,"k2_pct":0.028613,"base_k2_pct":0.022638,"k3_pct":0.001449,"base_k3_pct":0.001755,"k2_extra_pp":0.005975,"label":"21 NC3_W5_gap → 89-87-90"},{"spy":22,"condition":"C2_exact","followers":[61,27,74],"events":2136,"k2_pct":0.13764,"base_k2_pct":0.120696,"k3_pct":0.010768,"base_k3_pct":0.008872,"k2_extra_pp":0.016945,"label":"22 C2_exact → 61-27-74"},{"spy":22,"condition":"C3plus","followers":[21,60,79],"events":1773,"k2_pct":0.168641,"base_k2_pct":0.122139,"k3_pct":0.01128,"base_k3_pct":0.00895,"k2_extra_pp":0.046502,"label":"22 C3plus → 21-60-79"},{"spy":22,"condition":"NC2_W3_gap","followers":[89,88,90],"events":2288,"k2_pct":0.034091,"base_k2_pct":0.022501,"k3_pct":0.002185,"base_k3_pct":0.001774,"k2_extra_pp":0.01159,"label":"22 NC2_W3_gap → 89-88-90"},{"spy":22,"condition":"NC3_W5_gap","followers":[88,83,89],"events":2760,"k2_pct":0.036957,"base_k2_pct":0.02642,"k3_pct":0.002536,"base_k3_pct":0.002067,"k2_extra_pp":0.010536,"label":"22 NC3_W5_gap → 88-83-89"},{"spy":23,"condition":"C1_exact","followers":[88,57,14],"events":9001,"k2_pct":0.083324,"base_k2_pct":0.075615,"k3_pct":0.003888,"base_k3_pct":0.002067,"k2_extra_pp":0.007709,"label":"23 C1_exact → 88-57-14"},{"spy":23,"condition":"C3plus","followers":[22,42,39],"events":1797,"k2_pct":0.194213,"base_k2_pct":0.136977,"k3_pct":0.025598,"base_k3_pct":0.011875,"k2_extra_pp":0.057236,"label":"23 C3plus → 22-42-39"},{"spy":23,"condition":"NC2_W3_gap","followers":[88,89,83],"events":2344,"k2_pct":0.037543,"base_k2_pct":0.02642,"k3_pct":0.001706,"base_k3_pct":0.002067,"k2_extra_pp":0.011122,"label":"23 NC2_W3_gap → 88-89-83"},{"spy":24,"condition":"C1_exact","followers":[88,69,87],"events":8991,"k2_pct":0.037482,"base_k2_pct":0.0342,"k3_pct":0.002781,"base_k3_pct":0.002769,"k2_extra_pp":0.003282,"label":"24 C1_exact → 88-69-87"},{"spy":24,"condition":"C3plus","followers":[9,60,8],"events":581,"k2_pct":0.203098,"base_k2_pct":0.148169,"k3_pct":0.018933,"base_k3_pct":0.012811,"k2_extra_pp":0.054929,"label":"24 C3plus → 9-60-8"},{"spy":24,"condition":"NC2_W3_gap","followers":[87,3,13],"events":2005,"k2_pct":0.099252,"base_k2_pct":0.08474,"k3_pct":0.00399,"base_k3_pct":0.003861,"k2_extra_pp":0.014511,"label":"24 NC2_W3_gap → 87-3-13"},{"spy":24,"condition":"NC3_W5_gap","followers":[16,57,45],"events":2370,"k2_pct":0.18481,"base_k2_pct":0.157567,"k3_pct":0.016034,"base_k3_pct":0.014468,"k2_extra_pp":0.027243,"label":"24 NC3_W5_gap → 16-57-45"},{"spy":25,"condition":"C1_exact","followers":[20,90,36],"events":10461,"k2_pct":0.096931,"base_k2_pct":0.079105,"k3_pct":0.002103,"base_k3_pct":0.001657,"k2_extra_pp":0.017826,"label":"25 C1_exact → 20-90-36"},{"spy":25,"condition":"C2_exact","followers":[20,15,10],"events":2816,"k2_pct":0.278409,"base_k2_pct":0.2123,"k3_pct":0.037642,"base_k3_pct":0.023476,"k2_extra_pp":0.066109,"label":"25 C2_exact → 20-15-10"},{"spy":25,"condition":"C3plus","followers":[20,10,80],"events":1014,"k2_pct":0.20217,"base_k2_pct":0.156709,"k3_pct":0.017751,"base_k3_pct":0.01361,"k2_extra_pp":0.04546,"label":"25 C3plus → 20-10-80"},{"spy":25,"condition":"NC2_W3_gap","followers":[20,90,24],"events":2795,"k2_pct":0.100894,"base_k2_pct":0.080314,"k3_pct":0.002862,"base_k3_pct":0.001911,"k2_extra_pp":0.02058,"label":"25 NC2_W3_gap → 20-90-24"},{"spy":25,"condition":"NC2_W5","followers":[20,46,6],"events":9189,"k2_pct":0.183371,"base_k2_pct":0.163963,"k3_pct":0.019262,"base_k3_pct":0.015501,"k2_extra_pp":0.019409,"label":"25 NC2_W5 → 20-46-6"},{"spy":25,"condition":"NC3_W5_gap","followers":[20,15,57],"events":3872,"k2_pct":0.217459,"base_k2_pct":0.183383,"k3_pct":0.019628,"base_k3_pct":0.017763,"k2_extra_pp":0.034075,"label":"25 NC3_W5_gap → 20-15-57"},{"spy":26,"condition":"NC2_W3_gap","followers":[19,27,14],"events":2006,"k2_pct":0.185942,"base_k2_pct":0.146122,"k3_pct":0.021436,"base_k3_pct":0.012245,"k2_extra_pp":0.03982,"label":"26 NC2_W3_gap → 19-27-14"},{"spy":27,"condition":"C1_exact","followers":[7,40,88],"events":8833,"k2_pct":0.098268,"base_k2_pct":0.088465,"k3_pct":0.003849,"base_k3_pct":0.00232,"k2_extra_pp":0.009803,"label":"27 C1_exact → 7-40-88"},{"spy":28,"condition":"C3plus","followers":[63,39,60],"events":588,"k2_pct":0.192177,"base_k2_pct":0.127189,"k3_pct":0.015306,"base_k3_pct":0.009691,"k2_extra_pp":0.064988,"label":"28 C3plus → 63-39-60"},{"spy":28,"condition":"NC2_W3_gap","followers":[63,52,27],"events":2003,"k2_pct":0.137294,"base_k2_pct":0.12479,"k3_pct":0.009985,"base_k3_pct":0.009203,"k2_extra_pp":0.012504,"label":"28 NC2_W3_gap → 63-52-27"},{"spy":29,"condition":"C1_exact","followers":[81,8,77],"events":9051,"k2_pct":0.115236,"base_k2_pct":0.10576,"k3_pct":0.008618,"base_k3_pct":0.008072,"k2_extra_pp":0.009476,"label":"29 C1_exact → 81-8-77"},{"spy":29,"condition":"C2_exact","followers":[84,59,54],"events":2059,"k2_pct":0.114133,"base_k2_pct":0.090493,"k3_pct":0.008742,"base_k3_pct":0.005128,"k2_extra_pp":0.023641,"label":"29 C2_exact → 84-59-54"},{"spy":29,"condition":"C3plus","followers":[65,67,78],"events":602,"k2_pct":0.156146,"base_k2_pct":0.113462,"k3_pct":0.016611,"base_k3_pct":0.008033,"k2_extra_pp":0.042684,"label":"29 C3plus → 65-67-78"},{"spy":29,"condition":"NC2_W3_gap","followers":[81,32,42],"events":2124,"k2_pct":0.134181,"base_k2_pct":0.103518,"k3_pct":0.012712,"base_k3_pct":0.007097,"k2_extra_pp":0.030663,"label":"29 NC2_W3_gap → 81-32-42"},{"spy":29,"condition":"NC2_W5","followers":[89,18,81],"events":7428,"k2_pct":0.058158,"base_k2_pct":0.053816,"k3_pct":0.002423,"base_k3_pct":0.002028,"k2_extra_pp":0.004342,"label":"29 NC2_W5 → 89-18-81"},{"spy":30,"condition":"C2_exact","followers":[25,20,1],"events":2772,"k2_pct":0.24531,"base_k2_pct":0.184729,"k3_pct":0.029582,"base_k3_pct":0.019187,"k2_extra_pp":0.060581,"label":"30 C2_exact → 25-20-1"},{"spy":30,"condition":"C3plus","followers":[20,25,10],"events":982,"k2_pct":0.271894,"base_k2_pct":0.200815,"k3_pct":0.026477,"base_k3_pct":0.021663,"k2_extra_pp":0.071079,"label":"30 C3plus → 20-25-10"},{"spy":30,"condition":"NC2_W3_gap","followers":[25,2,10],"events":2823,"k2_pct":0.211477,"base_k2_pct":0.181317,"k3_pct":0.024088,"base_k3_pct":0.018153,"k2_extra_pp":0.030161,"label":"30 NC2_W3_gap → 25-2-10"},{"spy":30,"condition":"NC3_W5_gap","followers":[10,25,15],"events":3866,"k2_pct":0.219607,"base_k2_pct":0.201069,"k3_pct":0.02328,"base_k3_pct":0.021019,"k2_extra_pp":0.018538,"label":"30 NC3_W5_gap → 10-25-15"},{"spy":31,"condition":"NC3_W5_gap","followers":[19,69,81],"events":2473,"k2_pct":0.130611,"base_k2_pct":0.112857,"k3_pct":0.009705,"base_k3_pct":0.007546,"k2_extra_pp":0.017753,"label":"31 NC3_W5_gap → 19-69-81"},{"spy":32,"condition":"C2_exact","followers":[35,33,13],"events":2012,"k2_pct":0.183897,"base_k2_pct":0.156202,"k3_pct":0.016899,"base_k3_pct":0.014721,"k2_extra_pp":0.027694,"label":"32 C2_exact → 35-33-13"},{"spy":32,"condition":"NC3_W5_gap","followers":[56,1,47],"events":2386,"k2_pct":0.162196,"base_k2_pct":0.135027,"k3_pct":0.021794,"base_k3_pct":0.012031,"k2_extra_pp":0.027169,"label":"32 NC3_W5_gap → 56-1-47"},{"spy":33,"condition":"C2_exact","followers":[26,29,87],"events":2043,"k2_pct":0.083211,"base_k2_pct":0.071579,"k3_pct":0.004895,"base_k3_pct":0.002925,"k2_extra_pp":0.011632,"label":"33 C2_exact → 26-29-87"},{"spy":33,"condition":"C3plus","followers":[39,67,18],"events":639,"k2_pct":0.173709,"base_k2_pct":0.135359,"k3_pct":0.017214,"base_k3_pct":0.011699,"k2_extra_pp":0.03835,"label":"33 C3plus → 39-67-18"},{"spy":34,"condition":"C1_exact","followers":[58,77,62],"events":8895,"k2_pct":0.1267,"base_k2_pct":0.115841,"k3_pct":0.009556,"base_k3_pct":0.008014,"k2_extra_pp":0.01086,"label":"34 C1_exact → 58-77-62"},{"spy":34,"condition":"C2_exact","followers":[13,30,18],"events":2008,"k2_pct":0.191733,"base_k2_pct":0.16406,"k3_pct":0.016932,"base_k3_pct":0.016203,"k2_extra_pp":0.027673,"label":"34 C2_exact → 13-30-18"},{"spy":35,"condition":"C1_exact","followers":[30,85,48],"events":10426,"k2_pct":0.123921,"base_k2_pct":0.098019,"k3_pct":0.007865,"base_k3_pct":0.005557,"k2_extra_pp":0.025902,"label":"35 C1_exact → 30-85-48"},{"spy":35,"condition":"C2_exact","followers":[30,25,4],"events":2823,"k2_pct":0.222813,"base_k2_pct":0.176286,"k3_pct":0.023025,"base_k3_pct":0.018777,"k2_extra_pp":0.046527,"label":"35 C2_exact → 30-25-4"},{"spy":35,"condition":"C3plus","followers":[30,15,29],"events":1050,"k2_pct":0.222857,"base_k2_pct":0.173615,"k3_pct":0.026667,"base_k3_pct":0.016574,"k2_extra_pp":0.049243,"label":"35 C3plus → 30-15-29"},{"spy":35,"condition":"NC2_W3_gap","followers":[30,8,85],"events":2848,"k2_pct":0.133427,"base_k2_pct":0.108295,"k3_pct":0.005969,"base_k3_pct":0.006123,"k2_extra_pp":0.025132,"label":"35 NC2_W3_gap → 30-8-85"},{"spy":35,"condition":"NC2_W5","followers":[30,25,12],"events":9029,"k2_pct":0.19094,"base_k2_pct":0.175175,"k3_pct":0.021043,"base_k3_pct":0.017705,"k2_extra_pp":0.015766,"label":"35 NC2_W5 → 30-25-12"},{"spy":35,"condition":"NC3_W5_gap","followers":[30,49,64],"events":3871,"k2_pct":0.16404,"base_k2_pct":0.143762,"k3_pct":0.016533,"base_k3_pct":0.012128,"k2_extra_pp":0.020278,"label":"35 NC3_W5_gap → 30-49-64"},{"spy":36,"condition":"C2_exact","followers":[31,33,25],"events":2029,"k2_pct":0.184327,"base_k2_pct":0.146902,"k3_pct":0.015278,"base_k3_pct":0.012811,"k2_extra_pp":0.037426,"label":"36 C2_exact → 31-33-25"},{"spy":37,"condition":"C3plus","followers":[54,32,24],"events":623,"k2_pct":0.168539,"base_k2_pct":0.126389,"k3_pct":0.014446,"base_k3_pct":0.010763,"k2_extra_pp":0.04215,"label":"37 C3plus → 54-32-24"},{"spy":37,"condition":"NC3_W5_gap","followers":[58,3,67],"events":2514,"k2_pct":0.153142,"base_k2_pct":0.133721,"k3_pct":0.016706,"base_k3_pct":0.010919,"k2_extra_pp":0.019422,"label":"37 NC3_W5_gap → 58-3-67"},{"spy":38,"condition":"C3plus","followers":[31,72,14],"events":661,"k2_pct":0.175492,"base_k2_pct":0.133292,"k3_pct":0.022693,"base_k3_pct":0.011836,"k2_extra_pp":0.0422,"label":"38 C3plus → 31-72-14"},{"spy":38,"condition":"NC3_W5_gap","followers":[48,42,69],"events":2454,"k2_pct":0.144254,"base_k2_pct":0.124244,"k3_pct":0.016707,"base_k3_pct":0.009691,"k2_extra_pp":0.02001,"label":"38 NC3_W5_gap → 48-42-69"},{"spy":39,"condition":"C3plus","followers":[88,63,10],"events":647,"k2_pct":0.120556,"base_k2_pct":0.087178,"k3_pct":0.004637,"base_k3_pct":0.002535,"k2_extra_pp":0.033379,"label":"39 C3plus → 88-63-10"},{"spy":39,"condition":"NC2_W5","followers":[81,25,79],"events":7274,"k2_pct":0.120291,"base_k2_pct":0.109192,"k3_pct":0.010311,"base_k3_pct":0.008579,"k2_extra_pp":0.0111,"label":"39 NC2_W5 → 81-25-79"},{"spy":40,"condition":"C2_exact","followers":[35,30,25],"events":2780,"k2_pct":0.228777,"base_k2_pct":0.180888,"k3_pct":0.02518,"base_k3_pct":0.018582,"k2_extra_pp":0.047889,"label":"40 C2_exact → 35-30-25"},{"spy":40,"condition":"NC2_W3_gap","followers":[35,32,43],"events":2866,"k2_pct":0.175157,"base_k2_pct":0.145537,"k3_pct":0.016399,"base_k3_pct":0.012577,"k2_extra_pp":0.02962,"label":"40 NC2_W3_gap → 35-32-43"},{"spy":40,"condition":"NC3_W5_gap","followers":[35,30,25],"events":3913,"k2_pct":0.198824,"base_k2_pct":0.180888,"k3_pct":0.020445,"base_k3_pct":0.018582,"k2_extra_pp":0.017937,"label":"40 NC3_W5_gap → 35-30-25"},{"spy":41,"condition":"C2_exact","followers":[78,6,13],"events":2034,"k2_pct":0.160275,"base_k2_pct":0.134267,"k3_pct":0.017207,"base_k3_pct":0.010217,"k2_extra_pp":0.026009,"label":"41 C2_exact → 78-6-13"},{"spy":41,"condition":"NC2_W3_gap","followers":[46,36,88],"events":2078,"k2_pct":0.085659,"base_k2_pct":0.06998,"k3_pct":0.004812,"base_k3_pct":0.002457,"k2_extra_pp":0.015679,"label":"41 NC2_W3_gap → 46-36-88"},{"spy":41,"condition":"NC3_W5_gap","followers":[73,6,42],"events":2515,"k2_pct":0.154672,"base_k2_pct":0.130776,"k3_pct":0.012326,"base_k3_pct":0.011621,"k2_extra_pp":0.023896,"label":"41 NC3_W5_gap → 73-6-42"},{"spy":42,"condition":"C3plus","followers":[27,47,56],"events":590,"k2_pct":0.159322,"base_k2_pct":0.12598,"k3_pct":0.023729,"base_k3_pct":0.009535,"k2_extra_pp":0.033342,"label":"42 C3plus → 27-47-56"},{"spy":42,"condition":"NC2_W3_gap","followers":[66,72,19],"events":2046,"k2_pct":0.154448,"base_k2_pct":0.134559,"k3_pct":0.012708,"base_k3_pct":0.0109,"k2_extra_pp":0.019889,"label":"42 NC2_W3_gap → 66-72-19"},{"spy":44,"condition":"C2_exact","followers":[67,77,43],"events":2023,"k2_pct":0.148295,"base_k2_pct":0.118531,"k3_pct":0.009886,"base_k3_pct":0.008813,"k2_extra_pp":0.029763,"label":"44 C2_exact → 67-77-43"},{"spy":44,"condition":"NC2_W3_gap","followers":[6,15,66],"events":2058,"k2_pct":0.192906,"base_k2_pct":0.16213,"k3_pct":0.01895,"base_k3_pct":0.015423,"k2_extra_pp":0.030776,"label":"44 NC2_W3_gap → 6-15-66"},{"spy":44,"condition":"NC3_W5_gap","followers":[15,73,66],"events":2619,"k2_pct":0.169912,"base_k2_pct":0.14854,"k3_pct":0.017946,"base_k3_pct":0.012284,"k2_extra_pp":0.021373,"label":"44 NC3_W5_gap → 15-73-66"},{"spy":45,"condition":"C1_exact","followers":[40,35,90],"events":10461,"k2_pct":0.105248,"base_k2_pct":0.087626,"k3_pct":0.002485,"base_k3_pct":0.00193,"k2_extra_pp":0.017622,"label":"45 C1_exact → 40-35-90"},{"spy":45,"condition":"C2_exact","followers":[40,35,30],"events":2859,"k2_pct":0.23015,"base_k2_pct":0.181999,"k3_pct":0.026583,"base_k3_pct":0.018524,"k2_extra_pp":0.048151,"label":"45 C2_exact → 40-35-30"},{"spy":45,"condition":"C3plus","followers":[40,15,54],"events":1021,"k2_pct":0.226249,"base_k2_pct":0.173849,"k3_pct":0.022527,"base_k3_pct":0.017295,"k2_extra_pp":0.0524,"label":"45 C3plus → 40-15-54"},{"spy":45,"condition":"NC2_W3_gap","followers":[40,30,73],"events":2880,"k2_pct":0.191319,"base_k2_pct":0.156846,"k3_pct":0.01875,"base_k3_pct":0.013044,"k2_extra_pp":0.034474,"label":"45 NC2_W3_gap → 40-30-73"},{"spy":45,"condition":"NC2_W5","followers":[35,40,42],"events":9192,"k2_pct":0.174826,"base_k2_pct":0.164431,"k3_pct":0.017624,"base_k3_pct":0.015228,"k2_extra_pp":0.010395,"label":"45 NC2_W5 → 35-40-42"},{"spy":45,"condition":"NC3_W5_gap","followers":[35,40,77],"events":3919,"k2_pct":0.170196,"base_k2_pct":0.152634,"k3_pct":0.016076,"base_k3_pct":0.013863,"k2_extra_pp":0.017562,"label":"45 NC3_W5_gap → 35-40-77"},{"spy":46,"condition":"C3plus","followers":[86,68,34],"events":622,"k2_pct":0.114148,"base_k2_pct":0.077409,"k3_pct":0.012862,"base_k3_pct":0.003841,"k2_extra_pp":0.036739,"label":"46 C3plus → 86-68-34"},{"spy":46,"condition":"NC2_W5","followers":[11,22,21],"events":7241,"k2_pct":0.170142,"base_k2_pct":0.153161,"k3_pct":0.018368,"base_k3_pct":0.014019,"k2_extra_pp":0.016982,"label":"46 NC2_W5 → 11-22-21"},{"spy":48,"condition":"NC2_W3_gap","followers":[86,84,88],"events":1987,"k2_pct":0.051334,"base_k2_pct":0.038315,"k3_pct":0.004529,"base_k3_pct":0.002379,"k2_extra_pp":0.013019,"label":"48 NC2_W3_gap → 86-84-88"},{"spy":48,"condition":"NC3_W5_gap","followers":[19,55,34],"events":2408,"k2_pct":0.190199,"base_k2_pct":0.15784,"k3_pct":0.013704,"base_k3_pct":0.014429,"k2_extra_pp":0.032359,"label":"48 NC3_W5_gap → 19-55-34"},{"spy":49,"condition":"NC2_W3_gap","followers":[15,81,42],"events":2062,"k2_pct":0.164403,"base_k2_pct":0.128008,"k3_pct":0.008244,"base_k3_pct":0.008774,"k2_extra_pp":0.036396,"label":"49 NC2_W3_gap → 15-81-42"},{"spy":49,"condition":"NC3_W5_gap","followers":[89,46,81],"events":2466,"k2_pct":0.064477,"base_k2_pct":0.050111,"k3_pct":0.002028,"base_k3_pct":0.001618,"k2_extra_pp":0.014366,"label":"49 NC3_W5_gap → 89-46-81"},{"spy":50,"condition":"C1_exact","followers":[45,39,81],"events":10459,"k2_pct":0.151544,"base_k2_pct":0.121573,"k3_pct":0.010995,"base_k3_pct":0.008131,"k2_extra_pp":0.029971,"label":"50 C1_exact → 45-39-81"},{"spy":50,"condition":"C2_exact","followers":[45,40,18],"events":2875,"k2_pct":0.241391,"base_k2_pct":0.174395,"k3_pct":0.027478,"base_k3_pct":0.018251,"k2_extra_pp":0.066997,"label":"50 C2_exact → 45-40-18"},{"spy":50,"condition":"C3plus","followers":[35,4,40],"events":1024,"k2_pct":0.222656,"base_k2_pct":0.177183,"k3_pct":0.022461,"base_k3_pct":0.018836,"k2_extra_pp":0.045473,"label":"50 C3plus → 35-4-40"},{"spy":50,"condition":"NC2_W3_gap","followers":[45,39,25],"events":2848,"k2_pct":0.202949,"base_k2_pct":0.166244,"k3_pct":0.019663,"base_k3_pct":0.01595,"k2_extra_pp":0.036705,"label":"50 NC2_W3_gap → 45-39-25"},{"spy":50,"condition":"NC2_W5","followers":[45,40,35],"events":9152,"k2_pct":0.200066,"base_k2_pct":0.184222,"k3_pct":0.019996,"base_k3_pct":0.019206,"k2_extra_pp":0.015844,"label":"50 NC2_W5 → 45-40-35"},{"spy":50,"condition":"NC3_W5_gap","followers":[45,40,20],"events":3920,"k2_pct":0.229082,"base_k2_pct":0.19518,"k3_pct":0.029082,"base_k3_pct":0.019109,"k2_extra_pp":0.033902,"label":"50 NC3_W5_gap → 45-40-20"},{"spy":51,"condition":"NC2_W5","followers":[63,45,66],"events":7369,"k2_pct":0.162437,"base_k2_pct":0.143899,"k3_pct":0.018727,"base_k3_pct":0.012908,"k2_extra_pp":0.018538,"label":"51 NC2_W5 → 63-45-66"},{"spy":52,"condition":"NC2_W3_gap","followers":[5,8,1],"events":2045,"k2_pct":0.213692,"base_k2_pct":0.17611,"k3_pct":0.019071,"base_k3_pct":0.017022,"k2_extra_pp":0.037581,"label":"52 NC2_W3_gap → 5-8-1"},{"spy":53,"condition":"C2_exact","followers":[82,3,83],"events":2032,"k2_pct":0.103839,"base_k2_pct":0.082459,"k3_pct":0.007382,"base_k3_pct":0.006259,"k2_extra_pp":0.021379,"label":"53 C2_exact → 82-3-83"},{"spy":54,"condition":"C2_exact","followers":[85,66,52],"events":2029,"k2_pct":0.101528,"base_k2_pct":0.083532,"k3_pct":0.007886,"base_k3_pct":0.004543,"k2_extra_pp":0.017996,"label":"54 C2_exact → 85-66-52"},{"spy":54,"condition":"NC2_W3_gap","followers":[84,70,71],"events":2025,"k2_pct":0.108642,"base_k2_pct":0.087451,"k3_pct":0.003951,"base_k3_pct":0.004387,"k2_extra_pp":0.021191,"label":"54 NC2_W3_gap → 84-70-71"},{"spy":54,"condition":"NC3_W5_gap","followers":[48,16,51],"events":2502,"k2_pct":0.156675,"base_k2_pct":0.1361,"k3_pct":0.013589,"base_k3_pct":0.012148,"k2_extra_pp":0.020575,"label":"54 NC3_W5_gap → 48-16-51"},{"spy":55,"condition":"C2_exact","followers":[50,45,42],"events":2906,"k2_pct":0.21989,"base_k2_pct":0.165737,"k3_pct":0.0234,"base_k3_pct":0.016086,"k2_extra_pp":0.054153,"label":"55 C2_exact → 50-45-42"},{"spy":55,"condition":"C3plus","followers":[45,50,40],"events":1109,"k2_pct":0.228133,"base_k2_pct":0.184534,"k3_pct":0.019838,"base_k3_pct":0.017978,"k2_extra_pp":0.0436,"label":"55 C3plus → 45-50-40"},{"spy":55,"condition":"NC3_W5_gap","followers":[50,78,45],"events":4126,"k2_pct":0.167232,"base_k2_pct":0.149982,"k3_pct":0.016723,"base_k3_pct":0.012811,"k2_extra_pp":0.01725,"label":"55 NC3_W5_gap → 50-78-45"},{"spy":56,"condition":"C2_exact","followers":[52,61,47],"events":2083,"k2_pct":0.151224,"base_k2_pct":0.125356,"k3_pct":0.010082,"base_k3_pct":0.009769,"k2_extra_pp":0.025868,"label":"56 C2_exact → 52-61-47"},{"spy":56,"condition":"NC3_W5_gap","followers":[55,21,4],"events":2522,"k2_pct":0.191118,"base_k2_pct":0.167824,"k3_pct":0.021015,"base_k3_pct":0.016379,"k2_extra_pp":0.023295,"label":"56 NC3_W5_gap → 55-21-4"},{"spy":57,"condition":"C2_exact","followers":[55,87,15],"events":2098,"k2_pct":0.133937,"base_k2_pct":0.108509,"k3_pct":0.003813,"base_k3_pct":0.004036,"k2_extra_pp":0.025428,"label":"57 C2_exact → 55-87-15"},{"spy":57,"condition":"NC2_W3_gap","followers":[77,64,81],"events":1992,"k2_pct":0.121988,"base_k2_pct":0.095777,"k3_pct":0.01004,"base_k3_pct":0.006649,"k2_extra_pp":0.026211,"label":"57 NC2_W3_gap → 77-64-81"},{"spy":57,"condition":"NC3_W5_gap","followers":[73,28,63],"events":2498,"k2_pct":0.13811,"base_k2_pct":0.121495,"k3_pct":0.008006,"base_k3_pct":0.009613,"k2_extra_pp":0.016615,"label":"57 NC3_W5_gap → 73-28-63"},{"spy":58,"condition":"C3plus","followers":[32,61,88],"events":645,"k2_pct":0.086822,"base_k2_pct":0.06805,"k3_pct":0.013953,"base_k3_pct":0.002554,"k2_extra_pp":0.018772,"label":"58 C3plus → 32-61-88"},{"spy":58,"condition":"NC3_W5_gap","followers":[35,10,13],"events":2577,"k2_pct":0.207606,"base_k2_pct":0.18352,"k3_pct":0.022507,"base_k3_pct":0.018426,"k2_extra_pp":0.024086,"label":"58 NC3_W5_gap → 35-10-13"},{"spy":61,"condition":"C1_exact","followers":[19,59,83],"events":9023,"k2_pct":0.116591,"base_k2_pct":0.103654,"k3_pct":0.007758,"base_k3_pct":0.006415,"k2_extra_pp":0.012937,"label":"61 C1_exact → 19-59-83"},{"spy":62,"condition":"NC2_W3_gap","followers":[83,9,90],"events":2013,"k2_pct":0.064083,"base_k2_pct":0.044866,"k3_pct":0.000994,"base_k3_pct":0.001501,"k2_extra_pp":0.019217,"label":"62 NC2_W3_gap → 83-9-90"},{"spy":63,"condition":"C2_exact","followers":[5,61,67],"events":2012,"k2_pct":0.184891,"base_k2_pct":0.1524,"k3_pct":0.01839,"base_k3_pct":0.013922,"k2_extra_pp":0.03249,"label":"63 C2_exact → 5-61-67"},{"spy":63,"condition":"C3plus","followers":[29,51,6],"events":579,"k2_pct":0.16753,"base_k2_pct":0.136314,"k3_pct":0.018998,"base_k3_pct":0.011894,"k2_extra_pp":0.031216,"label":"63 C3plus → 29-51-6"},{"spy":64,"condition":"NC3_W5_gap","followers":[69,44,83],"events":2454,"k2_pct":0.114099,"base_k2_pct":0.094334,"k3_pct":0.008557,"base_k3_pct":0.006025,"k2_extra_pp":0.019766,"label":"64 NC3_W5_gap → 69-44-83"},{"spy":65,"condition":"NC2_W3_gap","followers":[79,66,80],"events":2054,"k2_pct":0.123174,"base_k2_pct":0.099306,"k3_pct":0.009737,"base_k3_pct":0.007702,"k2_extra_pp":0.023868,"label":"65 NC2_W3_gap → 79-66-80"},{"spy":65,"condition":"NC3_W5_gap","followers":[21,9,47],"events":2445,"k2_pct":0.17137,"base_k2_pct":0.143645,"k3_pct":0.022495,"base_k3_pct":0.012811,"k2_extra_pp":0.027725,"label":"65 NC3_W5_gap → 21-9-47"},{"spy":66,"condition":"C2_exact","followers":[25,69,26],"events":1962,"k2_pct":0.175841,"base_k2_pct":0.143684,"k3_pct":0.013761,"base_k3_pct":0.011855,"k2_extra_pp":0.032157,"label":"66 C2_exact → 25-69-26"},{"spy":66,"condition":"C3plus","followers":[49,28,76],"events":594,"k2_pct":0.181818,"base_k2_pct":0.117771,"k3_pct":0.010101,"base_k3_pct":0.008579,"k2_extra_pp":0.064047,"label":"66 C3plus → 49-28-76"},{"spy":66,"condition":"NC2_W3_gap","followers":[72,25,70],"events":2032,"k2_pct":0.163878,"base_k2_pct":0.141423,"k3_pct":0.01624,"base_k3_pct":0.012323,"k2_extra_pp":0.022455,"label":"66 NC2_W3_gap → 72-25-70"},{"spy":66,"condition":"NC3_W5_gap","followers":[25,40,1],"events":2447,"k2_pct":0.203106,"base_k2_pct":0.17533,"k3_pct":0.028198,"base_k3_pct":0.017841,"k2_extra_pp":0.027775,"label":"66 NC3_W5_gap → 25-40-1"},{"spy":67,"condition":"C3plus","followers":[90,2,45],"events":637,"k2_pct":0.130298,"base_k2_pct":0.082303,"k3_pct":0.00314,"base_k3_pct":0.001345,"k2_extra_pp":0.047995,"label":"67 C3plus → 90-2-45"},{"spy":67,"condition":"NC2_W5","followers":[1,71,75],"events":7146,"k2_pct":0.139659,"base_k2_pct":0.127481,"k3_pct":0.011755,"base_k3_pct":0.009925,"k2_extra_pp":0.012177,"label":"67 NC2_W5 → 1-71-75"},{"spy":67,"condition":"NC3_W5_gap","followers":[57,83,42],"events":2414,"k2_pct":0.110605,"base_k2_pct":0.095465,"k3_pct":0.009942,"base_k3_pct":0.005752,"k2_extra_pp":0.01514,"label":"67 NC3_W5_gap → 57-83-42"},{"spy":68,"condition":"C3plus","followers":[55,65,13],"events":573,"k2_pct":0.21466,"base_k2_pct":0.157372,"k3_pct":0.022688,"base_k3_pct":0.014273,"k2_extra_pp":0.057287,"label":"68 C3plus → 55-65-13"},{"spy":69,"condition":"NC2_W5","followers":[51,39,21],"events":7185,"k2_pct":0.145999,"base_k2_pct":0.136684,"k3_pct":0.014057,"base_k3_pct":0.011426,"k2_extra_pp":0.009314,"label":"69 NC2_W5 → 51-39-21"},{"spy":70,"condition":"C3plus","followers":[37,76,43],"events":519,"k2_pct":0.175337,"base_k2_pct":0.119331,"k3_pct":0.009634,"base_k3_pct":0.009125,"k2_extra_pp":0.056006,"label":"70 C3plus → 37-76-43"},{"spy":70,"condition":"NC2_W3_gap","followers":[6,23,75],"events":1944,"k2_pct":0.165123,"base_k2_pct":0.137718,"k3_pct":0.016461,"base_k3_pct":0.01166,"k2_extra_pp":0.027406,"label":"70 NC2_W3_gap → 6-23-75"},{"spy":72,"condition":"C3plus","followers":[10,89,87],"events":505,"k2_pct":0.055446,"base_k2_pct":0.031861,"k3_pct":0.00198,"base_k3_pct":0.002067,"k2_extra_pp":0.023585,"label":"72 C3plus → 10-89-87"},{"spy":74,"condition":"C2_exact","followers":[89,86,40],"events":1753,"k2_pct":0.047918,"base_k2_pct":0.036248,"k3_pct":0.002852,"base_k3_pct":0.001969,"k2_extra_pp":0.01167,"label":"74 C2_exact → 89-86-40"},{"spy":74,"condition":"C3plus","followers":[76,16,11],"events":468,"k2_pct":0.188034,"base_k2_pct":0.136684,"k3_pct":0.025641,"base_k3_pct":0.010666,"k2_extra_pp":0.05135,"label":"74 C3plus → 76-16-11"},{"spy":75,"condition":"NC3_W5_gap","followers":[21,7,90],"events":2103,"k2_pct":0.096529,"base_k2_pct":0.075381,"k3_pct":0.001902,"base_k3_pct":0.001891,"k2_extra_pp":0.021148,"label":"75 NC3_W5_gap → 21-7-90"},{"spy":76,"condition":"C1_exact","followers":[45,55,16],"events":8397,"k2_pct":0.193045,"base_k2_pct":0.178938,"k3_pct":0.021793,"base_k3_pct":0.018329,"k2_extra_pp":0.014107,"label":"76 C1_exact → 45-55-16"},{"spy":76,"condition":"C2_exact","followers":[23,13,70],"events":1656,"k2_pct":0.174517,"base_k2_pct":0.142904,"k3_pct":0.014493,"base_k3_pct":0.011972,"k2_extra_pp":0.031612,"label":"76 C2_exact → 23-13-70"},{"spy":76,"condition":"NC2_W3_gap","followers":[41,49,48],"events":1751,"k2_pct":0.149629,"base_k2_pct":0.126955,"k3_pct":0.018275,"base_k3_pct":0.009691,"k2_extra_pp":0.022674,"label":"76 NC2_W3_gap → 41-49-48"},{"spy":76,"condition":"NC3_W5_gap","followers":[23,49,87],"events":1901,"k2_pct":0.101526,"base_k2_pct":0.078559,"k3_pct":0.00526,"base_k3_pct":0.002983,"k2_extra_pp":0.022966,"label":"76 NC3_W5_gap → 23-49-87"},{"spy":77,"condition":"NC3_W5_gap","followers":[29,50,5],"events":1865,"k2_pct":0.198391,"base_k2_pct":0.177222,"k3_pct":0.028418,"base_k3_pct":0.016808,"k2_extra_pp":0.02117,"label":"77 NC3_W5_gap → 29-50-5"},{"spy":79,"condition":"C2_exact","followers":[90,55,29],"events":1494,"k2_pct":0.084337,"base_k2_pct":0.07622,"k3_pct":0.002677,"base_k3_pct":0.001657,"k2_extra_pp":0.008118,"label":"79 C2_exact → 90-55-29"},{"spy":79,"condition":"NC2_W3_gap","followers":[32,31,49],"events":1455,"k2_pct":0.164948,"base_k2_pct":0.127462,"k3_pct":0.014433,"base_k3_pct":0.010159,"k2_extra_pp":0.037487,"label":"79 NC2_W3_gap → 32-31-49"},{"spy":80,"condition":"C1_exact","followers":[3,55,44],"events":7345,"k2_pct":0.171818,"base_k2_pct":0.156924,"k3_pct":0.017427,"base_k3_pct":0.015072,"k2_extra_pp":0.014894,"label":"80 C1_exact → 3-55-44"},{"spy":80,"condition":"NC2_W3_gap","followers":[55,3,22],"events":1325,"k2_pct":0.211321,"base_k2_pct":0.166907,"k3_pct":0.022642,"base_k3_pct":0.016847,"k2_extra_pp":0.044414,"label":"80 NC2_W3_gap → 55-3-22"},{"spy":80,"condition":"NC2_W5","followers":[22,88,86],"events":5149,"k2_pct":0.047776,"base_k2_pct":0.039406,"k3_pct":0.00369,"base_k3_pct":0.00232,"k2_extra_pp":0.00837,"label":"80 NC2_W5 → 22-88-86"},{"spy":81,"condition":"C1_exact","followers":[55,68,21],"events":6965,"k2_pct":0.174444,"base_k2_pct":0.157158,"k3_pct":0.017373,"base_k3_pct":0.01593,"k2_extra_pp":0.017286,"label":"81 C1_exact → 55-68-21"},{"spy":81,"condition":"NC2_W3_gap","followers":[55,68,34],"events":1139,"k2_pct":0.19403,"base_k2_pct":0.147857,"k3_pct":0.014925,"base_k3_pct":0.013512,"k2_extra_pp":0.046173,"label":"81 NC2_W3_gap → 55-68-34"},{"spy":81,"condition":"NC3_W5_gap","followers":[90,83,76],"events":1110,"k2_pct":0.063964,"base_k2_pct":0.042058,"k3_pct":0.0,"base_k3_pct":0.001384,"k2_extra_pp":0.021906,"label":"81 NC3_W5_gap → 90-83-76"},{"spy":82,"condition":"C2_exact","followers":[26,6,89],"events":989,"k2_pct":0.092012,"base_k2_pct":0.071248,"k3_pct":0.002022,"base_k3_pct":0.002145,"k2_extra_pp":0.020765,"label":"82 C2_exact → 26-6-89"},{"spy":82,"condition":"C3plus","followers":[89,5,54],"events":164,"k2_pct":0.195122,"base_k2_pct":0.081972,"k3_pct":0.006098,"base_k3_pct":0.001852,"k2_extra_pp":0.11315,"label":"82 C3plus → 89-5-54"},{"spy":82,"condition":"NC2_W3_gap","followers":[29,15,13],"events":1060,"k2_pct":0.20283,"base_k2_pct":0.164041,"k3_pct":0.017925,"base_k3_pct":0.015384,"k2_extra_pp":0.038789,"label":"82 NC2_W3_gap → 29-15-13"},{"spy":82,"condition":"NC2_W5","followers":[90,84,29],"events":4563,"k2_pct":0.042954,"base_k2_pct":0.038217,"k3_pct":0.001534,"base_k3_pct":0.001521,"k2_extra_pp":0.004737,"label":"82 NC2_W5 → 90-84-29"},{"spy":83,"condition":"C2_exact","followers":[87,89,88],"events":826,"k2_pct":0.039952,"base_k2_pct":0.027376,"k3_pct":0.007264,"base_k3_pct":0.002184,"k2_extra_pp":0.012576,"label":"83 C2_exact → 87-89-88"},{"spy":83,"condition":"NC2_W5","followers":[89,88,87],"events":3700,"k2_pct":0.038108,"base_k2_pct":0.027376,"k3_pct":0.001892,"base_k3_pct":0.002184,"k2_extra_pp":0.010732,"label":"83 NC2_W5 → 89-88-87"},{"spy":83,"condition":"NC3_W5_gap","followers":[89,34,82],"events":695,"k2_pct":0.067626,"base_k2_pct":0.047713,"k3_pct":0.002878,"base_k3_pct":0.001638,"k2_extra_pp":0.019913,"label":"83 NC3_W5_gap → 89-34-82"},{"spy":84,"condition":"C2_exact","followers":[87,89,86],"events":650,"k2_pct":0.06,"base_k2_pct":0.030125,"k3_pct":0.004615,"base_k3_pct":0.002047,"k2_extra_pp":0.029875,"label":"84 C2_exact → 87-89-86"},{"spy":84,"condition":"NC2_W5","followers":[90,87,88],"events":3203,"k2_pct":0.029035,"base_k2_pct":0.025056,"k3_pct":0.00281,"base_k3_pct":0.001813,"k2_extra_pp":0.00398,"label":"84 NC2_W5 → 90-87-88"},{"spy":84,"condition":"NC3_W5_gap","followers":[50,90,81],"events":563,"k2_pct":0.078153,"base_k2_pct":0.055044,"k3_pct":0.007105,"base_k3_pct":0.001599,"k2_extra_pp":0.023108,"label":"84 NC3_W5_gap → 50-90-81"},{"spy":85,"condition":"C1_exact","followers":[55,49,48],"events":4826,"k2_pct":0.167219,"base_k2_pct":0.146999,"k3_pct":0.015541,"base_k3_pct":0.012538,"k2_extra_pp":0.02022,"label":"85 C1_exact → 55-49-48"},{"spy":85,"condition":"C2_exact","followers":[88,82,87],"events":500,"k2_pct":0.056,"base_k2_pct":0.033869,"k3_pct":0.006,"base_k3_pct":0.002827,"k2_extra_pp":0.022131,"label":"85 C2_exact → 88-82-87"},{"spy":85,"condition":"NC2_W5","followers":[89,90,88],"events":2656,"k2_pct":0.034639,"base_k2_pct":0.022501,"k3_pct":0.001883,"base_k3_pct":0.001774,"k2_extra_pp":0.012137,"label":"85 NC2_W5 → 89-90-88"},{"spy":85,"condition":"NC3_W5_gap","followers":[88,41,90],"events":411,"k2_pct":0.043796,"base_k2_pct":0.025056,"k3_pct":0.007299,"base_k3_pct":0.001755,"k2_extra_pp":0.01874,"label":"85 NC3_W5_gap → 88-41-90"},{"spy":86,"condition":"C2_exact","followers":[89,90,88],"events":337,"k2_pct":0.059347,"base_k2_pct":0.022501,"k3_pct":0.002967,"base_k3_pct":0.001774,"k2_extra_pp":0.036846,"label":"86 C2_exact → 89-90-88"},{"spy":86,"condition":"NC2_W5","followers":[89,88,90],"events":2178,"k2_pct":0.039945,"base_k2_pct":0.022501,"k3_pct":0.002296,"base_k3_pct":0.001774,"k2_extra_pp":0.017444,"label":"86 NC2_W5 → 89-88-90"},{"spy":86,"condition":"NC3_W5_gap","followers":[16,90,74],"events":302,"k2_pct":0.099338,"base_k2_pct":0.065105,"k3_pct":0.0,"base_k3_pct":0.001794,"k2_extra_pp":0.034232,"label":"86 NC3_W5_gap → 16-90-74"},{"spy":87,"condition":"C1_exact","followers":[55,6,3],"events":3343,"k2_pct":0.20341,"base_k2_pct":0.167804,"k3_pct":0.021238,"base_k3_pct":0.016398,"k2_extra_pp":0.035606,"label":"87 C1_exact → 55-6-3"},{"spy":87,"condition":"C2_exact","followers":[90,89,85],"events":178,"k2_pct":0.067416,"base_k2_pct":0.02215,"k3_pct":0.005618,"base_k3_pct":0.001618,"k2_extra_pp":0.045265,"label":"87 C2_exact → 90-89-85"},{"spy":87,"condition":"NC2_W3_gap","followers":[25,33,6],"events":498,"k2_pct":0.204819,"base_k2_pct":0.159868,"k3_pct":0.028112,"base_k3_pct":0.014643,"k2_extra_pp":0.044951,"label":"87 NC2_W3_gap → 25-33-6"},{"spy":87,"condition":"NC2_W5","followers":[90,89,88],"events":1875,"k2_pct":0.0352,"base_k2_pct":0.022501,"k3_pct":0.0048,"base_k3_pct":0.001774,"k2_extra_pp":0.012699,"label":"87 NC2_W5 → 90-89-88"},{"spy":87,"condition":"NC3_W5_gap","followers":[6,62,37],"events":216,"k2_pct":0.189815,"base_k2_pct":0.137347,"k3_pct":0.027778,"base_k3_pct":0.011114,"k2_extra_pp":0.052467,"label":"87 NC3_W5_gap → 6-62-37"},{"spy":88,"condition":"NC2_W3_gap","followers":[67,6,55],"events":446,"k2_pct":0.210762,"base_k2_pct":0.158425,"k3_pct":0.026906,"base_k3_pct":0.014526,"k2_extra_pp":0.052337,"label":"88 NC2_W3_gap → 67-6-55"},{"spy":88,"condition":"NC2_W5","followers":[89,90,87],"events":1645,"k2_pct":0.037082,"base_k2_pct":0.022638,"k3_pct":0.007295,"base_k3_pct":0.001755,"k2_extra_pp":0.014444,"label":"88 NC2_W5 → 89-90-87"},{"spy":89,"condition":"C1_exact","followers":[55,70,33],"events":2260,"k2_pct":0.187611,"base_k2_pct":0.147175,"k3_pct":0.014602,"base_k3_pct":0.012362,"k2_extra_pp":0.040436,"label":"89 C1_exact → 55-70-33"},{"spy":89,"condition":"NC2_W3_gap","followers":[15,10,70],"events":420,"k2_pct":0.245238,"base_k2_pct":0.177183,"k3_pct":0.042857,"base_k3_pct":0.018465,"k2_extra_pp":0.068055,"label":"89 NC2_W3_gap → 15-10-70"},{"spy":89,"condition":"NC2_W5","followers":[88,90,84],"events":1473,"k2_pct":0.038018,"base_k2_pct":0.025114,"k3_pct":0.000679,"base_k3_pct":0.001657,"k2_extra_pp":0.012904,"label":"89 NC2_W5 → 88-90-84"},{"spy":90,"condition":"C1_exact","followers":[55,45,24],"events":1955,"k2_pct":0.207673,"base_k2_pct":0.167551,"k3_pct":0.019437,"base_k3_pct":0.01554,"k2_extra_pp":0.040122,"label":"90 C1_exact → 55-45-24"},{"spy":90,"condition":"NC2_W5","followers":[87,89,88],"events":1445,"k2_pct":0.044291,"base_k2_pct":0.027376,"k3_pct":0.002768,"base_k3_pct":0.002184,"k2_extra_pp":0.016915,"label":"90 NC2_W5 → 87-89-88"}]'

SPY_NETWORK_DEFS = {
    "CATENA_5": {
        "label": "CATENA 5",
        "nodes": {5, 10, 15, 20, 25, 30},
        "note": "rete 30→25→20→15→10→5",
    },
    "PONTE_55": {
        "label": "PONTE 55",
        "nodes": {4, 5, 14, 15, 28, 55, 56},
        "note": "ponte 5/15 verso 55-56",
    },
    "ZONA_40": {
        "label": "ZONA 40/50",
        "nodes": {18, 40, 45, 50},
        "note": "scala 50→45→40 con ponte 18",
    },
    "LATERALE_23": {
        "label": "LATERALE 23",
        "nodes": {22, 23, 39, 42},
        "note": "laterale 23 verso 22-39-42",
    },
    "MOD5": {"label": "MOD 5", "nodes": set(), "note": "legame per resto modulo 5"},
    "DECINA": {"label": "DECINA", "nodes": set(), "note": "concentrazione nella stessa decina"},
    "ALTRO": {"label": "ALTRO", "nodes": set(), "note": "fuori dalle reti principali"},
}
SPY_LEVELS = ("NORMALE", "FORTE", "MULTIPLA")


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
    return hashlib.md5(f"{e}-{'-'.join(map(str, nums))}".encode()).hexdigest()


def now_dt():
    return datetime.now(BOT_TZ)


def day_key():
    return now_dt().strftime("%Y-%m-%d")


def now_txt():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def pct(part, total):
    return (part / total * 100.0) if total else 0.0


def roi_text(gross, cost):
    net = gross - cost
    roi = (net / cost * 100.0) if cost else 0.0
    return net, roi


def maybe_git_commit_state(reason="state", force=False):
    """Persist state/csv on GitHub Actions by committing them back to the repo.

    Se il codice gira fuori da un repository git, o se PERSIST_GIT_STATE=0, non fa nulla.
    Il throttling evita un commit a ogni estrazione.
    """
    global _LAST_GIT_COMMIT_TS
    if not PERSIST_GIT_STATE:
        return

    now_ts = time.time()
    if not force and _LAST_GIT_COMMIT_TS and (now_ts - _LAST_GIT_COMMIT_TS) < GIT_COMMIT_MIN_SECONDS:
        return

    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if inside.returncode != 0:
            return

        subprocess.run(["git", "config", "user.name", "sniper-bot"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "config", "user.email", "sniper-bot@users.noreply.github.com"], cwd=BASE_DIR, check=False)

        # Evita conflitti quando la run nuova cancella una precedente.
        subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=BASE_DIR, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        paths = []
        if os.path.exists(STATE_FILE):
            paths.append(os.path.basename(STATE_FILE))
        if os.path.exists(CSV_FILE):
            paths.append(os.path.basename(CSV_FILE))
        if not paths:
            return

        subprocess.run(["git", "add", *paths], cwd=BASE_DIR, check=False)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=BASE_DIR)
        if diff.returncode == 0:
            _LAST_GIT_COMMIT_TS = now_ts
            return

        msg = f"SNIPER state update {now_txt()} [{reason}]"
        committed = subprocess.run(["git", "commit", "-m", msg], cwd=BASE_DIR, check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if committed.returncode == 0:
            subprocess.run(["git", "push"], cwd=BASE_DIR, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _LAST_GIT_COMMIT_TS = now_ts
    except Exception as ex:
        print(f"Persistenza git saltata: {ex}")


def fmt_nums(nums):
    return "-".join(map(str, nums or []))


def fmt_ambi(ambi):
    out = []
    for item in ambi or []:
        a, b = item["ambo"]
        out.append(f"{a}-{b}")
    return ", ".join(out)


def condition_clean_label(cond):
    return {
        "C1_exact": "C1",
        "C2_exact": "C2",
        "C3plus": "C3+",
        "NC2_W3_gap": "NC2/W3",
        "NC2_W5": "NC2/W5",
        "NC3_W5_gap": "NC3/W5",
    }.get(cond, cond)


def expected_within_h(one_draw_prob, h):
    p = max(0.0, min(1.0, float(one_draw_prob or 0.0)))
    return 1.0 - ((1.0 - p) ** int(h))


def expected_pct_from_sum(expected_sum, closed):
    """Percentuale attesa media sulle sole sessioni chiuse.

    Protezione importante: una probabilita' non puo' superare 100%.
    Nelle versioni precedenti l'atteso veniva sommato all'apertura delle sessioni
    e poi diviso per le sole chiuse: con molte sessioni ancora aperte poteva uscire
    un atteso impossibile tipo 118%, 130%, 187%.
    """
    if not closed:
        return 0.0
    value = pct(float(expected_sum or 0.0), int(closed))
    return max(0.0, min(100.0, value))


def chunks(text, max_len=3000):
    return [text[i:i + max_len] for i in range(0, len(text), max_len)] or [""]


def max_consecutive_presence(draws, n):
    best = cur = 0
    for draw in draws:
        if n in draw:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


# ============================================================
# CSV
# ============================================================

CSV_FIELDS = [
    "time", "day", "event", "estrazione", "play_id", "colpo",
    "ambata", "ambi", "cluster", "outcome", "hit_ambi", "hit_ranks",
    "v48_play", "v48_hit", "v48_stop", "v48_cost", "v48_gross", "v48_net", "v48_roi",
    "spy_id", "spy", "spy_condition", "spy_followers", "spy_network", "spy_level",
    "spy_horizon", "spy_k1", "spy_k2", "spy_k3", "spy_hit_nums",
    "spy_cost", "spy_gross", "spy_net", "spy_roi",
    "playable_id", "playable_colpo", "playable_ambata", "playable_ambi",
    "playable_outcome", "playable_hit_ambata", "playable_hit_ambi", "playable_support",
]


def ensure_csv():
    if os.path.exists(CSV_FILE):
        return
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()


# ============================================================
# MODELLO SPIE
# ============================================================

def load_spy_model():
    rows = json.loads(SPY_MODEL_EMBEDDED_JSON)
    model = {}
    for r in rows:
        if int(r.get("events", 0)) < SPY_MIN_MODEL_EVENTS:
            continue
        spy = int(r["spy"])
        condition = str(r["condition"])
        followers = tuple(int(x) for x in r["followers"])
        if len(followers) != 3 or not all(1 <= x <= 90 for x in followers):
            continue
        key = f"{spy}_{condition}"
        model[key] = {
            "key": key,
            "spy": spy,
            "condition": condition,
            "followers": followers,
            "events": int(r.get("events", 0)),
            "k2_pct": float(r.get("k2_pct", 0.0)),
            "base_k2_pct": float(r.get("base_k2_pct", 0.0)),
            "k3_pct": float(r.get("k3_pct", 0.0)),
            "base_k3_pct": float(r.get("base_k3_pct", 0.0)),
            "k2_extra_pp": float(r.get("k2_extra_pp", 0.0)),
            "label": r.get("label", f"{spy} {condition} → {fmt_nums(followers)}"),
        }
    return model


def number_decina(n):
    return (int(n) - 1) // 10


def classify_network(spy, followers):
    spy = int(spy)
    nums = {spy, *map(int, followers)}

    for key in ("CATENA_5", "PONTE_55", "ZONA_40", "LATERALE_23"):
        nodes = SPY_NETWORK_DEFS[key]["nodes"]
        if spy in nodes and len(set(followers) & nodes) >= 2:
            return key

    mod_counts = Counter(n % 5 for n in nums)
    if mod_counts and max(mod_counts.values()) >= 3:
        return "MOD5"

    dec_counts = Counter(number_decina(n) for n in nums)
    if dec_counts and max(dec_counts.values()) >= 3:
        return "DECINA"

    return "ALTRO"


# ============================================================
# MOTORE
# ============================================================

class SniperV48BaseFullSpy:
    def __init__(self):
        self.version = "v48_playable_ambata_ambi_6"
        self.day = day_key()
        self.max_e = 0
        self.last_fp = None
        self.last_draws = []
        self.processed_ids = []
        self.processed_fps = []

        # v48 core
        self.watch = {}
        self.hot_confirmed = {}
        self.active = False
        self.colpi = 0
        self.cooldown = 0
        self.active_snapshot = None
        self.last_cluster_numbers = []
        self.last_cluster_e = 0
        self.play_uid = 0
        self.total_play = 0
        self.total_hit_ambata = 0
        self.total_hit_ambo = 0
        self.total_stop = 0
        self.v48_rank_hits = {"1": 0, "2": 0, "3": 0}
        self.v48_multi_ambo_hit_draws = 0
        self.v48_hit_colpi = {str(i): 0 for i in range(1, MAX_COLPI + 1)}
        self.v48_cost_units = 0.0
        self.v48_gross_units = 0.0

        # spie
        self.spy_model = load_spy_model()
        self.spy_uid = 0
        self.spy_sessions = []
        self.spy_horizon_stats = {str(h): self.new_spy_stats() for h in SPY_HORIZONS}
        self.spy_candidate_horizon_stats = {}
        self.spy_network_horizon_stats = {}
        self.spy_level_horizon_stats = {}
        self.draws_since_spy_report = 0
        self.scheduled_reports_sent = {}

        # giocata operativa ambata/ambi
        self.playable_active = False
        self.playable_snapshot = None
        self.playable_colpi = 0
        self.playable_uid = 0
        self.playable_total = 0
        self.playable_hit_ambata = 0
        self.playable_hit_ambo = 0
        self.playable_stop = 0
        self.playable_hit_colpi = {str(i): 0 for i in range(1, PLAYABLE_MAX_COLPI + 1)}
        self.playable_cost_units = 0.0
        self.playable_gross_units = 0.0

        self.load_state()
        ensure_csv()

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------
    async def tg(self, app, msg, with_keyboard=True, inline_menu=False):
        if not msg:
            return
        for part in chunks(str(msg), 3000):
            for attempt in range(3):
                try:
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        text=part,
                        reply_markup=(INLINE_MENU if inline_menu else (MENU_KEYBOARD if with_keyboard else None)),
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=30,
                        pool_timeout=30,
                    )
                    break
                except Exception as ex:
                    print(f"Telegram send error attempt {attempt + 1}: {ex}")
                    await asyncio.sleep(4)

    # --------------------------------------------------------
    # State / CSV
    # --------------------------------------------------------
    @staticmethod
    def new_spy_stats():
        return {
            "sessions": 0,
            "closed": 0,
            "k1_hits": 0,
            "k2_hits": 0,
            "k3_hits": 0,
            "k3_cost_units": 0.0,
            "k3_gross_units": 0.0,
            "expected_k2_sum": 0.0,
            "expected_k3_sum": 0.0,
        }

    def get_nested_stat(self, container, key, h):
        key = str(key)
        h = str(h)
        if key not in container:
            container[key] = {}
        if h not in container[key]:
            container[key][h] = self.new_spy_stats()
        return container[key][h]

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
            "play_uid": self.play_uid,
            "total_play": self.total_play,
            "total_hit_ambata": self.total_hit_ambata,
            "total_hit_ambo": self.total_hit_ambo,
            "total_stop": self.total_stop,
            "v48_rank_hits": self.v48_rank_hits,
            "v48_multi_ambo_hit_draws": self.v48_multi_ambo_hit_draws,
            "v48_hit_colpi": self.v48_hit_colpi,
            "v48_cost_units": self.v48_cost_units,
            "v48_gross_units": self.v48_gross_units,
            "spy_uid": self.spy_uid,
            "spy_sessions": self.spy_sessions,
            "spy_horizon_stats": self.spy_horizon_stats,
            "spy_candidate_horizon_stats": self.spy_candidate_horizon_stats,
            "spy_network_horizon_stats": self.spy_network_horizon_stats,
            "spy_level_horizon_stats": self.spy_level_horizon_stats,
            "draws_since_spy_report": self.draws_since_spy_report,
            "playable_active": self.playable_active,
            "playable_snapshot": self.playable_snapshot,
            "playable_colpi": self.playable_colpi,
            "playable_uid": self.playable_uid,
            "playable_total": self.playable_total,
            "playable_hit_ambata": self.playable_hit_ambata,
            "playable_hit_ambo": self.playable_hit_ambo,
            "playable_stop": self.playable_stop,
            "playable_hit_colpi": self.playable_hit_colpi,
            "playable_cost_units": self.playable_cost_units,
            "playable_gross_units": self.playable_gross_units,
            "scheduled_reports_sent": self.scheduled_reports_sent,
        }
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
        maybe_git_commit_state("state", force=False)

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
            self.play_uid = int(data.get("play_uid", 0))
            self.total_play = int(data.get("total_play", 0))
            self.total_hit_ambata = int(data.get("total_hit_ambata", 0))
            self.total_hit_ambo = int(data.get("total_hit_ambo", 0))
            self.total_stop = int(data.get("total_stop", 0))
            self.v48_rank_hits = {str(i): int(data.get("v48_rank_hits", {}).get(str(i), 0)) for i in (1, 2, 3)}
            self.v48_multi_ambo_hit_draws = int(data.get("v48_multi_ambo_hit_draws", 0))
            self.v48_hit_colpi = {str(i): int(data.get("v48_hit_colpi", {}).get(str(i), 0)) for i in range(1, MAX_COLPI + 1)}
            self.v48_cost_units = float(data.get("v48_cost_units", 0.0))
            self.v48_gross_units = float(data.get("v48_gross_units", 0.0))
            self.spy_uid = int(data.get("spy_uid", 0))
            self.spy_sessions = data.get("spy_sessions", [])
            self.spy_horizon_stats = self._load_stat_map(data.get("spy_horizon_stats", {}), SPY_HORIZONS)
            self.spy_candidate_horizon_stats = data.get("spy_candidate_horizon_stats", {})
            self.spy_network_horizon_stats = data.get("spy_network_horizon_stats", {})
            self.spy_level_horizon_stats = data.get("spy_level_horizon_stats", {})
            self.draws_since_spy_report = int(data.get("draws_since_spy_report", 0))
            self.playable_active = bool(data.get("playable_active", False))
            self.playable_snapshot = data.get("playable_snapshot")
            self.playable_colpi = int(data.get("playable_colpi", 0))
            self.playable_uid = int(data.get("playable_uid", 0))
            self.playable_total = int(data.get("playable_total", 0))
            self.playable_hit_ambata = int(data.get("playable_hit_ambata", 0))
            self.playable_hit_ambo = int(data.get("playable_hit_ambo", 0))
            self.playable_stop = int(data.get("playable_stop", 0))
            self.playable_hit_colpi = {str(i): int(data.get("playable_hit_colpi", {}).get(str(i), 0)) for i in range(1, PLAYABLE_MAX_COLPI + 1)}
            self.playable_cost_units = float(data.get("playable_cost_units", 0.0))
            self.playable_gross_units = float(data.get("playable_gross_units", 0.0))
            self.scheduled_reports_sent = data.get("scheduled_reports_sent", {}) if isinstance(data.get("scheduled_reports_sent", {}), dict) else {}
        except Exception as ex:
            print(f"⚠️ Stato non caricato: {ex}")

    def _load_stat_map(self, src, horizons):
        out = {str(h): self.new_spy_stats() for h in horizons}
        for h in horizons:
            hkey = str(h)
            old = src.get(hkey, {}) if isinstance(src, dict) else {}
            for k, default in out[hkey].items():
                value = old.get(k, default)
                out[hkey][k] = float(value) if isinstance(default, float) else int(value)
        return out

    def reset_for_new_day(self, new_day):
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
        self.spy_sessions = []
        self.playable_active = False
        self.playable_snapshot = None
        self.playable_colpi = 0
        self.draws_since_spy_report = 0
        self.save_state()

    def append_csv_event(self, event, **kwargs):
        ensure_csv()
        v48_net, v48_roi = roi_text(self.v48_gross_units, self.v48_cost_units)
        row = {
            "time": now_txt(),
            "day": self.day,
            "event": event,
            "estrazione": kwargs.get("e", ""),
            "play_id": kwargs.get("play_id", ""),
            "colpo": kwargs.get("colpo", ""),
            "ambata": kwargs.get("ambata", ""),
            "ambi": kwargs.get("ambi", ""),
            "cluster": kwargs.get("cluster", ""),
            "outcome": kwargs.get("outcome", ""),
            "hit_ambi": kwargs.get("hit_ambi", ""),
            "hit_ranks": kwargs.get("hit_ranks", ""),
            "v48_play": self.total_play,
            "v48_hit": self.total_hit_ambo,
            "v48_stop": self.total_stop,
            "v48_cost": f"{self.v48_cost_units:.2f}",
            "v48_gross": f"{self.v48_gross_units:.2f}",
            "v48_net": f"{v48_net:.2f}",
            "v48_roi": f"{v48_roi:.4f}",
            "spy_id": kwargs.get("spy_id", ""),
            "spy": kwargs.get("spy", ""),
            "spy_condition": kwargs.get("spy_condition", ""),
            "spy_followers": kwargs.get("spy_followers", ""),
            "spy_network": kwargs.get("spy_network", ""),
            "spy_level": kwargs.get("spy_level", ""),
            "spy_horizon": kwargs.get("spy_horizon", ""),
            "spy_k1": kwargs.get("spy_k1", ""),
            "spy_k2": kwargs.get("spy_k2", ""),
            "spy_k3": kwargs.get("spy_k3", ""),
            "spy_hit_nums": kwargs.get("spy_hit_nums", ""),
            "spy_cost": kwargs.get("spy_cost", ""),
            "spy_gross": kwargs.get("spy_gross", ""),
            "spy_net": kwargs.get("spy_net", ""),
            "spy_roi": kwargs.get("spy_roi", ""),
            "playable_id": kwargs.get("playable_id", ""),
            "playable_colpo": kwargs.get("playable_colpo", ""),
            "playable_ambata": kwargs.get("playable_ambata", ""),
            "playable_ambi": kwargs.get("playable_ambi", ""),
            "playable_outcome": kwargs.get("playable_outcome", ""),
            "playable_hit_ambata": kwargs.get("playable_hit_ambata", ""),
            "playable_hit_ambi": kwargs.get("playable_hit_ambi", ""),
            "playable_support": kwargs.get("playable_support", ""),
        }
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow(row)

    # --------------------------------------------------------
    # Dedup/history
    # --------------------------------------------------------
    def already_processed(self, e, nums):
        fp = fingerprint(e, nums)
        return e in self.processed_ids or fp in self.processed_fps

    def remember_processed(self, e, nums):
        fp = fingerprint(e, nums)
        self.max_e = max(self.max_e, int(e))
        self.last_fp = fp
        self.processed_ids.append(int(e))
        self.processed_fps.append(fp)
        self.processed_ids = self.processed_ids[-PROCESSED_MAX:]
        self.processed_fps = self.processed_fps[-PROCESSED_MAX:]

    def preload_today_as_processed(self, es):
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

    # --------------------------------------------------------
    # v48 core features
    # --------------------------------------------------------
    def lag(self, n):
        lag = 0
        for d in reversed(self.last_draws[:-1]):
            lag += 1
            if n in d:
                return lag
        return lag

    def heat(self, n):
        weights = [5, 4, 3, 2, 1]
        return sum(w for i, w in enumerate(weights) if i < len(self.last_draws) and n in self.last_draws[-(i + 1)])

    def dominance(self, n, window=6):
        return sum(1 for d in self.last_draws[-window:] if n in d)

    def pressure(self, n):
        weights = [5, 4, 3, 2, 1]
        return sum(w for i, w in enumerate(weights) if i < len(self.last_draws) and n in self.last_draws[-(i + 1)])

    def top_ritardatari(self):
        data = [{"number": n, "lag": self.lag(n)} for n in range(1, 91)]
        data.sort(key=lambda x: (-x["lag"], x["number"]))
        return data[:TOP_RITARDATARI]

    def selected_ritardatari(self):
        top10 = self.top_ritardatari()
        selected = []
        for pos in PLAY_POSITIONS:
            idx = pos - 1
            if idx < len(top10):
                selected.append({"position": pos, "number": top10[idx]["number"], "lag": top10[idx]["lag"]})
        return top10, selected

    def clean_old_watch(self, current_e):
        for key in [k for k, d in self.watch.items() if current_e - int(d["first_e"]) > WATCH_WINDOW]:
            self.watch.pop(key, None)

    def clean_old_hot(self, current_e):
        for key in [k for k, d in self.hot_confirmed.items() if current_e - int(d["confirmed_e"]) > HOT_TTL]:
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
                    self.hot_confirmed[key] = {**self.watch[key], "confirmed_e": e}
                    self.watch.pop(key, None)
        self.clean_old_watch(e)
        self.clean_old_hot(e)

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
        hot_score = self.confirmed_score(hot, e) if hot else 0
        return hot_score + self.heat(n) * 2 + self.dominance(n, 6) * 3 + self.pressure(n) - self.lag(n)

    def duplicate_cluster(self, cluster_numbers, e):
        if not self.last_cluster_numbers:
            return False
        if e - int(self.last_cluster_e) >= CLUSTER_REUSE_AFTER:
            return False
        return len(set(cluster_numbers) & set(self.last_cluster_numbers)) >= 2

    def build_play(self, e):
        hot_items = [x for x in self.hot_confirmed.values() if 0 <= e - int(x["confirmed_e"]) <= HOT_TTL]
        if len(hot_items) < MIN_HOT_ACTIVE:
            return None

        pair_candidates = []
        for a, b in combinations(hot_items, 2):
            pair = tuple(sorted((int(a["number"]), int(b["number"]))))
            score = self.confirmed_score(a, e) + self.confirmed_score(b, e)
            pair_candidates.append({"ambo": pair, "score": round(score, 2)})

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
        return {"ambata": ambata, "ambi": ambi, "cluster_numbers": cluster_numbers}

    def check_v48_hit(self, nums):
        s = set(nums)
        snap = self.active_snapshot or {}
        ambata_hit = snap.get("ambata") in s
        ambi_hit = []
        for item in snap.get("ambi", []):
            a, b = item["ambo"]
            if a in s and b in s:
                ambi_hit.append(item)
        return {"ambata_hit": ambata_hit, "ambi_hit": ambi_hit}

    # --------------------------------------------------------
    # Spy conditions
    # --------------------------------------------------------
    def condition_active(self, n, condition):
        n = int(n)
        hist = self.last_draws
        if not hist:
            return False

        def present(offset):
            # offset 1 = ultimo colpo
            return len(hist) >= offset and n in hist[-offset]

        if condition == "C1_exact":
            return present(1) and not present(2)
        if condition == "C2_exact":
            return present(1) and present(2) and not present(3)
        if condition == "C3plus":
            return present(1) and present(2) and present(3)
        if condition == "NC2_W3_gap":
            return present(1) and (not present(2)) and present(3)
        if condition == "NC2_W5":
            if len(hist) < 5:
                return False
            w = hist[-5:]
            count = sum(1 for d in w if n in d)
            return count == 2 and max_consecutive_presence(w, n) < 2
        if condition == "NC3_W5_gap":
            if len(hist) < 5:
                return False
            w = hist[-5:]
            count = sum(1 for d in w if n in d)
            return count == 3 and max_consecutive_presence(w, n) < 3
        return False

    def detect_spy_rules(self):
        active = []
        for rule in self.spy_model.values():
            if self.condition_active(rule["spy"], rule["condition"]):
                r = dict(rule)
                r["network"] = classify_network(r["spy"], r["followers"])
                active.append(r)

        network_counts = Counter(r["network"] for r in active)
        for r in active:
            related = network_counts[r["network"]]
            if related >= 2:
                level = "MULTIPLA"
            elif r["network"] in {"CATENA_5", "PONTE_55", "ZONA_40"} or r["condition"] == "C3plus":
                level = "FORTE"
            else:
                level = "NORMALE"
            r["level"] = level
            r["active_related"] = related
            r["active_total"] = len(active)

        # Ordine: segnali con rete multipla/extra storico piu' forte in alto.
        active.sort(key=lambda r: (-(r["level"] == "MULTIPLA"), -r.get("k2_extra_pp", 0.0), -r.get("events", 0), r["spy"]))
        return active

    def add_session_to_stat_buckets(self, rule):
        # Conta le sessioni aperte.
        # L'atteso K2/K3 viene aggiunto SOLO quando l'orizzonte chiude,
        # cosi' il confronto atteso/reale e' calcolato sulle stesse sessioni chiuse.
        for h in SPY_HORIZONS:
            hkey = str(h)
            for st in (
                self.spy_horizon_stats[hkey],
                self.get_nested_stat(self.spy_candidate_horizon_stats, rule["key"], hkey),
                self.get_nested_stat(self.spy_network_horizon_stats, rule["network"], hkey),
                self.get_nested_stat(self.spy_level_horizon_stats, rule["level"], hkey),
            ):
                st["sessions"] += 1

    def update_stat_on_close(self, st, horizon, max_k, k3_colpo, exp_k2=None, exp_k3=None):
        horizon = int(horizon)
        st["closed"] += 1
        if max_k >= 1:
            st["k1_hits"] += 1
        if max_k >= 2:
            st["k2_hits"] += 1
        if max_k >= 3:
            st["k3_hits"] += 1
        cost = float(k3_colpo if k3_colpo else horizon)
        gross = TERNO_PAYOUT if k3_colpo else 0.0
        st["k3_cost_units"] += cost
        st["k3_gross_units"] += gross
        st["expected_k2_sum"] += max(0.0, min(1.0, float(exp_k2 or 0.0)))
        st["expected_k3_sum"] += max(0.0, min(1.0, float(exp_k3 or 0.0)))
        return cost, gross

    async def maybe_open_spy_sessions(self, app, e):
        rules = self.detect_spy_rules()
        if not rules:
            return

        opened = []
        for r in rules:
            self.spy_uid += 1
            session = {
                "id": self.spy_uid,
                "opened_e": e,
                "spy": int(r["spy"]),
                "condition": r["condition"],
                "followers": list(r["followers"]),
                "key": r["key"],
                "label": r["label"],
                "network": r["network"],
                "level": r["level"],
                "base_k2_pct": float(r.get("base_k2_pct", 0.0)),
                "base_k3_pct": float(r.get("base_k3_pct", 0.0)),
                "active_related": int(r["active_related"]),
                "active_total": int(r["active_total"]),
                "colpi": 0,
                "k_by_colpo": [],
                "hit_nums_by_colpo": [],
                "closed_horizons": [],
                "notified_k2": False,
                "notified_k3": False,
            }
            self.spy_sessions.append(session)
            self.add_session_to_stat_buckets(r)
            opened.append(session)
            self.append_csv_event(
                "SPY_OPEN",
                e=e,
                spy_id=session["id"],
                spy=session["spy"],
                spy_condition=session["condition"],
                spy_followers=fmt_nums(session["followers"]),
                spy_network=session["network"],
                spy_level=session["level"],
            )

        if SPY_NOTIFY_OPEN:
            lines = [
                "🕵️ NUMERI SPIA LAB — SEGNALI APERTI",
                f"• estrazione origine = {e}",
                f"• segnali attivi = {len(opened)}",
                "• osservazione parallela = H1 / H2 / H3",
            ]
            for s in opened[:SPY_OPEN_NOTIFY_MAX_LINES]:
                label_net = SPY_NETWORK_DEFS.get(s["network"], {}).get("label", s["network"])
                lines.append(
                    f"• id {s['id']} | {s['spy']} {condition_clean_label(s['condition'])} → {fmt_nums(s['followers'])}\n"
                    f"  🧬 {label_net} | {s['level']} | rete/tot = {s['active_related']}/{s['active_total']}"
                )
            if len(opened) > SPY_OPEN_NOTIFY_MAX_LINES:
                lines.append(f"• altri segnali non mostrati = {len(opened) - SPY_OPEN_NOTIFY_MAX_LINES}")
            lines.append("\nTocca /spie per il quadro completo.")
            await self.tg(app, "\n".join(lines))

    async def process_spy_sessions(self, app, e, nums):
        if not self.spy_sessions:
            return

        still_open = []
        nums_set = set(nums)
        for s in self.spy_sessions:
            s["colpi"] = int(s.get("colpi", 0)) + 1
            followers = [int(x) for x in s.get("followers", [])]
            hit_nums = sorted([n for n in followers if n in nums_set])
            k = len(hit_nums)
            s.setdefault("k_by_colpo", []).append(k)
            s.setdefault("hit_nums_by_colpo", []).append(hit_nums)

            if k >= 2 and not s.get("notified_k2") and SPY_NOTIFY_HIT_K2:
                s["notified_k2"] = True
                await self.tg(
                    app,
                    "💥 NUMERI SPIA LAB — ALMENO 2/3\n"
                    f"• signal_id = {s['id']}\n"
                    f"• spia = {s['spy']} | condizione = {s['condition']}\n"
                    f"• rete = {s['network']} | livello = {s['level']}\n"
                    f"• TOP3 accompagnatori = {fmt_nums(followers)}\n"
                    f"• usciti = {fmt_nums(hit_nums)}\n"
                    f"• colpo = {s['colpi']}"
                )

            if k >= 3 and not s.get("notified_k3") and SPY_NOTIFY_HIT_K3:
                s["notified_k3"] = True
                await self.tg(
                    app,
                    "💥 NUMERI SPIA LAB — TRIS 3/3\n"
                    f"• signal_id = {s['id']}\n"
                    f"• spia = {s['spy']} | condizione = {s['condition']}\n"
                    f"• rete = {s['network']} | livello = {s['level']}\n"
                    f"• TERNO = {fmt_nums(followers)}\n"
                    f"• colpo = {s['colpi']}"
                )

            closed_h = set(map(str, s.get("closed_horizons", [])))
            for h in SPY_HORIZONS:
                hkey = str(h)
                if hkey in closed_h or s["colpi"] < h:
                    continue

                k_values = s.get("k_by_colpo", [])[:h]
                max_k = max(k_values) if k_values else 0
                k3_colpo = None
                for idx, kval in enumerate(k_values, start=1):
                    if kval >= 3:
                        k3_colpo = idx
                        break
                best_idx = max(range(len(k_values)), key=lambda i: k_values[i]) if k_values else None
                best_nums = s.get("hit_nums_by_colpo", [])[best_idx] if best_idx is not None else []

                # atteso storico relativo SOLO a questa sessione chiusa e a questo orizzonte
                rule_info = self.spy_model.get(s.get("key"), {})
                base_k2 = float(s.get("base_k2_pct", rule_info.get("base_k2_pct", 0.0)) or 0.0)
                base_k3 = float(s.get("base_k3_pct", rule_info.get("base_k3_pct", 0.0)) or 0.0)
                exp_k2 = expected_within_h(base_k2, h)
                exp_k3 = expected_within_h(base_k3, h)

                # aggiorna globale, candidato, rete, livello
                for st in (
                    self.spy_horizon_stats[hkey],
                    self.get_nested_stat(self.spy_candidate_horizon_stats, s["key"], hkey),
                    self.get_nested_stat(self.spy_network_horizon_stats, s["network"], hkey),
                    self.get_nested_stat(self.spy_level_horizon_stats, s["level"], hkey),
                ):
                    cost, gross = self.update_stat_on_close(st, h, max_k, k3_colpo, exp_k2, exp_k3)

                cost = float(k3_colpo if k3_colpo else h)
                gross = TERNO_PAYOUT if k3_colpo else 0.0
                net, roi = roi_text(gross, cost)
                s.setdefault("closed_horizons", []).append(hkey)
                self.append_csv_event(
                    f"SPY_CLOSE_H{h}",
                    e=e,
                    colpo=s["colpi"],
                    spy_id=s["id"],
                    spy=s["spy"],
                    spy_condition=s["condition"],
                    spy_followers=fmt_nums(followers),
                    spy_network=s["network"],
                    spy_level=s["level"],
                    spy_horizon=h,
                    spy_k1=int(max_k >= 1),
                    spy_k2=int(max_k >= 2),
                    spy_k3=int(max_k >= 3),
                    spy_hit_nums=fmt_nums(best_nums),
                    spy_cost=f"{cost:.2f}",
                    spy_gross=f"{gross:.2f}",
                    spy_net=f"{net:.2f}",
                    spy_roi=f"{roi:.4f}",
                )

            if len(set(map(str, s.get("closed_horizons", [])))) < len(SPY_HORIZONS):
                still_open.append(s)

        self.spy_sessions = still_open

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------
    def v48_stats_text(self):
        net, roi = roi_text(self.v48_gross_units, self.v48_cost_units)
        hit_rate = pct(self.total_hit_ambo, self.total_play)
        stop_rate = pct(self.total_stop, self.total_play)
        active_txt = "SI" if self.active else "NO"
        open_txt = ""
        if self.active_snapshot:
            open_txt = (
                f"\n\n🎯 PLAY ATTIVO\n"
                f"• play_id = {self.active_snapshot.get('play_id')}\n"
                f"• colpo corrente = {self.colpi}/{MAX_COLPI}\n"
                f"• ambata = {self.active_snapshot.get('ambata')}\n"
                f"• ambi = {fmt_ambi(self.active_snapshot.get('ambi'))}"
            )
        by_colpo = ", ".join(f"C{i}:{self.v48_hit_colpi[str(i)]}" for i in range(1, MAX_COLPI + 1))
        return (
            "🎯 QUADRO v48 BASE\n"
            "• solo 3 ambi classici, core invariato\n"
            f"• play = {self.total_play}\n"
            f"• HIT AMBO = {self.total_hit_ambo} ({hit_rate:.2f}%)\n"
            f"• STOP = {self.total_stop} ({stop_rate:.2f}%)\n"
            f"• hit ambata eventi = {self.total_hit_ambata}\n"
            f"• attivo ora = {active_txt}\n"
            f"• hit per colpo = {by_colpo}\n\n"
            "📌 RANK AMBO VINCENTE\n"
            f"• rank 1 = {self.v48_rank_hits['1']}\n"
            f"• rank 2 = {self.v48_rank_hits['2']}\n"
            f"• rank 3 = {self.v48_rank_hits['3']}\n"
            f"• colpi con 2+ ambi insieme = {self.v48_multi_ambo_hit_draws}\n\n"
            f"💰 Economia teorica ambo {AMBO_PAYOUT:.0f}x\n"
            f"• costo = {self.v48_cost_units:.2f}u\n"
            f"• lordo = {self.v48_gross_units:.2f}u\n"
            f"• netto = {net:+.2f}u\n"
            f"• ROI = {roi:+.2f}%"
            f"{open_txt}"
        )

    def spy_summary_text(self):
        lines = [
            "🕵️ QUADRO NUMERI SPIA — LIVE",
            f"• modello storico caricato = {len(self.spy_model)} regole",
            f"• sessioni aperte ora = {len(self.spy_sessions)}",
            "• orizzonti = H1 / H2 / H3",
            "",
            "📍 RISULTATO GENERALE",
        ]
        h3_k2 = 0.0
        h3_extra = 0.0
        h3_closed = 0
        h3_k3 = 0

        for h in SPY_HORIZONS:
            hkey = str(h)
            st = self.spy_horizon_stats[hkey]
            closed = int(st["closed"])
            k1 = int(st["k1_hits"])
            k2 = int(st["k2_hits"])
            k3 = int(st["k3_hits"])
            cost = float(st["k3_cost_units"])
            gross = float(st["k3_gross_units"])
            net, roi = roi_text(gross, cost)
            exp_k2_pct = expected_pct_from_sum(st.get("expected_k2_sum", 0.0), closed)
            exp_k3_pct = expected_pct_from_sum(st.get("expected_k3_sum", 0.0), closed)
            extra_k2 = pct(k2, closed) - exp_k2_pct
            if h == 3:
                h3_k2 = pct(k2, closed)
                h3_extra = extra_k2
                h3_closed = closed
                h3_k3 = k3
            colpo_label = "colpi" if h > 1 else "colpo"
            lines.extend([
                "",
                f"H{h} — entro {h} {colpo_label}",
                f"• chiuse = {closed} / sessioni = {st['sessions']}",
                f"• K1 = {k1}/{closed} = {pct(k1, closed):.2f}%",
                f"• K2 = {k2}/{closed} = {pct(k2, closed):.2f}% | atteso≈{exp_k2_pct:.2f}% | extra={extra_k2:+.2f} pp",
                f"• K3 = {k3}/{closed} = {pct(k3, closed):.2f}% | atteso≈{exp_k3_pct:.2f}%",
                f"• terno 45x: costo={cost:.2f}u | lordo={gross:.2f}u | netto={net:+.2f}u | ROI={roi:+.2f}%",
            ])

        st3 = self.spy_horizon_stats.get("3", self.new_spy_stats())
        _, h3_roi = roi_text(float(st3.get("k3_gross_units", 0.0)), float(st3.get("k3_cost_units", 0.0)))
        if h3_closed < 50:
            verdict = "🟡 campione piccolo: osservazione"
        elif h3_extra >= 5 and h3_roi >= 0:
            verdict = "🟢 K2 positivo e K3 profittevole nel periodo"
        elif h3_extra >= 5:
            verdict = "🟡 K2 positivo, terno K3 non profittevole"
        elif h3_extra > 0:
            verdict = "🟡 leggermente sopra atteso"
        else:
            verdict = "🔴 non confermato"
        lines.extend([
            "",
            "🚦 VERDETTO SPIE",
            f"• H3 K2 = {h3_k2:.2f}% | extra≈{h3_extra:+.2f} pp | chiuse={h3_closed}",
            f"• H3 K3 = {h3_k3}",
            f"• stato = {verdict}",
        ])
        return "\n".join(lines)

    def _h3_extra_for_network(self, network):
        st = self.spy_network_horizon_stats.get(network, {}).get("3", self.new_spy_stats())
        closed = int(st.get("closed", 0))
        k2 = int(st.get("k2_hits", 0))
        exp = expected_pct_from_sum(st.get("expected_k2_sum", 0.0), closed)
        return pct(k2, closed) - exp, closed, k2, exp

    def _h3_extra_for_level(self, level):
        st = self.spy_level_horizon_stats.get(level, {}).get("3", self.new_spy_stats())
        closed = int(st.get("closed", 0))
        k2 = int(st.get("k2_hits", 0))
        exp = expected_pct_from_sum(st.get("expected_k2_sum", 0.0), closed)
        return pct(k2, closed) - exp, closed, k2, exp

    def playable_signal_snapshot(self):
        """Rende giocabili i segnali DECINA/MULTIPLA aperti.

        La logica e' volutamente stretta:
        - considera solo rete DECINA + livello MULTIPLA;
        - ricava top numeri e top ambi dai target aperti;
        - scarta i segnali fuori dal cuore live;
        - il terno resta solo osservazione.
        """
        raw_signals = [
            s for s in self.spy_sessions
            if s.get("network") == PLAYABLE_NETWORK and s.get("level") == PLAYABLE_LEVEL
        ]

        num_counter = Counter()
        pair_counter = Counter()
        trio_counter = Counter()
        for s in raw_signals:
            followers = tuple(sorted(map(int, s.get("followers", []))))
            if len(followers) != 3:
                continue
            trio_counter[followers] += 1
            num_counter.update(followers)
            for pair in combinations(followers, 2):
                pair_counter[tuple(sorted(pair))] += 1

        top_nums = num_counter.most_common(PLAYABLE_MAX_NUMBERS)
        top_num_set = {n for n, _ in top_nums[:PLAYABLE_TOP_NUMBERS_FOR_CONFIRM]}
        top_pairs = pair_counter.most_common(PLAYABLE_MAX_PAIRS)

        supported_pairs = []
        for pair, support in top_pairs:
            a, b = pair
            if support < PLAYABLE_MIN_PAIR_SUPPORT:
                continue
            if a not in top_num_set or b not in top_num_set:
                continue
            supported_pairs.append((pair, support))

        supported_pair_set = {tuple(pair) for pair, _ in supported_pairs}
        focused_signals = []
        for s in raw_signals:
            followers = tuple(sorted(map(int, s.get("followers", []))))
            follower_pairs = {tuple(sorted(p)) for p in combinations(followers, 2)}
            in_core = len(set(followers) & top_num_set)
            if follower_pairs & supported_pair_set or in_core >= 2:
                focused_signals.append(s)

        focused_signals.sort(key=lambda s: (int(s.get("colpi", 0)), -int(s.get("active_related", 0)), s.get("label", "")))
        dec_extra, dec_closed, dec_k2, dec_exp = self._h3_extra_for_network(PLAYABLE_NETWORK)
        mult_extra, mult_closed, mult_k2, mult_exp = self._h3_extra_for_level(PLAYABLE_LEVEL)

        return {
            "raw_signals": raw_signals,
            "signals": focused_signals,
            "num_counter": num_counter,
            "pair_counter": pair_counter,
            "trio_counter": trio_counter,
            "top_nums": top_nums,
            "top_num_set": top_num_set,
            "top_pairs": top_pairs,
            "supported_pairs": supported_pairs,
            "dec_extra": dec_extra,
            "dec_closed": dec_closed,
            "dec_k2": dec_k2,
            "dec_exp": dec_exp,
            "mult_extra": mult_extra,
            "mult_closed": mult_closed,
            "mult_k2": mult_k2,
            "mult_exp": mult_exp,
        }

    def build_playable_candidate(self, e):
        if not PLAYABLE_AUTO_ENABLED or self.playable_active:
            return None, "play gia' attivo o auto off"
        if not self.active_snapshot:
            return None, "manca conferma v48 attiva"

        snap = self.playable_signal_snapshot()
        signals = snap["signals"]
        supported_pairs = snap["supported_pairs"]
        if len(signals) < PLAYABLE_MIN_SIGNALS:
            return None, f"pochi segnali focus ({len(signals)}/{PLAYABLE_MIN_SIGNALS})"
        if not supported_pairs:
            return None, f"nessun ambo con supporto >= {PLAYABLE_MIN_PAIR_SUPPORT}"
        if snap["dec_extra"] < PLAYABLE_MIN_DECINA_EXTRA:
            return None, f"DECINA extra basso ({snap['dec_extra']:+.2f} pp)"
        if snap["mult_extra"] < PLAYABLE_MIN_MULTIPLA_EXTRA:
            return None, f"MULTIPLA extra basso ({snap['mult_extra']:+.2f} pp)"

        v48 = self.active_snapshot or {}
        v48_cluster = set(map(int, v48.get("cluster_numbers", [])))
        v48_ambata = v48.get("ambata")
        try:
            v48_ambata = int(v48_ambata)
        except Exception:
            v48_ambata = None

        eligible = []
        for pair, support in supported_pairs:
            pair_set = set(pair)
            overlap = len(pair_set & v48_cluster)
            if PLAYABLE_REQUIRE_V48_CONFIRM and overlap <= 0:
                continue
            eligible.append((pair, support, overlap))

        if not eligible:
            return None, "nessun ambo top incrocia il cluster v48"

        eligible.sort(key=lambda x: (-x[1], -x[2], x[0]))
        selected = eligible[:PLAYABLE_MAX_AMBI]
        selected_pairs = [pair for pair, _, _ in selected]
        selected_union = set()
        for pair in selected_pairs:
            selected_union.update(pair)

        num_counter = snap["num_counter"]
        top_num_set = snap["top_num_set"]
        ambata_candidates = []
        if v48_ambata in selected_union or v48_ambata in top_num_set:
            ambata_candidates.append(v48_ambata)
        ambata_candidates.extend(sorted((v48_cluster & top_num_set) | (selected_union & top_num_set)))
        if not ambata_candidates:
            ambata_candidates.extend(sorted(selected_union))
        # dedup preservando ordine
        seen = set()
        ambata_candidates = [x for x in ambata_candidates if x and not (x in seen or seen.add(x))]
        ambata = max(ambata_candidates, key=lambda n: (num_counter.get(n, 0), n)) if ambata_candidates else None
        if not ambata:
            return None, "ambata non determinabile"

        ambi = [{"ambo": tuple(pair), "support": support, "overlap_v48": overlap} for pair, support, overlap in selected]
        top_nums = snap["top_nums"][:PLAYABLE_MAX_NUMBERS]
        top_pairs = snap["supported_pairs"][:PLAYABLE_MAX_PAIRS]
        support_text = "; ".join(f"{a}-{b}:{support}" for (a, b), support, _ in selected)

        return {
            "origin_e": e,
            "opened_at": now_txt(),
            "ambata": int(ambata),
            "ambi": ambi,
            "top_nums": top_nums,
            "top_pairs": top_pairs,
            "signals_count": len(signals),
            "raw_signals_count": len(snap["raw_signals"]),
            "dec_extra": snap["dec_extra"],
            "mult_extra": snap["mult_extra"],
            "v48_play_id": v48.get("play_id"),
            "v48_ambata": v48.get("ambata"),
            "v48_cluster": list(v48.get("cluster_numbers", [])),
            "ambata_hit": False,
            "ambata_hit_colpo": None,
            "support_text": support_text,
        }, "ok"

    def _playable_ambi_text(self, snapshot=None):
        snapshot = snapshot or self.playable_snapshot or {}
        return ", ".join(
            f"{a}-{b}({item.get('support', 0)})"
            for item in snapshot.get("ambi", [])
            for a, b in [tuple(item.get("ambo", []))]
        ) or "n/d"

    def _close_playable(self):
        self.playable_active = False
        self.playable_snapshot = None
        self.playable_colpi = 0

    async def maybe_open_playable_play(self, app, e):
        candidate, reason = self.build_playable_candidate(e)
        if not candidate:
            return False
        self.playable_uid += 1
        candidate["playable_id"] = self.playable_uid
        self.playable_snapshot = candidate
        self.playable_active = True
        self.playable_colpi = 0
        self.playable_total += 1
        self.append_csv_event(
            "PLAYABLE_OPEN",
            e=e,
            playable_id=self.playable_uid,
            playable_colpo=0,
            playable_ambata=candidate["ambata"],
            playable_ambi=self._playable_ambi_text(candidate),
            playable_outcome="OPEN",
            playable_support=candidate.get("support_text", ""),
        )
        if PLAYABLE_NOTIFY_OPEN:
            top_nums_txt = ", ".join(f"{n}({c})" for n, c in candidate.get("top_nums", [])[:5]) or "n/d"
            await self.tg(
                app,
                "🎯 PLAY GIOCABILE — AMBATA/AMBI\n"
                "• logica = v48 + DECINA/MULTIPLA + top ambi live\n"
                f"• play_id = {candidate['playable_id']}\n"
                f"• ambata = {candidate['ambata']}\n"
                f"• ambi = {self._playable_ambi_text(candidate)}\n"
                f"• durata = max {PLAYABLE_MAX_COLPI} colpi\n"
                f"• v48 conferma = play {candidate.get('v48_play_id')} | cluster {fmt_nums(candidate.get('v48_cluster'))}\n"
                f"• top numeri live = {top_nums_txt}\n"
                f"• supporto ambi = {candidate.get('support_text', '')}\n"
                f"• DECINA extra = {candidate.get('dec_extra', 0):+.2f} pp | MULTIPLA extra = {candidate.get('mult_extra', 0):+.2f} pp\n"
                "• nota = terno escluso; segnalo ambata presa, ambo preso oppure stop"
            )
        return True

    async def process_playable_play(self, app, e, nums):
        if not self.playable_active or not self.playable_snapshot:
            return False
        self.playable_colpi += 1
        snap = self.playable_snapshot
        nums_set = set(nums)
        hit_ambata_now = int(snap.get("ambata")) in nums_set
        hit_pairs = []
        for item in snap.get("ambi", []):
            a, b = tuple(map(int, item.get("ambo", [])))
            if a in nums_set and b in nums_set:
                hit_pairs.append((a, b))

        if hit_ambata_now and not snap.get("ambata_hit"):
            snap["ambata_hit"] = True
            snap["ambata_hit_colpo"] = self.playable_colpi
            self.playable_hit_ambata += 1
            self.append_csv_event(
                "PLAYABLE_HIT_AMBATA",
                e=e,
                playable_id=snap.get("playable_id"),
                playable_colpo=self.playable_colpi,
                playable_ambata=snap.get("ambata"),
                playable_ambi=self._playable_ambi_text(snap),
                playable_outcome="HIT_AMBATA",
                playable_hit_ambata=1,
                playable_support=snap.get("support_text", ""),
            )
            if PLAYABLE_NOTIFY_HIT:
                await self.tg(app, f"🎯 AMBATA PRESA PLAY GIOCABILE | colpo {self.playable_colpi}\n• ambata = {snap.get('ambata')}\n• play_id = {snap.get('playable_id')}")

        if hit_pairs:
            self.playable_hit_ambo += 1
            self.playable_hit_colpi[str(self.playable_colpi)] += 1
            cost = len(snap.get("ambi", [])) * self.playable_colpi
            gross = AMBO_PAYOUT * len(hit_pairs)
            self.playable_cost_units += cost
            self.playable_gross_units += gross
            hit_txt = ", ".join(f"{a}-{b}" for a, b in hit_pairs)
            self.append_csv_event(
                "PLAYABLE_HIT_AMBO",
                e=e,
                playable_id=snap.get("playable_id"),
                playable_colpo=self.playable_colpi,
                playable_ambata=snap.get("ambata"),
                playable_ambi=self._playable_ambi_text(snap),
                playable_outcome="HIT_AMBO",
                playable_hit_ambata=int(bool(snap.get("ambata_hit"))),
                playable_hit_ambi=hit_txt,
                playable_support=snap.get("support_text", ""),
            )
            play_id = snap.get("playable_id")
            hit_colpo = self.playable_colpi
            ambata_status = f"presa al colpo {snap.get('ambata_hit_colpo')}" if snap.get("ambata_hit") else "non presa prima dell'ambo"
            self._close_playable()
            if PLAYABLE_NOTIFY_HIT:
                await self.tg(
                    app,
                    f"🔥 HIT AMBO PLAY GIOCABILE | colpo {hit_colpo}\n"
                    f"• play_id = {play_id}\n"
                    f"• ambi presi = {hit_txt}\n"
                    f"• ambata = {snap.get('ambata')} ({ambata_status})\n\n"
                    f"{self.playable_stats_text()}"
                )
            return True

        if self.playable_colpi >= PLAYABLE_MAX_COLPI:
            self.playable_stop += 1
            cost = len(snap.get("ambi", [])) * PLAYABLE_MAX_COLPI
            self.playable_cost_units += cost
            self.append_csv_event(
                "PLAYABLE_STOP",
                e=e,
                playable_id=snap.get("playable_id"),
                playable_colpo=self.playable_colpi,
                playable_ambata=snap.get("ambata"),
                playable_ambi=self._playable_ambi_text(snap),
                playable_outcome="STOP",
                playable_hit_ambata=int(bool(snap.get("ambata_hit"))),
                playable_support=snap.get("support_text", ""),
            )
            play_id = snap.get("playable_id")
            ambata_msg = f"PRESA al colpo {snap.get('ambata_hit_colpo')}" if snap.get("ambata_hit") else "NON PRESA"
            ambi_txt = self._playable_ambi_text(snap)
            self._close_playable()
            if PLAYABLE_NOTIFY_STOP:
                await self.tg(
                    app,
                    f"🛑 STOP PLAY GIOCABILE | {PLAYABLE_MAX_COLPI} colpi\n"
                    f"• play_id = {play_id}\n"
                    f"• ambata = {ambata_msg}\n"
                    f"• ambi non presi = {ambi_txt}\n\n"
                    f"{self.playable_stats_text()}"
                )
            return True

        self.save_state()
        return False

    def playable_stats_text(self):
        net, roi = roi_text(self.playable_gross_units, self.playable_cost_units)
        active = "SI" if self.playable_active else "NO"
        active_txt = ""
        if self.playable_snapshot:
            active_txt = (
                "\n\n🎲 PLAY GIOCABILE ATTIVO\n"
                f"• play_id = {self.playable_snapshot.get('playable_id')}\n"
                f"• colpo corrente = {self.playable_colpi}/{PLAYABLE_MAX_COLPI}\n"
                f"• ambata = {self.playable_snapshot.get('ambata')}\n"
                f"• ambi = {self._playable_ambi_text(self.playable_snapshot)}\n"
                f"• v48 cluster = {fmt_nums(self.playable_snapshot.get('v48_cluster'))}"
            )
        return (
            "🎲 QUADRO PLAY GIOCABILE — AMBATA/AMBI\n"
            "• logica = DECINA/MULTIPLA H3 + conferma v48\n"
            f"• play = {self.playable_total}\n"
            f"• HIT AMBATA = {self.playable_hit_ambata} ({pct(self.playable_hit_ambata, self.playable_total):.2f}%)\n"
            f"• HIT AMBO = {self.playable_hit_ambo} ({pct(self.playable_hit_ambo, self.playable_total):.2f}%)\n"
            f"• STOP AMBO = {self.playable_stop} ({pct(self.playable_stop, self.playable_total):.2f}%)\n"
            f"• attivo ora = {active}\n"
            f"• hit ambo per colpo = {', '.join(f'C{i}:{self.playable_hit_colpi.get(str(i), 0)}' for i in range(1, PLAYABLE_MAX_COLPI + 1))}\n"
            f"• economia ambo {AMBO_PAYOUT:.0f}x: costo={self.playable_cost_units:.2f}u | lordo={self.playable_gross_units:.2f}u | netto={net:+.2f}u | ROI={roi:+.2f}%\n"
            "• nota = ambata conteggiata come presa/non presa; ROI calcolato solo sugli ambi"
            f"{active_txt}"
        )

    def decina_multipla_playability_text(self):
        """Lettura operativa dei segnali aperti DECINA/MULTIPLA.

        La sezione mostra sia i dati grezzi, sia il filtro stretto usato dalla giocata automatica.
        """
        snap = self.playable_signal_snapshot()
        raw_signals = snap["raw_signals"]
        signals = snap["signals"]
        top_nums = snap["top_nums"]
        supported_pairs = snap["supported_pairs"]

        lines = [
            "🎲 GIOCABILITÀ DECINA/MULTIPLA — H3",
            "• cosa significa: non terno secco, ma ricerca di almeno 2/3 numeri entro 3 colpi",
            "• filtro usato: rete DECINA + livello MULTIPLA + cuore top numeri/ambi",
            "• giocata auto = ambata + max 2 ambi solo se c'e' conferma v48",
            "• nota: laboratorio statistico, non previsione certa",
        ]

        if not raw_signals:
            lines.extend(["", "• segnali aperti ora = 0", "• lettura = nessuna giocabilità DECINA/MULTIPLA attiva adesso"])
            return "\n".join(lines)

        top_nums_txt = ", ".join(f"{n}({c})" for n, c in top_nums[:PLAYABLE_MAX_NUMBERS]) or "n/d"
        if supported_pairs:
            ambi_line = ", ".join(f"{a}-{b}({c})" for (a, b), c in supported_pairs[:PLAYABLE_MAX_PAIRS])
            verdict = "ambi concentrati: giocabili solo se incrociano v48"
        else:
            top_pairs = snap["top_pairs"]
            ambi_line = ", ".join(f"{a}-{b}({c})" for (a, b), c in top_pairs[:PLAYABLE_MAX_PAIRS]) if top_pairs else "n/d"
            verdict = "supporto insufficiente: osservare, non giocare"

        lines.extend([
            "",
            f"• segnali DECINA/MULTIPLA grezzi = {len(raw_signals)}",
            f"• segnali focus giocabili = {len(signals)}",
            f"• DECINA extra = {snap['dec_extra']:+.2f} pp | MULTIPLA extra = {snap['mult_extra']:+.2f} pp",
            f"• numeri piu' ripetuti = {top_nums_txt}",
            f"• ambi piu' supportati = {ambi_line}",
            f"• lettura = {verdict}",
            f"• schema auto = max {PLAYABLE_MAX_COLPI} colpi; terno escluso",
        ])

        if self.active_snapshot:
            lines.extend([
                "",
                "📎 CONFERMA v48 ATTUALE",
                f"• play v48 = {self.active_snapshot.get('play_id')}",
                f"• ambata v48 = {self.active_snapshot.get('ambata')}",
                f"• cluster v48 = {fmt_nums(self.active_snapshot.get('cluster_numbers'))}",
            ])
        else:
            lines.extend(["", "📎 CONFERMA v48 ATTUALE", "• nessun play v48 attivo: il play automatico non parte"])

        candidate, reason = self.build_playable_candidate(0)
        lines.extend(["", "🎯 STATO PLAY AUTO"])
        if self.playable_active:
            lines.append("• play giocabile già attivo")
            lines.append(f"• ambata = {self.playable_snapshot.get('ambata')} | ambi = {self._playable_ambi_text(self.playable_snapshot)}")
        elif candidate:
            lines.append("• pronto: condizioni giocabili presenti")
            lines.append(f"• ambata proposta = {candidate.get('ambata')} | ambi = {self._playable_ambi_text(candidate)}")
        else:
            lines.append(f"• non parte: {reason}")

        lines.append("")
        lines.append("📌 SEGNALI FOCUS MOSTRATI")
        for idx, s in enumerate(signals[:PLAYABLE_MAX_SIGNALS], start=1):
            age = int(s.get("colpi", 0))
            left = max(0, SPY_MAX_COLPI - age)
            lines.append(
                f"{idx}) {s.get('label')} | aperto da {age}/{SPY_MAX_COLPI} colpi | restano {left} colpi | "
                f"supporto rete={s.get('active_related', 0)}/{s.get('active_total', 0)}"
            )
        if len(signals) > PLAYABLE_MAX_SIGNALS:
            lines.append(f"• altri segnali focus non mostrati = {len(signals) - PLAYABLE_MAX_SIGNALS}")

        return "\n".join(lines)


    def spy_elite_text(self):
        def read_stats(key):
            st = self.spy_candidate_horizon_stats.get(key, {}).get("3", self.new_spy_stats())
            closed = int(st.get("closed", 0))
            k2 = int(st.get("k2_hits", 0))
            k3 = int(st.get("k3_hits", 0))
            cost = float(st.get("k3_cost_units", 0.0))
            gross = float(st.get("k3_gross_units", 0.0))
            _, roi = roi_text(gross, cost)
            active_now = sum(1 for s in self.spy_sessions if s.get("key") == key)
            return st, closed, k2, k3, roi, active_now

        def aggregate(keys):
            out = self.new_spy_stats()
            active_now = 0
            for key in keys:
                st, _, _, _, _, open_count = read_stats(key)
                active_now += open_count
                for field in out:
                    out[field] += st.get(field, 0)
            return out, active_now

        lines = [
            "⭐ SPIE ELITE STORICHE — LIVE H3",
            f"• elite monitorate = {len(SPY_ELITE_ALL_KEYS)} | TOP3 = {len(SPY_ELITE_TOP3_KEYS)}",
            "• confronto = storico H3 vs live del giorno/versione corrente",
            "• uso = filtro laboratorio, non giocata automatica",
            "",
        ]

        for title, keys in (("NUCLEO TOP3", SPY_ELITE_TOP3_KEYS), ("ELITE COMPLETE", SPY_ELITE_ALL_KEYS)):
            agg, active_now = aggregate(keys)
            closed = int(agg.get("closed", 0))
            k2 = int(agg.get("k2_hits", 0))
            k3 = int(agg.get("k3_hits", 0))
            _, roi = roi_text(float(agg.get("k3_gross_units", 0.0)), float(agg.get("k3_cost_units", 0.0)))
            exp = expected_pct_from_sum(agg.get("expected_k2_sum", 0.0), closed)
            if closed < SPY_ELITE_MIN_CLOSED:
                stato = "campione piccolo"
            elif roi >= 0:
                stato = "K3 positivo nel live"
            elif pct(k2, closed) - exp >= 5:
                stato = "K2 positivo, K3 negativo"
            else:
                stato = "non confermato"
            lines.extend([
                f"📌 {title}",
                f"• live chiuse = {closed} | aperte ora = {active_now}",
                f"• K2 H3 = {k2}/{closed} = {pct(k2, closed):.2f}% | atteso≈{exp:.2f}% | extra={pct(k2, closed)-exp:+.2f} pp",
                f"• K3 H3 = {k3}/{closed} | ROI={roi:+.2f}%",
                f"• stato = {stato}",
                "",
            ])

        lines.append("📋 DETTAGLIO ELITE")
        for key in SPY_ELITE_ALL_KEYS:
            meta = SPY_ELITE_HISTORIC[key]
            st, closed, k2, k3, roi, active_now = read_stats(key)
            k2_live = pct(k2, closed)
            exp = expected_pct_from_sum(st.get("expected_k2_sum", 0.0), closed)
            sample = "OK" if closed >= SPY_ELITE_MIN_CLOSED else "piccolo"
            if closed <= 0:
                live_line = "live: nessun caso chiuso"
            else:
                live_line = (
                    f"live: chiuse={closed} | K2={k2_live:.2f}% | extra={k2_live-exp:+.2f} pp | "
                    f"K3={k3} | ROI={roi:+.2f}% | sample={sample}"
                )
            lines.append(
                f"{meta['rank']}) [{meta['tier']}] {meta['label']}\n"
                f"• storico H3: K2={meta['hist_k2_pct']:.2f}% | K3={meta['hist_k3_pct']:.2f}% | ROI={meta['hist_roi_pct']:+.2f}% | rete={meta['network']}\n"
                f"• {live_line} | aperte ora={active_now}"
            )

        lines.append("")
        lines.append("🔎 LETTURA")
        lines.append("• Coincide quando le elite storiche fanno almeno 20 chiuse e restano sopra atteso nel live.")
        lines.append("• Se DECINA/MULTIPLA vola ma le elite storiche no, il periodo live è caldo su altra zona.")
        return "\n\n".join(lines)

    def spy_top_text(self, limit=12, min_closed=SPY_TOP_MIN_CLOSED):
        rows = []
        low_sample = 0
        for key, hstats in self.spy_candidate_horizon_stats.items():
            st = hstats.get("3") or {}
            closed = int(st.get("closed", 0))
            if closed <= 0:
                continue
            if closed < min_closed:
                low_sample += 1
                continue
            rule = self.spy_model.get(key, {})
            rows.append({
                "key": key,
                "label": rule.get("label", key),
                "closed": closed,
                "k2": int(st.get("k2_hits", 0)),
                "k3": int(st.get("k3_hits", 0)),
                "roi": roi_text(float(st.get("k3_gross_units", 0.0)), float(st.get("k3_cost_units", 0.0)))[1],
                "extra": pct(int(st.get("k2_hits", 0)), closed) - expected_pct_from_sum(st.get("expected_k2_sum", 0.0), closed),
            })
        rows.sort(key=lambda r: (-r["extra"], -r["k2"], -r["closed"]))
        lines = [
            "🏆 MIGLIORI SPIE LIVE — H3",
            f"ordinate per extra K2 sopra atteso | minimo casi chiusi = {min_closed}",
            "",
        ]
        if not rows:
            if low_sample:
                lines.append(f"Nessuna spia con almeno {min_closed} casi chiusi. Regole con campione piccolo escluse = {low_sample}.")
            else:
                lines.append("Nessuna spia chiusa ancora.")
            return "\n".join(lines)
        if low_sample:
            lines.append(f"Regole escluse per campione piccolo (<{min_closed}) = {low_sample}")
            lines.append("")
        for i, r in enumerate(rows[:limit], start=1):
            lines.append(
                f"{i}) {r['label']}\n"
                f"• chiuse = {r['closed']} | K2 H3 = {r['k2']}/{r['closed']} ({pct(r['k2'], r['closed']):.2f}%) | extra≈{r['extra']:+.2f} pp\n"
                f"• K3 H3 = {r['k3']} | ROI K3 = {r['roi']:+.2f}%"
            )
        return "\n\n".join(lines)

    def spy_network_text(self):
        lines = ["🧬 NETWORK NUMERI SPIA — H3", ""]
        networks = sorted(self.spy_network_horizon_stats.keys())
        if not networks:
            return "🧬 NETWORK NUMERI SPIA\nNessuna rete chiusa ancora."
        for net in networks:
            st = self.spy_network_horizon_stats.get(net, {}).get("3", self.new_spy_stats())
            closed = int(st.get("closed", 0))
            if closed <= 0:
                continue
            k2 = int(st.get("k2_hits", 0))
            k3 = int(st.get("k3_hits", 0))
            cost = float(st.get("k3_cost_units", 0.0))
            gross = float(st.get("k3_gross_units", 0.0))
            _, roi = roi_text(gross, cost)
            exp_k2_pct = expected_pct_from_sum(st.get("expected_k2_sum", 0.0), closed)
            label = SPY_NETWORK_DEFS.get(net, {}).get("label", net)
            lines.extend([
                f"{label}",
                f"• chiuse = {closed}",
                f"• K2 H3 = {k2}/{closed} = {pct(k2, closed):.2f}% | atteso≈{exp_k2_pct:.2f}% | extra={pct(k2, closed)-exp_k2_pct:+.2f} pp",
                f"• K3 H3 = {k3} | ROI K3 = {roi:+.2f}%",
                "",
            ])
        lines.append("📶 LIVELLI RETE — H3")
        for level in SPY_LEVELS:
            st = self.spy_level_horizon_stats.get(level, {}).get("3", self.new_spy_stats())
            closed = int(st.get("closed", 0))
            if closed <= 0:
                continue
            k2 = int(st.get("k2_hits", 0))
            exp_k2_pct = expected_pct_from_sum(st.get("expected_k2_sum", 0.0), closed)
            lines.append(f"• {level}: K2 {k2}/{closed} = {pct(k2, closed):.2f}% | extra={pct(k2, closed)-exp_k2_pct:+.2f} pp")
        return "\n".join(lines).strip()

    def focus_h3_text(self):
        h3 = self.spy_horizon_stats.get("3", self.new_spy_stats())
        closed = int(h3.get("closed", 0))
        k2 = int(h3.get("k2_hits", 0))
        k3 = int(h3.get("k3_hits", 0))
        exp = expected_pct_from_sum(h3.get("expected_k2_sum", 0.0), closed)
        k2p = pct(k2, closed)
        _, roi = roi_text(float(h3.get("k3_gross_units", 0.0)), float(h3.get("k3_cost_units", 0.0)))

        dec = self.spy_network_horizon_stats.get("DECINA", {}).get("3", self.new_spy_stats())
        dec_closed = int(dec.get("closed", 0))
        dec_k2 = int(dec.get("k2_hits", 0))
        dec_exp = expected_pct_from_sum(dec.get("expected_k2_sum", 0.0), dec_closed)

        mult = self.spy_level_horizon_stats.get("MULTIPLA", {}).get("3", self.new_spy_stats())
        mult_closed = int(mult.get("closed", 0))
        mult_k2 = int(mult.get("k2_hits", 0))
        mult_exp = expected_pct_from_sum(mult.get("expected_k2_sum", 0.0), mult_closed)

        return (
            "🔎 FOCUS LETTURA RAPIDA — H3\n"
            f"• Spie globali: K2={k2}/{closed} = {k2p:.2f}% | extra={k2p-exp:+.2f} pp\n"
            f"• K3 terno 45x: {k3}/{closed} | ROI={roi:+.2f}%\n"
            f"• Rete DECINA: K2={dec_k2}/{dec_closed} = {pct(dec_k2, dec_closed):.2f}% | extra={pct(dec_k2, dec_closed)-dec_exp:+.2f} pp\n"
            f"• Livello MULTIPLA: K2={mult_k2}/{mult_closed} = {pct(mult_k2, mult_closed):.2f}% | extra={pct(mult_k2, mult_closed)-mult_exp:+.2f} pp\n"
            "• lettura: K2 misura la forza statistica; K3/ROI decide se il terno è sostenibile"
        )

    def full_report_text(self):
        return "\n\n".join([
            self.v48_stats_text(),
            self.playable_stats_text(),
            self.focus_h3_text(),
            self.decina_multipla_playability_text(),
            self.spy_elite_text(),
            self.spy_summary_text(),
            self.spy_top_text(limit=10),
            self.spy_network_text(),
            self.operational_verdict_text(),
        ])

    def operational_verdict_text(self):
        st = self.spy_horizon_stats.get("3", self.new_spy_stats())
        closed = int(st.get("closed", 0))
        k2 = int(st.get("k2_hits", 0))
        k3 = int(st.get("k3_hits", 0))
        cost = float(st.get("k3_cost_units", 0.0))
        gross = float(st.get("k3_gross_units", 0.0))
        _, roi = roi_text(gross, cost)
        exp_k2_pct = expected_pct_from_sum(st.get("expected_k2_sum", 0.0), closed)
        k2_pct = pct(k2, closed)
        extra = k2_pct - exp_k2_pct
        if closed < 50:
            stato = "campione piccolo: raccogliere dati"
        elif extra >= 5 and roi > -15:
            stato = "spie interessanti: K2 forte, K3 da verificare"
        elif extra >= 5:
            stato = "K2 positivo, terno K3 non ancora profittevole"
        elif extra > 0:
            stato = "leggero vantaggio, non sufficiente"
        else:
            stato = "spie non confermate nel periodo"
        return (
            "🧾 LETTURA OPERATIVA\n"
            f"• H3 K2 = {k2_pct:.2f}% | extra≈{extra:+.2f} pp\n"
            f"• H3 K3 = {k3}/{closed} | ROI terno={roi:+.2f}%\n"
            f"• v48: HIT={self.total_hit_ambo}, STOP={self.total_stop}, play={self.total_play}\n"
            f"• verdetto = {stato}\n"
            "• nota = uso statistico/laboratorio, non previsione certa"
        )

    def scheduled_report_header(self, slot, reason=None):
        label = {
            "14:00": "TRANCHE 1 — metà giornata",
            "23:50": "TRANCHE 2 — fine giornata",
            "DAY_CHANGE": "REPORT FINE GIORNATA — cambio giorno",
        }.get(slot, f"REPORT {slot}")
        txt = [
            f"📊 REPORT AUTOMATICO — {label}",
            f"• giorno statistiche = {self.day}",
            f"• generato = {now_txt()}",
            "• modalità = report-only: niente messaggi spie aperte/K2/K3",
        ]
        if reason:
            txt.append(f"• motivo = {reason}")
        return "\n".join(txt)

    def scheduled_report_text(self, slot, reason=None):
        return f"{self.scheduled_report_header(slot, reason)}\n\n{self.full_report_text()}"

    @staticmethod
    def _slot_to_minutes(slot):
        hh, mm = str(slot).split(":", 1)
        return int(hh) * 60 + int(mm)

    def has_reportable_data(self):
        # Per i comandi manuali: mostra sempre cio' che esiste, anche se poco.
        has_spy_data = any(
            int(v.get("sessions", 0)) or int(v.get("closed", 0))
            for v in self.spy_horizon_stats.values()
        )
        return bool(
            self.total_play
            or self.total_hit_ambo
            or self.total_stop
            or self.playable_total
            or self.playable_active
            or self.spy_sessions
            or has_spy_data
        )

    def has_scheduled_reportable_data(self):
        # Per i report automatici: evita report vuoti/giovani da istanze appena avviate.
        h3_closed = int(self.spy_horizon_stats.get("3", {}).get("closed", 0))
        meaningful_v48 = bool(
            self.total_play
            or self.total_hit_ambo
            or self.total_stop
            or self.playable_total
            or self.playable_active
            or (self.active and self.colpi >= AUTO_REPORT_ALLOW_ACTIVE_V48_AFTER_COLPO)
        )
        return meaningful_v48 or h3_closed >= AUTO_REPORT_MIN_H3_CLOSED

    async def maybe_send_scheduled_report(self, app):
        if not AUTO_REPORT_ENABLED:
            return
        if not self.has_scheduled_reportable_data():
            return
        now = now_dt()
        current = now.hour * 60 + now.minute
        today = day_key()
        if len(self.scheduled_reports_sent) > 40:
            self.scheduled_reports_sent = dict(list(self.scheduled_reports_sent.items())[-25:])
        for slot in AUTO_REPORT_TIMES:
            target = self._slot_to_minutes(slot)
            key = f"{today}_{slot}"
            if key in self.scheduled_reports_sent:
                continue
            if target <= current <= target + AUTO_REPORT_WINDOW_MINUTES:
                self.scheduled_reports_sent[key] = now_txt()
                self.save_state()
                await self.tg(app, self.scheduled_report_text(slot), inline_menu=True)

    async def send_day_change_report_if_needed(self, app):
        # Fallback: se la tranche serale non è partita, prima del reset invia un report finale.
        key = f"{self.day}_DAY_CHANGE"
        if key in self.scheduled_reports_sent:
            return
        if not self.has_scheduled_reportable_data():
            return
        self.scheduled_reports_sent[key] = now_txt()
        self.save_state()
        await self.tg(app, self.scheduled_report_text("DAY_CHANGE", reason="reset nuovo giorno"), inline_menu=True)

    def menu_text(self):
        return (
            "🧭 MENU RAPIDO\n"
            "Tocca un pulsante sotto, senza digitare nulla.\n\n"
            "/report — quadro completo\n"
            "/play — solo play giocabile ambata/ambi\n"
            "/v48 — solo v48 base\n"
            "/spie — quadro numeri spia\n"
            "/spie_elite — spie elite storiche live\n"
            "/spie_play — giocabilità DECINA/MULTIPLA live\n"
            "/spie_top — migliori spie live\n"
            "/spie_network — reti numeriche spia\n"
            "/menu — mostra questo menu"
        )

    # --------------------------------------------------------
    # Main draw logic
    # --------------------------------------------------------
    async def on_new(self, app, e, nums):
        if len(set(nums)) != 20:
            return
        if self.already_processed(e, nums):
            return

        self.remember_processed(e, nums)
        self.last_draws.append(nums)
        self.last_draws = self.last_draws[-HISTORY_MAX:]
        self.draws_since_spy_report += 1

        if DRAW_NOTIFY:
            await self.tg(app, f"📌 Estrazione {e}\n🎱 {', '.join(map(str, nums))}")

        # 1) aggiorna sessioni spia e play operativo già aperti sui nuovi numeri.
        await self.process_spy_sessions(app, e, nums)
        await self.process_playable_play(app, e, nums)

        # 2) apre nuove spie dalla condizione appena creata.
        await self.maybe_open_spy_sessions(app, e)

        # 3) processa v48 attivo. v48 resta core/struttura; le notifiche singole sono opzionali.
        skip_new_play = False
        if self.active:
            self.colpi += 1
            hit_data = self.check_v48_hit(nums)

            if hit_data["ambata_hit"]:
                self.total_hit_ambata += 1
                self.append_csv_event("V48_HIT_AMBATA", e=e, play_id=self.active_snapshot.get("play_id"), colpo=self.colpi, outcome="HIT_AMBATA")
                if V48_NOTIFY_EVENTS:
                    await self.tg(app, f"🎯 AMBATA PRESA v48 | colpo {self.colpi}\n• ambata = {self.active_snapshot['ambata']}")

            if hit_data["ambi_hit"]:
                self.total_hit_ambo += 1
                self.v48_hit_colpi[str(self.colpi)] += 1
                hit_ranks = []
                hit_pairs = []
                for hit_item in hit_data["ambi_hit"]:
                    hp = tuple(map(int, hit_item["ambo"]))
                    hit_pairs.append(f"{hp[0]}-{hp[1]}")
                    for idx, item in enumerate(self.active_snapshot.get("ambi", []), start=1):
                        if tuple(map(int, item["ambo"])) == hp:
                            self.v48_rank_hits[str(idx)] += 1
                            hit_ranks.append(idx)
                            break
                if len(set(hit_ranks)) >= 2:
                    self.v48_multi_ambo_hit_draws += 1

                self.v48_cost_units += MAX_AMBI_PER_PLAY * self.colpi
                self.v48_gross_units += AMBO_PAYOUT * max(1, len(hit_data["ambi_hit"]))
                self.append_csv_event(
                    "V48_HIT_AMBO",
                    e=e,
                    play_id=self.active_snapshot.get("play_id"),
                    colpo=self.colpi,
                    ambata=self.active_snapshot.get("ambata"),
                    ambi=fmt_ambi(self.active_snapshot.get("ambi")),
                    cluster=fmt_nums(self.active_snapshot.get("cluster_numbers")),
                    outcome="HIT_AMBO",
                    hit_ambi=", ".join(hit_pairs),
                    hit_ranks=", ".join(map(str, sorted(set(hit_ranks)))),
                )
                hit_colpo = self.colpi
                closed_snapshot = self.active_snapshot
                self.last_cluster_numbers = closed_snapshot["cluster_numbers"]
                self.last_cluster_e = e
                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None
                if V48_NOTIFY_EVENTS:
                    await self.tg(
                        app,
                        f"🔥 HIT AMBO v48 | colpo {hit_colpo}\n"
                        f"• ambi = {', '.join(hit_pairs)}\n"
                        f"• rank vincenti = {', '.join(map(str, sorted(set(hit_ranks)))) or 'n/d'}\n\n"
                        f"{self.v48_stats_text()}"
                    )
                skip_new_play = True

            elif self.colpi >= MAX_COLPI:
                self.total_stop += 1
                self.v48_cost_units += MAX_AMBI_PER_PLAY * MAX_COLPI
                self.append_csv_event(
                    "V48_STOP",
                    e=e,
                    play_id=self.active_snapshot.get("play_id"),
                    colpo=self.colpi,
                    ambata=self.active_snapshot.get("ambata"),
                    ambi=fmt_ambi(self.active_snapshot.get("ambi")),
                    cluster=fmt_nums(self.active_snapshot.get("cluster_numbers")),
                    outcome="STOP",
                )
                closed_snapshot = self.active_snapshot
                self.last_cluster_numbers = closed_snapshot["cluster_numbers"]
                self.last_cluster_e = e
                self.active = False
                self.colpi = 0
                self.cooldown = COOLDOWN_AFTER_PLAY
                self.active_snapshot = None
                if V48_NOTIFY_EVENTS:
                    await self.tg(app, f"🛑 STOP v48 | {MAX_COLPI} colpi\n\n{self.v48_stats_text()}")
                skip_new_play = True
            else:
                # v48 resta attivo: se ora DECINA/MULTIPLA convergono, apri il play pratico.
                await self.maybe_open_playable_play(app, e)
                self.save_state()
                return

        # 4) se v48 era attivo e ha chiuso, non apre un nuovo play nello stesso colpo.
        if skip_new_play:
            self.save_state()
            return

        # 5) cooldown/history/hot/build v48.
        if self.cooldown > 0:
            self.cooldown -= 1
            self.save_state()
            return

        if len(self.last_draws) >= 30:
            _, selected = self.selected_ritardatari()
            self.update_watch_and_confirmed(e, nums, selected)
            play = self.build_play(e)
            if play and not self.active:
                self.active = True
                self.colpi = 0
                self.play_uid += 1
                play["play_id"] = self.play_uid
                self.active_snapshot = play
                self.total_play += 1
                self.append_csv_event(
                    "V48_PLAY",
                    e=e,
                    play_id=play["play_id"],
                    colpo=0,
                    ambata=play["ambata"],
                    ambi=fmt_ambi(play["ambi"]),
                    cluster=fmt_nums(play["cluster_numbers"]),
                    outcome="OPEN",
                )
                if V48_NOTIFY_EVENTS:
                    await self.tg(
                        app,
                        "🎯 PLAY v48 BASE\n"
                        f"• play_id = {play['play_id']}\n"
                        f"• ambata = {play['ambata']}\n"
                        f"• ambi = {fmt_ambi(play['ambi'])}\n"
                        f"• cluster = {fmt_nums(play['cluster_numbers'])}\n"
                        f"• max colpi = {MAX_COLPI}\n"
                        "• modulo attivo = solo 3 ambi classici"
                    )
                # Prova subito a trasformare la struttura v48 in play operativo giocabile.
                await self.maybe_open_playable_play(app, e)

        if SPY_REPORT_EVERY_DRAWS and self.draws_since_spy_report >= SPY_REPORT_EVERY_DRAWS:
            self.draws_since_spy_report = 0
            await self.tg(app, self.spy_summary_text())

        self.save_state()


# ============================================================
# TELEGRAM COMMAND HANDLERS
# ============================================================

async def reply(update: Update, text: str, inline_menu=False):
    if update.message:
        for part in chunks(text, 3000):
            await update.message.reply_text(part, reply_markup=INLINE_MENU if inline_menu else MENU_KEYBOARD)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.menu_text(), inline_menu=True)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.menu_text(), inline_menu=True)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.full_report_text())


async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.playable_stats_text() + "\n\n" + engine.decina_multipla_playability_text())


async def cmd_v48(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.v48_stats_text())


async def cmd_spie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.spy_summary_text())


async def cmd_spie_elite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.spy_elite_text())


async def cmd_spie_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.decina_multipla_playability_text())


async def cmd_spie_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.spy_top_text())


async def cmd_spie_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine = context.application.bot_data["engine"]
    await reply(update, engine.spy_network_text())


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    engine = context.application.bot_data["engine"]
    data = query.data
    if data == "report":
        text = engine.full_report_text()
    elif data == "play":
        text = engine.playable_stats_text() + "\n\n" + engine.decina_multipla_playability_text()
    elif data == "v48":
        text = engine.v48_stats_text()
    elif data == "spie":
        text = engine.spy_summary_text()
    elif data == "spie_elite":
        text = engine.spy_elite_text()
    elif data == "spie_play":
        text = engine.decina_multipla_playability_text()
    elif data == "spie_top":
        text = engine.spy_top_text()
    elif data == "spie_network":
        text = engine.spy_network_text()
    else:
        text = engine.menu_text()
    for part in chunks(text, 3000):
        await query.message.reply_text(part, reply_markup=INLINE_MENU)


# ============================================================
# SINGLE INSTANCE LOCK
# ============================================================

_LOCK_HANDLE = None


def acquire_single_instance_lock():
    global _LOCK_HANDLE
    _LOCK_HANDLE = open(LOCK_FILE, "a+", encoding="utf-8")
    if fcntl is not None:
        try:
            fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("⚠️ Un'altra istanza SNIPER v48 BASE + FULL SPY è già attiva. Avvio bloccato.")
            sys.exit(1)
    else:
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
# LIVE LOOP + POLLING COMMANDS
# ============================================================

async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("report", "Quadro completo"),
        BotCommand("play", "Play giocabile ambata/ambi"),
        BotCommand("v48", "Statistiche v48 base"),
        BotCommand("spie", "Quadro numeri spia"),
        BotCommand("spie_elite", "Spie elite storiche live"),
        BotCommand("spie_play", "Giocabilità DECINA/MULTIPLA"),
        BotCommand("spie_top", "Migliori spie live"),
        BotCommand("spie_network", "Reti numeriche spia"),
        BotCommand("menu", "Mostra pulsanti"),
    ])


async def startup(engine, app):
    current_day = day_key()
    if engine.day != current_day:
        await engine.send_day_change_report_if_needed(app)
        engine.reset_for_new_day(current_day)
        await engine.tg(app, "🗓️ Nuovo giorno rilevato: reset operativo v48/spie. Storico numerico conservato.")

    es = parse_site()
    if not es:
        await engine.tg(app, "⚠️ parser vuoto")
        return

    if not engine.last_draws:
        engine.preload_today_as_processed(es)
        await engine.tg(
            app,
            "🚀 SNIPER v48 BASE + FULL NUMERI SPIA LAB — v6 PLAY AMBATA/AMBI AVVIATO\n"
            "✅ v48 base invariata: ambata + 3 ambi classici\n"
            "✅ max 7 colpi, cooldown e cluster reuse invariati\n"
            "✅ monitor rank ambo vincente 1/2/3\n"
            f"✅ economia v48: ambo {AMBO_PAYOUT:.0f}x\n"
            f"✅ numeri spia caricati: {len(engine.spy_model)} regole storico-statistiche\n"
            "✅ condizioni C1/C2/C3+/non consecutive\n"
            "✅ orizzonti spia H1/H2/H3\n"
            f"✅ economia terno spie: {TERNO_PAYOUT:.0f}x\n"
            "✅ comandi Telegram cliccabili attivi\n"
            "✅ modalità report-only: niente messaggi spie aperte/K2/K3\n"
            "✅ atteso K2/K3 corretto solo sulle sessioni chiuse\n"
            "✅ sezione ⭐ SPIE ELITE STORICHE — LIVE\n"
            "✅ sezione 🎲 GIOCABILITÀ DECINA/MULTIPLA — H3\n"
            f"✅ play operativo = ambata + max {PLAYABLE_MAX_AMBI} ambi, max {PLAYABLE_MAX_COLPI} colpi\n"
            "✅ notifiche PLAY = apertura, ambata presa, ambo preso, stop/non preso\n"
            f"✅ notifiche v48 singole = {'ON' if V48_NOTIFY_EVENTS else 'OFF'}\n"
            f"✅ orario bot = {BOT_TZ_NAME}\n"
            f"✅ persistenza GitHub state/csv = {'ON' if PERSIST_GIT_STATE else 'OFF'}\n"
            "✅ report automatici severi anti-report-vuoto\n"
            f"✅ report automatici: {', '.join(AUTO_REPORT_TIMES)} + cambio giorno\n"
            "✅ storico iniziale marcato come processato\n"
            "✅ niente replay iniziale\n\n"
            "Tocca /menu per vedere i pulsanti."
        )
        await engine.tg(app, engine.menu_text(), inline_menu=True)


async def live_loop(engine, app):
    while True:
        try:
            current_day = day_key()
            if engine.day != current_day:
                await engine.send_day_change_report_if_needed(app)
                engine.reset_for_new_day(current_day)
                await engine.tg(app, "🗓️ Nuovo giorno rilevato: reset operativo dedup/watch/hot/spie.")
                es = parse_site()
                if es:
                    engine.preload_today_as_processed(es)
                    await engine.tg(app, "✅ nuovo giorno inizializzato: estrazioni già uscite oggi marcate come storico/processate")
                await asyncio.sleep(LOOP_SEC)
                continue

            es = parse_site()
            for e, nums in es:
                if engine.already_processed(e, nums):
                    continue
                await engine.on_new(app, e, nums)
            await engine.maybe_send_scheduled_report(app)
        except Exception as ex:
            print(f"Errore loop: {ex}")
            try:
                await engine.tg(app, f"⚠️ errore SNIPER v48 BASE + FULL SPY: {ex}")
            except Exception:
                pass
        await asyncio.sleep(LOOP_SEC)


async def main():
    global CHAT_ID
    CHAT_ID = validate_env()
    acquire_single_instance_lock()

    engine = SniperV48BaseFullSpy()
    app = ApplicationBuilder().token(TOKEN).build()
    app.bot_data["engine"] = engine

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("play", cmd_play))
    app.add_handler(CommandHandler("v48", cmd_v48))
    app.add_handler(CommandHandler("spie", cmd_spie))
    app.add_handler(CommandHandler("spie_elite", cmd_spie_elite))
    app.add_handler(CommandHandler("spie_play", cmd_spie_play))
    app.add_handler(CommandHandler("spie_top", cmd_spie_top))
    app.add_handler(CommandHandler("spie_network", cmd_spie_network))
    app.add_handler(CallbackQueryHandler(on_button))

    await app.initialize()
    await setup_commands(app)
    await app.start()
    await app.updater.start_polling()

    await startup(engine, app)
    try:
        await live_loop(engine, app)
    finally:
        try:
            engine.save_state()
            maybe_git_commit_state("shutdown", force=True)
        except Exception as ex:
            print(f"Salvataggio finale saltato: {ex}")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
