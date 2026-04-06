"""LangGraph state schema for the trading workflow."""

from typing import TypedDict, Any
from datetime import datetime


class TradingState(TypedDict):
    """State schema for the trading graph.

    All fields must be present between nodes.
    """
    # Core identifiers
    symbol: str
    timeframe: str
    timestamp: str

    # Account information
    account: dict[str, Any]  # balance, equity, margin, positions

    # Market data
    ohlcv: list[dict[str, Any]]  # raw candles as list of dicts

    # Agent outputs
    market_analysis: dict[str, Any] | None  # output of market analyst
    sentiment: dict[str, Any] | None  # output of sentiment agent
    signal: dict[str, Any] | None  # output of strategy agent
    risk_params: dict[str, Any] | None  # output of risk manager
    execution_result: dict[str, Any] | None  # fill confirmation or error

    # Metadata
    cycle_log: dict[str, Any]  # full audit trail
    error: str | None  # any agent error
    should_continue: bool  # whether to proceed to next node


def create_initial_state(
    symbol: str,
    timeframe: str,
    account: dict[str, Any],
    ohlcv: list[dict[str, Any]],
) -> TradingState:
    """Create initial state for a trading cycle.

    Args:
        symbol: Trading symbol
        timeframe: Timeframe string
        account: Account state dict
        ohlcv: OHLCV data as list of dicts

    Returns:
        Initial TradingState
    """
    return TradingState(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.utcnow().isoformat(),
        account=account,
        ohlcv=ohlcv,
        market_analysis=None,
        sentiment=None,
        signal=None,
        risk_params=None,
        execution_result=None,
        cycle_log={
            "started_at": datetime.utcnow().isoformat(),
            "nodes_visited": [],
            "decisions": [],
        },
        error=None,
        should_continue=True,
    )


def update_state(state: TradingState, **updates) -> TradingState:
    """Update state with new values.

    Args:
        state: Current state
        **updates: Fields to update

    Returns:
        Updated state
    """
    new_state = dict(state)
    new_state.update(updates)

    # Track visited nodes
    if "node_name" in updates:
        new_state["cycle_log"]["nodes_visited"].append(updates["node_name"])

    return TradingState(**new_state)
