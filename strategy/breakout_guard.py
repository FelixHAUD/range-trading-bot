class BreakoutGuard:
    def __init__(self, buffer_pct: float, confirm_candles: int):
        self.buffer_pct = buffer_pct
        self.confirm_candles = confirm_candles
        self.paused = False
        self._candles_inside = 0

    def check(self, price: float, support: float, resistance: float) -> bool:
        """Return True if safe to trade, False if paused due to breakout."""
        lower = support * (1 - self.buffer_pct)
        upper = resistance * (1 + self.buffer_pct)

        if price < lower or price > upper:
            self.paused = True
            self._candles_inside = 0
            return False

        if self.paused:
            self._candles_inside += 1
            if self._candles_inside >= self.confirm_candles:
                self.paused = False
            else:
                return False

        return True
