import asyncio
import json
import os
from typing import Any

import websockets


class TwelveDataProvider:
    """
    Real-time market-data adapter using Twelve Data WebSocket.

    API key must be supplied through the TWELVE_DATA_API_KEY
    environment variable. Never put the real API key in GitHub.
    """

    WS_URL = "wss://ws.twelvedata.com/v1/quotes/price"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY")
        self.websocket = None
        self.connected = False
        self.latest_prices: dict[str, dict[str, Any]] = {}

    async def connect(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "TWELVE_DATA_API_KEY is not configured."
            )

        url = f"{self.WS_URL}?apikey={self.api_key}"

        self.websocket = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=20,
        )

        self.connected = True

    async def subscribe(self, symbols: list[str]) -> None:
        if not self.websocket:
            raise RuntimeError("WebSocket is not connected.")

        payload = {
            "action": "subscribe",
            "params": {
                "symbols": ",".join(symbols)
            },
        }

        await self.websocket.send(json.dumps(payload))

    async def receive(self) -> dict[str, Any]:
        if not self.websocket:
            raise RuntimeError("WebSocket is not connected.")

        message = await self.websocket.recv()

        if isinstance(message, bytes):
            message = message.decode("utf-8")

        data = json.loads(message)

        if data.get("event") == "price":
            symbol = data.get("symbol")
            price = data.get("price")
            timestamp = data.get("timestamp")

            if symbol and price is not None:
                self.latest_prices[symbol] = {
                    "symbol": symbol,
                    "price": float(price),
                    "timestamp": timestamp,
                }

        return data
    

    async def stream(
        self,
        symbols: list[str],
    ):
        await self.connect()
        await self.subscribe(symbols)

        while self.connected:
            try:
                yield await self.receive()
            except websockets.ConnectionClosed:
                self.connected = False
                break
            except asyncio.CancelledError:
                self.connected = False
                raise

    async def close(self) -> None:
        self.connected = False

        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    def get_latest_price(
        self,
        symbol: str,
    ) -> dict[str, Any] | None:
        return self.latest_prices.get(symbol)

    async def health_check(self) -> dict[str, Any]:
        return {
            "provider": "Twelve Data",
            "connected": self.connected,
            "live_data": bool(self.connected),
            "symbols_cached": len(self.latest_prices),
        }
      
    async def get_candles(
        self,
        symbol: str,
        timeframe_seconds: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch real OHLC candles from Twelve Data.
        """

        if not self.api_key:
            raise RuntimeError(
                "TWELVE_DATA_API_KEY is not configured."
            )

        symbol = symbol.strip()

        if not symbol:
            raise ValueError("Symbol must not be empty.")

        interval_map = {
            60: "1min",
            300: "5min",
            900: "15min",
            1800: "30min",
            3600: "1h",
            7200: "2h",
            14400: "4h",
            28800: "8h",
            86400: "1day",
            604800: "1week",
            2592000: "1month",
        }

        interval = interval_map.get(timeframe_seconds)

        if interval is None:
            raise ValueError(
                f"Unsupported Twelve Data timeframe: "
                f"{timeframe_seconds} seconds."
            )

        limit = max(35, min(int(limit), 5000))

        import urllib.parse
        import urllib.request

        params = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "interval": interval,
                "outputsize": limit,
                "order": "asc",
                "apikey": self.api_key,
            }
        )

        url = (
            "https://api.twelvedata.com/time_series?"
            + params
        )

        def fetch() -> dict[str, Any]:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Chinese-boot/1.0",
                    "Accept": "application/json",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=20,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        data = await asyncio.to_thread(fetch)

        if data.get("status") == "error":
            raise RuntimeError(
                data.get(
                    "message",
                    "Twelve Data request failed.",
                )
            )

        values = data.get("values", [])

        if not isinstance(values, list):
            return []

        candles = []

        for item in values:
            try:
                candles.append(
                    {
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": float(item["close"]),
                    }
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

        return candles
            async def get_quote(self, symbol: str) -> dict[str, Any]:
        price = self.get_latest_price(symbol)

        if price is not None:
            return price

        return {
            "symbol": symbol,
            "price": None,
            "timestamp": None,
        }
        
