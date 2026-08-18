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
      
