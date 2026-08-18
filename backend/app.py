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
  
