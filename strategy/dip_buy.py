from dataclasses import dataclass
from typing import List
import time


@dataclass
class Lot:
    id: str
    entry_price: float
    quantity: float
    entry_time: int
    reference_price: float   # rolling high at time of buy


class DipBuyStrategy:
    def __init__(
        self,
        dip_pct: float,
        target_pct: float,
        max_lots: int,
        lot_size_usd: float,
        rolling_high_candles: int = 20,
    ):
        self.dip_pct = dip_pct
        self.target_pct = target_pct
        self.max_lots = max_lots
        self.lot_size_usd = lot_size_usd
        self.rolling_high_candles = rolling_high_candles

        self.open_lots: List[Lot] = []
        self._rolling_high: float | None = None
        self._recent_closes: list[float] = []
        self._lot_counter: int = 0

    def on_candle(self, close: float, timestamp: int) -> list:
        """
        Process a closed candle. Returns a list of signal dicts:
          {"action": "BUY",        "lot": Lot}
          {"action": "SELL_CHECK", "lot": Lot, "gain": float}
        """
        self._recent_closes.append(close)
        if len(self._recent_closes) > self.rolling_high_candles:
            self._recent_closes.pop(0)

        rolling_high = max(self._recent_closes)
        if self._rolling_high is None:
            self._rolling_high = rolling_high

        signals = []

        # BUY signal — price dropped >= dip_pct from rolling high
        drop = (self._rolling_high - close) / self._rolling_high
        if drop >= self.dip_pct and len(self.open_lots) < self.max_lots:
            self._lot_counter += 1
            lot = Lot(
                id=f"lot_{int(time.time() * 1000)}_{self._lot_counter}",
                entry_price=close,
                quantity=self.lot_size_usd / close,
                entry_time=timestamp,
                reference_price=self._rolling_high,
            )
            self.open_lots.append(lot)
            signals.append({"action": "BUY", "lot": lot})
            self._rolling_high = close   # reset so next dip is measured from new base

        # SELL CHECK — per lot
        for lot in list(self.open_lots):
            gain = (close - lot.entry_price) / lot.entry_price
            if gain >= self.target_pct:
                signals.append({"action": "SELL_CHECK", "lot": lot, "gain": gain})

        return signals

    def close_lot(self, lot_id: str) -> None:
        self.open_lots = [lot for lot in self.open_lots if lot.id != lot_id]
