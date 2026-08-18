from abc import ABC, abstractmethod
from typing import Any


class MarketDataProvider(ABC):
    """Common interface for real-time market-data providers."""

    @abstractmethod
    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Return the latest verified quote for a symbol."""
        raise NotImplementedError

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe_seconds: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return OHLC candles for the requested timeframe."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return provider connection/status information."""
        raise NotImplementedError
