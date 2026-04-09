---
id: TASK-012
title: backtest: runner + dynamic RangeDetector
branch: feature/backtest-range-detector
status: done
depends_on: [TASK-007]
files:
  - strategy/range_detector.py
  - backtest/__init__.py
  - backtest/runner.py
  - config.py
  - strategy/engine.py
  - main.py
---

## Goal
Two related features:
1. `RangeDetector` — recalculates support/resistance weekly from the prior 4 weeks of
   highs/lows. Replaces the static $78/$85 config values in both backtest and live bot.
2. `backtest/runner.py` — CLI that fetches historical OHLCV via ccxt REST, replays candles
   through the live StrategyEngine, and prints a results summary.

## Acceptance criteria
- [x] All unit tests pass (range_detector=None default keeps existing tests green)
- [x] RangeDetector recalcs every RANGE_RECALC_CANDLES (672 = 1 week at 15m)
  using a RANGE_LOOKBACK_CANDLES (2688 = 4 week) rolling window
- [x] Falls back to config.RANGE_SUPPORT/RESISTANCE until first recalc fires
- [x] backtest/runner.py fetches candles from Binance.US with pagination
- [x] Report prints: PnL, win rate, avg win/loss, best/worst trade, drawdown, breakout pauses
- [x] main.py pre-fetches 4 weeks of history at startup to warm the detector
- [x] No Telegram messages sent during backtest (_NoAlert no-op)
- [x] config.py gains RANGE_LOOKBACK_CANDLES and RANGE_RECALC_CANDLES

## Implementation notes
- RangeDetector uses TYPE_CHECKING import in engine.py to avoid circular dep
- Sync ccxt used for REST fetch (no event loop needed for one-shot calls)
- logging.basicConfig(level=ERROR) in runner.py silences engine log spam during backtest

## Review decision
APPROVED — 162/162 tests pass. Backtest smoke-tested against 30 days of live data.
