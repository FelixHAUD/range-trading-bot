import asyncpg

import config
from feeds.normalizer import NormalizedCandle
from storage.db import get_pool


class CandleStore:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await get_pool(config.DB_URL)

    async def write(self, c: NormalizedCandle) -> None:
        if not c.is_closed:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO candles
                    (time, exchange, symbol, interval, open, high, low, close, volume)
                VALUES
                    (to_timestamp($1 / 1000.0), $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT DO NOTHING
                """,
                c.timestamp, c.exchange, c.symbol, c.interval,
                c.open, c.high, c.low, c.close, c.volume,
            )
