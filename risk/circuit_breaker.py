"""Circuit breaker for trading risk management."""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Any

from config.logging_config import get_logger

logger = get_logger(__name__)


class CircuitBreaker:
    """Trading circuit breaker that enforces hard risk limits.

    This class enforces:
    - Maximum daily loss percentage
    - Maximum trades per day
    - Maximum open positions
    - Maximum risk per trade

    These limits are INDEPENDENT of LLM decisions and are always enforced.
    """

    def __init__(
        self,
        max_daily_loss_percent: float = 5.0,
        max_trades_per_day: int = 10,
        max_open_positions: int = 3,
        max_risk_percent: float = 2.0,
        state_file: Path | None = None,
    ):
        """Initialize circuit breaker.

        Args:
            max_daily_loss_percent: Maximum daily loss as % of starting balance
            max_trades_per_day: Maximum number of trades per day
            max_open_positions: Maximum concurrent open positions
            max_risk_percent: Maximum risk per trade as % of balance
            state_file: Optional file to persist state across restarts
        """
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_trades_per_day = max_trades_per_day
        self.max_open_positions = max_open_positions
        self.max_risk_percent = max_risk_percent
        self.state_file = state_file

        # Daily state
        self._current_date: date | None = None
        self._starting_balance: float = 0.0
        self._trade_count: int = 0
        self._daily_pnl: float = 0.0
        self._is_tripped: bool = False
        self._trip_reason: str | None = None

        # Load persisted state if available
        self._load_state()

    def _load_state(self) -> None:
        """Load state from file if it exists."""
        if self.state_file and self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                saved_date = date.fromisoformat(data.get("date", ""))

                if saved_date == date.today():
                    self._current_date = saved_date
                    self._starting_balance = data.get("starting_balance", 0.0)
                    self._trade_count = data.get("trade_count", 0)
                    self._daily_pnl = data.get("daily_pnl", 0.0)
                    self._is_tripped = data.get("is_tripped", False)
                    self._trip_reason = data.get("trip_reason")
                    logger.info("Circuit breaker state restored", **data)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Failed to load circuit breaker state", error=str(e))

    def _save_state(self) -> None:
        """Save state to file."""
        if self.state_file:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "date": self._current_date.isoformat() if self._current_date else None,
                "starting_balance": self._starting_balance,
                "trade_count": self._trade_count,
                "daily_pnl": self._daily_pnl,
                "is_tripped": self._is_tripped,
                "trip_reason": self._trip_reason,
            }
            self.state_file.write_text(json.dumps(data, indent=2))

    def initialize_day(self, starting_balance: float) -> None:
        """Initialize or reset for a new trading day.

        Args:
            starting_balance: Account balance at start of day
        """
        today = date.today()

        if self._current_date != today:
            self._current_date = today
            self._starting_balance = starting_balance
            self._trade_count = 0
            self._daily_pnl = 0.0
            self._is_tripped = False
            self._trip_reason = None
            self._save_state()
            logger.info(
                "Circuit breaker initialized for new day",
                date=today.isoformat(),
                starting_balance=starting_balance,
            )

    def check_preconditions(
        self,
        current_equity: float,
        open_position_count: int,
    ) -> tuple[bool, str | None]:
        """Check if trading is allowed based on current state.

        Args:
            current_equity: Current account equity
            open_position_count: Number of currently open positions

        Returns:
            Tuple of (allowed, reason_if_not_allowed)
        """
        # Already tripped
        if self._is_tripped:
            return False, self._trip_reason

        # Check daily loss limit
        if self._starting_balance > 0:
            loss_percent = (
                (self._starting_balance - current_equity) / self._starting_balance * 100
            )
            if loss_percent >= self.max_daily_loss_percent:
                self._trip(
                    f"Daily loss limit reached: {loss_percent:.2f}% >= {self.max_daily_loss_percent}%"
                )
                return False, self._trip_reason

        # Check trade count
        if self._trade_count >= self.max_trades_per_day:
            return False, f"Max daily trades reached: {self._trade_count}/{self.max_trades_per_day}"

        # Check open positions
        if open_position_count >= self.max_open_positions:
            return False, f"Max open positions reached: {open_position_count}/{self.max_open_positions}"

        return True, None

    def validate_trade(
        self,
        account_balance: float,
        risk_amount: float,
        stop_loss_pips: float | None = None,
    ) -> tuple[bool, str | None]:
        """Validate a proposed trade against risk limits.

        This is called AFTER the risk manager agent, as a final safety check.

        Args:
            account_balance: Current account balance
            risk_amount: Dollar amount being risked on this trade
            stop_loss_pips: Optional stop loss in pips

        Returns:
            Tuple of (valid, reason_if_invalid)
        """
        if self._is_tripped:
            return False, self._trip_reason

        # Calculate risk percentage
        risk_percent = (risk_amount / account_balance * 100) if account_balance > 0 else 100

        # HARD LIMIT: Risk must never exceed max_risk_percent
        if risk_percent > self.max_risk_percent:
            return False, (
                f"Risk exceeds limit: {risk_percent:.2f}% > {self.max_risk_percent}%"
            )

        # Warn if stop loss is missing
        if stop_loss_pips is None or stop_loss_pips <= 0:
            logger.warning("Trade has no stop loss defined")

        return True, None

    def record_trade(self, profit: float = 0.0) -> None:
        """Record that a trade was executed.

        Args:
            profit: Realized profit/loss (for closed trades)
        """
        self._trade_count += 1
        self._daily_pnl += profit
        self._save_state()
        logger.debug(
            "Trade recorded",
            count=self._trade_count,
            daily_pnl=self._daily_pnl,
        )

    def _trip(self, reason: str) -> None:
        """Trip the circuit breaker.

        Args:
            reason: Reason for tripping
        """
        self._is_tripped = True
        self._trip_reason = reason
        self._save_state()
        logger.warning("Circuit breaker TRIPPED", reason=reason)

    def reset(self) -> None:
        """Manually reset the circuit breaker.

        Use with caution - typically only for testing or manual override.
        """
        self._is_tripped = False
        self._trip_reason = None
        self._save_state()
        logger.info("Circuit breaker manually reset")

    @property
    def is_tripped(self) -> bool:
        """Check if circuit breaker is tripped."""
        return self._is_tripped

    @property
    def status(self) -> dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "date": self._current_date.isoformat() if self._current_date else None,
            "starting_balance": self._starting_balance,
            "trade_count": self._trade_count,
            "max_trades": self.max_trades_per_day,
            "daily_pnl": self._daily_pnl,
            "max_daily_loss_percent": self.max_daily_loss_percent,
            "is_tripped": self._is_tripped,
            "trip_reason": self._trip_reason,
        }
