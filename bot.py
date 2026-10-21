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

# --- خادم الويب لمنع السكون ---
async def handle(request):
    status_str = "🟢 شغال" if BOT_SETTINGS["is_running"] else "🔴 متوقف"
    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>السوبر بوت المدمج (مستقر وآمن)</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #0d1117; color: #c9d1d9; text-align: center; padding: 20px; }}
            .card {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 20px; margin: 15px auto; max-width: 500px; }}
            h1 {{ color: #58a6ff; }}
            .stat {{ font-size: 18px; margin: 10px 0; }}
            .profit {{ color: #3fb950; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🚀 السوبر بوت (صفقة واحدة بـ 100$) يعمل بتوقيت الرياض</h1>
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
        atr_
