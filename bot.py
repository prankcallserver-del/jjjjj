import asyncio
from datetime import datetime, timedelta
import os
import sys
import numpy as np
import pandas as pd
import pytz
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import yfinance as yf

# ==================== 🔑 কনফিগারেশন ও ডেভেলপার ইনফো ====================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", "8942863443:AAFch9vDKsEqMfE3X_Ze9wjFPxH9bTzc0WI"
)
TIMEZONE = pytz.timezone("Asia/Dhaka")

# ডেভেলপার তথ্য
DEV_NAME = "NOOBXVAU"
DEV_USERNAME = "noobxvau"
DEV_LINK = "https://t.me/noobxvau"

# 📢 ফোর্স জয়েন চ্যানেল তালিকা (পাবলিক ও প্রাইভেট চ্যানেল কনফিগারেশন)
# বটকে অবশ্যই এই চ্যানেলগুলোতে Admin থাকতে হবে!
REQUIRED_CHANNELS = [
    {
        "name": "📢 Official Channel (Public)",
        "chat_id": "-1002990965609",  # পাবলিক চ্যানেলের ইউজারনেম বা আইডি
        "link": "https://t.me/+ENYrQ5N9WNE3NWQ9",  # চ্যানেল লিংক
    },
    # {
    #     "name": "🔒 VIP Signal Channel (Private)",
    #     "chat_id": -1001234567890,  # প্রাইভেট চ্যানেলের -100 দিয়ে শুরু হওয়া আইডি
    #     "link": "https://t.me/+AbCdEfGhIjK12345"  # প্রাইভেট চ্যানেলের ইনভাইট লিংক
    # }
]

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

# ==================== 📱 স্থায়ী মেনু কিবোর্ড (Permanent Keyboard) ====================

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton("📊 Live Signal"),
            KeyboardButton("⚡ Market Scanner"),
        ],
        [KeyboardButton("🎯 Change Pair"), KeyboardButton("📋 All Pairs")],
        [KeyboardButton("👨‍💻 Contact Developer")],
    ],
    resize_keyboard=True,
)

# ==================== 🔒 ফোর্স জয়েন ভেরিফিকেশন ইঞ্জিন ====================


async def check_user_joined_all(
    bot, user_id: int
) -> tuple[bool, list[dict]]:
    """ইউজার সকল বাধ্যতামূলক চ্যানেলে জয়েন আছে কিনা যাচাই করে"""
    not_joined = []

    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(
                chat_id=ch["chat_id"], user_id=user_id
            )
            if member.status in ["left", "kicked"]:
                not_joined.append(ch)
        except (BadRequest, TelegramError):
            # বট অ্যাডমিন না থাকলে বা ভেরিফাই করতে না পারলে জয়েন রিকোয়েস্ট পাঠাবে
            not_joined.append(ch)

    return (len(not_joined) == 0, not_joined)


def build_force_join_keyboard(unjoined_channels: list[dict]):
    """ফোর্স জয়েন বাটন এবং ভেরিফিকেশন বাটন তৈরি করে"""
    buttons = []
    for ch in unjoined_channels:
        buttons.append([InlineKeyboardButton(f"➕ {ch['name']}", url=ch["link"])])
    buttons.append(
        [
            InlineKeyboardButton(
                "✅ Check / Verify Joined", callback_data="check_subscription"
            )
        ]
    )
    return InlineKeyboardMarkup(buttons)


async def enforce_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """সকল কমান্ড ও বাটনের পূর্বে সাবস্ক্রিপশন চেক করার গার্ড"""
    user_id = update.effective_user.id
    is_joined, unjoined = await check_user_joined_all(context.bot, user_id)

    if not is_joined:
        text = (
            "⚠️ **বটটি ব্যবহার করতে আমাদের চ্যানেলে জয়েন থাকা বাধ্যতামূলক!**\n\n"
            "নিচের চ্যানেলগুলোতে জয়েন করে **'✅ Check / Verify Joined'** বাটনে চাপ দিন:"
        )
        if update.callback_query:
            await update.callback_query.message.reply_text(
                text,
                reply_markup=build_force_join_keyboard(unjoined),
                parse_mode="Markdown",
            )
        elif update.message:
            await update.message.reply_text(
                text,
                reply_markup=build_force_join_keyboard(unjoined),
                parse_mode="Markdown",
            )
        return False
    return True


# ==================== টেকনিক্যাল অ্যানালাইসিস ইঞ্জিন ====================


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
    if df is None or len(df) < 15:
        return None

    df["EMA7"] = df["Close"].ewm(span=7, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["RSI"] = calculate_rsi(df["Close"], period=14)

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
    lower_bb = (
        float(last["LowerBB"])
        if not np.isnan(last["LowerBB"])
        else c_low - 0.001
    )
    upper_bb = (
        float(last["UpperBB"])
        if not np.isnan(last["UpperBB"])
        else c_high + 0.001
    )

    body = abs(c_close - c_open)
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low

    is_uptrend = c_ema7 > c_ema21
    is_downtrend = c_ema7 < c_ema21

    score = 0
    pattern_name = "Price Action Setup"
    logics = []

    if c_low <= lower_bb or lower_wick > body * 1.2:
        score += 3
        pattern_name = "Lower Support Rejection"
        logics.append("লোয়ার ব্যান্ড/সাপোর্টে শক্তিশালী বায়ার্স রিজেকশন তৈরি হয়েছে")
    elif c_high >= upper_bb or upper_wick > body * 1.2:
        score -= 3
        pattern_name = "Upper Resistance Rejection"
        logics.append("আপার ব্যান্ড/রেজিস্ট্যান্সে সেলারদের স্ট্রং রিজেকশন রয়েছে")

    if c_close > c_open and p_close < p_open and c_close >= p_open:
        score += 2
        pattern_name = "Bullish Engulfing / Reversal"
        logics.append("বুলিশ এনগাল্ফিং ক্যান্ডেল দিয়ে বায়ারদের প্রবেশ ঘটেছে")
    elif c_close < c_open and p_close > p_open and c_close <= p_open:
        score -= 2
        pattern_name = "Bearish Engulfing / Reversal"
        logics.append("বিয়ারিশ ক্যান্ডেল দিয়ে শক্তিশালী সেলিং প্রেসার তৈরি হয়েছে")

    if c_rsi < 40:
        score += 2
        logics.append(f"RSI ({c_rsi:.1f}) রিভার্সাল জোনের কাছাকাছি")
    elif c_rsi > 60:
        score -= 2
        logics.append(f"RSI ({c_rsi:.1f}) ওভারবট জোনের কাছাকাছি")

    if is_uptrend and c_close > c_open:
        score += 1
        logics.append("EMA ৭ ও ২১ অনুযায়ী আপট্রেন্ড মোমেন্টাম সক্রিয়")
    elif is_downtrend and c_close < c_open:
        score -= 1
        logics.append("EMA ৭ ও ২১ অনুযায়ী ডাউনট্রেন্ড মোমেন্টাম সক্রিয়")

    if score >= 2:
        decision = "CALL"
        confidence = min(94, 75 + (score * 3))
    elif score <= -2:
        decision = "PUT"
        confidence = min(94, 75 + (abs(score) * 3))
    else:
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


# ==================== বট হ্যান্ডলার ও বাটন একশন ====================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, context):
        return

    welcome_msg = (
        "👋 **স্বাগতম AI Live Market Signal Bot-এ!**\n\n"
        "নিচের স্থায়ী মেনু বাটনগুলো ব্যবহার করে সরাসরি সিগন্যাল এবং মার্কেট স্ক্যানিং করুন।\n\n"
        "🎯 **ফিচারসমূহ:**\n"
        "• 📊 **Live Signal:** নির্বাচিত পেয়ারের লাইভ সিগন্যাল ও বিশ্লেষণ\n"
        "• ⚡ **Market Scanner:** সব পেয়ার স্ক্যান করে সেরা এন্ট্রি পয়েন্ট\n"
        "• 🎯 **Change Pair:** পছন্দের কারেন্সি পেয়ার পরিবর্তন\n"
        "• 👨‍💻 **Contact Developer:** ডেভেলপারের সাথে যোগাযোগ"
    )
    await update.message.reply_text(
        welcome_msg, reply_markup=MAIN_MENU_KEYBOARD, parse_mode="Markdown"
    )


async def show_developer_info(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not await enforce_subscription(update, context):
        return

    dev_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Send Message", url=DEV_LINK)]]
    )

    dev_msg = (
        "╔══════════════════════╗\n"
        "║   👨‍💻 **DEVELOPER INFORMATION**   ║\n"
        "╚══════════════════════╝\n\n"
        f"👑 **Developer Name:** `{DEV_NAME}`\n"
        f"✈️ **Telegram Handle:** @{DEV_USERNAME}\n"
        f"🛠 **System Support:** 24/7 Available\n\n"
        "বটের যেকোনো সহায়তা, কাস্টমাইজেশন বা বাগ রিপোর্টের জন্য সরাসরি নিচের বাটনে যোগাযোগ করুন:"
    )
    await update.message.reply_text(
        dev_msg, reply_markup=dev_keyboard, parse_mode="Markdown"
    )


async def setpair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, context):
        return

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
        f"এখন মেনু থেকে **📊 Live Signal** বাটন চাপুন।",
        parse_mode="Markdown",
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, context):
        return

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
            f"❌ *{pair_name}*-এর লাইভ ডেটা আনা যায়নি। অন্য পেয়ার ব্যবহার করুন।"
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
        f"💡 *টিপস: ক্যান্ডেল শুরু হওয়ার সাথে সাথে ১ম ৩ সেকেন্ডের মধ্যে এন্ট্রি নিন।*"
    )

    await wait_msg.edit_text(signal_card, parse_mode="Markdown")


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, context):
        return

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
        await wait_msg.edit_text("❌ এই মুহূর্তে ডেটা পাওয়া যায়নি।")
        return

    valid_signals.sort(key=lambda x: x[1]["confidence"], reverse=True)

    scan_msg = "🔥 **লাইভ মার্কেট সেরা ট্রেড সিগন্যালসমূহ:**\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for name, s in valid_signals[:5]:
        icon = "🟢 CALL" if s["decision"] == "CALL" else "🔴 PUT"
        scan_msg += (
            f"🪙 *{name}* ➔ {icon} (`{s['confidence']}%`)\n"
            f"⏰ এন্ট্রি: `{s['entry_time']}` | RSI: `{s['rsi']:.1f}`\n"
            f"💡 লজিক: _{s['logics'][0]}_\n"
            f"─────────────────────\n"
        )

    scan_msg += "\n👉 মেনুর **🎯 Change Pair** থেকে পেয়ার সিলেক্ট করে বিস্তারিত দেখতে পারেন।"
    await wait_msg.edit_text(scan_msg, parse_mode="Markdown")


async def pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, context):
        return

    msg = "📋 *সক্রিয় পেয়ার তালিকা:*\n━━━━━━━━━━━━━━━━━━━━━\n"
    for k, v in AVAILABLE_PAIRS.items():
        msg += f"• `{v['name']}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


# ==================== ভেরিফাই বাটন ও টেক্সট রাউটিং ====================


async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ভেরিফিকেশন বাটনে ক্লিক করলে সাবস্ক্রিপশন পুনরায় চেক করা"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    is_joined, unjoined = await check_user_joined_all(context.bot, user_id)

    if is_joined:
        await query.message.delete()
        await query.message.reply_text(
            "🎉 **ধন্যবাদ! ভেরিফিকেশন সফল হয়েছে।**\n\n"
            "এখন নিচের মেনু বাটন ব্যবহার করে বটটি ব্যবহার করতে পারেন:",
            reply_markup=MAIN_MENU_KEYBOARD,
            parse_mode="Markdown",
        )
    else:
        await query.message.reply_text(
            "❌ **আপনি এখনও সবকটি চ্যানেলে জয়েন করেননি!**\n"
            "দয়া করে সবগুলোতে জয়েন করে আবার ভেরিফাই করুন।",
            reply_markup=build_force_join_keyboard(unjoined),
            parse_mode="Markdown",
        )


async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """পার্মানেন্ট কিবোর্ডের বাটন ক্লিকের মেসেজ হ্যান্ডলার"""
    text = update.message.text

    if text == "📊 Live Signal":
        await signal(update, context)
    elif text == "⚡ Market Scanner":
        await scan(update, context)
    elif text == "🎯 Change Pair":
        await setpair(update, context)
    elif text == "📋 All Pairs":
        await pairs(update, context)
    elif text == "👨‍💻 Contact Developer":
        await show_developer_info(update, context)


# ==================== মেইন এন্ট্রি পয়েন্ট ====================


async def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # কমান্ড হ্যান্ডলার
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("setpair", setpair))
    app.add_handler(CommandHandler("pairs", pairs))
    app.add_handler(CommandHandler("developer", show_developer_info))

    # বাটন ও টেক্সট হ্যান্ডলার
    app.add_handler(CallbackQueryHandler(pair_callback, pattern="^pair:"))
    app.add_handler(
        CallbackQueryHandler(verify_callback, pattern="^check_subscription$")
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text)
    )

    print("🚀 Bot is running with Permanent Keyboard & Force-Join Guard...")

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
