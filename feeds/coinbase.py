from .normalizer import ExchangeNormalizer, NormalizedCandle


class CoinbaseNormalizer(ExchangeNormalizer):
    def __init__(self, interval: str = "15m"):
        self._interval = interval

    def ws_url(self) -> str:
        return "wss://advanced-trade-ws.coinbase.com"

    def build_subscribe_msg(self, symbol: str, interval: str) -> dict:
        return {
            "type": "subscribe",
            "product_ids": [symbol.replace("/", "-")],
            "channel": "candles",
        }

    def parse_message(self, raw: dict) -> NormalizedCandle | None:
        if raw.get("channel") != "candles":
            return None
        for event in raw.get("events", []):
            for c in event.get("candles", []):
                return NormalizedCandle(
                    exchange="coinbase",
                    symbol=c["product_id"].replace("-", "/"),
                    timestamp=int(c["start"]) * 1000,
                    open=float(c["open"]),
                    high=float(c["high"]),
                    low=float(c["low"]),
                    close=float(c["close"]),
                    volume=float(c["volume"]),
                    interval=self._interval,
                    is_closed=True,
                )
        return None
