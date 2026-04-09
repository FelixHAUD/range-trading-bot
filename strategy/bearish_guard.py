from strategy.dip_buy import Lot


class BearishGuard:
    """
    Mirrors HoldExtension's bullish signal-counting pattern but for bearish conditions.

    Counts 4 bearish signals each candle:
      - RSI < 40             (declining momentum)
      - not macd_bullish     (MACD falling / below signal line)
      - price < range midpoint (price biased to lower half)
      - ADX > 25 AND minus_di > plus_di  (strong trend confirmed as downward by DI lines)

    When >= min_bearish signals fire:
      - evaluate() returns "PAUSE_BUYS" → engine skips new lot purchases
      - should_exit_lot() is consulted per open lot → lots losing >= max_lot_loss_pct
        are force-exited as "BEARISH_EXIT"

    When signals are insufficient, evaluate() returns "NORMAL" and trading continues.
    """

    def __init__(self, min_bearish: int, max_lot_loss_pct: float):
        self.min_bearish = min_bearish
        self.max_lot_loss_pct = max_lot_loss_pct

    def evaluate(
        self,
        price: float,
        support: float,
        resistance: float,
        indicators: dict,
    ) -> str:
        midpoint = (support + resistance) / 2.0
        adx_bearish = (
            indicators.get("adx", 0.0) > 25.0
            and indicators.get("minus_di", 0.0) > indicators.get("plus_di", 0.0)
        )
        bearish = sum([
            indicators.get("rsi", 50.0) < 40.0,
            not indicators.get("macd_bullish", True),
            price < midpoint,
            adx_bearish,
        ])
        return "PAUSE_BUYS" if bearish >= self.min_bearish else "NORMAL"

    def should_exit_lot(self, lot: Lot, price: float) -> bool:
        """True when the lot has lost >= max_lot_loss_pct from its entry price."""
        loss = (price - lot.entry_price) / lot.entry_price
        return loss <= -self.max_lot_loss_pct
