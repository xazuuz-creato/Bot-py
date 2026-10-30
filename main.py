import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="OKX Scalper Guardian Server")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>File index.html not found!</h1>", status_code=404)

@app.get("/health")
async def health_check():
    return {"status": "ok", "engine": "FastAPI Async Python"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
