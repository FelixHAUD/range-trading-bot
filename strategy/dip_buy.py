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
    ):
        self.dip_pct = dip_pct
        self.target_pct = target_pct
        self.max_lots = max_lots
        self.lot_size_usd = lot_size_usd

        self.open_lots: List[Lot] = []
        self._rolling_high: float | None = None
        self._pending_dip_high: float | None = None
        self._lot_counter: int = 0

    def on_candle(self, close: float, timestamp: int) -> list:
        """
        Process a closed candle. Returns a list of signal dicts:
          {"action": "BUY",        "lot": Lot}
          {"action": "SELL_CHECK", "lot": Lot, "gain": float}
        """
        # Ratchet rolling high upward; only resets down to close after a confirmed BUY.
        self._rolling_high = max(self._rolling_high or 0.0, close)

        # Clear pending dip if price has recovered above the original high
        if self._pending_dip_high is not None and close >= self._pending_dip_high:
            self._pending_dip_high = None

        # Use the higher of rolling_high or pending_dip_high so a previously
        # blocked dip is still visible on the next candle after the gate clears.
        effective_high = self._rolling_high
        if self._pending_dip_high is not None and self._pending_dip_high > self._rolling_high:
            effective_high = self._pending_dip_high

        signals = []

        # BUY signal — price dropped >= dip_pct from effective high
        drop = (effective_high - close) / effective_high
        if drop >= self.dip_pct and len(self.open_lots) < self.max_lots:
            self._lot_counter += 1
            lot = Lot(
                id=f"lot_{int(time.time() * 1000)}_{self._lot_counter}",
                entry_price=close,
                quantity=self.lot_size_usd / close,
                entry_time=timestamp,
                reference_price=effective_high,
            )
            self.open_lots.append(lot)
            signals.append({"action": "BUY", "lot": lot})
            self._rolling_high = close
            self._pending_dip_high = None

        # SELL CHECK — per lot
        for lot in list(self.open_lots):
            gain = (close - lot.entry_price) / lot.entry_price
            if gain >= self.target_pct:
                signals.append({"action": "SELL_CHECK", "lot": lot, "gain": gain})

        return signals

    def close_lot(self, lot_id: str) -> None:
        """Remove a lot after a confirmed trade (SELL / BEARISH_EXIT / TRAIL_STOP_HIT)."""
        self.open_lots = [lot for lot in self.open_lots if lot.id != lot_id]

    def cancel_lot(self, lot_id: str) -> None:
        """Cancel a lot whose BUY was gated by the engine before execution.

        Sets _rolling_high to the entry price (prevents downward cascade) and
        stores the original high in _pending_dip_high so the next candle can
        re-attempt the buy without requiring a fresh full dip.
        """
        lot = next((l for l in self.open_lots if l.id == lot_id), None)
        if lot is not None:
            self._pending_dip_high = lot.reference_price
            self._rolling_high = lot.entry_price
        self.open_lots = [l for l in self.open_lots if l.id != lot_id]
