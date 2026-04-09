from feeds.normalizer import NormalizedCandle
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy
from strategy.hold_extension import HoldExtension
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker


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

    async def on_candle(self, candle: NormalizedCandle) -> None:
        if not candle.is_closed:
            return

        # Update all indicators first
        self.rsi.update(candle.close)
        self.macd.update(candle.close)
        self.adx.update(candle.high, candle.low, candle.close)
        self.volume.update(candle.volume)

        # Breakout guard gates everything
        if not self.guard.check(candle.close, self.support, self.resistance):
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
                    await self.alert.send(
                        f"{decision} {lot.id} @ ${candle.close:.2f} | "
                        f"PnL: ${pnl:.2f}"
                    )
                # HOLD: keep lot open, do nothing
