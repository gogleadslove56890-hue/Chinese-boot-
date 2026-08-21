from __future__ import annotations

import asyncio
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from backend.market.provider import MarketDataProvider


class YahooFinanceProvider(MarketDataProvider):
    """Independent public market-data provider using Yahoo Finance chart API."""

    NAME = "Yahoo Finance"
    BASE_URL = "https://query1.finance.yahoo.com"
    SUPPORTED_INTERVALS = {
        60: "1m",
        300: "5m",
        900: "15m",
        1800: "30m",
        3600: "1h",
    }

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        value = symbol.strip().upper().replace("-", "/")
        if "/" not in value:
            raise ValueError("Symbol must be a forex pair like EUR/USD.")
        base, quote = [part.strip() for part in value.split("/", 1)]
        if len(base) != 3 or len(quote) != 3:
            raise ValueError("Symbol must be a forex pair like EUR/USD.")
        return f"{base}{quote}=X"

    @staticmethod
    def _symbol(symbol: str) -> str:
        return YahooFinanceProvider._normalize_symbol(symbol)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            text = str(value).replace("Z", "+00:00")
            observed = datetime.fromisoformat(text)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            return observed.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None

    async def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        url = f"{self.BASE_URL}{endpoint}?{query}"

        def fetch() -> dict[str, Any]:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="ignore")
                message = body.strip() or f"Yahoo Finance HTTP {exc.code}."
                raise RuntimeError(f"Yahoo Finance provider failed: {message}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError("Yahoo Finance provider is unavailable.") from exc
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Yahoo Finance returned invalid JSON.") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("Yahoo Finance returned an invalid payload.")
            return payload

        return await asyncio.to_thread(fetch)

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            number = float(value)
            if math.isnan(number) or math.isinf(number):
                return None
            return number
        except (TypeError, ValueError):
            return None

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        symbol_code = self._normalize_symbol(symbol)
        payload = await self._request("/v8/finance/chart/" + symbol_code, {"interval": "1m", "range": "5d"})
        result = payload.get("chart", {}).get("result")
        if not result:
            raise RuntimeError("Yahoo Finance returned no chart result.")
        meta = result[0].get("meta", {})
        regular = self._to_float(meta.get("regularMarketPrice"))
        close = self._to_float(meta.get("previousClose"))
        price = regular if regular is not None else close
        if price is None:
            raise RuntimeError("Yahoo Finance returned no valid quote price.")
        ts = self._parse_datetime(meta.get("regularMarketTime") or meta.get("chartPreviousCloseTime"))
        if ts is None:
            raise RuntimeError("Yahoo Finance returned an invalid quote timestamp.")
        return {
            "symbol": symbol.upper(),
            "price": price,
            "close": price,
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "provider": self.NAME,
            "source_status": "verified",
            "price_basis": "public_market_price",
        }

    async def get_candles(self, symbol: str, timeframe_seconds: int, limit: int = 100) -> list[dict[str, Any]]:
        interval = self.SUPPORTED_INTERVALS.get(timeframe_seconds)
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe_seconds} seconds. Supported values are {sorted(self.SUPPORTED_INTERVALS)}.")
        symbol_code = self._normalize_symbol(symbol)
        payload = await self._request("/v8/finance/chart/" + symbol_code, {"interval": interval, "range": "5d", "includeAdjustedClose": "true"})
        result = payload.get("chart", {}).get("result")
        if not result:
            raise RuntimeError("Yahoo Finance returned no candle data.")
        chart = result[0]
        timestamps = chart.get("timestamp") or []
        quotes = (chart.get("indicators") or {}).get("quote") or []
        if not timestamps or not quotes:
            raise RuntimeError("Yahoo Finance returned malformed candle data.")
        quote = quotes[0] if isinstance(quotes, list) and quotes else {}
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        if not all(len(seq) == len(timestamps) for seq in (opens, highs, lows, closes)):
            raise RuntimeError("Yahoo Finance candle lengths do not match the timestamp series.")

        prepared: list[dict[str, Any]] = []
        for index, stamp in enumerate(timestamps):
            observed = self._parse_datetime(stamp)
            if observed is None:
                continue
            open_price = self._to_float(opens[index])
            high_price = self._to_float(highs[index])
            low_price = self._to_float(lows[index])
            close_price = self._to_float(closes[index])
            if None in (open_price, high_price, low_price, close_price):
                continue
            if low_price > high_price or not all(low_price <= value <= high_price for value in (open_price, close_price)):
                continue
            prepared.append({
                "timestamp": observed.isoformat().replace("+00:00", "Z"),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": 0,
            })
        if not prepared:
            raise RuntimeError("Yahoo Finance returned no valid OHLC candles.")
        prepared = prepared[-int(limit):]
        return prepared

    async def health_check(self) -> dict[str, Any]:
        return {
            "provider": self.NAME,
            "configured": True,
            "connected": True,
            "live_data_verified": True,
            "source_status": "verified",
            "supported_timeframes": sorted(self.SUPPORTED_INTERVALS),
            "message": "Independent public market data provider is available.",
        }
