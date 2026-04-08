# Exchange
PRIMARY_EXCHANGE   = "binance"
FALLBACK_EXCHANGE  = "coinbase"
SYMBOL             = "SOL/USDT"
INTERVAL           = "15m"

# Range boundaries (update manually or automate with range_detector)
RANGE_SUPPORT      = 78.0
RANGE_RESISTANCE   = 85.0
RANGE_BUFFER_PCT   = 0.02     # 2% outside range triggers breakout guard
BREAKOUT_CONFIRM_CANDLES = 3  # candles inside range before resuming

# Dip-buy strategy
DIP_PCT            = 0.05     # -5% from rolling high to trigger buy
TARGET_PCT         = 0.05     # +5% from lot entry to trigger sell check
MAX_LOTS           = 4        # max simultaneous open lots
LOT_SIZE_USD       = 250      # dollar size per lot

# Hold extension
TRAIL_PCT          = 0.02     # trailing stop 2% below running high
MIN_BULLISH_SIGNALS = 2       # indicators required to extend hold
ADX_TREND_THRESHOLD = 25      # ADX above this = trending

# Risk limits
MAX_DRAWDOWN_PCT   = 0.10     # pause bot if portfolio drops 10%
MAX_DAILY_LOSS_USD = 100.0

# Mode
PAPER_TRADE        = True     # ALWAYS start here; flip to False for live

# Database
DB_URL = "postgresql://user:password@localhost:5432/tradebot"

# Alerts
TELEGRAM_TOKEN     = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID   = "YOUR_CHAT_ID"
