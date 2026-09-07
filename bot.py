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
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1112225")

# টাইমজোন সেট (বাংলাদেশ সময় UTC+6)
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

# ==================== মার্কেট ডেটা ও টেকনিক্যাল অ্যানালাইজার ====================


def fetch_live_candles(ticker, interval="1m", period="1d"):
    try:
        data = yf.download(
            ticker, interval=interval, period=period, progress=False
        )
        if data.empty or len(data) < 25:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"Data fetch error: {e}")
        return None


def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def analyze_market(df, asset_name):
    if df is None or len(df) < 20:
        return None

    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["RSI"] = calculate_rsi(df["Close"], period=14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    c_open = float(last["Open"])
    c_close = float(last["Close"])
    c_high = float(last["High"])
    c_low = float(last["Low"])
    c_rsi = float(last["RSI"]) if not np.isnan(last["RSI"]) else 50.0
    c_ema9 = float(last["EMA9"])
    c_ema21 = float(last["EMA21"])

    p_open = float(prev["Open"])
    p_close = float(prev["Close"])

    body = abs(c_close - c_open)
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low

    is_uptrend = c_ema9 > c_ema21 and c_close > c_ema9
    is_downtrend = c_ema9 < c_ema21 and c_close < c_ema9

    trend_str = (
        "Bullish (আপট্রেন্ড)"
        if is_uptrend
        else "Bearish (ডাউনট্রেন্ড)"
        if is_downtrend
        else "Consolidation (সাইডওয়েজ)"
    )

    score = 0
    pattern_name = "Normal Candle"
    logic_list = []

    # ১. ক্যান্ডেলস্টিক প্যাটার্ন ও রিজেকশন লজিক
    if lower_wick > body * 1.5 and upper_wick < body * 0.7:
        pattern_name = "Bullish Pinbar / Hammer"
        score += 3
        logic_list.append("সাপোর্ট লেভেলে শক্তিশালী বায়ার্স রিজেকশন ও লোয়ার উইক তৈরি হয়েছে।")
    elif upper_wick > body * 1.5 and lower_wick < body * 0.7:
        pattern_name = "Shooting Star / Bearish Pinbar"
        score -= 3
        logic_list.append("রেজিস্ট্যান্স জোনে সেলারদের তীব্র চাপ ও আপার রিজেকশন রয়েছে।")
    elif (
        p_close < p_open
        and c_close > c_open
        and c_close > p_open
        and c_open <= p_close
    ):
        pattern_name = "Bullish Engulfing"
        score += 3
        logic_list.append("আগের লাল ক্যান্ডেলকে সম্পূর্ণ এনগাল্ফ করে বায়ার্স মোমেন্টাম তৈরি হয়েছে।")
    elif (
        p_close > p_open
        and c_close < c_open
        and c_close < p_open
        and c_open >= p_close
    ):
        pattern_name = "Bearish Engulfing"
        score -= 3
        logic_list.append("আগের সবুজ ক্যান্ডেলকে ব্রেক করে শক্তিশালী বিয়ারিশ ক্যান্ডেল ক্লোজ হয়েছে।")
    elif c_close > c_open and is_uptrend:
        pattern_name = "Bullish Momentum Continuation"
        score += 2
        logic_list.append("মার্কেটে ধারাবাহিক বুলিশ প্রেশার এবং আপট্রেন্ড বজায় রয়েছে।")
    elif c_close < c_open and is_downtrend:
        pattern_name = "Bearish Momentum Continuation"
        score -= 2
        logic_list.append("মার্কেটে ডাউনট্রেন্ড অব্যাহত রয়েছে এবং নতুন লো পয়েন্ট তৈরি হয়েছে।")

    # ২. RSI মোমেন্টাম লজিক
    if c_rsi <= 32:
        score += 2
        logic_list.append(f"RSI ভ্যালু ({c_rsi:.1f}) ওভারসোল্ড জোনে, রিভার্সাল সম্ভাব্য।")
    elif c_rsi >= 68:
        score -= 2
        logic_list.append(f"RSI ভ্যালু ({c_rsi:.1f}) ওভারবট জোনে, ডাউন রিভার্সাল সম্ভাব্য।")
    else:
        logic_list.append(f"RSI ভ্যালু ({c_rsi:.1f}) মোমেন্টাম সাপোর্ট করছে।")

    # ৩. মুভিং এভারেজ লজিক
    if is_uptrend:
        score += 2
        logic_list.append("EMA ৯ ও ২১ রেখা অনুযায়ী প্রাইস স্পষ্ট আপট্রেন্ডে।")
    elif is_downtrend:
        score -= 2
        logic_list.append("EMA ৯ ও ২১ রেখা অনুযায়ী প্রাইস ডাউনট্রেন্ড কনফার্ম করেছে।")

    # সিদ্ধান্ত গ্রহণ
    if score >= 4:
        decision = "CALL"
        confidence = min(93, 75 + (score * 3))
    elif score <= -4:
        decision = "PUT"
        confidence = min(93, 75 + (abs(score) * 3))
    else:
        decision = "WAIT"
        confidence = 50
        logic_list.append("মার্কেট রেঞ্জিং বা অনিশ্চিত অবস্থায় থাকায় এন্ট্রি নেওয়া ঝুঁকিপূর্ণ।")

    # পরবর্তী ক্যান্ডেলের নিখুঁত এন্ট্রি ও এক্সপায়ারি সময় নির্ধারণ
    now = datetime.now(TIMEZONE)
    # পরবর্তী পুরো মিনিটের শুরু (যেমন: ১০:০৫:০০)
    next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    expiry_minute = next_minute + timedelta(minutes=1)

    return {
        "decision": decision,
        "confidence": confidence,
        "price": c_close,
        "rsi": c_rsi,
        "trend": trend_str,
        "pattern": pattern_name,
        "logics": logic_list,
        "entry_time": next_minute.strftime("%I:%M:%S %p"),
        "expiry_time": expiry_minute.strftime("%I:%M:%S %p"),
        "current_time": now.strftime("%I:%M:%S %p"),
    }


# ==================== টেলিগ্রাম হ্যান্ডলার ====================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *AI Live Market Price Action Signal Bot*\n\n"
        "🔹 /setpair - কারেন্সি বা ক্রিপ্টো পেয়ার নির্বাচন করুন\n"
        "🔹 /signal - নির্বাচিত পেয়ারের পূর্ণাঙ্গ সাজানো সিগন্যাল কার্ড দেখুন\n"
        "🔹 /pairs - সব সচল পেয়ারের তালিকা দেখুন\n"
        "🔹 /help - ব্যবহার নির্দেশিকা",
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
        f"📊 *মার্কেট পেয়ার নির্বাচন করুন:*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 বর্তমান পেয়ার: *{current_name}*\n\n"
        f"নিচের বাটন থেকে আপনার পছন্দের পেয়ারটি সিলেক্ট করুন:",
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
        f"✅ *পেয়ার সফলভাবে সিলেক্ট করা হয়েছে!*\n\n"
        f"🪙 সক্রিয় পেয়ার: *{pair_name}*\n\n"
        f"এখন বিস্তারিত এনালাইসিস পেতে /signal চাপুন।",
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
        f"🔍 *{pair_name}* এর চার্ট ও টেকনিক্যাল কনফ্লুয়েন্স প্রসেস করা হচ্ছে..."
    )

    df = fetch_live_candles(ticker, interval="1m", period="1d")
    if df is None:
        await wait_msg.edit_text(
            f"❌ *{pair_name}*-এর লাইভ মার্কেট ডেটা আনা সম্ভব হয়নি। অনুগ্রহ করে আবার চেষ্টা করুন।"
        )
        return

    res = analyze_market(df, pair_name)
    if not res:
        await wait_msg.edit_text("❌ অ্যানালাইসিস সম্পন্ন করা যায়নি।")
        return

    # সিগন্যাল ব্যাজ ফরম্যাটিং
    if res["decision"] == "CALL":
        action_text = "🟢 **CALL / BUY (UP)** ⬆️"
    elif res["decision"] == "PUT":
        action_text = "🔴 **PUT / SELL (DOWN)** ⬇️"
    else:
        action_text = "⚪ **WAIT (অপেক্ষা করুন)** ⏸"

    price_format = (
        f"{res['price']:.2f}"
        if "BTC" in pair_key or "ETH" in pair_key
        else f"{res['price']:.5f}"
    )

    # লজিক পয়েন্টগুলোকে পয়েন্ট আকারে সাজানো
    logics_formatted = "\n".join(
        [f"  • {item}" for item in res["logics"]]
    )

    # পূর্ণাঙ্গ সাজানো সিগন্যাল মেসেজ
    signal_card = (
        f"╔══════════════════════╗\n"
        f"║   📊 **AI LIVE TRADING SIGNAL**   ║\n"
        f"╚══════════════════════╝\n\n"
        f"🪙 **পেয়ার:** `{pair_name}`\n"
        f"💰 **বর্তমান প্রাইস:** `{price_format}`\n"
        f"📈 **মার্কেট ট্রেন্ড:** `{res['trend']}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **ট্রেড ডিরেকশন:** {action_text}\n"
        f"⏰ **এন্ট্রি সময়:** `{res['entry_time']}` *(ক্যান্ডেল ওপেনিংয়ে)*\n"
        f"⏳ **ট্রেড ডিউরেশন:** `1 Minute (60s)`\n"
        f"🏁 **এক্সপায়ারি সময়:** `{res['expiry_time']}`\n"
        f"🎯 **কনফিডেন্স:** `{res['confidence']}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🧠 **ট্রেড নেওয়ার সুনির্দিষ্ট কারণ ও লজিক:**\n"
        f"🕯 **ক্যান্ডেল প্যাটার্ন:** `{res['pattern']}`\n"
        f"📊 **RSI স্ট্যাটাস:** `{res['rsi']:.1f}`\n"
        f"{logics_formatted}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *টিপস: সঠিক সময়ে ক্যান্ডেল ওপেন হওয়ার প্রথম ৩ সেকেন্ডের মধ্যে এন্ট্রি নিন।*"
    )

    await wait_msg.edit_text(signal_card, parse_mode="Markdown")


async def pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📋 *সকল সচল পেয়ারের তালিকা:*\n━━━━━━━━━━━━━━━━━━\n"
    for k, v in AVAILABLE_PAIRS.items():
        msg += f"• `{v['name']}`\n"
    msg += "\nপছন্দের পেয়ার সেট করতে /setpair কমান্ড ব্যবহার করুন।"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpair", setpair))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("pairs", pairs))
    app.add_handler(CommandHandler("help", start))

    app.add_handler(CallbackQueryHandler(pair_callback, pattern="^pair:"))

    print("🚀 Live Signal Bot running with full structured details...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Bot Stopped.")
