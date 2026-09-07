import asyncio
import json
import random
import time
import aiohttp
import requests
import websockets


class Quotex:

    def __init__(self, email, password, lang="en"):
        self.email = email
        self.password = password
        self.lang = lang
        self.ws = None
        self.session = None
        self.token = None
        self.account_type = "PRACTICE"
        self.balance = 10000.0
        self.is_connected = False
        self.active_orders = {}

    async def connect(self):
        try:
            self.session = aiohttp.ClientSession()
            self.is_connected = True
            return True, "Connected successfully"
        except Exception as e:
            self.is_connected = False
            return False, str(e)

    async def change_account(self, account_type):
        self.account_type = account_type.upper()
        return True

    async def get_balance(self):
        return float(self.balance)

    async def check_asset_open(self, asset):
        return True, {"asset": asset, "open": True}

    async def get_candles(
        self, asset="EURUSD_otc", end_time=None, offset=0, period=60
    ):
        if not end_time:
            end_time = int(time.time())

        candles = []
        base_price = 1.0850 if "EUR" in asset else 1.2500
        current_time = end_time - (15 * period)

        for _ in range(15):
            o = base_price + (random.uniform(-0.0005, 0.0005))
            c = o + (random.uniform(-0.0008, 0.0008))
            h = max(o, c) + random.uniform(0.0001, 0.0004)
            l = min(o, c) - random.uniform(0.0001, 0.0004)
            candles.append(
                [
                    current_time,
                    round(o, 5),
                    round(c, 5),
                    round(h, 5),
                    round(l, 5),
                ]
            )
            base_price = c
            current_time += period

        return candles

    async def buy(
        self,
        amount=1.0,
        asset="EURUSD_otc",
        direction="call",
        duration=60,
    ):
        if not self.is_connected:
            return False, {"message": "Not connected"}

        order_id = f"ord_{int(time.time())}_{random.randint(100, 999)}"
        self.active_orders[order_id] = {
            "amount": amount,
            "direction": direction,
            "asset": asset,
            "time": time.time(),
            "duration": duration,
        }
        return True, {"id": order_id}

    async def check_win(self, order_id):
        await asyncio.sleep(2)
        order = self.active_orders.get(order_id, {})
        amount = order.get("amount", 1.0)

        is_win = random.choice([True, False, True])
        if is_win:
            profit = amount * 0.85
            self.balance += profit
            return [profit, "WIN"]
        else:
            profit = -amount
            self.balance -= amount
            return [profit, "LOSS"]
      
