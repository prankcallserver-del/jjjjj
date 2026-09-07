import asyncio
import os
import time
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pyquotex.stable_api import Quotex

# ==================== 🔑 সরাসরি এখানে ক্রেডেনশিয়াল বসাও ====================

# ---------- Quotex ----------
QUOTEX_EMAIL = "servertgrail@gmail.com"        # তোমার Quotex ইমেইল
QUOTEX_PASSWORD = "servertgrail@gmail.com"              # তোমার Quotex পাসওয়ার্ড
QUOTEX_IS_DEMO = True                          # True = ডেমো, False = রিয়েল

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = "8942863443:AAFch9vDKsEqMfE3X_Ze9wjFPxH9bTzc0WI" # @BotFather থেকে নেওয়া টোকেন
TELEGRAM_CHAT_ID = "your_telegram_user_id"     # তোমার টেলিগ্রাম ইউজার আইডি

# ===================================================================

# ==================== Quotex ইঞ্জিন ====================
class QuotexEngine:
    def __init__(self):
        self.client = None
        self.connected = False
        self.balance = 0
        self.profit_today = 0
        self.loss_today = 0
        self.last_candle = None

    async def connect(self):
        self.client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD, lang="en")
        check_connect, message = await self.client.connect()

        if not check_connect:
            print(f"❌ Connection failed: {message}")
            return False

        self.connected = True
        print("✅ Quotex connected")

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
                if balance:
                    self.balance = balance
            except Exception as e:
                print(f"Balance error: {e}")

    async def get_candle(self, asset="EURUSD_otc", period=60):
        if not self.connected:
            return None
        try:
            end_from_time = int(time.time())
            candles = await self.client.get_candles(asset, end_from_time, 0, period)
            if candles and len(candles) > 0:
                last = candles[-1]
                self.last_candle = {
                    "time": last[0],
                    "open": last[1],
                    "close": last[2],
                    "high": last[3],
                    "low": last[4]
                }
                return self.last_candle
        except Exception as e:
            print(f"Candle error: {e}")
        return None

    async def place_trade(self, asset="EURUSD_otc", amount=1.0, direction="call", duration=60):
        if not self.connected:
            return {"status": "error", "message": "Not connected"}

        try:
            asset_data, asset_info = await self.client.check_asset_open(asset)
            if not asset_data:
                return {"status": "error", "message": "Asset closed"}

            status, buy_info = await self.client.buy(amount, asset, direction, duration)

            if status:
                result = await self.client.check_win(buy_info["id"])
                profit = result[0] if result else 0
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
                    "profit_today": self.profit_today,
                    "loss_today": self.loss_today
                }
            else:
                return {"status": "error", "message": "Trade failed"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

# ==================== গ্লোবাল ভেরিয়েবল ====================
engine = QuotexEngine()
trade_history = []
user_assets = {}

# ==================== হেল্পার ====================
def format_signal(asset, direction, confidence, candle_data, trade_result=None):
    msg = f"📊 *{asset.replace('_otc','')}* | 1min TF\n"
    msg += f"🔮 *Signal:* {'📈 UP' if direction == 'call' else '📉 DOWN'}\n"
    msg += f"🎯 *Confidence:* {confidence}%\n"
    if candle_data:
        msg += f"💰 *Price:* {candle_data['close']:.4f}\n"
        msg += f"📊 *High/Low:* {candle_data['high']:.4f} / {candle_data['low']:.4f}\n"
    if trade_result:
        result = trade_result.get('result', 'WAITING')
        profit = trade_result.get('profit', 0)
        balance = trade_result.get('balance', 0)
        pnl_today = trade_result.get('profit_today', 0) - trade_result.get('loss_today', 0)
        msg += f"\n📈 *Trade Result:* {result}\n"
        msg += f"💰 *Profit/Loss:* {'+' if profit > 0 else ''}{profit:.2f}\n"
        msg += f"💵 *Balance:* {balance:.2f}\n"
        msg += f"📊 *Today PnL:* {'+' if pnl_today > 0 else ''}{pnl_today:.2f}"
    else:
        msg += f"\n⏳ *Next update:* 60s"
    return msg

# ==================== টেলিগ্রাম কমান্ড ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Quotex AI Signal Bot*\n"
        "Commands:\n"
        "/signal - Get latest signal\n"
        "/trade - Auto trade on signal\n"
        "/balance - Check balance\n"
        "/history - Last 5 trades\n"
        "/status - Bot status\n"
        "/setpair EURUSD_otc - Change pair\n"
        "/help - Show this message",
        parse_mode="Markdown"
    )

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, 'EURUSD_otc')
    candle = await engine.get_candle(asset)
    direction = "call" if candle and candle['close'] > candle['open'] else "put"
    confidence = 65 + (candle['close'] - candle['open']) * 10 if candle else 50
    confidence = max(50, min(95, confidence))

    msg = format_signal(asset, direction, int(confidence), candle)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = user_assets.get(update.effective_user.id, 'EURUSD_otc')
    candle = await engine.get_candle(asset)
    direction = "call" if candle and candle['close'] > candle['open'] else "put"
    confidence = 65 + (candle['close'] - candle['open']) * 10 if candle else 50
    confidence = max(50, min(95, confidence))

    result = await engine.place_trade(asset, 1.0, direction, 60)
    if result['status'] == 'success':
        global trade_history
        trade_history.append({
            "asset": asset,
            "direction": direction,
            "result": result['result'],
            "profit": result['profit']
        })
        msg = format_signal(asset, direction, int(confidence), candle, result)
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Trade failed: {result.get('message', 'Unknown error')}")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await engine.update_balance()
    msg = f"💰 *Balance:* {engine.balance:.2f}\n"
    msg += f"📈 *Today Profit:* +{engine.profit_today:.2f}\n"
    msg += f"📉 *Today Loss:* -{engine.loss_today:.2f}"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global trade_history
    if not trade_history:
        await update.message.reply_text("No trades yet.")
        return
    msg = "📜 *Last 5 Trades*\n"
    for t in trade_history[-5:]:
        msg += f"{t['asset']} → {t['direction']} | {t['result']} | {t['profit']:.2f}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = "🟢 Connected" if engine.connected else "🔴 Disconnected"
    asset = user_assets.get(update.effective_user.id, 'EURUSD_otc')
    await update.message.reply_text(
        f"*Bot Status:* {status_text}\n"
        f"*Asset:* {asset}\n"
        f"*Balance:* {engine.balance:.2f}",
        parse_mode="Markdown"
    )

async def setpair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setpair EURUSD_otc")
        return
    pair = context.args[0]
    user_assets[update.effective_user.id] = pair
    await update.message.reply_text(f"✅ Asset changed to {pair}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ==================== অটো সিগন্যাল (পটভূমি) ====================
async def auto_signal():
    global trade_history
    while True:
        await asyncio.sleep(60)
        if not engine.connected:
            continue

        asset = 'EURUSD_otc'
        candle = await engine.get_candle(asset)
        direction = "call" if candle and candle['close'] > candle['open'] else "put"
        confidence = 65 + (candle['close'] - candle['open']) * 10 if candle else 50
        confidence = max(50, min(95, confidence))

        result = await engine.place_trade(asset, 1.0, direction, 60)
        if result['status'] == 'success':
            trade_history.append({
                "asset": asset,
                "direction": direction,
                "result": result['result'],
                "profit": result['profit']
            })
            msg = format_signal(asset, direction, int(confidence), candle, result)
        else:
            msg = f"⚠️ Auto trade failed: {result.get('message', 'Unknown error')}"

        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")

# ==================== মেইন ====================
async def main():
    # Quotex কানেক্ট
    await engine.connect()

    # টেলিগ্রাম বট
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("trade", trade))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("setpair", setpair))

    # অটো সিগন্যাল শুরু
    asyncio.create_task(auto_signal())

    print("🤖 Bot running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
