# REVIEW-001 — feeds: normalizer, Binance, Coinbase

**Task:** TASK-001  
**Branch:** feature/feeds-normalizer  
**Files reviewed:**
- `feeds/normalizer.py`
- `feeds/binance.py`
- `feeds/coinbase.py`
- `tests/test_feeds_normalizer.py`

## Checklist

- [x] No raw exchange data leaves `feeds/` — all parse logic is internal to each normalizer
- [x] `NormalizedCandle` is the only type exposed outward
- [x] `is_closed` flag: Binance sets from `k["x"]` (correct); Coinbase hardcodes `True` (correct — candles channel delivers completed candles)
- [x] No hardcoded credentials
- [x] `stream_with_retry` uses exponential backoff: starts at 1s, doubles, capped at 60s
- [x] Type hints throughout; `@dataclass` used; `ABC` used
- [x] No `import *`
- [x] 22 unit tests — synthetic payloads, no network
- [x] Symbol normalisation tested for USDT, BTC, ETH, and unknown quotes
- [x] Edge cases covered: wrong event type, missing channel, empty events/candles list

## Review Decision

**APPROVED**

Implementation matches ARCHITECTURE.md spec exactly. Test coverage is thorough.
One note for future reference: Coinbase `is_closed=True` is intentional because
the candles channel delivers historical closed candles, not streaming partials.
This should be documented in `feeds/CLAUDE.md`.

**Action:** Move TASK-001 to `tasks/approved/`. Awaiting human sign-off to merge.
