import asyncio
import unittest

from fastapi.testclient import TestClient

from analysis.signal_engine import analyze
from backend.app import app, health
from backend.market.twelvedata import TwelveDataProvider


class TwelveDataTests(unittest.TestCase):
    def test_parses_only_valid_ohlc_records(self):
        payload = [
            {"open": "1", "high": "2", "low": "0.5", "close": "1.5"},
            {"open": "bad", "high": 2, "low": 1, "close": 1.5},
            {"open": 3, "high": 2, "low": 1, "close": 1.5},
        ]
        self.assertEqual(
            TwelveDataProvider._parse_candles(payload),
            [{"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}],
        )

    def test_missing_key_is_clear(self):
        with self.assertRaisesRegex(RuntimeError, "TWELVE_DATA_API_KEY"):
            asyncio.run(TwelveDataProvider(api_key="").get_quote("EUR/USD"))

    def test_unsupported_timeframe_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported timeframe"):
            asyncio.run(
                TwelveDataProvider(api_key="test").get_candles("EUR/USD", 5)
            )


class SignalAndHealthTests(unittest.TestCase):
    def test_insufficient_data_waits_without_signal(self):
        result = analyze({"symbol": "EUR/USD", "candles": []})
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["confidence"], 0)

    def test_health_reports_provider_configuration(self):
        result = asyncio.run(health())
        self.assertEqual(result["status"], "ok")
        self.assertIn("configured", result["provider"])

    def test_candle_aliases_validate_and_map_timeframe(self):
        with TestClient(app) as client:
            response = client.get(
                "/api/candles?symbol=EUR/USD&timeframe=1min&seconds=60&limit=1"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["timeframe_seconds"], 60)

    def test_candle_alias_mismatch_is_rejected(self):
        with TestClient(app) as client:
            response = client.get(
                "/api/candles?symbol=EUR/USD&timeframe=1min&seconds=300&limit=1"
            )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
