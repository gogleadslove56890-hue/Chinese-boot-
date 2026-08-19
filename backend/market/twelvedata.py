from __future__ import annotations

import asyncio
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class TwelveDataProvider:
    """Async REST adapter for verified Twelve Data market data."""

    DEFAULT_BASE_URL = "https://api.twelvedata.com"
    SUPPORTED_INTERVALS = {60: "1min", 300: "5min"}

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.getenv("TWELVE_DATA_API_KEY")
        )
        self.base_url = (
            base_url or os.getenv("TWELVE_DATA_BASE_URL") or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout

    def _require_key(self) -> str:
        if not self.api_key:
            raise RuntimeError("TWELVE_DATA_API_KEY is not configured.")
        return self.api_key

    async def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode({**params, "apikey": self._require_key()})
        url = f"{self.base_url}/{endpoint}?{query}"

        def fetch() -> dict[str, Any]:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Chinese-boot/1.0",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                try:
                    details = json.loads(exc.read().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    details = {}
                message = details.get("message") if isinstance(details, dict) else None
                suffix = f": {message}" if message else "."
                raise RuntimeError(f"Twelve Data HTTP error {exc.code}{suffix}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError("Unable to reach Twelve Data.") from exc
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Twelve Data returned invalid JSON.") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("Twelve Data returned an invalid response.")
            return payload

        payload = await asyncio.to_thread(fetch)
        if payload.get("status") == "error" or payload.get("code") in {401, 403, 429}:
            raise RuntimeError(str(payload.get("message") or "Twelve Data request failed."))
        return payload

    @staticmethod
    def _symbol(symbol: str) -> str:
        value = symbol.strip().upper()
        if not value or "/" not in value:
            raise ValueError("Symbol must be a currency pair such as EUR/USD.")
        return value

    @staticmethod
    def _parse_candles(values: Any) -> list[dict[str, float]]:
        if not isinstance(values, list):
            return []
        candles: list[dict[str, float]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            try:
                candle = {
                    key: float(item[key])
                    for key in ("open", "high", "low", "close")
                }
            except (KeyError, TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in candle.values()):
                continue
            if candle["low"] > candle["high"] or not all(
                candle["low"] <= candle[key] <= candle["high"]
                for key in ("open", "close")
            ):
                continue
            candles.append(candle)
        return candles

    async def get_candles(
        self, symbol: str, timeframe_seconds: int, limit: int = 100
    ) -> list[dict[str, float]]:
        interval = self.SUPPORTED_INTERVALS.get(timeframe_seconds)
        if interval is None:
            raise ValueError(
                f"Unsupported timeframe: {timeframe_seconds} seconds. "
                "Twelve Data supports 1 minute and 5 minute candles here."
            )
        try:
            outputsize = max(1, min(int(limit), 5000))
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be a positive integer.") from exc
        payload = await self._request(
            "time_series",
            {
                "symbol": self._symbol(symbol),
                "interval": interval,
                "outputsize": outputsize,
                "order": "asc",
            },
        )
        candles = self._parse_candles(payload.get("values"))
        if not candles:
            raise RuntimeError("Twelve Data returned no valid candle values.")
        return candles

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        normalized = self._symbol(symbol)
        payload = await self._request("quote", {"symbol": normalized})
        try:
            price = float(payload["close"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Twelve Data returned no valid quote price.") from exc
        if not math.isfinite(price):
            raise RuntimeError("Twelve Data returned an invalid quote price.")
        return {
            "symbol": normalized,
            "price": price,
            "timestamp": payload.get("timestamp"),
        }

    async def health_check(self) -> dict[str, Any]:
        return {
            "provider": "Twelve Data",
            "configured": bool(self.api_key),
            "supported_timeframes": sorted(self.SUPPORTED_INTERVALS),
        }
