import asyncio
from datetime import datetime, timedelta
import os
import sys
import numpy as np
import pandas as pd
import pytz
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
import yfinance as yf

# ==================== 🔑 কনফিগারেশন ====================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", "8942863443:AAFch9vDKsEqMfE3X_Ze9wjFPxH9bTzc0WI"
)
TIMEZONE = pytz.timezone("Asia/Dhaka")

AVAILABLE_PAIRS = {
    "EURUSD": {"name": "EUR/USD", "ticker": "EURUSD=X"},
    "GBPUSD": {"name": "GBP/USD", "ticker": "GBPUSD=X"},
    "USDJPY": {"name": "USD/JPY", "ticker": "USDJPY=X"},
    "AUDUSD": {"name": "AUD/USD", "ticker": "AUDUSD=X"},
    "USDCAD": {"name": "USD/CAD", "ticker": "USDCAD=X"},
    "EURGBP": {"name": "EUR/GBP", "ticker": "EURGBP=X"},
    "GBPJPY": {"name": "GBP/JPY", "ticker": "GBPJPY=X"},
    "EURJPY": {"name": "EUR/JPY", "ticker": "EURJPY=X"},
    "BTCUSD": {"name": "BTC/USD (Crypto)", "ticker": "BTC-USD"},
    "ETHUSD": {"name": "ETH/USD (Crypto)", "ticker": "ETH-USD"},
}

DEFAULT_ASSET_KEY = "EURUSD"
user_selected_pair = {}

# ==================== হাই-অ্যাকিউরেসি টেকনিক্যাল ইঞ্জিন ====================


def fetch_live_candles(ticker, interval="1m", period="1d"):
    try:
        data = yf.download(
            ticker, interval=interval, period=period, progress=False
        )
        if data.empty or len(data) < 20:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        df = data[["Open", "High", "Low", "Close"]].copy()
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"Fetch error: {e}")
        return None


def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def analyze_market_optimized(df, asset_name):
    """উন্নত প্রাইস অ্যাকশন + Bollinger Bands + RSI + EMA কনফ্লুয়েন্স"""
    if df is None or len(df) < 15:
        return None

    # ইন্ডিকেটর ক্যালকুলেশন
    df["EMA7"] = df["Close"].ewm(span=7, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["RSI"] = calculate_rsi(df["Close"], period=14)

    # Bollinger Bands (20, 2)
    df["SMA20"] = df["Close"].rolling(window=20).mean()
    df["STD20"] = df["Close"].rolling(window=20).std()
    df["UpperBB"] = df["SMA20"] + (df["STD20"] * 2)
    df["LowerBB"] = df["SMA20"] - (df["STD20"] * 2)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    c_open, c_close, c_high, c_low = (
        float(last["Open"]),
        float(last["Close"]),
        float(last["High"]),
        float(last["Low"]),
    )
    p_open, p_close = float(prev["Open"]), float(prev["Close"])

    c_rsi = float(last["RSI"]) if not np.isnan(last["RSI"]) else 50.0
    c_ema7, c_ema21 = float(last["EMA7"]), float(last["EMA21"])
    lower_bb, upper_bb = (
        float(last["LowerBB"])
        if not np.isnan(last["LowerBB"])
        else c_low - 0.001,
        (
            float(last["UpperBB"])
            if not np.isnan(last["UpperBB"])
            else c_high + 0.001
        ),
    )

    body = abs(c_close - c_open)
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low

    is_uptrend = c_ema7 > c_ema21
    is_downtrend = c_ema7 < c_ema21

    score = 0
    pattern_name = "Price Action Setup"
    logics = []

    # ১. বলিংগার ব্যান্ড ও প্রাইস রিজেকশন (হাই প্রোবাবিলিটি)
    if c_low <= lower_bb or lower_wick > body * 1.2:
        score += 3
        pattern_name = "Lower Support Rejection"
        logics.append("লোয়ার ব্যান্ড/সাপোর্টে বায়ার্স রিজেকশন তৈরি হয়েছে")
    elif c_high >= upper_bb or upper_wick > body * 1.2:
        score -= 3
        pattern_name = "Upper Resistance Rejection"
        logics.append("আপার ব্যান্ড/রেজিস্ট্যান্সে সেলারদের স্ট্রং রিজেকশন রয়েছে")

    # ২. ক্যান্ডেলস্টিক ব্রেকআউট ও এনগাল্ফিং
    if c_close > c_open and p_close < p_open and c_close >= p_open:
        score += 2
        pattern_name = "Bullish Engulfing / Reversal"
        logics.append("বুলিশ এনগাল্ফিং ক্যান্ডেল দিয়ে বায়ারদের প্রবেশ ঘটেছে")
    elif c_close < c_open and p_close > p_open and c_close <= p_open:
        score -= 2
        pattern_name = "Bearish Engulfing / Reversal"
        logics.append("বিয়ারিশ ক্যান্ডেল দিয়ে শক্তিশালী সেলিং প্রেসার তৈরি হয়েছে")

    # ৩. আরএসআই মোমেন্টাম ফিল্টার
    if c_rsi < 40:
        score += 2
        logics.append(f"RSI ({c_rsi:.1f}) রিভার্সাল জোনের কাছাকাছি")
    elif c_rsi > 60:
        score -= 2
        logics.append(f"RSI ({c_rsi:.1f}) ওভারবট জোনের কাছাকাছি")

    # ৪. ট্রেন্ড নিশ্চিতকরণ
    if is_uptrend and c_close > c_open:
        score += 1
        logics.append("EMA ৭ ও ২১ অনুযায়ী আপট্রেন্ড মোমেন্টাম বহাল আছে")
    elif is_downtrend and c_close < c_open:
        score -= 1
        logics.append("EMA ৭ ও ২১ অনুযায়ী ডাউনট্রেন্ড মোমেন্টাম সক্রিয়")

    # ৫. সিদ্ধান্ত (অপ্টিমাইজড থ্রেশহোল্ড)
    if score >= 2:
        decision = "CALL"
        confidence = min(94, 75 + (score * 3))
    elif score <= -2:
        decision = "PUT"
        confidence = min(94, 75 + (abs(score) * 3))
    else:
        # টাই হলে শেষ ক্যান্ডেলের ধারাবাহিকতা বিবেচনা
        if c_close > c_open:
            decision = "CALL"
            confidence = 72
            logics.append("স্বল্পমেয়াদী বুলিশ বাউন্স তৈরি হয়েছে")
        else:
            decision = "PUT"
            confidence = 72
            logics.append("স্বল্পমেয়াদী বিয়ারিশ প্রেসার সক্রিয়")

    now = datetime.now(TIMEZONE)
    next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    expiry_minute = next_minute + timedelta(minutes=1)

    trend_str = (
        "Bullish (আপট্রেন্ড)"
        if is_uptrend
        else "Bearish (ডাউনট্রেন্ড)"
        if is_downtrend
        else "Consolidation"
    )

    return {
        "decision": decision,
        "confidence": confidence,
        "price": c_close,
        "rsi": c_rsi,
        "trend": trend_str,
        "pattern": pattern_name,
        "logics": logics,
        "entry_time": next_minute.strftime("%I:%M:%S %p"),
        "expiry_time": expiry_minute.strftime("%I:%M:%S %p"),
    }


# ==================== টেলিগ্রাম হ্যান্ডলার ====================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *AI Live Market Signal Bot Pro*\n\n"
        "🔹 /signal - নির্বাচিত পেয়ারের লাইভ সিগন্যাল দেখুন\n"
        "🔹 /scan - 🔥 *সব পেয়ার স্ক্যান করে এই মুহূর্তের সেরা ভ্যালিড সিগন্যালগুলো খুঁজুন*\n"
        "🔹 /setpair - পেয়ার পরিবর্তন করুন\n"
        "🔹 /pairs - সব পেয়ারের তালিকা",
        parse_mode="Markdown",
    )


async def setpair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    pairs_list = list(AVAILABLE_PAIRS.items())

    for i in range(0, len(pairs_list), 2):
        row = []
        k1, v1 = pairs_list[i]
        row.append(
            InlineKeyboardButton(f"🪙 {v1['name']}", callback_data=f"pair:{k1}")
        )
        if i + 1 < len(pairs_list):
            k2, v2 = pairs_list[i + 1]
            row.append(
                InlineKeyboardButton(
                    f"🪙 {v2['name']}", callback_data=f"pair:{k2}"
                )
            )
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    current_key = user_selected_pair.get(
        update.effective_user.id, DEFAULT_ASSET_KEY
    )
    current_name = AVAILABLE_PAIRS[current_key]["name"]

    await update.message.reply_text(
        f"🎯 বর্তমান নির্বাচিত পেয়ার: *{current_name}*\n\n"
        f"নিচের বাটন থেকে নতুন পেয়ার বেছে নিন:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def pair_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pair_key = query.data.split(":")[1]
    user_selected_pair[query.from_user.id] = pair_key
    pair_name = AVAILABLE_PAIRS[pair_key]["name"]

    await query.edit_message_text(
        f"✅ সক্রিয় পেয়ার: *{pair_name}*\n\n"
        f"এখন সিগন্যাল পেতে /signal বা সব পেয়ার স্ক্যান করতে /scan কমান্ড দিন।",
        parse_mode="Markdown",
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pair_key = user_selected_pair.get(
        update.effective_user.id, DEFAULT_ASSET_KEY
    )
    pair_info = AVAILABLE_PAIRS[pair_key]
    pair_name = pair_info["name"]
    ticker = pair_info["ticker"]

    wait_msg = await update.message.reply_text(
        f"🔍 *{pair_name}* চার্ট ও কনফ্লুয়েন্স প্রসেস করা হচ্ছে..."
    )

    df = fetch_live_candles(ticker, interval="1m", period="1d")
    if df is None:
        await wait_msg.edit_text(
            f"❌ *{pair_name}*-এর লাইভ মার্কেট ডেটা লোড হতে পারেনি। /scan দিয়ে অন্য পেয়ার দেখুন।"
        )
        return

    res = analyze_market_optimized(df, pair_name)
    if not res:
        await wait_msg.edit_text("❌ ডেটা প্রসেসিং সমস্যা।")
        return

    action_text = (
        "🟢 **CALL / BUY (UP)** ⬆️"
        if res["decision"] == "CALL"
        else "🔴 **PUT / SELL (DOWN)** ⬇️"
    )
    price_format = (
        f"{res['price']:.2f}"
        if "BTC" in pair_key or "ETH" in pair_key
        else f"{res['price']:.5f}"
    )
    logics_formatted = "\n".join([f"  • {item}" for item in res["logics"]])

    signal_card = (
        f"╔══════════════════════╗\n"
        f"║   📊 **AI LIVE TRADING SIGNAL**   ║\n"
        f"╚══════════════════════╝\n\n"
        f"🪙 **পেয়ার:** `{pair_name}`\n"
        f"💰 **বর্তমান প্রাইস:** `{price_format}`\n"
        f"📈 **মার্কেট ট্রেন্ড:** `{res['trend']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **ট্রেড সিগন্যাল:** {action_text}\n"
        f"⏰ **এন্ট্রি সময়:** `{res['entry_time']}`\n"
        f"⏳ **ডিউরেশন:** `1 Minute (60s)`\n"
        f"🏁 **এক্সপায়ারি সময়:** `{res['expiry_time']}`\n"
        f"🎯 **কনফিডেন্স:** `{res['confidence']}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🧠 **ট্রেড নেওয়ার সুনির্দিষ্ট লজিক:**\n"
        f"🕯 **প্যাটার্ন:** `{res['pattern']}`\n"
        f"📊 **RSI:** `{res['rsi']:.1f}`\n"
        f"{logics_formatted}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *টিপস: সঠিক সেকেন্ডে ক্যান্ডেল শুরু হওয়ার সাথে সাথে এন্ট্রি নিন।*"
    )

    await wait_msg.edit_text(signal_card, parse_mode="Markdown")


# ==================== 🔥 মাল্টি-মার্কেট স্ক্যানার ====================
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """একসাথে সব পেয়ার স্ক্যান করে সেরা ভ্যালিড সিগন্যালগুলো বের করে"""
    wait_msg = await update.message.reply_text(
        "⚡ *সমস্ত ফরেক্স ও ক্রিপ্টো পেয়ার স্ক্যান করা হচ্ছে...*"
    )

    valid_signals = []

    for key, info in AVAILABLE_PAIRS.items():
        df = fetch_live_candles(info["ticker"], interval="1m", period="1d")
        if df is not None:
            res = analyze_market_optimized(df, info["name"])
            if res:
                valid_signals.append((info["name"], res))

    if not valid_signals:
        await wait_msg.edit_text("❌ এই মুহূর্তে কোনো পেয়ারে ডেটা পাওয়া যায়নি।")
        return

    # কনফিডেন্স অনুযায়ী সাজানো
    valid_signals.sort(key=lambda x: x[1]["confidence"], reverse=True)

    scan_msg = "🔥 **লাইভ মার্কেট সেরা ট্রেড সিগন্যালসমূহ:**\n━━━━━━━━━━━━━━━━━━━━━\n\n"

    for name, s in valid_signals[:5]:  # সেরা ৫টি পেয়ার দেখানো
        icon = "🟢 CALL" if s["decision"] == "CALL" else "🔴 PUT"
        scan_msg += (
            f"🪙 *{name}* ➔ {icon} (`{s['confidence']}%`)\n"
            f"⏰ এন্ট্রি: `{s['entry_time']}` | RSI: `{s['rsi']:.1f}`\n"
            f"💡 লজিক: _{s['logics'][0]}_\n"
            f"─────────────────────\n"
        )

    scan_msg += "\n👉 যেকোনো পেয়ার বিস্তারিত দেখতে `/setpair` থেকে সিলেক্ট করে `/signal` দিন।"
    await wait_msg.edit_text(scan_msg, parse_mode="Markdown")


async def pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📋 *সক্রিয় পেয়ার তালিকা:*\n"
    for k, v in AVAILABLE_PAIRS.items():
        msg += f"• `{v['name']}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpair", setpair))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("pairs", pairs))
    app.add_handler(CommandHandler("help", start))

    app.add_handler(CallbackQueryHandler(pair_callback, pattern="^pair:"))

    print("🚀 Scanner & Signal Bot is Running...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Stopped.")
