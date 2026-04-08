"""
Multi-agent orchestrator for range-trading-bot development.

Each step builds one module, runs unit tests, and merges only on green.
Mirrors the workflow defined in CLAUDE.md exactly.

Usage:
    python orchestrator.py <step>

    step: 1–9  (matches the module order table in CLAUDE.md)

Examples:
    python orchestrator.py 1   # feeds: normalizer, binance, coinbase
    python orchestrator.py 3   # indicators: RSI, MACD, ADX, Volume
"""
import sys
import anyio
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    ResultMessage,
    SystemMessage,
)

CWD = "C:/Users/Felix/VSCodeProjects/range_trading_bot"

# Matches the module order table in CLAUDE.md exactly.
MODULES = [
    {
        "step": 1,
        "branch": "feature/feeds-normalizer",
        "agent": "feeds-builder",
        "task": (
            "Implement feeds/normalizer.py (NormalizedCandle dataclass + ExchangeNormalizer ABC "
            "with stream and stream_with_retry), feeds/binance.py (BinanceNormalizer), and "
            "feeds/coinbase.py (CoinbaseNormalizer). "
            "Then write tests/test_feeds_normalizer.py: unit tests for parse_message on both "
            "exchanges using synthetic raw payloads — no network required."
        ),
    },
    {
        "step": 2,
        "branch": "feature/feeds-manager",
        "agent": "feeds-builder",
        "task": (
            "Implement feeds/manager.py (PriceFeedManager with deduplication by "
            "exchange:timestamp:interval key and concurrent feed support via asyncio.gather). "
            "Write tests/test_feeds_manager.py: confirm deduplication, subscriber callbacks, "
            "and seen-set pruning."
        ),
    },
    {
        "step": 3,
        "branch": "feature/indicators",
        "agent": "indicators-builder",
        "task": (
            "Implement indicators/rsi.py, indicators/macd.py, indicators/adx.py, "
            "indicators/volume.py, and indicators/candles.py (CandleAggregator stub). "
            "Write tests/test_indicators.py: feed each indicator a known OHLCV sequence "
            "and assert .value matches a reference calculation."
        ),
    },
    {
        "step": 4,
        "branch": "feature/breakout-guard",
        "agent": "strategy-builder",
        "task": (
            "Implement strategy/breakout_guard.py (BreakoutGuard). "
            "Write tests/test_breakout_guard.py: cover pauses on price outside buffer, "
            "confirm-candle countdown, and clean resume after N candles inside range."
        ),
    },
    {
        "step": 5,
        "branch": "feature/dip-buy",
        "agent": "strategy-builder",
        "task": (
            "Implement strategy/dip_buy.py (DipBuyStrategy + Lot dataclass). "
            "Write tests/test_dip_buy.py: cover lot creation on dip, per-lot sell check "
            "at +5%, rolling high reset after buy, and MAX_LOTS enforcement."
        ),
    },
    {
        "step": 6,
        "branch": "feature/hold-extension",
        "agent": "strategy-builder",
        "task": (
            "Implement strategy/hold_extension.py (HoldExtension). "
            "Write tests/test_hold_extension.py: cover HOLD path (bullish signals met), "
            "SELL path (insufficient signals), and TRAIL_STOP_HIT path (trailing stop breached)."
        ),
    },
    {
        "step": 7,
        "branch": "feature/engine-paper",
        "agent": "strategy-builder",
        "task": (
            "Implement strategy/engine.py (StrategyEngine) and execution/paper_trader.py "
            "(PaperTrader). "
            "Write tests/test_engine.py: feed a synthetic closed-candle stream that exercises "
            "the full BUY → HOLD → SELL flow through PaperTrader; assert balance_usd changes "
            "correctly and trades list is populated."
        ),
    },
    {
        "step": 8,
        "branch": "feature/storage",
        "agent": "storage-builder",
        "task": (
            "Implement storage/db.py (connection helper) and storage/candle_store.py "
            "(CandleStore with asyncpg pool). "
            "Write tests/integration_storage.py: write a NormalizedCandle and read it back; "
            "confirm round-trip fidelity and ON CONFLICT DO NOTHING deduplication. "
            "This test requires a local TimescaleDB instance."
        ),
    },
    {
        "step": 9,
        "branch": "feature/alerts",
        "agent": "alerts-builder",
        "task": (
            "Implement alerts/telegram.py (TelegramAlert). "
            "Write tests/test_alerts.py: mock aiohttp.ClientSession.post and confirm the "
            "correct payload is sent for BUY, SELL, TRAIL_STOP_HIT, and breakout-pause events. "
            "Assert that send() never raises — failures must be swallowed."
        ),
    },
]


def _agent_definitions() -> dict[str, AgentDefinition]:
    return {
        # ── Builder agents (one per package) ───────────────────────────────────
        "feeds-builder": AgentDefinition(
            description="Implements the data ingestion layer in feeds/.",
            prompt="""You implement the feeds/ package for a SOL/USDT range-trading bot.

Before writing code read CLAUDE.md and feeds/CLAUDE.md.

Hard rules:
- NormalizedCandle is the ONLY data type that leaves this layer.
- Raw exchange payloads must never be used outside feeds/.
- All IO is async (websockets, asyncio). No blocking calls.
- stream_with_retry uses exponential backoff starting at 1s, capped at 60s.
- is_closed must be set correctly — strategy logic depends on it.
- Never import * — explicit imports only.
- Use dataclasses and ABCs with full type hints.""",
            tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        ),
        "indicators-builder": AgentDefinition(
            description="Implements stateful indicator calculators in indicators/.",
            prompt="""You implement the indicators/ package for a SOL/USDT range-trading bot.

Before writing code read CLAUDE.md and indicators/CLAUDE.md.

Hard rules:
- Each indicator is a stateful class with an update() method and a .value attribute.
- Use collections.deque(maxlen=N) for all rolling windows.
- No side effects — pure calculation only.
- Return None / leave .value as None until enough data has arrived.
- Never import * — explicit imports only.""",
            tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        ),
        "strategy-builder": AgentDefinition(
            description="Implements strategy/ and execution/ modules.",
            prompt="""You implement the strategy/ and execution/ packages for a SOL/USDT range-trading bot.

Before writing code read CLAUDE.md, strategy/CLAUDE.md, and execution/CLAUDE.md.

Hard rules:
- NEVER act on a candle where is_closed is False.
- BreakoutGuard is checked FIRST — it gates all other logic.
- DipBuyStrategy tracks per-lot state; lots are only removed via close_lot().
- HoldExtension returns exactly one of: 'HOLD', 'SELL', 'TRAIL_STOP_HIT'.
- PaperTrader tracks balance_usd and a trades list. No real orders.
- OrderRouter reads credentials from os.getenv() only — nothing hardcoded.
- Never import * — explicit imports only.""",
            tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        ),
        "storage-builder": AgentDefinition(
            description="Implements the TimescaleDB storage layer in storage/.",
            prompt="""You implement the storage/ package for a SOL/USDT range-trading bot.

Before writing code read CLAUDE.md and storage/CLAUDE.md.

Hard rules:
- Only write candles where is_closed is True.
- Use ON CONFLICT DO NOTHING to prevent duplicates.
- DB credentials come from config.DB_URL — never hardcoded.
- Use asyncpg with a connection pool (create_pool).
- Never import * — explicit imports only.""",
            tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        ),
        "alerts-builder": AgentDefinition(
            description="Implements Telegram alerting in alerts/.",
            prompt="""You implement the alerts/ package for a SOL/USDT range-trading bot.

Before writing code read CLAUDE.md and alerts/CLAUDE.md.

Hard rules:
- Use aiohttp for HTTP — the codebase is fully async, never use requests.
- send() must NEVER raise. Swallow all exceptions and print the error.
- Token and chat_id come from constructor arguments (sourced from config) — not hardcoded.
- Never import * — explicit imports only.""",
            tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        ),

        # ── Test runner ────────────────────────────────────────────────────────
        "test-runner": AgentDefinition(
            description="Runs pytest unit tests and reports pass/fail with details.",
            prompt="""You run the unit test suite for a SOL/USDT range-trading bot.

Run exactly:
    python -m pytest tests/ -k "not integration" -v

Report:
- Total passed / failed / errored
- For every failure: the test name, the assertion that failed, and the full traceback
- Your final line must be either "ALL TESTS PASS" or "TESTS FAILED: <count> failure(s)"

Do not attempt to fix failures — only report them.""",
            tools=["Bash", "Read"],
        ),

        # ── Git / merge manager ────────────────────────────────────────────────
        "git-manager": AgentDefinition(
            description="Handles git branch creation, commits, push, and no-ff merge to main.",
            prompt="""You manage git operations for a SOL/USDT range-trading bot.

Hard rules:
- NEVER commit .env or any file containing credentials or secrets.
- NEVER use 'git add .' — always stage specific files by name.
- NEVER fast-forward merge — always use --no-ff to preserve branch history.
- Commit message format: <type>: <short description>
  Types: feat | fix | test | refactor | docs
- Implementation and its tests go in the same commit (or consecutive commits on the branch).
- Delete the feature branch locally after merging.
- If the branch already exists locally, check it out; do not recreate it.""",
            tools=["Bash"],
        ),
    }


async def run_step(step: int) -> None:
    module = next((m for m in MODULES if m["step"] == step), None)
    if module is None:
        print(f"Unknown step: {step}. Valid steps: 1–{len(MODULES)}")
        return

    branch = module["branch"]
    agent_name = module["agent"]
    task = module["task"]

    print(f"\n{'='*60}")
    print(f"Step {step}: {branch}")
    print(f"{'='*60}\n")

    options = ClaudeAgentOptions(
        cwd=CWD,
        allowed_tools=["Read", "Glob", "Grep", "Bash", "Agent"],
        permission_mode="acceptEdits",
        model="claude-opus-4-6",
        agents=_agent_definitions(),
        setting_sources=["project"],  # loads CLAUDE.md files
        max_turns=50,
    )

    prompt = f"""You are the development orchestrator for the range-trading-bot project.

Your job for this session is Step {step}: branch `{branch}`.

Follow this exact sequence — do not skip or reorder steps:

1. GIT SETUP
   Use the git-manager agent to:
   - Check out main and pull latest
   - Create and switch to branch `{branch}`

2. IMPLEMENTATION
   Use the {agent_name} agent to complete the following task:
   {task}

3. UNIT TESTS
   Use the test-runner agent to run the full unit test suite.
   Read its output carefully.

4. DECISION
   - If the test-runner reports "ALL TESTS PASS":
     Use the git-manager agent to:
       a. Stage the relevant new/changed files
       b. Commit with an appropriate message
       c. Push `{branch}` to origin
       d. Merge `{branch}` into main with --no-ff
       e. Push main
       f. Delete the local feature branch
     Then report: "Step {step} complete. Branch merged to main."

   - If the test-runner reports any failures:
     Do NOT merge.
     Report: "Step {step} blocked — tests failing:" followed by the failure details.
     Stop. Do not attempt to fix the failures yourself.

Be strict: merge only on a clean test run.
"""

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            print("\n--- Orchestrator Result ---")
            print(message.result)
        elif isinstance(message, SystemMessage) and message.subtype == "init":
            session_id = message.data.get("session_id", "unknown")
            print(f"Session: {session_id}")


def _print_usage() -> None:
    print(__doc__)
    print("Available steps:\n")
    for m in MODULES:
        print(f"  {m['step']:>2}  {m['branch']}")
    print()


async def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        return

    try:
        step = int(sys.argv[1])
    except ValueError:
        print(f"Error: step must be an integer, got '{sys.argv[1]}'")
        _print_usage()
        return

    await run_step(step)


anyio.run(main)
