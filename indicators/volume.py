from collections import deque


class VolumeTracker:
    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self._volumes: deque[float] = deque(maxlen=lookback)
        self.above_average: bool = False

    def update(self, volume: float) -> None:
        self._volumes.append(volume)
        if len(self._volumes) < 2:
            self.above_average = False
            return
        avg = sum(self._volumes) / len(self._volumes)
        self.above_average = volume > avg
