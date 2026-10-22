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
        <head><meta charset="UTF-8"><title>البوت الاحترافي المستقر بربط API</title></head>
        <body style="background:#0d1117; color:#c9d1d9; text-align:center; font-family:Arial; padding:50px;">
            <h1>🚀 البوت الاحترافي المستقر (ربط API حقيقي + تحليل شارت + أرباح 0.5% إلى 4%) يعمل بتوقيت الرياض</h1>
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
import numpy as np
import hmac
import hashlib
import base64
import time
from datetime import datetime, timezone, timedelta

RIYADH_TZ = timezone(timedelta(hours=3))

def get_riyadh_time():
    return datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %I:%M:%S %p')

BOT_SETTINGS = {
    "is_running": True,                  
    "trade_amount_usdt": 100.0,          
    "target_tp_pct": 0.03,               # هدف ربح 3% (ضمن النطاق 0.5% إلى 4%)
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

API_KEY = '2bf148cb-c010-49fb-bffc-79f72720dfae'
SECRET_KEY = '1FBA3210BF6500BB1A1570EE9EC41A5C'
PASSPHRASE = 'Aa11223344##'

# العملات الخمس الكبرى بتنسيق OKX الرسمي
MAJOR_COINS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT"]

# --- دالة توقيع الطلبات الخاصة بمنصة OKX (API Authentication) ---
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
        "x-simulated-trading": "1"  # وضع التداول التجريبي (Sandbox)
    }

# --- سحب الشموع والرسوم البيانية مباشرة عبر HTTP بدون أخطاء ccxt ---
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

# --- تحليل الشارت وهيكل السوق (Market Structure & RSI) ---
def analyze_chart_market_structure(df):
    try:
        if len(df) < 20:
            return False, "بيانات غير كافية"

        # المتوسطات المتحركة لقراءة الاتجاه
        df['sma_fast'] = df['close'].rolling(window=7).mean()
        df['sma_slow'] = df['close'].rolling(window=20).mean()
        
        fast_val = df['sma_fast'].iloc[-1]
        slow_val = df['sma_slow'].iloc[-1]
        is_structure_bullish = fast_val > slow_val

        # مؤشر القوة النسبية RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        rsi_val = df['rsi'].iloc[-1]

        # سلوك الشموع لمنع الارتداد الكاذب
        recent_low = df['low'].iloc[-6:-1].min()
        curr_low = df['low'].iloc[-1]
        curr_open = df['open'].iloc[-1]
        curr_close = df['close'].iloc[-1]
        
        is_green_candle = curr_close > curr_open
        body_size = abs(curr_close - curr_open)
        total_range = df['high'].iloc[-1] - curr_low
        
        if total_range == 0:
            return False, "مدى الشمعة صفر"

        is_bouncing_from_support = (curr_low <= recent_low * 1.004) and is_green_candle and ((body_size / total_range) > 0.4)
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
    import json
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

# --- المحرك الرئيسي المستقر فائق السرعة ---
async def unified_scalping_bot():
    print(f"[{get_riyadh_time()}] 🚀 [البوت الاحترافي بربط API] يعمل الآن باستقرار تام وبدون أخطاء اتصال...", flush=True, file=sys.stdout)
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
                        curr_price = candles[-1][4] # سعر الإغلاق الحالي
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
                            # بيع العملة عبر API
                            success, _ = await execute_okx_order(session, symbol, "sell", amount)
                            
                            profit_usdt = (curr_price - entry) * (amount * curr_price) # تقريبي للعرض
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

                print(f"[{get_riyadh_time()}] 🔍 [فحص السوق] فحص الرسوم البيانية للعملات الكبرى...", flush=True, file=sys.stdout)
                
                candidate_opportunities = []

                for symbol in MAJOR_COINS:
                    if symbol in BOT_SETTINGS["excluded_symbols"]:
                        continue

                    candles = await fetch_okx_candles(session, symbol)
                    if not candles or len(candles) < 25:
                        continue

                    df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    
                    is_signal, _ = analyze_chart_market_structure(df)
                    if is_signal:
                        last_price = df['close'].iloc[-1]
                        candidate_opportunities.append({
                            "symbol": symbol,
                            "last_val": last_price
                        })

                if candidate_opportunities:
                    best_opp = candidate_opportunities[0]
                    symbol = best_opp["symbol"]
                    last_val = best_opp["last_val"]

                    # حساب كمية العملة بناءً على 100 USDT
                    sz_amount = round(BOT_SETTINGS["trade_amount_usdt"] / last_val, 4)

                    # تنفيذ أمر الشراء الفعلي عبر API
                    success, _ = await execute_okx_order(session, symbol, "buy", sz_amount)

                    active_position = {
                        "in_pos": True,
                        "symbol": symbol,
                        "entry_price": last_val,
                        "highest_price": last_val,
                        "amount": sz_amount,
                        "entry_time": datetime.now(RIYADH_TZ)
                    }
                    BOT_STATS["active_positions_count"] = 1
                    
                    print(f"[{get_riyadh_time()}] 🚀 [دخول صفقة حقيقية عبر API] العملة: {symbol} | الشراء: {last_val} | الكمية: {sz_amount}", flush=True, file=sys.stdout)

            except Exception as e:
                print(f"[{get_riyadh_time()}] ⚠️ [خطأ مؤقت في حلقة التشغيل]: {e}", flush=True, file=sys.stdout)

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
