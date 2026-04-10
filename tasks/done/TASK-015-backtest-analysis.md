# TASK-015 — Backtest analysis tool

**Status:** DONE
**Branch:** `main` (committed directly)

## Problem
The existing `backtest/runner.py` produces a high-level summary but lacks trade-level detail,
guard/filter diagnostics, regime breakdowns, and parameter sensitivity sweeps needed to tune
the strategy after the 5-bug fix round (rolling high ratchet, directional ADX, cancel_lot,
hard stop, trend filter).

## Solution

### New file: `backtest/analysis.py`
- `InstrumentedEngine` subclass of `StrategyEngine` that logs every trade with full metadata
  (ADX, RSI, EMA state, support/resistance, rolling high at time of trade)
- Performance scorecard: win rate, profit factor, Sharpe ratio, max drawdown, fee-adjusted net PnL
- Guard/filter statistics: breakout guard, bearish guard, trend filter candle counts;
  buy-signal blocking breakdown (executed vs blocked by bearish/trend/drawdown)
- Hold extension tracking: HOLD triggers, immediate sells, trail stop hits, extension outperformance
- Exit reason breakdown table by type (SELL, TRAIL_STOP_HIT, BEARISH_EXIT, HARD_STOP)
- Regime analysis: splits trade results by ADX regime (ranging ≤25 vs trending >25)
- Parameter sensitivity sweeps: DIP_PCT, TARGET_PCT, TRAIL_PCT, MAX_LOT_LOSS_PCT,
  HARD_STOP_PCT, TREND_EMA_PERIOD, and DIP×TARGET combo grid
- Fetches 90 days of historical candles from Binance US via ccxt

## Test result
Analysis tool — no unit tests (diagnostic/reporting script).
