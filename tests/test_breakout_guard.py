"""
Unit tests for strategy/breakout_guard.py.
All inputs are synthetic — no config import, no network.
"""
import pytest
from strategy.breakout_guard import BreakoutGuard

SUPPORT = 78.0
RESISTANCE = 85.0
BUFFER = 0.02      # 2%
CONFIRM = 3


def make_guard() -> BreakoutGuard:
    return BreakoutGuard(buffer_pct=BUFFER, confirm_candles=CONFIRM)


# ── Normal in-range behaviour ─────────────────────────────────────────────────

class TestInRange:
    def test_mid_range_returns_true(self):
        g = make_guard()
        assert g.check(81.5, SUPPORT, RESISTANCE) is True

    def test_exactly_at_support_returns_true(self):
        g = make_guard()
        assert g.check(SUPPORT, SUPPORT, RESISTANCE) is True

    def test_exactly_at_resistance_returns_true(self):
        g = make_guard()
        assert g.check(RESISTANCE, SUPPORT, RESISTANCE) is True

    def test_at_lower_buffer_boundary_returns_true(self):
        # lower = 78 * 0.98 = 76.44 — price exactly at boundary is still inside
        lower = SUPPORT * (1 - BUFFER)
        g = make_guard()
        assert g.check(lower, SUPPORT, RESISTANCE) is True

    def test_at_upper_buffer_boundary_returns_true(self):
        upper = RESISTANCE * (1 + BUFFER)
        g = make_guard()
        assert g.check(upper, SUPPORT, RESISTANCE) is True

    def test_not_paused_initially(self):
        g = make_guard()
        assert g.paused is False


# ── Breakout detection ────────────────────────────────────────────────────────

class TestBreakout:
    def test_below_lower_buffer_returns_false(self):
        g = make_guard()
        below = SUPPORT * (1 - BUFFER) - 0.01
        assert g.check(below, SUPPORT, RESISTANCE) is False

    def test_above_upper_buffer_returns_false(self):
        g = make_guard()
        above = RESISTANCE * (1 + BUFFER) + 0.01
        assert g.check(above, SUPPORT, RESISTANCE) is False

    def test_breakout_sets_paused_true(self):
        g = make_guard()
        g.check(70.0, SUPPORT, RESISTANCE)
        assert g.paused is True

    def test_breakout_resets_candles_inside_counter(self):
        g = make_guard()
        # partial confirm progress then another breakout
        g.check(70.0, SUPPORT, RESISTANCE)   # breakout
        g.check(81.0, SUPPORT, RESISTANCE)   # 1 inside
        g.check(70.0, SUPPORT, RESISTANCE)   # breakout again — counter resets
        assert g._candles_inside == 0

    def test_consecutive_breakout_candles_keep_returning_false(self):
        g = make_guard()
        for _ in range(5):
            assert g.check(70.0, SUPPORT, RESISTANCE) is False


# ── Resume after confirm candles ──────────────────────────────────────────────

class TestResume:
    def test_returns_false_during_confirm_window(self):
        g = make_guard()
        g.check(70.0, SUPPORT, RESISTANCE)   # breakout
        for i in range(CONFIRM - 1):
            result = g.check(81.0, SUPPORT, RESISTANCE)
            assert result is False, f"expected False on confirm candle {i+1}"

    def test_resumes_after_exactly_confirm_candles(self):
        g = make_guard()
        g.check(70.0, SUPPORT, RESISTANCE)   # breakout
        for _ in range(CONFIRM):
            g.check(81.0, SUPPORT, RESISTANCE)
        # next in-range candle should return True and paused should be False
        assert g.check(81.0, SUPPORT, RESISTANCE) is True
        assert g.paused is False

    def test_paused_clears_after_confirm(self):
        g = make_guard()
        g.check(70.0, SUPPORT, RESISTANCE)
        for _ in range(CONFIRM):
            g.check(81.0, SUPPORT, RESISTANCE)
        assert g.paused is False

    def test_second_breakout_after_resume_re_pauses(self):
        g = make_guard()
        # first breakout + full confirm
        g.check(70.0, SUPPORT, RESISTANCE)
        for _ in range(CONFIRM):
            g.check(81.0, SUPPORT, RESISTANCE)
        g.check(81.0, SUPPORT, RESISTANCE)   # confirmed resumed
        # second breakout
        assert g.check(100.0, SUPPORT, RESISTANCE) is False
        assert g.paused is True

    def test_confirm_counter_increments_correctly(self):
        g = make_guard()
        g.check(70.0, SUPPORT, RESISTANCE)
        g.check(81.0, SUPPORT, RESISTANCE)
        assert g._candles_inside == 1
        g.check(81.0, SUPPORT, RESISTANCE)
        assert g._candles_inside == 2
