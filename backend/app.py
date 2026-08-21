import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from analysis.signal_engine import analyze
from backend.audit_log import AuditLog
from backend.market.assets import ASSETS, TIMEFRAMES
from backend.market.fallback import FallbackMarketDataProvider
from backend.market.olymptrade import OlympTradeProvider
from backend.market.twelvedata import TwelveDataProvider
from backend.scanner import SUPPORTED_TIMEFRAMES, Scanner

app = FastAPI(title="Chinese-boot", version="1.0.0")
provider_name = "independent-fallback"
configured_providers = []
if os.getenv("TWELVE_DATA_API_KEY"):
    configured_providers.append(TwelveDataProvider())
configured_providers.append(OlympTradeProvider())
market_provider = FallbackMarketDataProvider(configured_providers)
audit_log = AuditLog()
scanner = Scanner(market_provider, audit_log)

allowed_origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "provider": await market_provider.health_check(),
        "configured_provider": provider_name,
        "scanner": {
            "mode": scanner.mode,
            "running": scanner.running,
            "auto_execution_available": scanner.execution.available,
        },
    }


@app.get("/api/assets")
def assets() -> dict:
    return {
        "assets": ASSETS,
        "timeframes": [item for item in TIMEFRAMES if item["seconds"] in SUPPORTED_TIMEFRAMES],
        "provider": provider_name,
        "provider_label": "Independent market-data fallback",
    }


@app.get("/api/quote")
async def quote(symbol: str = Query(..., min_length=1)) -> dict:
    try:
        result = await market_provider.get_quote(symbol)
        return {**result, "provider": result.get("provider", "unknown"), "source_status": result.get("source_status", "verified")}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/olymptrade-reference")
def olymptrade_reference() -> dict:
    provider = OlympTradeProvider()
    return {
        "source": provider.NAME,
        "available": False,
        "price": None,
        "timestamp": None,
        "message": str(provider._unavailable()),
        "official_url": provider.OFFICIAL_URL,
        "verification_status": "unavailable",
    }


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
        interval_map = {"1min": 60, "5min": 300, "15min": 900, "30min": 1800, "1h": 3600}
        if timeframe not in interval_map:
            raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}. Use 1min, 5min, 15min, 30min, or 1h with the matching seconds value.")
        interval_seconds = interval_map[timeframe]
    if seconds is not None:
        if timeframe is not None and seconds != interval_seconds:
            raise HTTPException(status_code=400, detail="timeframe and seconds must describe the same interval.")
        interval_seconds = seconds
    if interval_seconds not in SUPPORTED_TIMEFRAMES:
        return {
            "symbol": symbol.strip().upper(),
            "timeframe_seconds": interval_seconds,
            "candles": [],
            "provider": "unavailable",
            "source_status": "unavailable",
            "analysis_available": False,
            "latest_price": None,
            "latest_timestamp": None,
            "signal": "WAIT",
            "confidence": 0,
            "reason": f"Unsupported timeframe: {interval_seconds} seconds. Verified candle data is unavailable.",
        }
    try:
        values = await market_provider.get_candles(symbol, interval_seconds, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "symbol": getattr(market_provider, "_symbol", lambda value: value.upper())(symbol),
        "timeframe_seconds": interval_seconds,
        "candles": values,
        "provider": getattr(market_provider, "last_selection", {}).get("provider", "unknown"),
        "source_status": "verified",
        "analysis_available": bool(values),
        "latest_price": values[-1]["close"] if values else None,
        "latest_timestamp": values[-1].get("timestamp") if values else None,
    }


@app.post("/api/analyze")
def analyze_market(payload: dict) -> dict:
    if payload.get("source_status") != "verified":
        raise HTTPException(status_code=409, detail="Analysis source mismatch: candles are not verified market data.")
    return analyze(payload)


@app.get("/api/scanner/status")
def scanner_status() -> dict:
    return {
        "mode": scanner.mode,
        "running": scanner.running,
        "status": "scanning" if scanner.running else "stopped",
        "auto_enabled": False,
        "auto_execution_available": scanner.execution.available,
        "message": "Authorized Olymp Trade trading access is required for AUTO mode.",
    }


@app.post("/api/scanner/scan")
async def scanner_scan(payload: dict) -> dict:
    symbol = str(payload.get("symbol", "EUR/USD"))
    timeframe = int(payload.get("timeframe_seconds", 60))
    limit = int(payload.get("limit", 100))
    return await scanner.scan(symbol, timeframe, limit)


@app.post("/api/scanner/start")
def scanner_start(payload: dict = {}) -> dict:
    try:
        return scanner.start(str(payload.get("mode", "MANUAL")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/scanner/stop")
def scanner_stop() -> dict:
    return scanner.stop()


@app.post("/api/scanner/emergency-stop")
def scanner_emergency_stop() -> dict:
    return scanner.emergency_stop()


@app.get("/api/audit")
def audit() -> dict:
    return {"events": audit_log.recent()}


@app.websocket("/api/scanner/live")
async def scanner_live(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(scanner_status())
            await asyncio.sleep(5)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/downloads/chinese-boot-scanner.apk")
def android_apk() -> FileResponse:
    apk = ROOT / "downloads" / "chinese-boot-scanner.apk"
    if not apk.is_file():
        raise HTTPException(status_code=404, detail="Android APK download is unavailable.")
    return FileResponse(apk, media_type="application/vnd.android.package-archive", filename="chinese-boot-scanner.apk")
