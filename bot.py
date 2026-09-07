import asyncio
from datetime import datetime
import json
import os
import re
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

# পাথ সেট
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from pyquotex.stable_api import Quotex

# ==================== 🔑 ক্রেডেনশিয়াল ====================

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL", "servertgrail@gmail.com")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD", "servertgrail@gmail.com")
QUOTEX_IS_DEMO = os.getenv("QUOTEX_IS_DEMO", "True").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", "8942863443:AAFch9vDKsEqMfE3X_Ze9wjFPxH9bTzc0WI"
)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1112225")
GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY", "AQ.Ab8RN6Ln67O4iIkOCNl84ta7qeOlWdAEOlpNBVGXZfWVphjRlw"
)

DEFAULT_ASSET = "EURUSD_otc"
TRADE_AMOUNT = 1.0
TRADE_DURATION = 60
MIN_CONFIDENCE = 70
AUTO_TRADE_ENABLED = True

# =========================================================

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

    async def get_available_pairs(self):
        if self.client:
            return await self.client.get_live_assets()
        return []

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
            is_open, info = await self.client.check_asset_open(asset)
            if not is_open:
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
                    "payout": info.get("payout", 85),
                }
            return {"status": "error", "message": "Order failed"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ==================== শক্তিশালী GEMINI এআই হ্যান্ডলার ====================
async def analyze_with_gemini(candles, asset_name="Asset"):
    """JSON Parsing Error ও Markdown Ticks প্রতিরোধক বিশ্লেষক"""
    if not candles:
        print("❌ Error: No candle data passed to Gemini")
        return None

    formatted = [
        {
            "time": c[0],
            "open": round(c[1], 5),
            "close": round(c[2], 5),
            "high": round(c[3], 5),
            "low": round(c[4], 5),
        }
        for c in candles
    ]

    prompt = f"""
    You are a professional price action binary options analyst.
    Analyze these sequential 1-minute OHLC candles for {asset_name}:
    {json.dumps(formatted)}
    
    Tasks:
    1. Identify trend, support/resistance, and candlestick patterns (Hammer, Pinbar, Engulfing).
    2. Give a trading decision: 'call', 'put', or 'wait'.
    3. Write a short explanation (in simple Bengali) stating WHY this decision was made.

    Return ONLY a valid JSON object matching this schema:
    {{
        "decision": "call" | "put" | "wait",
        "confidence": 75,
        "trend": "Bullish / Bearish / Sideways",
        "pattern": "Hammer / Engulfing / None",
        "analysis": "সংক্ষিপ্ত ২ লাইনের বাংলা যুক্তি"
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

        raw_text = response.text.strip()
        print(f"Gemini Raw Response: {raw_text}")

        # JSON ব্লক এক্সট্র্যাক্ট করা (মার্কডাউন ট্যাগ থাকলে সরানো)
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            clean_json = match.group(0)
            return json.loads(clean_json)

        return json.loads(raw_text)

    except Exception as e:
        print(f"❌ Gemini Execution/Parsing Error: {type(e).__name__} - {e}")
        return None


engine = QuotexEngine()
trade_history = []
user_assets = {}


# ==================== টেলিগ্রাম হ্যান্ডলার ====================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Quotex Gemini AI Pro Trader*\n\n"
        "🔹 /setpair - সমস্ত সক্রিয় পেয়ার ও তাদের পেআউট (%) দেখে সিলেক্ট করুন\n"
        "🔹 /signal - নির্বাচিত পেয়ারের লাইভ সিগন্যাল ও ক্যান্ডেলস্টিক যুক্তি দেখুন\n"
        "🔹 /trade - অ্যানালাইসিস করে সরাসরি ট্রেড এক্সিকিউট করুন\n"
        "🔹 /balance - একাউন্ট ব্যালেন্স ও আজকের PnL\n"
        "🔹 /history - শেষ ৫টি ট্রেড হিস্ট্রি\n"
        "🔹 /status - বট কানেকশন স্ট্যাটাস",
        parse_mode="Markdown",
    )


async def setpair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ব্রোকারের সব লাইভ পেয়ার ও প্রফিট % সহ বাটন তৈরি"""
    pairs = await engine.get_available_pairs()

    if not pairs:
        await update.message.reply_text("❌ কোনো সক্রিয় পেয়ার পাওয়া যায়নি।")
        return

    keyboard = []
    # প্রতি সারিতে ২টি করে পেয়ারের বাটন (নাম ও প্রফিট %)
    for i in range(0, len(pairs), 2):
        row = []
        p1 = pairs[i]
        btn1_text = f"🟢 {p1['name']} ({p1['payout']}%)"
        row.append(
            InlineKeyboardButton(btn1_text, callback_data=f"setpair:{p1['code']}")
        )

        if i + 1 < len(pairs):
            p2 = pairs[i + 1]
            btn2_text = f"🟢 {p2['name']} ({p2['payout']}%)"
            row.append(
                InlineKeyboardButton(
                    btn2_text, callback_data=f"setpair:{p2['code']}"
                )
            )
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    current_pair = user_assets.get(update.effective_user.id, DEFAULT_ASSET)

    await update.message.reply_text(
        f"📊 *বর্তমানে সচল মার্কেট পেয়ার ও পেআউট রেট:*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 বর্তমান নির্বাচিত পেয়ার: `{current_pair}`\n\n"
        f"ট্রেড করার জন্য নিচের যেকোনো পেয়ারে ট্যাপ করুন:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def pair_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pair_code = query.data.split(":")[1]
    user_assets[query.from_user.id] = pair_code

    # পেয়ারের নাম ও পেআউট বের করা
    pairs = await engine.get_available_pairs()
    pair_info = next((p for p in pairs if p["code"] == pair_code), None)

    name = pair_info["name"] if pair_info else pair_code
    payout = pair_info["payout"] if pair_info else 85

    await query.edit_message_text(
        f"✅ *পেয়ার সফলভাবে সিলেক্ট করা হয়েছে!*\n\n"
        f"🪙 *পেয়ার:* `{name}`\n"
        f"💰 *প্রফিট রেট:* `{payout}%`\n\n"
        f"এখন লাইভ সিগন্যাল ও এনালাইসিস পেতে /signal চাপুন।",
        parse_mode="Markdown",
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    msg_wait = await update.message.reply_text(
        f"🔍 *{asset}* চার্ট ও ক্যান্ডেলস্টিক এনালাইজ করা হচ্ছে..."
    )

    candles = await engine.get_candles_data(asset)
    res = await analyze_with_gemini(candles, asset_name=asset)

    if not res:
        await msg_wait.edit_text(
            f"❌ *বিশ্লেষণ ব্যর্থ হয়েছে!*\n"
            f"দয়া করে নিশ্চিত করুন আপনার Gemini API Key টি সক্রিয় রয়েছে এবং কোডে সঠিক মডেল কল হচ্ছে।"
        )
        return

    decision = str(res.get("decision", "wait")).lower()
    confidence = res.get("confidence", 70)
    trend = res.get("trend", "Sideways")
    pattern = res.get("pattern", "None")
    analysis_text = res.get("analysis", "মার্কেট পর্যবেক্ষণ করা হচ্ছে।")

    if decision == "call":
        signal_badge = "🟢 *CALL / UP (বাই)* 📈"
    elif decision == "put":
        signal_badge = "🔴 *PUT / DOWN (সেল)* 📉"
    else:
        signal_badge = "⚪ *WAIT (অপেক্ষা করুন)* ⏸"

    last_candle = candles[-1] if candles else None
    price_info = f"`{last_candle[2]:.5f}`" if last_candle else "N/A"

    pairs = await engine.get_available_pairs()
    payout = next((p["payout"] for p in pairs if p["code"] == asset), 85)

    msg = (
        f"📊 *লাইভ মার্কেট এআই সিগন্যাল*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *পেয়ার:* `{asset}` (Payout: `{payout}%`)\n"
        f"💰 *বর্তমান প্রাইস:* {price_info}\n"
        f"🔮 *সিগন্যাল:* {signal_badge}\n"
        f"🎯 *কনফিডেন্স:* `{confidence}%`\n"
        f"📈 *ট্রেন্ড:* `{trend}` | 🕯 *প্যাটার্ন:* `{pattern}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧠 *এনালাইসিস ও কারণ:*\n"
        f"_{analysis_text}_\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏱ *টাইমফ্রেম:* 1 Minute | ⚡ *ডিউরেশন:* 60s"
    )

    await msg_wait.edit_text(msg, parse_mode="Markdown")


async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    await update.message.reply_text(f"🧠 {asset} বিশ্লেষণ করে ট্রেড নেওয়া হচ্ছে...")

    candles = await engine.get_candles_data(asset)
    res = await analyze_with_gemini(candles, asset_name=asset)

    if not res:
        await update.message.reply_text("❌ চার্ট বিশ্লেষণ ব্যর্থ হয়েছে।")
        return

    decision = str(res.get("decision", "wait")).lower()
    confidence = res.get("confidence", 0)
    analysis_text = res.get("analysis", "")

    if decision not in ["call", "put"] or confidence < MIN_CONFIDENCE:
        await update.message.reply_text(
            f"⏸ *ট্রেড নেওয়া হয়নি*\n"
            f"সিদ্ধান্ত: `{decision.upper()}` | কনফিডেন্স: `{confidence}%`\n\n"
            f"💡 কারণ: {analysis_text}\n"
            f"*(ট্রেড নেওয়ার জন্য নূন্যতম {MIN_CONFIDENCE}% কনফিডেন্স প্রয়োজন)*",
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
            f"✅ *ট্রেড সম্পন্ন হয়েছে!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 *অ্যাসেট:* `{asset}`\n"
            f"🎯 *ডিরেকশন:* `{decision.upper()}` ({confidence}%)\n"
            f"🏆 *ফলাফল:* `{result['result']}`\n"
            f"💵 *প্রফিট/লস:* `{result['profit']:+.2f}` (Payout: {result['payout']}%)\n"
            f"💰 *ব্যালেন্স:* `${result['balance']:.2f}`\n\n"
            f"💡 *যুক্তি:* {analysis_text}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"❌ ট্রেড ব্যর্থ হয়েছে: {result.get('message')}"
        )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await engine.update_balance()
    pnl = engine.profit_today - engine.loss_today
    msg = (
        f"💰 *অ্যাকাউন্ট ব্যালেন্স:* `${engine.balance:.2f}`\n"
        f"📈 *আজকের লাভ:* `+${engine.profit_today:.2f}`\n"
        f"📉 *আজকের লস:* `-${engine.loss_today:.2f}`\n"
        f"📊 *নেট PnL:* `{' +' if pnl >= 0 else ''}${pnl:.2f}`"
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
        f"নির্বাচিত পেয়ার: `{asset}`\n"
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
        res = await analyze_with_gemini(candles, asset_name=asset)

        if not res:
            continue

        decision = str(res.get("decision", "wait")).lower()
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
                    print(f"Auto-trade notification error: {e}")


async def main():
    connected = await engine.connect()
    if not connected:
        print("❌ Quotex connection failed.")
        return

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
    print("🚀 Bot is running smoothly...")

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
            
