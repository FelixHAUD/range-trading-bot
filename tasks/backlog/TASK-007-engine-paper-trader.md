---
id: TASK-007
title: "strategy: StrategyEngine + execution: PaperTrader"
branch: feature/engine-paper
status: backlog
depends_on: [TASK-003, TASK-004, TASK-005, TASK-006]
files:
  - strategy/engine.py
  - execution/paper_trader.py
  - execution/order_router.py
  - tests/test_engine.py
---

## Goal
Wire all strategy modules together in `StrategyEngine`. On each closed candle:
update indicators → check breakout guard → run dip-buy → evaluate hold extension.
`PaperTrader` simulates order execution without real funds.
`OrderRouter` is a thin ccxt wrapper (credentials from env only).

## Acceptance criteria
- [ ] All unit tests pass
- [ ] `on_candle()` skips non-closed candles silently
- [ ] BreakoutGuard checked before any other strategy logic
- [ ] BUY → PaperTrader.buy() → alert
- [ ] SELL_CHECK → HoldExtension.evaluate() → SELL or TRAIL_STOP_HIT → PaperTrader.sell() → close_lot() → alert
- [ ] HOLD path logs state but does not sell
- [ ] PaperTrader balance_usd decreases on buy, increases on sell
- [ ] OrderRouter reads credentials from os.getenv() — never hardcoded

## Implementation notes
From ARCHITECTURE.md §strategy/engine.py and execution/:
Engine instantiates all components from config.
`on_candle` is the single entry point — async.
PaperTrader starts with `balance_usd = 10_000.0`.
OrderRouter uses `ccxt.async_support as ccxt`.
Tests should use a mock/stub for TelegramAlert and PaperTrader to avoid
real network calls; feed synthetic closed NormalizedCandles.
