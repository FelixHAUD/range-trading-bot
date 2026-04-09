import aiohttp
import logging


class TelegramAlert:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._base = f"https://api.telegram.org/bot{token}/sendMessage"

    async def send(self, message: str) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self._base, json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                })
        except Exception as e:
            logging.getLogger("alerts").error(f"[Alert] Failed to send Telegram message: {e}")
