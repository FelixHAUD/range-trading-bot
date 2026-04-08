# Range Trading Bot — Claude Context

## Project Overview

SOL/USDT crypto range-trading bot. Three composable strategies run simultaneously:

1. **Range trading** — buy near support, sell near resistance within a defined band.
2. **Dip-buy with per-lot tracking** — buy on -5% drawdowns from a rolling high, sell each lot at +5% from its own entry.
3. **Hold extension** — delay the sell at +5% if momentum indicators confirm further upside, then exit via trailing stop.

A **breakout guard** gates all strategies — if price exits the range, the bot pauses entirely.

---

## Architecture Layers

| Layer | Package | Responsibility |
|-------|---------|----------------|
| 1 | `feeds/` | WebSocket ingestion. Produces `NormalizedCandle`. Raw exchange data never leaves this layer. |
| 2 | `indicators/` | Stateful calculators (RSI, MACD, ADX, Volume). Accept candles, expose a single `.value`. |
| 2 | `strategy/` | `StrategyEngine` orchestrates all modules. `BreakoutGuard` → `DipBuyStrategy` → `HoldExtension`. |
| 3 | `execution/` | `PaperTrader` (default) or `OrderRouter` (live via ccxt). |
| 4 | `storage/` | TimescaleDB via asyncpg. `CandleStore` writes closed candles. |
| 4 | `alerts/` | Telegram notifications for trades and errors. |

---

## Key Conventions

- **Always start in paper mode.** `PAPER_TRADE = True` in `config.py`. Never flip to `False` without weeks of paper testing.
- **Credentials from environment only.** Use `os.getenv(...)`. Never hardcode API keys or tokens.
- **Only act on closed candles.** Every strategy entry point must check `candle.is_closed` before processing.
- **`NormalizedCandle` is the contract.** Nothing outside `feeds/` should know about raw exchange message formats.
- **Deduplication key:** `f"{exchange}:{timestamp}:{interval}"` — used in `PriceFeedManager`.

---

## Python Standards

- **Python 3.11+.** Use `dataclasses`, `ABC`, and type hints throughout.
- **Async everywhere.** Use `async/await` for all I/O. No blocking calls in the hot path.
- **Rolling windows** via `collections.deque(maxlen=N)`.
- **WebSocket reconnection** uses exponential backoff, capped at 60s (`stream_with_retry`).
- **Explicit imports only.** Never `from module import *`.
- **No speculative abstractions.** Build for the current requirement; don't design for hypothetical future symbols or exchanges.
- **Test indicators in isolation** against known values before wiring into `StrategyEngine`.

---

## Configuration (`config.py`)

All tunable parameters live here. Key ones:

| Parameter | Default | Notes |
|-----------|---------|-------|
| `RANGE_SUPPORT` / `RANGE_RESISTANCE` | 78.0 / 85.0 | Update manually when SOL shifts range |
| `RANGE_BUFFER_PCT` | 0.02 | 2% outside range triggers breakout guard |
| `BREAKOUT_CONFIRM_CANDLES` | 3 | Candles inside range before resuming |
| `DIP_PCT` / `TARGET_PCT` | 0.05 / 0.05 | -5% to buy, +5% to check sell |
| `MAX_LOTS` | 4 | Max simultaneous open lots |
| `LOT_SIZE_USD` | 250 | Dollar size per lot |
| `TRAIL_PCT` | 0.02 | Trailing stop 2% below running high |
| `MIN_BULLISH_SIGNALS` | 2 | Indicators required to extend hold |
| `PAPER_TRADE` | True | **Always start here** |

---

## Development Workflow

Each module follows this cycle before moving on. **Only one module is in progress at a time.** Do not start the next until all four gates are green.

```
[ Branch ] → [ Implement module ] → [ Unit tests pass ] → [ Integration test passes ] → [ Manual review ] → [ Merge ] → next module
```

---

### Git Process

**One branch per module.** Branch naming: `feature/<module-name>` (e.g. `feature/feeds-normalizer`, `feature/indicators-rsi`).

```bash
# Start a new module
git checkout main
git pull
git checkout -b feature/<module-name>

# During development — commit as logical units, not as a dump at the end
git add <specific files>
git commit -m "<type>: <short description>"
# types: feat | fix | test | refactor | docs

# When all unit tests pass
git push -u origin feature/<module-name>

# After manual review is complete — merge back to main
git checkout main
git merge --no-ff feature/<module-name>   # always a merge commit, never fast-forward
git push
git branch -d feature/<module-name>
```

**Commit rules:**
- Commit the implementation and its tests together in the same commit (or as consecutive commits on the same branch — never tests on main without the feature they cover)
- Never commit broken code to main — unit tests must be passing on the branch before merging
- Never commit `.env` or any file containing credentials
- Keep commits small and descriptive; one logical change per commit

**When discoveries or decisions are made during a module:**
- Update the relevant `<package>/CLAUDE.md` before committing — that note travels with the code into the PR
- If the discovery affects the whole project (e.g. a constraint that changes the architecture), update the root `CLAUDE.md` in the same commit

---

### Gate 1 — Unit tests
- Written in `tests/` immediately after (or alongside) the module — not deferred
- Use synthetic/hardcoded inputs — no live exchange, no DB, no network
- Assert on exact output values; cover edge cases and boundary conditions
- **Hard stop:** `python -m pytest tests/ -k "not integration"` must return 0 failures before any other work continues on this branch

### Gate 2 — Integration test
- Wire the new module into the layer above it with real (or realistic stubbed) neighbours
- For `feeds/`: replay a recorded WebSocket message file; confirm `NormalizedCandle` fields are correct
- For `indicators/`: feed a known OHLCV sequence; compare output to a reference value calculated externally (e.g. TradingView)
- For `strategy/`: feed synthetic candle streams covering buy, sell, hold, and breakout scenarios end-to-end through `StrategyEngine` + `PaperTrader`
- For `storage/`: write candles and read them back; confirm round-trip fidelity
- Integration tests live in `tests/` prefixed with `integration_` so they can be run separately

### Gate 3 — Manual review
- Read the implementation and its tests; confirm logic matches the ARCHITECTURE.md spec
- Check that no raw exchange data leaks outside `feeds/`, no credentials are hardcoded, and closed-candle guard is in place
- Sign off before merging

### Gate 4 — Merge to main
- Only after Gates 1–3 are green
- Use `git merge --no-ff` to preserve branch history
- Delete the feature branch after merge

---

### Module order

| Step | Branch name | Module(s) | Key things to verify |
|------|-------------|-----------|----------------------|
| 1 | `feature/feeds-normalizer` | `feeds/normalizer.py`, `feeds/binance.py`, `feeds/coinbase.py` | `NormalizedCandle` fields populated correctly; `is_closed` flag accurate |
| 2 | `feature/feeds-manager` | `feeds/manager.py` | Deduplication works; both feeds run concurrently; retry fires on drop |
| 3 | `feature/indicators` | `indicators/rsi.py`, `indicators/macd.py`, `indicators/adx.py`, `indicators/volume.py` | Values match reference calculations for known OHLCV sequences |
| 4 | `feature/breakout-guard` | `strategy/breakout_guard.py` | Pauses on breakout; resumes only after N confirm candles |
| 5 | `feature/dip-buy` | `strategy/dip_buy.py` | Correct lot creation, per-lot sell check, rolling high reset |
| 6 | `feature/hold-extension` | `strategy/hold_extension.py` | HOLD/SELL/TRAIL_STOP_HIT logic; trailing stop tracks running high |
| 7 | `feature/engine-paper` | `strategy/engine.py` + `execution/paper_trader.py` | Full paper run on live feed; PnL tracking accurate |
| 8 | `feature/storage` | `storage/db.py`, `storage/candle_store.py` | Candle and trade round-trips; no duplicates; schema matches |
| 9 | `feature/alerts` | `alerts/telegram.py` | Messages sent on BUY, SELL, TRAIL_STOP_HIT, and breakout pause |
| 10 | — | End-to-end paper trading | 2–4 weeks; review fill rates, guard frequency, fee-adjusted PnL |

---

## Known Risks

- **Static range boundaries** — if SOL moves to a new range, the bot pauses indefinitely. Consider a `/setrange` Telegram command for manual updates.
- **Lot stacking in downtrends** — enforce a minimum candle gap between lot entries; require `MAX_DRAWDOWN_PCT` check before new lots.
- **Indicator lag** — RSI/MACD/ADX are lagging. On 15m candles, moves can reverse before confirmation. Consider order book imbalance as a leading pre-filter.
- **Exchange downtime** — `stream_with_retry` handles reconnection. Add REST fallback via `ccxt.fetch_ohlcv` if no candle arrives for >2 minutes.
- **Fee drag** — at 0.1% per trade with 4 lots per cycle, fees consume ~0.8% of each range cycle's profit.
- **Paper-to-live gap** — paper trading ignores slippage, partial fills, and withdrawal limits. Forward-test with minimum lot sizes ($25) for at least 2–4 weeks before going live.
