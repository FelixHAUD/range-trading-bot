# SOL/USDT Range Trading Bot

A paper-first crypto trading bot for SOL/USDT. Three strategies run simultaneously inside a defined price range:

1. **Dip-buy** — buys on -5% drops from a rolling 5-hour high, checks sell at +5% per lot
2. **Hold extension** — if 2+ indicators are bullish at the +5% target, holds with a 2% trailing stop instead of selling immediately
3. **Breakout guard** — pauses all trading if price exits the range, resumes after 3 confirm candles back inside

The range boundaries update automatically each week using the prior 4 weeks of price data — no manual config edits needed when SOL shifts zones.

---

## Requirements

- Python 3.11+
- A Binance.US account (for live data feed and optional live trading)
- A Telegram bot (for trade alerts)
- TimescaleDB — optional, only needed for candle storage

---

## Installation

```bash
git clone https://github.com/FelixHAUD/range_trading_bot.git
cd range_trading_bot
pip install -r requirements.txt
```

---

## Configuration

### 1. Environment variables

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
DB_URL=postgresql://user:password@localhost:5432/tradebot   # optional

# Only needed for live trading (not paper mode)
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET=your_binance_secret
```

Load the file before running (or use a tool like `python-dotenv`):

```bash
# Windows
set TELEGRAM_TOKEN=xxx
set TELEGRAM_CHAT_ID=xxx

# Mac/Linux
export TELEGRAM_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx
```

### 2. Strategy parameters (`config.py`)

All tunable parameters are in `config.py`. The key ones:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `RANGE_SUPPORT` | 78.0 | Initial support — overwritten after first weekly recalc |
| `RANGE_RESISTANCE` | 85.0 | Initial resistance — overwritten after first weekly recalc |
| `DIP_PCT` | 0.05 | Buy trigger: -5% from rolling high |
| `TARGET_PCT` | 0.05 | Sell check trigger: +5% from lot entry |
| `MAX_LOTS` | 4 | Max simultaneous open positions |
| `LOT_SIZE_USD` | 250 | Dollar size per lot |
| `TRAIL_PCT` | 0.02 | Trailing stop: 2% below running high |
| `MIN_BULLISH_SIGNALS` | 2 | Indicators needed to extend hold past +5% |
| `PAPER_TRADE` | True | **Always start here** |

---

## Telegram Bot Setup

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts — choose a name and username
3. BotFather gives you a **token** like `7123456789:AAFxxxx...` — this is your `TELEGRAM_TOKEN`
4. Start a chat with your new bot (search for it by username and press Start)
5. Get your **Chat ID**:
   - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser after sending any message to the bot
   - Find `"chat":{"id":123456789}` — that number is your `TELEGRAM_CHAT_ID`
6. Add both values to your `.env` file

The bot sends alerts on: **BUY**, **SELL**, **TRAIL_STOP_HIT**, and **breakout pauses**.

---

## Running the Bot

### Paper trading (default — always start here)

```bash
python main.py
```

On startup the bot will:
1. Fetch 4 weeks of historical candles to warm up the dynamic range detector
2. Log the detected support/resistance levels
3. Connect to Binance.US and Coinbase WebSocket feeds
4. Print a live tick line every 15 minutes showing price, indicators, and balance

Example console output:
```
2026-04-09 10:00:00 [INFO] Range warmed up: support=$78.50  resistance=$96.20  (2688 candles)
2026-04-09 10:00:00 [INFO] Starting PAPER trading -- SOL/USDT @ 15m
2026-04-09 10:00:00 [INFO] Initial range: $78.50 -- $96.20
2026-04-09 10:00:00 [INFO] Initial balance: $10,000.00
2026-04-09 10:15:00 [INFO] [10:15] SOL/USDT $82.41 hi:$86.90 | RSI:48.2 MACD:- ADX:18.3 Vol:v | Lots:0/4 | Bal:$10,000.00
2026-04-09 10:30:00 [INFO] [10:30] SOL/USDT $80.20 hi:$86.90 | RSI:41.1 MACD:- ADX:21.4 Vol:^ | Lots:0/4 | Bal:$10,000.00
2026-04-09 10:30:00 [INFO] >>> BUY  lot_xxx @ $80.20 | 3.1172 SOL | dip from $86.90
```

Logs are also written to `logs/bot.log` (rotates at 10 MB, keeps 5 files).

### Stopping the bot

```bash
Ctrl+C
```

---

## Backtesting

Replay historical candles through the exact same strategy engine used in production.

### Default (last 90 days)

```bash
python backtest/runner.py
```

### Custom number of days

```bash
python backtest/runner.py --days 180
```

### Specific date range

```bash
python backtest/runner.py --start 2024-10-01 --end 2025-01-01
```

Example output:
```
Fetching SOL/USDT 15m candles from Binance.US...
Fetched 8,640 candles.

================================================
  BACKTEST: SOL/USDT 15m
================================================
  Period       : 2024-10-01 -> 2025-01-01  (92 days)
  Candles      : 8,640
  Range        : dynamic -- weekly recalc, 4-week lookback
  Final range  : $78.50 to $96.20

  Closed lots  : 14
  Gross PnL    : $+187.42
  Est. fees    : -$14.00  (0.1% per side)
  Net PnL      : $+173.42
  Win rate     : 71.4%  (10W / 4L)
  Avg win      : $+28.50
  Avg loss     : $-18.30
  Best trade   : $+61.20  lot_xxx  (TRAIL_STOP_HIT)
  Worst trade  : $-31.50  lot_xxx  (SELL)

  Max drawdown     : -$48.20
  Breakout pauses  : 7
  Open lots at end : 1  (unrealised $+5.20)
  Final balance    : $10,173.42
================================================
```

> **Tip:** If you see very few trades and many breakout pauses, SOL was trending (not ranging) during that period. Try a different date range or widen the range parameters in `config.py`.

---

## Running Tests

```bash
# All unit tests (fast, no network)
python -m pytest tests/ -k "not integration" -v

# Integration tests (require live DB and network)
python -m pytest tests/ -v
```

All 162 unit tests run in under 2 seconds with no external dependencies.

---

## Project Structure

```
range_trading_bot/
├── main.py                    # Entry point
├── config.py                  # All tunable parameters
├── backtest/
│   └── runner.py              # Backtest CLI
├── feeds/
│   ├── normalizer.py          # NormalizedCandle base class
│   ├── binance.py             # Binance.US WebSocket feed
│   ├── coinbase.py            # Coinbase WebSocket feed
│   └── manager.py             # Runs both feeds concurrently
├── indicators/
│   ├── rsi.py                 # RSI (period 14)
│   ├── macd.py                # MACD (12/26/9)
│   ├── adx.py                 # ADX (period 14)
│   └── volume.py              # Volume vs 20-candle average
├── strategy/
│   ├── engine.py              # Orchestrates all modules
│   ├── breakout_guard.py      # Pauses bot on range exit
│   ├── dip_buy.py             # Per-lot -5%/+5% logic
│   ├── hold_extension.py      # Indicator-gated trailing stop
│   └── range_detector.py      # Weekly dynamic support/resistance
├── execution/
│   ├── paper_trader.py        # Simulates trades (default)
│   └── order_router.py        # Live orders via ccxt
├── storage/
│   ├── db.py                  # TimescaleDB connection
│   └── candle_store.py        # Writes closed candles
├── alerts/
│   └── telegram.py            # Trade notifications
├── logs/                      # Auto-created, gitignored
└── tests/                     # 162 unit tests
```

---

## Tick Line Reference

Each closed candle (every 15 minutes) prints one line:

```
[HH:MM] SOL/USDT $82.41 hi:$86.90 | RSI:48.2 MACD:+ ADX:18.3 Vol:^ | Lots:0/4 | Bal:$10,000.00
```

| Field | Meaning |
|-------|---------|
| `hi:$86.90` | Current 5-hour rolling high (dip measured from here) |
| `MACD:+/-` | `+` = MACD line rising and positive, `-` = not |
| `Vol:^/v` | `^` = volume above 20-candle average |
| `Lots:0/4` | Open lots / max lots |

---

## Going Live

> **Do not go live without at least 2-4 weeks of paper testing.**

1. Set `PAPER_TRADE = False` in `config.py`
2. Add `BINANCE_API_KEY` and `BINANCE_SECRET` to `.env`
3. Change `BinanceUSNormalizer` to also use live order routing in `main.py` (swap `PaperTrader` for `OrderRouter`)
4. Start with minimum lot sizes (`LOT_SIZE_USD = 25`) for forward testing

---

## Known Limitations

- **Ranging markets only** — the breakout guard pauses the bot during trends. If SOL is in a strong uptrend, expect few or no trades.
- **Fee drag** — estimated at 0.1% per side. With 4 lots per cycle, fees can consume ~0.8% of each range cycle's profit.
- **Paper-to-live gap** — paper trading ignores slippage, partial fills, and withdrawal limits. Forward-test at minimum size first.
- **Coinbase fallback** — the Coinbase feed subscribes to `SOL/USDT` but Coinbase only lists `SOL/USD`. It connects but produces no candles; Binance.US is the effective sole feed.
