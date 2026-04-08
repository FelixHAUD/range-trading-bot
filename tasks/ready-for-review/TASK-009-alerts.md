---
id: TASK-009
title: "alerts: TelegramAlert"
branch: feature/alerts
status: backlog
depends_on: []
files:
  - alerts/telegram.py
  - tests/test_alerts.py
---

## Goal
Implement `TelegramAlert.send()`. Posts a message to a Telegram chat via
the Bot API using aiohttp. Must never raise — swallow all exceptions.

## Acceptance criteria
- [ ] All unit tests pass
- [ ] Uses `aiohttp.ClientSession` — not `requests`
- [ ] `send()` never raises; exceptions are caught and printed
- [ ] Token and chat_id come from constructor args (sourced from config)
- [ ] Correct endpoint: `https://api.telegram.org/bot{token}/sendMessage`
- [ ] Payload includes `chat_id`, `text`, `parse_mode: "HTML"`

## Implementation notes
From ARCHITECTURE.md §alerts/telegram.py:
```python
class TelegramAlert:
    def __init__(self, token: str, chat_id: str):
        self._base = f"https://api.telegram.org/bot{token}/sendMessage"

    async def send(self, message: str):
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self._base, json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                })
        except Exception as e:
            print(f"[Alert] Failed to send Telegram message: {e}")
```
Tests: mock `aiohttp.ClientSession` to capture post calls without network.
Assert payload shape. Assert no exception propagates even when post raises.
