from collections import deque


class EMA:
    """
    Exponential Moving Average with direction tracking.

    Attributes:
        value   -- current EMA (None until first update)
        rising  -- True when EMA moved up from the previous candle
    """

    def __init__(self, period: int = 50):
        self.period = period
        self._k = 2.0 / (period + 1)
        self._ema: float | None = None
        self._prev_ema: float | None = None
        self.value: float | None = None
        self.rising: bool = False

    def update(self, close: float) -> None:
        if self._ema is None:
            self._ema = close
        else:
            self._prev_ema = self._ema
            self._ema = close * self._k + self._ema * (1 - self._k)
            self.rising = self._ema > self._prev_ema
        self.value = self._ema
