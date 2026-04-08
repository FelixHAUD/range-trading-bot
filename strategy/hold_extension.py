from strategy.dip_buy import Lot


class HoldExtension:
    def __init__(self, trail_pct: float, min_bullish: int):
        self.trail_pct = trail_pct
        self.min_bullish = min_bullish
        self._lot_highs: dict[str, float] = {}

    def evaluate(self, lot: Lot, price: float, indicators: dict) -> str:
        """
        Decide whether to hold, sell, or trail-stop a lot that has reached target.

        indicators dict keys:
            rsi              (float, 0–100)
            macd_bullish     (bool)
            volume_above_avg (bool)
            adx              (float)

        Returns one of: 'HOLD', 'SELL', 'TRAIL_STOP_HIT'
        """
        bullish = sum([
            indicators.get("rsi", 0) > 55,
            indicators.get("macd_bullish", False),
            indicators.get("volume_above_avg", False),
            indicators.get("adx", 0) > 25,
        ])

        if bullish < self.min_bullish:
            return "SELL"

        # Momentum confirmed — manage with trailing stop
        lid = lot.id
        self._lot_highs[lid] = max(self._lot_highs.get(lid, price), price)
        trail_stop = self._lot_highs[lid] * (1 - self.trail_pct)

        if price <= trail_stop:
            del self._lot_highs[lid]
            return "TRAIL_STOP_HIT"

        return "HOLD"
