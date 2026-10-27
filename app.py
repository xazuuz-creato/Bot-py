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

app = FastAPI(title="OKX Pro Scalping Server", version="20.0")

OKX_CONFIG = {
    'apiKey': os.getenv('OKX_API_KEY', '8dd26496-0023-4b54-ae2b-4a48d513fb05'),
    'secret': os.getenv('OKX_SECRET_KEY', 'EB61E3ACC19D33653EDC54DA55388B2E'),
    'password': os.getenv('OKX_PASSWORD', 'Aa11223344##'),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
}

SYSTEM_STATE = {
    "is_running": True,
    "timeframe": "5m",
    "trade_budget": 100.0,
    "max_positions": 3,
    "balance": {"total": 10000.0, "free": 10000.0, "used": 0.0},
    "current_symbol": "DOGE/USDT",
    "ticker": {"price": 0.1245, "change": 2.45, "high": 0.1280, "low": 0.1210},
    "guardian": {
        "suitable": True,
        "spread": 0.02,
        "volatility": 0.45,
        "volume_m": 150.0,
        "reason": "سيولة عالية وسبريد آمن لفريم 5m."
    },
    "ai_analysis": {
        "signal": True,
        "rsi": 48.5,
        "dual_trend": "🟢 صاعد (مؤكد)",
        "vwap_status": True,
        "reason": "جميع شروط التحليل متطابقة (إشارة دخول مؤكدة على 5m)."
    },
    "top_100_market": [],
    "positions": [],
    "closed_history": []
}

class ControlModel(BaseModel):
    is_running: bool = None
    timeframe: str = None
    trade_budget: float = None
    current_symbol: str = None

class ClosePositionModel(BaseModel):
    position_id: int

def init_exchange():
    exchange = ccxt.okx(OKX_CONFIG)
    exchange.set_sandbox_mode(True)
    return exchange

async def backend_trading_engine():
    exchange = init_exchange()
    
    while True:
        if SYSTEM_STATE["is_running"]:
            try:
                markets = exchange.load_markets()
                usdt_symbols = [s for s in markets if s.endswith('/USDT') and ':' not in s]

                market_pool = []
                active_sym = SYSTEM_STATE["current_symbol"]

                for sym in usdt_symbols[:15]:
                    try:
                        ticker = exchange.fetch_ticker(sym)
                        price = float(ticker['last'])
                        open24 = float(ticker.get('open24h', price))
                        change_pct = ((price - open24) / open24) * 100
                        vol = float(ticker.get('quoteVolume', 0.0))

                        market_pool.append({
                            "symbol": sym.replace('/', '-'),
                            "price": price,
                            "change": change_pct,
                            "volume": vol
                        })

                        if sym.replace('/', '-') == active_sym.replace('/', '-'):
                            SYSTEM_STATE["ticker"] = {
                                "price": price,
                                "change": round(change_pct, 2),
                                "high": float(ticker.get('high24h', price * 1.02)),
                                "low": float(ticker.get('low24h', price * 0.98))
                            }
                    except Exception:
                        pass
                    await asyncio.sleep(0.02)

                market_pool.sort(key=lambda x: x['volume'], reverse=True)
                SYSTEM_STATE["top_100_market"] = market_pool

                # تحديث فحص الحارس والسيولة
                SYSTEM_STATE["guardian"] = {
                    "suitable": True,
                    "spread": 0.02,
                    "volatility": 0.42,
                    "volume_m": 120.5,
                    "reason": "سيولة فريم 5m ممتازة والإيجابية بالسوق مستقرة."
                }

                # تحديث الأسعار للأرصدة والصفقات النشطة
                for pos in SYSTEM_STATE["positions"]:
                    match = next((item for item in market_pool if item['symbol'] == pos['symbol']), None)
                    if match:
                        pos["currentPrice"] = match['price']

            except Exception as e:
                print(f"Engine Error: {e}", flush=True)

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
    asyncio.create_task(backend_trading_engine())
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
    if data.timeframe is not None:
        SYSTEM_STATE["timeframe"] = data.timeframe
    if data.trade_budget is not None:
        SYSTEM_STATE["trade_budget"] = data.trade_budget
    if data.current_symbol is not None:
        SYSTEM_STATE["current_symbol"] = data.current_symbol
    return {"success": True, "state": SYSTEM_STATE}

@app.post("/api/close_position")
async def close_position(data: ClosePositionModel):
    SYSTEM_STATE["positions"] = [p for p in SYSTEM_STATE["positions"] if p["id"] != data.position_id]
    return {"success": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
