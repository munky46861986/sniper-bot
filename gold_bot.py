# ============================================================
# 🟡 GOLD BOT TRADER PRO v4
# GitHub Ready
# ============================================================

import os
import asyncio
import nest_asyncio
import yfinance as yf
import pandas as pd

from datetime import datetime
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder

nest_asyncio.apply()

# ===================== CONFIG ===============================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

SYMBOL = "GC=F"

TIMEFRAME = "5m"
PERIOD = "5d"

HIGHER_TIMEFRAME = "1h"
HIGHER_PERIOD = "30d"

LOOP_SEC = 60

EMA_FAST = 20
EMA_SLOW = 50

RSI_PERIOD = 14
ATR_PERIOD = 14

RSI_LONG = 58
RSI_SHORT = 42

COOLDOWN_MINUTES = 20

# ============================================================

def now_italy():
    return datetime.now(
        ZoneInfo("Europe/Rome")
    ).strftime("%d/%m/%Y %H:%M:%S")


# ===================== DATA =================================

def get_data(interval, period):

    df = yf.download(
        SYMBOL,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=True
    )

    if df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()

    if df.empty:
        return None

    return df


# ===================== INDICATORS ===========================

def calc_rsi(series, period=14):

    delta = series.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def calc_atr(df, period=14):

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    return tr.rolling(period).mean()


# ===================== TREND H1 =============================

def higher_trend():

    df = get_data(
        HIGHER_TIMEFRAME,
        HIGHER_PERIOD
    )

    if df is None or len(df) < 60:
        return "SCONOSCIUTO"

    close = df["Close"]

    ema20 = float(
        close.ewm(
            span=20,
            adjust=False
        ).mean().iloc[-1]
    )

    ema50 = float(
        close.ewm(
            span=50,
            adjust=False
        ).mean().iloc[-1]
    )

    price = float(close.iloc[-1])

    if price > ema20 > ema50:
        return "RIALZISTA"

    elif price < ema20 < ema50:
        return "RIBASSISTA"

    else:
        return "LATERALE"


# ===================== SCORE ================================

def probability_score(
    signal,
    price,
    ema20,
    ema50,
    rsi,
    trend_h1
):

    score = 50

    if signal == "LONG":

        if ema20 > ema50:
            score += 10

        if price > ema20:
            score += 10

        if rsi > 60:
            score += 10

        if trend_h1 == "RIALZISTA":
            score += 15

        elif trend_h1 == "RIBASSISTA":
            score -= 15

    elif signal == "SHORT":

        if ema20 < ema50:
            score += 10

        if price < ema20:
            score += 10

        if rsi < 40:
            score += 10

        if trend_h1 == "RIBASSISTA":
            score += 15

        elif trend_h1 == "RIALZISTA":
            score -= 15

    return max(35, min(score, 90))


# ===================== ANALYZE ==============================

def analyze_gold():

    df = get_data(
        TIMEFRAME,
        PERIOD
    )

    if df is None or len(df) < 100:
        return None

    close = df["Close"]

    ema20_series = close.ewm(
        span=EMA_FAST,
        adjust=False
    ).mean()

    ema50_series = close.ewm(
        span=EMA_SLOW,
        adjust=False
    ).mean()

    rsi_series = calc_rsi(
        close,
        RSI_PERIOD
    )

    atr_series = calc_atr(
        df,
        ATR_PERIOD
    )

    price = float(close.iloc[-1])

    ema20 = float(
        ema20_series.iloc[-1]
    )

    ema50 = float(
        ema50_series.iloc[-1]
    )

    rsi = float(
        rsi_series.iloc[-1]
    )

    atr = float(
        atr_series.iloc[-1]
    )

    if pd.isna(rsi) or pd.isna(atr):
        return None

    trend_h1 = higher_trend()

    bull = (
        ema20 > ema50 and
        price > ema20 and
        rsi > RSI_LONG
    )

    bear = (
        ema20 < ema50 and
        price < ema20 and
        rsi < RSI_SHORT
    )

    if bull:

        signal = "LONG"

        title = "🟢 LONG XAUUSD"

        tp1 = price + atr * 1.2
        tp2 = price + atr * 2.0
        sl = price - atr * 1.0

        reason = (
            "EMA20 sopra EMA50, "
            "prezzo sopra EMA20, "
            "RSI forte."
        )

    elif bear:

        signal = "SHORT"

        title = "🔴 SHORT XAUUSD"

        tp1 = price - atr * 1.2
        tp2 = price - atr * 2.0
        sl = price + atr * 1.0

        reason = (
            "EMA20 sotto EMA50, "
            "prezzo sotto EMA20, "
            "RSI debole."
        )

    else:

        return "NEUTRAL", None

    prob = probability_score(
        signal,
        price,
        ema20,
        ema50,
        rsi,
        trend_h1
    )

    if prob >= 75:
        strength = "FORTE"

    elif prob >= 60:
        strength = "MEDIA"

    else:
        strength = "DEBOLE"

    if atr > 2.5:
        volatility = "ALTA"

    elif atr > 1.2:
        volatility = "MEDIA"

    else:
        volatility = "BASSA"

    data = {
        "signal": signal,
        "title": title,
        "price": price,
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "atr": atr,
        "trend_h1": trend_h1,
        "prob": prob,
        "strength": strength,
        "volatility": volatility,
        "reason": reason
    }

    return signal, data


# ===================== BOT =================================

class GoldBot:

    def __init__(self):

        self.last_signal = None
        self.last_alert_time = None
        self.active_trade = None

    async def tg(self, app, msg):

        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=msg
        )

        await asyncio.sleep(0.2)

    def cooldown_ok(self):

        if self.last_alert_time is None:
            return True

        diff = (
            datetime.now(
                ZoneInfo("Europe/Rome")
            ) - self.last_alert_time
        )

        return (
            diff.total_seconds() >=
            COOLDOWN_MINUTES * 60
        )

    async def open_trade(
        self,
        app,
        data
    ):

        msg = (
            f"{data['title']} | "
            f"Forza {data['strength']}\n\n"

            f"🕒 Ora Italia: {now_italy()}\n"
            f"📌 Simbolo: {SYMBOL}\n"
            f"⏱️ Timeframe: {TIMEFRAME}\n\n"

            f"💰 Entry: {data['price']:.2f}\n\n"

            f"🎯 TP1: {data['tp1']:.2f}\n"
            f"🎯 TP2: {data['tp2']:.2f}\n"
            f"🛑 SL: {data['sl']:.2f}\n\n"

            f"📈 EMA20: {data['ema20']:.2f}\n"
            f"📉 EMA50: {data['ema50']:.2f}\n"
            f"⚡ RSI14: {data['rsi']:.2f}\n"
            f"🌪️ ATR14: {data['atr']:.2f}\n\n"

            f"📊 Trend H1: {data['trend_h1']}\n"
            f"🔥 Volatilità: {data['volatility']}\n"
            f"📌 Probabilità: {data['prob']}%\n\n"

            f"🧠 Motivo:\n"
            f"{data['reason']}\n\n"

            "⚠️ Segnale tecnico."
        )

        await self.tg(app, msg)

        self.active_trade = {
            **data,
            "tp1_hit": False,
            "tp2_hit": False,
            "sl_hit": False
        }

    async def check(self, app):

        result = analyze_gold()

        if result is None:
            return

        signal, data = result

        if signal == "NEUTRAL":
            return

        if (
            signal != self.last_signal and
            self.cooldown_ok()
        ):

            await self.open_trade(
                app,
                data
            )

            self.last_signal = signal

            self.last_alert_time = datetime.now(
                ZoneInfo("Europe/Rome")
            )

    async def start(self, app):

        await self.tg(
            app,
            "🟡 GOLD BOT TRADER PRO v4 AVVIATO\n\n"

            f"📌 Simbolo: {SYMBOL}\n"
            f"⏱️ Timeframe: {TIMEFRAME}\n"
            f"📊 Trend filter: {HIGHER_TIMEFRAME}\n"
            f"🔁 Check ogni {LOOP_SEC} sec\n\n"

            "Strategia:\n"
            "EMA20 + EMA50 + RSI + ATR + Trend H1\n\n"

            "⚠️ Non è consulenza finanziaria."
        )


# ===================== MAIN =================================

bot = GoldBot()


async def live():

    app = ApplicationBuilder().token(TOKEN).build()

    await bot.start(app)

    while True:

        try:

            await bot.check(app)

        except Exception as ex:

            await bot.tg(
                app,
                f"⚠️ Errore BOT:\n{ex}"
            )

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
