import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import os
import aiohttp
from aiohttp import web

# --- إعدادات التحكم المتقدمة ---
BOT_SETTINGS = {
    "is_running": True,                  
    "trade_amount_usdt": 10.0,           
    "target_tp_pct": 0.006,              
    "excluded_symbols": []               
}

BOT_STATS = {
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_profit_usdt": 0.0,
    "total_profit_pct": 0.0,
    "active_positions_count": 0
}

# --- خادم الويب ---
async def handle(request):
    status_str = "🟢 شغال" if BOT_SETTINGS["is_running"] else "🔴 متوقف"
    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>مراقب البوت الذاتي</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #0d1117; color: #c9d1d9; text-align: center; padding: 20px; }}
            .card {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 20px; margin: 15px auto; max-width: 500px; }}
            h1 {{ color: #58a6ff; }}
            .stat {{ font-size: 18px; margin: 10px 0; }}
            .profit {{ color: #3fb950; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🚀 البوت يعمل ذاتياً 24/7</h1>
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
    print(f"🌐 [خادم الويب] يعمل على المنفذ {port}", flush=True)

# --- نظام الحفاظ على النشاط ذاتياً ---
async def self_ping_loop():
    await asyncio.sleep(10)
    port = os.environ.get("PORT", 10000)
    render_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
    print(f"🔄 [النظام الذاتي] بدأ إرسال نبضات النشاط إلى: {render_url}", flush=True)
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(render_url) as resp:
                    pass
            except Exception:
                pass
            await asyncio.sleep(240)

# --- إعدادات منصة OKX والتداول ---
API_KEY = '2bf148cb-c010-49fb-bffc-79f72720dfae'
SECRET_KEY = '1FBA3210BF6500BB1A1570EE9EC41A5C'
PASSPHRASE = 'Aa11223344##'
STOP_LOSS_PCT = 0.004

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- المحرك الرئيسي الذكي للتداول مع طباعة تفصيلية في الـ Logs ---
async def unified_scalping_bot():
    print("🚀 [محرك التداول الصامت] يعمل بكامل الميزات الذكية...", flush=True)
    active_positions = {}
    target_watchlist = ['BTC/USDT', 'SOL/USDT', 'ETH/USDT', 'DOGE/USDT', 'XRP/USDT', 'ADA/USDT']

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

            for symbol in target_watchlist:
                if symbol in BOT_SETTINGS["excluded_symbols"]:
                    continue

                try:
                    ohlcv_5m = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=35)
                    if len(ohlcv_5m) < 30:
                        continue

                    df = pd.DataFrame(ohlcv_5m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    df['ema_fast'] = df['close'].ewm(span=9, adjust=False).mean()
                    df['ema_slow'] = df['close'].ewm(span=21, adjust=False).mean()
                    df['rsi'] = calculate_rsi(df['close'], period=14)

                    prev_close = df['close'].iloc[-1]
                    ema_fast = df['ema_fast'].iloc[-1]
                    ema_slow = df['ema_slow'].iloc[-1]
                    rsi_val = df['rsi'].iloc[-1]

                    is_opportunity = (ema_fast > ema_slow) and (rsi_val < 55)

                    if symbol not in active_positions or not active_positions[symbol]["in_pos"]:
                        if is_opportunity:
                            crypto_amount = BOT_SETTINGS["trade_amount_usdt"] / prev_close
                            order = await exchange.create_market_buy_order(symbol, crypto_amount)
                            fill_price = order.get('average') or prev_close
                            actual_amount = order.get('filled') or crypto_amount
                            
                            active_positions[symbol] = {
                                "in_pos": True,
                                "entry_price": fill_price,
                                "amount": actual_amount
                            }
                            total_cost = actual_amount * fill_price
                            BOT_STATS["active_positions_count"] = sum(1 for p in active_positions.values() if p["in_pos"])
                            
                            print(f"\n🟢 [فتح صفقة جديدة] العملة: {symbol} | سعر الدخول: {fill_price} | القيمة: {total_cost:.2f} USDT", flush=True)

                except Exception as ex:
                    print(f"⚠️ خطأ في العملة {symbol}: {ex}", flush=True)

            # متابعة الصفقات المفتوحة وطباعة النتيجة فوراً في الـ Logs عند الإغلاق
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
                            BOT_STATS["total_profit_pct"] += (profit_ratio * 100)
                            BOT_STATS["active_positions_count"] = sum(1 for p in active_positions.values() if p["in_pos"])
                            
                            print(f"\n🎯 [جني أرباح بنجاح] العملة: {symbol} | النسبة: +{profit_ratio*100:.2f}% | الربح: +{profit_usdt:.4f} USDT | إجمالي أرباح البوت: {BOT_STATS['total_profit_usdt']:.4f} USDT", flush=True)

                        elif profit_ratio <= -STOP_LOSS_PCT:
                            loss_usdt = (curr_price - entry) * amount
                            await exchange.create_market_sell_order(symbol, amount)
                            active_positions[symbol]["in_pos"] = False
                            
                            BOT_STATS["total_trades"] += 1
                            BOT_STATS["losing_trades"] += 1
                            BOT_STATS["total_profit_usdt"] += loss_usdt
                            BOT_STATS["total_profit_pct"] += (profit_ratio * 100)
                            BOT_STATS["active_positions_count"] = sum(1 for p in active_positions.values() if p["in_pos"])
                            
                            print(f"\n🛑 [وقف خسارة] العملة: {symbol} | النسبة: {profit_ratio*100:.2f}% | الخسارة: {loss_usdt:.4f} USDT | إجمالي أرباح البوت: {BOT_STATS['total_profit_usdt']:.4f} USDT", flush=True)

                    except Exception as pos_ex:
                        print(f"⚠️ خطأ في متابعة الصفقة {symbol}: {pos_ex}", flush=True)

        except Exception as e:
            print(f"❌ خطأ عام في دورة التداول: {e}", flush=True)
        finally:
            if exchange:
                try:
                    await exchange.close()
                except Exception:
                    pass

        await asyncio.sleep(10)

# --- التشغيل الجماعي ---
async def main():
    await asyncio.gather(
        start_web_server(),
        self_ping_loop(),
        unified_scalping_bot()
    )

if __name__ == '__main__':
    asyncio.run(main())
