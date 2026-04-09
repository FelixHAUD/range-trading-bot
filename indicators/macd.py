class MACD:
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self._n: int = 0
        self._fast_ema: float | None = None
        self._slow_ema: float | None = None
        self._signal_ema: float | None = None
        self._prev_macd: float | None = None
        self.bullish: bool = False

    @staticmethod
    def _ema(prev: float | None, value: float, period: int) -> float:
        k = 2.0 / (period + 1)
        if prev is None:
            return value
        return value * k + prev * (1.0 - k)

    def update(self, close: float) -> None:
        self._n += 1
        self._fast_ema = self._ema(self._fast_ema, close, self.fast)
        self._slow_ema = self._ema(self._slow_ema, close, self.slow)

        if self._n < self.slow:
            return

        macd_line = self._fast_ema - self._slow_ema
        self._signal_ema = self._ema(self._signal_ema, macd_line, self.signal)

        if self._n < self.slow + self.signal:
            self._prev_macd = macd_line
            return

        prev = self._prev_macd
        self._prev_macd = macd_line

        if prev is not None:
            self.bullish = macd_line > 0 and macd_line > prev
