---
id: TASK-002
title: "feeds: PriceFeedManager"
branch: feature/feeds-manager
status: done
depends_on: [TASK-001]
files:
  - feeds/manager.py
  - tests/test_feeds_manager.py
---

## Goal
Implement `PriceFeedManager`: runs multiple exchange feeds concurrently via
`asyncio.gather`, deduplicates candles, and fans out to all subscribers.

## Acceptance criteria
- [x] All unit tests pass (15/15)
- [x] Deduplication key: `f"{exchange}:{timestamp}:{interval}"`
- [x] Seen-set pruned when it exceeds 10 000 entries (keeps last 5 000)
- [x] Multiple subscribers all receive each candle
- [x] No hardcoded credentials

## Implementation notes
From ARCHITECTURE.md §feeds/manager.py:
```python
class PriceFeedManager:
    def __init__(self):
        self.normalizers = []
        self._subscribers = []
        self._seen: set[str] = set()

    def add_exchange(self, normalizer): ...
    def subscribe(self, callback): ...
    async def _on_candle(self, candle: NormalizedCandle): ...  # dedup + fan-out
    async def start(self, symbol: str, interval: str): ...     # asyncio.gather
```
Dedup: key = `exchange:timestamp:interval`; skip if already seen.
Prune: when `len(self._seen) > 10_000`, keep last 5 000.

## Test results
```
15 passed in 2.38s
```
