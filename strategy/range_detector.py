from collections import deque

from feeds.normalizer import NormalizedCandle


class RangeDetector:
    """
    Tracks a rolling window of candle highs/lows and periodically recalculates
    support (window low) and resistance (window high).

    Falls back to initial_support / initial_resistance until the first recalc
    fires (after recalc_every candles). Subsequent recalcs fire every
    recalc_every candles using the full lookback_candles window.
    """

    def __init__(
        self,
        lookback_candles: int,
        recalc_every: int,
        initial_support: float,
        initial_resistance: float,
    ):
        self._highs: deque[float] = deque(maxlen=lookback_candles)
        self._lows: deque[float] = deque(maxlen=lookback_candles)
        self._count = 0
        self._recalc_every = recalc_every
        self.support = initial_support
        self.resistance = initial_resistance

    def update(self, candle: NormalizedCandle) -> tuple[float, float]:
        self._highs.append(candle.high)
        self._lows.append(candle.low)
        self._count += 1
        if self._count % self._recalc_every == 0 and len(self._highs) >= self._recalc_every:
            self.support = min(self._lows)
            self.resistance = max(self._highs)
        return self.support, self.resistance
