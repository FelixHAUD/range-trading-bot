from dataclasses import dataclass
from abc import ABC, abstractmethod
import asyncio
import json
import logging

import websockets


@dataclass
class NormalizedCandle:
    exchange: str
    symbol: str
    timestamp: int      # Unix ms, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str
    is_closed: bool     # Only run strategy logic when True


class ExchangeNormalizer(ABC):
    @abstractmethod
    def parse_message(self, raw: dict) -> NormalizedCandle | None: ...

    @abstractmethod
    def build_subscribe_msg(self, symbol: str, interval: str) -> dict: ...

    @abstractmethod
    def ws_url(self) -> str: ...

    async def stream(self, symbol: str, interval: str, callback):
        async with websockets.connect(self.ws_url()) as ws:
            await ws.send(json.dumps(self.build_subscribe_msg(symbol, interval)))
            async for raw_msg in ws:
                candle = self.parse_message(json.loads(raw_msg))
                if candle:
                    await callback(candle)

    async def stream_with_retry(self, symbol: str, interval: str, callback):
        delay = 1
        while True:
            try:
                await self.stream(symbol, interval, callback)
            except Exception as e:
                logging.getLogger("feeds").warning(
                    f"[{self.__class__.__name__}] Feed dropped: {e}. Retry in {delay}s"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
