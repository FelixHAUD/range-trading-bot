# strategy/ — Claude Context

## Key decisions (TASK-005)

- **Lot ID uses timestamp + monotonic counter** (`lot_{ms}_{counter}`).
  Pure millisecond timestamps collide when two lots are created in rapid succession
  (common in tests and in fast markets). The counter suffix guarantees uniqueness
  within a strategy instance.

- **Rolling high resets to close after every buy.** This is intentional: each
  subsequent dip is measured from the price at the last buy, not the all-time
  session high. This prevents the bot from never triggering a second lot when
  the overall trend is down.

- **Drop threshold is strictly `>=`.** A drop of exactly `dip_pct` (e.g. exactly
  5.000%) triggers a buy. Tests must use prices that exceed the threshold with
  enough margin to survive floating-point arithmetic (e.g. use 89.0 not 89.3
  when the threshold is 94 * 0.95 = 89.3).

## Key decisions (TASK-014 — BearishGuard)

- **BearishGuard mirrors HoldExtension's signal-counting pattern** but inverted: where
  HoldExtension counts bullish signals to *extend* a hold, BearishGuard counts bearish
  signals to *block* new entries. Both use a configurable `min_*` threshold.

- **RSI default is 50.0 (neutral) when not yet warmed up.** The engine passes
  `rsi.value if rsi.value is not None else 50.0` to the indicators dict. Using 0.0
  caused false bearish signals during the first 14 candles of any session.

- **`dip_buy.close_lot()` must be called when a BUY signal is skipped.** `dip_buy.on_candle()`
  adds the lot to `open_lots` before returning the signal. If the engine gates the buy
  (bearish guard or drawdown limit), it must call `close_lot(lot.id)` to keep the
  open_lots list clean.

- **BearishGuard bearish signals (4 total):**
  1. RSI < 40 (strictly less than — RSI=40.0 does NOT count)
  2. MACD not bullish
  3. Price < (support + resistance) / 2
  4. ADX > 25 (strictly greater than — ADX=25.0 does NOT count)

## Key decisions (TASK-012 — RangeDetector)

- **1-week lookback chosen over 4-week** based on 28-day backtest sweep. Longer lookbacks
  capture old highs/lows that no longer reflect current market structure, causing the
  breakout guard to pause excessively.

- **Recalc every `recalc_every` candles** (default: 1 week at 5m = 2016). The detector
  does not recalc on every candle — only when `count % recalc_every == 0` and the deque
  has at least `recalc_every` entries. Initial support/resistance are held until the first
  recalc fires.
