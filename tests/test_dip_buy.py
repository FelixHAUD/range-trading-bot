"""
Unit tests for strategy/dip_buy.py.
All inputs are synthetic — no network, no config import.
"""
import pytest
from strategy.dip_buy import DipBuyStrategy, Lot

DIP = 0.05        # -5%
TARGET = 0.05     # +5%
MAX_LOTS = 4
LOT_USD = 250.0
TS = 1_700_000_000_000


def make_strategy(**kwargs) -> DipBuyStrategy:
    defaults = dict(dip_pct=DIP, target_pct=TARGET, max_lots=MAX_LOTS,
                    lot_size_usd=LOT_USD, rolling_high_candles=5)
    defaults.update(kwargs)
    return DipBuyStrategy(**defaults)


# ── Rolling high initialisation ───────────────────────────────────────────────

class TestRollingHigh:
    def test_no_signal_on_first_candle_at_high(self):
        s = make_strategy()
        signals = s.on_candle(100.0, TS)
        assert signals == []

    def test_rolling_high_tracks_max_of_window(self):
        s = make_strategy(rolling_high_candles=3)
        s.on_candle(100.0, TS)
        s.on_candle(102.0, TS)
        s.on_candle(101.0, TS)
        assert s._rolling_high == 100.0   # set on first candle, hasn't reset
        # after a buy it resets to close


# ── BUY signal ────────────────────────────────────────────────────────────────

class TestBuySignal:
    def test_buy_fired_when_drop_meets_threshold(self):
        s = make_strategy()
        s.on_candle(100.0, TS)           # sets rolling high to 100
        signals = s.on_candle(94.9, TS)  # ~5.1% drop
        buys = [sig for sig in signals if sig["action"] == "BUY"]
        assert len(buys) == 1

    def test_no_buy_when_drop_below_threshold(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        signals = s.on_candle(96.0, TS)  # only 4% drop
        assert not any(sig["action"] == "BUY" for sig in signals)

    def test_lot_fields_populated_correctly(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        signals = s.on_candle(94.0, TS)
        lot = signals[0]["lot"]
        assert isinstance(lot, Lot)
        assert lot.entry_price == 94.0
        assert lot.quantity == pytest.approx(LOT_USD / 94.0)
        assert lot.reference_price == 100.0
        assert lot.entry_time == TS
        assert lot.id.startswith("lot_")

    def test_rolling_high_resets_to_close_after_buy(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)   # triggers buy → resets rolling high to 94.0
        assert s._rolling_high == 94.0

    def test_lot_added_to_open_lots(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)
        assert len(s.open_lots) == 1

    def test_no_buy_when_max_lots_reached(self):
        s = make_strategy(max_lots=1)
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)   # first buy
        # second dip — max_lots already reached
        signals = s.on_candle(88.0, TS)
        buys = [sig for sig in signals if sig["action"] == "BUY"]
        assert len(buys) == 0

    def test_multiple_lots_accumulate_up_to_max(self):
        s = make_strategy(max_lots=3)
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)   # lot 1, rolling high resets to 94
        s.on_candle(89.0, TS)   # lot 2, rolling high resets to 89
        s.on_candle(84.0, TS)   # lot 3, rolling high resets to 84
        assert len(s.open_lots) == 3
        signals = s.on_candle(79.0, TS)   # would be lot 4 but max=3
        buys = [sig for sig in signals if sig["action"] == "BUY"]
        assert len(buys) == 0


# ── SELL_CHECK signal ─────────────────────────────────────────────────────────

class TestSellCheck:
    def test_sell_check_fired_when_gain_meets_target(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)          # buy at 94
        entry = s.open_lots[0].entry_price
        sell_price = entry * (1 + TARGET + 0.001)
        signals = s.on_candle(sell_price, TS)
        checks = [sig for sig in signals if sig["action"] == "SELL_CHECK"]
        assert len(checks) == 1

    def test_sell_check_not_fired_below_target(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)          # buy at 94
        entry = s.open_lots[0].entry_price
        signals = s.on_candle(entry * 1.04, TS)   # only +4%, below +5%
        assert not any(sig["action"] == "SELL_CHECK" for sig in signals)

    def test_sell_check_gain_value_correct(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)
        entry = s.open_lots[0].entry_price
        sell_price = entry * 1.06
        signals = s.on_candle(sell_price, TS)
        check = next(sig for sig in signals if sig["action"] == "SELL_CHECK")
        assert check["gain"] == pytest.approx((sell_price - entry) / entry)

    def test_sell_check_fires_for_each_qualifying_lot(self):
        s = make_strategy(max_lots=2)
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)   # lot 1 at 94, rolling high resets to 94
        s.on_candle(89.0, TS)   # lot 2 at 89 (5.3% drop from 94 ✓)
        # price jumps high enough to trigger both lots
        high_price = 100.0
        signals = s.on_candle(high_price, TS)
        checks = [sig for sig in signals if sig["action"] == "SELL_CHECK"]
        assert len(checks) == 2


# ── close_lot ─────────────────────────────────────────────────────────────────

class TestCloseLot:
    def test_close_lot_removes_correct_lot(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)
        lot_id = s.open_lots[0].id
        s.close_lot(lot_id)
        assert len(s.open_lots) == 0

    def test_close_lot_unknown_id_is_noop(self):
        s = make_strategy()
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)
        s.close_lot("nonexistent_id")
        assert len(s.open_lots) == 1

    def test_close_lot_leaves_other_lots_intact(self):
        s = make_strategy(max_lots=2)
        s.on_candle(100.0, TS)
        s.on_candle(94.0, TS)   # lot 1: 6% drop from 100, rolling high resets to 94
        s.on_candle(89.0, TS)   # lot 2: 5.3% drop from 94 (94*0.95=89.3, so 89<89.3 ✓)
        assert len(s.open_lots) == 2, "setup: expected 2 open lots"
        id_to_close = s.open_lots[0].id
        s.close_lot(id_to_close)
        assert len(s.open_lots) == 1
        assert s.open_lots[0].id != id_to_close
