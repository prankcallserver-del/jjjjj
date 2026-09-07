import asyncio
from datetime import datetime
import json
import os
import sys
import time
from google import genai
from google.genai import types
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# লোকাল ফাইল পাথ পাইথনে সেট করা
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from pyquotex.stable_api import Quotex

# ==================== 🔑 ক্রেডেনশিয়াল (সরাসরি যুক্ত করা) ====================

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL", "servertgrail@gmail.com")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD", "servertgrail@gmail.com")
QUOTEX_IS_DEMO = os.getenv("QUOTEX_IS_DEMO", "True").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", "8942863443:AAFch9vDKsEqMfE3X_Ze9wjFPxH9bTzc0WI"
)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1112225")
GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY", "AQ.Ab8RN6I1RLraOzgPdJu5s6oG-gkMwixA-9fatmJd6kaASrR4BQ"
)

# ট্রেডিং সেটিংস
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
    Analyze this 1-minute OHLC candlestick data for binary options:
    {json.dumps(formatted)}
    
    Determine trend, support/resistance, and candlestick momentum.
    Respond ONLY in raw JSON matching this format:
    {{
        "decision": "call" | "put" | "wait",
        "confidence": <integer 50-95>,
        "reason": "<short reasoning>"
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Quotex Gemini AI Bot Online*\n\n"
        "Commands:\n"
        "🔹 /signal - Instant AI Market Signal\n"
        "🔹 /trade - Execute AI Trade\n"
        "🔹 /balance - View Balance & PnL\n"
        "🔹 /history - Last 5 Trades\n"
        "🔹 /status - Check Connection\n"
        "🔹 /setpair <asset> - Change Asset",
        parse_mode="Markdown",
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    await update.message.reply_text(f"🔍 Analyzing {asset}...")
    candles = await engine.get_candles_data(asset)
    res = await analyze_with_gemini(candles)

    if not res:
        await update.message.reply_text("❌ Analysis failed.")
        return

    icon = (
        "📈 UP (CALL)"
        if res["decision"].lower() == "call"
        else "📉 DOWN (PUT)"
        if res["decision"].lower() == "put"
        else "⏸ WAIT"
    )
    msg = (
        f"📊 *Asset:* {asset}\n"
        f"🔮 *Signal:* {icon}\n"
        f"🎯 *Confidence:* {res.get('confidence', 0)}%\n"
        f"💡 *Reason:* {res.get('reason', 'N/A')}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, DEFAULT_ASSET)
    candles = await engine.get_candles_data(asset)
    res = await analyze_with_gemini(candles)

    if not res:
        await update.message.reply_text("❌ Analysis failed.")
        return

    decision = res.get("decision", "wait").lower()
    confidence = res.get("confidence", 0)

    if decision not in ["call", "put"] or confidence < MIN_CONFIDENCE:
        await update.message.reply_text(
            f"⏸ *Skipped:* Decision `{decision.upper()}` ({confidence}% confidence)."
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
            f"✅ *Trade Executed*\n"
            f"📊 *Asset:* {asset} | *Dir:* {decision.upper()}\n"
            f"🏆 *Result:* {result['result']} ({result['profit']:+.2f})\n"
            f"💰 *Balance:* ${result['balance']:.2f}"
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
        f"💰 *Balance:* ${engine.balance:.2f}\n"
        f"📈 *Today Profit:* +${engine.profit_today:.2f}\n"
        f"📉 *Today Loss:* -${engine.loss_today:.2f}\n"
        f"📊 *Net PnL:* {'+' if pnl >= 0 else ''}${pnl:.2f}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not trade_history:
        await update.message.reply_text("No trades yet.")
        return
    msg = "📜 *Recent Trades:*\n"
    for t in trade_history[-5:]:
        msg += f"{t['asset']} | {t['direction'].upper()} | {t['result']} | {t['profit']:+.2f}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = "🟢 Connected" if engine.connected else "🔴 Offline"
    await update.message.reply_text(
        f"*Status:* {conn}\n*Balance:* ${engine.balance:.2f}",
        parse_mode="Markdown",
    )


async def setpair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/setpair EURUSD_otc`")
        return
    pair = context.args[0]
    user_assets[update.effective_user.id] = pair
    await update.message.reply_text(f"✅ Set to `{pair}`")


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
                    f"🤖 *Auto Trade*\n"
                    f"📊 *Asset:* {asset} | *Dir:* {decision.upper()} ({confidence}%)\n"
                    f"🏆 *Result:* {result['result']} ({result['profit']:+.2f})\n"
                    f"💰 *Balance:* ${result['balance']:.2f}"
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
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("trade", trade))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("setpair", setpair))

    asyncio.create_task(auto_trader_loop())
    print("🚀 Bot running...")

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

