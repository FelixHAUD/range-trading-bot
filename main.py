import asyncio

import config
from feeds.normalizer import NormalizedCandle
from feeds.binance import BinanceNormalizer
from feeds.coinbase import CoinbaseNormalizer
from feeds.manager import PriceFeedManager
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy
from strategy.hold_extension import HoldExtension
from strategy.engine import StrategyEngine
from execution.paper_trader import PaperTrader
from alerts.telegram import TelegramAlert


async def main():
    # ── Alerts ────────────────────────────────────────────────────────────────
    alert = TelegramAlert(
        token=config.TELEGRAM_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
    )

    # ── Trader ────────────────────────────────────────────────────────────────
    trader = PaperTrader()  # PAPER_TRADE = True; swap for OrderRouter to go live

    # ── Strategy components ───────────────────────────────────────────────────
    engine = StrategyEngine(
        guard=BreakoutGuard(
            buffer_pct=config.RANGE_BUFFER_PCT,
            confirm_candles=config.BREAKOUT_CONFIRM_CANDLES,
        ),
        dip_buy=DipBuyStrategy(
            dip_pct=config.DIP_PCT,
            target_pct=config.TARGET_PCT,
            max_lots=config.MAX_LOTS,
            lot_size_usd=config.LOT_SIZE_USD,
        ),
        hold_ext=HoldExtension(
            trail_pct=config.TRAIL_PCT,
            min_bullish=config.MIN_BULLISH_SIGNALS,
        ),
        rsi=RSI(),
        macd=MACD(),
        adx=ADX(),
        volume=VolumeTracker(),
        trader=trader,
        alert=alert,
        support=config.RANGE_SUPPORT,
        resistance=config.RANGE_RESISTANCE,
    )

    # ── Price feeds ───────────────────────────────────────────────────────────
    feed_manager = PriceFeedManager()
    feed_manager.add_exchange(BinanceNormalizer())
    feed_manager.add_exchange(CoinbaseNormalizer(interval=config.INTERVAL))
    feed_manager.subscribe(engine.on_candle)

    mode = "PAPER" if config.PAPER_TRADE else "LIVE"
    print(f"[main] Starting {mode} trading — {config.SYMBOL} @ {config.INTERVAL}")
    print(f"[main] Range: ${config.RANGE_SUPPORT} – ${config.RANGE_RESISTANCE}")
    print(f"[main] Initial balance: ${trader.balance_usd:,.2f}")

    await feed_manager.start(config.SYMBOL, config.INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
