import asyncio
from datetime import datetime
import json
import os
import sys
import time
from google import genai
from google.genai import types
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# লোকাল ফাইল পাথ পাইথনে সেট করা
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from pyquotex.stable_api import Quotex

# ==================== 🔑 ক্রেডেনশিয়াল ও কনফিগারেশন ====================

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL", "servertgrail@gmail.com")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD", "servertgrail@gmail.com")
QUOTEX_IS_DEMO = os.getenv("QUOTEX_IS_DEMO", "True").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", "8942863443:AAFch9vDKsEqMfE3X_Ze9wjFPxH9bTzc0WI"
)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1112225")

# এখানে আপনার AI Studio থেকে পাওয়া সঠিক 'AIzaSy...' Key টি বসাবেন
GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY", "AQ.Ab8RN6LA_5wmqYlG7PDeh9eUh0sGipwOwQYXNN25l_c4Q_uhCw"
)

# এভেলেবেল পেয়ারের তালিকা
AVAILABLE_PAIRS = [
    ("EUR/USD (OTC)", "EURUSD_otc"),
    ("GBP/USD (OTC)", "GBPUSD_otc"),
    ("USD/JPY (OTC)", "USDJPY_otc"),
    ("AUD/USD (OTC)", "AUDUSD_otc"),
    ("USD/CAD (OTC)", "USDCAD_otc"),
    ("EUR/GBP (OTC)", "EURGBP_otc"),
    ("NZD/USD (OTC)", "NZDUSD_otc"),
    ("GBP/JPY (OTC)", "GBPJPY_otc"),
    ("EUR/JPY (OTC)", "EURJPY_otc"),
    ("USD/CHF (OTC)", "USDCHF_otc"),
]

DEFAULT_ASSET = "EURUSD_otc"
TRADE_AMOUNT = 1.0
TRADE_DURATION = 60
MIN_CONFIDENCE = 70
AUTO_TRADE_ENABLED = True

# =====================================================================

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


class QuotexEngine:

    def __init__(self):
        self.client = None
        self.connected = False
        self.balance = 0.0
        self.profit_today = 0.0
        self.loss_today = 0.0

    async def connect(self):
        self.client = Quotex(
            email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD, lang="en"
        )
        check_connect, message = await self.client.connect()
        if not check_connect:
            print(f"❌ Connection failed: {message}")
            return False

        self.connected = True
        print("✅ Quotex Connected")

        if QUOTEX_IS_DEMO:
            await self.client.change_account("PRACTICE")
        else:
            await self.client.change_account("REAL")

        await self.update_balance()
        return True

    async def update_balance(self):
        if self.client and self.connected:
            try:
                bal = await self.client.get_balance()
                if bal is not None:
                    self.balance = float(bal)
            except Exception as e:
                print(f"Balance error: {e}")

    async def get_candles_data(self, asset="EURUSD_otc", count=15, period=60):
        if not self.connected:
            return None
        try:
            candles = await self.client.get_candles(
                asset, int(time.time()), 0, period
            )
            if candles and len(candles) >= count:
                return candles[-count:]
        except Exception as e:
            print(f"Candle error: {e}")
        return None

    async def place_trade(
        self,
        asset="EURUSD_otc",
        amount=1.0,
        direction="call",
        duration=60,
    ):
        if not self.connected:
            return {"status": "error", "message": "Not connected"}

        try:
            asset_data, _ = await self.client.check_asset_open(asset)
            if not asset_data:
                return {"status": "error", "message": "Asset closed"}

            status, buy_info = await self.client.buy(
                amount, asset, direction, duration
            )
            if status:
                result = await self.client.check_win(buy_info["id"])
                profit = result[0] if result else 0.0
                win_status = result[1] if result else "WAITING"

                if win_status == "WIN":
                    self.profit_today += profit
                elif win_status == "LOSS":
                    self.loss_today += abs(profit)

                await self.update_balance()
                return {
                    "status": "success",
                    "order_id": buy_info["id"],
                    "direction": direction,
                    "amount": amount,
                    "profit": profit,
                    "result": win_status,
                    "balance": self.balance,
                }
            return {"status": "error", "message": "Order failed"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


async def analyze_with_gemini(candles):
    if not candles:
        return None

    formatted = [
        {
            "time": c[0],
            "open": c[1],
            "close": c[2],
            "high": c[3],
            "low": c[4],
        }
        for c in candles
    ]

    prompt = f"""
    You are an expert technical analyst and professional price action trader for 1-minute binary options.
    Analyze the following recent 1-minute sequential OHLC candlestick data:
    {json.dumps(formatted)}
    
    Evaluate:
    1. Overall trend (Bullish/Bearish/Sideways).
    2. Candlestick patterns (Pinbar, Hammer, Engulfing, Rejection wick, Doji).
    3. Momentum and buyers/sellers volume exhaustion.
    4. Exact reasoning for why this trade should or shouldn't be taken.

    Respond STRICTLY in raw JSON format matching this schema:
    {{
        "decision": "call" | "put" | "wait",
        "confidence": <integer 50-95>,
        "trend": "<Bullish / Bearish / Sideways>",
        "pattern": "<detected pattern name or 'None'>",
        "analysis": "<Provide 2-3 clear sentences in Bengali or English explaining why this signal was selected based on price action and rejection>"
    }}
    """
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0.1
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return None


engine = QuotexEngine()
trade_history = []
user_assets = {}


# ==================== টেলিগ্রাম হ্যান্ডলার ====================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Quotex Gemini AI Trading Bot Online*\n\n"
        "📌 *কমান্ডসমূহ:*\n"
        "🔹 /setpair - মার্কেট পেয়ার সিলেক্ট করুন (বাটন মেনু)\n"
        "🔹 /signal - নির্বাচিত পেয়ারের লাইভ AI সিগন্যাল ও বিশ্লেষণ দেখুন\n"
        "🔹 /trade - অ্যানালাইসিস করে সাথে সাথে ট্রেড নিন\n"
        "🔹 /balance - একাউন্ট ব্যালেন্স ও আজকের PnL দেখুন\n"
        "🔹 /history - শেষ ৫টি ট্রেডের হিস্ট্রি\n"
        "🔹 /status - বট ও কোটেক্স কানেকশন স্ট্যাটাস",
        parse_mode="Markdown",
    )


async def setpair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """পেয়ার বাছাই করার জন্য বাটন মেনু তৈরি"""
    keyboard = []
    # প্রতি লাইনে ২টি করে বাটন রাখা
    for i in range(0, len(AVAILABLE_PAIRS), 2):
        row = []
        name1, code1 = AVAILABLE_PAIRS[i]
        row.append(
            InlineKeyboardButton(name1, callback_data=f"setpair:{code1}")
        )
        if i + 1 < len(AVAILABLE_PAIRS):
            name2, code2 = AVAILABLE_PAIRS[i + 1]
            row.append(
                InlineKeyboardButton(name2, callback_data=f"setpair:{code2}")
            )
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    current_pair = user_assets.get(update.effective_user.id, DEFAULT_ASSET)

    await update.message.reply_text(
        f"🎯 *মার্কেট পেয়ার নির্বাচন করুন:*\n"
        f"বর্তমান পেয়ার: `{current_pair}`\n\n"
        f"নিচের বাটন থেকে আপনার পছন্দের পেয়ারটি সিলেক্ট করুন:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def pair_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বাটনে ক্লিক করলে পেয়ার সেট করা"""
    query = update.callback_query
    await query.answer()

    pair_code = query.data.split(":")[1]
    user_assets[query.from_user.id] = pair_code

    # পেয়ারের ডিসপ্লে নাম বের করা
    pair_display = pair_code
    for name, code in AVAILABLE_PAIRS:
        if code == pair_code:
            pair_display = name
            break

    await query.edit_message_text(
        f"✅ *পেয়ার সফলভাবে পরিবর্তন করা হয়েছে!*\n\n"
        f"📊 বর্তমান সক্রিয় পেয়ার: *{pair_display}* (`{pair_code}`)\n\n"
        f"এখন সিগন্যাল পেতে /signal কমান্ড দিন।",
        parse_mode="Markdown",
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    msg_wait = await update.message.reply_text(
        f"🔍 *{asset}* চার্ট এবং ক্যান্ডেলস্টিক বিশ্লেষণ করা হচ্ছে..."
    )

    candles = await engine.get_candles_data(asset)
    res = await analyze_with_gemini(candles)

    if not res:
        await msg_wait.edit_text(
            "❌ চার্ট বিশ্লেষণ ব্যর্থ হয়েছে। দয়া করে Gemini API Key বা ইন্টারনেট কানেকশন চেক করুন।"
        )
        return

    decision = res.get("decision", "wait").lower()
    confidence = res.get("confidence", 0)
    trend = res.get("trend", "N/A")
    pattern = res.get("pattern", "None")
    analysis_text = res.get("analysis", "কোনো ব্যাখ্যা পাওয়া যায়নি।")

    if decision == "call":
        signal_badge = "🟢 *CALL / UP (বাই)* 📈"
    elif decision == "put":
        signal_badge = "🔴 *PUT / DOWN (সেল)* 📉"
    else:
        signal_badge = "⚪ *WAIT (মার্কেট ঝুঁকিপূর্ণ, অপেক্ষা করুন)* ⏸"

    last_candle = candles[-1] if candles else None
    price_info = f"`{last_candle[2]:.5f}`" if last_candle else "N/A"

    msg = (
        f"📊 *মার্কেট সিগন্যাল রিপোর্ট*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *পেয়ার:* `{asset}`\n"
        f"💰 *বর্তমান প্রাইস:* {price_info}\n"
        f"🔮 *সিগন্যাল:* {signal_badge}\n"
        f"🎯 *কনফিডেন্স:* `{confidence}%`\n"
        f"📈 *মার্কেট ট্রেন্ড:* `{trend}`\n"
        f"🕯 *ক্যান্ডেল প্যাটার্ন:* `{pattern}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧠 *এনালাইসিস ও যুক্তি:*\n"
        f"_{analysis_text}_\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏱ *টাইমফ্রেম:* 1 Minute | ⚡ *Expiry:* 60s"
    )

    await msg_wait.edit_text(msg, parse_mode="Markdown")


async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    await update.message.reply_text(f"🧠 {asset} বিশ্লেষণ করে ট্রেড নেওয়া হচ্ছে...")

    candles = await engine.get_candles_data(asset)
    res = await analyze_with_gemini(candles)

    if not res:
        await update.message.reply_text("❌ বিশ্লেষণ ব্যর্থ হয়েছে।")
        return

    decision = res.get("decision", "wait").lower()
    confidence = res.get("confidence", 0)
    analysis_text = res.get("analysis", "")

    if decision not in ["call", "put"] or confidence < MIN_CONFIDENCE:
        await update.message.reply_text(
            f"⏸ *ট্রেড স্কিপ করা হয়েছে*\n"
            f"সিদ্ধান্ত: `{decision.upper()}` | কনফিডেন্স: `{confidence}%`\n\n"
            f"কারণ: {analysis_text}\n"
            f"*(ট্রেড নেওয়ার জন্য সর্বনিম্ন {MIN_CONFIDENCE}% কনফিডেন্স প্রয়োজন)*",
            parse_mode="Markdown",
        )
        return

    result = await engine.place_trade(
        asset, TRADE_AMOUNT, decision, TRADE_DURATION
    )
    if result["status"] == "success":
        trade_history.append(
            {
                "asset": asset,
                "direction": decision,
                "result": result["result"],
                "profit": result["profit"],
            }
        )
        msg = (
            f"✅ *ট্রেড সম্পন্ন হয়েছে*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 *অ্যাসেট:* `{asset}`\n"
            f"🎯 *ডিরেকশন:* `{decision.upper()}` ({confidence}%)\n"
            f"🏆 *ফলাফল:* `{result['result']}`\n"
            f"💵 *প্রফিট/লস:* `{result['profit']:+.2f}`\n"
            f"💰 *বর্তমান ব্যালেন্স:* `${result['balance']:.2f}`\n\n"
            f"💡 *যুক্তি:* {analysis_text}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"❌ ট্রেড ফেইল হয়েছে: {result.get('message')}"
        )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await engine.update_balance()
    pnl = engine.profit_today - engine.loss_today
    msg = (
        f"💰 *অ্যাকাউন্ট ব্যালেন্স:* `${engine.balance:.2f}`\n"
        f"📈 *আজকের প্রফিট:* `+${engine.profit_today:.2f}`\n"
        f"📉 *আজকের লস:* `-${engine.loss_today:.2f}`\n"
        f"📊 *মোট PnL:* `{' +' if pnl >= 0 else ''}${pnl:.2f}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not trade_history:
        await update.message.reply_text("এখনও কোনো ট্রেড রেকর্ড নেই।")
        return
    msg = "📜 *সর্বশেষ ৫টি ট্রেড:*\n━━━━━━━━━━━━━━━━━━\n"
    for t in trade_history[-5:]:
        icon = (
            "🟢"
            if t["result"] == "WIN"
            else "🔴"
            if t["result"] == "LOSS"
            else "⚪"
        )
        msg += f"{icon} `{t['asset']}` | `{t['direction'].upper()}` | `{t['result']}` | `{t['profit']:+.2f}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = "🟢 Connected" if engine.connected else "🔴 Offline"
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    await update.message.reply_text(
        f"*বট স্ট্যাটাস:*\n"
        f"Quotex: {conn}\n"
        f"সক্রিয় পেয়ার: `{asset}`\n"
        f"ব্যালেন্স: `${engine.balance:.2f}`",
        parse_mode="Markdown",
    )


async def auto_trader_loop():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    while True:
        await asyncio.sleep(60)
        if not engine.connected or not AUTO_TRADE_ENABLED:
            continue

        asset = DEFAULT_ASSET
        candles = await engine.get_candles_data(asset)
        res = await analyze_with_gemini(candles)

        if not res:
            continue

        decision = res.get("decision", "wait").lower()
        confidence = res.get("confidence", 0)
        analysis_text = res.get("analysis", "")

        if decision in ["call", "put"] and confidence >= MIN_CONFIDENCE:
            result = await engine.place_trade(
                asset, TRADE_AMOUNT, decision, TRADE_DURATION
            )
            if result["status"] == "success":
                trade_history.append(
                    {
                        "asset": asset,
                        "direction": decision,
                        "result": result["result"],
                        "profit": result["profit"],
                    }
                )
                msg = (
                    f"🤖 *অটো ট্রেড এক্সিকিউট হয়েছে*\n"
                    f"📊 *পেয়ার:* `{asset}` | ডিরেকশন: `{decision.upper()}`\n"
                    f"🏆 *রেজাল্ট:* `{result['result']}` ({result['profit']:+.2f})\n"
                    f"💡 *লজিক:* {analysis_text}\n"
                    f"💰 *ব্যালেন্স:* `${result['balance']:.2f}`"
                )
                try:
                    await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=msg,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    print(f"Notification error: {e}")


async def main():
    connected = await engine.connect()
    if not connected:
        print("❌ Quotex connection failed.")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # কমান্ড হ্যান্ডলার
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpair", setpair))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("trade", trade))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("status", status))

    # বাটন ক্লিক হ্যান্ডলার
    app.add_handler(CallbackQueryHandler(pair_callback, pattern="^setpair:"))

    asyncio.create_task(auto_trader_loop())
    print("🚀 Bot running with interactive pair buttons and Gemini analysis...")

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
        
