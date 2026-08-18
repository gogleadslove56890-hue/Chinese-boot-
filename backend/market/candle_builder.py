from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Candle:
    symbol: str
    timeframe_seconds: int
    start_time: int
    open: float
    high: float
    low: float
    close: float
    tick_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe_seconds": self.timeframe_seconds,
            "start_time": self.start_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tick_count": self.tick_count,
        }


class CandleBuilder:
    """
    Converts live price ticks into OHLC candles.

    Supported timeframes:
    5s, 10s, 15s, 30s,
    1m, 2m, 3m, 5m
    """

    SUPPORTED_TIMEFRAMES = (
        5,
        10,
        15,
        30,
        60,
        120,
        180,
        300,
    )

    def __init__(self):
        self.current: dict[tuple[str, int], Candle] = {}

    def _bucket_start(
        self,
        timestamp: int,
        timeframe_seconds: int,
    ) -> int:
        return timestamp - (
            timestamp % timeframe_seconds
        )

    def update(
        self,
        symbol: str,
        price: float,
        timestamp: int,
        timeframe_seconds: int,
    ) -> dict[str, Any]:
        if timeframe_seconds not in self.SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe: {timeframe_seconds}"
            )

        if price <= 0:
            raise ValueError("Price must be greater than zero.")

        key = (symbol, timeframe_seconds)

        bucket = self._bucket_start(
            timestamp,
            timeframe_seconds,
        )

        candle = self.current.get(key)

        closed_candle = None

        if candle is None:
            candle = Candle(
                symbol=symbol,
                timeframe_seconds=timeframe_seconds,
                start_time=bucket,
                open=price,
                high=price,
                low=price,
                close=price,
                tick_count=1,
            )

            self.current[key] = candle

        elif candle.start_time != bucket:
            closed_candle = candle.to_dict()

            candle = Candle(
                symbol=symbol,
                timeframe_seconds=timeframe_seconds,
                start_time=bucket,
                open=price,
                high=price,
                low=price,
                close=price,
                tick_count=1,
            )

            self.current[key] = candle

        else:
            candle.high = max(candle.high, price)
            candle.low = min(candle.low, price)
            candle.close = price
            candle.tick_count += 1

        return {
            "closed_candle": closed_candle,
            "current_candle": candle.to_dict(),
        }

    def get_current(
        self,
        symbol: str,
        timeframe_seconds: int,
    ) -> dict[str, Any] | None:
        candle = self.current.get(
            (symbol, timeframe_seconds)
        )

        if candle is None:
            return None

        return candle.to_dict()

    def reset(
        self,
        symbol: str | None = None,
        timeframe_seconds: int | None = None,
    ) -> None:
        if symbol is None and timeframe_seconds is None:
            self.current.clear()
            return

        keys = list(self.current.keys())

        for key in keys:
            key_symbol, key_timeframe = key

            if symbol is not None and key_symbol != symbol:
                continue

            if (
                timeframe_seconds is not None
                and key_timeframe != timeframe_seconds
            ):
                continue

            del self.current[key]
          
