from .normalizer import ExchangeNormalizer, NormalizedCandle


class BinanceNormalizer(ExchangeNormalizer):
    def ws_url(self) -> str:
        return "wss://stream.binance.com:9443/ws"

    def build_subscribe_msg(self, symbol: str, interval: str) -> dict:
        stream = f"{symbol.lower().replace('/', '')}@kline_{interval}"
        return {"method": "SUBSCRIBE", "params": [stream], "id": 1}

    def parse_message(self, raw: dict) -> NormalizedCandle | None:
        if raw.get("e") != "kline":
            return None
        k = raw["k"]
        return NormalizedCandle(
            exchange="binance",
            symbol=self._norm_symbol(raw["s"]),
            timestamp=k["t"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            interval=k["i"],
            is_closed=k["x"],
        )

    def _norm_symbol(self, raw: str) -> str:
        for quote in ["USDT", "USDC", "BTC", "ETH"]:
            if raw.endswith(quote):
                return f"{raw[:-len(quote)]}/{quote}"
        return raw


class BinanceUSNormalizer(BinanceNormalizer):
    """Binance.US endpoint — use this in geo-blocked regions (e.g. United States)."""

    def ws_url(self) -> str:
        return "wss://stream.binance.us:9443/ws"
