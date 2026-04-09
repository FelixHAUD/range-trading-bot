# Task Board — Range Trading Bot

Master status board. Individual task files live in `tasks/<status>/TASK-NNN-*.md`.

| ID | Title | Branch | Status | Depends On |
|----|-------|--------|--------|------------|
| TASK-001 | feeds: normalizer, Binance, Coinbase | feature/feeds-normalizer | DONE | — |
| TASK-002 | feeds: PriceFeedManager | feature/feeds-manager | DONE | TASK-001 |
| TASK-003 | indicators: RSI, MACD, ADX, Volume, CandleAggregator | feature/indicators | DONE | TASK-001 |
| TASK-004 | strategy: BreakoutGuard | feature/breakout-guard | DONE | — |
| TASK-005 | strategy: DipBuyStrategy + Lot | feature/dip-buy | DONE | — |
| TASK-006 | strategy: HoldExtension | feature/hold-extension | DONE | TASK-005 |
| TASK-007 | strategy: StrategyEngine + execution: PaperTrader | feature/engine-paper | DONE | TASK-003, TASK-004, TASK-005, TASK-006 |
| TASK-008 | storage: CandleStore + db | feature/storage | DONE | TASK-001 |
| TASK-009 | alerts: TelegramAlert | feature/alerts | DONE | — |
| TASK-010 | feeds: BinanceUSNormalizer geo-block fix | feature/binance-us-fix | DONE | TASK-001 |
| TASK-011 | ops: dual console + file logging | feature/live-logging | DONE | TASK-007, TASK-009 |
| TASK-012 | backtest: runner + dynamic RangeDetector | feature/backtest-range-detector | DONE | TASK-007 |
| TASK-013 | docs: README | feature/readme | DONE | TASK-012 |
| TASK-014 | strategy: BearishGuard downtrend protection | feature/bearish-guard | DONE | TASK-007 |

## Status key
- **BACKLOG** — not started
- **IN-PROGRESS** — builder working
- **READY-FOR-TEST** — tester running pytest
- **IN-REVIEW** — review file created, awaiting human sign-off
- **APPROVED** — merge agent queued
- **DONE** — merged to main, branch deleted
