import asyncio

from feeds.normalizer import ExchangeNormalizer, NormalizedCandle


class PriceFeedManager:
    def __init__(self):
        self.normalizers: list[ExchangeNormalizer] = []
        self._subscribers: list = []
        self._seen: set[str] = set()

    def add_exchange(self, normalizer: ExchangeNormalizer) -> None:
        self.normalizers.append(normalizer)

    def subscribe(self, callback) -> None:
        self._subscribers.append(callback)

    async def _on_candle(self, candle: NormalizedCandle) -> None:
        key = f"{candle.exchange}:{candle.timestamp}:{candle.interval}"
        if key in self._seen:
            return
        self._seen.add(key)
        if len(self._seen) > 10_000:
            # Prune: discard oldest half, keep most recent 5 000
            self._seen = set(list(self._seen)[-5_000:])
        for callback in self._subscribers:
            await callback(candle)

    async def start(self, symbol: str, interval: str) -> None:
        await asyncio.gather(
            *(n.stream_with_retry(symbol, interval, self._on_candle)
              for n in self.normalizers)
        )
