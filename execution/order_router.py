import os

import ccxt.async_support as ccxt


class OrderRouter:
    def __init__(self, exchange_id: str = "binance"):
        self._exchange = getattr(ccxt, exchange_id)({
            "apiKey": os.getenv("EXCHANGE_API_KEY"),
            "secret": os.getenv("EXCHANGE_API_SECRET"),
        })

    async def buy(self, symbol: str, quantity: float) -> dict:
        return await self._exchange.create_order(
            symbol, "market", "buy", quantity
        )

    async def sell(self, symbol: str, quantity: float) -> dict:
        return await self._exchange.create_order(
            symbol, "market", "sell", quantity
        )

    async def close(self) -> None:
        await self._exchange.close()
