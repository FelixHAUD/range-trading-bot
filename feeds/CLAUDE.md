# feeds/ — Claude Context

## Key decisions (TASK-001)

- **Coinbase `is_closed=True`** is intentional. The Coinbase Advanced Trade `candles`
  channel delivers completed historical candles, not streaming partials. Every message
  from this channel represents a closed candle, so hardcoding `is_closed=True` is correct.

- **Symbol normalisation order matters.** Check longest quote suffix first to avoid
  partial matches (e.g. check `USDT` before `BTC` to handle `BTCUSDT` correctly).
  Current order: USDT → USDC → BTC → ETH. Extend this list if new quote assets are added.

- **`stream_with_retry` is the only public streaming method.** Direct `stream()` calls
  are for testing only — production code always uses `stream_with_retry`.
