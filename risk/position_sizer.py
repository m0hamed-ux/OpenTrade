"""Position sizing calculations."""

from typing import Any
from dataclasses import dataclass

from config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PositionSize:
    """Calculated position size details."""
    lot_size: float
    risk_amount: float
    risk_percent: float
    stop_loss_pips: float
    take_profit_pips: float
    risk_reward_ratio: float
    pip_value: float


class PositionSizer:
    """Position sizing calculator using various methods.

    Supports:
    - Fixed fractional sizing
    - Kelly criterion
    - Fixed lot sizing
    """

    # Pip values for major pairs (per standard lot)
    # These are approximate - actual values depend on account currency
    PIP_VALUES = {
        "EURUSD": 10.0,
        "GBPUSD": 10.0,
        "USDJPY": 9.0,  # Varies with USD/JPY rate
        "USDCHF": 10.0,
        "AUDUSD": 10.0,
        "NZDUSD": 10.0,
        "USDCAD": 7.5,  # Varies with USD/CAD rate
        "XAUUSD": 1.0,  # Gold - pip = $0.01 per oz, $1 per lot
    }

    def __init__(
        self,
        default_risk_percent: float = 1.0,
        min_lot_size: float = 0.01,
        max_lot_size: float = 10.0,
        lot_step: float = 0.01,
        min_rr_ratio: float = 1.5,
    ):
        """Initialize position sizer.

        Args:
            default_risk_percent: Default risk per trade as % of balance
            min_lot_size: Minimum lot size allowed
            max_lot_size: Maximum lot size allowed
            lot_step: Lot size increment
            min_rr_ratio: Minimum acceptable risk-reward ratio
        """
        self.default_risk_percent = default_risk_percent
        self.min_lot_size = min_lot_size
        self.max_lot_size = max_lot_size
        self.lot_step = lot_step
        self.min_rr_ratio = min_rr_ratio

    def calculate_fixed_fractional(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        symbol: str,
        risk_percent: float | None = None,
    ) -> PositionSize:
        """Calculate position size using fixed fractional method.

        Args:
            account_balance: Current account balance
            entry_price: Planned entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            symbol: Trading symbol
            risk_percent: Risk percentage (uses default if None)

        Returns:
            PositionSize with calculated values
        """
        risk_pct = risk_percent if risk_percent is not None else self.default_risk_percent

        # Calculate stop loss and take profit in pips
        pip_size = self._get_pip_size(symbol)
        sl_pips = abs(entry_price - stop_loss) / pip_size
        tp_pips = abs(take_profit - entry_price) / pip_size

        # Get pip value per lot
        pip_value = self._get_pip_value(symbol)

        # Calculate risk amount
        risk_amount = account_balance * (risk_pct / 100)

        # Calculate lot size: risk_amount / (sl_pips * pip_value)
        if sl_pips > 0 and pip_value > 0:
            lot_size = risk_amount / (sl_pips * pip_value)
        else:
            lot_size = self.min_lot_size

        # Round to lot step and clamp
        lot_size = self._round_lot_size(lot_size)

        # Recalculate actual risk with rounded lot size
        actual_risk = sl_pips * pip_value * lot_size

        # Calculate R:R ratio
        rr_ratio = tp_pips / sl_pips if sl_pips > 0 else 0

        return PositionSize(
            lot_size=lot_size,
            risk_amount=actual_risk,
            risk_percent=actual_risk / account_balance * 100 if account_balance > 0 else 0,
            stop_loss_pips=sl_pips,
            take_profit_pips=tp_pips,
            risk_reward_ratio=round(rr_ratio, 2),
            pip_value=pip_value,
        )

    def calculate_kelly(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        symbol: str,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        kelly_fraction: float = 0.5,
    ) -> PositionSize:
        """Calculate position size using Kelly criterion.

        Uses half-Kelly by default for more conservative sizing.

        Args:
            account_balance: Current account balance
            entry_price: Planned entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            symbol: Trading symbol
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade amount
            avg_loss: Average losing trade amount
            kelly_fraction: Fraction of Kelly to use (default 0.5 = half-Kelly)

        Returns:
            PositionSize with calculated values
        """
        # Kelly formula: f = (bp - q) / b
        # where: b = avg_win / avg_loss, p = win_rate, q = 1 - win_rate
        if avg_loss == 0:
            return self.calculate_fixed_fractional(
                account_balance, entry_price, stop_loss, take_profit, symbol
            )

        b = avg_win / abs(avg_loss)
        p = win_rate
        q = 1 - win_rate

        kelly_percent = ((b * p) - q) / b

        # Apply Kelly fraction and clamp to reasonable range
        risk_percent = max(0.5, min(5.0, kelly_percent * 100 * kelly_fraction))

        logger.debug(
            "Kelly calculation",
            win_rate=win_rate,
            b=b,
            full_kelly=kelly_percent * 100,
            adjusted=risk_percent,
        )

        return self.calculate_fixed_fractional(
            account_balance, entry_price, stop_loss, take_profit, symbol, risk_percent
        )

    def calculate_fixed_lot(
        self,
        lot_size: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        symbol: str,
        account_balance: float,
    ) -> PositionSize:
        """Calculate position details for a fixed lot size.

        Args:
            lot_size: Fixed lot size to use
            entry_price: Planned entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            symbol: Trading symbol
            account_balance: Current account balance

        Returns:
            PositionSize with calculated values
        """
        lot_size = self._round_lot_size(lot_size)

        pip_size = self._get_pip_size(symbol)
        pip_value = self._get_pip_value(symbol)

        sl_pips = abs(entry_price - stop_loss) / pip_size
        tp_pips = abs(take_profit - entry_price) / pip_size

        risk_amount = sl_pips * pip_value * lot_size
        risk_percent = risk_amount / account_balance * 100 if account_balance > 0 else 0

        rr_ratio = tp_pips / sl_pips if sl_pips > 0 else 0

        return PositionSize(
            lot_size=lot_size,
            risk_amount=risk_amount,
            risk_percent=risk_percent,
            stop_loss_pips=sl_pips,
            take_profit_pips=tp_pips,
            risk_reward_ratio=round(rr_ratio, 2),
            pip_value=pip_value,
        )

    def validate_position(self, position: PositionSize) -> tuple[bool, str | None]:
        """Validate a calculated position.

        Args:
            position: PositionSize to validate

        Returns:
            Tuple of (valid, reason_if_invalid)
        """
        # Check minimum R:R ratio
        if position.risk_reward_ratio < self.min_rr_ratio:
            return False, (
                f"R:R ratio {position.risk_reward_ratio} below minimum {self.min_rr_ratio}"
            )

        # Check lot size bounds
        if position.lot_size < self.min_lot_size:
            return False, f"Lot size {position.lot_size} below minimum {self.min_lot_size}"

        if position.lot_size > self.max_lot_size:
            return False, f"Lot size {position.lot_size} exceeds maximum {self.max_lot_size}"

        # Check for valid stop loss
        if position.stop_loss_pips <= 0:
            return False, "Invalid stop loss distance"

        return True, None

    def _get_pip_size(self, symbol: str) -> float:
        """Get pip size for a symbol."""
        # Most forex pairs: 0.0001 (4 decimal places)
        # JPY pairs: 0.01 (2 decimal places)
        # Gold: 0.01
        symbol_upper = symbol.upper()
        if "JPY" in symbol_upper:
            return 0.01
        elif symbol_upper in ["XAUUSD", "GOLD"]:
            return 0.01
        else:
            return 0.0001

    def _get_pip_value(self, symbol: str) -> float:
        """Get pip value per standard lot."""
        symbol_upper = symbol.upper()
        return self.PIP_VALUES.get(symbol_upper, 10.0)

    def _round_lot_size(self, lot_size: float) -> float:
        """Round lot size to valid increment and clamp to bounds."""
        # Round to lot step
        rounded = round(lot_size / self.lot_step) * self.lot_step
        # Clamp to bounds
        return max(self.min_lot_size, min(self.max_lot_size, rounded))

    def calculate_sl_tp_from_atr(
        self,
        entry_price: float,
        atr: float,
        order_type: str,
        sl_multiplier: float = 1.5,
        tp_multiplier: float = 2.0,
    ) -> tuple[float, float]:
        """Calculate SL/TP levels based on ATR.

        Args:
            entry_price: Entry price
            atr: Current ATR value
            order_type: "BUY" or "SELL"
            sl_multiplier: ATR multiplier for stop loss
            tp_multiplier: ATR multiplier for take profit

        Returns:
            Tuple of (stop_loss, take_profit) prices
        """
        sl_distance = atr * sl_multiplier
        tp_distance = atr * tp_multiplier

        if order_type.upper() == "BUY":
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

        return stop_loss, take_profit
