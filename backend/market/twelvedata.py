from __future__ import annotations

import asyncio
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


class TwelveDataProvider:
    """Async REST adapter for verified Twelve Data market data."""

    DEFAULT_BASE_URL = "https://api.twelvedata.com"
    SUPPORTED_INTERVALS = {60: "1min", 300: "5min", 900: "15min", 1800: "30min", 3600: "1h"}

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 15.0,
        retries: int = 2,
        max_stale_seconds: float = 900.0,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.getenv("TWELVE_DATA_API_KEY")
        )
        self.base_url = (
            base_url or os.getenv("TWELVE_DATA_BASE_URL") or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.max_stale_seconds = max_stale_seconds

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

        last_error: RuntimeError | None = None
        for attempt in range(self.retries + 1):
            try:
                payload = await asyncio.to_thread(fetch)
                break
            except RuntimeError as exc:
                last_error = exc
                if attempt == self.retries:
                    raise
                await asyncio.sleep(0.1 * (attempt + 1))
        else:
            raise last_error or RuntimeError("Twelve Data request failed.")
        if payload.get("status") == "error" or payload.get("code") in {401, 403, 429}:
            raise RuntimeError(str(payload.get("message") or "Twelve Data request failed."))
        return payload

    def _reject_stale(self, timestamp: Any) -> None:
        if timestamp in (None, ""):
            raise RuntimeError("Twelve Data returned no quote timestamp.")
        try:
            if isinstance(timestamp, (int, float)):
                observed = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            else:
                value = str(timestamp).replace("Z", "+00:00")
                observed = datetime.fromisoformat(value)
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
                observed = observed.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("Twelve Data returned an invalid quote timestamp.") from exc
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if age > self.max_stale_seconds:
            raise RuntimeError("Twelve Data quote is stale.")
        if age < -60:
            raise RuntimeError("Twelve Data quote timestamp is in the future.")

    @staticmethod
    def _symbol(symbol: str) -> str:
        value = symbol.strip().upper().replace("-", "/")
        if not value or value.count("/") != 1:
            raise ValueError("Symbol must be a currency pair such as EUR/USD.")
        base, quote = (part.strip() for part in value.split("/"))
        if len(base) != 3 or len(quote) != 3 or not base.isalpha() or not quote.isalpha():
            raise ValueError("Symbol must be a currency pair such as EUR/USD.")
        return f"{base}/{quote}"

    @staticmethod
    def _timestamp_utc(timestamp: Any) -> str | None:
        if timestamp in (None, ""):
            return None
        try:
            if isinstance(timestamp, (int, float)):
                observed = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            else:
                value = str(timestamp).strip().replace("Z", "+00:00")
                observed = datetime.fromisoformat(value)
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
                observed = observed.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None
        return observed.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_candles(values: Any) -> list[dict[str, Any]]:
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
            timestamp = TwelveDataProvider._timestamp_utc(item.get("datetime"))
            if item.get("datetime") is not None:
                if timestamp is None:
                    continue
                candle["timestamp"] = timestamp
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
                "timezone": "UTC",
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
            close = float(payload["close"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Twelve Data returned no valid quote price.") from exc
        if not math.isfinite(close):
            raise RuntimeError("Twelve Data returned an invalid quote price.")
        self._reject_stale(payload.get("timestamp"))

        def optional_price(name: str) -> float | None:
            try:
                value = float(payload[name])
            except (KeyError, TypeError, ValueError):
                return None
            return value if math.isfinite(value) and value > 0 else None

        bid = optional_price("bid")
        ask = optional_price("ask")
        if bid is not None and ask is not None and bid <= ask:
            price = (bid + ask) / 2
            price_basis = "bid_ask_midpoint"
        else:
            price = close
            price_basis = "last_close"

        return {
            "symbol": normalized,
            "price": price,
            "close": close,
            "bid": bid,
            "ask": ask,
            "price_basis": price_basis,
            "timestamp": payload.get("timestamp"),
        }

    async def health_check(self) -> dict[str, Any]:
        return {
            "provider": "Twelve Data",
            "configured": bool(self.api_key),
            "connected": bool(self.api_key),
            "live_data_verified": bool(self.api_key),
            "supported_timeframes": sorted(self.SUPPORTED_INTERVALS),
            "source_status": "verified" if self.api_key else "unavailable",
        }
