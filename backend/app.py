from pathlib import Path

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from analysis.signal_engine import analyze
from backend.market.assets import ASSETS, TIMEFRAMES
from backend.market.twelvedata import TwelveDataProvider

app = FastAPI(title="Chinese-boot", version="1.0.0")
ROOT = Path(__file__).resolve().parent.parent
market_provider = TwelveDataProvider()

allowed_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "provider": await market_provider.health_check()}


@app.get("/api/assets")
def assets() -> dict:
    return {"assets": ASSETS, "timeframes": TIMEFRAMES}


@app.get("/api/quote")
async def quote(symbol: str = Query(..., min_length=1)) -> dict:
    try:
        return await market_provider.get_quote(symbol)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/candles")
async def candles(
    symbol: str = Query(..., min_length=1),
    timeframe_seconds: int = Query(60, ge=1),
    timeframe: str | None = Query(None),
    seconds: int | None = Query(None, ge=1),
    limit: int = Query(100, ge=1, le=5000),
) -> dict:
    interval_seconds = timeframe_seconds
    if timeframe is not None:
        interval_map = {"1min": 60, "5min": 300}
        if timeframe not in interval_map:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported timeframe: {timeframe}. "
                    "Use 1min or 5min with the matching seconds value."
                ),
            )
        interval_seconds = interval_map[timeframe]
    if seconds is not None:
        if timeframe is not None and seconds != interval_seconds:
            raise HTTPException(
                status_code=400,
                detail="timeframe and seconds must describe the same interval.",
            )
        interval_seconds = seconds
    try:
        values = await market_provider.get_candles(symbol, interval_seconds, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "symbol": symbol.strip().upper(),
        "timeframe_seconds": interval_seconds,
        "candles": values,
    }


@app.post("/api/analyze")
def analyze_market(payload: dict) -> dict:
    return analyze(payload)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "frontend" / "index.html")
