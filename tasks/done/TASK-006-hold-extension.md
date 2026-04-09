---
id: TASK-006
title: "strategy: HoldExtension"
branch: feature/hold-extension
status: done
depends_on: [TASK-005]
files:
  - strategy/hold_extension.py
  - tests/test_hold_extension.py
---

## Goal
Implement `HoldExtension`: evaluates whether a lot that has reached its +5%
target should be sold immediately or held longer behind a trailing stop.
Returns one of three string signals: `'HOLD'`, `'SELL'`, `'TRAIL_STOP_HIT'`.

## Acceptance criteria
- [ ] All unit tests pass
- [ ] Returns `'SELL'` when bullish signal count < min_bullish
- [ ] Returns `'HOLD'` when bullish signals met and trailing stop not hit
- [ ] Returns `'TRAIL_STOP_HIT'` when price <= running_high * (1 - trail_pct)
- [ ] Running high tracks upward moves but never decreases
- [ ] Cleans up lot state on TRAIL_STOP_HIT

## Implementation notes
From ARCHITECTURE.md §strategy/hold_extension.py:
```python
class HoldExtension:
    def __init__(self, trail_pct: float, min_bullish: int):
        self._lot_highs: dict[str, float] = {}

    def evaluate(self, lot, price: float, indicators: dict) -> str:
        # indicators keys: rsi (float), macd_bullish (bool),
        #                  volume_above_avg (bool), adx (float)
        bullish = sum([
            indicators.get("rsi", 0) > 55,
            indicators.get("macd_bullish", False),
            indicators.get("volume_above_avg", False),
            indicators.get("adx", 0) > 25,
        ])
        if bullish < self.min_bullish:
            return "SELL"
        self._lot_highs[lot.id] = max(self._lot_highs.get(lot.id, price), price)
        trail_stop = self._lot_highs[lot.id] * (1 - self.trail_pct)
        if price <= trail_stop:
            del self._lot_highs[lot.id]
            return "TRAIL_STOP_HIT"
        return "HOLD"
```
Depends on `Lot` dataclass from TASK-005 (needs `lot.id`).
