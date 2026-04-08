# Task Board — Range Trading Bot

Master status board. Individual task files live in `tasks/<status>/TASK-NNN-*.md`.

| ID | Title | Branch | Status | Depends On |
|----|-------|--------|--------|------------|
| TASK-001 | feeds: normalizer, Binance, Coinbase | feature/feeds-normalizer | IN-REVIEW | — |
| TASK-002 | feeds: PriceFeedManager | feature/feeds-manager | BACKLOG | TASK-001 |
| TASK-003 | indicators: RSI, MACD, ADX, Volume, CandleAggregator | feature/indicators | BACKLOG | TASK-001 |
| TASK-004 | strategy: BreakoutGuard | feature/breakout-guard | IN-REVIEW | — |
| TASK-005 | strategy: DipBuyStrategy + Lot | feature/dip-buy | IN-REVIEW | — |
| TASK-006 | strategy: HoldExtension | feature/hold-extension | IN-REVIEW | TASK-005 |
| TASK-007 | strategy: StrategyEngine + execution: PaperTrader | feature/engine-paper | BACKLOG | TASK-003, TASK-004, TASK-005, TASK-006 |
| TASK-008 | storage: CandleStore + db | feature/storage | BACKLOG | TASK-001 |
| TASK-009 | alerts: TelegramAlert | feature/alerts | IN-REVIEW | — |

## Status key
- **BACKLOG** — not started
- **IN-PROGRESS** — builder working
- **READY-FOR-TEST** — tester running pytest
- **IN-REVIEW** — review file created, awaiting human sign-off
- **APPROVED** — merge agent queued
- **DONE** — merged to main, branch deleted
