---
id: TASK-005
title: "strategy: DipBuyStrategy + Lot"
branch: feature/dip-buy
status: done
depends_on: []
files:
  - strategy/dip_buy.py
  - tests/test_dip_buy.py
---

## Goal
Implement `DipBuyStrategy` with per-lot tracking. Buys when price drops ≥ dip_pct
from the rolling high; sells check fires per lot when gain ≥ target_pct.
Rolling high resets to close price after each buy.

## Acceptance criteria
- [ ] All unit tests pass
- [ ] BUY signal fired when drop >= dip_pct from rolling high
- [ ] No BUY when open_lots >= max_lots
- [ ] SELL_CHECK signal fired per lot when gain >= target_pct
- [ ] Rolling high resets to close after a buy
- [ ] `close_lot()` removes the correct lot by id
- [ ] Lot id is unique (timestamp-based)

## Implementation notes
From ARCHITECTURE.md §strategy/dip_buy.py:
```python
@dataclass
class Lot:
    id: str
    entry_price: float
    quantity: float
    entry_time: int
    reference_price: float   # rolling high at time of buy

class DipBuyStrategy:
    def on_candle(self, close: float, timestamp: int) -> list:
        # returns list of {"action": "BUY"|"SELL_CHECK", "lot": Lot, ...}
    def close_lot(self, lot_id: str): ...
```
Rolling high = `max(last rolling_high_candles closes)`.
Drop = `(rolling_high - close) / rolling_high`.
After buy: `self._rolling_high = close` (resets base).
Quantity = `lot_size_usd / close`.
