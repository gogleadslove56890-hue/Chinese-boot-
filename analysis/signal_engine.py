from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        if number != number:  # NaN
            return None
        return number
    except (TypeError, ValueError):
        return None


def _extract_candles(payload: dict) -> list[dict]:
    candles = payload.get("candles")

    if candles is None and isinstance(payload.get("data"), dict):
        candles = payload["data"].get("candles")

    if not isinstance(candles, list):
        return []

    result = []

    for item in candles:
        if not isinstance(item, dict):
            continue

        open_price = _number(
            item.get("open", item.get("o"))
        )
        high_price = _number(
            item.get("high", item.get("h"))
        )
        low_price = _number(
            item.get("low", item.get("l"))
        )
        close_price = _number(
            item.get("close", item.get("c"))
        )

        if None in (open_price, high_price, low_price, close_price):
            continue

        values = (open_price, high_price, low_price, close_price)
        if not all(math.isfinite(value) for value in values):
            continue

        if low_price > high_price or not all(
            low_price <= value <= high_price
            for value in (open_price, close_price)
        ):
            continue

        if high_price < low_price:
            continue

        result.append(
            {
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
            }
        )

    return result


def _closes(candles: list[dict]) -> list[float]:
    return [float(c["close"]) for c in candles]


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None

    multiplier = 2.0 / (period + 1.0)
    ema_value = sum(values[:period]) / period

    for price in values[period:]:
        ema_value = (
            (price - ema_value) * multiplier
            + ema_value
        )

    return ema_value


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    relative_strength = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _macd(values: list[float]) -> dict[str, float | None]:
    if len(values) < 35:
        return {
            "macd": None,
            "signal": None,
            "histogram": None,
        }

    ema12_series = []
    ema26_series = []

    # Build EMA series so MACD can be calculated without
    # external dependencies.
    for end in range(26, len(values) + 1):
        segment = values[:end]
        ema12 = _ema(segment, 12)
        ema26 = _ema(segment, 26)

        if ema12 is not None and ema26 is not None:
            ema12_series.append(ema12)
            ema26_series.append(ema26)

    if len(ema12_series) < 9:
        return {
            "macd": None,
            "signal": None,
            "histogram": None,
        }

    macd_series = [
        a - b
        for a, b in zip(ema12_series, ema26_series)
    ]

    macd_value = macd_series[-1]
    signal_value = _ema(macd_series, 9)

    if signal_value is None:
        return {
            "macd": macd_value,
            "signal": None,
            "histogram": None,
        }

    return {
        "macd": macd_value,
        "signal": signal_value,
        "histogram": macd_value - signal_value,
    }


def _support_resistance(
    candles: list[dict],
    lookback: int = 20,
) -> dict[str, float | None]:
    recent = candles[-lookback:]

    if not recent:
        return {
            "support": None,
            "resistance": None,
        }

    support = min(c["low"] for c in recent)
    resistance = max(c["high"] for c in recent)

    return {
        "support": support,
        "resistance": resistance,
    }


def _atr(candles: list[dict], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    true_ranges = []
    for previous, current in zip(candles[-period - 1:-1], candles[-period:]):
        true_ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
    return sum(true_ranges) / period


def _candle_strength(candle: dict) -> dict[str, Any]:
    open_price = candle["open"]
    high = candle["high"]
    low = candle["low"]
    close = candle["close"]

    candle_range = high - low
    body = abs(close - open_price)

    if candle_range <= 0:
        return {
            "direction": "NEUTRAL",
            "strength": 0.0,
            "body_ratio": 0.0,
        }

    body_ratio = body / candle_range

    if close > open_price:
        direction = "BULLISH"
    elif close < open_price:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    strength = round(body_ratio * 100.0, 2)

    return {
        "direction": direction,
        "strength": strength,
        "body_ratio": round(body_ratio, 4),
    }


def _trend(closes: list[float], ema9: float | None, ema21: float | None) -> str:
    if ema9 is None or ema21 is None:
        return "UNKNOWN"
    if ema9 > ema21 and closes[-1] > ema21:
        return "BULLISH"
    if ema9 < ema21 and closes[-1] < ema21:
        return "BEARISH"
    return "MIXED"


def _timestamp_status(timestamp: Any, timeframe: int | None) -> dict[str, Any]:
    if timestamp in (None, ""):
        return {"timestamp": None, "fresh": False, "status": "missing"}
    try:
        value = str(timestamp).replace("Z", "+00:00")
        observed = datetime.fromisoformat(value)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return {"timestamp": str(timestamp), "fresh": False, "status": "invalid"}
    max_age = max(120, (timeframe or 60) * 3)
    fresh = -60 <= age <= max_age
    return {"timestamp": str(timestamp), "fresh": fresh, "age_seconds": round(age, 1), "status": "fresh" if fresh else "stale"}


def analyze(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "Payload must be a JSON object.",
        }

    candles = _extract_candles(payload)

    timeframe = payload.get("timeframe")
    if len(candles) < 35:
        return {
            "ok": True,
            "signal": "WAIT",
            "confidence": 0,
            "explanation": "Insufficient verified market data for analysis.",
            "required_candles": 35,
            "received_candles": len(candles),
            "next_candle_outlook": {"direction": "WAIT", "confidence": 0, "signal_strength": "WEAK", "reasons": ["Insufficient verified market data."]},
            "trade_decision": "NO TRADE",
        }

    closes = _closes(candles)
    last = candles[-1]

    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    ema50 = _ema(closes, 50)

    rsi = _rsi(closes, 14)
    macd = _macd(closes)
    levels = _support_resistance(candles)
    candle = _candle_strength(last)
    trend = _trend(closes, ema9, ema21)
    higher_candles = _extract_candles({"candles": payload.get("higher_timeframe", [])})
    higher_closes = _closes(higher_candles)
    higher_ema9 = _ema(higher_closes, 9)
    higher_ema21 = _ema(higher_closes, 21)
    higher_trend = _trend(higher_closes, higher_ema9, higher_ema21) if higher_closes else "UNKNOWN"
    data_status = _timestamp_status(last.get("timestamp"), int(timeframe) if timeframe else None)

    score = 0
    reasons = []

    # Transparent model weights: trend/EMA 4, momentum/RSI 3, MACD 2,
    # candle structure 1, volatility 1, and higher-timeframe confirmation 3.

    # EMA trend
    if ema9 is not None and ema21 is not None:
        if ema9 > ema21:
            score += 2
            reasons.append("EMA 9 is above EMA 21.")
        elif ema9 < ema21:
            score -= 2
            reasons.append("EMA 9 is below EMA 21.")

    if ema21 is not None and ema50 is not None:
        if ema21 > ema50:
            score += 2
            reasons.append("EMA 21 is above EMA 50.")
        elif ema21 < ema50:
            score -= 2
            reasons.append("EMA 21 is below EMA 50.")

    # Price relative to EMA
    if ema21 is not None:
        if last["close"] > ema21:
            score += 1
            reasons.append("Price is above EMA 21.")
        elif last["close"] < ema21:
            score -= 1
            reasons.append("Price is below EMA 21.")

    # RSI
    if rsi is not None:
        if rsi >= 70:
            score -= 1
            reasons.append("RSI is overbought.")
        elif rsi <= 30:
            score += 1
            reasons.append("RSI is oversold.")
        elif rsi >= 55:
            score += 1
            reasons.append("RSI has bullish momentum.")
        elif rsi <= 45:
            score -= 1
            reasons.append("RSI has bearish momentum.")

    # MACD
    macd_value = macd.get("macd")
    signal_value = macd.get("signal")

    if macd_value is not None and signal_value is not None:
        if macd_value > signal_value:
            score += 2
            reasons.append("MACD is above its signal line.")
        elif macd_value < signal_value:
            score -= 2
            reasons.append("MACD is below its signal line.")

    # Last candle
    if candle["direction"] == "BULLISH":
        if candle["strength"] >= 60:
            score += 1
            reasons.append("Last candle has strong bullish body.")
    elif candle["direction"] == "BEARISH":
        if candle["strength"] >= 60:
            score -= 1
            reasons.append("Last candle has strong bearish body.")

    atr = _atr(candles)
    average_range = sum(item["high"] - item["low"] for item in candles[-20:]) / 20
    if atr is not None and average_range > 0 and atr <= average_range * 2:
        reasons.append("ATR volatility is within the acceptable range.")
    elif atr is not None:
        reasons.append("ATR volatility is elevated.")

    if higher_trend == "BULLISH":
        score += 3
        reasons.append("Higher timeframe trend is bullish.")
    elif higher_trend == "BEARISH":
        score -= 3
        reasons.append("Higher timeframe trend is bearish.")

    # Final signal
    if score >= 3:
        signal = "UP"
    elif score <= -3:
        signal = "DOWN"
    else:
        signal = "WAIT"

    # Confidence is deliberately capped.
    # It is a model score, NOT a probability of profit.
    confidence = min(95, 50 + abs(score) * 7)
    if signal == "WAIT":
        confidence = 0
    if signal == "UP" and higher_trend == "BEARISH" or signal == "DOWN" and higher_trend == "BULLISH":
        signal = "WAIT"
        confidence = 0
        reasons.append("Lower and higher timeframe trends conflict.")
    signal_strength = "STRONG" if confidence >= 78 else "MODERATE" if confidence >= 64 else "WEAK"

    if signal == "UP":
        explanation = (
            "Bullish conditions are stronger than bearish "
            "conditions based on the supplied candles."
        )
    elif signal == "DOWN":
        explanation = (
            "Bearish conditions are stronger than bullish "
            "conditions based on the supplied candles."
        )
    else:
        explanation = "Trend and momentum disagree or lack sufficient confirmation."

    reasons_against = {
        "UP": ["Bearish confirmations did not outweigh the bullish technical evidence."],
        "DOWN": ["Bullish confirmations did not outweigh the bearish technical evidence."],
        "WAIT": ["Technical confirmations are mixed or below the signal threshold."],
    }[signal]

    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe")

    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": signal,
        "confidence": confidence,
        "score": score,
        "price": last["close"],
        "indicators": {
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "rsi14": rsi,
            "macd": macd,
            "atr14": atr,
        },
        "levels": levels,
        "last_candle": candle,
        "current_candle": last,
        "previous_candles": candles[-5:-1],
        "trend": trend,
        "higher_timeframe_trend": higher_trend,
        "higher_timeframe_seconds": payload.get("higher_timeframe_seconds"),
        "momentum": {"rsi14": rsi, "macd": macd, "direction": "BULLISH" if score > 0 else "BEARISH" if score < 0 else "MIXED"},
        "recent_high": max(item["high"] for item in candles[-20:]),
        "recent_low": min(item["low"] for item in candles[-20:]),
        "volatility": {"average_range": average_range, "atr14": atr, "lookback": 20},
        "data_status": data_status,
        "next_candle_outlook": {"direction": signal, "confidence": confidence, "signal_strength": signal_strength, "reasons": reasons},
        "trade_decision": f"TRADE: {signal}" if signal in {"UP", "DOWN"} and confidence >= 64 else "NO TRADE",
        "reasons": reasons,
        "reasons_against": reasons_against,
        "explanation": explanation,
        "data_source": payload.get(
            "data_source",
            "provided_market_data",
        ),
        "warning": (
            "Signal is technical analysis, not a guarantee "
            "of the next candle or trading profit."
        ),
}
  
