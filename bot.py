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
        <head><meta charset="UTF-8"><title>السوبر بوت الخاطف للسكالبينج</title></head>
        <body style="background:#0d1117; color:#c9d1d9; text-align:center; font-family:Arial; padding:50px;">
            <h1>🚀 السوبر بوت الخاطف (أرباح سريعة 0.5% - 1.0%) يعمل بتوقيت الرياض</h1>
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
    "target_tp_pct": 0.0075,             # هدف ربح خاطف وسريع بين 0.50% و 1.00% (نختار الوسط 0.75%)
    "stop_loss_pct": 0.005,              # وقف خسارة سريع وصارم جداً (0.5%)
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

# --- صياد الانفجار اللحظي (الدخول في التوقيت الذي يتحرك فيه السعر فوراً) ---
def analyze_instant_flash_scalp(df):
    try:
        if len(df) < 5:
            return False, "بيانات غير كافية"

        recent_lows = df['low'].iloc[-4:-1].min()
        curr_open = df['open'].iloc[-1]
        curr_close = df['close'].iloc[-1]
        curr_high = df['high'].iloc[-1]
        curr_low = df['low'].iloc[-1]

        is_green = curr_close > curr_open
        body_size = abs(curr_close - curr_open)
        total_range = curr_high - curr_low
        if total_range == 0:
            return False, "المدى صفر"

        body_ratio = body_size / total_range
        is_flash_entry = (curr_low <= recent_lows * 1.002) and is_green and (body_ratio > 0.4)

        if is_flash_entry:
            return True, "توقيت انفجار سعري فوري"

        return False, "انتظار التوقيت المناسب"
    except Exception:
        return False, "خطأ في التحليل"

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
        avg_volume = df
