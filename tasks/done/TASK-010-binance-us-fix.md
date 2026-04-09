---
id: TASK-010
title: feeds: BinanceUSNormalizer geo-block fix
branch: feature/binance-us-fix
status: done
depends_on: [TASK-001]
files:
  - feeds/binance.py
---

## Goal
Binance.com returns HTTP 451 (geo-blocked) for US users. Add `BinanceUSNormalizer`
subclass pointing at `stream.binance.us:9443` so the bot can connect from US regions.

## Acceptance criteria
- [x] All unit tests pass
- [x] No raw exchange data leaves feeds/
- [x] BinanceUSNormalizer inherits all logic from BinanceNormalizer, only overrides ws_url()
- [x] main.py updated to use BinanceUSNormalizer

## Review decision
APPROVED — minimal, targeted change. Inherits all parsing logic. Tests pass (162/162).
