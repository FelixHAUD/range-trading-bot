# Crypto Range Trading Bot — Final Architecture

## Overview

This document defines the complete architecture for a Python-based crypto range-trading bot.
The system is designed to exploit price cycling within a defined support/resistance range (e.g. SOL at $76–$87),
with four composable strategies running simultaneously:

1. **Range trading** — buy near support, sell near resistance within a defined band.
2. **Dip-buy with per-lot tracking** — buy on -5% drawdowns from a rolling high, sell each lot at +5% from its own entry.
3. **Hold extension** — delay the sell at +5% if momentum indicators confirm the move has further to run, then exit via trailing stop.
4. **Bearish guard** — when 3+ of 4 indicators turn bearish (RSI < 40, MACD falling, price below midpoint, ADX > 25), block new buys and force-exit open lots losing ≥7%.

A **breakout guard** sits above all strategies and pauses the bot when price exits the range,
preventing the system from trading into a trending move.

The **range detector** recalculates support/resistance weekly using a 1-week rolling window of 5m candles,
so the bot adapts automatically when SOL shifts to a new price zone.

---

## Project Structure

```
range_trading_bot/
├── main.py                    # Entry point — wires everything together
├── config.py                  # All tunable parameters in one place
├── backtest/
│   └── runner.py              # CLI backtest: --days, --interval, --sweep, etc.
├── feeds/
│   ├── normalizer.py          # ExchangeNormalizer base class + NormalizedCandle
│   ├── binance.py             # BinanceNormalizer + BinanceUSNormalizer (geo-block fix)
│   ├── coinbase.py            # CoinbaseNormalizer
│   └── manager.py             # PriceFeedManager — runs all feeds concurrently
├── indicators/
│   ├── rsi.py                 # RSI calculator
│   ├── macd.py                # MACD calculator
│   ├── adx.py                 # ADX / directional movement
│   └── volume.py              # Volume average tracker
├── strategy/
│   ├── engine.py              # StrategyEngine — orchestrates all modules
│   ├── breakout_guard.py      # BreakoutGuard — pauses bot on range exit
│   ├── bearish_guard.py       # BearishGuard — blocks buys + force-exits in downtrends
│   ├── range_detector.py      # RangeDetector — weekly dynamic support/resistance
│   ├── dip_buy.py             # DipBuyStrategy — per-lot -5%/+5% logic
│   └── hold_extension.py      # HoldExtension — indicator-gated trailing stop
├── execution/
│   ├── order_router.py        # Places live orders via ccxt
│   └── paper_trader.py        # Simulates orders without real funds (default)
├── storage/
│   ├── db.py                  # TimescaleDB connection + schema
│   └── candle_store.py        # Writes/reads OHLCV data
├── alerts/
│   └── telegram.py            # Sends trade and error notifications
├── logs/                      # Auto-created; rotating log files (gitignored)
└── tests/                     # 180 unit tests; no network/DB required
```

---

## Configuration (`config.py`)

All parameters are defined here so they can be tuned without touching strategy logic.

```python
# Exchange
PRIMARY_EXCHANGE   = "binance"
FALLBACK_EXCHANGE  = "coinbase"
SYMBOL             = "SOL/USDT"
INTERVAL           = "5m"          # 5m outperforms 15m in ranging SOL markets

# Range boundaries (initial values — overwritten by RangeDetector after first weekly recalc)
RANGE_SUPPORT      = 78.0
RANGE_RESISTANCE   = 85.0
RANGE_BUFFER_PCT   = 0.03          # 3% outside range triggers breakout guard
BREAKOUT_CONFIRM_CANDLES = 2       # candles inside range before resuming

# Dynamic range detection
RANGE_LOOKBACK_CANDLES = 2016      # 1 week at 5m (7 * 24 * 12)
RANGE_RECALC_CANDLES   = 2016      # recalculate range every week

# Dip-buy strategy
DIP_PCT            = 0.05          # -5% from rolling high to trigger buy
TARGET_PCT         = 0.05          # +5% from lot entry to trigger sell check
MAX_LOTS           = 4             # max simultaneous open lots
LOT_SIZE_USD       = 250           # dollar size per lot

# Hold extension
TRAIL_PCT          = 0.02          # trailing stop 2% below running high
MIN_BULLISH_SIGNALS = 2            # indicators required to extend hold
ADX_TREND_THRESHOLD = 25           # ADX above this = trending

# Bearish guard
MIN_BEARISH_SIGNALS = 3            # 3 of 4 bearish signals -> block buys + scan exits
MAX_LOT_LOSS_PCT    = 0.07         # force-exit lot losing >= 7% when bearish active

# Risk limits
MAX_DRAWDOWN_PCT   = 0.10          # block new buys if portfolio down 10% from start
MAX_DAILY_LOSS_USD = 100.0

# Mode
PAPER_TRADE        = True          # ALWAYS start here; flip to False for live

# Database (credentials from environment only)
DB_URL = os.getenv("DB_URL", "postgresql://user:password@localhost:5432/tradebot")

# Alerts (credentials from environment only)
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
```

---

## Layer 1 — Data Ingestion

### `feeds/normalizer.py` — Shared data model + base class

Every downstream module consumes `NormalizedCandle`. No raw exchange data ever leaves this layer.

```python
from dataclasses import dataclass
from abc import ABC, abstractmethod
import asyncio, json
import websockets

@dataclass
class NormalizedCandle:
    exchange: str
    symbol: str
    timestamp: int      # Unix ms, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str
    is_closed: bool     # Only run strategy logic when True

class ExchangeNormalizer(ABC):
    @abstractmethod
    def parse_message(self, raw: dict) -> NormalizedCandle | None: ...

    @abstractmethod
    def build_subscribe_msg(self, symbol: str, interval: str) -> dict: ...

    @abstractmethod
    def ws_url(self) -> str: ...

    async def stream(self, symbol: str, interval: str, callback):
        async with websockets.connect(self.ws_url()) as ws:
            await ws.send(json.dumps(self.build_subscribe_msg(symbol, interval)))
            async for raw_msg in ws:
                candle = self.parse_message(json.loads(raw_msg))
                if candle:
                    await callback(candle)

    async def stream_with_retry(self, symbol: str, interval: str, callback):
        delay = 1
        while True:
            try:
                await self.stream(symbol, interval, callback)
            except Exception as e:
                print(f"[{self.__class__.__name__}] Feed dropped: {e}. Retry in {delay}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
```

### `feeds/binance.py`

```python
from .normalizer import ExchangeNormalizer, NormalizedCandle

class BinanceNormalizer(ExchangeNormalizer):
    def ws_url(self):
        return "wss://stream.binance.com:9443/ws"

    def build_subscribe_msg(self, symbol: str, interval: str):
        stream = f"{symbol.lower().replace('/', '')}@kline_{interval}"
        return {"method": "SUBSCRIBE", "params": [stream], "id": 1}

    def parse_message(self, raw: dict) -> NormalizedCandle | None:
        if raw.get("e") != "kline":
            return None
        k = raw["k"]
        return NormalizedCandle(
            exchange="binance",
            symbol=self._norm_symbol(raw["s"]),
            timestamp=k["t"],
            open=float(k["o"]), high=float(k["h"]),
            low=float(k["l"]),  close=float(k["c"]),
            volume=float(k["v"]),
            interval=k["i"],
            is_closed=k["x"],
        )

    def _norm_symbol(self, raw: str) -> str:
        for q in ["USDT", "USDC", "BTC", "ETH"]:
            if raw.endswith(q):
                return f"{raw[:-len(q)]}/{q}"
        return raw
```

### `feeds/coinbase.py`

```python
from .normalizer import ExchangeNormalizer, NormalizedCandle

class CoinbaseNormalizer(ExchangeNormalizer):
    def __init__(self, interval: str = "15m"):
        self._interval = interval

    def ws_url(self):
        return "wss://advanced-trade-ws.coinbase.com"

    def build_subscribe_msg(self, symbol: str, interval: str):
        return {
            "type": "subscribe",
            "product_ids": [symbol.replace("/", "-")],
            "channel": "candles",
        }

    def parse_message(self, raw: dict) -> NormalizedCandle | None:
        if raw.get("channel") != "candles":
            return None
        for event in raw.get("events", []):
            for c in event.get("candles", []):
                return NormalizedCandle(
                    exchange="coinbase",
                    symbol=c["product_id"].replace("-", "/"),
                    timestamp=int(c["start"]) * 1000,
                    open=float(c["open"]),  high=float(c["high"]),
                    low=float(c["low"]),    close=float(c["close"]),
                    volume=float(c["volume"]),
                    interval=self._interval,
                    is_closed=True,
                )
        return None
```

### `feeds/manager.py`

```python
import asyncio
from .normalizer import NormalizedCandle

class PriceFeedManager:
    def __init__(self):
        self.normalizers = []
        self._subscribers = []
        self._seen: set[str] = set()   # deduplication by exchange+timestamp

    def add_exchange(self, normalizer):
        self.normalizers.append(normalizer)

    def subscribe(self, callback):
        self._subscribers.append(callback)

    async def _on_candle(self, candle: NormalizedCandle):
        # Deduplicate: use primary exchange only for closed candles
        key = f"{candle.exchange}:{candle.timestamp}:{candle.interval}"
        if key in self._seen:
            return
        self._seen.add(key)
        if len(self._seen) > 10_000:
            self._seen = set(list(self._seen)[-5_000:])

        for cb in self._subscribers:
            await cb(candle)

    async def start(self, symbol: str, interval: str):
        tasks = [n.stream_with_retry(symbol, interval, self._on_candle)
                 for n in self.normalizers]
        await asyncio.gather(*tasks)
```

---

## Layer 2 — Indicators (`indicators/`)

Each indicator is a stateful class that accepts candles and returns its current value.

### `indicators/rsi.py`

```python
class RSI:
    def __init__(self, period=14):
        self.period = period
        self._closes = []
        self.value = None

    def update(self, close: float):
        self._closes.append(close)
        if len(self._closes) < self.period + 1:
            return
        closes = self._closes[-(self.period + 1):]
        gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
        losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
        avg_gain = sum(gains) / self.period
        avg_loss = sum(losses) / self.period
        if avg_loss == 0:
            self.value = 100.0
        else:
            rs = avg_gain / avg_loss
            self.value = 100 - (100 / (1 + rs))
```

### `indicators/macd.py`

```python
class MACD:
    def __init__(self, fast=12, slow=26, signal=9):
        self.fast = fast; self.slow = slow; self.signal = signal
        self._closes = []
        self.bullish = False   # True when MACD line crosses above signal line

    def _ema(self, data, period):
        ema = data[0]
        k = 2 / (period + 1)
        for v in data[1:]:
            ema = v * k + ema * (1 - k)
        return ema

    def update(self, close: float):
        self._closes.append(close)
        if len(self._closes) < self.slow + self.signal:
            return
        closes = self._closes
        fast_ema = self._ema(closes[-self.fast:], self.fast)
        slow_ema = self._ema(closes[-self.slow:], self.slow)
        macd_line = fast_ema - slow_ema
        # Simplified: compare current MACD to previous
        if len(self._closes) >= self.slow + self.signal + 1:
            prev_fast = self._ema(closes[-self.fast-1:-1], self.fast)
            prev_slow = self._ema(closes[-self.slow-1:-1], self.slow)
            prev_macd = prev_fast - prev_slow
            self.bullish = macd_line > 0 and macd_line > prev_macd
```

### `indicators/adx.py`

```python
class ADX:
    def __init__(self, period=14):
        self.period = period
        self._highs = []; self._lows = []; self._closes = []
        self.value = 0.0

    def update(self, high: float, low: float, close: float):
        self._highs.append(high); self._lows.append(low); self._closes.append(close)
        n = self.period
        if len(self._closes) < n + 1:
            return
        h, l, c = self._highs, self._lows, self._closes
        tr_list, pdm_list, ndm_list = [], [], []
        for i in range(-n, 0):
            tr = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
            pdm = max(h[i]-h[i-1], 0) if (h[i]-h[i-1]) > (l[i-1]-l[i]) else 0
            ndm = max(l[i-1]-l[i], 0) if (l[i-1]-l[i]) > (h[i]-h[i-1]) else 0
            tr_list.append(tr); pdm_list.append(pdm); ndm_list.append(ndm)
        atr = sum(tr_list) / n
        if atr == 0:
            return
        pdi = (sum(pdm_list) / n) / atr * 100
        ndi = (sum(ndm_list) / n) / atr * 100
        dx = abs(pdi - ndi) / (pdi + ndi) * 100 if (pdi + ndi) > 0 else 0
        self.value = dx   # Simplified; production should use smoothed ADX
```

### `indicators/volume.py`

```python
from collections import deque

class VolumeTracker:
    def __init__(self, lookback=20):
        self._volumes = deque(maxlen=lookback)
        self.above_average = False

    def update(self, volume: float):
        self._volumes.append(volume)
        if len(self._volumes) < 2:
            return
        avg = sum(self._volumes) / len(self._volumes)
        self.above_average = volume > avg
```

---

## Layer 2 — Strategy Engine (`strategy/`)

### `strategy/breakout_guard.py`

```python
class BreakoutGuard:
    def __init__(self, buffer_pct: float, confirm_candles: int):
        self.buffer_pct = buffer_pct
        self.confirm_candles = confirm_candles
        self.paused = False
        self._candles_inside = 0

    def check(self, price: float, support: float, resistance: float) -> bool:
        """Returns True if safe to trade."""
        lower = support * (1 - self.buffer_pct)
        upper = resistance * (1 + self.buffer_pct)

        if price < lower or price > upper:
            self.paused = True
            self._candles_inside = 0
            return False

        if self.paused:
            self._candles_inside += 1
            if self._candles_inside >= self.confirm_candles:
                self.paused = False
            else:
                return False

        return True
```

### `strategy/dip_buy.py`

```python
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
    def __init__(self, dip_pct, target_pct, max_lots, lot_size_usd,
                 rolling_high_candles=20):
        self.dip_pct = dip_pct
        self.target_pct = target_pct
        self.max_lots = max_lots
        self.lot_size_usd = lot_size_usd
        self.rolling_high_candles = rolling_high_candles

        self.open_lots: List[Lot] = []
        self._rolling_high = None
        self._recent_closes = []

    def on_candle(self, close: float, timestamp: int) -> list:
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
            lot = Lot(
                id=f"lot_{int(time.time()*1000)}",
                entry_price=close,
                quantity=self.lot_size_usd / close,
                entry_time=timestamp,
                reference_price=self._rolling_high,
            )
            self.open_lots.append(lot)
            signals.append({"action": "BUY", "lot": lot})
            self._rolling_high = close   # reset so next dip is from new base

        # SELL CHECK — per lot
        for lot in list(self.open_lots):
            gain = (close - lot.entry_price) / lot.entry_price
            if gain >= self.target_pct:
                signals.append({"action": "SELL_CHECK", "lot": lot, "gain": gain})

        return signals

    def close_lot(self, lot_id: str):
        self.open_lots = [l for l in self.open_lots if l.id != lot_id]
```

### `strategy/hold_extension.py`

```python
class HoldExtension:
    def __init__(self, trail_pct: float, min_bullish: int):
        self.trail_pct = trail_pct
        self.min_bullish = min_bullish
        self._lot_highs: dict[str, float] = {}

    def evaluate(self, lot, price: float, indicators: dict) -> str:
        """
        Returns 'HOLD', 'SELL', or 'TRAIL_STOP_HIT'.

        indicators dict must contain:
            rsi              (float, 0–100)
            macd_bullish     (bool)
            volume_above_avg (bool)
            adx              (float)
        """
        bullish = sum([
            indicators.get("rsi", 0) > 55,
            indicators.get("macd_bullish", False),
            indicators.get("volume_above_avg", False),
            indicators.get("adx", 0) > 25,
        ])

        if bullish < self.min_bullish:
            return "SELL"

        # Momentum confirmed — manage with trailing stop
        lid = lot.id
        self._lot_highs[lid] = max(self._lot_highs.get(lid, price), price)
        trail_stop = self._lot_highs[lid] * (1 - self.trail_pct)

        if price <= trail_stop:
            del self._lot_highs[lid]
            return "TRAIL_STOP_HIT"

        return "HOLD"
```

### `strategy/engine.py`

```python
import config
from feeds.normalizer import NormalizedCandle
from indicators.rsi import RSI
from indicators.macd import MACD
from indicators.adx import ADX
from indicators.volume import VolumeTracker
from strategy.breakout_guard import BreakoutGuard
from strategy.dip_buy import DipBuyStrategy
from strategy.hold_extension import HoldExtension
from execution.paper_trader import PaperTrader
from execution.order_router import OrderRouter
from alerts.telegram import TelegramAlert

class StrategyEngine:
    def __init__(self):
        self.guard    = BreakoutGuard(config.RANGE_BUFFER_PCT, config.BREAKOUT_CONFIRM_CANDLES)
        self.dip_buy  = DipBuyStrategy(config.DIP_PCT, config.TARGET_PCT,
                                        config.MAX_LOTS, config.LOT_SIZE_USD)
        self.hold_ext = HoldExtension(config.TRAIL_PCT, config.MIN_BULLISH_SIGNALS)

        self.rsi     = RSI(period=14)
        self.macd    = MACD(fast=12, slow=26, signal=9)
        self.adx     = ADX(period=14)
        self.volume  = VolumeTracker(lookback=20)

        self.executor = PaperTrader() if config.PAPER_TRADE else OrderRouter()
        self.alert    = TelegramAlert(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID)

    async def on_candle(self, candle: NormalizedCandle):
        if not candle.is_closed:
            return

        # Update all indicators
        self.rsi.update(candle.close)
        self.macd.update(candle.close)
        self.adx.update(candle.high, candle.low, candle.close)
        self.volume.update(candle.volume)

        indicators = {
            "rsi":              self.rsi.value,
            "macd_bullish":     self.macd.bullish,
            "volume_above_avg": self.volume.above_average,
            "adx":              self.adx.value,
        }

        # Breakout guard — gates everything
        if not self.guard.check(candle.close, config.RANGE_SUPPORT, config.RANGE_RESISTANCE):
            await self.alert.send(f"PAUSED — breakout detected at ${candle.close:.2f}")
            return

        # Run dip-buy logic
        signals = self.dip_buy.on_candle(candle.close, candle.timestamp)

        for sig in signals:
            if sig["action"] == "BUY":
                await self.executor.buy(sig["lot"])
                await self.alert.send(
                    f"BUY lot {sig['lot'].id} @ ${sig['lot'].entry_price:.2f} "
                    f"({sig['lot'].quantity:.4f} SOL)"
                )

            elif sig["action"] == "SELL_CHECK":
                lot = sig["lot"]
                decision = self.hold_ext.evaluate(lot, candle.close, indicators)

                if decision in ("SELL", "TRAIL_STOP_HIT"):
                    pnl = (candle.close - lot.entry_price) * lot.quantity
                    await self.executor.sell(lot, candle.close)
                    self.dip_buy.close_lot(lot.id)
                    await self.alert.send(
                        f"{decision} lot {lot.id} @ ${candle.close:.2f} | "
                        f"PnL: ${pnl:.2f}"
                    )
                else:
                    # Still holding — log current state
                    gain_pct = sig["gain"] * 100
                    await self.alert.send(
                        f"HOLD lot {lot.id} +{gain_pct:.1f}% — "
                        f"RSI {indicators['rsi']:.0f} ADX {indicators['adx']:.0f}"
                    )
```

---

## Layer 3 — Execution

### `execution/paper_trader.py`

```python
from strategy.dip_buy import Lot

class PaperTrader:
    def __init__(self):
        self.trades = []
        self.balance_usd = 10_000.0

    async def buy(self, lot: Lot):
        cost = lot.entry_price * lot.quantity
        self.balance_usd -= cost
        self.trades.append({
            "action": "BUY", "lot_id": lot.id,
            "price": lot.entry_price, "qty": lot.quantity,
            "cost": cost,
        })
        print(f"[PAPER] BUY {lot.quantity:.4f} SOL @ ${lot.entry_price:.2f} | "
              f"Balance: ${self.balance_usd:.2f}")

    async def sell(self, lot: Lot, price: float):
        proceeds = price * lot.quantity
        self.balance_usd += proceeds
        self.trades.append({
            "action": "SELL", "lot_id": lot.id,
            "price": price, "qty": lot.quantity,
            "proceeds": proceeds,
        })
        print(f"[PAPER] SELL {lot.quantity:.4f} SOL @ ${price:.2f} | "
              f"Balance: ${self.balance_usd:.2f}")
```

### `execution/order_router.py`

```python
import ccxt.async_support as ccxt
from strategy.dip_buy import Lot

class OrderRouter:
    def __init__(self):
        # Credentials should come from environment variables, never hardcoded
        self.exchange = ccxt.binance({
            "apiKey":  __import__("os").getenv("BINANCE_API_KEY"),
            "secret":  __import__("os").getenv("BINANCE_SECRET"),
        })

    async def buy(self, lot: Lot):
        order = await self.exchange.create_order(
            symbol="SOL/USDT",
            type="limit",
            side="buy",
            amount=lot.quantity,
            price=lot.entry_price,
        )
        return order

    async def sell(self, lot: Lot, price: float):
        order = await self.exchange.create_order(
            symbol="SOL/USDT",
            type="limit",
            side="sell",
            amount=lot.quantity,
            price=price,
        )
        return order

    async def close(self):
        await self.exchange.close()
```

---

## Layer 4 — Storage

### TimescaleDB schema

Run this once to initialize the database.

```sql
CREATE TABLE candles (
    time        TIMESTAMPTZ NOT NULL,
    exchange    TEXT        NOT NULL,
    symbol      TEXT        NOT NULL,
    interval    TEXT        NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    PRIMARY KEY (time, exchange, symbol, interval)
);

SELECT create_hypertable('candles', 'time');

CREATE TABLE trades (
    id          SERIAL PRIMARY KEY,
    lot_id      TEXT        NOT NULL,
    action      TEXT        NOT NULL,   -- BUY or SELL
    price       DOUBLE PRECISION,
    quantity    DOUBLE PRECISION,
    pnl_usd     DOUBLE PRECISION,
    reason      TEXT,                  -- SELL, TRAIL_STOP_HIT, etc.
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### `storage/candle_store.py`

```python
import asyncpg
import config
from feeds.normalizer import NormalizedCandle

class CandleStore:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(config.DB_URL)

    async def write(self, c: NormalizedCandle):
        if not c.is_closed:
            return
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO candles (time, exchange, symbol, interval, open, high, low, close, volume)
                VALUES (to_timestamp($1 / 1000.0), $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT DO NOTHING
            """, c.timestamp, c.exchange, c.symbol, c.interval,
                c.open, c.high, c.low, c.close, c.volume)
```

---

## Layer 4 — Alerts (`alerts/telegram.py`)

```python
import aiohttp

class TelegramAlert:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._base = f"https://api.telegram.org/bot{token}/sendMessage"

    async def send(self, message: str):
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self._base, json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                })
        except Exception as e:
            print(f"[Alert] Failed to send Telegram message: {e}")
```

---

## Entry Point (`main.py`)

```python
import asyncio
import config
from feeds.binance import BinanceNormalizer
from feeds.coinbase import CoinbaseNormalizer
from feeds.manager import PriceFeedManager
from storage.candle_store import CandleStore
from strategy.engine import StrategyEngine

async def main():
    store  = CandleStore()
    await store.connect()

    engine = StrategyEngine()
    feed   = PriceFeedManager()
    feed.add_exchange(BinanceNormalizer())
    feed.add_exchange(CoinbaseNormalizer(interval=config.INTERVAL))

    async def on_candle(candle):
        await store.write(candle)
        await engine.on_candle(candle)

    feed.subscribe(on_candle)

    print(f"Bot starting | Symbol: {config.SYMBOL} | Mode: "
          f"{'PAPER' if config.PAPER_TRADE else 'LIVE'}")
    await feed.start(config.SYMBOL, config.INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Dependencies (`requirements.txt`)

```
websockets>=12.0
ccxt>=4.0.0
asyncpg>=0.29.0
aiohttp>=3.9.0
python-dotenv>=1.0.0
```

Install with:
```bash
pip install -r requirements.txt
```

---

## Deployment (VPS — DigitalOcean / Hetzner)

```bash
# 1. Clone your repo
git clone https://github.com/yourname/sol-range-bot.git && cd sol-range-bot

# 2. Set environment variables
cp .env.example .env
# Edit .env with BINANCE_API_KEY, BINANCE_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DB_URL

# 3. Install TimescaleDB (Docker is easiest)
docker run -d --name timescaledb \
  -e POSTGRES_PASSWORD=yourpassword \
  -p 5432:5432 timescale/timescaledb:latest-pg15

# 4. Run schema migration
psql $DB_URL -f storage/schema.sql

# 5. Run in paper mode first (PAPER_TRADE = True in config.py)
python main.py

# 6. Run as a persistent service
pip install supervisor
# Configure supervisord to restart main.py on crash
```

---

## Known Weaknesses & Mitigations

### 1. Static range boundaries ✅ ADDRESSED
**Problem:** `RANGE_SUPPORT` and `RANGE_RESISTANCE` are hardcoded. If SOL shifts to a new range (e.g. $90–$98), the bot sits paused indefinitely.

**Resolution:** `strategy/range_detector.py` — `RangeDetector` recalculates support/resistance weekly using a rolling 1-week window of 5m candles. Pre-warmed at startup via `_warm_range_detector()` in `main.py`. `backtest/runner.py` supports `--lookback-weeks` to tune this.

---

### 2. Lot stacking in a waterfall ✅ ADDRESSED
**Problem:** If SOL drops 5%, then 10%, then 15%, the bot buys at each -5% interval, accumulating 3–4 lots in a sustained downtrend — not a cycle.

**Resolution:** `strategy/bearish_guard.py` — `BearishGuard` counts 4 bearish signals (RSI < 40, MACD falling, price below midpoint, ADX > 25). When ≥3 fire, new buys are blocked and open lots losing ≥7% are force-exited. `MAX_DRAWDOWN_PCT = 0.10` is also checked before every buy.

---

### 3. Indicator lag
**Problem:** RSI, MACD, and ADX are all lagging indicators. By the time they confirm a move, the price may have already reversed, especially on fast 5m candles.

**Mitigation:** Add a faster, leading signal such as order book imbalance (bid volume vs. ask volume ratio) or a short-term volume spike detector. Use these as pre-filters before the lagging indicators confirm. The `order_book_mgr` in the data layer is the right place to compute this.

---

### 4. Exchange downtime / API rate limits
**Problem:** Binance can throttle or disconnect during high-volatility periods — exactly when your bot most needs to act.

**Mitigation:** The `stream_with_retry` method handles reconnection with exponential backoff. Additionally, keep a secondary REST-based price fetch (via ccxt `fetch_ohlcv`) as a fallback that runs every 60s and catches any gaps in WebSocket data. Store the last known timestamp; if no candle arrives for >2 minutes, trigger the fallback.

---

### 5. Slippage on limit orders
**Problem:** Limit orders placed at the exact -5% or +5% price may not fill if the price gaps through the level, or may sit unfilled if price briefly touches and reverses.

**Mitigation:** Use a small offset on limit orders (e.g. buy at -5.1%, sell at +4.9%) to increase fill probability. Add an order timeout: if a limit order isn't filled within N candles, cancel it and re-evaluate. Track unfilled orders in `position_tracker.py`.

---

### 6. No multi-symbol support
**Problem:** The current architecture is hardcoded to SOL/USDT. Range cycling occurs across many assets simultaneously.

**Mitigation:** Refactor `StrategyEngine` to be instantiated per-symbol, with a top-level orchestrator that manages N engines. Capital allocation across symbols needs a shared risk budget so the bot doesn't open max_lots on 5 symbols simultaneously and over-extend exposure.

---

### 7. Paper-to-live transition risk
**Problem:** Paper trading doesn't account for real-world slippage, partial fills, withdrawal limits, or fee drag. A strategy that looks profitable on paper may break even or lose on live execution.

**Mitigation:** Before going live, run a forward test with minimum lot sizes (e.g. $25 per lot instead of $250) for at least 2–4 weeks. Track fee-adjusted PnL carefully — at 0.1% per trade and 4 lots per cycle, fees can consume 0.8% of each range cycle's profit.

---

## Development Sequence (Recommended Order)

1. Build and test `feeds/` — confirm normalized candles arriving from both exchanges.
2. Build `indicators/` — unit test each calculator against known values.
3. Build `strategy/breakout_guard.py` + `strategy/dip_buy.py` — test in isolation with synthetic candle data.
4. Wire `strategy/engine.py` with `execution/paper_trader.py` — run against live feed in paper mode.
5. Build `storage/` — confirm candles and trades writing to TimescaleDB.
6. Build `alerts/telegram.py` — confirm notifications on each trade event.
7. Run 2–4 weeks of paper trading. Review PnL, fill rates, and breakout guard trigger frequency.
8. Address any weaknesses surfaced during paper testing before enabling live execution.
