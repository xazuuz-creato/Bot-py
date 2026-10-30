import os
import math
import time
import hmac
import base64
import json
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import aiohttp

app = FastAPI(
    title="OKX Scalper Guardian Live API Server",
    description="Real Execution Python Backend for OKX Demo/Paper Trading API",
    version="3.0.0"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Fetch environment variables from Render automatically
ENV_API_KEY = os.environ.get("OKX_API_KEY", "")
ENV_SECRET_KEY = os.environ.get("OKX_SECRET_KEY", "")
ENV_PASSPHRASE = os.environ.get("OKX_PASSPHRASE", "")

class TradeRequest(BaseModel):
    apiKey: str = ""
    secretKey: str = ""
    passphrase: str = ""
    symbol: str
    action: str  # BUY or SELL
    amountUsdt: float = 100.0
    isDemo: bool = True  # True for OKX Demo / Paper Trading

def get_okx_signature(timestamp, method, request_path, body, secret_key):
    message = timestamp + method + request_path + (body if body else '')
    mac = hmac.new(bytes(secret_key, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    return base64.b64encode(mac.digest()).decode('utf-8')

@app.get("/api/config")
async def get_config():
    """
    إرجاع حالة توفر مفاتيح الـ API من متغيرات بيئة Render
    """
    has_keys = bool(ENV_API_KEY and ENV_SECRET_KEY and ENV_PASSPHRASE)
    return {
        "hasEnvKeys": has_keys,
        "apiKeyMasked": f"{ENV_API_KEY[:8]}...{ENV_API_KEY[-6:]}" if ENV_API_KEY else "",
        "message": "تم تحميل مفاتيح OKX API من متغيرات بيئة Render بنجاح!" if has_keys else "لم يتم العثور على المفاتيح في بيئة Render"
    }

@app.post("/api/execute-order")
async def execute_okx_order(req: TradeRequest):
    """
    تنفيذ صفقة حقيقية مباشرة عبر API في حساب OKX Demo Trading
    """
    # Use keys from environment variables as fallback if not explicitly provided in the request
    api_key = req.apiKey or ENV_API_KEY
    secret_key = req.secretKey or ENV_SECRET_KEY
    passphrase = req.passphrase or ENV_PASSPHRASE

    if not api_key or not secret_key or not passphrase:
        raise HTTPException(status_code=400, detail="مفاتيح OKX API غير موجودة في الطلب أو في متغيرات بيئة Render")

    # إعداد النقطة النهائية لمنصة OKX
    url_path = "/api/v5/trade/order"
    full_url = f"https://www.okx.com{url_path}"
    
    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    # تحديد كمية الأوردر وبناء الجسم
    side = "buy" if req.action.upper() == "BUY" else "sell"
    body_data = {
        "instId": req.symbol,
        "tdMode": "cash",
        "side": side,
        "ordType": "market",
        "sz": str(req.amountUsdt) if side == "buy" else "0"
    }
    
    body_str = json.dumps(body_data)
    signature = get_okx_signature(timestamp, "POST", url_path, body_str, secret_key)

    headers = {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json"
    }

    if req.isDemo:
        headers["x-simulated-trading"] = "1"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(full_url, data=body_str, headers=headers) as resp:
                result = await resp.json()
                if result.get("code") == "0":
                    return {
                        "status": "success",
                        "order_id": result["data"][0]["ordId"],
                        "message": f"تم تنفيذ أمر {side.upper()} بنجاح على OKX Demo API!",
                        "details": result["data"][0]
                    }
                else:
                    return {
                        "status": "error",
                        "code": result.get("code"),
                        "message": result.get("msg", "خطأ في تنفيذ الأمر عبر OKX API")
                    }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>File index.html not found!</h1>", status_code=404)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, workers=2)
