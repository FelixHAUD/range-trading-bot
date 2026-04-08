"""
Unit tests for feeds/normalizer.py, feeds/binance.py, feeds/coinbase.py.
No network required — all inputs are synthetic raw payloads.
"""
import pytest
from feeds.binance import BinanceNormalizer
from feeds.coinbase import CoinbaseNormalizer
from feeds.normalizer import NormalizedCandle


# ── BinanceNormalizer ─────────────────────────────────────────────────────────

class TestBinanceNormalizer:
    def setup_method(self):
        self.normalizer = BinanceNormalizer()

    def _kline_msg(self, symbol="SOLUSDT", is_closed=True):
        return {
            "e": "kline",
            "s": symbol,
            "k": {
                "t": 1700000000000,
                "o": "80.00",
                "h": "82.50",
                "l": "79.50",
                "c": "81.00",
                "v": "1500.25",
                "i": "15m",
                "x": is_closed,
            },
        }

    def test_parse_closed_kline(self):
        candle = self.normalizer.parse_message(self._kline_msg())
        assert isinstance(candle, NormalizedCandle)
        assert candle.exchange == "binance"
        assert candle.symbol == "SOL/USDT"
        assert candle.timestamp == 1700000000000
        assert candle.open == 80.0
        assert candle.high == 82.5
        assert candle.low == 79.5
        assert candle.close == 81.0
        assert candle.volume == 1500.25
        assert candle.interval == "15m"
        assert candle.is_closed is True

    def test_parse_open_kline_is_closed_false(self):
        candle = self.normalizer.parse_message(self._kline_msg(is_closed=False))
        assert candle is not None
        assert candle.is_closed is False

    def test_parse_non_kline_event_returns_none(self):
        assert self.normalizer.parse_message({"e": "trade", "s": "SOLUSDT"}) is None

    def test_parse_missing_event_key_returns_none(self):
        assert self.normalizer.parse_message({"s": "SOLUSDT"}) is None

    def test_symbol_normalisation_usdt(self):
        candle = self.normalizer.parse_message(self._kline_msg("SOLUSDT"))
        assert candle.symbol == "SOL/USDT"

    def test_symbol_normalisation_btc(self):
        candle = self.normalizer.parse_message(self._kline_msg("SOLBTC"))
        assert candle.symbol == "SOL/BTC"

    def test_symbol_normalisation_eth(self):
        candle = self.normalizer.parse_message(self._kline_msg("SOLETH"))
        assert candle.symbol == "SOL/ETH"

    def test_symbol_normalisation_unknown_kept_as_is(self):
        candle = self.normalizer.parse_message(self._kline_msg("SOLXYZ"))
        assert candle.symbol == "SOLXYZ"

    def test_ws_url(self):
        assert self.normalizer.ws_url() == "wss://stream.binance.com:9443/ws"

    def test_subscribe_msg(self):
        msg = self.normalizer.build_subscribe_msg("SOL/USDT", "15m")
        assert msg["method"] == "SUBSCRIBE"
        assert "solusdt@kline_15m" in msg["params"]
        assert msg["id"] == 1


# ── CoinbaseNormalizer ────────────────────────────────────────────────────────

class TestCoinbaseNormalizer:
    def setup_method(self):
        self.normalizer = CoinbaseNormalizer(interval="15m")

    def _candles_msg(self, product_id="SOL-USDT"):
        return {
            "channel": "candles",
            "events": [
                {
                    "candles": [
                        {
                            "product_id": product_id,
                            "start": "1700000000",
                            "open": "80.00",
                            "high": "82.50",
                            "low": "79.50",
                            "close": "81.00",
                            "volume": "1500.25",
                        }
                    ]
                }
            ],
        }

    def test_parse_candles_message(self):
        candle = self.normalizer.parse_message(self._candles_msg())
        assert isinstance(candle, NormalizedCandle)
        assert candle.exchange == "coinbase"
        assert candle.symbol == "SOL/USDT"
        assert candle.timestamp == 1700000000 * 1000
        assert candle.open == 80.0
        assert candle.high == 82.5
        assert candle.low == 79.5
        assert candle.close == 81.0
        assert candle.volume == 1500.25
        assert candle.interval == "15m"
        assert candle.is_closed is True

    def test_coinbase_candles_always_closed(self):
        candle = self.normalizer.parse_message(self._candles_msg())
        assert candle.is_closed is True

    def test_symbol_dash_to_slash(self):
        candle = self.normalizer.parse_message(self._candles_msg("BTC-USDT"))
        assert candle.symbol == "BTC/USDT"

    def test_wrong_channel_returns_none(self):
        assert self.normalizer.parse_message({"channel": "ticker"}) is None

    def test_no_channel_returns_none(self):
        assert self.normalizer.parse_message({}) is None

    def test_empty_events_returns_none(self):
        msg = {"channel": "candles", "events": []}
        assert self.normalizer.parse_message(msg) is None

    def test_empty_candles_list_returns_none(self):
        msg = {"channel": "candles", "events": [{"candles": []}]}
        assert self.normalizer.parse_message(msg) is None

    def test_interval_stored_from_constructor(self):
        normalizer = CoinbaseNormalizer(interval="1h")
        candle = normalizer.parse_message(self._candles_msg())
        assert candle.interval == "1h"

    def test_ws_url(self):
        assert self.normalizer.ws_url() == "wss://advanced-trade-ws.coinbase.com"

    def test_subscribe_msg(self):
        msg = self.normalizer.build_subscribe_msg("SOL/USDT", "15m")
        assert msg["type"] == "subscribe"
        assert "SOL-USDT" in msg["product_ids"]
        assert msg["channel"] == "candles"


# ── NormalizedCandle dataclass ────────────────────────────────────────────────

class TestNormalizedCandle:
    def test_fields_accessible(self):
        c = NormalizedCandle(
            exchange="binance",
            symbol="SOL/USDT",
            timestamp=1700000000000,
            open=80.0,
            high=82.5,
            low=79.5,
            close=81.0,
            volume=1500.0,
            interval="15m",
            is_closed=True,
        )
        assert c.exchange == "binance"
        assert c.is_closed is True

    def test_equality(self):
        kwargs = dict(
            exchange="binance", symbol="SOL/USDT", timestamp=1,
            open=1.0, high=2.0, low=0.5, close=1.5,
            volume=100.0, interval="15m", is_closed=True,
        )
        assert NormalizedCandle(**kwargs) == NormalizedCandle(**kwargs)
