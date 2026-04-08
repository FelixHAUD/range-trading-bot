"""
Unit tests for strategy/hold_extension.py.
All inputs are synthetic — no network, no config import.
"""
import pytest
from strategy.hold_extension import HoldExtension
from strategy.dip_buy import Lot

TRAIL = 0.02   # 2% trailing stop
MIN_BULLISH = 2

TS = 1_700_000_000_000


def make_ext(**kwargs) -> HoldExtension:
    defaults = dict(trail_pct=TRAIL, min_bullish=MIN_BULLISH)
    defaults.update(kwargs)
    return HoldExtension(**defaults)


def make_lot(entry: float = 80.0, lot_id: str = "lot_1") -> Lot:
    return Lot(
        id=lot_id,
        entry_price=entry,
        quantity=3.0,
        entry_time=TS,
        reference_price=entry * 1.05,
    )


def all_bullish() -> dict:
    return {"rsi": 60.0, "macd_bullish": True, "volume_above_avg": True, "adx": 30.0}


def no_bullish() -> dict:
    return {"rsi": 40.0, "macd_bullish": False, "volume_above_avg": False, "adx": 10.0}


# ── SELL path (insufficient bullish signals) ──────────────────────────────────

class TestSellPath:
    def test_returns_sell_when_no_bullish_signals(self):
        ext = make_ext()
        lot = make_lot()
        result = ext.evaluate(lot, 85.0, no_bullish())
        assert result == "SELL"

    def test_returns_sell_when_exactly_one_signal_but_min_is_two(self):
        ext = make_ext(min_bullish=2)
        indicators = {"rsi": 60.0, "macd_bullish": False,
                      "volume_above_avg": False, "adx": 10.0}
        result = ext.evaluate(make_lot(), 85.0, indicators)
        assert result == "SELL"

    def test_returns_sell_with_empty_indicators(self):
        ext = make_ext()
        result = ext.evaluate(make_lot(), 85.0, {})
        assert result == "SELL"

    def test_sell_does_not_create_lot_high_entry(self):
        ext = make_ext()
        lot = make_lot()
        ext.evaluate(lot, 85.0, no_bullish())
        assert lot.id not in ext._lot_highs

    def test_min_bullish_zero_always_holds(self):
        ext = make_ext(min_bullish=0)
        result = ext.evaluate(make_lot(), 85.0, no_bullish())
        assert result != "SELL"


# ── HOLD path (bullish confirmed, trailing stop not hit) ──────────────────────

class TestHoldPath:
    def test_returns_hold_when_bullish_and_price_above_trail(self):
        ext = make_ext()
        lot = make_lot()
        result = ext.evaluate(lot, 85.0, all_bullish())
        assert result == "HOLD"

    def test_running_high_initialised_to_first_price(self):
        ext = make_ext()
        lot = make_lot()
        ext.evaluate(lot, 85.0, all_bullish())
        assert ext._lot_highs[lot.id] == 85.0

    def test_running_high_tracks_upward_moves(self):
        ext = make_ext()
        lot = make_lot()
        ext.evaluate(lot, 85.0, all_bullish())
        ext.evaluate(lot, 87.0, all_bullish())
        assert ext._lot_highs[lot.id] == 87.0

    def test_running_high_does_not_decrease(self):
        ext = make_ext()
        lot = make_lot()
        ext.evaluate(lot, 87.0, all_bullish())
        # trail stop = 87 * 0.98 = 85.26; use 86.0 to stay above stop
        ext.evaluate(lot, 86.0, all_bullish())   # price dips but high stays
        assert ext._lot_highs[lot.id] == 87.0

    def test_hold_for_multiple_candles_while_above_trail(self):
        ext = make_ext()
        lot = make_lot()
        prices = [85.0, 86.0, 87.0, 86.5]
        for p in prices:
            result = ext.evaluate(lot, p, all_bullish())
            assert result == "HOLD"

    def test_exactly_min_bullish_signals_gives_hold(self):
        ext = make_ext(min_bullish=2)
        indicators = {"rsi": 60.0, "macd_bullish": True,
                      "volume_above_avg": False, "adx": 10.0}
        result = ext.evaluate(make_lot(), 85.0, indicators)
        assert result == "HOLD"


# ── TRAIL_STOP_HIT path ───────────────────────────────────────────────────────

class TestTrailStopHit:
    def test_returns_trail_stop_hit_when_price_falls_to_stop(self):
        ext = make_ext(trail_pct=0.02)
        lot = make_lot()
        ext.evaluate(lot, 100.0, all_bullish())   # high = 100, stop = 98
        result = ext.evaluate(lot, 98.0, all_bullish())
        assert result == "TRAIL_STOP_HIT"

    def test_trail_stop_calculated_from_running_high(self):
        ext = make_ext(trail_pct=0.02)
        lot = make_lot()
        ext.evaluate(lot, 85.0, all_bullish())    # high = 85, stop = 83.3
        ext.evaluate(lot, 90.0, all_bullish())    # high = 90, stop = 88.2
        result = ext.evaluate(lot, 88.0, all_bullish())  # 88 <= 88.2 → hit
        assert result == "TRAIL_STOP_HIT"

    def test_trail_stop_not_hit_just_above_stop(self):
        ext = make_ext(trail_pct=0.02)
        lot = make_lot()
        ext.evaluate(lot, 100.0, all_bullish())   # stop = 98.0
        result = ext.evaluate(lot, 98.01, all_bullish())
        assert result == "HOLD"

    def test_lot_high_removed_on_trail_stop_hit(self):
        ext = make_ext(trail_pct=0.02)
        lot = make_lot()
        ext.evaluate(lot, 100.0, all_bullish())
        ext.evaluate(lot, 98.0, all_bullish())    # TRAIL_STOP_HIT
        assert lot.id not in ext._lot_highs

    def test_multiple_lots_tracked_independently(self):
        ext = make_ext(trail_pct=0.02)
        lot_a = make_lot(entry=80.0, lot_id="lot_a")
        lot_b = make_lot(entry=82.0, lot_id="lot_b")
        ext.evaluate(lot_a, 100.0, all_bullish())
        ext.evaluate(lot_b, 90.0, all_bullish())
        # hit lot_a's stop (98.0) but lot_b's stop is 88.2 — not hit yet
        result_a = ext.evaluate(lot_a, 98.0, all_bullish())
        result_b = ext.evaluate(lot_b, 89.0, all_bullish())
        assert result_a == "TRAIL_STOP_HIT"
        assert result_b == "HOLD"
        assert "lot_a" not in ext._lot_highs
        assert "lot_b" in ext._lot_highs
