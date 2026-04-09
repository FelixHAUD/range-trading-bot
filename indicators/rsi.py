from collections import deque


class RSI:
    def __init__(self, period: int = 14):
        self.period = period
        self._closes: deque[float] = deque(maxlen=period + 1)
        self.value: float | None = None

    def update(self, close: float) -> None:
        self._closes.append(close)
        if len(self._closes) < self.period + 1:
            return

        closes = list(self._closes)
        gains: list[float] = []
        losses: list[float] = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(-diff)

        avg_gain = sum(gains) / self.period
        avg_loss = sum(losses) / self.period

        if avg_loss == 0:
            self.value = 100.0
        else:
            rs = avg_gain / avg_loss
            self.value = 100.0 - (100.0 / (1.0 + rs))
