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

def get_riyadh_time():
    return datetime.now(RIYADH_TZ).strftime('%I:%M %p')

app = FastAPI(title="OKX Live Automated Scalping Server", version="23.0")

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
    # True للحساب التجريبي Sandbox، وعند الرغبة بالحقيقي غيرها إلى False
    exchange.set_sandbox_mode(True)
    return exchange

async def live_trading_engine():
    """حلقة التنفيذ الآلي ومراقبة الأسعار عبر OKX API"""
    exchange = init_exchange()
    
    while True:
        if SYSTEM_STATE["is_running"]:
            try:
                sym = SYSTEM_STATE["symbol"]
                okx_sym = sym.replace('/', '-')
                
                # جلب السعر الحي والبيانات من المنصة
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

                # محاكاة / تفعيل شروط الدخول الآلي التلقائي (إذا لم توجد صفقة مفتوحة)
                # الشروط هنا تفترض فرصة سكالبينغ عند توافر السيولة
                if len(SYSTEM_STATE["active_trades"]) == 0:
                    # شرط إشارة آلي (يمكن ربطه بمؤشر RSI أو حجم تداول)
                    is_signal_triggered = True  # مبدئياً مفعلة للاختبار الآلي
                    
                    if is_signal_triggered:
                        budget = SYSTEM_STATE["trade_budget"]
                        target_pct = SYSTEM_STATE["target_pct"]
                        amount = budget / price
                        
                        try:
                            # 1. إرسال أمر الشراء الفعلي لـ OKX API
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
                                "expectedExit": riyadhTime
                            }
                            SYSTEM_STATE["active_trades"].append(new_trade)
                        except Exception as ord_err:
                            print(f"Order creation error: {ord_err}", flush=True)

                # تحديث ومراقبة الصفقات النشطة وإغلاقها عند الهدف
                remaining_trades = []
                for trade in SYSTEM_STATE["active_trades"]:
                    trade["currentPrice"] = price
                    trade["pnlPct"] = ((price - trade["entryPrice"]) / trade["entryPrice"]) * 100
                    trade["pnlUsdt"] = trade["budget"] * (trade["pnlPct"] / 100)

                    if trade["pnlPct"] >= trade["targetPct"]:
                        # إرسال أمر بيع لتحقيق الربح
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
                            
