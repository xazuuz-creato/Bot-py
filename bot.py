import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

# --- خادم الويب الفوري لضمان استقرار السيرفر على Render ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html dir="rtl" lang="ar">
        <head><meta charset="UTF-8"><title>البوت الاحترافي المستقر</title></head>
        <body style="background:#0d1117; color:#c9d1d9; text-align:center; font-family:Arial; padding:50px;">
            <h1>🚀 البوت الاحترافي المستقر (بدون أي أخطاء اتصال نهائياً) يعمل بتوقيت الرياض</h1>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))
    
    def log_message(self, format, *args):
        pass

def run_fast_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

server_thread = Thread(target=run_fast_server, daemon=True)
server_thread.start()

import aiohttp
import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta

RIYADH_TZ = timezone(timedelta(hours=3))

def get_riyadh_time():
    return datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %I:%M:%S %p')

BOT_SETTINGS = {
    "is_running": True,                  
    "trade_amount_usdt": 100.0,          
    "target_tp_pct": 0.03,               
    "min_secure_tp": 0.008,              
    "stop_loss_pct": 0.006,              
    "excluded_symbols": []               
}

BOT_STATS = {
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_profit_usdt": 0.0,
    "active_positions_count": 0
}

MAJOR_COINS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT"]

async def fetch_okx_candles(session, symbol):
    url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar=15m&limit=30"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("code") == "0" and data.get("data"):
                    raw_candles = data["data"]
                    candles = []
                    for c in reversed(raw_candles):
                        candles.append([
                            int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
                        ])
                    return candles
    except Exception:
        pass
    return None

async def fetch_okx_ticker(session, symbol):
    url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("code") == "0" and data.get("data"):
                    return float(data["data"][0]["last"])
    except Exception:
        pass
    return None

def analyze_market_signal(df):
    try:
        if len(df) < 25:
            return False

        df['sma_20'] = df['close'].rolling(window=20).mean()
        current_close = df['close'].iloc[-1]
        sma_val = df['sma_20'].iloc[-1]

        if current_close < sma_val:
            return False

        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        rsi_val = df['rsi'].iloc[-1]

        prev_open = df['open'].iloc[-2]
        prev_close = df['close'].iloc[-2]
        curr_open = df['open'].iloc[-1]
        curr_close = df['close'].iloc[-1]

        is_prev_green = prev_close > prev_open
        is_curr_green = curr_close > curr_open

        if is_prev_green and is_curr_green and (rsi_val > 40):
            return True

        return False
    except Exception:
        return False

async def unified_scalping_bot():
    print(f"[{get_riyadh_time()}] 🚀 [البوت الاحترافي المستقر] يعمل الآن بكفاءة تامة ودون أي مشاكل...", flush=True, file=sys.stdout)
    active_position = None  

    async with aiohttp.ClientSession() as session:
        while True:
            if not BOT_SETTINGS["is_running"]:
                await asyncio.sleep(3)
                continue

            try:
                if active_position and active_position["in_pos"]:
                    symbol = active_position["symbol"]
                    curr_price = await fetch_okx_ticker(session, symbol)
                    
                    if curr_price:
                        entry = active_position["entry_price"]
                        amount = active_position["amount"]
                        profit_ratio = (curr_price - entry) / entry

                        if curr_price > active_position["highest_price"]:
                            active_position["highest_price"] = curr_price

                        elapsed_time = datetime.now(RIYADH_TZ) - active_position["entry_time"]
                        elapsed_minutes = elapsed_time.total_seconds() / 60

                        highest_price = active_position["highest_price"]
                        drop_from_peak = (highest_price - curr_price) / highest_price

                        is_safe_exit = (profit_ratio >= BOT_SETTINGS["min_secure_tp"]) and (drop_from_peak >= 0.002)
                        is_max_target = profit_ratio >= BOT_SETTINGS["target_tp_pct"]
                        is_timeout = elapsed_minutes >= 40

                        print(f"[{get_riyadh_time()}] 📈 [متابعة الصفقة] العملة: {symbol} | الربح: {profit_ratio*100:.2f}%", flush=True, file=sys.stdout)

                        if is_safe_exit or is_max_target or is_timeout or (profit_ratio <= -BOT_SETTINGS["stop_loss_pct"]):
                            profit_usdt = (curr_price - entry) * amount
                            active_position = None
                            
                            BOT_STATS["total_trades"] += 1
                            if profit_usdt > 0:
                                BOT_STATS["winning_trades"] += 1
                                print(f"[{get_riyadh_time()}] 🎯 [جني أرباح ناجح] العملة: {symbol} | الصافي: +{profit_usdt:.4f}$ USDT", flush=True, file=sys.stdout)
                            else:
                                BOT_STATS["losing_trades"] += 1
                                print(f"[{get_riyadh_time()}] 🛑 [إغلاق حماية] العملة: {symbol} | النتيجة: {profit_usdt:.4f}$ USDT", flush=True, file=sys.stdout)

                            BOT_STATS["total_profit_usdt"] += profit_usdt
                            BOT_STATS["active_positions_count"] = 0

                    await asyncio.sleep(5)
                    continue

                print(f"[{get_riyadh_time()}] 🔍 [فحص السوق] فحص العملات الكبرى...", flush=True, file=sys.stdout)

                candidate_opportunities = []

                for symbol in MAJOR_COINS:
                    if symbol in BOT_SETTINGS["excluded_symbols"]:
                        continue

                    candles = await fetch_okx_candles(session, symbol)
                    if not candles or len(candles) < 25:
                        continue

                    df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    
                    if analyze_market_signal(df):
                        last_price = df['close'].iloc[-1]
                        candidate_opportunities.append({
                            "symbol": symbol,
                            "last_val": last_price
                        })

                if candidate_opportunities:
                    best_opp = candidate_opportunities[0]
                    symbol = best_opp["symbol"]
                    last_val = best_opp["last_val"]

                    crypto_amount = BOT_SETTINGS["trade_amount_usdt"] / last_val
                    
                    active_position = {
                        "in_pos": True,
                        "symbol": symbol,
                        "entry_price": last_val,
                        "highest_price": last_val,
                        "amount": crypto_amount,
                        "entry_time": datetime.now(RIYADH_TZ)
                    }
                    BOT_STATS["active_positions_count"] = 1
                    
                    print(f"[{get_riyadh_time()}] 🚀 [دخول صفقة ناجحة] العملة: {symbol} | الشراء: {last_val} | القيمة: {BOT_SETTINGS['trade_amount_usdt']}$ USDT", flush=True, file=sys.stdout)

            except Exception as e:
                print(f"[{get_riyadh_time()}] ⚠️ [خطأ مؤقت، استئناف تلقائي]: {e}", flush=True, file=sys.stdout)

            await asyncio.sleep(10)

async def self_ping_loop():
    port = int(os.environ.get("PORT", 10000))
    render_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
    while True:
        try:
            await asyncio.sleep(240)
            async with aiohttp.ClientSession() as session:
                async with session.get(render_url) as resp:
                    pass
        except asyncio.CancelledError:
            break
        except Exception:
            pass

async def main():
    asyncio.gather(
        self_ping_loop(),
        unified_scalping_bot()
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
