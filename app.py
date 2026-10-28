import os
import time
import asyncio
import ccxt
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

RIYADH_TZ = timezone(timedelta(hours=3))

app = FastAPI(title="OKX Fully Automated Scalping Server", version="25.0")

# إعدادات مفاتيح API لمنصة OKX
OKX_CONFIG = {
    'apiKey': os.getenv('OKX_API_KEY', '8dd26496-0023-4b54-ae2b-4a48d513fb05'),
    'secret': os.getenv('OKX_SECRET_KEY', 'EB61E3ACC19D33653EDC54DA55388B2E'),
    'password': os.getenv('OKX_PASSWORD', 'Aa11223344##'),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
}

# حالة النظام المركزية
SYSTEM_STATE = {
    "is_running": True,
    "symbol": "DOGE/USDT",
    "timeframe": "5m",
    "trade_budget": 100.0,
    "target_pct": 0.10,
    "ticker": {"price": 0.1425, "change": 2.45, "high": 0.1480, "low": 0.1390},
    "active_trades": [],
    "closed_trades": []
}

class ControlModel(BaseModel):
    is_running: bool = None
    symbol: str = None
    timeframe: str = None
    trade_budget: float = None
    target_pct: float = None

class TradeActionModel(BaseModel):
    symbol: str
    budget: float
    target_pct: float

class CloseTradeModel(BaseModel):
    trade_id: int
    reason: str = "إغلاق يدوي"

def init_exchange():
    exchange = ccxt.okx(OKX_CONFIG)
    exchange.set_sandbox_mode(True)  # True للحساب التجريبي Sandbox
    return exchange

async def live_trading_engine():
    """حلقة التنفيذ الآلي الحقيقي وإدارة الصفقات عبر OKX API"""
    exchange = init_exchange()
    
    while True:
        if SYSTEM_STATE["is_running"]:
            try:
                sym = SYSTEM_STATE["symbol"]
                okx_sym = sym.replace('/', '-')
                
                # جلب السعر الحي من المنصة
                ticker = exchange.fetch_ticker(okx_sym)
                price = float(ticker['last'])
                open24 = float(ticker.get('open24h', price))
                change_pct = ((price - open24) / open24) * 100
                
                SYSTEM_STATE["ticker"] = {
                    "price": price,
                    "change": round(change_pct, 2),
                    "high": float(ticker.get('high24h', price * 1.02)),
                    "low": float(ticker.get('low24h', price * 0.98))
                }

                # --- الشرط الآلي للتنفيذ التلقائي ---
                # إذا لم تكن هناك أي صفقة نشطة، يقوم البوت بفتح صفقة شراء تلقائياً فوراً
                if len(SYSTEM_STATE["active_trades"]) == 0:
                    budget = SYSTEM_STATE["trade_budget"]
                    target_pct = SYSTEM_STATE["target_pct"]
                    amount = budget / price

                    try:
                        # تنفيذ أمر الشراء الفعلي على OKX Sandbox API
                        exchange.create_order(okx_sym, 'market', 'buy', amount)
                        
                        target_price = price * (1 + (target_pct / 100))
                        stop_loss_price = price * 0.988

                        now = datetime.now(RIYADH_TZ) + timedelta(minutes=15)
                        riyadh_time = now.strftime('%I:%M %p')

                        new_trade = {
                            "id": int(time.time() * 1000),
                            "symbol": sym,
                            "type": "شراء (Long)",
                            "entryPrice": price,
                            "currentPrice": price,
                            "targetPrice": target_price,
                            "targetPct": target_pct,
                            "stopLossPrice": stop_loss_price,
                            "budget": budget,
                            "pnlPct": 0.0,
                            "pnlUsdt": 0.0,
                            "expectedExit": riyadhTime
                        }
                        SYSTEM_STATE["active_trades"].append(new_trade)
                        print(f"Auto-trade executed successfully for {sym} at {price}", flush=True)
                    except Exception as ord_err:
                        print(f"Auto-trade order error: {ord_err}", flush=True)

                # مراقبة الصفقات النشطة وإغلاقها تلقائياً عند الهدف أو الوقف
                remaining_trades = []
                for trade in SYSTEM_STATE["active_trades"]:
                    trade["currentPrice"] = price
                    trade["pnlPct"] = ((price - trade["entryPrice"]) / trade["entryPrice"]) * 100
                    trade["pnlUsdt"] = trade["budget"] * (trade["pnlPct"] / 100)

                    if trade["pnlPct"] >= trade["targetPct"]:
                        try:
                            amount = trade["budget"] / price
                            exchange.create_order(okx_sym, 'market', 'sell', amount)
                        except Exception as e:
                            print(f"Auto sell error: {e}", flush=True)
                        
                        trade["exitPrice"] = price
                        trade["reason"] = "حقيق هدف الربح 🎯"
                        SYSTEM_STATE["closed_trades"].insert(0, trade)
                    elif price <= trade["stopLossPrice"]:
                        try:
                            amount = trade["budget"] / price
                            exchange.create_order(okx_sym, 'market', 'sell', amount)
                        except Exception as e:
                            print(f"Auto stop-loss error: {e}", flush=True)
                            
                        trade["exitPrice"] = price
                        trade["reason"] = "ضرب وقف الخسارة 🛑"
                        SYSTEM_STATE["closed_trades"].insert(0, trade)
                    else:
                        remaining_trades.append(trade)

                SYSTEM_STATE["active_trades"] = remaining_trades

            except Exception as e:
                print(f"Engine Loop Error: {e}", flush=True)

            await asyncio.sleep(4)
        else:
            await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(live_trading_engine())

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
    if data.symbol is not None:
        SYSTEM_STATE["symbol"] = data.symbol
    if data.timeframe is not None:
        SYSTEM_STATE["timeframe"] = data.timeframe
    if data.trade_budget is not None:
        SYSTEM_STATE["trade_budget"] = data.trade_budget
    if data.target_pct is not None:
        SYSTEM_STATE["target_pct"] = data.target_pct
    return {"success": True, "state": SYSTEM_STATE}

@app.post("/api/execute_trade")
async def execute_trade_manual(data: TradeActionModel):
    exchange = init_exchange()
    okx_sym = data.symbol.replace('/', '-')
    try:
        ticker = exchange.fetch_ticker(okx_sym)
        price = float(ticker['last'])
        amount = data.budget / price
        
        exchange.create_order(okx_sym, 'market', 'buy', amount)
        
        target_price = price * (1 + (data.target_pct / 100))
        stop_loss_price = price * 0.988

        now = datetime.now(RIYADH_TZ) + timedelta(minutes=15)
        riyadh_time = now.strftime('%I:%M %p')

        new_trade = {
            "id": int(time.time() * 1000),
            "symbol": data.symbol,
            "type": "شراء (Long)",
            "entryPrice": price,
            "currentPrice": price,
            "targetPrice": target_price,
            "targetPct": data.target_pct,
            "stopLossPrice": stop_loss_price,
            "budget": data.budget,
            "pnlPct": 0.0,
            "pnlUsdt": 0.0,
            "expectedExit": riyadhTime
        }
        SYSTEM_STATE["active_trades"].append(new_trade)
        return {"success": True, "trade": new_trade}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/close_trade")
async def close_trade(data: CloseTradeModel):
    trade_idx = next((i for i, t in enumerate(SYSTEM_STATE["active_trades"]) if t["id"] == data.trade_id), None)
    if trade_idx is not None:
        trade = SYSTEM_STATE["active_trades"].pop(trade_idx)
        try:
            exchange = init_exchange()
            okx_sym = trade["symbol"].replace('/', '-')
            amount = trade["budget"] / trade["currentPrice"]
            exchange.create_order(okx_sym, 'market', 'sell', amount)
        except Exception as e:
            print(f"Manual close order error: {e}", flush=True)
            
        trade["exitPrice"] = trade["currentPrice"]
        trade["reason"] = data.reason
        SYSTEM_STATE["closed_trades"].insert(0, trade)
    return {"success": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
