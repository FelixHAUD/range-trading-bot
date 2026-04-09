"""
Unit tests for storage/candle_store.py and storage/db.py.
asyncpg is fully mocked — no real DB required.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from feeds.normalizer import NormalizedCandle
from storage.candle_store import CandleStore
import config


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_candle(is_closed: bool = True) -> NormalizedCandle:
    return NormalizedCandle(
        exchange="binance", symbol="SOL/USDT",
        timestamp=1_700_000_000_000,
        open=80.0, high=82.5, low=79.5, close=81.0,
        volume=1500.0, interval="15m", is_closed=is_closed,
    )


def make_store_with_mock_pool() -> tuple[CandleStore, AsyncMock]:
    store = CandleStore()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    store.pool = mock_pool
    return store, mock_conn


# ── write() ───────────────────────────────────────────────────────────────────

class TestWrite:
    def test_non_closed_candle_not_written(self):
        store, mock_conn = make_store_with_mock_pool()
        run(store.write(make_candle(is_closed=False)))
        mock_conn.execute.assert_not_called()

    def test_closed_candle_calls_execute(self):
        store, mock_conn = make_store_with_mock_pool()
        run(store.write(make_candle(is_closed=True)))
        mock_conn.execute.assert_called_once()

    def test_sql_contains_insert_into_candles(self):
        store, mock_conn = make_store_with_mock_pool()
        run(store.write(make_candle()))
        sql = mock_conn.execute.call_args[0][0]
        assert "INSERT INTO candles" in sql

    def test_sql_contains_on_conflict_do_nothing(self):
        store, mock_conn = make_store_with_mock_pool()
        run(store.write(make_candle()))
        sql = mock_conn.execute.call_args[0][0]
        assert "ON CONFLICT DO NOTHING" in sql

    def test_passes_nine_parameters(self):
        store, mock_conn = make_store_with_mock_pool()
        run(store.write(make_candle()))
        # call_args[0] = (sql, p1, p2, ..., p9)
        params = mock_conn.execute.call_args[0][1:]
        assert len(params) == 9

    def test_parameters_match_candle_fields(self):
        store, mock_conn = make_store_with_mock_pool()
        candle = make_candle()
        run(store.write(candle))
        params = mock_conn.execute.call_args[0][1:]
        assert params[0] == candle.timestamp
        assert params[1] == candle.exchange
        assert params[2] == candle.symbol
        assert params[3] == candle.interval
        assert params[4] == candle.open
        assert params[5] == candle.high
        assert params[6] == candle.low
        assert params[7] == candle.close
        assert params[8] == candle.volume

    def test_closed_false_then_true_only_writes_once(self):
        store, mock_conn = make_store_with_mock_pool()
        run(store.write(make_candle(is_closed=False)))
        run(store.write(make_candle(is_closed=True)))
        mock_conn.execute.assert_called_once()


# ── connect() ─────────────────────────────────────────────────────────────────

class TestConnect:
    def test_connect_uses_config_db_url(self):
        with patch("storage.db.asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock()
            store = CandleStore()
            run(store.connect())
            mock_create.assert_called_once_with(config.DB_URL)

    def test_connect_sets_pool_attribute(self):
        mock_pool = MagicMock()
        with patch("storage.db.asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_pool
            store = CandleStore()
            run(store.connect())
            assert store.pool is mock_pool

    def test_pool_initially_none(self):
        store = CandleStore()
        assert store.pool is None
