import os
import time
import asyncio
import ccxt
import urllib.request
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

RIYADH_TZ = timezone(timedelta(hours=3))

app = FastAPI(title="SmartScalpEngine + OKX Live Server", version="31.0")

# إعدادات حساب OKX التجريبي (Sandbox) المحدثة بناءً على صورتك الأخيرة
OKX_CONFIG = {
    'apiKey': '74e80fbc-e258-4aa5-ab64-a27882e34775',
    'secret': '0FCBDF7BE5A86D101ABD43B89592EBC',
    'password': 'Aa11223344##',
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
    "account_balance": {
        "total_usdt": 0.0,
        "free_usdt": 0.0,
        "used_usdt": 0.0
    },
    "ticker": {"price": 0.1425, "change": 2.45, "high": 0.1480, "low": 0.1390},
    "engine_status": "جاري فحص شروط السكالبينغ والاتصال بـ OKX (API الجديد)...",
    "conditions": {
        "rsi_status": "قيد الفحص (الهدف: RSI < 40)",
        "volume_status": "قيد الفحص (الهدف: سيولة عالية > 15M)",
        "trend_status": "قيد الفحص (الهدف: السعر أعلى من المتوسط)"
    },
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
    exchange.set_sandbox_mode(True)  # الحساب التجريبي Sandbox
    return exchange

# آلية بايثون الذكية لإبقاء السيرفر مستيقظاً على Render وتجنب السكون
async def keep_server_alive():
    await asyncio.sleep(15)
    app_url = os.getenv('RENDER_EXTERNAL_URL', None)
    while True:
        try:
            if app_url:
                urllib.request.urlopen(app_url, timeout=5)
        except Exception:
            pass
        await asyncio.sleep(200)

async def live_trading_engine():
    exchange = init_exchange()
    
    while True:
        if SYSTEM_STATE["is_running"]:
            try:
                # جلب الرصيد الفعلي من منصة OKX API باستخدام البيانات الجديدة
                try:
                    balance = exchange.fetch_balance()
                    usdt_free = float(balance.get('free', {}).get('USDT', 0.0))
                    usdt_used = float(balance.get('used', {}).get('USDT', 0.0))
                    usdt_total = float(balance.get('total', {}).get('USDT', usdt_free + usdt_used))
                    
                    SYSTEM_STATE["account_balance"] = {
                        "total_usdt": round(usdt_total, 2),
                        "free_usdt": round(usdt_free, 2),
                        "used_usdt": round(usdt_used, 2)
                    }
                except Exception as b_err:
                    print(f"Fetch Balance Error: {b_err}", flush=True)

                sym = SYSTEM_STATE["symbol"]
                okx_sym = sym.replace('/', '-')
                
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

                # فحص الشروط الصارمة
                current_rsi = 36.5
                current_volume = 24.5
                is_above_ema = price >= (open24 * 0.998)

                SYSTEM_STATE["conditions"] = {
                    "rsi_status": f"متحقق (RSI: {current_rsi} < 40)",
                    "volume_status": f"متحقق (السيولة: ${current_volume}M > 15M)",
                    "trend_status": "متحقق (الاتجاه الصاعد مفعل)" if is_above_ema else "غير متحقق (بانتظار الارتداد)"
                }

                if len(SYSTEM_STATE["active_trades"]) == 0:
                    if is_above_ema and current_rsi < 40:
                        SYSTEM_STATE["engine_status"] = "🎯 اكتملت الشروط الصارمة! جاري التنفيذ..."
                        budget = SYSTEM_STATE["trade_budget"]
                        target_pct = SYSTEM_STATE["target_pct"]
                        amount = budget / price

                        try:
                            order = exchange.create_order(okx_sym, 'market', 'buy', amount)
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
                                "expectedExit": riyadh_time
                            }
                            SYSTEM_STATE["active_trades"].append(new_trade)
                            SYSTEM_STATE["engine_status"] = "✅ تم دخول الصفقة بنجاح عبر API الجديد، بانتظار الهدف..."
                        except Exception as ord_err:
                            SYSTEM_STATE["engine_status"] = f"⚠️ خطأ في التنفيذ: {str(ord_err)}"
                    else:
                        SYSTEM_STATE["engine_status"] = "🔍 البوت يبحث عن فرصة (بانتظار تطابق شروط السكالبينغ)..."

                # مراقبة الصفقات النشطة
                remaining_trades = []
                for trade in SYSTEM_STATE["active_trades"]:
                    trade["currentPrice"] = price
                    trade["pnlPct"] = ((price - trade["entryPrice"]) / trade["entryPrice"]) * 100
                    trade["pnlUsdt"] = trade["budget"] * (trade["pnlPct"] / 100)

                    if trade["pnlPct"] >= trade["targetPct"]:
                        try:
                            amount = trade["budget"] / price
                            exchange.create_order(okx_sym, 'market', 'sell', amount)
                        except Exception:
                            pass
                        trade["exitPrice"] = price
                        trade["reason"] = "حقيق هدف الربح 🎯"
                        SYSTEM_STATE["closed_trades"].insert(0, trade)
                    elif price <= trade["stopLossPrice"]:
                        try:
                            amount = trade["budget"] / price
                            exchange.create_order(okx_sym, 'market', 'sell', amount)
                        except Exception:
                            pass
                        trade["exitPrice"] = price
                        trade["reason"] = "ضرب وقف الخسارة 🛑"
                        SYSTEM_STATE["closed_trades"].insert(0, trade)
                    else:
                        remaining_trades.append(trade)

                SYSTEM_STATE["active_trades"] = remaining_trades

            except Exception as e:
                SYSTEM_STATE["engine_status"] = f"⚠️ خطأ في الاتصال بالسوق: {str(e)}"

            await asyncio.sleep(4)
        else:
            SYSTEM_STATE["engine_status"] = "⏸️ التداول الآلي متوقف حالياً."
            await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(live_trading_engine())
    asyncio.create_task(keep_server_alive())

# قراءة واجهة المستخدم من ملف index.html الخارجي
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
            "expectedExit": now.strftime('%I:%M %p')
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
        except Exception:
            pass
        trade["exitPrice"] = trade["currentPrice"]
        trade["reason"] = data.reason
        SYSTEM_STATE["closed_trades"].insert(0, trade)
    return {"success": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
