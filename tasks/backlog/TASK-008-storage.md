---
id: TASK-008
title: "storage: CandleStore + db"
branch: feature/storage
status: backlog
depends_on: [TASK-001]
files:
  - storage/db.py
  - storage/candle_store.py
  - tests/integration_storage.py
---

## Goal
Implement `CandleStore` using asyncpg. Writes closed `NormalizedCandle` records
to TimescaleDB using the schema in `storage/schema.sql`. Deduplicates via
`ON CONFLICT DO NOTHING`.

## Acceptance criteria
- [ ] `write()` ignores candles where `is_closed=False`
- [ ] Duplicate candles silently ignored (`ON CONFLICT DO NOTHING`)
- [ ] DB URL from `config.DB_URL` — never hardcoded
- [ ] Integration test: write + read back confirms round-trip fidelity
- [ ] Integration test requires local TimescaleDB (marked `integration_`)

## Implementation notes
From ARCHITECTURE.md §storage/candle_store.py:
```python
class CandleStore:
    async def connect(self): ...   # creates asyncpg pool
    async def write(self, c: NormalizedCandle): ...
```
SQL:
```sql
INSERT INTO candles (time, exchange, symbol, interval, open, high, low, close, volume)
VALUES (to_timestamp($1 / 1000.0), $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT DO NOTHING
```
`storage/db.py` can expose a thin `get_pool(db_url)` helper used by CandleStore.
Unit tests should mock the asyncpg pool; integration tests need real DB.
