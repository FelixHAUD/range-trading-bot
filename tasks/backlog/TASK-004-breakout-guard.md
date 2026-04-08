---
id: TASK-004
title: "strategy: BreakoutGuard"
branch: feature/breakout-guard
status: backlog
depends_on: []
files:
  - strategy/breakout_guard.py
  - tests/test_breakout_guard.py
---

## Goal
Implement `BreakoutGuard`: watches price against support/resistance +/- a buffer.
When price exits the buffer zone the bot pauses. It resumes only after
`confirm_candles` consecutive closes back inside the zone.

## Acceptance criteria
- [ ] All unit tests pass
- [ ] `check()` returns False immediately on breakout
- [ ] `paused` flag set to True on breakout
- [ ] Counter resets on each breakout
- [ ] Resumes (`paused = False`) only after exactly N confirm candles inside range
- [ ] Returns True for normal in-range prices when not paused

## Implementation notes
From ARCHITECTURE.md §strategy/breakout_guard.py:
```python
class BreakoutGuard:
    def __init__(self, buffer_pct: float, confirm_candles: int):
        self.buffer_pct = buffer_pct
        self.confirm_candles = confirm_candles
        self.paused = False
        self._candles_inside = 0

    def check(self, price: float, support: float, resistance: float) -> bool:
        lower = support * (1 - self.buffer_pct)
        upper = resistance * (1 + self.buffer_pct)

        if price < lower or price > upper:
            self.paused = True
            self._candles_inside = 0
            return False

        if self.paused:
            self._candles_inside += 1
            if self._candles_inside >= self.confirm_candles:
                self.paused = False
            else:
                return False

        return True
```

Config values used: `RANGE_BUFFER_PCT = 0.02`, `BREAKOUT_CONFIRM_CANDLES = 3`.
Tests should pass explicit values — no config import in tests.
