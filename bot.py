import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import os
import aiohttp
from aiohttp import web
from datetime import datetime, timezone, timedelta

# --- توقيت مدينة الرياض (GMT+3) ---
RIYADH_TZ = timezone(timedelta(hours=3))

def get_riyadh_time():
    return datetime.now(RIYADH_TZ).strftime('%Y-%m-%d %I:%M:%S %p')

# --- إعدادات التحكم المتقدمة للنظام المدمج ---
BOT_SETTINGS = {
    "is_running": True,                  
    "trade_amount_usdt": 10.0,           
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

# --- خادم الويب لمنع السكون ---
async def handle(request):
    status_str = "🟢 شغال" if BOT_SETTINGS["is_running"] else "🔴 متوقف"
    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>السوبر بوت المدمج (سكالبينج + حارس + حيتان)</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #0d1117; color: #c9d1d9; text-align: center; padding: 20px; }}
            .card {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 20px; margin: 15px auto; max-width: 500px; }}
            h1 {{ color: #58a6ff; }}
            .stat {{ font-size: 18px; margin: 10px 0; }}
            .profit {{ color: #3fb950; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🚀 السوبر بوت المدمج يعمل بكفاءة تامة بتوقيت الرياض</h1>
        <div class="card">
            <div class="stat">حالة البوت: <b>{status_str}</b></div>
            <div class="stat">رأس المال للصفقة: <b>${BOT_SETTINGS['trade_amount_usdt']} USDT</b></div>
            <div class="stat">الأرباح الإجمالية: <span class="profit">${BOT_STATS['total_profit_usdt']:.4f} USDT</span></div>
            <div class="stat">الصفقات الناجحة: <b>{BOT_STATS['winning_trades']}</b> | الخاسرة: <b>{BOT_STATS['losing_trades']}</b></div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 [{get_riyadh_time()}] [خادم الويب] يعمل على المنفذ {port}", flush=True)

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

# --- 1. بوت محلل الأخبار وتتبع الحيتان والسيولة (Whale & Sentiment Engine) ---
def whale_and_sentiment_audit(df, symbol):
    """
    يتتبع تدفقات الحيتان، رصد أحجام التداول الذكية، والتحقق من عدم وجود تلاعبات أو فومو عنيف.
    """
    try:
        # أ) فحص تدفق سيولة الحيتان (Volume Spike مفاجئ مع استقرار)
        avg_volume = df['volume'].rolling(window=15).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        if avg_volume < 800 or current_volume < (avg_volume * 1.5):
            return False # لا توجد سيولة حيتان كافية

        # ب) التحقق من عدم وجود هلع بيعي أو صعود جنوني وهمي (Fomo/Panic)
        last_candle_change = abs(df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1]
        if last_candle_change > 0.025:
            print(f"[{get_riyadh_time()}] 📰 [محلل الحيتان والأخبار] حظر {symbol}: تم رصد تذبذب أو فومو عنيف مخادع.", flush=True)
            return False

        print(f"[{get_riyadh_time()}] 🐋 [محلل الحيتان والأخبار] رصد تدفق سيولة إيجابي وتراكم نظيف على: {symbol}", flush=True)
        return True
    except Exception as e:
        return False

# --- 2. البوت المراقب الحارس (Guardian Supervisor) ---
def guardian_supervisor_audit(df, symbol):
    """
    يفحص الشارت ويكشف الفخاخ، السوق العرضي الميت، ويؤكد إشارات السكالبينج الحقيقية.
    """
    try:
        # أ) فحص السوق العرضي الميت عبر (ATR)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['close'].shift())
        df['tr3'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        atr = df['tr'].rolling(window=14).mean().iloc[-1]
        price_now = df['close'].iloc[-1]
        
        if (atr / price_now) < 0.001:
            print(f"[{get_riyadh_time()}] 🛡️ [الحارس الذكي] حظر {symbol}: حركة الشموع ضيقة جداً (سوق عرضي ميت).", flush=True)
            return False

        # ب) مؤشرات الاتجاه والزخم (EMA 50 + MACD)
        df['ema_trend'] = df['close'].ewm(span=50, adjust=False).mean()
        df['macd'], df['signal'] = calculate_macd(df['close'])

        trend_line = df['ema_trend'].iloc[-1]
        macd_val = df['macd'].iloc[-1]
        sig_val = df['signal'].iloc[-1]
        prev_macd = df['macd'].iloc[-2]
        prev_sig = df['signal'].iloc[-2]

        is_uptrend = price_now > trend_line
        macd_cross_up = (prev_macd <= prev_sig) and (macd_val > sig_val)

        if not (is_uptrend and macd_cross_up):
            return False

        print(f"[{get_riyadh_time()}] 🛡️ [الحارس الذكي] اجتاز الفحص الفني بنجاح: {symbol}", flush=True)
        return True
    except Exception as e:
        return False

# --- 3. المحرك المدمج الرئيسي (Super Bot Engine) ---
async def unified_scalping_bot():
    print(f"[{get_riyadh_time()}] 🚀 [السوبر بوت المدمج] يعمل بكامل طاقته (سكالبينج + حارس + تتبع حيتان)...", flush=True)
    active_positions = {}

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

            all_symbols = [symbol for symbol in exchange.markets if symbol.endswith('/USDT') and not symbol.endswith(':USDT')]
            stable_coins = ['USDC/USDT', 'DAI/USDT', 'TUSD/USDT', 'USDP/USDT']
            target_watchlist = [s for s in all_symbols if s not in stable_coins]

            for symbol in target_watchlist:
                if symbol in BOT_SETTINGS["excluded_symbols"]:
                    continue

                try:
                    ohlcv_5m = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=60)
                    if len(ohlcv_5m) < 50:
                        continue

                    df = pd.DataFrame(ohlcv_5m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    price_now = df['close'].iloc[-1]

                    if symbol not in active_positions or not active_positions[symbol]["in_pos"]:
                        # الربط المرتب: أولاً فحص الحيتان والسيولة، ثانياً فحص الحارس التقني
                        is_whale_approved = whale_and_sentiment_audit(df, symbol)
                        if is_whale_approved:
                            is_guardian_approved = guardian_supervisor_audit(df, symbol)

                            if is_guardian_approved:
                                crypto_amount = BOT_SETTINGS["trade_amount_usdt"] / price_now
                                order = await exchange.create_market_buy_order(symbol, crypto_amount)
                                fill_price = order.get('average') or price_now
                                actual_amount = order.get('filled') or crypto_amount
                                
                                active_positions[symbol] = {
                                    "in_pos": True,
                                    "entry_price": fill_price,
                                    "amount": actual_amount
                                }
                                total_cost = actual_amount * fill_price
                                BOT_STATS["active_positions_count"] = sum(1 for p in active_positions.values() if p["in_pos"])
                                
                                print(f"[{get_riyadh_time()}] 🟢 [صفقة ناجحة مؤكدة] {symbol} | السعر: {fill_price} | التكلفة: {total_cost:.2f}$ USDT", flush=True)

                except Exception as ex:
                    continue

            # متابعة الصفقات المفتوحة وحمايتها بأهداف TP و SL
            for symbol, pos in list(active_positions.items()):
                if pos["in_pos"]:
                    if symbol in BOT_SETTINGS["excluded_symbols"]:
                        continue

                    try:
                        ticker = await exchange.fetch_ticker(symbol)
                        curr_price = ticker['last']
                        entry = pos["entry_price"]
                        amount = pos["amount"]
                        profit_ratio = (curr_price - entry) / entry

                        if profit_ratio >= BOT_SETTINGS["target_tp_pct"]:
                            profit_usdt = (curr_price - entry) * amount
                            await exchange.create_market_sell_order(symbol, amount)
                            active_positions[symbol]["in_pos"] = False
                            
                            BOT_STATS["total_trades"] += 1
                            BOT_STATS["winning_trades"] += 1
                            BOT_STATS["total_profit_usdt"] += profit_usdt
                            BOT_STATS["active_positions_count"] = sum(1 for p in active_positions.values() if p["in_pos"])
                            
                            print(f"[{get_riyadh_time()}] 🎯 [تحقق هدف الربح TP] {symbol} | بنسبة +{profit_ratio*100:.2f}% | الربح: +{profit_usdt:.4f}$ USDT", flush=True)

                        elif profit_ratio <= -BOT_SETTINGS["stop_loss_pct"]:
                            loss_usdt = (curr_price - entry) * amount
                            await exchange.create_market_sell_order(symbol, amount)
                            active_positions[symbol]["in_pos"] = False
                            
                            BOT_STATS["total_trades"] += 1
                            BOT_STATS["losing_trades"] += 1
                            BOT_STATS["total_profit_usdt"] += loss_usdt
                            BOT_STATS["active_positions_count"] = sum(1 for p in active_positions.values() if p["in_pos"])
                            
                            print(f"[{get_riyadh_time()}] 🛑 [وقف خسارة SL] {symbol} | بنسبة {profit_ratio*100:.2f}% | الخسارة: {loss_usdt:.4f}$ USDT", flush=True)

                    except Exception as pos_ex:
                        print(f"[{get_riyadh_time()}] ❌ [خطأ في الصفقة] {symbol}: {pos_ex}", flush=True)

        except Exception as e:
            print(f"[{get_riyadh_time()}] ❌ [خطأ رئيسي في الدورة]: {e}", flush=True)
        finally:
            if exchange:
                try:
                    await exchange.close()
                except Exception:
                    pass

        await asyncio.sleep(15)

async def main():
    await asyncio.gather(
        start_web_server(),
        self_ping_loop(),
        unified_scalping_bot()
    )

if __name__ == '__main__':
    asyncio.run(main())
