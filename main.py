import os
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import ccxt.async_support as ccxt

app = FastAPI(
    title="OKX Scalper Guardian Live/Demo API Server",
    description="Real Account Order Execution Python Backend with CCXT",
    version="6.1.0"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# مفاتيح الـ API الخاصة بك وكلمة المرور المعتمدة
DEFAULT_API_KEY = "74e80fbc-e258-4aa5-ab64-a27882e34775"
DEFAULT_SECRET_KEY = "0FCBDF7BE5A86DB101ABD43B89592EBC"
DEFAULT_PASSPHRASE = "Aa11223344##"

ENV_API_KEY = os.environ.get("OKX_API_KEY", DEFAULT_API_KEY)
ENV_SECRET_KEY = os.environ.get("OKX_SECRET_KEY", DEFAULT_SECRET_KEY)
ENV_PASSPHRASE = os.environ.get("OKX_PASSPHRASE", DEFAULT_PASSPHRASE)

class TradeRequest(BaseModel):
    apiKey: str = ""
    secretKey: str = ""
    passphrase: str = ""
    symbol: str  # e.g., "DOGE-USDT"
    action: str  # BUY or SELL
    amountUsdt: float = 100.0

def get_okx_exchange(api_key=None, secret_key=None, passphrase=None):
    """
    إنشاء اتصال مباشر وآمن مع منصة OKX وتفعيل الحساب التجريبي (Sandbox)
    """
    exchange = ccxt.okx({
        'apiKey': api_key or ENV_API_KEY or DEFAULT_API_KEY,
        'secret': secret_key or ENV_SECRET_KEY or DEFAULT_SECRET_KEY,
        'password': passphrase or ENV_PASSPHRASE or DEFAULT_PASSPHRASE,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot'
        }
    })
    # تفعيل بيئة التداول التجريبي Sandbox حصرياً
    exchange.set_sandbox_mode(True)
    return exchange

@app.get("/api/config")
async def get_config():
    api_k = ENV_API_KEY or DEFAULT_API_KEY
    return {
        "hasEnvKeys": bool(api_k),
        "apiKeyMasked": f"{api_k[:8]}...{api_k[-6:]}" if api_k else "",
        "mode": "OKX Sandbox API via CCXT ⚡",
        "message": "تم ربط الإستراتيجية والميزات بنجاح!"
    }

@app.get("/api/account-balance")
async def get_account_balance():
    """
    جلب رصيد الحساب المباشر من منصة OKX
    """
    exchange = get_okx_exchange()
    try:
        balance = await exchange.fetch_balance()
        await exchange.close()
        
        total_usdt = 0.0
        if 'USDT' in balance and 'total' in balance['USDT']:
            total_usdt = float(balance['USDT']['total'])

        if total_usdt <= 0 and 'info' in balance:
            for item in balance['info'].get('data', []):
                total_usdt = float(item.get('totalEq', 0.0))

        final_bal = round(total_usdt, 2)
        return {"status": "success", "mode": "okx_sandbox", "totalUsdtBalance": final_bal}

    except Exception as e:
        await exchange.close()
        print("OKX Balance Error:", str(e))
        return {"status": "error", "message": str(e), "totalUsdtBalance": 0.0}

@app.post("/api/execute-order")
async def execute_okx_order(req: TradeRequest):
    """
    تنفيذ الأوامر الفورية (شراء/بيع) عبر API المنصة بدون المساس بمميزات الاستراتيجية
    """
    exchange = get_okx_exchange(req.apiKey, req.secretKey, req.passphrase)
    try:
        ccxt_symbol = req.symbol.replace('-', '/')
        side = req.action.lower()
        amount_usdt = float(req.amountUsdt)

        ticker = await exchange.fetch_ticker(ccxt_symbol)
        current_price = ticker['last']
        amount_coins = amount_usdt / current_price if current_price > 0 else 1.0

        order = await exchange.create_order(
            symbol=ccxt_symbol,
            type='market',
            side=side,
            amount=amount_coins,
            params={
                'tgtCcy': 'quote' if side == 'buy' else 'base'
            }
        )
        await exchange.close()

        return {
            "status": "success",
            "order_id": order.get('id'),
            "message": f"تم تنفيذ أمر {side.upper()} على {ccxt_symbol} بنجاح عبر API!",
            "details": order
        }

    except Exception as e:
        await exchange.close()
        print("OKX Order Execution Error:", str(e))
        return {
            "status": "error",
            "message": f"رفضت المنصة الأمر: {str(e)}"
        }

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>File index.html not found!</h1>", status_code=404)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
