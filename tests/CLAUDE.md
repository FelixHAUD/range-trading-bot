# Tests

## File naming
- `test_<module>.py` — unit tests (no network, no DB, no filesystem)
- `integration_<module>.py` — integration tests (real or realistic neighbours)

## Running
```bash
# Unit tests only
python -m pytest tests/ -k "not integration"

# Integration tests only
python -m pytest tests/ -k "integration"

# All
python -m pytest tests/
```

## Unit test rules
- No mocking of the module under test — only mock its external dependencies (exchange, DB, network)
- Use hardcoded inputs and assert exact outputs
- One `assert` concept per test function; keep tests short and readable
- Cover: happy path, boundary values, and one realistic failure/edge case per function

## Integration test rules
- Tests prefixed `integration_` may hit the network or a local DB but must never touch production credentials
- Use the Binance testnet or replay a saved WebSocket message file for feed tests
- For DB tests, use a local TimescaleDB instance seeded in the test setup; tear down after
- Assert on observable side-effects (rows written, messages sent) not internal state

## What NOT to test
- `config.py` values — these are configuration, not logic
- `main.py` wiring — covered by end-to-end paper run
- Third-party library behaviour (ccxt, asyncpg, aiohttp)
