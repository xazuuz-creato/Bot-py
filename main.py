"""Rapid Guard V5: public Binance Spot data, isolated paper trading only.
No private Binance API credentials are read or used.
"""
import asyncio
import math
import os
import secrets
import sqlite3
import tempfile
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import httpx
import websockets
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = os.getenv(
    "DATABASE_PATH",
    str(ROOT / "scalper.sqlite3")
)
ACCESS_KEY = os.getenv("APP_ACCESS_KEY", "")

FEE = float(os.getenv("DEMO_FEE_RATE", "0.001"))
SLIP = float(os.getenv("DEMO_SLIPPAGE_RATE", "0.0002"))
TARGET_PCT = float(os.getenv("TARGET_GROSS_PCT", "0.45"))
STOP_PCT = float(os.getenv("STOP_GROSS_PCT", "0.30"))
MAX_SPREAD = float(os.getenv("MAX_SPREAD_PCT", "0.05"))
MIN_IMBALANCE = float(os.getenv("MIN_IMBALANCE", "1.5"))
MIN_BUY_RATIO = float(os.getenv("MIN_BUY_RATIO", "0.60"))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "3"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS_USDT", "25"))
MAX_HOLD = int(os.getenv("MAX_HOLD_SECONDS", "180"))
START_CASH = float(os.getenv("DEMO_START_BALANCE", "10000"))

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT",
    "XRPUSDT", "BNBUSDT", "DOGEUSDT",
    "ADAUSDT", "LINKUSDT", "AVAXUSDT",
    "LTCUSDT", "DOTUSDT", "TRXUSDT"
]

if not (
    0 <= FEE < .02
    and 0 <= SLIP < .02
    and 0 < TARGET_PCT < 10
    and 0 < STOP_PCT < 10
    and 0 < MAX_SPREAD < 2
):
    raise RuntimeError("Invalid risk/fee configuration")


class Engine:
    def __init__(self, db_path):
        self.db_path = str(db_path)

        Path(self.db_path).parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.books = {}
        self.samples = defaultdict(
            lambda: deque(maxlen=35)
        )
        self.tape = defaultdict(
            lambda: deque(maxlen=1500)
        )
        self.tokens = {}
        self.last_scan = {}
        self.verified = set()
        self.connected = False
        self.last_event = 0.0
        self.last_error = ""
        self.auto = False
        self.lock = asyncio.Lock()

        with self.db() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS wallet (
                    id INTEGER PRIMARY KEY,
                    cash REAL NOT NULL
                )
            """)

            c.execute(
                "INSERT OR IGNORE INTO wallet VALUES (1,?)",
                (START_CASH,)
            )

            c.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    entry REAL NOT NULL,
                    qty REAL NOT NULL,
                    cost REAL NOT NULL,
                    buy_fee REAL NOT NULL,
                    opened REAL NOT NULL,
                    peak REAL NOT NULL,
                    stop REAL NOT NULL,
                    target REAL NOT NULL,
                    hold INTEGER NOT NULL
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    entry REAL NOT NULL,
                    exit REAL NOT NULL,
                    qty REAL NOT NULL,
                    buy_fee REAL NOT NULL,
                    sell_fee REAL NOT NULL,
                    gross REAL NOT NULL,
                    net REAL NOT NULL,
                    opened REAL NOT NULL,
                    closed REAL NOT NULL,
                    reason TEXT NOT NULL
                )
            """)

    @contextmanager
    def db(self):
        c = sqlite3.connect(
            self.db_path,
            timeout=10
        )
        c.row_factory = sqlite3.Row

        try:
            with c:
                yield c
        finally:
            c.close()

    def position(self, symbol):
        with self.db() as c:
            r = c.execute(
                "SELECT * FROM positions WHERE symbol=?",
                (symbol,)
            ).fetchone()

        return dict(r) if r else None

    def state(self):
        with self.db() as c:
            cash = float(
                c.execute(
                    "SELECT cash FROM wallet WHERE id=1"
                ).fetchone()[0]
            )

            positions = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM positions ORDER BY opened DESC"
                )
            ]

            history = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM history ORDER BY id DESC LIMIT 100"
                )
            ]

        equity = cash

        for p in positions:
            b = self.books.get(p["symbol"])

            price = (
                b["bid"]
                if b and time.time() - b["t"] < 3
                else p["entry"]
            )

            equity += (
                p["qty"]
                * price
                * (1 - SLIP)
                * (1 - FEE)
            )

        return {
            "cashUsdt": cash,
            "estimatedEquityUsdt": equity,
            "positions": positions,
            "history": history,
            "autoEnabled": self.auto
        }

    def update_book(
        self,
        symbol,
        bids,
        asks,
        at=None
    ):
        if symbol not in SYMBOLS:
            raise ValueError("Unknown symbol")

        try:
            b = sorted(
                [
                    (float(p), float(q))
                    for p, q in bids[:5]
                ],
                reverse=True
            )

            a = sorted(
                [
                    (float(p), float(q))
                    for p, q in asks[:5]
                ]
            )

        except (ValueError, TypeError, IndexError) as exc:
            raise ValueError(
                "Malformed order book"
            ) from exc

        if (
            not b
            or not a
            or b[0][0] >= a[0][0]
            or any(
                not math.isfinite(x) or x <= 0
                for pair in b + a
                for x in pair
            )
        ):
            raise ValueError(
                "Invalid/crossed order book"
            )

        t = time.time() if at is None else at

        imbalance = (
            sum(p * q for p, q in b)
            / sum(p * q for p, q in a)
        )

        self.books[symbol] = {
            "bid": b[0][0],
            "ask": a[0][0],
            "imbalance": imbalance,
            "t": t
        }

        self.samples[symbol].append({
            "mid": (b[0][0] + a[0][0]) / 2,
            "imbalance": imbalance,
            "t": t
        })

        self.last_event = time.time()

    def update_trade(
        self,
        symbol,
        price,
        qty,
        buyer_maker,
        at=None
    ):
        if (
            symbol not in SYMBOLS
            or not all(
                math.isfinite(v) and v > 0
                for v in (price, qty)
            )
        ):
            raise ValueError("Invalid trade")

        self.tape[symbol].append({
            "p": price,
            "q": qty,
            "buyer_maker": buyer_maker,
            "t": (
                time.time()
                if at is None
                else at
            )
        })

        self.last_event = time.time()

    def fresh(self, symbol):
        b = self.books.get(symbol)

        if not b or time.time() - b["t"] > 3:
            raise ValueError(
                "Market data stale; execution blocked"
            )

        return b

    def features(self, symbol):
        b = self.fresh(symbol)
        now = time.time()

        h = [
            x for x in self.samples[symbol]
            if now - x["t"] <= 6
        ]

        t = [
            x for x in self.tape[symbol]
            if now - x["t"] <= 5
        ]

        if (
            len(h) < 7
            or h[-1]["t"] - h[0]["t"] < .5
            or not t
        ):
            raise ValueError(
                "Insufficient recent depth/trade samples"
            )

        buy = sum(
            x["p"] * x["q"]
            for x in t
            if not x["buyer_maker"]
        )

        sell = sum(
            x["p"] * x["q"]
            for x in t
            if x["buyer_maker"]
        )

        if buy + sell <= 0:
            raise ValueError(
                "No executed volume"
            )

        m = len(h) // 2

        v1 = (
            (h[m]["mid"] / h[0]["mid"] - 1)
            / max(
                h[m]["t"] - h[0]["t"],
                .01
            )
        )

        v2 = (
            (h[-1]["mid"] / h[m]["mid"] - 1)
            / max(
                h[-1]["t"] - h[m]["t"],
                .01
            )
        )

        return {
            "imbalance": round(
                b["imbalance"], 4
            ),
            "sustained": round(
                sum(
                    x["imbalance"] >= MIN_IMBALANCE
                    for x in h
                ) / len(h),
                4
            ),
            "buyRatio": round(
                buy / (buy + sell), 4
            ),
            "spreadPct": round(
                (b["ask"] - b["bid"])
                / b["ask"] * 100,
                5
            ),
            "velocityPctPerSec": round(
                (
                    h[-1]["mid"] / h[0]["mid"] - 1
                ) * 100 / (
                    h[-1]["t"] - h[0]["t"]
                ),
                5
            ),
            "acceleration": round(
                (v2 - v1) * 100, 5
            ),
            "executedNotional5s": round(
                buy + sell, 2
            )
        }

    def daily_pnl(self):
        midnight = (
            int(time.time() // 86400) * 86400
        )

        with self.db() as c:
            return float(
                c.execute(
                    """
                    SELECT COALESCE(SUM(net),0)
                    FROM history
                    WHERE closed>=?
                    """,
                    (midnight,)
                ).fetchone()[0]
            )

    def signal(self, symbol):
        try:
            f = self.features(symbol)

        except ValueError as exc:
            return {
                "enter": False,
                "reasons": [str(exc)]
            }

        friction = (
            (2 * FEE + 2 * SLIP) * 100
            + f["spreadPct"]
        )

        checks = [
            (
                f["imbalance"] >= MIN_IMBALANCE,
                "عمق الشراء ضعيف"
            ),
            (
                f["sustained"] >= .70,
                "عمق الشراء غير مستمر"
            ),
            (
                f["buyRatio"] >= MIN_BUY_RATIO,
                "الشراء المنفذ ضعيف"
            ),
            (
                f["spreadPct"] <= MAX_SPREAD,
                "السبريد مرتفع"
            ),
            (
                f["velocityPctPerSec"] > 0,
                "الزخم غير إيجابي"
            ),
            (
                f["acceleration"] >= -.002,
                "الزخم يتباطأ"
            ),
            (
                TARGET_PCT - friction >= .10,
                "الهدف لا يغطي التكاليف"
            )
        ]

        reasons = [
            reason
            for ok, reason in checks
            if not ok
        ]

        with self.db() as c:
            n = c.execute(
                "SELECT COUNT(*) FROM positions"
            ).fetchone()[0]

        if self.position(symbol):
            reasons.append(
                "يوجد مركز مفتوح"
            )

        if n >= MAX_POSITIONS:
            reasons.append(
                "الحد الأقصى للمراكز"
            )

        if self.daily_pnl() <= -MAX_DAILY_LOSS:
            reasons.append(
                "حد الخسارة اليومي"
            )

        if symbol not in self.verified:
            reasons.append(
                "الزوج غير متحقق من Binance Spot"
            )

        result = {
            "enter": not reasons,
            "reasons": reasons,
            "features": f,
            "estimatedNetAtTargetPct": round(
                TARGET_PCT - friction, 5
            )
        }

        if not reasons:
            token = secrets.token_urlsafe(24)

            self.tokens[token] = (
                symbol,
                time.time() + 4,
                self.books[symbol]["ask"]
            )

            result["signalToken"] = token

        if len(self.tokens) > 300:
            self.tokens = {
                k: v
                for k, v in self.tokens.items()
                if v[1] > time.time()
            }

        return result

    def buy(
        self,
        symbol,
        budget,
        token,
        hold
    ):
        b = self.fresh(symbol)

        record = self.tokens.pop(
            token, None
        )

        if (
            not record
            or record[0] != symbol
            or record[1] < time.time()
            or abs(
                b["ask"] / record[2] - 1
            ) > .001
        ):
            raise ValueError(
                "Invalid, used, or expired signal token"
            )

        if symbol not in self.verified:
            raise ValueError(
                "Unverified symbol"
            )

        # Recheck the complete entry conditions.
        check = self.signal(symbol)

        if not check["enter"]:
            raise ValueError(
                "Signal expired: "
                + ", ".join(check["reasons"])
            )

        if not (
            10 <= budget <= 100000
            and 30 <= hold <= 600
        ):
            raise ValueError(
                "Invalid budget/hold"
            )

        with self.db() as c:
            cash = c.execute(
                "SELECT cash FROM wallet WHERE id=1"
            ).fetchone()[0]

            if cash < budget:
                raise ValueError(
                    "Insufficient demo balance"
                )

            fill = b["ask"] * (1 + SLIP)

            cost = budget / (1 + FEE)
            fee = cost * FEE
            qty = cost / fill

            c.execute(
                """
                UPDATE wallet
                SET cash=cash-?
                WHERE id=1
                """,
                (budget,)
            )

            c.execute(
                """
                INSERT INTO positions
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    symbol,
                    fill,
                    qty,
                    cost,
                    fee,
                    time.time(),
                    fill,
                    fill * (
                        1 - STOP_PCT / 100
                    ),
                    fill * (
                        1 + TARGET_PCT / 100
                    ),
                    hold
                )
            )

        return {
            "status": "success",
            "action": "BUY",
            "fillPrice": fill,
            "quantity": qty,
            "feeUsdt": fee,
            "mode": "DEMO"
        }

    def sell(
        self,
        symbol,
        reason="MANUAL"
    ):
        b = self.fresh(symbol)

        with self.db() as c:
            r = c.execute(
                """
                SELECT *
                FROM positions
                WHERE symbol=?
                """,
                (symbol,)
            ).fetchone()

            if not r:
                raise ValueError(
                    "No open position"
                )

            p = dict(r)

            fill = b["bid"] * (1 - SLIP)

            gross_proceeds = (
                p["qty"] * fill
            )

            sell_fee = (
                gross_proceeds * FEE
            )

            gross_pnl = (
                gross_proceeds - p["cost"]
            )

            net = (
                gross_pnl
                - p["buy_fee"]
                - sell_fee
            )

            c.execute(
                """
                UPDATE wallet
                SET cash=cash+?
                WHERE id=1
                """,
                (
                    gross_proceeds - sell_fee,
                )
            )

            c.execute(
                """
                DELETE FROM positions
                WHERE symbol=?
                """,
                (symbol,)
            )

            c.execute(
                """
                INSERT INTO history (
                    symbol,
                    entry,
                    exit,
                    qty,
                    buy_fee,
                    sell_fee,
                    gross,
                    net,
                    opened,
                    closed,
                    reason
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    symbol,
                    p["entry"],
                    fill,
                    p["qty"],
                    p["buy_fee"],
                    sell_fee,
                    gross_pnl,
                    net,
                    p["opened"],
                    time.time(),
                    reason[:60]
                )
            )

        return {
            "status": "success",
            "action": "SELL",
            "fillPrice": fill,
            "netPnlUsdt": net,
            "feeUsdt": sell_fee,
            "mode": "DEMO"
        }

    def exit_reason(self, symbol):
        p = self.position(symbol)

        if not p:
            return None

        bid = self.fresh(symbol)["bid"]

        peak = max(
            p["peak"], bid
        )

        stop = p["stop"]

        if (
            (peak / p["entry"] - 1) * 100
            > (2 * FEE + 2 * SLIP) * 100 + .15
        ):
            stop = max(
                stop,
                peak * (1 - .0015)
            )

        if (
            peak != p["peak"]
            or stop != p["stop"]
        ):
            with self.db() as c:
                c.execute(
                    """
                    UPDATE positions
                    SET peak=?,stop=?
                    WHERE symbol=?
                    """,
                    (
                        peak,
                        stop,
                        symbol
                    )
                )

        if bid <= stop:
            return "STOP_OR_TRAIL"

        if bid >= p["target"]:
            return "TAKE_PROFIT"

        if (
            time.time() - p["opened"]
            >= p["hold"]
        ):
            return "TIMEOUT"

        return None


engine = Engine(DB_PATH)


def require_key(value):
    if not ACCESS_KEY:
        raise HTTPException(
            503,
            "اضبط APP_ACCESS_KEY في إعدادات السيرفر"
        )

    if (
        not value
        or not secrets.compare_digest(
            value, ACCESS_KEY
        )
    ):
        raise HTTPException(
            401,
            "مفتاح الوصول غير صحيح"
        )


class ControlIn(BaseModel):
    enabled: bool


class SymbolIn(BaseModel):
    symbol: str


class OrderIn(BaseModel):
    symbol: str
    action: str
    amountUsdt: float = Field(
        default=100,
        ge=10,
        le=100000
    )
    signalToken: str | None = None
    maxHoldSeconds: int = Field(
        default=MAX_HOLD,
        ge=30,
        le=600
    )
    useDemo: bool = True


def valid_symbol(s):
    s = (
        s.upper()
        .replace("/", "")
        .strip()
    )

    if s not in SYMBOLS:
        raise HTTPException(
            400,
            "رمز غير مدعوم"
        )

    return s


async def verify_symbols():
    urls = [
        "https://data-api.binance.vision/api/v3/exchangeInfo",
        "https://api.binance.com/api/v3/exchangeInfo"
    ]

    for url in urls:
        try:
            async with httpx.AsyncClient(
                timeout=8
            ) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()

            valid = {
                x["symbol"]
                for x in data["symbols"]
                if (
                    x.get("status") == "TRADING"
                    and x.get(
                        "isSpotTradingAllowed",
                        False
                    )
                )
            }

            result = (
                set(SYMBOLS) & valid
            )

            if result:
                return result

        except Exception as exc:
            engine.last_error = (
                "Spot verification: "
                + type(exc).__name__
            )

    # Fail closed if Binance verification fails.
    return set()


async def market_worker():
    while True:
        try:
            verified = await verify_symbols()

            engine.verified = verified

            if not verified:
                raise RuntimeError(
                    "تعذر التحقق من أزواج Binance Spot"
                )

            streams = "/".join(
                x
                for s in sorted(verified)
                for x in (
                    s.lower() + "@depth5@100ms",
                    s.lower() + "@aggTrade"
                )
            )

            hosts = [
                "wss://data-stream.binance.vision/stream?streams=",
                "wss://stream.binance.com:9443/stream?streams="
            ]

            for host in hosts:
                try:
                    async with websockets.connect(
                        host + streams,
                        open_timeout=10,
                        ping_interval=20,
                        ping_timeout=20,
                        max_size=2**20
                    ) as ws:

                        engine.connected = True
                        engine.last_error = ""

                        async for raw in ws:
                            import json

                            packet = json.loads(raw)
                            d = packet.get(
                                "data", {}
                            )

                            s = str(
                                d.get("s")
                                or packet.get(
                                    "stream", ""
                                ).split("@")[0]
                            ).upper()

                            if s not in verified:
                                continue

                            async with engine.lock:
                                if (
                                    "bids" in d
                                    and "asks" in d
                                ):
                                    engine.update_book(
                                        s,
                                        d["bids"],
                                        d["asks"]
                                    )

                                elif (
                                    d.get("e")
                                    == "aggTrade"
                                ):
                                    engine.update_trade(
                                        s,
                                        float(d["p"]),
                                        float(d["q"]),
                                        bool(d["m"])
                                    )

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    engine.last_error = (
                        "Stream: "
                        + type(exc).__name__
                        + ": "
                        + str(exc)[:100]
                    )

                finally:
                    engine.connected = False

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            engine.connected = False
            engine.last_error = str(exc)[:160]

        await asyncio.sleep(5)


async def monitor_worker():
    while True:
        try:
            await asyncio.sleep(.6)

            async with engine.lock:
                for p in engine.state()["positions"]:
                    try:
                        reason = engine.exit_reason(
                            p["symbol"]
                        )

                        if reason:
                            engine.sell(
                                p["symbol"],
                                reason
                            )

                    except ValueError:
                        # Never invent a fill with stale data.
                        pass

                if (
                    not engine.auto
                    or not engine.connected
                ):
                    continue

                for symbol in sorted(
                    engine.verified
                ):
                    if (
                        time.time()
                        - engine.last_scan.get(
                            symbol, 0
                        ) < 2
                    ):
                        continue

                    engine.last_scan[symbol] = (
                        time.time()
                    )

                    signal = engine.signal(
                        symbol
                    )

                    if signal.get("enter"):
                        try:
                            engine.buy(
                                symbol,
                                100,
                                signal["signalToken"],
                                MAX_HOLD
                            )

                        except (
                            ValueError,
                            sqlite3.Error
                        ):
                            pass

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            engine.last_error = (
                "Monitor: "
                + type(exc).__name__
                + ": "
                + str(exc)[:100]
            )


@asynccontextmanager
async def lifespan(app):
    tasks = [
        asyncio.create_task(
            market_worker()
        ),
        asyncio.create_task(
            monitor_worker()
        )
    ]

    try:
        yield

    finally:
        for t in tasks:
            t.cancel()

        await asyncio.gather(
            *tasks,
            return_exceptions=True
        )


app = FastAPI(
    title="Rapid Guard V5 — Demo Only",
    lifespan=lifespan
)


@app.get("/")
def home():
    return FileResponse(
        ROOT / "index.html"
    )


@app.get("/api/status")
def status():
    age = (
        time.time() - engine.last_event
        if engine.last_event
        else None
    )

    return {
        "mode": "DEMO_ONLY",
        "connected": engine.connected,
        "dataAgeSeconds": (
            round(age, 2)
            if age is not None
            else None
        ),
        "verifiedSymbols": sorted(
            engine.verified
        ),
        "autoEnabled": engine.auto,
        "error": engine.last_error,
        "tickers": {
            s: {
                "bid": b["bid"],
                "ask": b["ask"],
                "imbalance": round(
                    b["imbalance"], 3
                ),
                "age": round(
                    time.time() - b["t"], 2
                )
            }
            for s, b in engine.books.items()
            if s in engine.verified
        },
        "feeRatePerSide": FEE,
        "slippageRatePerSide": SLIP,
        "targetPct": TARGET_PCT,
        "stopPct": STOP_PCT
    }


@app.get("/api/state")
def state(
    x_access_key: str | None = Header(None)
):
    require_key(x_access_key)
    return engine.state()


@app.post("/api/control")
async def control(
    req: ControlIn,
    x_access_key: str | None = Header(None)
):
    require_key(x_access_key)

    async with engine.lock:
        if req.enabled and (
            not engine.connected
            or not engine.verified
        ):
            raise HTTPException(
                409,
                "لا يوجد اتصال موثوق ببيانات Binance"
            )

        engine.auto = req.enabled

    return {
        "autoEnabled": engine.auto
    }


@app.post("/api/signal")
async def signal(
    req: SymbolIn,
    x_access_key: str | None = Header(None)
):
    require_key(x_access_key)

    async with engine.lock:
        return engine.signal(
            valid_symbol(req.symbol)
        )


@app.post("/api/order")
async def order(
    req: OrderIn,
    x_access_key: str | None = Header(None)
):
    require_key(x_access_key)

    if not req.useDemo:
        raise HTTPException(
            403,
            "التداول الحقيقي معطل بالكامل"
        )

    symbol = valid_symbol(
        req.symbol
    )

    if req.action not in (
        "BUY", "SELL"
    ):
        raise HTTPException(
            422,
            "أمر غير معروف"
        )

    async with engine.lock:
        try:
            if req.action == "BUY":
                return engine.buy(
                    symbol,
                    req.amountUsdt,
                    req.signalToken,
                    req.maxHoldSeconds
                )

            return engine.sell(
                symbol,
                "MANUAL"
            )

        except (
            ValueError,
            sqlite3.IntegrityError
        ) as exc:
            raise HTTPException(
                409,
                str(exc)
            )


# ==========================================
# ISOLATED SELF-TESTS
# ==========================================

def self_tests():
    results = []

    def run(name, fn):
        try:
            detail = fn()

            results.append({
                "name": name,
                "status": "PASS",
                "detail": detail
            })

        except Exception as exc:
            results.append({
                "name": name,
                "status": "FAIL",
                "detail": (
                    f"{type(exc).__name__}: {exc}"
                )
            })

    def fixture(fn):
        with tempfile.TemporaryDirectory() as folder:
            e = Engine(
                Path(folder) / "test.sqlite3"
            )

            e.verified = {
                "BTCUSDT"
            }

            return fn(e)

    def seed(e):
        start = time.time() - .8

        for i in range(8):
            mid = (
                100 + .004 * i * i
            )

            e.update_book(
                "BTCUSDT",
                [
                    [mid - .01, 15],
                    [mid - .02, 10]
                ],
                [
                    [mid + .01, 2],
                    [mid + .02, 2]
                ],
                start + i * .1
            )

        e.update_trade(
            "BTCUSDT",
            100.2,
            20,
            False
        )

        e.update_trade(
            "BTCUSDT",
            100.2,
            2,
            True
        )

    def indicators(e):
        seed(e)

        f = e.features(
            "BTCUSDT"
        )

        assert f["imbalance"] > 1.5
        assert f["buyRatio"] > .8
        assert f["velocityPctPerSec"] > 0

        return (
            f"imbalance={f['imbalance']}, "
            f"buyRatio={f['buyRatio']}"
        )

    def signals(e):
        assert not e.signal(
            "BTCUSDT"
        )["enter"]

        seed(e)

        assert e.signal(
            "BTCUSDT"
        )["enter"]

        return (
            "Missing data rejected; "
            "synthetic signal accepted"
        )

    def execution(e):
        seed(e)

        token = e.signal(
            "BTCUSDT"
        )["signalToken"]

        e.buy(
            "BTCUSDT",
            100,
            token,
            180
        )

        try:
            e.buy(
                "BTCUSDT",
                100,
                token,
                180
            )

        except ValueError:
            pass

        else:
            raise AssertionError(
                "Replay accepted"
            )

        sold = e.sell(
            "BTCUSDT"
        )

        assert (
            sold["status"] == "success"
            and not e.state()["positions"]
        )

        return (
            "BUY, SELL, replay protection"
        )

    def fees(e):
        seed(e)

        e.buy(
            "BTCUSDT",
            100,
            e.signal(
                "BTCUSDT"
            )["signalToken"],
            180
        )

        p = e.position(
            "BTCUSDT"
        )

        result = e.sell(
            "BTCUSDT"
        )

        expected = (
            p["qty"]
            * result["fillPrice"]
            * (1 - FEE)
            - p["cost"]
            - p["buy_fee"]
        )

        assert abs(
            expected - result["netPnlUsdt"]
        ) < 1e-9

        assert abs(
            e.state()["cashUsdt"]
            - (START_CASH + expected)
        ) < 1e-8

        return (
            f"Net={expected:.6f} USDT; "
            "wallet reconciled"
        )

    def recovery(e):
        seed(e)

        e.buy(
            "BTCUSDT",
            100,
            e.signal(
                "BTCUSDT"
            )["signalToken"],
            180
        )

        restored = Engine(
            e.db_path
        )

        assert restored.position(
            "BTCUSDT"
        ) is not None

        assert abs(
            restored.state()["cashUsdt"]
            - (START_CASH - 100)
        ) < 1e-8

        return (
            "SQLite position and cash restored"
        )

    def validation(e):
        try:
            e.update_book(
                "BTCUSDT",
                [[101, 1]],
                [[100, 1]]
            )

        except ValueError:
            return (
                "Crossed book rejected"
            )

        raise AssertionError(
            "Crossed book accepted"
        )

    checks = [
        (
            "التحقق من دفتر الطلبات",
            validation
        ),
        (
            "المؤشرات",
            indicators
        ),
        (
            "الإشارات",
            signals
        ),
        (
            "الشراء والبيع",
            execution
        ),
        (
            "الرسوم والرصيد",
            fees
        ),
        (
            "استعادة SQLite",
            recovery
        )
    ]

    for name, fn in checks:
        run(
            name,
            lambda fn=fn: fixture(fn)
        )

    return results


@app.post("/api/self-test")
async def self_test(
    x_access_key: str | None = Header(None)
):
    require_key(x_access_key)

    results = await asyncio.to_thread(
        self_tests
    )

    return {
        "isolated": True,
        "liveOrdersSent": 0,
        "results": results,
        "passed": sum(
            r["status"] == "PASS"
            for r in results
        ),
        "failed": sum(
            r["status"] == "FAIL"
            for r in results
        )
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(
            os.getenv("PORT", "10000")
        )
    )
