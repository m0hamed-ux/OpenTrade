"""MT5 tools for Gemini function calling."""

from typing import Any

from connectors.mt5_connector import MT5Connector


# Tool schemas for Gemini function calling
MT5_TOOLS = [
    {
        "name": "get_price",
        "description": "Get the current bid/ask price for a trading symbol",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol (e.g., EURUSD, GBPUSD)",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_ohlcv",
        "description": "Get OHLCV candlestick data for technical analysis",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol",
                },
                "timeframe": {
                    "type": "string",
                    "description": "Timeframe (M1, M5, M15, M30, H1, H4, D1)",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of candles to fetch (default 100)",
                },
            },
            "required": ["symbol", "timeframe"],
        },
    },
    {
        "name": "place_order",
        "description": "Place a market order to buy or sell",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol",
                },
                "order_type": {
                    "type": "string",
                    "description": "Order type: BUY or SELL",
                },
                "volume": {
                    "type": "number",
                    "description": "Lot size",
                },
                "sl": {
                    "type": "number",
                    "description": "Stop loss price (optional)",
                },
                "tp": {
                    "type": "number",
                    "description": "Take profit price (optional)",
                },
                "comment": {
                    "type": "string",
                    "description": "Order comment (optional)",
                },
            },
            "required": ["symbol", "order_type", "volume"],
        },
    },
    {
        "name": "modify_position",
        "description": "Modify stop loss or take profit of an open position",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket": {
                    "type": "integer",
                    "description": "Position ticket number",
                },
                "sl": {
                    "type": "number",
                    "description": "New stop loss price",
                },
                "tp": {
                    "type": "number",
                    "description": "New take profit price",
                },
            },
            "required": ["ticket"],
        },
    },
    {
        "name": "close_position",
        "description": "Close an open position",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket": {
                    "type": "integer",
                    "description": "Position ticket number to close",
                },
            },
            "required": ["ticket"],
        },
    },
]


class MT5Tools:
    """MT5 tool executor for agent function calls."""

    def __init__(self, connector: MT5Connector):
        """Initialize with MT5 connector.

        Args:
            connector: Connected MT5Connector instance
        """
        self.connector = connector

    async def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        handlers = {
            "get_price": self._get_price,
            "get_ohlcv": self._get_ohlcv,
            "place_order": self._place_order,
            "modify_position": self._modify_position,
            "close_position": self._close_position,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return await handler(**args)
        except Exception as e:
            return {"error": str(e)}

    async def _get_price(self, symbol: str) -> dict[str, Any]:
        """Get current price for a symbol."""
        price = await self.connector.get_current_price(symbol)
        if price is None:
            return {"error": f"Symbol {symbol} not found"}
        return {"symbol": symbol, **price}

    async def _get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> dict[str, Any]:
        """Get OHLCV data."""
        df = await self.connector.get_ohlcv(symbol, timeframe, count)
        # Convert to list of dicts for JSON serialization
        candles = df.to_dict("records")
        # Convert timestamps to strings
        for candle in candles:
            candle["time"] = candle["time"].isoformat()
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": candles,
        }

    async def _place_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: float | None = None,
        tp: float | None = None,
        comment: str = "",
    ) -> dict[str, Any]:
        """Place a market order."""
        result = await self.connector.place_order(
            symbol=symbol,
            order_type=order_type,
            volume=volume,
            sl=sl,
            tp=tp,
            comment=comment,
        )
        return {
            "success": result.success,
            "order_id": result.order_id,
            "price": result.price,
            "volume": result.volume,
            "error": result.error_message,
        }

    async def _modify_position(
        self,
        ticket: int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> dict[str, Any]:
        """Modify position SL/TP."""
        result = await self.connector.modify_position(ticket, sl, tp)
        return {
            "success": result.success,
            "ticket": ticket,
            "error": result.error_message,
        }

    async def _close_position(self, ticket: int) -> dict[str, Any]:
        """Close a position."""
        result = await self.connector.close_position(ticket)
        return {
            "success": result.success,
            "order_id": result.order_id,
            "price": result.price,
            "error": result.error_message,
        }
