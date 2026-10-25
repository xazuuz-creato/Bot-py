import os
import time
import asyncio
import ccxt
import aiohttp
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

RIYADH_TZ = timezone(timedelta(hours=3))

def get_riyadh_time():
    return datetime.now(RIYADH_TZ).strftime('%I:%M:%S %p')

def get_predicted_end_time(minutes_ahead):
    future_time = datetime.now(RIYADH_TZ) + timedelta(minutes=minutes_ahead)
    return future_time.strftime('%I:%M:%S %p')

app = FastAPI(title="OKX Pro Multi-Mode Scalping System", version="6.0")

OKX_CONFIG = {
    'apiKey': '8dd26496-0023-4b54-ae2b-4a48d513fb05',
    'secret': 'EB61E3ACC19D33653EDC54DA55388B2E',
    'password': 'Aa11223344##',
    'enableRateLimit': True,
}

SYSTEM_STATE = {
    "is_running": True,
    "normal_mode": True,
    "fast_mode": False,
    "normal_budget": 5000.0,
    "fast_budget": 5000.0,
    "normal_classification": "none", # التصنيف الأساسي للنمط العادي: none, most_profitable, fastest, medium
    "balance": {"total": 10000.0, "free": 10000.0, "used": 0.0},
    "tickers": {},
    "positions": [],
    "fast_positions": [],
    "stats": {
        "successful_trades": 0,
        "total_pnl": 0.0,
        "last_action": "البوتات تعمل وتقسيم الشغل والوقت مفعل...",
        "ai_bias": "BULLISH",
        "current_rsi": 28.5
    }
}

class ControlModel(BaseModel):
    is_running: bool = None
    normal_mode: bool = None
    fast_mode: bool = None
    normal_budget: float = None
    fast_budget: float = None
    normal_classification: str = None

def init_exchange():
    exchange = ccxt.okx(OKX_CONFIG)
    exchange.set_sandbox_mode(True)
    return exchange

async def automated_trading_supervisor():
    exchange = init_exchange()
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']

    while True:
        if SYSTEM_STATE["is_running"]:
            try:
                tickers_data = {}
                for sym in symbols:
                    try:
                        ticker = exchange.fetch_ticker(sym)
                        tickers_data[sym] = {
                            "price": float(ticker['last']),
                            "change": f"{float(ticker.get('percentage', 0.0)):+.2f}%"
                        }
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)
                
                if tickers_data:
                    SYSTEM_STATE["tickers"] = tickers_data

                try:
                    balance = exchange.fetch_balance()
                    if 'USDT' in balance:
                        SYSTEM_STATE["balance"] = {
                            "total": float(balance['USDT'].get('total', 10000.0)),
                            "free": float(balance['USDT'].get('free', 10000.0)),
                            "used": float(balance['USDT'].get('used', 0.0))
                        }
                except Exception:
                    pass

                # --- 1. النمط العادي (مع التصنيفات وتوقع وقت الانتهاء) ---
                if SYSTEM_STATE["normal_mode"]:
                    for sym in symbols:
                        if sym in SYSTEM_STATE["tickers"]:
                            cur_price = SYSTEM_STATE["tickers"][sym]["price"]
                            if len(SYSTEM_STATE["positions"]) < 3:
                                existing = [p for p in SYSTEM_STATE["positions"] if p["symbol"] == sym]
                                if not existing:
                                    # تحديد الهدف ووقت الانتهاء بناءً على التصنيف
                                    classification = SYSTEM_STATE["normal_classification"]
                                    if classification == "most_profitable":
                                        tp = round(cur_price * 1.006, 4) # ربح أعلى
                                        duration_mins = 12
                                    elif classification == "fastest":
                                        tp = round(cur_price * 1.0035, 4)
                                        duration_mins = 4
                                    elif classification == "medium":
                                        tp = round(cur_price * 1.0045, 4)
                                        duration_mins = 8
                                    else: # none (الوضع الأساسي)
                                        tp = round(cur_price * 1.0030, 4) # الحد الأدنى 0.30%
                                        duration_mins = 10

                                    sl = round(cur_price * 0.995, 4)
                                    
                                    new_pos = {
                                        "id": int(time.time() * 1000),
                                        "symbol": sym,
                                        "type": f"عادي ({classification})",
                                        "entryPrice": cur_price,
                                        "currentPrice": cur_price,
                                        "tp": tp,
                                        "sl": sl,
                                        "pnlVal": 0.0,
                                        "pnl": "+0.00%",
                                        "isProfit": True,
                                        "time": get_riyadh_time(),
                                        "endTime": get_predicted_end_time(duration_mins)
                                    }
                                    SYSTEM_STATE["positions"].insert(0, new_pos)
                                    SYSTEM_STATE["stats"]["successful_trades"] += 1

                # --- 2. النمط السريع (أسرع الصفقات / حد أدنى للربح 0.10%) ---
                if SYSTEM_STATE["fast_mode"]:
                    for sym in symbols:
                        if sym in SYSTEM_STATE["tickers"]:
                            cur_price = SYSTEM_STATE["tickers"][sym]["price"]
                            if len(SYSTEM_STATE["fast_positions"]) < 3:
                                existing = [p for p in SYSTEM_STATE["fast_positions"] if p["symbol"] == sym]
                                if not existing:
                                    tp = round(cur_price * 1.001, 4) # حد أدنى للربح 0.10%
                                    sl = round(cur_price * 0.998, 4)
                                    fast_pos = {
                                        "id": int(time.time() * 1000) + 1,
                                        "symbol": sym,
                                        "type": "سريع ⚡ (أسرع صفقات)",
                                        "entryPrice": cur_price,
                                        "currentPrice": cur_price,
                                        "tp": tp,
                                        "sl": sl,
                                        "pnlVal": 0.0,
                                        "pnl": "+0.00%",
                                        "isProfit": True,
                                        "time": get_riyadh_time(),
                                        "endTime": get_predicted_end_time(2) # تنتهي خلال دقيقتين تقريباً
                                    }
                                    SYSTEM_STATE["fast_positions"].insert(0, fast_pos)

                # تحديث PnL
                total_pnl = 0.0
                all_pos = SYSTEM_STATE["positions"] + SYSTEM_STATE["fast_positions"]
                for pos in all_pos:
                    sym = pos["symbol"]
                    if sym in SYSTEM_STATE["tickers"]:
                        pos["currentPrice"] = SYSTEM_STATE["tickers"][sym]["price"]
                    diff = ((pos["currentPrice"] - pos["entryPrice"]) / pos["entryPrice"]) * 100
                    pos["pnlVal"] = round(diff, 2)
                    pos["pnl"] = (("+" if diff >= 0 else "") + f"{diff:.2f}%")
                    pos["isProfit"] = diff >= 0
                    total_pnl += diff

                SYSTEM_STATE["stats"]["total_pnl"] = round(total_pnl, 2)

            except Exception as e:
                print(f"Error: {e}", flush=True)

            await asyncio.sleep(3)
        else:
            await asyncio.sleep(2)

async def self_ping_loop():
    port = int(os.environ.get("PORT", 10000))
    url = f"http://127.0.0.1:{port}/"
    await asyncio.sleep(5)
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    pass
        except Exception:
            pass
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(automated_trading_supervisor())
    asyncio.create_task(self_ping_loop())

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return "<h1>Error: index.html not found!</h1>"

@app.get("/api/state")
async def get_state():
    return SYSTEM_STATE

@app.post("/api/control")
async def control_system(data: ControlModel):
    if data.is_running is not None:
        SYSTEM_STATE["is_running"] = data.is_running
    if data.normal_mode is not None:
        SYSTEM_STATE["normal_mode"] = data.normal_mode
    if data.fast_mode is not None:
        SYSTEM_STATE["fast_mode"] = data.fast_mode
    if data.normal_budget is not None:
        SYSTEM_State["normal_budget"] = data.normal_budget
    if data.fast_budget is not None:
        SYSTEM_STATE["fast_budget"] = data.fast_budget
    if data.normal_classification is not None:
        SYSTEM_STATE["normal_classification"] = data.normal_classification
    return {"success": True, "state": SYSTEM_STATE}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
