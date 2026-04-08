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
