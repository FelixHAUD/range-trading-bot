import asyncio
import logging
import logging.handlers
import os
from datetime import datetime, timezone, timedelta

import ccxt

import config
from feeds.normalizer import NormalizedCandle
from feeds.binance import BinanceUSNormalizer
from feeds.coinbase import CoinbaseNormalizer
from feeds.manager import PriceFeedManager
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy
from strategy.hold_extension import HoldExtension
from strategy.bearish_guard import BearishGuard
from strategy.range_detector import RangeDetector
from strategy.engine import StrategyEngine
from execution.paper_trader import PaperTrader
from alerts.telegram import TelegramAlert


def _setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Suppress websockets internal protocol debug (PING/PONG frames contain raw
    # binary bytes that crash cp1252 console encoding on Windows)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    sh.stream.reconfigure(encoding="utf-8", errors="replace")

    fh = logging.handlers.RotatingFileHandler(
        "logs/bot.log", maxBytes=10_485_760, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    root.addHandler(sh)
    root.addHandler(fh)


def _warm_range_detector(detector: RangeDetector) -> None:
    """Pre-fetch historical candles via REST to seed the range detector."""
    logging.info(f"Warming range detector with {config.RANGE_LOOKBACK_CANDLES} candles of history...")
    exchange = ccxt.binanceus()
    interval_minutes = int(config.INTERVAL.rstrip("m")) if config.INTERVAL.endswith("m") else int(config.INTERVAL.rstrip("h")) * 60
    since_ms = int(
        (datetime.now(timezone.utc) - timedelta(minutes=interval_minutes * config.RANGE_LOOKBACK_CANDLES)).timestamp() * 1000
    )
    current = since_ms
    count = 0
    while count < config.RANGE_LOOKBACK_CANDLES:
        ohlcv = exchange.fetch_ohlcv(config.SYMBOL, config.INTERVAL, since=current, limit=1000)
        if not ohlcv:
            break
        for row in ohlcv:
            ts, o, h, l, c, v = row
            candle = NormalizedCandle(
                exchange="binance",
                symbol=config.SYMBOL,
                timestamp=ts,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(v),
                interval=config.INTERVAL,
                is_closed=True,
            )
            detector.update(candle)
            count += 1
        last_ts = ohlcv[-1][0]
        if last_ts <= current:
            break
        current = last_ts + 1
    logging.info(
        f"Range warmed up: support=${detector.support:.2f}  resistance=${detector.resistance:.2f}"
        f"  ({count:,} candles)"
    )


async def main():
    # ── Alerts ────────────────────────────────────────────────────────────────
    alert = TelegramAlert(
        token=config.TELEGRAM_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
    )

    # ── Trader ────────────────────────────────────────────────────────────────
    trader = PaperTrader()  # PAPER_TRADE = True; swap for OrderRouter to go live

    # ── Dynamic range detector ────────────────────────────────────────────────
    detector = RangeDetector(
        lookback_candles=config.RANGE_LOOKBACK_CANDLES,
        recalc_every=config.RANGE_RECALC_CANDLES,
        initial_support=config.RANGE_SUPPORT,
        initial_resistance=config.RANGE_RESISTANCE,
    )
    _warm_range_detector(detector)

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
        support=detector.support,
        resistance=detector.resistance,
        bearish_guard=BearishGuard(
            min_bearish=config.MIN_BEARISH_SIGNALS,
            max_lot_loss_pct=config.MAX_LOT_LOSS_PCT,
        ),
        max_drawdown_pct=config.MAX_DRAWDOWN_PCT,
        range_detector=detector,
    )

    # ── Price feeds ───────────────────────────────────────────────────────────
    feed_manager = PriceFeedManager()
    feed_manager.add_exchange(BinanceUSNormalizer())
    feed_manager.add_exchange(CoinbaseNormalizer(interval=config.INTERVAL))
    feed_manager.subscribe(engine.on_candle)

    mode = "PAPER" if config.PAPER_TRADE else "LIVE"
    logging.info(f"Starting {mode} trading — {config.SYMBOL} @ {config.INTERVAL}")
    logging.info(f"Initial range: ${detector.support:.2f} – ${detector.resistance:.2f}")
    logging.info(f"Initial balance: ${trader.balance_usd:,.2f}")

    await feed_manager.start(config.SYMBOL, config.INTERVAL)


if __name__ == "__main__":
    _setup_logging()
    asyncio.run(main())
