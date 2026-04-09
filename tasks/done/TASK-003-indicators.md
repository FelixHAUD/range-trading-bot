---
id: TASK-003
title: "indicators: RSI, MACD, ADX, Volume, CandleAggregator"
branch: feature/indicators
status: done
depends_on: [TASK-001]
files:
  - indicators/rsi.py
  - indicators/macd.py
  - indicators/adx.py
  - indicators/volume.py
  - indicators/candles.py
  - tests/test_indicators.py
---

## Goal
Implement five stateful indicator calculators. Each accepts candle data via
`update()` and exposes its current value via `.value` (or `.bullish`,
`.above_average` for MACD/Volume). All use `collections.deque(maxlen=N)`.

## Acceptance criteria
- [x] All unit tests pass (29/29)
- [x] RSI value matches reference for known sequences (all-up→100, all-down→0, alternating→50)
- [x] MACD `.bullish` flag toggles correctly on trend changes
- [x] ADX `.value` is non-zero after period+1 candles
- [x] VolumeTracker `.above_average` correct
- [x] No side effects — pure calculation only
- [x] Returns None / leaves `.value = None` until enough data (RSI)

## Implementation notes
From ARCHITECTURE.md §Layer 2 — Indicators:

**RSI** (period=14): simple (not smoothed) avg gain / avg loss.
`.value = None` until `period + 1` closes available.
`avg_loss == 0` → `value = 100.0`.

**MACD** (fast=12, slow=26, signal=9): EMA-based (online, initialized from first close).
`.bullish = True` when MACD line > 0 and greater than previous MACD.
Not evaluated until `slow + signal` closes available.
Tests use fast=3, slow=5, signal=3 for deterministic small-N coverage.

**ADX** (period=14): simplified (not smoothed).
`tr`, `+DM`, `-DM` over last N candles; DX = |+DI - -DI| / (+DI + -DI).
`.value = 0.0` until `period + 1` bars.

**VolumeTracker** (lookback=20): `deque(maxlen=20)`.
`.above_average = volume > mean(deque)`.
`.above_average = False` on first candle (insufficient history).

**CandleAggregator**: stub — `update()` is a no-op. Not yet wired into engine.

## Test results
```
29 passed in 2.10s
```
