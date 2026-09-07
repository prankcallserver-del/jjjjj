import asyncio
from datetime import datetime
import json
import os
import re
import sys
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from pyquotex.stable_api import Quotex

# ==================== 🔑 ক্রেডেনশিয়াল ====================

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL", "servertgrail@gmail.com")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD", "servertgrail@gmail.com")
QUOTEX_IS_DEMO = True  # সবসময় রিয়েল ডেমো অ্যাকাউন্টে ট্রেড হবে

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", "8942863443:AAFch9vDKsEqMfE3X_Ze9wjFPxH9bTzc0WI"
)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1112225")

DEFAULT_ASSET = "EURUSD_otc"
TRADE_AMOUNT = 1.0
TRADE_DURATION = 60
MIN_CONFIDENCE = 70
AUTO_TRADE_ENABLED = True

# =========================================================

engine = QuotexEngine = None


class TradingEngine:

    def __init__(self):
        self.client = Quotex(
            email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD, lang="en"
        )
        self.connected = False
        self.profit_today = 0.0
        self.loss_today = 0.0

    async def connect(self):
        status, msg = await self.client.connect()
        if status:
            self.connected = True
            await self.client.change_account("PRACTICE")
            print("✅ Quotex Live Server Connected (PRACTICE Mode)")
            return True
        return False

    async def get_balance(self):
        return await self.client.get_balance()


trading_engine = TradingEngine()
trade_history = []
user_assets = {}


# ==================== প্রাইস অ্যাকশন ও অ্যানালাইসিস ইঞ্জিন ====================
def analyze_price_action(candles, asset_name):
    if not candles or len(candles) < 3:
        return {
            "decision": "wait",
            "confidence": 50,
            "trend": "Sideways",
            "pattern": "None",
            "analysis": "পর্যাপ্ত মার্কেট ডেটা নেই।",
        }

    last = candles[-1]
    prev = candles[-2]

    c_open, c_close, c_high, c_low = last[1], last[2], last[3], last[4]
    p_open, p_close, p_high, p_low = prev[1], prev[2], prev[3], prev[4]

    body = abs(c_close - c_open)
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low

    closes = [c[2] for c in candles[-6:]]
    is_uptrend = closes[-1] > closes[0]
    is_downtrend = closes[-1] < closes[0]

    trend = (
        "Bullish (আপট্রেন্ড)"
        if is_uptrend
        else "Bearish (ডাউনট্রেন্ড)"
        if is_downtrend
        else "Sideways"
    )

    if lower_wick > body * 1.6 and upper_wick < body * 0.8:
        return {
            "decision": "call",
            "confidence": 85,
            "trend": trend,
            "pattern": "Bullish Pinbar / Hammer",
            "analysis": (
                f"{asset_name}-এ সাপোর্ট লেভেল থেকে স্ট্রং বায়ার্স রিজেকশন"
                " তৈরি হয়েছে। পরবর্তী ১ মিনিটে মার্কেট আপে যাওয়ার সম্ভাবনা"
                " প্রবল।"
            ),
        }
    elif upper_wick > body * 1.6 and lower_wick < body * 0.8:
        return {
            "decision": "put",
            "confidence": 86,
            "trend": trend,
            "pattern": "Shooting Star / Bearish Pinbar",
            "analysis": (
                f"{asset_name}-এ রেজিস্ট্যান্স জোন থেকে সেলারদের শক্তিশালী"
                " ডাউন-পুশ দেখা গেছে।"
            ),
        }
    elif (
        p_close < p_open
        and c_close > c_open
        and c_close > p_open
        and c_open <= p_close
    ):
        return {
            "decision": "call",
            "confidence": 83,
            "trend": trend,
            "pattern": "Bullish Engulfing",
            "analysis": (
                "পূর্ববর্তী বিয়ারিশ ক্যান্ডেলকে সম্পূর্ণ এনগাল্ফ করে বুলিশ"
                " মোমেন্টাম তৈরি হয়েছে।"
            ),
        }
    elif (
        p_close > p_open
        and c_close < c_open
        and c_close < p_open
        and c_open >= p_close
    ):
        return {
            "decision": "put",
            "confidence": 84,
            "trend": trend,
            "pattern": "Bearish Engulfing",
            "analysis": (
                "বুলিশ ক্যান্ডেলকে ব্রেক করে শক্তিশালী বিয়ারিশ এনগাল্ফিং তৈরি"
                " হয়েছে।"
            ),
        }
    elif c_close > c_open and is_uptrend:
        return {
            "decision": "call",
            "confidence": 76,
            "trend": trend,
            "pattern": "Trend Continuation",
            "analysis": (
                "মার্কেটে স্পষ্ট আপট্রেন্ড রয়েছে এবং বায়ারদের ভলিউম বাড়ছে।"
            ),
        }
    elif c_close < c_open and is_downtrend:
        return {
            "decision": "put",
            "confidence": 77,
            "trend": trend,
            "pattern": "Trend Continuation",
            "analysis": (
                "মার্কেটে ডাউনট্রেন্ড অব্যাহত রয়েছে এবং ক্যান্ডেল নতুন লো তৈরি"
                " করেছে।"
            ),
        }
    else:
        return {
            "decision": "wait",
            "confidence": 55,
            "trend": trend,
            "pattern": "Consolidation",
            "analysis": (
                "মার্কেট রেঞ্জিং অবস্থায় আছে। পরিষ্কার রিজেকশন ছাড়া ট্রেড নেওয়া"
                " ঝুঁকিপূর্ণ।"
            ),
        }


# ==================== ট্রেড এক্সিকিউশন ও লাইভ রেজাল্ট ট্র্যাকার ====================
async def execute_and_track_trade(
    bot, chat_id, asset, direction, confidence, reason, amount=TRADE_AMOUNT
):
    """ট্রেড প্লেস করবে এবং ৬০ সেকেন্ড পর সাথে সাথে রেজাল্ট মেসেজ পাঠাবে"""
    status, buy_info = await trading_engine.client.buy(
        amount=amount, asset=asset, direction=direction, duration=TRADE_DURATION
    )

    if not status:
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ *ট্রেড প্লেস ব্যর্থ হয়েছে:* সার্ভার অর্ডার গ্রহণ করেনি।",
            parse_mode="Markdown",
        )
        return

    order_id = buy_info["id"]
    payout = buy_info.get("payout", 85)
    dir_icon = "📈 CALL (UP)" if direction == "call" else "📉 PUT (DOWN)"

    # ১. সাথে সাথে এন্ট্রি মেসেজ
    start_msg = (
        f"🚀 *লাইভ ট্রেড প্লেস করা হয়েছে!*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *পেয়ার:* `{asset}` (Payout: `{payout}%`)\n"
        f"🎯 *ডিরেকশন:* {dir_icon}\n"
        f"💵 *ট্রেড অ্যামাউন্ট:* `${amount:.2f}`\n"
        f"⏱ *ডিউরেশন:* `{TRADE_DURATION}s` (চলমান...)\n"
        f"💡 *লজিক:* _{reason}_\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ *ফলাফলের জন্য অপেক্ষা করুন ({TRADE_DURATION} সেকেন্ড)...*"
    )
    await bot.send_message(
        chat_id=chat_id, text=start_msg, parse_mode="Markdown"
    )

    # ২. ট্রেড এক্সপায়ার হওয়া পর্যন্ত অপেক্ষা এবং রেজাল্ট যাচাই
    profit, result_status = await trading_engine.client.check_win(order_id)
    new_balance = await trading_engine.client.get_balance()

    if result_status == "WIN":
        trading_engine.profit_today += profit
        outcome_badge = "🏆 *RESULT: WIN (লাভ)* 🟢"
        pnl_text = f"`+${profit:.2f}`"
    else:
        trading_engine.loss_today += abs(profit)
        outcome_badge = "💀 *RESULT: LOSS (ক্ষতি)* 🔴"
        pnl_text = f"`-${abs(profit):.2f}`"

    trade_history.append(
        {
            "asset": asset,
            "direction": direction,
            "result": result_status,
            "profit": profit,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
    )

    # ৩. ট্রেড শেষ হওয়ার সাথে সাথে রেজাল্ট মেসেজ পাঠানো
    result_msg = (
        f"📢 *ট্রেড সমাপ্তি নোটিফিকেশন*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{outcome_badge}\n"
        f"🪙 *পেয়ার:* `{asset}`\n"
        f"🎯 *ডিরেকশন:* {dir_icon}\n"
        f"💰 *প্রফিট/লস:* {pnl_text}\n"
        f"💳 *বর্তমান ডেমো ব্যালেন্স:* `${new_balance:.2f}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 আজকের নেট PnL: `+{trading_engine.profit_today - trading_engine.loss_today:.2f}$`"
    )
    await bot.send_message(
        chat_id=chat_id, text=result_msg, parse_mode="Markdown"
    )


# ==================== টেলিগ্রাম কমান্ড হ্যান্ডলার ====================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Quotex Live AI Trading Bot Active*\n\n"
        "🔹 /setpair - লাইভ মার্কেট পেয়ার ও আসল পেআউট (%) দেখে সিলেক্ট করুন\n"
        "🔹 /signal - নির্বাচিত পেয়ারের লাইভ অ্যানালাইসিস দেখুন\n"
        "🔹 /trade - অ্যানালাইসিস অনুযায়ী লাইভ ডেমো ট্রেড নিন\n"
        "🔹 /balance - ডেমো ব্যালেন্স ও আজকের PnL দেখুন\n"
        "🔹 /history - ট্রেড হিস্ট্রি\n"
        "🔹 /status - সার্ভার ও একাউন্ট স্ট্যাটাস",
        parse_mode="Markdown",
    )


async def setpair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কোটেক্সের লাইভ সার্ভার থেকে সরাসরি পেয়ার ও পেআউট রেট আনা"""
    pairs = await trading_engine.client.get_live_assets()

    keyboard = []
    for i in range(0, len(pairs), 2):
        row = []
        p1 = pairs[i]
        row.append(
            InlineKeyboardButton(
                f"🟢 {p1['name']} ({p1['payout']}%)",
                callback_data=f"setpair:{p1['code']}",
            )
        )
        if i + 1 < len(pairs):
            p2 = pairs[i + 1]
            row.append(
                InlineKeyboardButton(
                    f"🟢 {p2['name']} ({p2['payout']}%)",
                    callback_data=f"setpair:{p2['code']}",
                )
            )
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    current = user_assets.get(update.effective_user.id, DEFAULT_ASSET)

    await update.message.reply_text(
        f"📊 *Quotex লাইভ মার্কেট পেয়ার ও পেআউট রেট:*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 বর্তমান সিলেক্টেড পেয়ার: `{current}`\n\n"
        f"ট্রেড করার জন্য নিচের বাটন থেকে পেয়ার পছন্দ করুন:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def pair_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pair_code = query.data.split(":")[1]
    user_assets[query.from_user.id] = pair_code

    pairs = await trading_engine.client.get_live_assets()
    info = next((p for p in pairs if p["code"] == pair_code), None)
    payout = info["payout"] if info else 85
    name = info["name"] if info else pair_code

    await query.edit_message_text(
        f"✅ *সফলভাবে পেয়ার পরিবর্তন করা হয়েছে!*\n\n"
        f"🪙 *পেয়ার:* `{name}`\n"
        f"💰 *লাইভ পেআউট:* `{payout}%`\n\n"
        f"এখন সিগন্যাল পেতে /signal বা ট্রেড করতে /trade কমান্ড দিন।",
        parse_mode="Markdown",
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    wait_msg = await update.message.reply_text(
        f"🔍 *{asset}* চার্ট ও লাইভ ক্যান্ডেল অ্যানালাইজ করা হচ্ছে..."
    )

    candles = await trading_engine.client.get_candles(asset)
    res = analyze_price_action(candles, asset)

    decision = res["decision"]
    confidence = res["confidence"]

    if decision == "call":
        badge = "🟢 *CALL / UP (বাই)* 📈"
    elif decision == "put":
        badge = "🔴 *PUT / DOWN (সেল)* 📉"
    else:
        badge = "⚪ *WAIT (অপেক্ষা করুন)* ⏸"

    _, info = await trading_engine.client.check_asset_open(asset)
    payout = info.get("payout", 85)

    msg = (
        f"📊 *মার্কেট লাইভ সিগন্যাল*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *পেয়ার:* `{asset}` (Payout: `{payout}%`)\n"
        f"🔮 *সিগন্যাল:* {badge}\n"
        f"🎯 *কনফিডেন্স:* `{confidence}%`\n"
        f"📈 *মার্কেট ট্রেন্ড:* `{res['trend']}`\n"
        f"🕯 *ক্যান্ডেল প্যাটার্ন:* `{res['pattern']}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧠 *প্রাইস অ্যাকশন লজিক:*\n"
        f"_{res['analysis']}_\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ ট্রেড ওপেন করতে /trade চাপুন।"
    )
    await wait_msg.edit_text(msg, parse_mode="Markdown")


async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    candles = await trading_engine.client.get_candles(asset)
    res = analyze_price_action(candles, asset)

    decision = res["decision"]
    confidence = res["confidence"]

    if decision not in ["call", "put"] or confidence < MIN_CONFIDENCE:
        await update.message.reply_text(
            f"⏸ *ট্রেড স্কিপ করা হয়েছে!*\n"
            f"সিদ্ধান্ত: `{decision.upper()}` ({confidence}%)\n\n"
            f"💡 *কারণ:* {res['analysis']}\n"
            f"*(ট্রেড নেওয়ার জন্য নূন্যতম {MIN_CONFIDENCE}% কনফিডেন্স প্রয়োজন)*",
            parse_mode="Markdown",
        )
        return

    # ট্রেড নেওয়া এবং শেষ হওয়া পর্যন্ত ব্যাকগ্রাউন্ডে ট্র্যাক করা
    asyncio.create_task(
        execute_and_track_trade(
            context.bot,
            update.effective_chat.id,
            asset,
            decision,
            confidence,
            res["analysis"],
            TRADE_AMOUNT,
        )
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = await trading_engine.get_balance()
    pnl = trading_engine.profit_today - trading_engine.loss_today
    msg = (
        f"💳 *Quotex ডেমো অ্যাকাউন্ট ব্যালেন্স*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *ব্যালেন্স:* `${bal:.2f}`\n"
        f"📈 *আজকের লাভ:* `+${trading_engine.profit_today:.2f}`\n"
        f"📉 *আজকের লস:* `-${trading_engine.loss_today:.2f}`\n"
        f"📊 *মোট PnL:* `{' +' if pnl >= 0 else ''}${pnl:.2f}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not trade_history:
        await update.message.reply_text("এখনও কোনো ট্রেড হিস্ট্রি নেই।")
        return
    msg = "📜 *সর্বশেষ ৫টি লাইভ ট্রেড রেজাল্ট:*\n━━━━━━━━━━━━━━━━━━\n"
    for t in trade_history[-5:]:
        icon = "🟢 WIN" if t["result"] == "WIN" else "🔴 LOSS"
        msg += f"• `{t['time']}` | {icon} | `{t['asset']}` | `{t['profit']:+.2f}$`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = await trading_engine.get_balance()
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    conn_text = "🟢 Live Connected" if trading_engine.connected else "🔴 Offline"
    await update.message.reply_text(
        f"*সিস্টেম স্ট্যাটাস:*\n"
        f"Quotex Server: {conn_text}\n"
        f"মোড: `PRACTICE (Demo)`\n"
        f"সক্রিয় পেয়ার: `{asset}`\n"
        f"লাইভ ব্যালেন্স: `${bal:.2f}`",
        parse_mode="Markdown",
    )


async def auto_trader_loop():
    """স্বয়ংক্রিয়ভাবে মার্কেট দেখে ট্রেড নেওয়া এবং ফলাফল মেসেজ পাঠানো"""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    while True:
        await asyncio.sleep(65)  # প্রতি ট্রেড শেষ হওয়ার পর পরবর্তী ট্রেড চেক
        if not trading_engine.connected or not AUTO_TRADE_ENABLED:
            continue

        asset = DEFAULT_ASSET
        candles = await trading_engine.client.get_candles(asset)
        res = analyze_price_action(candles, asset)

        decision = res["decision"]
        confidence = res["confidence"]

        if decision in ["call", "put"] and confidence >= MIN_CONFIDENCE:
            await execute_and_track_trade(
                bot,
                TELEGRAM_CHAT_ID,
                asset,
                decision,
                confidence,
                res["analysis"],
                TRADE_AMOUNT,
            )


async def main():
    await trading_engine.connect()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpair", setpair))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("trade", trade))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("status", status))

    app.add_handler(CallbackQueryHandler(pair_callback, pattern="^setpair:"))

    asyncio.create_task(auto_trader_loop())
    print("🚀 Quotex Real-Time Tracking Bot is Live...")

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
