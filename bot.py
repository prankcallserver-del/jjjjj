import asyncio
import json
import time
from datetime import datetime
from google import genai
from google.genai import types
from pyquotex.stable_api import Quotex
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ==================== 🔑 ক্রেডেনশিয়াল ও সেটিংস ====================

# ---------- Quotex ----------
QUOTEX_EMAIL = "servertgrail@gmail.com"
QUOTEX_PASSWORD = "servertgrail@gmail.com"
QUOTEX_IS_DEMO = True  # True = ডেমো অ্যাকাউন্ট, False = রিয়েল অ্যাকাউন্ট

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = "8942863443:AAFch9vDKsEqMfE3X_Ze9wjFPxH9bTzc0WI"
TELEGRAM_CHAT_ID = "1112225"

# ---------- Google Gemini ----------
GEMINI_API_KEY = "AQ.Ab8RN6I1RLraOzgPdJu5s6oG-gkMwixA-9fatmJd6kaASrR4BQ"

# ---------- Trading Settings ----------
DEFAULT_ASSET = "EURUSD_otc"
TRADE_AMOUNT = 1.0  # প্রতি ট্রেডের ডলার অ্যামাউন্ট
TRADE_DURATION = 60  # ট্রেড ডিউরেশন (সেকেন্ড)
MIN_CONFIDENCE = 75  # Gemini-এর মিনিমাম কনফিডেন্স কত হলে ট্রেড নেবে (%)
AUTO_TRADE_ENABLED = True  # ব্যাকগ্রাউন্ডে স্বয়ংক্রিয় ট্রেডিং চালু/বন্ধ

# ===================================================================

# Gemini Client ইনিশিয়ালাইজ
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# ==================== Quotex ইঞ্জিন ====================
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
        print("✅ Quotex connected successfully")

        if QUOTEX_IS_DEMO:
            await self.client.change_account("PRACTICE")
        else:
            await self.client.change_account("REAL")

        await self.update_balance()
        return True

    async def update_balance(self):
        if self.client and self.connected:
            try:
                balance = await self.client.get_balance()
                if balance is not None:
                    self.balance = float(balance)
            except Exception as e:
                print(f"Balance error: {e}")

    async def get_candles_data(self, asset="EURUSD_otc", count=15, period=60):
        if not self.connected:
            return None
        try:
            end_from_time = int(time.time())
            candles = await self.client.get_candles(
                asset, end_from_time, 0, period
            )
            if candles and len(candles) >= count:
                return candles[-count:]
        except Exception as e:
            print(f"Candle fetch error: {e}")
        return None

    async def place_trade(
        self,
        asset="EURUSD_otc",
        amount=1.0,
        direction="call",
        duration=60,
    ):
        if not self.connected:
            return {"status": "error", "message": "Not connected to Quotex"}

        try:
            asset_data, _ = await self.client.check_asset_open(asset)
            if not asset_data:
                return {
                    "status": "error",
                    "message": f"Asset {asset} is currently closed",
                }

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
            else:
                return {
                    "status": "error",
                    "message": "Broker rejected the trade order",
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ==================== Gemini এআই অ্যানালাইসিস ====================
async def analyze_with_gemini(candles):
    """ক্যান্ডেলস্টিক ডেটা বিশ্লেষণ করে Gemini থেকে সিগন্যাল সংগ্রহ"""
    if not candles:
        return None

    formatted_candles = []
    for c in candles:
        formatted_candles.append(
            {
                "time": c[0],
                "open": round(c[1], 5),
                "close": round(c[2], 5),
                "high": round(c[3], 5),
                "low": round(c[4], 5),
            }
        )

    prompt = f"""
    You are an elite quantitative technical analyst specializing in 1-minute binary options price action trading.
    Analyze the following recent 1-minute sequential OHLC candle data:
    {json.dumps(formatted_candles)}

    Evaluate:
    1. Trend direction & momentum.
    2. Candlestick patterns (e.g., pinbars, engulfing, rejections).
    3. Overbought/Oversold exhaustion states.

    Respond STRICTLY in JSON format using this schema:
    {{
        "decision": "call" | "put" | "wait",
        "confidence": <integer from 50 to 95>,
        "reason": "<one sentence concise reasoning>"
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
        data = json.loads(response.text)
        return data
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return None


# ==================== গ্লোবাল ভেরিয়েবল ====================
engine = QuotexEngine()
trade_history = []
user_assets = {}


# ==================== টেলিগ্রাম কমান্ড হ্যান্ডলার ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Quotex Gemini AI Trading Bot Active*\n\n"
        "Commands:\n"
        "🔹 /signal - Get instant AI market analysis\n"
        "🔹 /trade - Analyze and execute trade immediately\n"
        "🔹 /balance - View account balance and PnL\n"
        "🔹 /history - View last 5 trades\n"
        "🔹 /status - Connection and setup status\n"
        "🔹 /setpair <asset> - Change active asset (e.g. `/setpair GBPUSD_otc`)",
        parse_mode="Markdown",
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    await update.message.reply_text(f"🔍 Analyzing {asset} with Gemini AI...")

    candles = await engine.get_candles_data(asset=asset, count=15, period=60)
    analysis = await analyze_with_gemini(candles)

    if not analysis:
        await update.message.reply_text("❌ Failed to analyze market data.")
        return

    decision = analysis.get("decision", "wait").upper()
    confidence = analysis.get("confidence", 0)
    reason = analysis.get("reason", "N/A")

    direction_icon = (
        "📈 UP (CALL)"
        if decision == "CALL"
        else "📉 DOWN (PUT)"
        if decision == "PUT"
        else "⏸ WAIT"
    )

    msg = (
        f"📊 *Asset:* {asset}\n"
        f"🔮 *Signal:* {direction_icon}\n"
        f"🎯 *Confidence:* {confidence}%\n"
        f"💡 *Reason:* {reason}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    await update.message.reply_text(
        f"🧠 Analyzing {asset} and executing trade..."
    )

    candles = await engine.get_candles_data(asset=asset, count=15, period=60)
    analysis = await analyze_with_gemini(candles)

    if not analysis:
        await update.message.reply_text("❌ Analysis failed.")
        return

    decision = analysis.get("decision", "wait").lower()
    confidence = analysis.get("confidence", 0)
    reason = analysis.get("reason", "N/A")

    if decision not in ["call", "put"] or confidence < MIN_CONFIDENCE:
        await update.message.reply_text(
            f"⏸ *Trade Skipped*\n"
            f"Decision: {decision.upper()} | Confidence: {confidence}%\n"
            f"Reason: {reason}\n"
            f"*(Requires minimum {MIN_CONFIDENCE}% confidence to execute)*",
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
            f"✅ *Trade Completed*\n"
            f"📊 *Asset:* {asset}\n"
            f"🎯 *Direction:* {decision.upper()} ({confidence}%)\n"
            f"🏆 *Result:* {result['result']}\n"
            f"💵 *Profit/Loss:* {result['profit']:+.2f}\n"
            f"💰 *Balance:* {result['balance']:.2f}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"❌ Trade failed: {result.get('message')}"
        )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await engine.update_balance()
    pnl = engine.profit_today - engine.loss_today
    msg = (
        f"💰 *Current Balance:* ${engine.balance:.2f}\n"
        f"📈 *Today's Profit:* +${engine.profit_today:.2f}\n"
        f"📉 *Today's Loss:* -${engine.loss_today:.2f}\n"
        f"📊 *Net PnL:* {'+' if pnl >= 0 else ''}${pnl:.2f}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not trade_history:
        await update.message.reply_text("No trades recorded yet.")
        return
    msg = "📜 *Recent Trades (Last 5):*\n\n"
    for t in trade_history[-5:]:
        icon = (
            "🟢"
            if t["result"] == "WIN"
            else "🔴"
            if t["result"] == "LOSS"
            else "⚪"
        )
        msg += f"{icon} {t['asset']} | {t['direction'].upper()} | {t['result']} | {t['profit']:+.2f}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn_text = (
        "🟢 Connected" if engine.connected else "🔴 Connection Offline"
    )
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    await update.message.reply_text(
        f"*System Status:*\n"
        f"Quotex: {conn_text}\n"
        f"Active Asset: `{asset}`\n"
        f"Min Confidence Threshold: {MIN_CONFIDENCE}%\n"
        f"Balance: ${engine.balance:.2f}",
        parse_mode="Markdown",
    )


async def setpair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/setpair EURUSD_otc`")
        return
    pair = context.args[0]
    user_assets[update.effective_user.id] = pair
    await update.message.reply_text(f"✅ Active asset updated to `{pair}`")


# ==================== অটো ট্রেডার লুপ ====================
async def auto_trader_loop():
    """প্রতি ৬০ সেকেন্ড অন্তর ক্যান্ডেল অ্যানালাইসিস করে স্বয়ংক্রিয় ট্রেড নেবে"""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    while True:
        await asyncio.sleep(60)

        if not engine.connected or not AUTO_TRADE_ENABLED:
            continue

        asset = DEFAULT_ASSET
        candles = await engine.get_candles_data(
            asset=asset, count=15, period=60
        )
        analysis = await analyze_with_gemini(candles)

        if not analysis:
            continue

        decision = analysis.get("decision", "wait").lower()
        confidence = analysis.get("confidence", 0)
        reason = analysis.get("reason", "")

        # কনফিডেন্স থ্রেশহোল্ড পূরণ করলে ট্রেড ওপেন করবে
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
                    f"🤖 *Auto Trade Executed*\n"
                    f"📊 *Asset:* {asset}\n"
                    f"🎯 *Signal:* {decision.upper()} ({confidence}%)\n"
                    f"💡 *Reason:* {reason}\n"
                    f"🏆 *Result:* {result['result']} ({result['profit']:+.2f})\n"
                    f"💰 *Balance:* ${result['balance']:.2f}"
                )
                try:
                    await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Telegram notification error: {e}")


# ==================== মেইন এন্ট্রি পয়েন্ট ====================
async def main():
    # Quotex কানেক্ট
    connected = await engine.connect()
    if not connected:
        print("❌ Quotex connection failed. Check credentials and retry.")
        return

    # টেলিগ্রাম অ্যাপ বিল্ডার
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("trade", trade))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("setpair", setpair))

    # ব্যাকগ্রাউন্ডে অটো ট্রেডার চালু
    asyncio.create_task(auto_trader_loop())

    print("🚀 Bot is running and waiting for Telegram commands...")

    # টেলিগ্রাম পোলিং চালু
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # বট সচল রাখতে ইনফিনিট ওয়েট
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Bot stopped manually.")
