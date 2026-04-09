import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from feeds.normalizer import NormalizedCandle
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy
from strategy.hold_extension import HoldExtension
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker

if TYPE_CHECKING:
    from strategy.range_detector import RangeDetector


class StrategyEngine:
    def __init__(
        self,
        guard: BreakoutGuard,
        dip_buy: DipBuyStrategy,
        hold_ext: HoldExtension,
        rsi: RSI,
        macd: MACD,
        adx: ADX,
        volume: VolumeTracker,
        trader,
        alert,
        support: float,
        resistance: float,
        range_detector: "RangeDetector | None" = None,
    ):
        self.guard = guard
        self.dip_buy = dip_buy
        self.hold_ext = hold_ext
        self.rsi = rsi
        self.macd = macd
        self.adx = adx
        self.volume = volume
        self.trader = trader
        self.alert = alert
        self.support = support
        self.resistance = resistance
        self.range_detector = range_detector
        self._log = logging.getLogger("engine")

    def _log_tick(self, candle: NormalizedCandle) -> None:
        ts = datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc).strftime("%H:%M")
        rsi = f"{self.rsi.value:.1f}" if self.rsi.value is not None else "---"
        macd = "+" if self.macd.bullish else "-"
        adx = f"{self.adx.value:.1f}"
        vol = "^" if self.volume.above_average else "v"
        lots = len(self.dip_buy.open_lots)
        rolling_high = self.dip_buy._rolling_high
        high_str = f" hi:${rolling_high:.2f}" if rolling_high is not None else ""
        self._log.info(
            f"[{ts}] {candle.symbol} ${candle.close:.2f}{high_str} | "
            f"RSI:{rsi} MACD:{macd} ADX:{adx} Vol:{vol} | "
            f"Lots:{lots}/{self.dip_buy.max_lots} | Bal:${self.trader.balance_usd:,.2f}"
        )

    async def on_candle(self, candle: NormalizedCandle) -> None:
        if not candle.is_closed:
            return

        # Update all indicators first
        self.rsi.update(candle.close)
        self.macd.update(candle.close)
        self.adx.update(candle.high, candle.low, candle.close)
        self.volume.update(candle.volume)

        self._log_tick(candle)

        # Update dynamic range if detector is active
        if self.range_detector is not None:
            self.support, self.resistance = self.range_detector.update(candle)

        # Breakout guard gates everything
        if not self.guard.check(candle.close, self.support, self.resistance):
            self._log.warning(f"[GUARD] PAUSED — breakout at ${candle.close:.2f}")
            await self.alert.send(
                f"PAUSED — breakout detected at ${candle.close:.2f}"
            )
            return

        indicators = {
            "rsi": self.rsi.value if self.rsi.value is not None else 0.0,
            "macd_bullish": self.macd.bullish,
            "volume_above_avg": self.volume.above_average,
            "adx": self.adx.value,
        }

        signals = self.dip_buy.on_candle(candle.close, candle.timestamp)

        for sig in signals:
            if sig["action"] == "BUY":
                lot = sig["lot"]
                self.trader.buy(lot)
                self._log.info(
                    f">>> BUY  {lot.id} @ ${lot.entry_price:.2f} | "
                    f"{lot.quantity:.4f} SOL | dip from ${lot.reference_price:.2f}"
                )
                await self.alert.send(
                    f"BUY {lot.id} @ ${lot.entry_price:.2f} "
                    f"({lot.quantity:.4f} SOL)"
                )

            elif sig["action"] == "SELL_CHECK":
                lot = sig["lot"]
                decision = self.hold_ext.evaluate(lot, candle.close, indicators)
                if decision in ("SELL", "TRAIL_STOP_HIT"):
                    pnl = self.trader.sell(lot, candle.close, reason=decision)
                    self.dip_buy.close_lot(lot.id)
                    self._log.info(
                        f">>> {decision} {lot.id} @ ${candle.close:.2f} | "
                        f"PnL:${pnl:+.2f} | Bal:${self.trader.balance_usd:,.2f}"
                    )
                    await self.alert.send(
                        f"{decision} {lot.id} @ ${candle.close:.2f} | "
                        f"PnL: ${pnl:.2f}"
                    )
                else:
                    # HOLD: keep lot open, do nothing
                    self._log.debug(
                        f"    HOLD {lot.id} | gain target hit, extending hold"
                    )
