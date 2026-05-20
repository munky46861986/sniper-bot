# ============================================================
# 🟡 GOLD BOT TRADER PRO v5.4
# EARLY MOMENTUM + PRE ALERT + TP/SL
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

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

SYMBOL = "GC=F"

TIMEFRAME = "1m"
PERIOD = "1d"

HIGHER_TIMEFRAME = "1h"
HIGHER_PERIOD = "30d"

LOOP_SEC = 10

EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
ATR_PERIOD = 14

RSI_LONG = 58
RSI_SHORT = 42

RSI_PRE_LONG = 50
RSI_PRE_SHORT = 50

COOLDOWN_MINUTES = 20
PRE_COOLDOWN_MINUTES = 3
EARLY_COOLDOWN_MINUTES = 2


def now_italy():
    return datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M:%S")


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

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean()


def higher_trend():
    df = get_data(HIGHER_TIMEFRAME, HIGHER_PERIOD)

    if df is None or len(df) < 60:
        return "SCONOSCIUTO"

    close = df["Close"]

    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    price = float(close.iloc[-1])

    if price > ema20 > ema50:
        return "RIALZISTA"

    if price < ema20 < ema50:
        return "RIBASSISTA"

    return "LATERALE"


def probability_score(signal, price, ema20, ema50, rsi, trend_h1):
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


def analyze_gold():
    df = get_data(TIMEFRAME, PERIOD)

    if df is None or len(df) < 100:
        return None

    close = df["Close"]
    open_ = df["Open"]

    ema20_series = close.ewm(span=EMA_FAST, adjust=False).mean()
    ema50_series = close.ewm(span=EMA_SLOW, adjust=False).mean()
    rsi_series = calc_rsi(close, RSI_PERIOD)
    atr_series = calc_atr(df, ATR_PERIOD)

    price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])

    ema20 = float(ema20_series.iloc[-1])
    ema50 = float(ema50_series.iloc[-1])

    ema20_prev = float(ema20_series.iloc[-2])
    ema50_prev = float(ema50_series.iloc[-2])

    rsi = float(rsi_series.iloc[-1])
    rsi_prev = float(rsi_series.iloc[-2])
    rsi_prev2 = float(rsi_series.iloc[-3])

    atr = float(atr_series.iloc[-1])

    candle_open = float(open_.iloc[-1])
    candle_close = float(close.iloc[-1])

    if pd.isna(rsi) or pd.isna(atr):
        return None

    trend_h1 = higher_trend()

    ema20_slope = ema20 - ema20_prev
    ema50_slope = ema50 - ema50_prev
    rsi_slope = rsi - rsi_prev
    rsi_acceleration = (rsi - rsi_prev) + (rsi_prev - rsi_prev2)

    bullish_candle = candle_close > candle_open
    bearish_candle = candle_close < candle_open

    price_momentum_up = price > prev_price
    price_momentum_down = price < prev_price

    base = {
        "price": price,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "atr": atr,
        "trend_h1": trend_h1,
        "rsi_slope": rsi_slope,
        "rsi_acceleration": rsi_acceleration,
        "ema20_slope": ema20_slope,
    }

    # ================= EARLY MOMENTUM =================

    early_long = (
        ema20 > ema50
        and ema20_slope > 0
        and price > ema20
        and rsi >= 48
        and rsi_slope > 0.8
        and rsi_acceleration > 0
        and bullish_candle
        and price_momentum_up
    )

    early_short = (
        ema20 < ema50
        and ema20_slope < 0
        and price < ema20
        and rsi <= 52
        and rsi_slope < -0.8
        and rsi_acceleration < 0
        and bearish_candle
        and price_momentum_down
    )

    # ================= PRE SIGNAL =================

    pre_long = (
        ema20 > ema50
        and price > ema20
        and RSI_PRE_LONG <= rsi < RSI_LONG
    )

    pre_short = (
        ema20 < ema50
        and price < ema20
        and RSI_SHORT < rsi <= RSI_PRE_SHORT
    )

    # ================= CONFIRMED =================

    long_signal = (
        ema20 > ema50
        and price > ema20
        and rsi >= RSI_LONG
    )

    short_signal = (
        ema20 < ema50
        and price < ema20
        and rsi <= RSI_SHORT
    )

    if early_long:
        return "EARLY_LONG", base

    if early_short:
        return "EARLY_SHORT", base

    if pre_long:
        return "PRE_LONG", base

    if pre_short:
        return "PRE_SHORT", base

    if long_signal:
        signal = "LONG"
        title = "🟢 LONG XAUUSD"
        tp1 = price + atr * 1.2
        tp2 = price + atr * 2.0
        sl = price - atr * 1.0
        reason = "EMA20 sopra EMA50, prezzo sopra EMA20, RSI forte."

    elif short_signal:
        signal = "SHORT"
        title = "🔴 SHORT XAUUSD"
        tp1 = price - atr * 1.2
        tp2 = price - atr * 2.0
        sl = price + atr * 1.0
        reason = "EMA20 sotto EMA50, prezzo sotto EMA20, RSI debole."

    else:
        return "NEUTRAL", None

    prob = probability_score(signal, price, ema20, ema50, rsi, trend_h1)

    strength = "FORTE" if prob >= 75 else "MEDIA" if prob >= 60 else "DEBOLE"
    volatility = "ALTA" if atr > 2.5 else "MEDIA" if atr > 1.2 else "BASSA"

    data = {
        **base,
        "signal": signal,
        "title": title,
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
        "reason": reason,
        "prob": prob,
        "strength": strength,
        "volatility": volatility,
    }

    return signal, data


class GoldBot:

    def __init__(self):
        self.last_signal = None
        self.last_alert_time = None

        self.last_pre_signal = None
        self.last_pre_alert_time = None

        self.last_early_signal = None
        self.last_early_alert_time = None

        self.active_trade = None

    async def tg(self, app, msg):
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)
        await asyncio.sleep(0.2)

    def cooldown_ok(self):
        if self.last_alert_time is None:
            return True

        diff = datetime.now(ZoneInfo("Europe/Rome")) - self.last_alert_time
        return diff.total_seconds() >= COOLDOWN_MINUTES * 60

    def pre_cooldown_ok(self):
        if self.last_pre_alert_time is None:
            return True

        diff = datetime.now(ZoneInfo("Europe/Rome")) - self.last_pre_alert_time
        return diff.total_seconds() >= PRE_COOLDOWN_MINUTES * 60

    def early_cooldown_ok(self):
        if self.last_early_alert_time is None:
            return True

        diff = datetime.now(ZoneInfo("Europe/Rome")) - self.last_early_alert_time
        return diff.total_seconds() >= EARLY_COOLDOWN_MINUTES * 60

    async def send_early_alert(self, app, signal, data):
        price = data["price"]
        atr = data["atr"]

        if signal == "EARLY_LONG":
            title = "⚡ EARLY LONG MOMENTUM XAUUSD"
            tp1 = price + atr * 0.8
            tp2 = price + atr * 1.5
            sl = price - atr * 0.7
            direction = "Momentum rialzista in accelerazione."
        else:
            title = "⚡ EARLY SHORT MOMENTUM XAUUSD"
            tp1 = price - atr * 0.8
            tp2 = price - atr * 1.5
            sl = price + atr * 0.7
            direction = "Momentum ribassista in accelerazione."

        msg = (
            f"{title}\n\n"
            f"🕒 Ora Italia: {now_italy()}\n"
            f"📌 Simbolo: {SYMBOL}\n"
            f"⏱️ Timeframe: {TIMEFRAME}\n\n"
            f"💰 Entry anticipata: {price:.2f}\n\n"
            f"🎯 TP1 veloce: {tp1:.2f}\n"
            f"🎯 TP2 veloce: {tp2:.2f}\n"
            f"🛑 SL stretto: {sl:.2f}\n\n"
            f"📈 EMA20: {data['ema20']:.2f}\n"
            f"📉 EMA50: {data['ema50']:.2f}\n"
            f"⚡ RSI14: {data['rsi']:.2f}\n"
            f"🚀 RSI slope: {data['rsi_slope']:.2f}\n"
            f"🔥 RSI acceleration: {data['rsi_acceleration']:.2f}\n"
            f"🌪️ ATR14: {data['atr']:.2f}\n"
            f"📊 Trend H1: {data['trend_h1']}\n\n"
            f"🧠 {direction}\n\n"
            f"⚠️ Segnale anticipato: più veloce, ma più rischioso."
        )

        await self.tg(app, msg)

        self.last_early_signal = signal
        self.last_early_alert_time = datetime.now(ZoneInfo("Europe/Rome"))

    async def send_pre_alert(self, app, signal, data):
        atr = data["atr"]
        price = data["price"]

        if signal == "PRE_LONG":
            title = "⚠️ PRE-LONG XAUUSD"
            confirm = f"Possibile LONG se RSI supera {RSI_LONG}."
            tp1 = price + atr * 1.0
            tp2 = price + atr * 1.8
            sl = price - atr * 0.8
        else:
            title = "⚠️ PRE-SHORT XAUUSD"
            confirm = f"Possibile SHORT se RSI scende sotto {RSI_SHORT}."
            tp1 = price - atr * 1.0
            tp2 = price - atr * 1.8
            sl = price + atr * 0.8

        msg = (
            f"{title}\n\n"
            f"🕒 Ora Italia: {now_italy()}\n"
            f"📌 Simbolo: {SYMBOL}\n"
            f"⏱️ Timeframe: {TIMEFRAME}\n\n"
            f"💰 Entry possibile: {price:.2f}\n\n"
            f"🎯 TP1: {tp1:.2f}\n"
            f"🎯 TP2: {tp2:.2f}\n"
            f"🛑 SL: {sl:.2f}\n\n"
            f"📈 EMA20: {data['ema20']:.2f}\n"
            f"📉 EMA50: {data['ema50']:.2f}\n"
            f"⚡ RSI14: {data['rsi']:.2f}\n"
            f"🌪️ ATR14: {data['atr']:.2f}\n"
            f"📊 Trend H1: {data['trend_h1']}\n\n"
            f"🧠 {confirm}\n\n"
            f"⚠️ Allerta anticipata, non conferma definitiva."
        )

        await self.tg(app, msg)

        self.last_pre_signal = signal
        self.last_pre_alert_time = datetime.now(ZoneInfo("Europe/Rome"))

    async def open_trade(self, app, data):
        msg = (
            f"{data['title']} | Forza {data['strength']}\n\n"
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
            f"🧠 Motivo:\n{data['reason']}\n\n"
            f"⚠️ Segnale tecnico."
        )

        await self.tg(app, msg)

        self.active_trade = {
            **data,
            "tp1_hit": False,
            "tp2_hit": False,
            "sl_hit": False,
        }

    async def track_trade(self, app, current_price):
        if self.active_trade is None:
            return

        t = self.active_trade

        if t["signal"] == "LONG":
            if not t["tp1_hit"] and current_price >= t["tp1"]:
                t["tp1_hit"] = True
                await self.tg(app, f"✅ TP1 LONG RAGGIUNTO\n\n💰 Prezzo: {current_price:.2f}")

            if not t["tp2_hit"] and current_price >= t["tp2"]:
                t["tp2_hit"] = True
                await self.tg(app, f"🏆 TP2 LONG RAGGIUNTO\n\n💰 Prezzo: {current_price:.2f}")
                self.active_trade = None

            if not t["sl_hit"] and current_price <= t["sl"]:
                t["sl_hit"] = True
                await self.tg(app, f"🛑 STOP LOSS LONG\n\n💰 Prezzo: {current_price:.2f}")
                self.active_trade = None

        elif t["signal"] == "SHORT":
            if not t["tp1_hit"] and current_price <= t["tp1"]:
                t["tp1_hit"] = True
                await self.tg(app, f"✅ TP1 SHORT RAGGIUNTO\n\n💰 Prezzo: {current_price:.2f}")

            if not t["tp2_hit"] and current_price <= t["tp2"]:
                t["tp2_hit"] = True
                await self.tg(app, f"🏆 TP2 SHORT RAGGIUNTO\n\n💰 Prezzo: {current_price:.2f}")
                self.active_trade = None

            if not t["sl_hit"] and current_price >= t["sl"]:
                t["sl_hit"] = True
                await self.tg(app, f"🛑 STOP LOSS SHORT\n\n💰 Prezzo: {current_price:.2f}")
                self.active_trade = None

    async def check(self, app):
        result = analyze_gold()

        if result is None:
            return

        signal, data = result

        if signal == "NEUTRAL":
            return

        if signal in ["EARLY_LONG", "EARLY_SHORT"]:
            if self.early_cooldown_ok():
                await self.send_early_alert(app, signal, data)
            return

        if signal in ["PRE_LONG", "PRE_SHORT"]:
            if self.pre_cooldown_ok():
                await self.send_pre_alert(app, signal, data)
            return

        if self.active_trade is not None:
            await self.track_trade(app, data["price"])

        if signal != self.last_signal and self.cooldown_ok():
            await self.open_trade(app, data)
            self.last_signal = signal
            self.last_alert_time = datetime.now(ZoneInfo("Europe/Rome"))

    async def start(self, app):
        await self.tg(
            app,
            "🟡 GOLD BOT TRADER PRO v5.4 AVVIATO\n\n"
            f"📌 Simbolo: {SYMBOL}\n"
            f"⏱️ Timeframe: {TIMEFRAME}\n"
            f"📊 Trend filter: {HIGHER_TIMEFRAME}\n"
            f"🔁 Check ogni {LOOP_SEC} sec\n\n"
            "Funzioni:\n"
            "✅ EARLY MOMENTUM ultra anticipato\n"
            "✅ PRE ALERT con Entry / TP / SL\n"
            "✅ LONG / SHORT confermati\n"
            "✅ TP1 / TP2 tracking\n"
            "✅ SL tracking\n\n"
            "⚠️ Non è consulenza finanziaria."
        )


bot = GoldBot()


async def live():
    app = ApplicationBuilder().token(TOKEN).build()

    await bot.start(app)

    while True:
        try:
            await bot.check(app)

        except Exception as ex:
            await bot.tg(app, f"⚠️ Errore BOT:\n{ex}")

        await asyncio.sleep(LOOP_SEC)


asyncio.run(live())
