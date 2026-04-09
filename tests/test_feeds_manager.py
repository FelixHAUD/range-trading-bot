"""
Unit tests for feeds/manager.py.
Normalizers are mocked — no network calls.
"""
import asyncio
import pytest
from feeds.manager import PriceFeedManager
from feeds.normalizer import NormalizedCandle


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_candle(
    exchange: str = "binance",
    timestamp: int = 1_700_000_000_000,
    interval: str = "15m",
) -> NormalizedCandle:
    return NormalizedCandle(
        exchange=exchange, symbol="SOL/USDT",
        timestamp=timestamp, open=80.0, high=82.0,
        low=79.0, close=81.0, volume=1000.0,
        interval=interval, is_closed=True,
    )


def make_normalizer(candles: list):
    """Returns a mock normalizer whose stream_with_retry yields the given candles."""
    from unittest.mock import MagicMock

    normalizer = MagicMock()

    async def stream_with_retry(symbol, interval, callback):
        for candle in candles:
            await callback(candle)

    normalizer.stream_with_retry = stream_with_retry
    return normalizer


# ── Deduplication ─────────────────────────────────────────────────────────────

class TestDeduplication:
    def test_duplicate_candle_delivered_only_once(self):
        mgr = PriceFeedManager()
        candle = make_candle()
        received = []

        async def cb(c):
            received.append(c)

        mgr.subscribe(cb)
        mgr.add_exchange(make_normalizer([candle, candle]))
        run(mgr.start("SOL/USDT", "15m"))
        assert len(received) == 1

    def test_different_timestamps_both_delivered(self):
        mgr = PriceFeedManager()
        c1 = make_candle(timestamp=1_700_000_000_000)
        c2 = make_candle(timestamp=1_700_000_900_000)
        received = []

        async def cb(c):
            received.append(c)

        mgr.subscribe(cb)
        mgr.add_exchange(make_normalizer([c1, c2]))
        run(mgr.start("SOL/USDT", "15m"))
        assert len(received) == 2

    def test_same_timestamp_different_exchanges_both_delivered(self):
        mgr = PriceFeedManager()
        c_binance = make_candle(exchange="binance")
        c_coinbase = make_candle(exchange="coinbase")
        received = []

        async def cb(c):
            received.append(c)

        mgr.subscribe(cb)
        mgr.add_exchange(make_normalizer([c_binance]))
        mgr.add_exchange(make_normalizer([c_coinbase]))
        run(mgr.start("SOL/USDT", "15m"))
        assert len(received) == 2

    def test_same_timestamp_different_intervals_both_delivered(self):
        mgr = PriceFeedManager()
        c1 = make_candle(interval="15m")
        c2 = make_candle(interval="1h")
        received = []

        async def cb(c):
            received.append(c)

        mgr.subscribe(cb)
        mgr.add_exchange(make_normalizer([c1, c2]))
        run(mgr.start("SOL/USDT", "15m"))
        assert len(received) == 2

    def test_dedup_key_format_is_exchange_timestamp_interval(self):
        mgr = PriceFeedManager()
        candle = make_candle(exchange="binance", timestamp=1_700_000_000_000, interval="15m")

        async def cb(c):
            pass

        mgr.subscribe(cb)
        mgr.add_exchange(make_normalizer([candle]))
        run(mgr.start("SOL/USDT", "15m"))
        assert "binance:1700000000000:15m" in mgr._seen


# ── Fan-out to subscribers ────────────────────────────────────────────────────

class TestFanout:
    def test_single_subscriber_receives_candle(self):
        mgr = PriceFeedManager()
        candle = make_candle()
        received = []

        async def cb(c):
            received.append(c)

        mgr.subscribe(cb)
        mgr.add_exchange(make_normalizer([candle]))
        run(mgr.start("SOL/USDT", "15m"))
        assert received == [candle]

    def test_multiple_subscribers_all_receive_candle(self):
        mgr = PriceFeedManager()
        candle = make_candle()
        received_a: list = []
        received_b: list = []

        async def cb_a(c):
            received_a.append(c)

        async def cb_b(c):
            received_b.append(c)

        mgr.subscribe(cb_a)
        mgr.subscribe(cb_b)
        mgr.add_exchange(make_normalizer([candle]))
        run(mgr.start("SOL/USDT", "15m"))
        assert received_a == [candle]
        assert received_b == [candle]

    def test_no_crash_with_no_subscribers(self):
        mgr = PriceFeedManager()
        mgr.add_exchange(make_normalizer([make_candle()]))
        run(mgr.start("SOL/USDT", "15m"))   # must not raise

    def test_no_crash_with_no_exchanges(self):
        mgr = PriceFeedManager()
        received = []

        async def cb(c):
            received.append(c)

        mgr.subscribe(cb)
        run(mgr.start("SOL/USDT", "15m"))
        assert received == []


# ── Seen-set pruning ──────────────────────────────────────────────────────────

class TestSeenSetPruning:
    def test_seen_set_pruned_when_exceeds_ten_thousand(self):
        mgr = PriceFeedManager()
        candles = [make_candle(timestamp=i) for i in range(10_001)]
        mgr.add_exchange(make_normalizer(candles))
        run(mgr.start("SOL/USDT", "15m"))
        assert len(mgr._seen) <= 5_000

    def test_seen_set_not_pruned_below_threshold(self):
        mgr = PriceFeedManager()
        candles = [make_candle(timestamp=i) for i in range(100)]
        mgr.add_exchange(make_normalizer(candles))
        run(mgr.start("SOL/USDT", "15m"))
        assert len(mgr._seen) == 100
