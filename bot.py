import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import os
import aiohttp
from aiohttp import web

# --- إعدادات تيليجرام ---
TELEGRAM_BOT_TOKEN = '8675421121:AAEM_QnkWC50TNPwnaJlMGSeZ1yl7opvETA'
TELEGRAM_CHAT_ID = '1359566062'

# --- إعدادات التحكم المتقدمة ---
BOT_SETTINGS = {
    "is_running": True,                  # حالة التشغيل العامة
    "trade_amount_usdt": 10.0,           # رأس المال المتاح لكل صفقة (قابل للتعديل)
    "target_tp_pct": 0.006,              # هدف الربح الأساسي (0.6%)
    "excluded_symbols": []               # العملات المستبعدة مؤقتاً بناءً على رغبتك (لا يبيعها أو يشتريها)
}

BOT_STATS = {
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_profit_usdt": 0.0,
    "total_profit_pct": 0.0,
    "active_positions_count": 0
}

# --- دالة إرسال الرسائل إلى تيليجرام ---
async def send_telegram_message(message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                pass
    except Exception as e:
        print(f"⚠️ خطأ في إرسال تيليجرام: {e}", flush=True)

# --- لوحة التحكم التفاعلية المتقدمة ---
async def send_control_panel():
    status_icon = "🟢 شغال" if BOT_SETTINGS["is_running"] else "🔴 متوقف"
    excluded_str = ", ".join(BOT_SETTINGS["excluded_symbols"]) if BOT_SETTINGS["excluded_symbols"] else "لا توجد"
    
    text = (
        f"🎮 **لوحة التحكم الذكية والمتقدمة**\n\n"
        f"📌 **حالة البوت:** {status_icon}\n"
        f"💵 **رأس المال لكل صفقة:** `${BOT_SETTINGS['trade_amount_usdt']} USDT`\n"
        f"🚫 **عملات مستبعدة (محمية):** `{excluded_str}`\n"
        f"📊 **إجمالي الصفقات:** `{BOT_STATS['total_trades']}` (ربح: {BOT_STATS['winning_trades']} | خسارة: {BOT_STATS['losing_trades']})\n"
        f"💰 **صافي الأرباح:** `${BOT_STATS['total_profit_usdt']:.4f} USDT`\n"
    )

    toggle_btn = {"text": "⏸️ إيقاف البوت", "callback_data": "btn_stop"} if BOT_SETTINGS["is_running"] else {"text": "▶️ تشغيل البوت", "callback_data": "btn_start"}

    keyboard = {
        "inline_keyboard": [
            [toggle_btn, {"text": "📊 التقرير المباشر", "callback_data": "btn_report"}],
            [{"text": "🚫 استبعاد BTC (حماية الصعود)", "callback_data": "exclude_BTC/USDT"}, {"text": "🟢 السماح لـ BTC", "callback_data": "include_BTC/USDT"}],
            [{"text": "🚫 استبعاد SOL", "callback_data": "exclude_SOL/USDT"}, {"text": "🟢 السماح لـ SOL", "callback_data": "include_SOL/USDT"}],
            [{"text": "💵 ضبط رأس المال 10$", "callback_data": "cap_10"}, {"text": "💵 ضبط رأس المال 20$", "callback_data": "cap_20"}]
        ]
    }
    await send_telegram_message(text, reply_markup=keyboard)

# --- مستقبل الأوامر من تيليجرام ---
async def telegram_updates_loop():
    print("📲 [مستقبل الأوامر] بدأ الاستماع للأزرار التفاعلية...", flush=True)
    offset = 0
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}?offset={offset}&timeout=10") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            
                            if "message" in update and "text" in update["message"]:
                                cmd = update["message"]["text"]
                                if cmd in ["/start", "/control", "تحكم"]:
                                    await send_control_panel()

                            if "callback_query" in update:
                                callback = update["callback_query"]
                                data_code = callback["data"]
                                
                                if data_code == "btn_start":
                                    BOT_SETTINGS["is_running"] = True
                                    await send_telegram_message("▶️ **تم تشغيل البوت بنجاح!**")
                                    await send_control_panel()
                                elif data_code == "btn_stop":
                                    BOT_SETTINGS["is_running"] = False
                                    await send_telegram_message("⏸️ **تم إيقاف البوت مؤقتاً.**")
                                    await send_control_panel()
                                elif data_code == "btn_report":
                                    await send_control_panel()
                                elif data_code.startswith("exclude_"):
                                    sym = data_code.replace("exclude_", "")
                                    if sym not in BOT_SETTINGS["excluded_symbols"]:
                                        BOT_SETTINGS["excluded_symbols"].append(sym)
                                    await send_telegram_message(f"🚫 **تم استبعاد العملة `{sym}` بناءً على رغبتك!** البوت لن يتدخل فيها وسيتركها ترتفع بحرية، ويستمر بالباقي.")
                                    await send_control_panel()
                                elif data_code.startswith("include_"):
                                    sym = data_code.replace("include_", "")
                                    if sym in BOT_SETTINGS["excluded_symbols"]:
                                        BOT_SETTINGS["excluded_symbols"].remove(sym)
                                    await send_telegram_message(f"🟢 **تمت إعادة العملة `{sym}` لقائمة التداول العادي.**")
                                    await send_control_panel()
                                elif data_code == "cap_10":
                                    BOT_SETTINGS["trade_amount_usdt"] = 10.0
                                    await send_telegram_message("💵 **تم ضبط رأس المال لكل صفقة على 10 USDT**")
                                    await send_control_panel()
                                elif data_code == "cap_20":
                                    BOT_SETTINGS["trade_amount_usdt"] = 20.0
                                    await send_telegram_message("💵 **تم ضبط رأس المال لكل صفقة على 20 USDT**")
                                    await send_control_panel()
        except Exception as e:
            await asyncio.sleep(2)
        await asyncio.sleep(2)

# --- خادم ويب لوحة التحكم ---
async def handle(request):
    status_str = "🟢 شغال" if BOT_SETTINGS["is_running"] else "🔴 متوقف"
    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>لوحة مراقبة البوت</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #0d1117; color: #c9d1d9; text-align: center; padding: 20px; }}
            .card {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 20px; margin: 15px auto; max-width: 500px; }}
            h1 {{ color: #58a6ff; }}
            .stat {{ font-size: 18px; margin: 10px 0; }}
            .profit {{ color: #3fb950; font-weight: bold; }}
            .loss {{ color: #f85149; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🚀 مراقب البوت المباشر</h1>
        <div class="card">
            <div class="stat">حالة البوت: <b>{status_str}</b></div>
            <div class="stat">رأس المال للصفقة: <b>${BOT_SETTINGS['trade_amount_usdt']} USDT</b></div>
            <div class="stat">الأرباح: <span class="profit">${BOT_STATS['total_profit_usdt']:.4f} USDT</span></div>
        </div>
        <p>📱 للتحكم الكامل واستبعاد العملات، أرسل كلمة (تحكم) لبوت تيليجرام.</p>
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

async def self_ping_loop():
    await asyncio.sleep(10)
    port = os.environ.get("PORT", 10000)
    render_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(render_url) as resp:
                    pass
            except Exception:
                pass
            await asyncio.sleep(180)

# --- إعدادات منصة OKX ---
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

# --- المحرك الرئيسي الذكي ---
async def unified_scalping_bot():
    print("🚀 [محرك التداول] يعمل بكامل الميزات الذكية...", flush=True)
    await send_control_panel()
    
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
                # إذا كانت العملة مستبعدة بناءً على طلبك، يتخطاها البوت تماماً لتركها تصعد بحرية
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
                            BOT_STATS["active_positions_count"] = sum(1 for p in active_positions.values() if p["in_pos"])
                            
                            await send_telegram_message(
                                f"🟢 **تم فتح صفقة جديدة!**\n"
                                f"🪙 العملة: `{symbol}`\n"
                                f"💰 السعر: `{fill_price}`\n"
                                f"💵 رأس المال: `${BOT_SETTINGS['trade_amount_usdt']}`"
                            )

                except Exception as ex:
                    print(f"⚠️ خطأ أثناء فحص {symbol}: {ex}", flush=True)

            # متابعة الأرباح للصفقات المفتوحة (مع احترام الاستبعاد الفوري)
            for symbol, pos in list(active_positions.items()):
                if pos["in_pos"]:
                    # إذا قمت باستبعاد العملة وهي في صفقة، يتركها البوت ولا يتدعب في إغلاقها قسراً إلا إذا رغبت، أو يتخطى إدارتها
                    if symbol in BOT_SETTINGS["excluded_symbols"]:
                        continue

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

                        await send_telegram_message(
                            f"🎯 **جني الأرباح بنجاح!**\n"
                            f"🪙 العملة: `{symbol}`\n"
                            f"📈 النسبة: `+{profit_ratio*100:.2f}%`\n"
                            f"💵 الربح: `${profit_usdt:.4f} USDT`"
                        )

                    elif profit_ratio <= -STOP_LOSS_PCT:
                        loss_usdt = (curr_price - entry) * amount
                        await exchange.create_market_sell_order(symbol, amount)
                        active_positions[symbol]["in_post"] = False
                        active_positions[symbol]["in_pos"] = False
                        
                        BOT_STATS["total_trades"] += 1
                        BOT_STATS["losing_trades"] += 1
                        BOT_STATS["total_profit_usdt"] += loss_usdt
                        BOT_STATS["total_profit_pct"] += (profit_ratio * 100)
                        BOT_STATS["active_positions_count"] = sum(1 for p in active_positions.values() if p["in_pos"])

                        await send_telegram_message(
                            f"🛑 **تفعيل وقف الخسارة!**\n"
                            f"🪙 العملة: `{symbol}`\n"
                            f"📉 النسبة: `{profit_ratio*100:.2f}%`\n"
                            f"💸 الخسارة: `${loss_usdt:.4f} USDT`"
                        )

        except Exception as e:
            print(f"❌ خطأ رئيسي: {e}", flush=True)
        finally:
            if exchange:
                try:
                    await exchange.close()
                except Exception:
                    pass

        await asyncio.sleep(10)

# --- الدالة الرئيسية ---
async def main():
    await asyncio.gather(
        start_web_server(),
        self_ping_loop(),
        telegram_updates_loop(),
        unified_scalping_bot()
    )

if __name__ == '__main__':
    asyncio.run(main())
