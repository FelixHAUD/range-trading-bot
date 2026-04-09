"""
Backtest runner — replays historical SOL/USDT candles through the live strategy.

Usage:
    python backtest/runner.py                          # last 90 days
    python backtest/runner.py --days 180
    python backtest/runner.py --days 28 --interval 5m --lookback-weeks 1 --buffer-pct 0.03 --confirm-candles 1
    python backtest/runner.py --days 28 --sweep        # full 54-combination grid
"""
import argparse
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
import ccxt

# Silence all engine/strategy logging during backtest — only print() output is shown
logging.basicConfig(level=logging.ERROR)

import config
from feeds.normalizer import NormalizedCandle
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker
from strategy.bearish_guard import BearishGuard
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy
from strategy.hold_extension import HoldExtension
from strategy.range_detector import RangeDetector
from strategy.engine import StrategyEngine
from execution.paper_trader import PaperTrader


class _NoAlert:
    async def send(self, _: str) -> None:
        pass


def _candles_per_week(interval: str) -> int:
    """Convert an interval string (e.g. '5m', '15m', '1h') to candles per week."""
    if interval.endswith("m"):
        minutes = int(interval[:-1])
    elif interval.endswith("h"):
        minutes = int(interval[:-1]) * 60
    else:
        raise ValueError(f"Unsupported interval: {interval}")
    return 7 * 24 * 60 // minutes


def fetch_candles(symbol: str, interval: str, since_ms: int, until_ms: int) -> list[NormalizedCandle]:
    exchange = ccxt.binanceus()
    candles: list[NormalizedCandle] = []
    current = since_ms
    print(f"Fetching {symbol} {interval} candles from Binance.US...")

    while current < until_ms:
        ohlcv = exchange.fetch_ohlcv(symbol, interval, since=current, limit=1000)
        if not ohlcv:
            break
        for row in ohlcv:
            ts, o, h, l, c, v = row
            if ts >= until_ms:
                break
            candles.append(NormalizedCandle(
                exchange="binance",
                symbol=symbol,
                timestamp=ts,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(v),
                interval=interval,
                is_closed=True,
            ))
        last_ts = ohlcv[-1][0]
        if last_ts >= until_ms or last_ts <= current:
            break
        current = last_ts + 1

    print(f"Fetched {len(candles):,} candles.")
    return candles


async def _run(
    candles: list[NormalizedCandle],
    lookback_candles: int,
    recalc_candles: int,
    buffer_pct: float,
    confirm_candles: int,
) -> tuple[PaperTrader, StrategyEngine, int]:
    trader = PaperTrader()
    detector = RangeDetector(
        lookback_candles=lookback_candles,
        recalc_every=recalc_candles,
        initial_support=config.RANGE_SUPPORT,
        initial_resistance=config.RANGE_RESISTANCE,
    )
    engine = StrategyEngine(
        guard=BreakoutGuard(buffer_pct, confirm_candles),
        dip_buy=DipBuyStrategy(config.DIP_PCT, config.TARGET_PCT, config.MAX_LOTS, config.LOT_SIZE_USD),
        hold_ext=HoldExtension(config.TRAIL_PCT, config.MIN_BULLISH_SIGNALS),
        rsi=RSI(),
        macd=MACD(),
        adx=ADX(),
        volume=VolumeTracker(),
        trader=trader,
        alert=_NoAlert(),
        support=config.RANGE_SUPPORT,
        resistance=config.RANGE_RESISTANCE,
        bearish_guard=BearishGuard(
            min_bearish=config.MIN_BEARISH_SIGNALS,
            max_lot_loss_pct=config.MAX_LOT_LOSS_PCT,
        ),
        max_drawdown_pct=config.MAX_DRAWDOWN_PCT,
        range_detector=detector,
    )

    breakout_pauses = 0
    prev_support = engine.support
    prev_resistance = engine.resistance

    for candle in candles:
        await engine.on_candle(candle)
        if engine.guard.paused:
            breakout_pauses += 1
        if engine.support != prev_support or engine.resistance != prev_resistance:
            prev_support = engine.support
            prev_resistance = engine.resistance

    return trader, engine, breakout_pauses


def _print_report(
    trader: PaperTrader,
    engine: StrategyEngine,
    candles: list[NormalizedCandle],
    breakout_pauses: int,
    start_dt: datetime,
    end_dt: datetime,
    interval: str,
    lookback_weeks: int,
    buffer_pct: float,
    confirm_candles: int,
) -> None:
    days = (end_dt - start_dt).days
    sells = [t for t in trader.trades if t["action"] == "SELL"]

    gross_pnl = sum(t["pnl_usd"] for t in sells)
    fee_est   = sum(t["price"] * t["quantity"] * 0.001 for t in trader.trades)
    net_pnl   = gross_pnl - fee_est

    wins   = [t for t in sells if t["pnl_usd"] > 0]
    losses = [t for t in sells if t["pnl_usd"] <= 0]
    win_rate = len(wins) / len(sells) * 100 if sells else 0.0
    avg_win  = sum(t["pnl_usd"] for t in wins)  / len(wins)  if wins   else 0.0
    avg_loss = sum(t["pnl_usd"] for t in losses) / len(losses) if losses else 0.0

    best  = max(sells, key=lambda t: t["pnl_usd"], default=None)
    worst = min(sells, key=lambda t: t["pnl_usd"], default=None)

    running = 10_000.0
    peak = running
    max_dd = 0.0
    for t in trader.trades:
        if t["action"] == "BUY":
            running -= t["price"] * t["quantity"]
        else:
            running += t["price"] * t["quantity"]
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    open_lots = engine.dip_buy.open_lots
    last_close = candles[-1].close if candles else 0.0
    unrealised = sum((last_close - lot.entry_price) * lot.quantity for lot in open_lots)

    sep = "=" * 48
    print(f"\n{sep}")
    print(f"  BACKTEST: {config.SYMBOL} {interval}")
    print(sep)
    print(f"  Period       : {start_dt.strftime('%Y-%m-%d')} -> {end_dt.strftime('%Y-%m-%d')}  ({days} days)")
    print(f"  Candles      : {len(candles):,}")
    print(f"  Interval     : {interval}")
    print(f"  Lookback     : {lookback_weeks}-week")
    print(f"  Buffer       : {buffer_pct*100:.1f}%")
    print(f"  Confirm      : {confirm_candles} candle{'s' if confirm_candles != 1 else ''}")
    print(f"  Final range  : ${engine.support:.2f} to ${engine.resistance:.2f}")
    print()
    print(f"  Closed lots  : {len(sells)}")
    print(f"  Gross PnL    : ${gross_pnl:+.2f}")
    print(f"  Est. fees    : -${fee_est:.2f}  (0.1% per side)")
    print(f"  Net PnL      : ${net_pnl:+.2f}")
    if sells:
        print(f"  Win rate     : {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
        print(f"  Avg win      : ${avg_win:+.2f}")
        print(f"  Avg loss     : ${avg_loss:+.2f}")
    if best:
        print(f"  Best trade   : ${best['pnl_usd']:+.2f}  {best['lot_id']}  ({best['reason']})")
    if worst:
        print(f"  Worst trade  : ${worst['pnl_usd']:+.2f}  {worst['lot_id']}  ({worst['reason']})")
    print()
    print(f"  Max drawdown     : -${max_dd:.2f}")
    print(f"  Breakout pauses  : {breakout_pauses}")
    print(f"  Open lots at end : {len(open_lots)}  (unrealised ${unrealised:+.2f})")
    print(f"  Final balance    : ${trader.balance_usd:,.2f}")
    print(sep)


def _print_sweep_table(results: list[dict]) -> None:
    results.sort(key=lambda r: (r["net_pnl"], -r["open_lots"], -r["pauses"]), reverse=True)

    header = f"{'Rank':>4}  {'Intv':>4}  {'Look':>4}  {'Buf':>5}  {'Conf':>4}  {'Closed':>6}  {'Net PnL':>9}  {'Win%':>5}  {'Open':>4}  {'Pauses':>6}"
    sep = "-" * len(header)
    print(f"\n{'=' * len(header)}")
    print("  SWEEP RESULTS — ranked by net PnL")
    print(f"{'=' * len(header)}")
    print(header)
    print(sep)
    for i, r in enumerate(results, 1):
        print(
            f"{i:>4}  {r['interval']:>4}  {r['lookback_weeks']:>3}wk  "
            f"{r['buffer_pct']*100:>4.1f}%  {r['confirm_candles']:>4}  "
            f"{r['closed']:>6}  ${r['net_pnl']:>+8.2f}  "
            f"{r['win_rate']:>4.0f}%  {r['open_lots']:>4}  {r['pauses']:>6}"
        )
    print(sep)
    best = results[0]
    print(f"\n  Best: {best['interval']} | {best['lookback_weeks']}wk lookback | "
          f"{best['buffer_pct']*100:.1f}% buffer | {best['confirm_candles']} confirm candle(s) "
          f"-> net ${best['net_pnl']:+.2f}, {best['closed']} closed, {best['open_lots']} open")


def _parse_args():
    parser = argparse.ArgumentParser(description="Backtest the range trading strategy.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, default=90, help="Number of days to backtest (default: 90)")
    group.add_argument("--start", type=str, help="Start date YYYY-MM-DD (use with --end)")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--interval", type=str, default=None,
                        help="Candle interval e.g. 5m, 15m (default: from config)")
    parser.add_argument("--lookback-weeks", type=int, default=None,
                        help="Range detector lookback in weeks (default: from config)")
    parser.add_argument("--buffer-pct", type=float, default=None,
                        help="Breakout guard buffer %% e.g. 0.03 (default: from config)")
    parser.add_argument("--confirm-candles", type=int, default=None,
                        help="Candles inside range before resuming (default: from config)")
    parser.add_argument("--sweep", action="store_true",
                        help="Run full parameter grid and print ranked table")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if args.start:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.end else now
    else:
        end_dt = now
        start_dt = end_dt - timedelta(days=args.days)

    return start_dt, end_dt, args


if __name__ == "__main__":
    start_dt, end_dt, args = _parse_args()
    since_ms = int(start_dt.timestamp() * 1000)
    until_ms = int(end_dt.timestamp() * 1000)

    if args.sweep:
        SWEEP_INTERVALS      = ["5m", "15m"]
        SWEEP_LOOKBACK_WEEKS = [1, 2, 4]
        SWEEP_BUFFER_PCTS    = [0.02, 0.03, 0.04]
        SWEEP_CONFIRM        = [1, 2, 3]

        results = []
        for interval in SWEEP_INTERVALS:
            candles = fetch_candles(config.SYMBOL, interval, since_ms, until_ms)
            if not candles:
                print(f"No candles for {interval}, skipping.")
                continue
            cpw = _candles_per_week(interval)
            for lookback_weeks in SWEEP_LOOKBACK_WEEKS:
                for buffer_pct in SWEEP_BUFFER_PCTS:
                    for confirm_candles in SWEEP_CONFIRM:
                        lookback_candles = lookback_weeks * cpw
                        recalc_candles = max(cpw, lookback_candles // 4)
                        trader, engine, pauses = asyncio.run(
                            _run(candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles)
                        )
                        sells = [t for t in trader.trades if t["action"] == "SELL"]
                        gross = sum(t["pnl_usd"] for t in sells)
                        fees  = sum(t["price"] * t["quantity"] * 0.001 for t in trader.trades)
                        wins  = [t for t in sells if t["pnl_usd"] > 0]
                        results.append({
                            "interval": interval,
                            "lookback_weeks": lookback_weeks,
                            "buffer_pct": buffer_pct,
                            "confirm_candles": confirm_candles,
                            "closed": len(sells),
                            "net_pnl": gross - fees,
                            "win_rate": len(wins) / len(sells) * 100 if sells else 0.0,
                            "open_lots": len(engine.dip_buy.open_lots),
                            "pauses": pauses,
                        })

        _print_sweep_table(results)

    else:
        # Single run
        interval = args.interval or config.INTERVAL
        cpw = _candles_per_week(interval)

        if args.lookback_weeks is not None:
            lookback_weeks = args.lookback_weeks
            lookback_candles = lookback_weeks * cpw
            recalc_candles = max(cpw, lookback_candles // 4)
        else:
            lookback_weeks = config.RANGE_LOOKBACK_CANDLES // cpw
            lookback_candles = config.RANGE_LOOKBACK_CANDLES
            recalc_candles = config.RANGE_RECALC_CANDLES

        buffer_pct      = args.buffer_pct      if args.buffer_pct      is not None else config.RANGE_BUFFER_PCT
        confirm_candles = args.confirm_candles  if args.confirm_candles is not None else config.BREAKOUT_CONFIRM_CANDLES

        candles = fetch_candles(config.SYMBOL, interval, since_ms, until_ms)
        if not candles:
            print("No candles fetched. Check symbol, interval, and date range.")
            sys.exit(1)

        trader, engine, breakout_pauses = asyncio.run(
            _run(candles, lookback_candles, recalc_candles, buffer_pct, confirm_candles)
        )
        _print_report(
            trader, engine, candles, breakout_pauses,
            start_dt, end_dt, interval, lookback_weeks, buffer_pct, confirm_candles,
        )
