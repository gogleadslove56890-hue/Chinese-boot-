SUPPORTED_TIMEFRAMES = [
    60,
    300,
    900,
    1800,
    3600,
]

class Scanner:
    def __init__(self, market_provider, audit_log):
        self.market_provider = market_provider
        self.audit_log = audit_log
        self.mode = "manual"
        self.running = False

    @property
    def execution(self):
        return self

    @property
    def available(self):
        return True

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    async def scan(self, symbol, timeframe_seconds, limit):
        candles = await self.market_provider.get_candles(
            symbol,
            timeframe_seconds,
            limit
        )

        if not candles:
            return {
                "signal": "WAIT",
                "confidence": 0,
                "reason": "No candles available",
                "candles": []
            }

        closes = [c["close"] for c in candles]

        last = closes[-1]
        previous = closes[-2] if len(closes) > 1 else last

        if last > previous:
            signal = "UP"
            confidence = 60
        elif last < previous:
            signal = "DOWN"
            confidence = 60
        else:
            signal = "WAIT"
            confidence = 0

        return {
            "symbol": symbol,
            "timeframe_seconds": timeframe_seconds,
            "signal": signal,
            "confidence": confidence,
            "candles": candles,
            "reason": "Basic candle movement analysis"
        }
