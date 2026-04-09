---
id: TASK-011
title: ops: dual console + file logging
branch: feature/live-logging
status: done
depends_on: [TASK-007, TASK-009]
files:
  - feeds/normalizer.py
  - alerts/telegram.py
  - strategy/engine.py
  - .gitignore
---

## Goal
The bot runs silently between trades. Add structured logging so every closed candle
prints a compact tick line (price, indicators, lots, balance) to console and to a
rotating log file at logs/bot.log.

## Acceptance criteria
- [x] All unit tests pass
- [x] Per-candle tick line logged at INFO on every closed candle
- [x] BUY / SELL / TRAIL_STOP_HIT / HOLD decisions logged with context
- [x] Breakout guard pause logged as WARNING
- [x] Console uses UTF-8 (Windows cp1252 safe)
- [x] File handler rotates at 10MB, keeps 5 files
- [x] websockets internal logger suppressed (PING/PONG binary frames crash cp1252)
- [x] logs/ added to .gitignore

## Review decision
APPROVED — stdlib logging only, no new deps. 162/162 tests pass.
