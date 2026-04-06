"""Execution Agent - MT5 Order Execution."""

from typing import Any
from datetime import datetime

from connectors.mt5_connector import MT5Connector, TradeResult
from tools.mt5_tools import MT5Tools
from memory.agent_memory import AgentMemory
from config.logging_config import get_logger

logger = get_logger(__name__)


class ExecutionAgent:
    """Agent responsible for executing trades on MT5."""

    def __init__(
        self,
        mt5_connector: MT5Connector,
        memory: AgentMemory | None = None,
        max_slippage_pips: float = 3.0,
        magic_number: int = 123456,
    ):
        """Initialize execution agent.

        Args:
            mt5_connector: MT5 connector instance
            memory: Optional agent memory
            max_slippage_pips: Maximum acceptable slippage in pips
            magic_number: Magic number for order identification
        """
        self.mt5 = mt5_connector
        self.mt5_tools = MT5Tools(mt5_connector)
        self.memory = memory
        self.max_slippage_pips = max_slippage_pips
        self.magic_number = magic_number

    async def execute_trade(
        self,
        symbol: str,
        signal: dict[str, Any],
        risk_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a trade based on approved parameters.

        Args:
            symbol: Trading symbol
            signal: Strategy signal
            risk_params: Approved risk parameters

        Returns:
            Execution result dict
        """
        if not risk_params.get("approved", False):
            return {
                "success": False,
                "error": "Trade not approved by risk manager",
                "order_id": None,
                "executed_price": None,
                "executed_volume": None,
                "sl_set": None,
                "tp_set": None,
                "timestamp": datetime.utcnow().isoformat(),
            }

        order_type = signal["signal"]
        lot_size = risk_params["lot_size"]
        stop_loss = risk_params["stop_loss"]
        take_profit = risk_params["take_profit"]

        logger.info(
            "Executing trade",
            symbol=symbol,
            type=order_type,
            lots=lot_size,
            sl=stop_loss,
            tp=take_profit,
        )

        # Get current price to check slippage
        current_price = await self.mt5.get_current_price(symbol)
        if not current_price:
            return self._error_result(f"Unable to get current price for {symbol}")

        # Validate price hasn't moved too much
        expected_entry = signal.get("suggested_entry")
        if expected_entry:
            actual_entry = current_price["ask"] if order_type == "BUY" else current_price["bid"]
            slippage = abs(actual_entry - expected_entry)

            # Get pip size for symbol
            pip_size = 0.0001 if "JPY" not in symbol.upper() else 0.01
            slippage_pips = slippage / pip_size

            if slippage_pips > self.max_slippage_pips:
                logger.warning(
                    "Price slippage too high",
                    expected=expected_entry,
                    actual=actual_entry,
                    slippage_pips=slippage_pips,
                )
                return self._error_result(
                    f"Price slippage {slippage_pips:.1f} pips exceeds max {self.max_slippage_pips}"
                )

        # Check spread
        spread = current_price.get("spread", 0)
        max_spread = 30  # Maximum acceptable spread in points

        if spread > max_spread:
            logger.warning("Spread too wide", spread=spread)
            return self._error_result(f"Spread {spread} points exceeds maximum {max_spread}")

        # Execute the order
        comment = f"OpenTrade_{signal['signal']}_{datetime.now().strftime('%H%M')}"

        result = await self.mt5.place_order(
            symbol=symbol,
            order_type=order_type,
            volume=lot_size,
            sl=stop_loss,
            tp=take_profit,
            comment=comment,
            magic=self.magic_number,
        )

        if not result.success:
            logger.error(
                "Order execution failed",
                error_code=result.error_code,
                error_msg=result.error_message,
            )
            return self._error_result(result.error_message or "Unknown execution error")

        execution_result = {
            "success": True,
            "order_id": result.order_id,
            "executed_price": result.price,
            "executed_volume": result.volume,
            "sl_set": stop_loss,
            "tp_set": take_profit,
            "error": None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Store execution in memory
        if self.memory:
            await self.memory.store(
                memory_type="decision",
                content={
                    "type": "execution",
                    "symbol": symbol,
                    "signal": order_type,
                    **execution_result,
                },
                symbol=symbol,
                ttl_minutes=60 * 24,  # Keep for 24 hours
            )

        logger.info(
            "Trade executed successfully",
            order_id=result.order_id,
            price=result.price,
            volume=result.volume,
        )

        return execution_result

    async def modify_position(
        self,
        ticket: int,
        new_sl: float | None = None,
        new_tp: float | None = None,
    ) -> dict[str, Any]:
        """Modify an existing position's SL/TP.

        Args:
            ticket: Position ticket
            new_sl: New stop loss
            new_tp: New take profit

        Returns:
            Modification result
        """
        result = await self.mt5.modify_position(ticket, sl=new_sl, tp=new_tp)

        if not result.success:
            return {
                "success": False,
                "error": result.error_message,
                "ticket": ticket,
            }

        logger.info(
            "Position modified",
            ticket=ticket,
            new_sl=new_sl,
            new_tp=new_tp,
        )

        return {
            "success": True,
            "ticket": ticket,
            "new_sl": new_sl,
            "new_tp": new_tp,
            "error": None,
        }

    async def close_position(
        self,
        ticket: int,
        reason: str = "Manual close",
    ) -> dict[str, Any]:
        """Close an open position.

        Args:
            ticket: Position ticket
            reason: Reason for closing

        Returns:
            Close result
        """
        # Get position info first
        positions = await self.mt5.get_positions()
        position = next((p for p in positions if p.ticket == ticket), None)

        if not position:
            return {
                "success": False,
                "error": f"Position {ticket} not found",
                "ticket": ticket,
            }

        result = await self.mt5.close_position(ticket)

        if not result.success:
            return {
                "success": False,
                "error": result.error_message,
                "ticket": ticket,
            }

        close_result = {
            "success": True,
            "ticket": ticket,
            "close_price": result.price,
            "profit": position.profit,
            "reason": reason,
            "error": None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Store in memory
        if self.memory:
            await self.memory.store(
                memory_type="decision",
                content={
                    "type": "position_close",
                    **close_result,
                },
                symbol=position.symbol,
                ttl_minutes=60 * 24,
            )

        logger.info(
            "Position closed",
            ticket=ticket,
            profit=position.profit,
            reason=reason,
        )

        return close_result

    async def verify_execution(
        self,
        order_id: int,
        expected_symbol: str,
        expected_type: str,
    ) -> dict[str, Any]:
        """Verify that an order was executed correctly.

        Args:
            order_id: Order ID to verify
            expected_symbol: Expected symbol
            expected_type: Expected order type

        Returns:
            Verification result
        """
        # Get current positions to find the order
        positions = await self.mt5.get_positions()

        # Find position matching the order
        matching = [
            p for p in positions
            if p.symbol == expected_symbol and p.type == expected_type
        ]

        if not matching:
            return {
                "verified": False,
                "error": "No matching position found",
                "order_id": order_id,
            }

        # Assume the most recent matching position is ours
        position = max(matching, key=lambda p: p.time)

        return {
            "verified": True,
            "ticket": position.ticket,
            "symbol": position.symbol,
            "type": position.type,
            "volume": position.volume,
            "entry_price": position.price_open,
            "current_price": position.price_current,
            "sl": position.sl,
            "tp": position.tp,
            "error": None,
        }

    def _error_result(self, error: str) -> dict[str, Any]:
        """Create an error result dict."""
        return {
            "success": False,
            "error": error,
            "order_id": None,
            "executed_price": None,
            "executed_volume": None,
            "sl_set": None,
            "tp_set": None,
            "timestamp": datetime.utcnow().isoformat(),
        }
