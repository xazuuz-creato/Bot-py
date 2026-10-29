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

app = FastAPI(title="OKX Ultra-Fast Python Scalping Bot", version="35.0")

# إعدادات حساب OKX التجريبي (Sandbox)
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
    "use_ai_target": True,
    "market_status": "🟢 البوت يعمل بلغة بايثون ويحلل السوق...",
    "account_balance": {"total": 1000.0, "free": 1000.0, "used": 0.0},
    "ticker": {"price": 0.0, "change": 0.0},
    "ranked_coins": [],
    "engine_status": "وكلاء بايثون يفحصون السيولة ويرتبون العملات...",
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

# آلية بايثون الذكية لإبقاء السيرفر مستيقظاً 24/7 بلا توقف
async def keep_server_alive():
    await asyncio.sleep(10)
    app_url = os.getenv('RENDER_EXTERNAL_URL', None)
    while True:
        try:
            if app_url:
                urllib.request.urlopen(app_url, timeout=5)
        except Exception:
            pass
        await asyncio.sleep(200)

async def python_trading_engine():
    exchange = init_exchange()
    watch_symbols = ["DOGE/USDT", "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
    
    while True:
        if SYSTEM_STATE["is_running"]:
            try:
                # 1. جلب الرصيد اللحظي عبر CCXT
                try:
                    balance = exchange.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 1000.0))
                    used_usdt = float(balance.get('used', {}).get('USDT', 0.0))
                    SYSTEM_STATE["account_balance"] = {
                        "total": round(free_usdt + used_usdt, 2),
                        "free": round(free_usdt, 2),
                        "used": round(used_usdt, 2)
                    }
                except Exception:
                    pass

                # 2. وكيل بايثون لتحليل وترتيب العملات حسب السيولة والاستقرار
                coin_rankings = []
                for sym in watch_symbols:
                    try:
                        okx_s = sym.replace('/', '-')
                        t = exchange.fetch_ticker(okx_s)
                        price = float(t['last'])
                        change = float(t.get('percentage', 0.0))
                        base_vol = float(t.get('baseVolume', 100000))
                        
                        score = base_vol * (1 - abs(change) / 100)
                        
                        coin_rankings.append({
                            "symbol": sym,
                            "price": price,
                            "change": round(change, 2),
                            "score": score,
                            "status": "⭐ ممتازة للسكالبينغ" if -2.0 <= change <= 5.0 else "⚠️ تقلب عالي"
                        })
                    except Exception:
                        pass

                coin_rankings.sort(key=lambda x: x['score'], reverse=True)
                SYSTEM_STATE["ranked_coins"] = coin_rankings

                # اختيار العملة النشطة
                sym = SYSTEM_STATE["symbol"]
                okx_sym = sym.replace('/', '-')

                active_ticker = next((c for c in coin_rankings if c['symbol'] == sym), None)
                if active_ticker:
                    price = active_ticker['price']
                    change_24h = active_ticker['change']
                else:
                    t = exchange.fetch_ticker(okx_sym)
                    price = float(t['last'])
                    change_24h = float(t.get('percentage', 0.0))

                SYSTEM_STATE["ticker"] = {"price": price, "change": change_24h}

                # 3. حارس السوق الآلي
                if change_24h < -4.5:
                    SYSTEM_STATE["market_status"] = "🔴 السوق هابط بعنف - تم تجميد التداول مؤقتاً"
                    await asyncio.sleep(4)
                    continue
                else:
                    SYSTEM_STATE["market_status"] = "🟢 بوت بايثون: السوق مستقر والسيولة ممتازة"

                # 4. تحديد نسبة الربح الذكية
                applied_target_pct = SYSTEM_STATE["target_pct"]
                if SYSTEM_STATE["use_ai_target"]:
                    applied_target_pct = 0.20 if abs(change_24h) > 3.0 else 0.10

                is_signal_ready = change_24h > -1.5

                if len(SYSTEM_STATE["active_trades"]) == 0 and is_signal_ready:
                    SYSTEM_STATE["engine_status"] = f"🎯 مطابقة شروط {sym}! جاري التنفيذ الفوري..."
                    budget = SYSTEM_STATE["trade_budget"]
                    amount = budget / price

                    exchange.create_order(okx_sym, 'market', 'buy', amount)
                    
                    target_price = price * (1 + (applied_target_pct / 100))
                    stop_loss_price = price * 0.985
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
                        SYSTEM_STATE["engine_status"] = "🔍 بوت بايثون يفرز العملات ويبحث عن الفرصة الأفضل..."

                # 5. إدارة الصفقات والوقف المتحرك
                remaining_trades = []
                for trade in SYSTEM_STATE["active_trades"]:
                    trade["currentPrice"] = price
                    trade["pnlPct"] = ((price - trade["entryPrice"]) / trade["entryPrice"]) * 100
                    trade["pnlUsdt"] = trade["budget"] * (trade["pnlPct"] / 100)

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
                SYSTEM_STATE["engine_status"] = f"⚠️ إعادة محاولة الاتصال بالسوق..."

            await asyncio.sleep(1.2)
        else:
            SYSTEM_STATE["engine_status"] = "⏸️ التداول الآلي متوقف."
            await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(python_trading_engine())
    asyncio.create_task(keep_server_alive())

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return "<h1>Python Scalping Server is online</h1>"

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
