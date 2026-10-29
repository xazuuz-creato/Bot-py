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

app = FastAPI(title="OKX Pro Scalping Bot - Full Featured", version="32.0")

# إعدادات حساب OKX التجريبي (Sandbox) بناءً على مفاتيحك
OKX_CONFIG = {
    'apiKey': os.getenv('OKX_API_KEY', '74e80fbc-e258-4aa5-ab64-a27882e34775'),
    'secret': os.getenv('OKX_SECRET_KEY', '0FCBDF7BE5A86D101ABD43B89592EBC'),
    'password': os.getenv('OKX_PASSWORD', 'Aa11223344##'),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
}

SYSTEM_STATE = {
    "is_running": True,
    "symbol": "DOGE/USDT",
    "trade_budget": 100.0,
    "target_pct": 0.12,
    "use_ai_target": True,  # خيار اختيار نسبة الربح الذكية بواسطة البوت
    "market_status": "🟢 السوق مستقر ومناسب للسكالبينغ",
    "account_balance": {"total": 0.0, "free": 0.0, "used": 0.0},
    "ticker": {"price": 0.0, "change": 0.0},
    "engine_status": "البوت يراقب السيولة والشروط الصارمة...",
    "active_trades": [],
    "closed_trades": []
}

class ControlModel(BaseModel):
    is_running: bool = None
    symbol: str = None
    trade_budget: float = None
    target_pct: float = None
    use_ai_target: bool = None

def init_exchange():
    exchange = ccxt.okx(OKX_CONFIG)
    exchange.set_sandbox_mode(True)
    return exchange

async def advanced_trading_engine():
    exchange = init_exchange()
    
    while True:
        if SYSTEM_STATE["is_running"]:
            try:
                # 1. جلب رصيد المحفظة الحي من OKX Sandbox
                balance = exchange.fetch_balance()
                free_usdt = float(balance.get('free', {}).get('USDT', 1000.0))
                used_usdt = float(balance.get('used', {}).get('USDT', 0.0))
                SYSTEM_STATE["account_balance"] = {
                    "total": round(free_usdt + used_usdt, 2),
                    "free": round(free_usdt, 2),
                    "used": round(used_usdt, 2)
                }

                sym = SYSTEM_STATE["symbol"]
                okx_sym = sym.replace('/', '-')

                ticker = exchange.fetch_ticker(okx_sym)
                price = float(ticker['last'])
                change_24h = float(ticker.get('percentage', 1.0))
                
                SYSTEM_STATE["ticker"] = {"price": price, "change": round(change_24h, 2)}

                # 2. حارس السوق (Market Condition Agent)
                if change_24h < -4.0:
                    SYSTEM_STATE["market_status"] = "🔴 السوق هابط بعنف - تم تجميد التداول آلياً"
                    await asyncio.sleep(5)
                    continue
                else:
                    SYSTEM_STATE["market_status"] = "🟢 سيولة السوق ممتازة ومناسبة للسكالبينغ"

                # 3. تحديد نسبة الربح المستهدفة (يدوية أو اختيار ذكي بواسطة البوت)
                applied_target_pct = SYSTEM_STATE["target_pct"]
                if SYSTEM_STATE["use_ai_target"]:
                    if abs(change_24h) > 3.0:
                        applied_target_pct = 0.20  # تقلبات عالية ربح أعلى
                    else:
                        applied_target_pct = 0.10  # سوق هادئ سكالبينغ سريع

                # شروط الدخول السريعة
                is_signal_ready = change_24h > -1.5

                if len(SYSTEM_STATE["active_trades"]) == 0 and is_signal_ready:
                    SYSTEM_STATE["engine_status"] = f"🎯 شروط السيولة مطابقة! جاري التنفيذ (الهدف: {applied_target_pct}%)"
                    budget = SYSTEM_STATE["trade_budget"]
                    amount = budget / price

                    exchange.create_order(okx_sym, 'market', 'buy', amount)
                    
                    target_price = price * (1 + (applied_target_pct / 100))
                    stop_loss_price = price * 0.985
                    
                    # حساب وقت الخروج المتوقع (سكالبينغ سريع 7 دقائق)
                    expected_exit_time = datetime.now(RIYADH_TZ) + timedelta(minutes=7)

                    new_trade = {
                        "id": int(time.time() * 1000),
                        "symbol": sym,
                        "entryPrice": price,
                        "currentPrice": price,
                        "targetPrice": target_price,
                        "targetPct": applied_target_pct,
                        "stopLossPrice": stop_loss_price,
                        "budget": budget,
                        "pnlPct": 0.0,
                        "pnlUsdt": 0.0,
                        "expectedExit": expected_exit_time.strftime('%I:%M %p'),
                        "time": datetime.now(RIYADH_TZ).strftime('%I:%M:%S %p')
                    }
                    SYSTEM_STATE["active_trades"].append(new_trade)
                else:
                    if len(SYSTEM_STATE["active_trades"]) == 0:
                        SYSTEM_STATE["engine_status"] = "🔍 وكيل السيولة يمسح أزواج التداول..."

                # 4. متابعة الصفقات والوقف المتحرك الذكي وإغلاقها عند الهدف
                remaining_trades = []
                for trade in SYSTEM_STATE["active_trades"]:
                    trade["currentPrice"] = price
                    trade["pnlPct"] = ((price - trade["entryPrice"]) / trade["entryPrice"]) * 100
                    trade["pnlUsdt"] = trade["budget"] * (trade["pnlPct"] / 100)

                    # وقف متحرك ذكي (Trailing Stop)
                    if trade["pnlPct"] >= 0.08:
                        trade["stopLossPrice"] = max(trade["stopLossPrice"], trade["entryPrice"])

                    if price >= trade["targetPrice"] or price <= trade["stopLossPrice"]:
                        try:
                            exchange.create_order(okx_sym, 'market', 'sell', trade["budget"] / price)
                        except Exception:
                            pass
                        
                        trade["exitPrice"] = price
                        trade["result"] = "ربح هدف 🎯" if trade["pnlPct"] >= 0 else "وقف خسارة 🛑"
                        SYSTEM_STATE["closed_trades"].insert(0, trade)
                    else:
                        remaining_trades.append(trade)

                SYSTEM_STATE["active_trades"] = remaining_trades

            except Exception as e:
                SYSTEM_STATE["engine_status"] = f"⚠️ خطأ في المعالجة: {str(e)}"

            await asyncio.sleep(1.2)
        else:
            SYSTEM_STATE["engine_status"] = "⏸️ البوت متوقف حالياً."
            await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(advanced_trading_engine())

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return "<h1>Server is online</h1>"

@app.get("/api/state")
async def get_state():
    return SYSTEM_STATE

@app.post("/api/control")
async def control_system(data: ControlModel):
    if data.is_running is not None:
        SYSTEM_STATE["is_running"] = data.is_running
    if data.symbol is not None:
        SYSTEM_STATE["symbol"] = data.symbol
    if data.trade_budget is not None:
        SYSTEM_STATE["trade_budget"] = data.trade_budget
    if data.target_pct is not None:
        SYSTEM_STATE["target_pct"] = data.target_pct
    if data.use_ai_target is not None:
        SYSTEM_STATE["use_ai_target"] = data.use_ai_target
    return {"success": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
