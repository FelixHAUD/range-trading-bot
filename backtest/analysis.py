"""
Detailed backtest analysis — trade-level breakdown, regime analysis, parameter sweeps.
Writes results to stdout for the analyst to review.
"""
import argparse
import asyncio
import sys
import os
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
logging.basicConfig(level=logging.ERROR)

import ccxt
import config
from feeds.normalizer import NormalizedCandle
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker
from indicators.ema import EMA
from strategy.bearish_guard import BearishGuard
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy
from strategy.hold_extension import HoldExtension
from strategy.range_detector import RangeDetector
from strategy.engine import StrategyEngine
from execution.paper_trader import PaperTrader
from collections import deque
import math


def fetch_candles(symbol, interval, since_ms, until_ms):
    exchange = ccxt.binanceus()
    candles = []
    current = since_ms
    while current < until_ms:
        ohlcv = exchange.fetch_ohlcv(symbol, interval, since=current, limit=1000)
        if not ohlcv:
            break
        for row in ohlcv:
            ts, o, h, l, c, v = row
            if ts >= until_ms:
                break
            candles.append(NormalizedCandle(
                exchange="binance", symbol=symbol, timestamp=ts,
                open=float(o), high=float(h), low=float(l), close=float(c),
                volume=float(v), interval=interval, is_closed=True,
            ))
        last_ts = ohlcv[-1][0]
        if last_ts >= until_ms or last_ts <= current:
            break
        current = last_ts + 1
    return candles


def _candles_per_week(interval):
    if interval.endswith("m"):
        minutes = int(interval[:-1])
    elif interval.endswith("h"):
        minutes = int(interval[:-1]) * 60
    else:
        raise ValueError(f"Unsupported interval: {interval}")
    return 7 * 24 * 60 // minutes


class InstrumentedEngine(StrategyEngine):
    """StrategyEngine subclass that logs detailed trade metadata."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trade_log = []
        self.candle_count = 0
        self.guard_paused_candles = 0
        self.bearish_paused_candles = 0
        self.trend_filter_candles = 0
        self.hold_ext_triggers = 0
        self.hold_ext_outperformed = 0
        self.hold_ext_trail_stops = 0
        self.hold_ext_immediate_sells = 0
        self.buy_signals_generated = 0
        self.buy_signals_blocked_bearish = 0
        self.buy_signals_blocked_trend = 0
        self.buy_signals_blocked_drawdown = 0
        self.buy_signals_executed = 0
        self._adx_values = []
        self._equity_curve = []

    async def on_candle(self, candle):
        if not candle.is_closed:
            return

        self.candle_count += 1

        # Update indicators
        self.rsi.update(candle.close)
        self.macd.update(candle.close)
        self.adx.update(candle.high, candle.low, candle.close)
        self.volume.update(candle.volume)
        if self.trend_ema is not None:
            self.trend_ema.update(candle.close)

        # Track ADX
        self._adx_values.append(self.adx.value)

        # Update dynamic range
        if self.range_detector is not None:
            self.support, self.resistance = self.range_detector.update(candle)

        # Hard stop
        for lot in list(self.dip_buy.open_lots):
            loss = (candle.close - lot.entry_price) / lot.entry_price
            if loss <= -self.hard_stop_pct:
                pnl = self.trader.sell(lot, candle.close, reason="HARD_STOP")
                self.dip_buy.close_lot(lot.id)
                self.trade_log.append({
                    "candle_idx": self.candle_count,
                    "timestamp": candle.timestamp,
                    "action": "HARD_STOP",
                    "lot_id": lot.id,
                    "entry_price": lot.entry_price,
                    "exit_price": candle.close,
                    "pnl": pnl,
                    "hold_candles": 0,
                    "adx": self.adx.value,
                    "rsi": self.rsi.value,
                })

        # Breakout guard
        if not self.guard.check(candle.close, self.support, self.resistance):
            self.guard_paused_candles += 1
            self._track_equity(candle)
            return

        indicators = {
            "rsi": self.rsi.value if self.rsi.value is not None else 50.0,
            "macd_bullish": self.macd.bullish,
            "volume_above_avg": self.volume.above_average,
            "adx": self.adx.value,
            "plus_di": self.adx.plus_di,
            "minus_di": self.adx.minus_di,
        }

        # Bearish guard
        bearish_state = "NORMAL"
        if self.bearish_guard is not None:
            bearish_state = self.bearish_guard.evaluate(
                candle.close, self.support, self.resistance, indicators
            )
            if bearish_state == "PAUSE_BUYS":
                self.bearish_paused_candles += 1

        # Trend filter
        trend_bearish = (
            self.trend_ema is not None
            and self.trend_ema.value is not None
            and candle.close < self.trend_ema.value
            and not self.trend_ema.rising
        )
        if trend_bearish:
            self.trend_filter_candles += 1

        signals = self.dip_buy.on_candle(candle.close, candle.timestamp)

        for sig in signals:
            if sig["action"] == "BUY":
                lot = sig["lot"]
                self.buy_signals_generated += 1

                if bearish_state == "PAUSE_BUYS":
                    self.buy_signals_blocked_bearish += 1
                    self.dip_buy.cancel_lot(lot.id)
                    continue

                if trend_bearish:
                    self.buy_signals_blocked_trend += 1
                    self.dip_buy.cancel_lot(lot.id)
                    continue

                drawdown = (self._initial_balance - self.trader.balance_usd) / self._initial_balance
                if drawdown >= self.max_drawdown_pct:
                    self.buy_signals_blocked_drawdown += 1
                    self.dip_buy.cancel_lot(lot.id)
                    continue

                self.buy_signals_executed += 1
                self.trader.buy(lot)
                self.trade_log.append({
                    "candle_idx": self.candle_count,
                    "timestamp": candle.timestamp,
                    "action": "BUY",
                    "lot_id": lot.id,
                    "entry_price": lot.entry_price,
                    "adx": self.adx.value,
                    "rsi": self.rsi.value,
                    "ema_value": self.trend_ema.value if self.trend_ema else None,
                    "ema_rising": self.trend_ema.rising if self.trend_ema else None,
                    "support": self.support,
                    "resistance": self.resistance,
                    "rolling_high": self.dip_buy._rolling_high,
                })

            elif sig["action"] == "SELL_CHECK":
                lot = sig["lot"]
                decision = self.hold_ext.evaluate(lot, candle.close, indicators)

                if decision == "HOLD":
                    self.hold_ext_triggers += 1
                elif decision == "TRAIL_STOP_HIT":
                    self.hold_ext_trail_stops += 1
                    pnl = self.trader.sell(lot, candle.close, reason=decision)
                    self.dip_buy.close_lot(lot.id)
                    # Calculate what immediate sell would have been
                    immediate_pnl = (lot.entry_price * (1 + self.dip_buy.target_pct) - lot.entry_price) * lot.quantity
                    if pnl > immediate_pnl:
                        self.hold_ext_outperformed += 1
                    self.trade_log.append({
                        "candle_idx": self.candle_count,
                        "timestamp": candle.timestamp,
                        "action": "TRAIL_STOP_HIT",
                        "lot_id": lot.id,
                        "entry_price": lot.entry_price,
                        "exit_price": candle.close,
                        "pnl": pnl,
                        "adx": self.adx.value,
                        "rsi": self.rsi.value,
                        "immediate_pnl_would_be": immediate_pnl,
                    })
                else:  # SELL
                    self.hold_ext_immediate_sells += 1
                    pnl = self.trader.sell(lot, candle.close, reason=decision)
                    self.dip_buy.close_lot(lot.id)
                    self.trade_log.append({
                        "candle_idx": self.candle_count,
                        "timestamp": candle.timestamp,
                        "action": "SELL",
                        "lot_id": lot.id,
                        "entry_price": lot.entry_price,
                        "exit_price": candle.close,
                        "pnl": pnl,
                        "adx": self.adx.value,
                        "rsi": self.rsi.value,
                    })

        # Bearish exits
        if bearish_state == "PAUSE_BUYS" and self.bearish_guard is not None:
            for lot in list(self.dip_buy.open_lots):
                if self.bearish_guard.should_exit_lot(lot, candle.close):
                    pnl = self.trader.sell(lot, candle.close, reason="BEARISH_EXIT")
                    self.dip_buy.close_lot(lot.id)
                    self.trade_log.append({
                        "candle_idx": self.candle_count,
                        "timestamp": candle.timestamp,
                        "action": "BEARISH_EXIT",
                        "lot_id": lot.id,
                        "entry_price": lot.entry_price,
                        "exit_price": candle.close,
                        "pnl": pnl,
                        "adx": self.adx.value,
                        "rsi": self.rsi.value,
                    })

        self._track_equity(candle)

    def _track_equity(self, candle):
        # Mark-to-market equity
        unrealised = sum(
            (candle.close - lot.entry_price) * lot.quantity
            for lot in self.dip_buy.open_lots
        )
        equity = self.trader.balance_usd + unrealised + sum(
            lot.entry_price * lot.quantity for lot in self.dip_buy.open_lots
        )
        self._equity_curve.append(equity)


async def run_instrumented(candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles,
                           dip_pct=None, target_pct=None, trail_pct=None, max_lots=None,
                           lot_size_usd=None, min_bullish=None, max_lot_loss_pct=None,
                           hard_stop_pct=None, trend_ema_period=None):
    dip_pct = dip_pct or config.DIP_PCT
    target_pct = target_pct or config.TARGET_PCT
    trail_pct = trail_pct or config.TRAIL_PCT
    max_lots = max_lots or config.MAX_LOTS
    lot_size_usd = lot_size_usd or config.LOT_SIZE_USD
    min_bullish = min_bullish or config.MIN_BULLISH_SIGNALS
    max_lot_loss_pct = max_lot_loss_pct or config.MAX_LOT_LOSS_PCT
    hard_stop_pct = hard_stop_pct or config.HARD_STOP_PCT
    trend_ema_period = trend_ema_period or config.TREND_EMA_PERIOD

    warmup = candles[:min(lookback_candles, len(candles))]
    if warmup:
        initial_support = min(c.low for c in warmup)
        initial_resistance = max(c.high for c in warmup)
    else:
        initial_support = config.RANGE_SUPPORT
        initial_resistance = config.RANGE_RESISTANCE

    detector = RangeDetector(
        lookback_candles=lookback_candles,
        recalc_every=recalc_candles,
        initial_support=initial_support,
        initial_resistance=initial_resistance,
    )
    trader = PaperTrader()
    engine = InstrumentedEngine(
        guard=BreakoutGuard(buffer_pct, confirm_candles),
        dip_buy=DipBuyStrategy(dip_pct, target_pct, max_lots, lot_size_usd),
        hold_ext=HoldExtension(trail_pct, min_bullish),
        rsi=RSI(),
        macd=MACD(),
        adx=ADX(),
        volume=VolumeTracker(),
        trader=trader,
        alert=type("NoAlert", (), {"send": staticmethod(lambda _: asyncio.sleep(0))})(),
        support=initial_support,
        resistance=initial_resistance,
        bearish_guard=BearishGuard(min_bearish=config.MIN_BEARISH_SIGNALS, max_lot_loss_pct=max_lot_loss_pct),
        max_drawdown_pct=config.MAX_DRAWDOWN_PCT,
        range_detector=detector,
        trend_ema=EMA(period=trend_ema_period),
        hard_stop_pct=hard_stop_pct,
    )

    breakout_pauses = 0
    was_paused = False
    for candle in candles:
        await engine.on_candle(candle)
        if engine.guard.paused and not was_paused:
            breakout_pauses += 1
        was_paused = engine.guard.paused

    return trader, engine, breakout_pauses


def compute_metrics(trader, engine, candles, breakout_pauses):
    sells = [t for t in trader.trades if t["action"] == "SELL"]
    buys = [t for t in trader.trades if t["action"] == "BUY"]

    gross_pnl = sum(t["pnl_usd"] for t in sells)
    fee_est = sum(t["price"] * t["quantity"] * 0.001 for t in trader.trades)
    net_pnl = gross_pnl - fee_est

    wins = [t for t in sells if t["pnl_usd"] > 0]
    losses = [t for t in sells if t["pnl_usd"] <= 0]
    win_rate = len(wins) / len(sells) * 100 if sells else 0.0

    avg_win = sum(t["pnl_usd"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t["pnl_usd"] for t in losses) / len(losses) if losses else 0.0

    gross_profit = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Max drawdown from equity curve
    peak = 10000.0
    max_dd = 0.0
    max_dd_pct = 0.0
    running = 10000.0
    for t in trader.trades:
        if t["action"] == "BUY":
            running -= t["price"] * t["quantity"]
        else:
            running += t["price"] * t["quantity"]
        peak = max(peak, running)
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd / peak * 100

    # Sharpe ratio (using trade returns)
    if len(sells) > 1:
        returns = [t["pnl_usd"] / (t["price"] * t["quantity"]) for t in sells]
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = var_r ** 0.5
        # Annualize: ~25920 candles per 90 days, each trade holds avg N candles
        # Rough: trades per year = len(sells) / 90 * 365
        trades_per_year = len(sells) / 90 * 365
        sharpe = (mean_r / std_r) * (trades_per_year ** 0.5) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "total_trades": len(trader.trades),
        "buys": len(buys),
        "sells": len(sells),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "gross_pnl": gross_pnl,
        "fee_est": fee_est,
        "net_pnl": net_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_dd": max_dd,
        "max_dd_pct": max_dd_pct,
        "sharpe": sharpe,
        "breakout_pauses": breakout_pauses,
    }


def print_trade_log(engine):
    """Print every trade with full detail."""
    print("\n" + "=" * 100)
    print("  TRADE-BY-TRADE LOG")
    print("=" * 100)
    for t in engine.trade_log:
        ts = datetime.fromtimestamp(t["timestamp"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        if t["action"] == "BUY":
            print(
                f"  [{ts}] BUY  {t['lot_id']:>30s} @ ${t['entry_price']:.2f} | "
                f"RSI:{t.get('rsi', '?'):>5} ADX:{t['adx']:.1f} "
                f"EMA:{'rising' if t.get('ema_rising') else 'falling'} "
                f"Range:[${t['support']:.2f}-${t['resistance']:.2f}]"
            )
        else:
            pnl = t.get("pnl", 0)
            pnl_pct = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
            print(
                f"  [{ts}] {t['action']:15s} {t['lot_id']:>30s} @ ${t['exit_price']:.2f} "
                f"(entry ${t['entry_price']:.2f}) | PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%) "
                f"RSI:{t.get('rsi', '?'):>5} ADX:{t['adx']:.1f}"
            )


def print_guard_stats(engine, total_candles):
    print("\n" + "=" * 80)
    print("  GUARD / FILTER STATISTICS")
    print("=" * 80)
    print(f"  Total candles processed:      {total_candles:,}")
    print(f"  Breakout guard paused:        {engine.guard_paused_candles:,} candles ({engine.guard_paused_candles / total_candles * 100:.1f}%)")
    print(f"  Bearish guard active:         {engine.bearish_paused_candles:,} candles ({engine.bearish_paused_candles / total_candles * 100:.1f}%)")
    print(f"  Trend filter active:          {engine.trend_filter_candles:,} candles ({engine.trend_filter_candles / total_candles * 100:.1f}%)")
    print()
    print(f"  Buy signals generated:        {engine.buy_signals_generated}")
    print(f"    -> Executed:                {engine.buy_signals_executed}")
    print(f"    -> Blocked by bearish:      {engine.buy_signals_blocked_bearish}")
    print(f"    -> Blocked by trend filter: {engine.buy_signals_blocked_trend}")
    print(f"    -> Blocked by drawdown:     {engine.buy_signals_blocked_drawdown}")
    print()
    print(f"  Hold extension events:")
    print(f"    -> Triggered HOLD:          {engine.hold_ext_triggers}")
    print(f"    -> Immediate SELL:          {engine.hold_ext_immediate_sells}")
    print(f"    -> Trail stop hits:         {engine.hold_ext_trail_stops}")
    print(f"    -> Extensions outperformed: {engine.hold_ext_outperformed}")


def print_exit_reason_breakdown(trader):
    """Break down sells by reason."""
    sells = [t for t in trader.trades if t["action"] == "SELL"]
    reasons = {}
    for t in sells:
        r = t.get("reason", "SELL")
        if r not in reasons:
            reasons[r] = {"count": 0, "total_pnl": 0.0, "wins": 0}
        reasons[r]["count"] += 1
        reasons[r]["total_pnl"] += t["pnl_usd"]
        if t["pnl_usd"] > 0:
            reasons[r]["wins"] += 1

    print("\n" + "=" * 80)
    print("  EXIT REASON BREAKDOWN")
    print("=" * 80)
    print(f"  {'Reason':<20s} {'Count':>6s} {'Win%':>6s} {'Total PnL':>12s} {'Avg PnL':>10s}")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*12} {'-'*10}")
    for r, d in sorted(reasons.items()):
        wr = d["wins"] / d["count"] * 100 if d["count"] > 0 else 0
        avg = d["total_pnl"] / d["count"]
        print(f"  {r:<20s} {d['count']:>6d} {wr:>5.1f}% ${d['total_pnl']:>+10.2f} ${avg:>+8.2f}")


def regime_analysis(candles, engine):
    """Split results by ADX regime (ranging vs trending)."""
    print("\n" + "=" * 80)
    print("  REGIME ANALYSIS (ADX threshold = 25)")
    print("=" * 80)

    # Build ADX series aligned with candles
    adx_calc = ADX()
    adx_values = []
    for c in candles:
        adx_calc.update(c.high, c.low, c.close)
        adx_values.append(adx_calc.value)

    ranging_candles = sum(1 for v in adx_values if v <= 25)
    trending_candles = sum(1 for v in adx_values if v > 25)

    print(f"  Ranging candles (ADX <= 25): {ranging_candles:,} ({ranging_candles / len(candles) * 100:.1f}%)")
    print(f"  Trending candles (ADX > 25): {trending_candles:,} ({trending_candles / len(candles) * 100:.1f}%)")

    # Classify trades by ADX at time of exit
    sells = [t for t in engine.trade_log if t["action"] != "BUY"]
    ranging_trades = [t for t in sells if t.get("adx", 0) <= 25]
    trending_trades = [t for t in sells if t.get("adx", 0) > 25]

    for label, trades in [("RANGING (ADX<=25)", ranging_trades), ("TRENDING (ADX>25)", trending_trades)]:
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        wr = len(wins) / len(trades) * 100 if trades else 0
        print(f"\n  {label}:")
        print(f"    Trades: {len(trades)} ({len(wins)}W / {len(losses)}L)")
        print(f"    Win rate: {wr:.1f}%")
        print(f"    Total PnL: ${total_pnl:+.2f}")
        if wins:
            print(f"    Avg win: ${sum(t['pnl'] for t in wins) / len(wins):+.2f}")
        if losses:
            print(f"    Avg loss: ${sum(t['pnl'] for t in losses) / len(losses):+.2f}")


async def parameter_sweep(candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles):
    """Sweep key parameters and report impact."""
    print("\n" + "=" * 100)
    print("  PARAMETER SENSITIVITY SWEEPS")
    print("=" * 100)

    # DIP_PCT sweep
    print("\n  --- DIP_PCT sweep (current: 0.05) ---")
    print(f"  {'DIP_PCT':>8s} {'Closed':>6s} {'Net PnL':>10s} {'Win%':>6s} {'PF':>6s} {'MaxDD':>8s}")
    for dip in [0.03, 0.04, 0.05, 0.06, 0.07]:
        trader, eng, bp = await run_instrumented(
            candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles, dip_pct=dip
        )
        m = compute_metrics(trader, eng, candles, bp)
        print(f"  {dip:>8.2f} {m['sells']:>6d} ${m['net_pnl']:>+9.2f} {m['win_rate']:>5.1f}% {m['profit_factor']:>5.2f} ${m['max_dd']:>7.2f}")

    # TARGET_PCT sweep
    print("\n  --- TARGET_PCT sweep (current: 0.05) ---")
    print(f"  {'TARGET':>8s} {'Closed':>6s} {'Net PnL':>10s} {'Win%':>6s} {'PF':>6s} {'MaxDD':>8s}")
    for target in [0.03, 0.04, 0.05, 0.06, 0.07, 0.08]:
        trader, eng, bp = await run_instrumented(
            candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles, target_pct=target
        )
        m = compute_metrics(trader, eng, candles, bp)
        print(f"  {target:>8.2f} {m['sells']:>6d} ${m['net_pnl']:>+9.2f} {m['win_rate']:>5.1f}% {m['profit_factor']:>5.2f} ${m['max_dd']:>7.2f}")

    # TRAIL_PCT sweep
    print("\n  --- TRAIL_PCT sweep (current: 0.02) ---")
    print(f"  {'TRAIL':>8s} {'Closed':>6s} {'Net PnL':>10s} {'Win%':>6s} {'PF':>6s} {'MaxDD':>8s}")
    for trail in [0.010, 0.015, 0.020, 0.025, 0.030, 0.035]:
        trader, eng, bp = await run_instrumented(
            candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles, trail_pct=trail
        )
        m = compute_metrics(trader, eng, candles, bp)
        print(f"  {trail:>8.3f} {m['sells']:>6d} ${m['net_pnl']:>+9.2f} {m['win_rate']:>5.1f}% {m['profit_factor']:>5.2f} ${m['max_dd']:>7.2f}")

    # MAX_LOT_LOSS_PCT sweep (bearish exit threshold)
    print("\n  --- MAX_LOT_LOSS_PCT sweep (current: 0.05) ---")
    print(f"  {'LOSS':>8s} {'Closed':>6s} {'Net PnL':>10s} {'Win%':>6s} {'PF':>6s} {'MaxDD':>8s}")
    for loss_pct in [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10]:
        trader, eng, bp = await run_instrumented(
            candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles, max_lot_loss_pct=loss_pct
        )
        m = compute_metrics(trader, eng, candles, bp)
        print(f"  {loss_pct:>8.2f} {m['sells']:>6d} ${m['net_pnl']:>+9.2f} {m['win_rate']:>5.1f}% {m['profit_factor']:>5.2f} ${m['max_dd']:>7.2f}")

    # HARD_STOP_PCT sweep
    print("\n  --- HARD_STOP_PCT sweep (current: 0.15) ---")
    print(f"  {'HSTOP':>8s} {'Closed':>6s} {'Net PnL':>10s} {'Win%':>6s} {'PF':>6s} {'MaxDD':>8s}")
    for hs in [0.08, 0.10, 0.12, 0.15, 0.20, 0.25]:
        trader, eng, bp = await run_instrumented(
            candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles, hard_stop_pct=hs
        )
        m = compute_metrics(trader, eng, candles, bp)
        print(f"  {hs:>8.2f} {m['sells']:>6d} ${m['net_pnl']:>+9.2f} {m['win_rate']:>5.1f}% {m['profit_factor']:>5.2f} ${m['max_dd']:>7.2f}")

    # TREND_EMA_PERIOD sweep
    print("\n  --- TREND_EMA_PERIOD sweep (current: 50) ---")
    print(f"  {'EMA':>8s} {'Closed':>6s} {'Net PnL':>10s} {'Win%':>6s} {'PF':>6s} {'MaxDD':>8s}")
    for ema in [20, 30, 50, 80, 100, 150]:
        trader, eng, bp = await run_instrumented(
            candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles, trend_ema_period=ema
        )
        m = compute_metrics(trader, eng, candles, bp)
        print(f"  {ema:>8d} {m['sells']:>6d} ${m['net_pnl']:>+9.2f} {m['win_rate']:>5.1f}% {m['profit_factor']:>5.2f} ${m['max_dd']:>7.2f}")

    # DIP_PCT + TARGET_PCT combo sweep (key interaction)
    print("\n  --- DIP_PCT x TARGET_PCT combo sweep ---")
    print(f"  {'DIP':>5s} {'TGT':>5s} {'Closed':>6s} {'Net PnL':>10s} {'Win%':>6s} {'PF':>6s} {'MaxDD':>8s}")
    for dip in [0.03, 0.04, 0.05]:
        for target in [0.03, 0.04, 0.05]:
            trader, eng, bp = await run_instrumented(
                candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles,
                dip_pct=dip, target_pct=target
            )
            m = compute_metrics(trader, eng, candles, bp)
            print(f"  {dip:>5.2f} {target:>5.2f} {m['sells']:>6d} ${m['net_pnl']:>+9.2f} {m['win_rate']:>5.1f}% {m['profit_factor']:>5.2f} ${m['max_dd']:>7.2f}")


if __name__ == "__main__":
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = now - timedelta(days=90)
    since_ms = int(start_dt.timestamp() * 1000)
    until_ms = int(now.timestamp() * 1000)

    interval = config.INTERVAL
    cpw = _candles_per_week(interval)
    lookback_candles = config.RANGE_LOOKBACK_CANDLES
    recalc_candles = config.RANGE_RECALC_CANDLES
    buffer_pct = config.RANGE_BUFFER_PCT
    confirm_candles = config.BREAKOUT_CONFIRM_CANDLES

    print(f"Fetching {config.SYMBOL} {interval} candles for last 90 days...")
    candles = fetch_candles(config.SYMBOL, interval, since_ms, until_ms)
    print(f"Fetched {len(candles):,} candles.\n")

    if not candles:
        print("No candles. Exiting.")
        sys.exit(1)

    # Run instrumented backtest
    trader, engine, breakout_pauses = asyncio.run(
        run_instrumented(candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles)
    )

    # Print all analysis
    metrics = compute_metrics(trader, engine, candles, breakout_pauses)

    print("\n" + "=" * 80)
    print("  PERFORMANCE SCORECARD")
    print("=" * 80)
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k:>25s}: {v:+.4f}" if abs(v) < 1 else f"  {k:>25s}: {v:+.2f}")
        else:
            print(f"  {k:>25s}: {v}")

    print_trade_log(engine)
    print_guard_stats(engine, len(candles))
    print_exit_reason_breakdown(trader)
    regime_analysis(candles, engine)

    # Parameter sweeps
    asyncio.run(parameter_sweep(candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles))
