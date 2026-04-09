from collections import deque


class ADX:
    def __init__(self, period: int = 14):
        self.period = period
        self._candles: deque[tuple[float, float, float]] = deque(maxlen=period + 1)
        self.value: float = 0.0
        self.plus_di: float = 0.0   # +DI: upward directional component
        self.minus_di: float = 0.0  # -DI: downward directional component

    def update(self, high: float, low: float, close: float) -> None:
        self._candles.append((high, low, close))
        if len(self._candles) < self.period + 1:
            return

        candles = list(self._candles)
        tr_sum = 0.0
        plus_dm_sum = 0.0
        minus_dm_sum = 0.0

        for i in range(1, len(candles)):
            h, l, c = candles[i]
            ph, pl, pc = candles[i - 1]

            tr = max(h - l, abs(h - pc), abs(l - pc))
            up_move = h - ph
            down_move = pl - l

            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

            tr_sum += tr
            plus_dm_sum += plus_dm
            minus_dm_sum += minus_dm

        if tr_sum == 0:
            self.value = 0.0
            return

        plus_di = 100.0 * plus_dm_sum / tr_sum
        minus_di = 100.0 * minus_dm_sum / tr_sum
        di_sum = plus_di + minus_di

        if di_sum == 0:
            self.value = 0.0
            return

        self.value = 100.0 * abs(plus_di - minus_di) / di_sum
        self.plus_di = plus_di
        self.minus_di = minus_di
