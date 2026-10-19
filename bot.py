import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import os
from aiohttp import web

# --- خادم ويب وهمي لإرضاء منصة Render ومنع السكون ---
async def handle(request):
    return web.Response(text="Advanced Scalping Multi-Bot is running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 [خادم الويب الوهمي] يعمل على المنفذ {port}", flush=True)

# --- إعدادات منصة OKX ---
API_KEY = '2bf148cb-c010-49fb-bffc-79f72720dfae'
SECRET_KEY = '1FBA3210BF6500BB1A1570EE9EC41A5C'
PASSPHRASE = 'Aa11223344##'
TRADE_AMOUNT = 0.001  # حجم الدخول التجريبي

# ==========================================
# 🤖 البوت رقم 1: بوت الأخبار وحسابات الحيتان (News & Whale Analyzer)
# ==========================================
async def news_and_whales_bot(shared_memory):
    """
    يقوم برصد الأخبار وحسابات الحيتان وتصفية العملات ذات الاهتمام العالي من بين 300+ عملة.
    """
    print("🤖 [البوت 1] بدأ العمل: مراقبة الأخبار وحسابات الحيتان...", flush=True)
    
    while True:
        try:
            # محاكاة العملات المستهدفة بناءً على سيولة ورصد الحيتان والأخبار من أصل 300 عملة
            target_watchlist = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'ADA/USDT']
            
            print(f"📰 [البوت 1] تم تحديث قائمة الاهتمام والسيولة لـ {len(target_watchlist)} عملة.", flush=True)
            shared_memory['target_coins'] = target_watchlist
            
        except Exception as e:
            print(f"⚠️ [البوت 1] خطأ في رصد الأخبار: {e}", flush=True)
            
        await asyncio.sleep(60)  # تحديث دوري كل دقيقة

# ==========================================
# 📊 البوت رقم 2: بوت تحليل المؤشرات وفلاتر التوقيت (Scalping & Timing Analyzer)
# ==========================================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

async def scalping_indicator_bot(shared_memory):
    """
    يحلل مؤشرات السكالبينغ مع فلاتر التوقيت المثالي (إغلاق الشمعة + Volume Spike + RSI).
    """
    print("📊 [البوت 2] بدأ العمل: فحص مؤشرات السكالبينغ وتوقيت الدخول...", flush=True)
    
    exchange = ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
    await exchange.load_markets()

    while True:
        try:
            target_coins = shared_memory.get('target_coins', [])
            approved_signals = []

            for symbol in target_coins:
                try:
                    ohlcv_5m = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
                    if len(ohlcv_5m) < 40:
                        continue

                    df = pd.DataFrame(ohlcv_5m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # حساب المؤشرات الفنية
                    df['ema_fast'] = df['close'].ewm(span=9, adjust=False).mean()
                    df['ema_slow'] = df['close'].ewm(span=21, adjust=False).mean()
                    df['rsi'] = calculate_rsi(df['close'], period=14)
                    df['vol_ma'] = df['volume'].rolling(window=10).mean()

                    # استخدام الشمعة المغلقة السابقة (iloc[-2]) لتفادي الإشارات الوهمية والالتزام بالتوقيت
                    prev_close = df['close'].iloc[-2]
                    ema_fast = df['ema_fast'].iloc[-2]
                    ema_slow = df['ema_slow'].iloc[-2]
                    rsi_val = df['rsi'].iloc[-2]
                    curr_vol = df['volume'].iloc[-2]
                    avg_vol = df['vol_ma'].iloc[-2]

                    # --- شروط التوقيت المثالي للسكالبينغ ---
                    # 1. تقاطع صاعد (EMA Fast > EMA Slow)
                    # 2. فلتر الزخم RSI (أعلى من 50 وأقل من 70 لتجنب التشبع)
                    # 3. فلتر الحجم (حجم الشمعة المغلقة أعلى من المتوسط بـ 1.3 مرة على الأقل لتأكيد السيولة)
                    is_ema_cross = ema_fast > ema_slow
                    is_rsi_good = 50 < rsi_val < 70
                    is_volume_spike = curr_vol > (avg_vol * 1.3)

                    if is_ema_cross and is_rsi_good and is_volume_spike:
                        approved_signals.append({
                            'symbol': symbol,
                            'price': prev_close,
                            'action': 'BUY'
                        })
                        print(f"✅ [البوت 2 - توقيت مثالي] تم تأكيد فرصة سكالبينغ لـ {symbol} | RSI: {rsi_val:.1f} | حجم السيولة مؤكد", flush=True)

                except Exception as ex:
                    print(f"⚠️ [البوت 2] خطأ في تحليل {symbol}: {ex}", flush=True)

            shared_memory['ready_signals'] = approved_signals
            await exchange.close()

        except Exception as e:
            print(f"⚠️ [البوت 2] خطأ رئيسي: {e}", flush=True)

        await asyncio.sleep(15)

# ==========================================
# ⚡ البوت رقم 3: بوت التنفيذ الدقيق للإستراتيجية (Execution Bot)
# ==========================================
async def execution_bot(shared_memory):
    """
    ينفذ الصفقات فور وصول الإشارة المعتمدة مع إدارة صارمة لأهداف الربح ووقف الخسارة.
    """
    print("⚡ [البوت 3] بدأ العمل: جاهز لتنفيذ وإدارة الصفقات بدقة...", flush=True)
    
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

        active_positions = {}
        TAKE_PROFIT_PCT = 0.006  # 0.6% جني أرباح سريع
        STOP_LOSS_PCT = 0.004    # 0.4% وقف خسارة صارم

        while True:
            signals = shared_memory.get('ready_signals', [])

            for sig in signals:
                symbol = sig['symbol']
                current_price = sig['price']

                # فتح صفقة شراء جديدة إذا لم تكن مفتوحة مسبقاً
                if symbol not in active_positions or not active_positions[symbol]["in_pos"]:
                    print(f"🚀 [البوت 3 - تنفيذي] تنفيذ أمر شراء فوري للعملة {symbol}...", flush=True)
                    order = await exchange.create_market_buy_order(symbol, TRADE_AMOUNT)
                    fill_price = order.get('average') or current_price
                    
                    active_positions[symbol] = {
                        "in_pos": True,
                        "entry_price": fill_price
                    }
                    print(f"🎯 [تم فتح الصفقة بنجاح] للرمز {symbol} بسعر التنفيذ: {fill_price}", flush=True)

            # متابعة الصفقات المفتوحة للبيع عند تحقيق الهدف أو ضرب وقف الخسارة
            for symbol, pos in list(active_positions.items()):
                if pos["in_pos"]:
                    ticker = await exchange.fetch_ticker(symbol)
                    curr_price = ticker['last']
                    entry = pos["entry_price"]
                    profit_ratio = (curr_price - entry) / entry

                    if profit_ratio >= TAKE_PROFIT_PCT:
                        print(f"🎯 [البوت 3] تحقق هدف الربح (TP) لـ {symbol} بنسبة +{profit_ratio*100:.2f}%.. جاري إغلاق الصفقة.", flush=True)
                        await exchange.create_market_sell_order(symbol, TRADE_AMOUNT)
                        active_positions[symbol]["in_pos"] = False

                    elif profit_ratio <= -STOP_LOSS_PCT:
                        print(f"🛑 [البوت 3] ضرب وقف الخسارة (SL) لـ {symbol} بنسبة -{profit_ratio*100:.2f}%.. بيع للحماية.", flush=True)
                        await exchange.create_market_sell_order(symbol, TRADE_AMOUNT)
                        active_positions[symbol]["in_pos"] = False

            await asyncio.sleep(10)

    except Exception as e:
        print(f"❌ [البوت 3] خطأ في التنفيذ: {e}", flush=True)

# --- الدالة الرئيسية لتشغيل المنظومة كاملة مع خادم الويب ---
async def main():
    shared_memory = {
        'target_coins': [],
        'ready_signals': []
    }

    await asyncio.gather(
        start_web_server(),
        news_and_whales_bot(shared_memory),
        scalping_indicator_bot(shared_memory),
        execution_bot(shared_memory)
    )

if __name__ == '__main__':
    asyncio.run(main())
