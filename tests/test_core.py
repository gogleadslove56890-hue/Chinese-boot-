import asyncio
from datetime import timedelta
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from analysis.signal_engine import analyze
from backend.app import app, health
import backend.app as app_module
from backend.market.twelvedata import TwelveDataProvider
from backend.market.fallback import FallbackMarketDataProvider
from backend.market.olymptrade import OlympTradeProvider
from backend.risk_manager import RiskManager, RiskPolicy
from backend.scanner import Scanner


class TwelveDataTests(unittest.TestCase):
    def test_normalizes_currency_symbols(self):
        self.assertEqual(TwelveDataProvider._symbol(" eur-usd "), "EUR/USD")

    def test_quote_uses_bid_ask_midpoint_when_available(self):
        provider = TwelveDataProvider(api_key="test")

        async def fake_request(endpoint, params):
            return {
                "close": "1.1677",
                "bid": "1.1676",
                "ask": "1.1678",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        provider._request = fake_request
        result = asyncio.run(provider.get_quote("EUR/USD"))
        self.assertEqual(result["price"], 1.1677)
        self.assertEqual(result["price_basis"], "bid_ask_midpoint")

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

    def test_malformed_quote_is_rejected(self):
        provider = TwelveDataProvider(api_key="test")

        async def fake_request(endpoint, params):
            return {"close": "not-a-price", "timestamp": datetime.now(timezone.utc).isoformat()}

        provider._request = fake_request
        with self.assertRaisesRegex(RuntimeError, "valid quote price"):
            asyncio.run(provider.get_quote("EUR/USD"))

    def test_stale_quote_is_rejected(self):
        provider = TwelveDataProvider(api_key="test", max_stale_seconds=1)

        async def fake_request(endpoint, params):
            return {"close": "1.1", "timestamp": "2020-01-01T00:00:00+00:00"}

        provider._request = fake_request
        with self.assertRaisesRegex(RuntimeError, "quote is stale"):
            asyncio.run(provider.get_quote("EUR/USD"))

    def test_candle_timestamps_are_normalized_to_utc(self):
        parsed = TwelveDataProvider._parse_candles([
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "datetime": "2026-08-20 18:00:00"},
        ])
        self.assertEqual(parsed[0]["timestamp"], "2026-08-20T18:00:00Z")


class FallbackProviderTests(unittest.TestCase):
    class Provider:
        def __init__(self, candles=None, error=None, name="provider"):
            self.candles = candles or []
            self.error = error
            self.name = name

        async def get_candles(self, symbol, timeframe_seconds, limit):
            if self.error:
                raise RuntimeError(self.error)
            return self.candles

        async def get_quote(self, symbol):
            raise RuntimeError("quote unavailable")

        async def health_check(self):
            return {"provider": self.name, "live_data_verified": True}

    def test_falls_back_after_provider_failure(self):
        now = datetime.now(timezone.utc)
        candles = [{"timestamp": (now - timedelta(seconds=90)).isoformat(), "open": 1, "high": 2, "low": 0.5, "close": 1.5}]
        provider = FallbackMarketDataProvider([self.Provider(error="HTTP 429"), self.Provider(candles, name="secondary")])
        result = asyncio.run(provider.get_candles("EUR/USD", 60, 1))
        self.assertEqual(result[0]["close"], 1.5)
        self.assertEqual(provider.last_selection["provider"], "secondary")

    def test_rejects_future_and_malformed_candles(self):
        now = datetime.now(timezone.utc)
        candles = [
            {"timestamp": (now + timedelta(seconds=5)).isoformat(), "open": 1, "high": 2, "low": 0.5, "close": 1.5},
            {"timestamp": (now - timedelta(seconds=90)).isoformat(), "open": 2, "high": 1, "low": 3, "close": 2},
        ]
        provider = FallbackMarketDataProvider([self.Provider(candles)])
        with self.assertRaisesRegex(RuntimeError, "All market-data providers failed"):
            asyncio.run(provider.get_candles("EUR/USD", 60, 2))


class SignalAndHealthTests(unittest.TestCase):
    def test_scanner_route_is_read_only_without_authentication(self):
        class StubScanner:
            async def scan(self, symbol, timeframe, limit):
                return {
                    "status": "ready",
                    "source_status": "verified",
                    "signal": "WAIT",
                    "confidence": 0,
                    "symbol": symbol,
                    "timeframe_seconds": timeframe,
                    "price": 1.1,
                    "provider": "test-provider",
                    "candle_timestamp": "2026-08-21T03:20:00Z",
                }

        with patch.object(app_module, "scanner", StubScanner()), TestClient(app) as client:
            response = client.post("/api/scanner/scan", json={"symbol": "EUR/USD", "timeframe_seconds": 60})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source_status"], "verified")

    def test_scanner_response_contains_android_display_fields(self):
        class StubScanner:
            async def scan(self, symbol, timeframe, limit):
                return {
                    "status": "ready", "source_status": "verified", "signal": "UP", "confidence": 82,
                    "symbol": symbol, "timeframe_seconds": timeframe, "price": 1.17,
                    "provider": "Yahoo Finance", "candle_timestamp": "2026-08-21T03:20:00Z",
                    "latest_price": 1.17, "current_utc_timestamp": "2026-08-21T03:20:01Z",
                    "verified": True, "data_freshness": "fresh",
                    "analysis": {"reasons": ["test"]}, "trade_direction": "UP",
                    "validation_status": "verified closed market data",
                    "data_status": {"status": "fresh", "closed": True},
                }

        with patch.object(app_module, "scanner", StubScanner()), TestClient(app) as client:
            response = client.post("/api/scanner/scan", json={"symbol": "GBP/USD", "timeframe_seconds": 300})
        body = response.json()
        self.assertEqual(response.status_code, 200)
        for field in ("symbol", "timeframe_seconds", "price", "latest_price", "current_utc_timestamp", "provider", "verified", "signal", "confidence", "candle_timestamp", "data_freshness", "analysis", "trade_direction", "validation_status", "data_status"):
            self.assertIn(field, body)

    def test_unknown_scanner_route_is_404(self):
        with TestClient(app) as client:
            response = client.post("/api/scanner/scan/old")
        self.assertEqual(response.status_code, 404)

    def test_insufficient_data_waits_without_signal(self):
        result = analyze({"symbol": "EUR/USD", "candles": []})
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["confidence"], 0)

    def test_health_reports_provider_configuration(self):
        with patch.object(app_module, "provider_name", "olymptrade"), patch.object(
            app_module, "market_provider", OlympTradeProvider()
        ):
            result = asyncio.run(health())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["configured_provider"], "olymptrade")
        self.assertEqual(result["provider"]["source_status"], "unavailable")

    def test_olymptrade_reference_is_explicitly_unavailable(self):
        with TestClient(app) as client:
            response = client.get("/api/olymptrade-reference")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertEqual(
            response.json()["message"],
            "Olymp Trade live quote unavailable: no official public unauthenticated quote/candle feed is exposed.",
        )

    def test_stale_quote_is_rejected_without_fabrication(self):
        class Provider:
            async def get_quote(self, symbol):
                raise RuntimeError("Twelve Data quote is stale.")

            async def get_candles(self, symbol, timeframe_seconds, limit):
                return [{"close": 1.1676, "timestamp": "2026-08-20 18:00:00"}]

            @staticmethod
            def _symbol(symbol):
                return "EUR/USD"

        with patch.object(app_module, "market_provider", Provider()):
            with self.assertRaisesRegex(Exception, "Twelve Data quote is stale"):
                asyncio.run(app_module.quote("EUR/USD"))

    def test_candle_aliases_validate_and_map_timeframe(self):
        with patch.object(app_module, "provider_name", "olymptrade"), patch.object(
            app_module, "market_provider", OlympTradeProvider()
        ), TestClient(app) as client:
            response = client.get("/api/candles?symbol=EUR/USD&timeframe=1min&seconds=60&limit=1")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Olymp Trade live quote unavailable", response.json()["detail"])

    def test_candle_alias_mismatch_is_rejected(self):
        with TestClient(app) as client:
            response = client.get(
                "/api/candles?symbol=EUR/USD&timeframe=1min&seconds=300&limit=1"
            )
        self.assertEqual(response.status_code, 400)

    def test_analysis_rejects_source_mismatch(self):
        with patch.object(app_module, "provider_name", "twelvedata"):
            with self.assertRaisesRegex(Exception, "source mismatch"):
                app_module.analyze_market({"provider": "Olymp Trade", "source_status": "unavailable"})


class OlympTradeTests(unittest.TestCase):
    def test_maps_normal_and_otc_symbols_without_mixing_them(self):
        self.assertEqual(OlympTradeProvider._symbol("EUR/USD"), "EURUSD")
        self.assertEqual(OlympTradeProvider._symbol("EUR/USD_OTC"), "EURUSD_OTC")
        self.assertNotEqual(
            OlympTradeProvider._symbol("EUR/USD"),
            OlympTradeProvider._symbol("EUR/USD_OTC"),
        )

    def test_rejects_unknown_symbol(self):
        with self.assertRaises(ValueError):
            OlympTradeProvider._symbol("EUR/CHF")

    def test_public_quote_is_explicitly_unavailable(self):
        with self.assertRaisesRegex(RuntimeError, "Olymp Trade live quote unavailable"):
            asyncio.run(OlympTradeProvider().get_quote("GBP/JPY"))


class ScannerSafetyTests(unittest.TestCase):
    @staticmethod
    def candles(closes):
        timestamp = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
        return [{"open": close, "high": close + 0.001, "low": close - 0.001, "close": close, "timestamp": timestamp} for close in closes]

    class VerifiedProvider:
        def __init__(self, candles):
            self.candles = candles

        async def get_candles(self, symbol, timeframe_seconds, limit):
            return self.candles

        async def health_check(self):
            return {"provider": "Test feed", "live_data_verified": True}

    def test_verified_analysis_exposes_full_outlook(self):
        values = [1.0 + index * 0.001 for index in range(40)]
        result = asyncio.run(Scanner(self.VerifiedProvider(self.candles(values))).scan("EUR/USD", 60))
        self.assertEqual(result["status"], "ready")
        self.assertIn(result["signal"], {"UP", "WAIT"})
        self.assertIn("current_candle", result)
        self.assertIn("next_candle_outlook", result)
        self.assertIn(result["trade_decision"], {"TRADE: UP", "NO TRADE"})

    def test_verified_bearish_analysis_produces_down_or_wait(self):
        values = [1.2 - index * 0.001 for index in range(40)]
        result = asyncio.run(Scanner(self.VerifiedProvider(self.candles(values))).scan("EUR/USD", 60))
        self.assertIn(result["signal"], {"DOWN", "WAIT"})

    def test_mixed_verified_analysis_waits(self):
        values = [1.0 for _ in range(40)]
        result = asyncio.run(Scanner(self.VerifiedProvider(self.candles(values))).scan("EUR/USD", 60))
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["trade_decision"], "NO TRADE")

    def test_stale_verified_data_is_wait(self):
        candles = self.candles([1.0 + index * 0.001 for index in range(40)])
        for candle in candles:
            candle["timestamp"] = "2020-01-01T00:00:00+00:00"
        result = asyncio.run(Scanner(self.VerifiedProvider(candles)).scan("EUR/USD", 60))
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["trade_decision"], "NO TRADE")
        self.assertIn("stale", result["reason"])

    def test_future_verified_data_is_wait(self):
        candles = self.candles([1.0 + index * 0.001 for index in range(40)])
        for candle in candles:
            candle["timestamp"] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        result = asyncio.run(Scanner(self.VerifiedProvider(candles)).scan("EUR/USD", 60))
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["confidence"], 0)
        self.assertIn("future", result["reason"])

    def test_scan_stays_unavailable_without_verified_source(self):
        result = asyncio.run(Scanner(OlympTradeProvider()).scan("EUR/USD", 60))
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["source_status"], "unavailable")
        self.assertIsNone(result["price"])

    def test_future_tail_retries_and_selects_latest_closed_candle(self):
        valid = self.candles([1.0 + index * 0.001 for index in range(40)])
        valid = [{**candle, "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=330)).isoformat()} for candle in valid]
        future = {**valid[-1], "timestamp": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}

        class RetryingProvider(self.VerifiedProvider):
            def __init__(self):
                super().__init__([future])
                self.calls = 0

            async def get_candles(self, symbol, timeframe_seconds, limit):
                self.calls += 1
                return self.candles if self.calls == 1 else valid

        provider = RetryingProvider()
        result = asyncio.run(Scanner(provider).scan("GBP/USD", 300))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["data_status"]["status"], "fresh")
        self.assertTrue(result["data_status"]["closed"])
        self.assertGreaterEqual(provider.calls, 1)

    def test_required_pairs_and_timeframes_use_verified_closed_data(self):
        values = [1.0 + index * 0.001 for index in range(40)]
        for symbol in ("EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"):
            for timeframe in (60, 300):
                age = 150 if timeframe == 60 else 330
                candles = [{**candle, "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()} for candle in self.candles(values)]
                result = asyncio.run(Scanner(self.VerifiedProvider(candles)).scan(symbol, timeframe))
                self.assertEqual(result["status"], "ready", (symbol, timeframe))
                self.assertEqual(result["data_status"]["status"], "fresh")
                self.assertTrue(result["data_status"]["closed"])

    def test_auto_mode_is_disabled_without_execution_provider(self):
        result = Scanner(OlympTradeProvider()).start("AUTO")
        self.assertFalse(result["enabled"])
        self.assertIn("Authorized", result["reason"])

    def test_risk_manager_enforces_limits_and_emergency_stop(self):
        manager = RiskManager(RiskPolicy(minimum_confidence=80, maximum_trades=1))
        self.assertFalse(manager.check_trade(79, 1)[0])
        self.assertTrue(manager.check_trade(80, 1)[0])
        manager.record_trade()
        self.assertFalse(manager.check_trade(80, 1)[0])
        manager.emergency_stop()
        self.assertIn("Emergency", manager.check_trade(100, 1)[1])

    def test_scanner_endpoints_expose_manual_only_status(self):
        with TestClient(app) as client:
            status = client.get("/api/scanner/status")
            auto = client.post("/api/scanner/start", json={"mode": "AUTO"})
        self.assertFalse(status.json()["auto_enabled"])
        self.assertFalse(auto.json()["enabled"])


if __name__ == "__main__":
    unittest.main()
