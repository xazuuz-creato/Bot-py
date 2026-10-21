import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import os
import aiohttp
from aiohttp import web
from datetime import datetime, timezone, timedelta
from threading import Thread

# --- توقيت مدينة الرياض (GMT+3) ---
RIYADH_TZ = timezone(timedelta(hours=3))

def get_riyadh_time():
    return datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %I:%M:%S %p')

# --- إعدادات التحكم المتقدمة (رأس مال 100 دولار صفقة صفقة) ---
BOT_SETTINGS = {
    "is_running": True,                  
    "trade_amount_usdt": 100.0,          
    "target_tp_pct": 0.008,              # هدف أرباح سكالبينج ذكي (0.8%)
    "stop_loss_pct": 0.004,              # وقف خسارة صارم (0.4%)
    "excluded_symbols": []               
}

BOT_STATS = {
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_profit_usdt": 0.0,
    "active_positions_count": 0
}

# --- خادم الويب لمنع السكون (يعمل فوراً لفتح البورت) ---
async def handle(request):
    status_str = "🟢 شغال" if BOT_SETTINGS["is_running"] else "🔴 متوقف"
    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>السوبر بوت المدمج (جاهز وآمن)</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #0d1117; color: #c9d1d9; text-align: center; padding: 20px; }}
            .card {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 20px; margin: 15px auto; max-width: 500px; }}
            h1 {{ color: #58a6ff; }}
            .stat {{ font-size: 18px; margin: 10px 0; }}
            .profit {{ color: #3fb950; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🚀 السوبر بوت (صفقة واحدة بـ 100$، البورت مفتوح فوري) يعمل بتوقيت الرياض</h1>
        <div class="card">
            <div class="stat">حالة البوت: <b>{status_str}</b></div>
            <div class="stat">رأس مال الصفقة: <b>${BOT_SETTINGS['trade_amount_usdt']} USDT</b></div>
            <div class="stat">الأرباح الإجمالية: <span class="profit">${BOT_STATS['total_profit_usdt']:.4f} USDT</span></div>
            <div class="stat">الصفقات الناجحة: <b>{BOT_STATS['winning_trades']}</b> | الخاسرة: <b>{BOT_STATS['losing_trades']}</b></div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port, print=lambda x: print(f"🌐 [{get_riyadh_time()}] [خادم الويب] يعمل على المنفذ {port}", flush=True))

async def self_ping_loop():
    await asyncio.sleep(10)
    port = int(os.environ.get("PORT", 10000))
    render_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(render_url) as resp:
                    pass
            except Exception:
                pass
            await asyncio.sleep(240)

API_KEY = '2bf148cb-c010-49fb-bffc-79f72720dfae'
SECRET_KEY = '1FBA3210BF6500BB1A1570EE9EC41A5C'
PASSPHRASE = 'Aa11223344##'

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

# --- فئة الحارس المتقدم (ScalpingGuardian) ---
class ScalpingGuardian:
    def __init__(self, min_volume=10_000_000, max_spread_pct=0.08, min_volatility_pct=0.25):
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

        reasons = []
        is_ready = True

        if volume < self.min_volume:
            is_ready = False
            reasons.append(f"سيولة ضعيفة: (${volume:,.0f} أقل من ${self.min_volume:,.0f})")

        if spread_pct > self.max_spread_pct:
            is_ready = False
            reasons.append(f"الفارق (Spread) مرتفع: ({spread_pct:.3f}% أكبر من {self.max_spread_pct}%)")

        if volatility_pct < self.min_volatility_pct:
            is_ready = False
            reasons.append(f"العملة بطيئة/خاملة: (التذبذب {volatility_pct:.2f}% أقل من {self.min_volatility_pct}%)")

        return {
            "symbol": symbol,
            "can_scalp": is_ready,
            "spread_pct": round(spread_pct, 4),
            "volatility_pct": round(volatility_pct, 2),
            "volume_24h": volume,
            "reasons": reasons
        }

guardian = ScalpingGuardian(
    min_volume=5_000_000,     
    max_spread_pct=0.10,       
    min_volatility_pct=0.20    
)

def whale_and_sentiment_audit(df, symbol):
    try:
        avg_volume = df['volume'].rolling(window=15).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        if avg_volume < 800 or current_volume < (avg_volume * 1.3):
            return False

        last_candle_change = abs(df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1]
        if last_candle_change > 0.025:
            return False

        return True
    except Exception as e:
        return False

# --- المحرك الرئيسي المدمج ---
async def unified_scalping_bot():
    print(f"[{get_riyadh_time()}] 🚀 [السوبر بوت الآمن] بدأ العمل بتركيز على أفضل 10 عملات واختيار الفرصة الأضمن...", flush=True)
    active_position = None  

    top_10_symbols = [
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 
        'DOGE/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'NEAR/USDT'
    ]

    while True:
        if not BOT_SETTINGS["is_running"]:
            await asyncio.sleep(5)
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

            if active_position and active_position["in_pos"]:
                symbol = active_position["symbol"]
                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    curr_price = ticker['last']
                    entry = active_position["entry_price"]
                    amount = active_position["amount"]
                    profit_ratio = (curr_price - entry) / entry

                    base_currency = symbol.split('/')[0]
                    fresh_balance = await exchange.fetch_balance()
                    available_coin_balance = fresh_balance['free'].get(base_currency, amount)
                    sell_amount = min(amount, available_coin_balance)

                    if sell_amount <= 0:
                        print(f"[{get_riyadh_time()}] ⚠️ [تنبيه رصيد عملة] رصيد {base_currency} غير متوفر للبيع، إغلاق الحالة المحلياً.", flush=True)
                        active_position = None
                        BOT_STATS["active_positions_count"] = 0
                        continue

                    if profit_ratio >= BOT_SETTINGS["target_tp_pct"]:
                        profit_usdt = (curr_price - entry) * sell_amount
                        await exchange.create_market_sell_order(symbol, sell_amount)
                        active_position = None
                        
                        BOT_STATS["total_trades"] += 1
                        BOT_STATS["winning_trades"] += 1
                        BOT_STATS["total_profit_usdt"] += profit_usdt
                        BOT_STATS["active_positions_count"] = 0
                        
                        print(f"[{get_riyadh_time()}] 🎯 [تحقق هدف الربح TP] {symbol} | بنسبة +{profit_ratio*100:.2f}% | الربح: +{profit_usdt:.4f}$ USDT", flush=True)

                    elif profit_ratio <= -BOT_SETTINGS["stop_loss_pct"]:
                        loss_usdt = (curr_price - entry) * sell_amount
                        await exchange.create_market_sell_order(symbol, sell_amount)
                        active_position = None
                        
                        BOT_STATS["total_trades"] += 1
                        BOT_STATS["losing_trades"] += 1
                        BOT_STATS["total_profit_usdt"] += loss_usdt
                        BOT_STATS["active_positions_count"] = 0

                        print(f"[{get_riyadh_time()}] 🛑 [وقف خسارة SL] {symbol} | بنسبة {profit_ratio*100:.2f}% | الخسارة: {loss_usdt:.4f}$ USDT", flush=True)

                except Exception as pos_ex:
                    print(f"[{get_riyadh_time()}] ❌ [خطأ في متابعة الصفقة الحالية] {symbol}: {pos_ex}", flush=True)

                await asyncio.sleep(15)
                continue

            if free_usdt < BOT_SETTINGS["trade_amount_usdt"]:
                print(f"[{get_riyadh_time()}] ⚠️ [تنبيه رصيد] رصيد الـ USDT المتاح ({free_usdt:.2f}$) أقل من رأس المال المطلوب (${BOT_SETTINGS['trade_amount_usdt']}).", flush=True)
                await asyncio.sleep(30)
                continue

            all_market_symbols = [symbol for symbol in exchange.markets if symbol.endswith('/USDT') and not symbol.endswith(':USDT')]
            stable_coins = ['USDC/USDT', 'DAI/USDT', 'TUSD/USDT', 'USDP/USDT']
            other_symbols = [s for s in all_market_symbols if s not in stable_coins and s not in top_10_symbols]

            target_watchlist = top_10_symbols + other_symbols
            candidate_opportunities = []

            for symbol in target_watchlist:
                if symbol in BOT_SETTINGS["excluded_symbols"]:
                    continue

                try:
                    ohlcv_5m = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=60)
                    if len(ohlcv_5m) < 50:
                        continue

                    df = pd.DataFrame(ohlcv_5m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    
                    df['tr1'] = df['high'] - df['low']
                    df['tr2'] = abs(df['high'] - df['close'].shift())
                    df['tr3'] = abs(df['low'] - df['close'].shift())
                    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
                    atr_5m_val = df['tr'].rolling(window=14).mean().iloc[-1]

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
                    passed_extra_filter = True
                    if not is_top_10:
                        passed_extra_filter = whale_and_sentiment_audit(df, symbol)

                    if guardian_report['can_scalp'] and passed_extra_filter:
                        df['ema_trend'] = df['close'].ewm(span=50, adjust=False).mean()
                        df['macd'], df['signal'] = calculate_macd(df['close'])

                        trend_line = df['ema_trend'].iloc[-1]
                        macd_val = df['macd'].iloc[-1]
                        sig_val = df['signal'].iloc[-1]
                        prev_macd = df['macd'].iloc[-2]
                        prev_sig = df['signal'].iloc[-2]

                        is_uptrend = last_val > trend_line
                        macd_cross_up = (prev_macd <= prev_sig) and (macd_val > sig_val)

                        if is_uptrend and macd_cross_up:
                            macd_strength = macd_val - sig_val
                            score = macd_strength * (2.0 if is_top_10 else 1.0)

                            candidate_opportunities.append({
                                "symbol": symbol,
                                "last_val": last_val,
                                "score": score,
                                "is_top_10": is_top_10
                            })

                except Exception as ex:
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
                    "amount": actual_amount
                }
                total_cost = actual_amount * fill_price
                BOT_STATS["active_positions_count"] = 1
                
                category_str = "⭐ [الأضمن من أفضل 10 عملات]" if is_top_10 else "🔍 [الأضمن من بحر العملات - مؤكدة]"
                print(f"[{get_riyadh_time()}] {category_str} تم اختيار واقتناص الصفقة: {symbol} | السعر: {fill_price} | التكلفة: {total_cost:.2f}$ USDT", flush=True)

        except Exception as e:
            print(f"[{get_riyadh_time()}] ❌ [خطأ رئيسي في الدورة]: {e}", flush=True)
        finally:
            if exchange:
                try:
                    await exchange.close()
                except Exception:
                    pass

        await asyncio.sleep(15)

if __name__ == '__main__':
    # تشغيل خادم الويب في خلفية مستقلة (Background Thread) لضمان فتح البورت فوراً لمنصة Render
    server_thread = Thread(target=run_web_server, daemon=True)
    server_thread.start()

    # تشغيل مهام البوت الأساسية
    asyncio.run(asyncio.gather(
        self_ping_loop(),
        unified_scalping_bot()
    ))
