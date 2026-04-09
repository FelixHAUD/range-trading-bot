"""
Unit tests for indicators/.
All inputs are synthetic — no network, no config import.
"""
import pytest
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker
from indicators.candles import CandleAggregator


# ── RSI ───────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_value_none_before_period_plus_one_candles(self):
        rsi = RSI(period=14)
        for i in range(14):
            rsi.update(100.0 + i)
        assert rsi.value is None

    def test_value_set_after_period_plus_one_candles(self):
        rsi = RSI(period=14)
        for i in range(15):
            rsi.update(100.0 + i)
        assert rsi.value is not None

    def test_all_gains_gives_rsi_100(self):
        rsi = RSI(period=14)
        for i in range(15):
            rsi.update(100.0 + i)   # every candle up
        assert rsi.value == pytest.approx(100.0)

    def test_all_losses_gives_rsi_0(self):
        rsi = RSI(period=14)
        for i in range(15):
            rsi.update(114.0 - i)   # every candle down
        assert rsi.value == pytest.approx(0.0)

    def test_equal_gains_and_losses_gives_rsi_50(self):
        # 14 alternating +1 / -1 moves → avg_gain == avg_loss → RSI = 50
        rsi = RSI(period=14)
        closes = [100, 101, 100, 101, 100, 101, 100, 101,
                  100, 101, 100, 101, 100, 101, 100]
        for c in closes:
            rsi.update(float(c))
        assert rsi.value == pytest.approx(50.0)

    def test_rsi_bounded_between_0_and_100(self):
        rsi = RSI(period=14)
        for i in range(30):
            rsi.update(float(i * 5))
        assert rsi.value is not None
        assert 0.0 <= rsi.value <= 100.0

    def test_rsi_decreases_after_sharp_drop(self):
        rsi = RSI(period=14)
        for i in range(15):
            rsi.update(100.0 + i)   # all-up run → RSI 100
        v_before = rsi.value
        rsi.update(50.0)            # sharp drop
        assert rsi.value < v_before

    def test_rsi_period_respected(self):
        """Smaller period converges faster."""
        rsi = RSI(period=3)
        for i in range(4):
            rsi.update(float(i))
        assert rsi.value is not None


# ── MACD ──────────────────────────────────────────────────────────────────────

class TestMACD:
    # Use small periods so tests need fewer candles and are deterministic.
    # fast=3, slow=5, signal=3 → needs slow+signal=8 candles before bullish is evaluated.

    def test_bullish_false_initially(self):
        macd = MACD(fast=3, slow=5, signal=3)
        assert macd.bullish is False

    def test_bullish_stays_false_before_enough_candles(self):
        macd = MACD(fast=3, slow=5, signal=3)
        for i in range(7):   # slow+signal-1 = 7
            macd.update(100.0 + i)
        assert macd.bullish is False

    def test_bullish_true_on_sustained_uptrend(self):
        # After 8 rising candles with fast=3, slow=5, signal=3 the MACD
        # line is positive and still accelerating → bullish = True.
        macd = MACD(fast=3, slow=5, signal=3)
        for i in range(8):
            macd.update(100.0 + i)
        assert macd.bullish is True

    def test_bullish_false_on_flat_price(self):
        macd = MACD(fast=3, slow=5, signal=3)
        for _ in range(20):
            macd.update(100.0)
        # Flat → MACD line = 0, not > 0
        assert macd.bullish is False

    def test_bullish_false_on_downtrend(self):
        macd = MACD(fast=3, slow=5, signal=3)
        for i in range(20):
            macd.update(120.0 - i)
        assert macd.bullish is False

    def test_bullish_can_flip_false_after_trend_reversal(self):
        macd = MACD(fast=3, slow=5, signal=3)
        for i in range(8):        # uptrend → bullish True
            macd.update(100.0 + i)
        assert macd.bullish is True
        for i in range(20):       # sustained downtrend → bullish False
            macd.update(108.0 - i * 2)
        assert macd.bullish is False

    def test_default_periods_are_12_26_9(self):
        macd = MACD()
        assert macd.fast == 12
        assert macd.slow == 26
        assert macd.signal == 9


# ── ADX ───────────────────────────────────────────────────────────────────────

class TestADX:
    def test_value_zero_before_period_plus_one_candles(self):
        adx = ADX(period=14)
        for i in range(14):
            adx.update(100.0 + i * 2, 99.0 + i * 2, 99.5 + i * 2)
        assert adx.value == 0.0

    def test_value_nonzero_after_period_plus_one_candles(self):
        adx = ADX(period=14)
        for i in range(15):
            adx.update(100.0 + i * 2, 99.0 + i * 2, 99.5 + i * 2)
        assert adx.value > 0.0

    def test_adx_bounded_0_to_100(self):
        adx = ADX(period=14)
        for i in range(30):
            adx.update(100.0 + i, 99.0 + i, 99.5 + i)
        assert 0.0 <= adx.value <= 100.0

    def test_adx_zero_on_perfectly_flat_market(self):
        # No directional movement at all → +DM = -DM = 0 → DX = 0
        adx = ADX(period=14)
        for _ in range(15):
            adx.update(100.0, 99.0, 99.5)
        assert adx.value == pytest.approx(0.0)

    def test_adx_high_on_strong_uptrend(self):
        adx = ADX(period=5)
        # Clear, consistent uptrend: each candle's high/low entirely above previous
        for i in range(6):
            adx.update(100.0 + i * 3, 100.0 + i * 3 - 1, 100.0 + i * 3 - 0.5)
        assert adx.value > 0.0

    def test_adx_increases_with_stronger_trend(self):
        # Mild trend vs. strong trend: strong should give higher ADX
        adx_mild = ADX(period=5)
        adx_strong = ADX(period=5)
        for i in range(6):
            adx_mild.update(100.0 + i * 0.5, 100.0 + i * 0.5 - 0.3, 100.0 + i * 0.5 - 0.1)
            adx_strong.update(100.0 + i * 5, 100.0 + i * 5 - 1, 100.0 + i * 5 - 0.5)
        assert adx_strong.value >= adx_mild.value


# ── VolumeTracker ─────────────────────────────────────────────────────────────

class TestVolumeTracker:
    def test_above_average_false_on_first_candle(self):
        vt = VolumeTracker(lookback=5)
        vt.update(1000.0)
        assert vt.above_average is False

    def test_above_average_true_when_volume_exceeds_mean(self):
        vt = VolumeTracker(lookback=5)
        for _ in range(4):
            vt.update(1000.0)
        vt.update(2000.0)   # well above rolling avg of 1200
        assert vt.above_average is True

    def test_above_average_false_when_volume_below_mean(self):
        vt = VolumeTracker(lookback=5)
        for _ in range(4):
            vt.update(1000.0)
        vt.update(500.0)   # below rolling avg
        assert vt.above_average is False

    def test_exactly_at_average_is_not_above(self):
        vt = VolumeTracker(lookback=3)
        vt.update(1000.0)
        vt.update(1000.0)
        vt.update(1000.0)   # current = avg = 1000 → not strictly above
        assert vt.above_average is False

    def test_rolling_window_prunes_old_data(self):
        vt = VolumeTracker(lookback=3)
        vt.update(1000.0)
        vt.update(1000.0)
        vt.update(1000.0)   # window: [1000, 1000, 1000], avg=1000
        vt.update(5000.0)   # window: [1000, 1000, 5000], avg≈2333; current > avg ✓
        vt.update(100.0)    # window: [1000, 5000, 100], avg≈2033; current < avg ✓
        assert vt.above_average is False

    def test_lookback_window_is_enforced(self):
        vt = VolumeTracker(lookback=3)
        for _ in range(10):
            vt.update(1000.0)
        assert len(vt._volumes) == 3


# ── CandleAggregator (stub) ───────────────────────────────────────────────────

class TestCandleAggregator:
    def test_update_does_not_raise(self):
        agg = CandleAggregator()
        agg.update(None)

    def test_update_accepts_any_argument(self):
        agg = CandleAggregator()
        agg.update("anything")
        agg.update(42)
        agg.update({})
