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
