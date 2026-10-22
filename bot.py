import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

# --- خادم الويب الإلزامي لضمان استقرار البوت 24/7 على Render ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html dir="rtl" lang="ar">
        <head><meta charset="UTF-8"><title>بوت سكالبينج OKX المتزامن</title></head>
        <body style="background:#0d1117; color:#c9d1d9; text-align:center; font-family:Arial; padding:50px;">
            <h1>🚀 بوت سكالبينج OKX الاحترافي يعمل الآن بنجاح واستقرار تام بتوقيت الرياض</h1>
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
import hmac
import hashlib
import base64
import json
from datetime import datetime, timezone, timedelta

RIYADH_TZ = timezone(timedelta(hours=3))

def get_riyadh_time():
    return datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %I:%M:%S %p')

BOT_SETTINGS = {
    "is_running": True,                  
    "trade_amount_usdt": 100.0,          
    "target_tp_pct": 0.03,               # هدف ربح 3%
    "min_secure_tp": 0.008,              # جني أرباح آمن عند 0.8%
    "stop_loss_pct": 0.006,              # وقف خسارة 0.6%
}

BOT_STATS = {
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_profit_usdt": 0.0,
    "active_positions_count": 0
}

# بيانات الاعتماد لمنصة OKX
API_KEY = '2bf148cb-c010-49fb-bffc-79f72720dfae'
SECRET_KEY = '1FBA3210BF6500BB1A1570EE9EC41A5C'
PASSPHRASE = 'Aa11223344##'

MAJOR_COINS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT"]

# --- توقيع الطلبات الآمن لمنصة OKX ---
def get_okx_headers(method, request_path, body=""):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    message = timestamp + method.upper() + request_path + body
    mac = hmac.new(SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    signature = base64.b64encode(mac.digest()).decode('utf-8')
    return {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "x-simulated-trading": "1"  # وضع التجربة (Sandbox)
    }

# --- سحب الشموع والأسعار المتزامنة من OKX مباشرة ---
async def fetch_okx_candles(session, symbol):
    url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar=15m&limit=30"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("code") == "0" and data.get("data"):
                    raw = data["data"]
                    candles = []
                    for c in reversed(raw):
                        candles.append([int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])])
                    return candles
    except Exception:
        pass
    return None

# --- تحليل هيكل السوق (SMA و RSI وتأكيد الشمعة) ---
def analyze_chart_market_structure(data):
    try:
        if not data or len(data) < 20:
            return False, "بيانات غير كافية"
            
        c = [r[4] for r in data]
        h = [r[2] for r in data]
        l = [r[3] for r in data]
        o = [r[1] for r in data]
        
        sma_fast = sum(c[-7:]) / 7
        sma_slow = sum(c[-20:]) / 20
        is_structure_bullish = sma_fast > sma_slow
        
        gains = 0.0
        losses = 0.0
        for i in range(-14, 0):
            diff = c[i] - c[i-1]
            if diff > 0:
                gains += diff
            else:
                losses -= diff
                
        avg_gain = gains / 14
        avg_loss = losses / 14 if losses != 0 else 0.001
        rs = avg_gain / avg_loss
        rsi_val = 100 - (100 / (1 + rs))
        
        min_recent_low = min(l[-6:-1])
        curr_low = l[-1]
        curr_open = o[-1]
        curr_close = c[-1]
        
        is_green_candle = curr_close > curr_open
        body_size = abs(curr_close - curr_open)
        total_range = h[-1] - curr_low
        
        if total_range == 0:
            return False, "مدى الشمعة صفر"

        is_bouncing_from_support = (curr_low <= min_recent_low * 1.004) and is_green_candle and ((body_size / total_range) > 0.4)
        is_rsi_healthy = rsi_val > 40

        if is_structure_bullish and is_bouncing_from_support and is_rsi_healthy:
            return True, "هيكل صاعد وتأكيد ارتداد ناجح"

        return False, "لا توجد إشارة واضحة"
    except Exception:
        return False, "خطأ في التحليل"

# --- تنفيذ الأوامر الحقيقية عبر API ---
async def execute_okx_order(session, symbol, side, sz):
    url = "https://www.okx.com/api/v5/trade/order"
    body_dict = {
        "instId": symbol,
        "tdMode": "cash",
        "side": side,
        "ordType": "market",
        "sz": str(sz)
    }
    body_str = json.dumps(body_dict)
    headers = get_okx_headers("POST", "/api/v5/trade/order", body_str)
    try:
        async with session.post(url, headers=headers, data=body_str, timeout=10) as resp:
            if resp.status == 200:
                res_data = await resp.json()
                if res_data.get("code") == "0":
                    return True, res_data
    except Exception as e:
        print(f"Order error: {e}", flush=True, file=sys.stdout)
    return False, None

# --- محرك التداول الرئيسي ---
async def unified_scalping_bot():
    print(f"[{get_riyadh_time()}] 🚀 [بوت السكالبينج الاحترافي] يعمل الآن بثبات تام عبر API...", flush=True, file=sys.stdout)
    active_position = None  

    async with aiohttp.ClientSession() as session:
        while True:
            if not BOT_SETTINGS["is_running"]:
                await asyncio.sleep(3)
                continue

            try:
                # --- متابعة الصفقة النشطة ---
                if active_position and active_position["in_pos"]:
                    symbol = active_position["symbol"]
                    candles = await fetch_okx_candles(session, symbol)
                    if candles:
                        curr_price = candles[-1][4]  # السعر المتزامن الفعلي
                        entry = active_position["entry_price"]
                        amount = active_position["amount"]
                        profit_ratio = (curr_price - entry) / entry

                        if curr_price > active_position["highest_price"]:
                            active_position["highest_price"] = curr_price

                        elapsed_time = datetime.now(RIYADH_TZ) - active_position["entry_time"]
                        elapsed_minutes = elapsed_time.total_seconds() / 60

                        highest_price = active_position["highest_price"]
                        drop_from_peak = (highest_price - curr_price) / highest_price

                        is_safe_exit = (profit_ratio >= BOT_SETTINGS["min_secure_tp"]) and (drop_from_peak >= 0.0025)
                        is_max_target = profit_ratio >= BOT_SETTINGS["target_tp_pct"]
                        is_timeout = elapsed_minutes >= 40

                        print(f"[{get_riyadh_time()}] 📈 [متابعة الصفقة] العملة: {symbol} | السعر: {curr_price} | الربح: {profit_ratio*100:.2f}%", flush=True, file=sys.stdout)

                        if is_safe_exit or is_max_target or is_timeout or (profit_ratio <= -BOT_SETTINGS["stop_loss_pct"]):
                            await execute_okx_order(session, symbol, "sell", amount)
                            
                            profit_usdt = (curr_price - entry) * (amount * curr_price)
                            active_position = None
                            
                            BOT_STATS["total_trades"] += 1
                            if profit_usdt > 0:
                                BOT_STATS["winning_trades"] += 1
                                print(f"[{get_riyadh_time()}] 🎯 [جني أرباح] العملة: {symbol} | الصافي: +{profit_usdt:.4f}$ USDT", flush=True, file=sys.stdout)
                            else:
                                BOT_STATS["losing_trades"] += 1
                                print(f"[{get_riyadh_time()}] 🛑 [وقف خسارة] العملة: {symbol} | النتيجة: {profit_usdt:.4f}$ USDT", flush=True, file=sys.stdout)

                            BOT_STATS["total_profit_usdt"] += profit_usdt
                            BOT_STATS["active_positions_count"] = 0

                    await asyncio.sleep(5)
                    continue

                print(f"[{get_riyadh_time()}] 🔍 [فحص السوق] فحص الأسعار المتزامنة للعملات...", flush=True, file=sys.stdout)
                
                candidate_opportunities = []

                for symbol in MAJOR_COINS:
                    candles = await fetch_okx_candles(session, symbol)
                    if not candles or len(candles) < 25:
                        continue

                    is_signal, _ = analyze_chart_market_structure(candles)
                    if is_signal:
                        synchronized_price = candles[-1][4]
                        candidate_opportunities.append({
                            "symbol": symbol,
                            "last_val": synchronized_price
                        })

                if candidate_opportunities:
                    best_opp = candidate_opportunities[0]
                    symbol = best_opp["symbol"]
                    last_val = best_opp["last_val"]

                    sz_amount = round(BOT_SETTINGS["trade_amount_usdt"] / last_val, 4)

                    await execute_okx_order(session, symbol, "buy", sz_amount)

                    active_position = {
                        "in_pos": True,
                        "symbol": symbol,
                        "entry_price": last_val,
                        "highest_price": last_val,
                        "amount": sz_amount,
                        "entry_time": datetime.now(RIYADH_TZ)
                    }
                    BOT_STATS["active_positions_count"] = 1
                    
                    print(f"[{get_riyadh_time()}] 🚀 [دخول صفقة حقيقية] العملة: {symbol} | السعر: {last_val} | الكمية: {sz_amount}", flush=True, file=sys.stdout)

            except Exception as e:
                print(f"[{get_riyadh_time()}] ⚠️ [خطأ مؤقت]: {e}", flush=True, file=sys.stdout)

            await asyncio.sleep(10)

# --- حلقة الحفاظ على نشاط السيرفر (Self-Ping) ---
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
    await asyncio.gather(
        self_ping_loop(),
        unified_scalping_bot()
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
