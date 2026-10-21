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
        <head><meta charset="UTF-8"><title>السوبر بوت المحترف لصيد القيعان</title></head>
        <body style="background:#0d1117; color:#c9d1d9; text-align:center; font-family:Arial; padding:50px;">
            <h1>🚀 السوبر بوت (فلتر منع التذبذب الجانبي + صيد القيعان + أرباح 0.5% إلى 3%) يعمل بتوقيت الرياض</h1>
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
    "target_tp_pct": 0.03,               # الحد الأقصى لجني الأرباح المفتوح حتى 3.0%[span_2](start_span)[span_2](end_span)
    "min_secure_tp": 0.005,              # الخروج الآمن عند التوقف (0.5%)[span_3](start_span)[span_3](end_span)
    "stop_loss_pct": 0.006,              # وقف خسارة محمي (0.6%)[span_4](start_span)[span_4](end_span)
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

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

# --- فلتر منع التذبذب الجانبي واصطياد القاع الحقيقي ---
def analyze_no_choppy_dip_rebound(df):
    """
    يتأكد البوت من أن السوق ليس في حالة تذبذب عرضي أو جانبي،
    بل هبط بقوة ثم شكل قاعاً حقيقياً وبدأت شمعة صعود واضحة وقوية.
    """
    try:
        if len(df) < 8:
            return False, "بيانات غير كافية"

        # 1. فلتر منع التذبذب الجانبي: قياس مدى الحركة (ATR أو نطاق التذبذب الأخير)
        recent_highs = df['high'].iloc[-6:-1].max()
        recent_lows = df['low'].iloc[-6:-1].min()
        total_span = recent_highs - recent_lows
        current_price = df['close'].iloc[-1]

        if total_span <= 0:
            return False, "تذبذب معدوم"

        # 2. التأكد من حدوث هبوط حقيقي سابق ثم ارتداد صعودي واضح
        is_previous_dropping = df['close'].iloc[-3] < df['close'].iloc[-5]
        
        curr_open = df['open'].iloc[-1]
        curr_close = df['close'].iloc[-1]
        curr_high = df['high'].iloc[-1]
        curr_low = df['low'].iloc[-1]

        is_green = curr_close > curr_open
        body_size = abs(curr_close - curr_open)
        total_candle_range = curr_high - curr_low
        
        if total_candle_range == 0:
            return False, "مدى الشمعة صفر"

        body_ratio = body_size / total_candle_range
        
        # الشرط الحاسم: هبوط سابق + شمعة خضراء قوية وواضحة وليست ضمن تذبذب ضيق وممل
        is_valid_rebound = is_previous_dropping and is_green and (body_ratio > 0.40)

        if is_valid_rebound:
            return True, "تم تجاوز التذبذب ورصد قاع حقيقي"

        return False, "منطقة تذبذب أو انتظار القاع"
    except Exception:
        return False, "خطأ في تحليل السوق"

class ScalpingGuardian:
    def __init__(self, min_volume=3_000_000, max_spread_pct=0.10, min_volatility_pct=0.12):
        self.min_volume = min_volume
        self.max_spread_pct = max_spread_pct
        self.min_volatility_pct = min_volatility_pct

    def inspect_symbol_for_scalping(self, data):
        symbol = data.get('symbol', 'UNKNOWN')
        volume = data.get('volume_24h', 0)
        bid = data.get('bid', 0)
        ask = data.get('ask', 0)
        last_price = data.get('last_price', 0)
        atr_5m = data.get('atr_5m', 0)

        spread_pct = ((ask - bid) / ask * 100) if ask > 0 else 999.0
        volatility_pct = (atr_5m / last_price * 100) if last_price > 0 else 0.0

        is_ready = True
        if volume < self.min_volume or spread_pct > self.max_spread_pct or volatility_pct < self.min_volatility_pct:
            is_ready = False

        return {"symbol": symbol, "can_scalp": is_ready}

guardian = ScalpingGuardian()

def whale_and_sentiment_audit(df, symbol):
    try:
        avg_volume = df['volume'].rolling(window=15).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        if avg_volume < 400 or current_volume < (avg_volume * 1.15):
            return False
        return True
    except Exception:
        return False

# --- المحرك الذكي المطور لمنع التذبذب ---
async def unified_scalping_bot():
    print(f"[{get_riyadh_time()}] 🚀 [السوبر بوت المانع للتذبذب] يعمل بكفاءة عالية لاصطياد القيعان الحقيقية...", flush=True, file=sys.stdout)
    active_position = None  

    top_10_symbols = [
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 
        'DOGE/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'NEAR/USDT'
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
            await exchange.load_markets()

            try:
                balance = await exchange.fetch_balance()
                free_usdt = balance['free'].get('USDT', 0)
            except Exception:
                free_usdt = 1000.0

            # --- إدارة الصفقة والمراقبة اللحظية لمنع الهبوط المفاجئ ---
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

                    is_safe_exit_on_weakness = (profit_ratio >= BOT_SETTINGS["min_secure_tp"]) and (drop_from_peak >= 0.0018)
                    is_max_target = profit_ratio >= BOT_SETTINGS["target_tp_pct"]
                    is_timeout = elapsed_minutes >= 20

                    print(f"[{get_riyadh_time()}] 📈 [متابعة الصفقة بعيداً عن التذبذب] العملة: {symbol} | القمة: {highest_price} | الربح: {profit_ratio*100:.2f}%", flush=True, file=sys.stdout)

                    if is_safe_exit_on_weakness or is_max_target or is_timeout or (profit_ratio <= -BOT_SETTINGS["stop_loss_pct"]):
                        profit_usdt = (curr_price - entry) * sell_amount
                        await exchange.create_market_sell_order(symbol, sell_amount)
                        active_position = None
                        
                        BOT_STATS["total_trades"] += 1
                        if profit_usdt > 0:
                            BOT_STATS["winning_trades"] += 1
                            print(f"[{get_riyadh_time()}] 🎯 [جني أرباح ناجح] العملة: {symbol} | سعر البيع: {curr_price} | نسبة الربح: +{profit_ratio*100:.2f}% | الصافي: +{profit_usdt:.4f}$ USDT", flush=True, file=sys.stdout)
                        else:
                            BOT_STATS["losing_trades"] += 1
                            print(f"[{get_riyadh_time()}] 🛑 [إغلاق حماية طارئ] العملة: {symbol} | سعر البيع: {curr_price} | النسبة: {profit_ratio*100:.2f}% | النتيجة: {profit_usdt:.4f}$ USDT", flush=True, file=sys.stdout)

                        BOT_STATS["total_profit_usdt"] += profit_usdt
                        BOT_STATS["active_positions_count"] = 0

                except Exception as pos_ex:
                    print(f"[{get_riyadh_time()}] ⚠️ [خطأ في المتابعة]: {pos_ex}", flush=True, file=sys.stdout)

                await asyncio.sleep(3)
                continue

            if free_usdt < BOT_SETTINGS["trade_amount_usdt"]:
                print(f"[{get_riyadh_time()}] ⚠️ رصيد USDT المتاح ({free_usdt:.2f}$) أقل من رأس المال (${BOT_SETTINGS['trade_amount_usdt']}). انتظار...", flush=True, file=sys.stdout)
                await asyncio.sleep(15)
                continue

            scan_counter += 1
            if scan_counter % 3 == 0:
                print(f"[{get_riyadh_time()}] 🔍 [فحص السوق وتصفية التذبذب] جارٍ البحث عن فرص حقيقية بعيداً عن الأسواق الجانبية...", flush=True, file=sys.stdout)

            all_market_symbols = [s for s in exchange.markets if s.endswith('/USDT') and not s.endswith(':USDT')]
            stable_coins = ['USDC/USDT', 'DAI/USDT', 'TUSD/USDT', 'USDP/USDT']
            other_symbols = [s for s in all_market_symbols if s not in stable_coins and s not in top_10_symbols]

            target_watchlist = top_10_symbols + other_symbols
            candidate_opportunities = []

            for symbol in target_watchlist:
                if symbol in BOT_SETTINGS["excluded_symbols"]:
                    continue

                try:
                    ohlcv_5m = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=15)
                    if len(ohlcv_5m) < 10:
                        continue

                    df = pd.DataFrame(ohlcv_5m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    
                    is_clean_signal, _ = analyze_no_choppy_dip_rebound(df)
                    if not is_clean_signal:
                        continue

                    df['tr1'] = df['high'] - df['low']
                    df['tr2'] = abs(df['high'] - df['close'].shift())
                    df['tr3'] = abs(df['low'] - df['close'].shift())
                    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
                    atr_5m_val = df['tr'].rolling(window=5).mean().iloc[-1]

                    ticker = await exchange.fetch_ticker(symbol)
                    bid_val = ticker.get('bid') or ticker['last']
                    ask_val = ticker.get('ask') or ticker['last']
                    last_val = ticker['last']
                    vol_24h = ticker.get('quoteVolume') or (ticker['last'] * ticker.get('baseVolume', 0))

                    market_inspection_data = {
                        'symbol': symbol,
                        'volume_24h': vol_24h,
                        'bid': bid_val,
                        'ask': ask_val,
                        'last_price': last_val,
                        'atr_5m': atr_5m_val
                    }

                    guardian_report = guardian.inspect_symbol_for_scalping(market_inspection_data)
                    is_top_10 = symbol in top_10_symbols
                    passed_extra_filter = True if is_top_10 else whale_and_sentiment_audit(df, symbol)

                    if guardian_report['can_scalp'] and passed_extra_filter:
                        df['macd'], df['signal'] = calculate_macd(df['close'])
                        macd_val = df['macd'].iloc[-1]
                        sig_val = df['signal'].iloc[-1]

                        if macd_val > sig_val:
                            score = (macd_val - sig_val) * (2.0 if is_top_10 else 1.0)
                            candidate_opportunities.append({
                                "symbol": symbol,
                                "last_val": last_val,
                                "score": score,
                                "is_top_10": is_top_10
                            })
                except Exception:
                    continue

            if candidate_opportunities:
                candidate_opportunities.sort(key=lambda x: x["score"], reverse=True)
                best_opp = candidate_opportunities[0]

                symbol = best_opp["symbol"]
                last_val = best_opp["last_val"]
                is_top_10 = best_opp["is_top_10"]

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
                
                print(f"[{get_riyadh_time()}] 🚀 [دخول صفقة نظيفة بعيداً عن التذبذب] العملة: {symbol} | سعر الشراء: {fill_price} | القيمة: {total_cost:.2f}$ USDT", flush=True, file=sys.stdout)

        except Exception as e:
            print(f"[{get_riyadh_time()}] ⚠️ [خطأ واستئناف فوري]: {e}", flush=True, file=sys.stdout)
        finally:
            if exchange:
                try:
                    await exchange.close()
                except Exception:
                    pass

        await asyncio.sleep(3)

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
