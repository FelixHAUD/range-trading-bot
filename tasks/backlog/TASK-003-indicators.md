---
id: TASK-003
title: "indicators: RSI, MACD, ADX, Volume, CandleAggregator"
branch: feature/indicators
status: backlog
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
- [ ] All unit tests pass
- [ ] RSI value matches reference for a known OHLCV sequence
- [ ] MACD `.bullish` flag toggles correctly
- [ ] ADX `.value` is non-zero after period+1 candles
- [ ] VolumeTracker `.above_average` correct
- [ ] No side effects — pure calculation only
- [ ] Returns None / leaves `.value = None` until enough data

## Implementation notes
From ARCHITECTURE.md §Layer 2 — Indicators:

**RSI** (period=14): simple (not smoothed) avg gain / avg loss.
`.value = None` until `period + 1` closes available.
`avg_loss == 0` → `value = 100.0`.

**MACD** (fast=12, slow=26, signal=9): EMA-based.
`.bullish = True` when MACD line > 0 and greater than previous MACD.
No value until `slow + signal` closes available.

**ADX** (period=14): simplified (not smoothed).
`tr`, `+DM`, `-DM` over last N candles; DX = |+DI - -DI| / (+DI + -DI).
`.value = 0.0` until `period + 1` bars.

**VolumeTracker** (lookback=20): `deque(maxlen=20)`.
`.above_average = volume > mean(deque)`.

**CandleAggregator**: stub for 15m/1h/4h candle building — implement interface,
body can be `pass` for now (not wired into engine yet).
