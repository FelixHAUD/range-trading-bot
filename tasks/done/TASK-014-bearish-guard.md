# TASK-014 — BearishGuard: downtrend protection

**Status:** DONE
**Branch:** `feature/bearish-guard`

## Problem
180-day backtest (Oct 2025 – Apr 2026) showed the bot accumulating 4 losing lots with 0 completed
trades during a sustained SOL downtrend. The dip-buy strategy kept buying into what appeared to be
-5% dips within the detected range, but the overall trend was down and recovery never came.

Two safeguards were missing or unenforced:
- `MAX_DRAWDOWN_PCT = 0.10` existed in config but was never checked before buying
- No signal-based mechanism to stop buying or force-exit losing lots in bearish conditions

## Solution

### New file: `strategy/bearish_guard.py`
- `BearishGuard.evaluate()` counts 4 bearish signals (RSI < 40, MACD not bullish, price < midpoint,
  ADX > 25) and returns `"PAUSE_BUYS"` when `>= min_bearish` signals fire, else `"NORMAL"`
- `BearishGuard.should_exit_lot()` returns True when a lot has lost >= `max_lot_loss_pct` from entry

### Modified: `strategy/engine.py`
- Accept `bearish_guard` and `max_drawdown_pct` parameters
- Capture `_initial_balance` at init for drawdown tracking
- RSI indicator default changed from `0.0` to `50.0` (neutral when not warmed up — avoids false bearish)
- Evaluate bearish state each candle; gate BUY signals when `PAUSE_BUYS`
- Call `dip_buy.close_lot()` when skipping a buy (lot was already added to open_lots by dip_buy)
- Post-signal bearish lot scan: force-exit open lots with deep losses via `BEARISH_EXIT`

### Modified: `config.py`
```
MIN_BEARISH_SIGNALS = 3
MAX_LOT_LOSS_PCT    = 0.07
```

### Modified: `main.py`
Wire `BearishGuard` and `max_drawdown_pct` into `StrategyEngine`.

### New file: `tests/test_bearish_guard.py`
13 tests covering `evaluate()` (9) and `should_exit_lot()` (4).

### Modified: `tests/test_engine.py`
5 new integration tests in `TestBearishGuardEngine`.

## Test result
180/180 unit tests pass.
