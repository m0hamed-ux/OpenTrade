"""Account information tools."""

from typing import Any

from connectors.mt5_connector import MT5Connector


# Tool schemas for Gemini function calling
ACCOUNT_TOOLS = [
    {
        "name": "get_balance",
        "description": "Get current account balance",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_equity",
        "description": "Get current account equity (balance + floating P/L)",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_positions",
        "description": "Get all open positions or positions for a specific symbol",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Optional symbol filter",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_account_summary",
        "description": "Get full account summary including balance, equity, margin, and positions",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_daily_stats",
        "description": "Get trading statistics for the current day",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


class AccountTools:
    """Account information tool executor."""

    def __init__(self, connector: MT5Connector):
        """Initialize with MT5 connector.

        Args:
            connector: Connected MT5Connector instance
        """
        self.connector = connector
        self._daily_trades: list[dict] = []
        self._daily_pnl: float = 0.0
        self._starting_balance: float | None = None

    async def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        handlers = {
            "get_balance": self._get_balance,
            "get_equity": self._get_equity,
            "get_positions": self._get_positions,
            "get_account_summary": self._get_account_summary,
            "get_daily_stats": self._get_daily_stats,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return await handler(**args)
        except Exception as e:
            return {"error": str(e)}

    async def _get_balance(self) -> dict[str, Any]:
        """Get current account balance."""
        info = await self.connector.get_account_info()
        return {
            "balance": info["balance"],
            "currency": info["currency"],
        }

    async def _get_equity(self) -> dict[str, Any]:
        """Get current account equity."""
        info = await self.connector.get_account_info()
        return {
            "equity": info["equity"],
            "balance": info["balance"],
            "floating_pnl": info["profit"],
            "currency": info["currency"],
        }

    async def _get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        """Get open positions."""
        positions = await self.connector.get_positions(symbol)

        position_list = []
        total_profit = 0.0

        for pos in positions:
            total_profit += pos.profit
            position_list.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": pos.type,
                "volume": pos.volume,
                "price_open": pos.price_open,
                "price_current": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "time": pos.time.isoformat(),
            })

        return {
            "position_count": len(positions),
            "total_profit": total_profit,
            "positions": position_list,
        }

    async def _get_account_summary(self) -> dict[str, Any]:
        """Get full account summary."""
        info = await self.connector.get_account_info()
        positions = await self.connector.get_positions()

        position_summary = {}
        for pos in positions:
            if pos.symbol not in position_summary:
                position_summary[pos.symbol] = {"count": 0, "volume": 0.0, "profit": 0.0}
            position_summary[pos.symbol]["count"] += 1
            position_summary[pos.symbol]["volume"] += pos.volume
            position_summary[pos.symbol]["profit"] += pos.profit

        return {
            "balance": info["balance"],
            "equity": info["equity"],
            "margin": info["margin"],
            "free_margin": info["free_margin"],
            "margin_level": info["margin_level"],
            "floating_pnl": info["profit"],
            "currency": info["currency"],
            "leverage": info["leverage"],
            "open_positions": len(positions),
            "position_by_symbol": position_summary,
        }

    async def _get_daily_stats(self) -> dict[str, Any]:
        """Get daily trading statistics."""
        info = await self.connector.get_account_info()

        # Initialize starting balance if not set
        if self._starting_balance is None:
            self._starting_balance = info["balance"]

        return {
            "starting_balance": self._starting_balance,
            "current_balance": info["balance"],
            "current_equity": info["equity"],
            "realized_pnl": info["balance"] - self._starting_balance,
            "floating_pnl": info["profit"],
            "total_pnl": info["equity"] - self._starting_balance,
            "trade_count": len(self._daily_trades),
            "currency": info["currency"],
        }

    def record_trade(self, trade_data: dict[str, Any]) -> None:
        """Record a trade for daily statistics.

        Args:
            trade_data: Trade execution data
        """
        self._daily_trades.append(trade_data)
        if "profit" in trade_data:
            self._daily_pnl += trade_data["profit"]

    def reset_daily_stats(self) -> None:
        """Reset daily statistics (call at start of new trading day)."""
        self._daily_trades = []
        self._daily_pnl = 0.0
        self._starting_balance = None

    async def get_full_state(self) -> dict[str, Any]:
        """Get complete account state for orchestrator.

        Returns:
            Comprehensive account state dict
        """
        summary = await self._get_account_summary()
        daily = await self._get_daily_stats()

        return {
            **summary,
            "daily_stats": daily,
        }
