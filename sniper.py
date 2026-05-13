# ============================================================
# 🟡 GOLD BOT v1 — Strategia Oro/XAUUSD
#
# Logica:
# 1) Scarica dati oro ogni minuto
# 2) Calcola EMA20, EMA50, RSI14, supporto/resistenza
# 3) Genera segnale:
#    🟢 LONG se trend rialzista + RSI forte + breakout
#    🔴 SHORT se trend ribassista + RSI debole + breakdown
#    ⚪ NEUTRO se mercato incerto
# 4) Manda alert Telegram solo quando cambia segnale
# ============================================================

import asyncio
import os
import json
from datetime import datetime

import yfinance as yf
import pandas as pd
from telegram.ext import ApplicationBuilder
import nest_asyncio

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

STATE_FILE = "gold_bot_state.json"

SYMBOL = os.getenv("GOLD_SYMBOL", "GC=F")  # Oro future Yahoo Finance
INTERVAL = "1m"
PERIOD = "1d"

LOOP_SEC = 60

EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
SR_WINDOW = 30

RSI_LONG_MIN = 55
RSI_SHORT_MAX = 45


def now_txt():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def download_gold():
    df = yf.download(
        SYMBOL,
        period=PERIOD,
        interval=INTERVAL,
        progress=False,
        auto_adjust=True
    )

    if df.empty:
        return None

    df = df.dropna()
    return df


def rsi(series, period=14):
    delta = series.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def analyze_gold():
    df = download_gold()

    if df is None or len(df) < 80:
        return {
            "signal": "NO_DATA",
            "message": "⚠️ Dati insufficienti per analizzare l’oro."
        }

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    df["ema_fast"] = close.ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=EMA_SLOW, adjust=False).mean()
    df["rsi"] = rsi(close, RSI_PERIOD)

    price = float(close.iloc[-1])
    prev_price = float(close.iloc[-5])

    ema_fast = float(df["ema_fast"].iloc[-1])
    ema_slow = float(df["ema_slow"].iloc[-1])
    rsi_now = float(df["rsi"].iloc[-1])

    resistance = float(high.iloc[-SR_WINDOW:-1].max())
    support = float(low.iloc[-SR_WINDOW:-1].min())

    change = ((price - prev_price) / prev_price) * 100

    trend_up = price > ema_fast > ema_slow
    trend_down = price < ema_fast < ema_slow

    breakout_up = price > resistance
    breakout_down = price < support

    if trend_up and rsi_now >= RSI_LONG_MIN:
        signal = "LONG"
        title = "🟢 POSSIBILE SALITA ORO"
        reason = "Prezzo sopra EMA20/EMA50 e RSI positivo."

        if breakout_up:
            title = "🚀 BREAKOUT RIALZISTA ORO"
            reason = "Prezzo sopra la resistenza recente con trend positivo."

    elif trend_down and rsi_now <= RSI_SHORT_MAX:
        signal = "SHORT"
        title = "🔴 POSSIBILE DISCESA ORO"
        reason = "Prezzo sotto EMA20/EMA50 e RSI debole."

        if breakout_down:
            title = "📉 BREAKDOWN RIBASSISTA ORO"
            reason = "Prezzo sotto il supporto recente con trend negativo."

    else:
        signal = "NEUTRAL"
        title = "⚪ ORO INCERTO / LATERALE"
        reason = "Non c’è conferma chiara tra trend, RSI e livelli tecnici."

    message = (
        f"{title}\n\n"
        f"🕒 Ora: {now_txt()}\n"
        f"📌 Simbolo: {SYMBOL}\n"
        f"💰 Prezzo: {price:.2f}\n"
        f"📊 Variazione ultimi minuti: {change:.2f}%\n\n"
        f"📈 EMA{EMA_FAST}: {ema_fast:.2f}\n"
        f"📉 EMA{EMA_SLOW}: {ema_slow:.2f}\n"
        f"⚡ RSI{RSI_PERIOD}: {rsi_now:.2f}\n\n"
        f"🧱 Supporto: {support:.2f}\n"
        f"🚧 Resistenza: {resistance:.2f}\n\n"
        f"🧠 Motivo: {reason}\n\n"
        f"⚠️ Segnale tecnico, non consiglio finanziario."
    )

    return {
        "signal": signal,
        "message": message,
        "price": price,
        "rsi": rsi_now,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "support": support,
        "resistance": resistance
    }


class GOLD_BOT:

    def __init__(self):
        self.version = "gold_bot_v1"
        self.last_signal = None
        self.last_price = None
        self.total_checks = 0
        self.total_alerts = 0
        self.load_state()

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

    def save_state(self):
        data = {
            "version": self.version,
            "last_signal": self.last_signal,
            "last_price": self.last_price,
            "total_checks": self.total_checks,
            "total_alerts": self.total_alerts,
            "updated_at": now_txt()
        }

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            return

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.last_signal = data.get("last_signal")
            self.last_price = data.get("last_price")
            self.total_checks = int(data.get("total_checks", 0))
            self.total_alerts = int(data.get("total_alerts", 0))

        except Exception:
            pass

    async def check_gold(self, app):
        result = analyze_gold()

        self.total_checks += 1

        signal = result.get("signal")
        message = result.get("message")

        if signal == "NO_DATA":
            await self.tg(app, message)
            self.save_state()
            return

        price = result.get("price")

        signal_changed = signal != self.last_signal

        if signal_changed:
            self.total_alerts += 1
            await self.tg(app, message)

        self.last_signal = signal
        self.last_price = price
        self.save_state()

    async def send_start_message(self, app):
        await self.tg(
            app,
            "🟡 GOLD BOT v1 AVVIATO\n\n"
            f"📌 Simbolo: {SYMBOL}\n"
            f"⏱️ Controllo ogni {LOOP_SEC} secondi\n"
            f"📊 Strategia: EMA{EMA_FAST}/EMA{EMA_SLOW} + RSI{RSI_PERIOD} + supporti/resistenze\n\n"
            "⚠️ I segnali sono tecnici, non consigli finanziari."
        )

    async def send_report(self, app):
        await self.tg(
            app,
            "📊 REPORT GOLD BOT\n\n"
            f"• controlli totali = {self.total_checks}\n"
            f"• alert inviati = {self.total_alerts}\n"
            f"• ultimo segnale = {self.last_signal}\n"
            f"• ultimo prezzo = {self.last_price}\n"
        )


bot = GOLD_BOT()


async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    await bot.send_start_message(app)

    while True:
        try:
            await bot.check_gold(app)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore GOLD BOT: {ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
