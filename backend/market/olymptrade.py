from typing import Any

from backend.market.provider import MarketDataProvider


class OlympTradeProvider(MarketDataProvider):
    """
    Olymp Trade market-data adapter.

    Real transport/authentication must be connected to an
    officially supported or otherwise verified market-data
    source before live quotes are returned.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url
        self.connected = False

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError(
                "Verified real-time market-data connection is not configured."
            )

        raise NotImplementedError(
            "Connect a verified live market-data transport."
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe_seconds: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self.connected:
            raise RuntimeError(
                "Verified real-time market-data connection is not configured."
            )

        raise NotImplementedError(
            "Connect a verified live candle-data transport."
        )

    async def health_check(self) -> dict[str, Any]:
        return {
            "provider": "Olymp Trade",
            "connected": self.connected,
            "live_data_verified": False,
        }

