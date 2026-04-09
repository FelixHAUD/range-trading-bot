# Exchange
PRIMARY_EXCHANGE   = "binance"
FALLBACK_EXCHANGE  = "coinbase"
SYMBOL             = "SOL/USDT"
INTERVAL           = "5m"

# Range boundaries (update manually or automate with range_detector)
RANGE_SUPPORT      = 78.0
RANGE_RESISTANCE   = 85.0
RANGE_BUFFER_PCT   = 0.02     # 2% outside range triggers breakout guard (sweep-optimised)
BREAKOUT_CONFIRM_CANDLES = 2  # candles inside range before resuming

# Dip-buy strategy
DIP_PCT            = 0.05     # -5% from rolling high to trigger buy
TARGET_PCT         = 0.05     # +5% from lot entry to trigger sell check
MAX_LOTS           = 4        # max simultaneous open lots
LOT_SIZE_USD       = 250      # dollar size per lot

# Hold extension
TRAIL_PCT          = 0.02     # trailing stop 2% below running high
MIN_BULLISH_SIGNALS = 2       # indicators required to extend hold
ADX_TREND_THRESHOLD = 25      # ADX above this = trending

# Dynamic range detection
RANGE_LOOKBACK_CANDLES = 2016   # 1 week at 5m  (7 * 24 * 12)
RANGE_RECALC_CANDLES   = 2016   # recalc every week at 5m

# Bearish guard
MIN_BEARISH_SIGNALS = 3       # 3 of 4 indicators bearish -> block new buys + scan exits
MAX_LOT_LOSS_PCT    = 0.05    # force-exit any open lot losing >= 5% when bearish active (tightened from 7%)

# Hard stop-loss — unconditional, fires regardless of bearish guard state
HARD_STOP_PCT      = 0.15     # close any lot down >=15% from entry immediately

# Macro trend filter — block new buys when price is below a declining EMA
TREND_EMA_PERIOD   = 50       # candles (50 × 5m ≈ 4 hours; tune higher for slower filter)

# Risk limits
MAX_DRAWDOWN_PCT   = 0.10     # pause bot if portfolio drops 10%
MAX_DAILY_LOSS_USD = 100.0

# Mode
PAPER_TRADE        = True     # ALWAYS start here; flip to False for live

# Database
import os
DB_URL = os.getenv("DB_URL", "postgresql://user:password@localhost:5432/tradebot")

# Alerts
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
