---
id: TASK-001
title: "feeds: normalizer, Binance, Coinbase"
branch: feature/feeds-normalizer
status: ready-for-review
depends_on: []
files:
  - feeds/normalizer.py
  - feeds/binance.py
  - feeds/coinbase.py
  - tests/test_feeds_normalizer.py
---

## Goal
Implement the data ingestion foundation: the `NormalizedCandle` dataclass, the
`ExchangeNormalizer` ABC, and two concrete adapters (Binance, Coinbase).
This is the only layer that knows about raw exchange message formats.

## Acceptance criteria
- [x] All unit tests pass (22/22)
- [x] No raw exchange data leaves feeds/
- [x] NormalizedCandle is_closed flag set correctly per exchange
- [x] No hardcoded credentials
- [x] stream_with_retry uses exponential backoff capped at 60s
- [x] Package CLAUDE.md updated with any decisions

## Implementation notes
From ARCHITECTURE.md §Layer 1:
- `NormalizedCandle` is the shared data model; all downstream modules consume it
- `ExchangeNormalizer` ABC exposes `stream()` and `stream_with_retry()`
- Binance: parses `kline` events; `is_closed = k["x"]`
- Coinbase: parses `candles` channel; always `is_closed = True` (historical candles only)
- Symbol normalisation: `SOLUSDT` → `SOL/USDT` for USDT, USDC, BTC, ETH quotes

## Test results
```
22 passed in 1.50s
```
