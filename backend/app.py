from fastapi import FastAPI
from fastapi.responses import FileResponse
from pathlib import Path

from backend.market.assets import ASSETS, TIMEFRAMES
from backend.analysis.signal_engine import analyze

app = FastAPI(title="Chinese-boot", version="0.1.0")

ROOT = Path(__file__).resolve().parent.parent


@app.get("/api/assets")
def assets():
    return {
        "assets": ASSETS,
        "timeframes": TIMEFRAMES
    }


@app.post("/api/analyze")
def analyze_market(payload: dict):
    return analyze(payload)


@app.get("/")
def index():
    return FileResponse(
        ROOT / "frontend" / "index.html"
    )
  from backend.market.twelvedata import TwelveDataProvider


market_provider = TwelveDataProvider()


@app.get("/api/quote")
async def get_quote(symbol: str):
    symbol = symbol.strip()

    if not symbol:
        return {"error": "Symbol is required"}

    candles = await market_provider.get_candles(
        symbol=symbol,
        timeframe_seconds=60,
        limit=1,
    )

    if not candles:
        return {
            "symbol": symbol,
            "price": None,
            "error": "No market data available",
        }

    candle = candles[-1]

    return {
        "symbol": symbol,
        "price": candle["close"],
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
    }


@app.get("/api/candles")
async def get_candles(
    symbol: str,
    timeframe_seconds: int = 60,
    limit: int = 100,
):
    symbol = symbol.strip()

    if not symbol:
        return {"error": "Symbol is required"}

    candles = await market_provider.get_candles(
        symbol=symbol,
        timeframe_seconds=timeframe_seconds,
        limit=limit,
    )

    return {
        "symbol": symbol,
        "timeframe_seconds": timeframe_seconds,
        "candles": candles,
    }
    
