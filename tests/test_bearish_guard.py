"""
Unit tests for strategy/bearish_guard.py.
No network, no I/O — pure logic tests with hardcoded inputs.
"""
import pytest
from strategy.bearish_guard import BearishGuard
from strategy.dip_buy import Lot

SUPPORT    = 78.0
RESISTANCE = 85.0
MIDPOINT   = (SUPPORT + RESISTANCE) / 2.0   # 81.5
TS         = 1_700_000_000_000


def make_guard(min_bearish: int = 3, max_lot_loss_pct: float = 0.07) -> BearishGuard:
    return BearishGuard(min_bearish=min_bearish, max_lot_loss_pct=max_lot_loss_pct)


def make_lot(entry: float = 100.0, qty: float = 2.5) -> Lot:
    return Lot(id="lot_test", entry_price=entry, quantity=qty,
               entry_time=TS, reference_price=entry)


# All-neutral indicators: RSI=50, MACD bullish, price above midpoint, ADX=20
NEUTRAL = {
    "rsi": 50.0,
    "macd_bullish": True,
    "volume_above_avg": False,
    "adx": 20.0,
}

# All-bearish indicators
ALL_BEARISH = {
    "rsi": 35.0,
    "macd_bullish": False,
    "volume_above_avg": True,
    "adx": 30.0,
}


# ── BearishGuard.evaluate() ───────────────────────────────────────────────────

class TestEvaluate:
    def test_normal_when_zero_bearish_signals(self):
        guard = make_guard(min_bearish=3)
        # Price above midpoint, all indicators neutral/bullish
        result = guard.evaluate(MIDPOINT + 1, SUPPORT, RESISTANCE, NEUTRAL)
        assert result == "NORMAL"

    def test_normal_when_below_threshold(self):
        # Only 2 of 4 signals bearish (price below midpoint + MACD not bullish)
        guard = make_guard(min_bearish=3)
        indicators = {**NEUTRAL, "macd_bullish": False}
        result = guard.evaluate(MIDPOINT - 1, SUPPORT, RESISTANCE, indicators)
        assert result == "NORMAL"

    def test_pause_buys_when_threshold_met(self):
        # Exactly 3 of 4 bearish: RSI<40, MACD not bullish, price below midpoint
        guard = make_guard(min_bearish=3)
        indicators = {**NEUTRAL, "rsi": 38.0, "macd_bullish": False}
        result = guard.evaluate(MIDPOINT - 1, SUPPORT, RESISTANCE, indicators)
        assert result == "PAUSE_BUYS"

    def test_pause_buys_when_all_bearish(self):
        guard = make_guard(min_bearish=3)
        result = guard.evaluate(MIDPOINT - 1, SUPPORT, RESISTANCE, ALL_BEARISH)
        assert result == "PAUSE_BUYS"

    def test_rsi_bearish_strictly_below_40(self):
        # RSI=39.9 counts as bearish
        guard = make_guard(min_bearish=1)
        indicators = {**NEUTRAL, "rsi": 39.9}
        result = guard.evaluate(MIDPOINT + 1, SUPPORT, RESISTANCE, indicators)
        assert result == "PAUSE_BUYS"

    def test_rsi_not_bearish_at_exactly_40(self):
        # RSI=40.0 does NOT count (strictly less than)
        guard = make_guard(min_bearish=1)
        indicators = {**NEUTRAL, "rsi": 40.0}
        result = guard.evaluate(MIDPOINT + 1, SUPPORT, RESISTANCE, indicators)
        assert result == "NORMAL"

    def test_macd_bearish_when_not_bullish(self):
        guard = make_guard(min_bearish=1)
        indicators = {**NEUTRAL, "macd_bullish": False}
        result = guard.evaluate(MIDPOINT + 1, SUPPORT, RESISTANCE, indicators)
        assert result == "PAUSE_BUYS"

    def test_price_below_midpoint_bearish(self):
        guard = make_guard(min_bearish=1)
        result = guard.evaluate(MIDPOINT - 0.01, SUPPORT, RESISTANCE, NEUTRAL)
        assert result == "PAUSE_BUYS"

    def test_adx_bearish_strictly_above_25(self):
        # ADX=25.1 counts; ADX=25.0 does NOT
        guard = make_guard(min_bearish=1)
        above = {**NEUTRAL, "adx": 25.1}
        at    = {**NEUTRAL, "adx": 25.0}
        assert guard.evaluate(MIDPOINT + 1, SUPPORT, RESISTANCE, above) == "PAUSE_BUYS"
        assert guard.evaluate(MIDPOINT + 1, SUPPORT, RESISTANCE, at)    == "NORMAL"


# ── BearishGuard.should_exit_lot() ───────────────────────────────────────────

class TestShouldExitLot:
    def test_exit_at_exact_threshold(self):
        guard = make_guard(max_lot_loss_pct=0.07)
        lot = make_lot(entry=100.0)
        # price exactly 7% below entry
        assert guard.should_exit_lot(lot, 93.0) is True

    def test_exit_above_threshold(self):
        guard = make_guard(max_lot_loss_pct=0.07)
        lot = make_lot(entry=100.0)
        # 10% loss — well beyond threshold
        assert guard.should_exit_lot(lot, 90.0) is True

    def test_no_exit_below_threshold(self):
        guard = make_guard(max_lot_loss_pct=0.07)
        lot = make_lot(entry=100.0)
        # 4% loss — below 7% threshold
        assert guard.should_exit_lot(lot, 96.0) is False

    def test_no_exit_lot_in_profit(self):
        guard = make_guard(max_lot_loss_pct=0.07)
        lot = make_lot(entry=100.0)
        # 5% gain — definitely not an exit
        assert guard.should_exit_lot(lot, 105.0) is False
