from typing import Any

from backend.market.provider import MarketDataProvider


class OlympTradeProvider(MarketDataProvider):
    """
    Olymp Trade market-data adapter.

    Olymp Trade does not publish an unauthenticated quote/candle API.

    This adapter deliberately fails closed until Olymp Trade publishes a
    legitimate public feed that can be verified without private endpoints,
    authentication bypass, or anti-bot circumvention.
    """

    NAME = "Olymp Trade"
    OFFICIAL_URL = "https://olymptrade.com/"
    SYMBOLS = {
        "EUR/USD": "EURUSD",
        "GBP/USD": "GBPUSD",
        "USD/JPY": "USDJPY",
        "AUD/USD": "AUDUSD",
        "USD/CAD": "USDCAD",
        "NZD/USD": "NZDUSD",
        "GBP/JPY": "GBPJPY",
    }
    OTC_SUFFIX = "_OTC"

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url
        self.connected = False

    @classmethod
    def _symbol(cls, symbol: str) -> str:
        value = symbol.strip().upper().replace("-", "/")
        otc = value.endswith(cls.OTC_SUFFIX)
        pair = value[:-len(cls.OTC_SUFFIX)] if otc else value
        if pair not in cls.SYMBOLS:
            raise ValueError("Unsupported Olymp Trade asset symbol.")
        return cls.SYMBOLS[pair] + (cls.OTC_SUFFIX if otc else "")

    @classmethod
    def _display_symbol(cls, symbol: str) -> str:
        normalized = cls._symbol(symbol)
        for display, mapped in cls.SYMBOLS.items():
            if normalized == mapped:
                return display
            if normalized == mapped + cls.OTC_SUFFIX:
                return display + cls.OTC_SUFFIX
        raise ValueError("Unsupported Olymp Trade asset symbol.")

    @staticmethod
    def _unavailable() -> RuntimeError:
        return RuntimeError(
            "Olymp Trade live quote unavailable: no official public "
            "unauthenticated quote/candle feed is exposed."
        )

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        normalized = self._symbol(symbol)
        raise self._unavailable()

    async def get_candles(
        self,
        symbol: str,
        timeframe_seconds: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._symbol(symbol)
        if timeframe_seconds not in {60, 300}:
            raise ValueError(
                f"Unsupported timeframe: {timeframe_seconds} seconds. "
                "Olymp Trade public timeframe data is unavailable."
            )
        raise self._unavailable()

    async def health_check(self) -> dict[str, Any]:
        return {
            "provider": self.NAME,
            "connected": self.connected,
            "live_data_verified": False,
            "source_status": "unavailable",
            "official_url": self.OFFICIAL_URL,
            "message": str(self._unavailable()),
        }

