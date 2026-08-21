from typing import Any


class FallbackMarketDataProvider:
    """Try configured market-data providers in order."""

    def __init__(self, providers):
        self.providers = providers or []

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        last_error = None

        for provider in self.providers:
            try:
                return await provider.get_quote(symbol)
            except Exception as exc:
                last_error = exc

        if last_error:
            raise RuntimeError(
                f"No market-data provider available: {last_error}"
            )

        raise RuntimeError("No market-data providers configured")

    async def get_candles(
        self,
        symbol: str,
        timeframe_seconds: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        last_error = None

        for provider in self.providers:
            try:
                return await provider.get_candles(
                    symbol,
                    timeframe_seconds,
                    limit,
                )
            except Exception as exc:
                last_error = exc

        if last_error:
            raise RuntimeError(
                f"No market-data provider available: {last_error}"
            )

        raise RuntimeError("No market-data providers configured")

    async def health_check(self) -> dict[str, Any]:
        for provider in self.providers:
            try:
                result = await provider.health_check()
                if result:
                    return result
            except Exception:
                continue

        return {
            "ok": False,
            "provider": "fallback",
            "message": "No configured market-data provider is available",
        }
