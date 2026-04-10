"""
Unit tests for strategy/engine.py and execution/paper_trader.py.
No network — alert is mocked (AsyncMock), all strategy components are real.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock

from feeds.normalizer import NormalizedCandle
from strategy.engine import StrategyEngine
from strategy.bearish_guard import BearishGuard
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy, Lot
from strategy.hold_extension import HoldExtension
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker
from indicators.ema import EMA
from execution.paper_trader import PaperTrader

SUPPORT = 78.0
RESISTANCE = 85.0
TS = 1_700_000_000_000


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_candle(close: float, is_closed: bool = True, volume: float = 1000.0) -> NormalizedCandle:
    return NormalizedCandle(
        exchange="binance", symbol="SOL/USDT", timestamp=TS,
        open=close, high=close * 1.005, low=close * 0.995,
        close=close, volume=volume, interval="15m", is_closed=is_closed,
    )


def make_engine(
    min_bullish: int = 2,
    min_bearish: int = 3,
    max_lot_loss_pct: float = 0.07,
    hard_stop_pct: float = 1.0,       # default=100% (disabled) unless explicitly set
    trend_ema: EMA | None = None,
) -> tuple[StrategyEngine, AsyncMock]:
    alert = AsyncMock()
    engine = StrategyEngine(
        guard=BreakoutGuard(buffer_pct=0.02, confirm_candles=3),
        dip_buy=DipBuyStrategy(dip_pct=0.05, target_pct=0.05, max_lots=4, lot_size_usd=250.0),
        hold_ext=HoldExtension(trail_pct=0.02, min_bullish=min_bullish),
        rsi=RSI(period=14),
        macd=MACD(),
        adx=ADX(period=14),
        volume=VolumeTracker(lookback=20),
        trader=PaperTrader(),
        alert=alert,
        support=SUPPORT,
        resistance=RESISTANCE,
        bearish_guard=BearishGuard(min_bearish=min_bearish, max_lot_loss_pct=max_lot_loss_pct),
        max_drawdown_pct=0.10,
        hard_stop_pct=hard_stop_pct,
        trend_ema=trend_ema,
    )
    return engine, alert


# ── Candle gating ─────────────────────────────────────────────────────────────

class TestOnCandleGating:
    def test_non_closed_candle_skipped_no_trade(self):
        engine, alert = make_engine()
        run(engine.on_candle(make_candle(81.0, is_closed=False)))
        assert len(engine.trader.trades) == 0

    def test_non_closed_candle_skipped_no_alert(self):
        engine, alert = make_engine()
        run(engine.on_candle(make_candle(81.0, is_closed=False)))
        alert.send.assert_not_called()

    def test_breakout_fires_pause_alert(self):
        engine, alert = make_engine()
        # 70.0 < 78 * 0.98 = 76.44 → breakout
        run(engine.on_candle(make_candle(70.0)))
        alert.send.assert_called_once()
        assert "PAUSED" in alert.send.call_args[0][0]

    def test_breakout_does_not_trigger_trade(self):
        engine, alert = make_engine()
        run(engine.on_candle(make_candle(70.0)))
        assert len(engine.trader.trades) == 0

    def test_in_range_first_candle_no_trade(self):
        engine, alert = make_engine()
        run(engine.on_candle(make_candle(81.0)))
        assert len(engine.trader.trades) == 0


# ── BUY path ─────────────────────────────────────────────────────────────────

class TestBuyPath:
    def _trigger_buy(self, engine: StrategyEngine) -> None:
        run(engine.on_candle(make_candle(81.0)))   # rolling high = 81
        run(engine.on_candle(make_candle(76.5)))   # 5.6% drop → BUY

    def test_buy_signal_recorded_in_trades(self):
        engine, alert = make_engine()
        self._trigger_buy(engine)
        assert any(t["action"] == "BUY" for t in engine.trader.trades)

    def test_buy_sends_alert_with_buy_in_message(self):
        engine, alert = make_engine()
        self._trigger_buy(engine)
        assert any("BUY" in str(call) for call in alert.send.call_args_list)

    def test_buy_reduces_balance(self):
        engine, alert = make_engine()
        initial = engine.trader.balance_usd
        self._trigger_buy(engine)
        assert engine.trader.balance_usd < initial

    def test_buy_adds_lot_to_open_lots(self):
        engine, alert = make_engine()
        self._trigger_buy(engine)
        assert len(engine.dip_buy.open_lots) == 1

    def test_buy_lot_entry_price_matches_candle_close(self):
        engine, alert = make_engine()
        self._trigger_buy(engine)
        assert engine.dip_buy.open_lots[0].entry_price == pytest.approx(76.5)


# ── SELL path (no momentum → immediate sell) ──────────────────────────────────

class TestSellPath:
    def _setup_buy(self, engine: StrategyEngine) -> float:
        """Drive to a bought state. Returns entry_price."""
        run(engine.on_candle(make_candle(81.0)))
        run(engine.on_candle(make_candle(76.5)))   # BUY at 76.5
        return engine.dip_buy.open_lots[0].entry_price

    def test_sell_check_leads_to_sell_with_no_momentum(self):
        # Indicators not warmed up → 0 bullish signals < min_bullish=2 → SELL
        engine, alert = make_engine(min_bullish=2)
        entry = self._setup_buy(engine)
        run(engine.on_candle(make_candle(entry * 1.06)))  # +6% → SELL_CHECK → SELL
        assert any(t["action"] == "SELL" for t in engine.trader.trades)

    def test_sell_closes_lot(self):
        engine, alert = make_engine(min_bullish=2)
        entry = self._setup_buy(engine)
        run(engine.on_candle(make_candle(entry * 1.06)))
        assert len(engine.dip_buy.open_lots) == 0

    def test_sell_increases_balance_above_post_buy(self):
        engine, alert = make_engine(min_bullish=2)
        entry = self._setup_buy(engine)
        balance_after_buy = engine.trader.balance_usd
        run(engine.on_candle(make_candle(entry * 1.06)))
        assert engine.trader.balance_usd > balance_after_buy

    def test_sell_sends_alert(self):
        engine, alert = make_engine(min_bullish=2)
        entry = self._setup_buy(engine)
        alert.reset_mock()
        run(engine.on_candle(make_candle(entry * 1.06)))
        assert alert.send.called
        msg = alert.send.call_args[0][0]
        assert "SELL" in msg or "TRAIL_STOP_HIT" in msg

    def test_sell_pnl_is_positive_on_gain(self):
        engine, alert = make_engine(min_bullish=2)
        entry = self._setup_buy(engine)
        run(engine.on_candle(make_candle(entry * 1.06)))
        sell_trade = next(t for t in engine.trader.trades if t["action"] == "SELL")
        assert sell_trade["pnl_usd"] > 0


# ── HOLD path (momentum confirmed, trail stop not hit) ────────────────────────

class TestHoldPath:
    def test_hold_does_not_execute_sell(self):
        # min_bullish=0 → always enters trail-stop path; price just above stop → HOLD
        engine, alert = make_engine(min_bullish=0)
        run(engine.on_candle(make_candle(81.0)))
        run(engine.on_candle(make_candle(76.5)))   # BUY
        entry = engine.dip_buy.open_lots[0].entry_price
        run(engine.on_candle(make_candle(entry * 1.06)))  # SELL_CHECK → HOLD
        assert not any(t["action"] == "SELL" for t in engine.trader.trades)

    def test_hold_keeps_lot_open(self):
        engine, alert = make_engine(min_bullish=0)
        run(engine.on_candle(make_candle(81.0)))
        run(engine.on_candle(make_candle(76.5)))
        entry = engine.dip_buy.open_lots[0].entry_price
        run(engine.on_candle(make_candle(entry * 1.06)))
        assert len(engine.dip_buy.open_lots) == 1


# ── TRAIL_STOP_HIT path ───────────────────────────────────────────────────────

class TestTrailStopHit:
    def _setup_trail(self, engine: StrategyEngine) -> tuple[float, float]:
        """Buy, then push price up to set a trail high. Returns (entry, trail_high)."""
        run(engine.on_candle(make_candle(81.0)))
        run(engine.on_candle(make_candle(76.5)))      # BUY
        entry = engine.dip_buy.open_lots[0].entry_price
        run(engine.on_candle(make_candle(entry * 1.06)))  # SELL_CHECK → HOLD
        trail_high = entry * 1.10
        run(engine.on_candle(make_candle(trail_high)))    # SELL_CHECK → HOLD, trail updated
        return entry, trail_high

    def test_trail_stop_hit_closes_lot(self):
        engine, alert = make_engine(min_bullish=0)
        entry, trail_high = self._setup_trail(engine)
        # Drop to just below trail stop (trail_high * 0.98) but still above +5% target
        trail_stop_price = trail_high * 0.98 - 0.01
        run(engine.on_candle(make_candle(trail_stop_price)))
        assert len(engine.dip_buy.open_lots) == 0

    def test_trail_stop_hit_sends_alert(self):
        engine, alert = make_engine(min_bullish=0)
        entry, trail_high = self._setup_trail(engine)
        alert.reset_mock()
        trail_stop_price = trail_high * 0.98 - 0.01
        run(engine.on_candle(make_candle(trail_stop_price)))
        assert alert.send.called
        assert "TRAIL_STOP_HIT" in alert.send.call_args[0][0]

    def test_trail_stop_hit_records_sell_trade(self):
        engine, alert = make_engine(min_bullish=0)
        entry, trail_high = self._setup_trail(engine)
        trail_stop_price = trail_high * 0.98 - 0.01
        run(engine.on_candle(make_candle(trail_stop_price)))
        assert any(t["action"] == "SELL" for t in engine.trader.trades)


# ── PaperTrader unit tests ────────────────────────────────────────────────────

class TestPaperTrader:
    def _make_lot(self, entry: float = 80.0, qty: float = 3.0) -> Lot:
        return Lot(id="lot_1", entry_price=entry, quantity=qty,
                   entry_time=TS, reference_price=entry * 1.05)

    def test_initial_balance_is_ten_thousand(self):
        assert PaperTrader().balance_usd == 10_000.0

    def test_custom_initial_balance(self):
        assert PaperTrader(5_000.0).balance_usd == 5_000.0

    def test_buy_deducts_cost(self):
        trader = PaperTrader()
        lot = self._make_lot(80.0, 3.0)
        trader.buy(lot)
        assert trader.balance_usd == pytest.approx(10_000.0 - 240.0)

    def test_sell_adds_proceeds(self):
        trader = PaperTrader()
        lot = self._make_lot(80.0, 3.0)
        trader.buy(lot)
        trader.sell(lot, 84.0)
        assert trader.balance_usd == pytest.approx(10_000.0 - 240.0 + 252.0)

    def test_sell_returns_correct_pnl(self):
        trader = PaperTrader()
        lot = self._make_lot(80.0, 3.0)
        trader.buy(lot)
        pnl = trader.sell(lot, 84.0)
        assert pnl == pytest.approx((84.0 - 80.0) * 3.0)

    def test_sell_records_reason(self):
        trader = PaperTrader()
        lot = self._make_lot()
        trader.buy(lot)
        trader.sell(lot, 84.0, reason="TRAIL_STOP_HIT")
        assert trader.trades[-1]["reason"] == "TRAIL_STOP_HIT"

    def test_trades_list_records_both_actions(self):
        trader = PaperTrader()
        lot = self._make_lot()
        trader.buy(lot)
        trader.sell(lot, 84.0)
        assert len(trader.trades) == 2
        assert trader.trades[0]["action"] == "BUY"
        assert trader.trades[1]["action"] == "SELL"

    def test_negative_pnl_on_losing_sell(self):
        trader = PaperTrader()
        lot = self._make_lot(80.0, 3.0)
        trader.buy(lot)
        pnl = trader.sell(lot, 78.0)
        assert pnl < 0


# ── BearishGuard engine integration ──────────────────────────────────────────

class TestBearishGuardEngine:
    def test_buy_blocked_by_bearish_guard(self):
        # min_bearish=2: price at 76.5 < midpoint(81.5) + MACD not ready(not bullish) = 2 signals
        # → PAUSE_BUYS → BUY suppressed even though dip_pct met
        engine, _ = make_engine(min_bearish=2)
        run(engine.on_candle(make_candle(82.0)))   # rolling high
        run(engine.on_candle(make_candle(76.5)))   # -6.7% dip → BUY signal generated, blocked
        assert len(engine.trader.trades) == 0
        assert len(engine.dip_buy.open_lots) == 0

    def test_buy_proceeds_when_bearish_guard_inactive(self):
        # min_bearish=3 (default): only 2 signals (MACD not ready + price below midpoint) → NORMAL
        engine, _ = make_engine(min_bearish=3)
        run(engine.on_candle(make_candle(82.0)))
        run(engine.on_candle(make_candle(76.5)))   # 2 signals < 3 → NORMAL → buy proceeds
        assert any(t["action"] == "BUY" for t in engine.trader.trades)

    def test_buy_blocked_by_drawdown_limit(self):
        # Portfolio down >10% → buy blocked regardless of bearish state
        engine, _ = make_engine(min_bearish=3)
        engine.trader.balance_usd = 8_999.0   # (10000-8999)/10000 = 10.01% > 10% limit
        run(engine.on_candle(make_candle(82.0)))
        run(engine.on_candle(make_candle(76.5)))   # would be BUY signal → blocked
        assert len(engine.trader.trades) == 0

    def test_bearish_exit_closes_losing_lot(self):
        # Lot at entry=85.0, price drops to 78.2 (8% loss > 7% threshold).
        # Price within range (78.2 > 76.44 lower buffer), 2 bearish signals (MACD + price) → PAUSE_BUYS.
        engine, _ = make_engine(min_bearish=2, max_lot_loss_pct=0.07)
        lot = Lot(id="lot_test", entry_price=85.0, quantity=250.0 / 85.0,
                  entry_time=TS, reference_price=85.0)
        engine.dip_buy.open_lots.append(lot)
        engine.trader.buy(lot)
        run(engine.on_candle(make_candle(78.2)))   # 8% loss, bearish, within range
        assert len(engine.dip_buy.open_lots) == 0
        assert any(t.get("reason") == "BEARISH_EXIT" for t in engine.trader.trades)

    def test_bearish_guard_does_not_exit_lot_with_small_loss(self):
        # Same setup but price=81.0 (4.7% loss < 7% threshold) → lot stays open
        engine, _ = make_engine(min_bearish=2, max_lot_loss_pct=0.07)
        lot = Lot(id="lot_test", entry_price=85.0, quantity=250.0 / 85.0,
                  entry_time=TS, reference_price=85.0)
        engine.dip_buy.open_lots.append(lot)
        engine.trader.buy(lot)
        run(engine.on_candle(make_candle(81.0)))   # 4.7% loss, bearish active, but below threshold
        assert len(engine.dip_buy.open_lots) == 1


# ── Hard stop ─────────────────────────────────────────────────────────────────

class TestHardStop:
    def _open_lot(self, engine: StrategyEngine, entry: float) -> Lot:
        lot = Lot(id="lot_hs", entry_price=entry, quantity=250.0 / entry,
                  entry_time=TS, reference_price=entry)
        engine.dip_buy.open_lots.append(lot)
        engine.trader.buy(lot)
        return lot

    def test_hard_stop_closes_lot_at_threshold(self):
        # entry=82, hard_stop=10%, stop fires at <=73.8
        engine, _ = make_engine(hard_stop_pct=0.10)
        self._open_lot(engine, 82.0)
        run(engine.on_candle(make_candle(73.0)))   # 11% loss → HARD_STOP
        assert len(engine.dip_buy.open_lots) == 0
        assert any(t.get("reason") == "HARD_STOP" for t in engine.trader.trades)

    def test_hard_stop_does_not_fire_below_threshold(self):
        engine, _ = make_engine(hard_stop_pct=0.10)
        self._open_lot(engine, 82.0)
        run(engine.on_candle(make_candle(75.0)))   # 8.5% loss < 10% threshold → lot stays
        assert len(engine.dip_buy.open_lots) == 1
        assert not any(t.get("reason") == "HARD_STOP" for t in engine.trader.trades)

    def test_hard_stop_fires_regardless_of_bearish_guard_state(self):
        # min_bearish=99 so bearish guard never activates; hard stop still must fire
        engine, _ = make_engine(hard_stop_pct=0.10, min_bearish=99)
        self._open_lot(engine, 82.0)
        run(engine.on_candle(make_candle(73.0)))   # bearish guard inactive, hard stop still fires
        assert len(engine.dip_buy.open_lots) == 0

    def test_hard_stop_records_negative_pnl(self):
        engine, _ = make_engine(hard_stop_pct=0.10)
        self._open_lot(engine, 82.0)
        run(engine.on_candle(make_candle(73.0)))
        sell = next(t for t in engine.trader.trades if t.get("reason") == "HARD_STOP")
        assert sell["pnl_usd"] < 0

    def test_hard_stop_sends_alert(self):
        engine, alert = make_engine(hard_stop_pct=0.10)
        self._open_lot(engine, 82.0)
        run(engine.on_candle(make_candle(73.0)))
        assert any("HARD_STOP" in str(c) for c in alert.send.call_args_list)

    def test_hard_stop_disabled_when_pct_is_one(self):
        # Default hard_stop_pct=1.0 means 100% loss required — effectively disabled
        engine, _ = make_engine(hard_stop_pct=1.0)
        self._open_lot(engine, 82.0)
        run(engine.on_candle(make_candle(1.0)))   # 98.8% loss, but 1.0 threshold not reached (loss=0.988 < 1.0)
        # Still fires because (1-82)/82 = -0.988 which IS <= -1.0? No: 0.988 < 1.0 → NOT fired
        assert not any(t.get("reason") == "HARD_STOP" for t in engine.trader.trades)


# ── Trend filter ──────────────────────────────────────────────────────────────

class TestTrendFilter:
    def _make_declining_ema(self, period: int = 3) -> EMA:
        """Return an EMA that is declining with price below it."""
        ema = EMA(period=period)
        for price in [100.0, 99.0, 98.0, 97.0, 96.0]:
            ema.update(price)
        # After [100,99,98,97,96] with k=0.5: EMA≈96.94, rising=False, price(96) < EMA
        return ema

    def test_buy_blocked_when_price_below_declining_ema(self):
        ema = self._make_declining_ema()
        engine, _ = make_engine(min_bearish=99, trend_ema=ema)  # bearish guard off
        # Set rolling high to 100 so a 5% dip at 95 fires; EMA≈96.9 > 95 and still declining
        engine.dip_buy._rolling_high = 100.0
        run(engine.on_candle(make_candle(95.0)))   # 5% dip, but trend filter blocks
        assert len(engine.trader.trades) == 0
        assert len(engine.dip_buy.open_lots) == 0

    def test_buy_allowed_when_price_above_rising_ema(self):
        ema = EMA(period=3)
        for price in [80.0, 81.0, 82.0, 83.0, 84.0]:
            ema.update(price)
        # EMA is rising, price (84) above EMA → trend filter inactive
        engine, _ = make_engine(min_bearish=99, trend_ema=ema)
        engine.dip_buy._rolling_high = 88.5   # set so 84 = 5% dip from 88.5
        run(engine.on_candle(make_candle(84.0)))
        assert any(t["action"] == "BUY" for t in engine.trader.trades)

    def test_buy_allowed_when_price_above_ema(self):
        # EMA(3) settled ~79 (declining from [82,80,79,78]); price=80.75 > EMA=79 → filter inactive
        # k=0.5: update(82)=82, update(80)=81, update(79)=80, update(78)=79
        ema = EMA(period=3)
        for price in [82.0, 80.0, 79.0, 78.0]:
            ema.update(price)
        # EMA≈79, declining; rolling_high=85 → 5% dip at 80.75 which is > EMA=79 → no block
        engine, _ = make_engine(min_bearish=99, trend_ema=ema)
        engine.dip_buy._rolling_high = 85.0   # 5% dip lands at 80.75 (within range $76.44–$86.7)
        run(engine.on_candle(make_candle(80.75)))
        assert any(t["action"] == "BUY" for t in engine.trader.trades)

    def test_no_filter_when_trend_ema_is_none(self):
        engine, _ = make_engine(min_bearish=99, trend_ema=None)
        run(engine.on_candle(make_candle(81.0)))   # rolling high = 81
        run(engine.on_candle(make_candle(76.5)))   # 5.6% dip → BUY proceeds
        assert any(t["action"] == "BUY" for t in engine.trader.trades)


# ── Pending dip retry after gate clears ──────────────────────────────────────

class TestPendingDipRetry:
    def test_buy_retries_after_bearish_guard_clears(self):
        # min_bearish=2: price below midpoint(81.5) + MACD not ready = 2 signals → PAUSE_BUYS
        engine, _ = make_engine(min_bearish=2)
        run(engine.on_candle(make_candle(82.0)))   # rolling high = 82
        run(engine.on_candle(make_candle(76.5)))   # 6.7% dip → BUY generated, blocked by bearish
        assert len(engine.trader.trades) == 0
        # pending_dip_high should be set, allowing retry
        assert engine.dip_buy._pending_dip_high is not None

        # Now feed a candle where bearish guard won't fire (price above midpoint)
        # min_bearish=2 needs 2 signals; at 82.0 only MACD(not ready)=1 signal → NORMAL
        run(engine.on_candle(make_candle(78.0)))   # still 4.9% below pending high of 82
        # With DIP_PCT=0.05: drop = (82-78)/82 = 4.9% < 5% → no buy from pending
        # Actually at 78.0: price < midpoint(81.5) → 2 signals → still bearish
        # Use price above midpoint to clear bearish
        run(engine.on_candle(make_candle(82.0)))   # above midpoint, only 1 signal → NORMAL
        # But 82 >= pending_dip_high(82) → pending cleared. Let's use a different setup.

        # Reset and use a cleaner scenario
        engine, _ = make_engine(min_bearish=2)
        run(engine.on_candle(make_candle(84.0)))   # rolling high = 84
        run(engine.on_candle(make_candle(78.0)))   # 7.1% dip, price<midpoint + MACD = 2 → blocked
        assert len(engine.trader.trades) == 0
        assert engine.dip_buy._pending_dip_high is not None

        # Price at 80.0: above midpoint(81.5)? No, 80<81.5. Still 2 signals.
        # Need min_bearish=3 for the retry candle so bearish doesn't fire.
        engine, _ = make_engine(min_bearish=2)
        # Warm up rolling high above range so dip lands inside range
        run(engine.on_candle(make_candle(84.0)))   # rolling high
        # Force bearish by going below midpoint with enough signals
        run(engine.on_candle(make_candle(78.0)))   # 7.1% dip, blocked by bearish (2 signals)
        assert len(engine.trader.trades) == 0
        # Now increase min_bearish threshold to simulate guard clearing
        engine.bearish_guard.min_bearish = 99      # effectively disable bearish guard
        run(engine.on_candle(make_candle(79.5)))   # effective_high=84, drop=5.4% ≥ 5% → BUY
        assert any(t["action"] == "BUY" for t in engine.trader.trades)
