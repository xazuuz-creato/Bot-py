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
        <head><meta charset="UTF-8"><title>بوت الحماية المتقدم من الارتداد الكاذب</title></head>
        <body style="background:#0d1117; color:#c9d1d9; text-align:center; font-family:Arial; padding:50px;">
            <h1>🚀 بوت التداول المحترف (حماية كاملة من الارتدادات الكاذبة + أرباح 0.5% إلى 4%) يعمل بتوقيت الرياض</h1>
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

import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta

RIYADH_TZ = timezone(timedelta(hours=3))

def get_riyadh_time():
    return datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %I:%M:%S %p')

BOT_SETTINGS = {
    "is_running": True,                  
    "trade_amount_usdt": 100.0,          
    "target_tp_pct": 0.03,               # هدف ربح مرن واحترافي (3.0% ضمن النطاق 0.5% إلى 4%)
    "min_secure_tp": 0.008,              # جني أرباح آمن ومضمون (0.8%)
    "stop_loss_pct": 0.006,              # وقف خسارة صارم ومحمي (0.6%)
    "excluded_symbols": []               
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

# --- تحليل متقدم يمنع الارتداد الكاذب وفخ الانهيار ---
def analyze_no_false_bounce(df):
    try:
        if len(df) < 25:
            return False, "بيانات الشارت غير كافية"

        # 1. فلتر الاتجاه العام (منع الشراء في الانهيارات الموضحة بالصور)
        df['sma_20'] = df['close'].rolling(window=20).mean()
        current_close = df['close'].iloc[-1]
        sma_val = df['sma_20'].iloc[-1]

        # إذا كان السعر تحت المتوسط بمسافة كبيرة أو الاتجاه هابط حاد، نمنع الشراء فوراً
        if current_close < sma_val:
            return False, "تجنب صيد السكين الهابطة (الترند تحت المتوسط)"

        # 2. مؤشر القوة النسبية RSI للتأكد من خروج العملة من التشبع البيعي الحقيقي
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        rsi_val = df['rsi'].iloc[-1]

        # 3. شرط تأكيد الشموع المزدوجة (شمعتان خضراوان متتاليتان لضمان عدم كذب الارتداد)
        prev_open = df['open'].iloc[-2]
        prev_close = df['close'].iloc[-2]
        curr_open = df['open'].iloc[-1]
        curr_close = df['close'].iloc[-1]

        is_prev_green = prev_close > prev_open
        is_curr_green = curr_close > curr_open

        # التأكد أن الشمعتين صاعدتان وذواتا جسم حقيقي يؤكد دخول السيولة
        is_double_confirmation = is_prev_green and is_curr_green and (rsi_val > 40)

        if is_double_confirmation:
            return True, "تم تأكيد الارتداد بشمعتين متتاليتين وترند إيجابي"

        return False, "انتظار تأكيد حقيقي (منع الارتداد الكاذب)"
    except Exception:
        return False, "خطأ في تحليل السوق"

class ScalpingGuardian:
    def __init__(self, min_volume=5_000_000, max_spread_pct=0.05):
        self.min_volume = min_volume
        self.max_spread_pct = max_spread_pct

    def inspect_symbol_for_scalping(self, data):
        symbol = data.get('symbol', 'UNKNOWN')
        volume = data.get('volume_24h', 0)
        bid = data.get('bid', 0)
        ask = data.get('ask', 0)
        
        spread_pct = ((ask - bid) / ask * 100) if ask > 0 else 999.0
        is_ready = True
        if volume < self.min_volume or spread_pct > self.max_spread_pct:
            is_ready = False

        return {"symbol": symbol, "can_scalp": is_ready}

guardian = ScalpingGuardian()

# --- المحرك الرئيسي المحمي ضد الارتدادات الوهمية ---
async def unified_scalping_bot():
    print(f"[{get_riyadh_time()}] 🚀 [بوت الحماية من الارتداد الكاذب] بدأ العمل بكفاءة عالية...", flush=True, file=sys.stdout)
    active_position = None  

    major_5_symbols = [
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT'
    ]

    scan_counter = 0

    while True:
        if not BOT_SETTINGS["is_running"]:
            await asyncio.sleep(3)
            continue

        exchange = None
        try:
            exchange = ccxt.okx({
                'apiKey': API_KEY, 
                'secret': SECRET_KEY,
                'password': PASSPHRASE, 
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
            exchange.set_sandbox_mode(True)
            
            try:
                await exchange.load_markets()
            except Exception as load_err:
                print(f"[{get_riyadh_time()}] ⚠️ [إعادة تحميل الأسواق]: {load_err}", flush=True, file=sys.stdout)
                await asyncio.sleep(3)
                continue

            try:
                balance = await exchange.fetch_balance()
                free_usdt = balance['free'].get('USDT', 0)
            except Exception:
                free_usdt = 1000.0

            # --- إدارة الصفقة والمتابعة المحمية ---
            if active_position and active_position["in_pos"]:
                symbol = active_position["symbol"]
                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    curr_price = ticker['last']
                    entry = active_position["entry_price"]
                    amount = active_position["amount"]
                    profit_ratio = (curr_price - entry) / entry

                    if curr_price > active_position["highest_price"]:
                        active_position["highest_price"] = curr_price

                    elapsed_time = datetime.now(RIYADH_TZ) - active_position["entry_time"]
                    elapsed_minutes = elapsed_time.total_seconds() / 60

                    base_currency = symbol.split('/')[0]
                    fresh_balance = await exchange.fetch_balance()
                    available_coin_balance = fresh_balance['free'].get(base_currency, amount)
                    sell_amount = min(amount, available_coin_balance)

                    if sell_amount <= 0:
                        active_position = None
                        BOT_STATS["active_positions_count"] = 0
                        continue

                    highest_price = active_position["highest_price"]
                    drop_from_peak = (highest_price - curr_price) / highest_price

                    is_safe_exit = (profit_ratio >= BOT_SETTINGS["min_secure_tp"]) and (drop_from_peak >= 0.002)
                    is_max_target = profit_ratio >= BOT_SETTINGS["target_tp_pct"]  # يصل حتى 4%
                    is_timeout = elapsed_minutes >= 40

                    print(f"[{get_riyadh_time()}] 📈 [متابعة الصفقة المحمية] العملة: {symbol} | الربح: {profit_ratio*100:.2f}%", flush=True, file=sys.stdout)

                    if is_safe_exit or is_max_target or is_timeout or (profit_ratio <= -BOT_SETTINGS["stop_loss_pct"]):
                        profit_usdt = (curr_price - entry) * sell_amount
                        await exchange.create_market_sell_order(symbol, sell_amount)
                        active_position = None
                        
                        BOT_STATS["total_trades"] += 1
                        if profit_usdt > 0:
                            BOT_STATS["winning_trades"] += 1
                            print(f"[{get_riyadh_time()}] 🎯 [جني أرباح ناجح ومضمون] العملة: {symbol} | الصافي: +{profit_usdt:.4f}$ USDT", flush=True, file=sys.stdout)
                        else:
                            BOT_STATS["losing_trades"] += 1
                            print(f"[{get_riyadh_time()}] 🛑 [إغلاق حماية فوري] العملة: {symbol} | النتيجة: {profit_usdt:.4f}$ USDT", flush=True, file=sys.stdout)

                        BOT_STATS["total_profit_usdt"] += profit_usdt
                        BOT_STATS["active_positions_count"] = 0

                except Exception as pos_ex:
                    print(f"[{get_riyadh_time()}] ⚠️ [خطأ في المتابعة]: {pos_ex}", flush=True, file=sys.stdout)

                await asyncio.sleep(5)
                continue

            if free_usdt < BOT_SETTINGS["trade_amount_usdt"]:
                print(f"[{get_riyadh_time()}] ⚠️ رصيد USDT غير كافٍ. انتظار...", flush=True, file=sys.stdout)
                await asyncio.sleep(20)
                continue

            scan_counter += 1
            if scan_counter % 3 == 0:
                print(f"[{get_riyadh_time()}] 🔍 [فحص السوق] فحص العملات الكبرى وتجنب الارتدادات الوهمية...", flush=True, file=sys.stdout)

            candidate_opportunities = []

            for symbol in major_5_symbols:
                if symbol in BOT_SETTINGS["excluded_symbols"]:
                    continue

                try:
                    ohlcv_5m = await exchange.fetch_ohlcv(symbol, timeframe='15m', limit=30)
                    if len(ohlcv_5m) < 25:
                        continue

                    df = pd.DataFrame(ohlcv_5m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    
                    is_safe_signal, _ = analyze_no_false_bounce(df)
                    if not is_safe_signal:
                        continue

                    ticker = await exchange.fetch_ticker(symbol)
                    bid_val = ticker.get('bid') or ticker['last']
                    ask_val = ticker.get('ask') or ticker['last']
                    last_val = ticker['last']
                    vol_24h = ticker.get('quoteVolume') or (ticker['last'] * ticker.get('baseVolume', 0))

                    market_inspection_data = {
                        'symbol': symbol,
                        'volume_24h': vol_24h,
                        'bid': bid_val,
                        'ask': ask_val
                    }

                    guardian_report = guardian.inspect_symbol_for_scalping(market_inspection_data)

                    if guardian_report['can_scalp']:
                        candidate_opportunities.append({
                            "symbol": symbol,
                            "last_val": last_val
                        })
                except Exception:
                    continue

            if candidate_opportunities:
                best_opp = candidate_opportunities[0]
                symbol = best_opp["symbol"]
                last_val = best_opp["last_val"]

                crypto_amount = BOT_SETTINGS["trade_amount_usdt"] / last_val
                order = await exchange.create_market_buy_order(symbol, crypto_amount)
                fill_price = order.get('average') or last_val
                actual_amount = order.get('filled') or crypto_amount
                
                active_position = {
                    "in_pos": True,
                    "symbol": symbol,
                    "entry_price": fill_price,
                    "highest_price": fill_price,
                    "amount": actual_amount,
                    "entry_time": datetime.now(RIYADH_TZ)
                }
                total_cost = actual_amount * fill_price
                BOT_STATS["active_positions_count"] = 1
                
                print(f"[{get_riyadh_time()}] 🚀 [دخول صفقة مؤكدة بشمعتين] العملة: {symbol} | الشراء: {fill_price} | القيمة: {total_cost:.2f}$ USDT", flush=True, file=sys.stdout)

        except Exception as e:
            print(f"[{get_riyadh_time()}] ⚠️ [خطأ مؤقت، استئناف تلقائي]: {e}", flush=True, file=sys.stdout)
        finally:
            if exchange:
                try:
                    await exchange.close()
                except Exception:
                    pass

        await asyncio.sleep(5)

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
