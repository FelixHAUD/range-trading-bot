"""
Unit tests for strategy/engine.py and execution/paper_trader.py.
No network — alert is mocked (AsyncMock), all strategy components are real.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock

from feeds.normalizer import NormalizedCandle
from strategy.engine import StrategyEngine
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy, Lot
from strategy.hold_extension import HoldExtension
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker
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


def make_engine(min_bullish: int = 2) -> tuple[StrategyEngine, AsyncMock]:
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
