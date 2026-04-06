"""MetaTrader 5 connector wrapper class."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from enum import IntEnum

import MetaTrader5 as mt5
import pandas as pd

from config.logging_config import get_logger

logger = get_logger(__name__)


class OrderType(IntEnum):
    """MT5 Order types."""
    BUY = mt5.ORDER_TYPE_BUY
    SELL = mt5.ORDER_TYPE_SELL
    BUY_LIMIT = mt5.ORDER_TYPE_BUY_LIMIT
    SELL_LIMIT = mt5.ORDER_TYPE_SELL_LIMIT
    BUY_STOP = mt5.ORDER_TYPE_BUY_STOP
    SELL_STOP = mt5.ORDER_TYPE_SELL_STOP


class Timeframe(IntEnum):
    """MT5 Timeframes."""
    M1 = mt5.TIMEFRAME_M1
    M5 = mt5.TIMEFRAME_M5
    M15 = mt5.TIMEFRAME_M15
    M30 = mt5.TIMEFRAME_M30
    H1 = mt5.TIMEFRAME_H1
    H4 = mt5.TIMEFRAME_H4
    D1 = mt5.TIMEFRAME_D1
    W1 = mt5.TIMEFRAME_W1
    MN1 = mt5.TIMEFRAME_MN1


TIMEFRAME_MAP = {
    "M1": Timeframe.M1,
    "M5": Timeframe.M5,
    "M15": Timeframe.M15,
    "M30": Timeframe.M30,
    "H1": Timeframe.H1,
    "H4": Timeframe.H4,
    "D1": Timeframe.D1,
    "W1": Timeframe.W1,
    "MN1": Timeframe.MN1,
}


@dataclass
class TradeResult:
    """Result of a trade operation."""
    success: bool
    order_id: int | None
    price: float | None
    volume: float | None
    error_code: int | None
    error_message: str | None


@dataclass
class Position:
    """Open position data."""
    ticket: int
    symbol: str
    type: str
    volume: float
    price_open: float
    price_current: float
    sl: float
    tp: float
    profit: float
    time: datetime


class MT5Connector:
    """MetaTrader 5 Python bridge wrapper."""

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: str | None = None,
    ):
        """Initialize MT5 connector.

        Args:
            login: MT5 account login
            password: MT5 account password
            server: Broker server name
            path: Path to MT5 terminal executable (optional)
        """
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self._initialized = False
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Initialize connection to MT5 terminal.

        Returns:
            True if connection successful
        """
        async with self._lock:
            if self._initialized:
                return True

            # Run MT5 initialization in thread pool (blocking call)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._initialize)
            return result

    def _initialize(self) -> bool:
        """Synchronous MT5 initialization."""
        init_kwargs = {}
        if self.path:
            init_kwargs["path"] = self.path

        if not mt5.initialize(**init_kwargs):
            error = mt5.last_error()
            logger.error("MT5 initialization failed", error_code=error[0], error_msg=error[1])
            return False

        # Login to account
        if not mt5.login(self.login, password=self.password, server=self.server):
            error = mt5.last_error()
            logger.error("MT5 login failed", error_code=error[0], error_msg=error[1])
            mt5.shutdown()
            return False

        self._initialized = True
        logger.info("MT5 connected", account=self.login, server=self.server)
        return True

    async def disconnect(self) -> None:
        """Shutdown MT5 connection."""
        async with self._lock:
            if self._initialized:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, mt5.shutdown)
                self._initialized = False
                logger.info("MT5 disconnected")

    async def get_account_info(self) -> dict[str, Any]:
        """Get current account information.

        Returns:
            Account info dict with balance, equity, margin, etc.
        """
        if not self._initialized:
            raise RuntimeError("MT5 not connected")

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, mt5.account_info)

        if info is None:
            error = mt5.last_error()
            raise RuntimeError(f"Failed to get account info: {error}")

        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "profit": info.profit,
            "currency": info.currency,
            "leverage": info.leverage,
        }

    async def get_symbol_info(self, symbol: str) -> dict[str, Any] | None:
        """Get symbol information.

        Args:
            symbol: Trading symbol (e.g., "EURUSD")

        Returns:
            Symbol info dict or None if not found
        """
        if not self._initialized:
            raise RuntimeError("MT5 not connected")

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, mt5.symbol_info, symbol)

        if info is None:
            return None

        return {
            "symbol": info.name,
            "bid": info.bid,
            "ask": info.ask,
            "spread": info.spread,
            "digits": info.digits,
            "point": info.point,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_mode": info.trade_mode,
        }

    async def get_current_price(self, symbol: str) -> dict[str, float] | None:
        """Get current bid/ask price for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Dict with bid, ask, spread or None
        """
        info = await self.get_symbol_info(symbol)
        if info is None:
            return None

        return {
            "bid": info["bid"],
            "ask": info["ask"],
            "spread": info["spread"],
        }

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> pd.DataFrame:
        """Get OHLCV candle data.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe string (M1, M5, M15, H1, etc.)
            count: Number of candles to fetch

        Returns:
            DataFrame with columns: time, open, high, low, close, volume
        """
        if not self._initialized:
            raise RuntimeError("MT5 not connected")

        tf = TIMEFRAME_MAP.get(timeframe.upper())
        if tf is None:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        loop = asyncio.get_event_loop()
        rates = await loop.run_in_executor(
            None,
            lambda: mt5.copy_rates_from_pos(symbol, tf, 0, count)
        )

        if rates is None or len(rates) == 0:
            error = mt5.last_error()
            raise RuntimeError(f"Failed to get OHLCV data: {error}")

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df[["time", "open", "high", "low", "close", "tick_volume"]]
        df = df.rename(columns={"tick_volume": "volume"})

        return df

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        """Get open positions.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of Position objects
        """
        if not self._initialized:
            raise RuntimeError("MT5 not connected")

        loop = asyncio.get_event_loop()

        if symbol:
            positions = await loop.run_in_executor(
                None,
                lambda: mt5.positions_get(symbol=symbol)
            )
        else:
            positions = await loop.run_in_executor(None, mt5.positions_get)

        if positions is None:
            return []

        result = []
        for pos in positions:
            result.append(Position(
                ticket=pos.ticket,
                symbol=pos.symbol,
                type="BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                volume=pos.volume,
                price_open=pos.price_open,
                price_current=pos.price_current,
                sl=pos.sl,
                tp=pos.tp,
                profit=pos.profit,
                time=datetime.fromtimestamp(pos.time),
            ))

        return result

    async def place_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        price: float | None = None,
        sl: float | None = None,
        tp: float | None = None,
        comment: str = "",
        magic: int = 0,
    ) -> TradeResult:
        """Place a trade order.

        Args:
            symbol: Trading symbol
            order_type: "BUY" or "SELL"
            volume: Lot size
            price: Entry price (None for market orders)
            sl: Stop loss price
            tp: Take profit price
            comment: Order comment
            magic: Magic number for EA identification

        Returns:
            TradeResult with order details
        """
        if not self._initialized:
            raise RuntimeError("MT5 not connected")

        # Get symbol info for price if not provided
        info = await self.get_symbol_info(symbol)
        if info is None:
            return TradeResult(
                success=False,
                order_id=None,
                price=None,
                volume=None,
                error_code=-1,
                error_message=f"Symbol {symbol} not found",
            )

        # Determine order type and price
        if order_type.upper() == "BUY":
            mt5_type = mt5.ORDER_TYPE_BUY
            entry_price = price if price else info["ask"]
        elif order_type.upper() == "SELL":
            mt5_type = mt5.ORDER_TYPE_SELL
            entry_price = price if price else info["bid"]
        else:
            return TradeResult(
                success=False,
                order_id=None,
                price=None,
                volume=None,
                error_code=-1,
                error_message=f"Invalid order type: {order_type}",
            )

        # Build request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": entry_price,
            "deviation": 20,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        if sl:
            request["sl"] = sl
        if tp:
            request["tp"] = tp

        # Execute order
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, mt5.order_send, request)

        if result is None:
            error = mt5.last_error()
            return TradeResult(
                success=False,
                order_id=None,
                price=None,
                volume=None,
                error_code=error[0],
                error_message=error[1],
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return TradeResult(
                success=False,
                order_id=None,
                price=None,
                volume=None,
                error_code=result.retcode,
                error_message=result.comment,
            )

        logger.info(
            "Order placed",
            order_id=result.order,
            symbol=symbol,
            type=order_type,
            volume=volume,
            price=result.price,
        )

        return TradeResult(
            success=True,
            order_id=result.order,
            price=result.price,
            volume=result.volume,
            error_code=None,
            error_message=None,
        )

    async def modify_position(
        self,
        ticket: int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> TradeResult:
        """Modify an open position's SL/TP.

        Args:
            ticket: Position ticket number
            sl: New stop loss price
            tp: New take profit price

        Returns:
            TradeResult
        """
        if not self._initialized:
            raise RuntimeError("MT5 not connected")

        # Get position info
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(
            None,
            lambda: mt5.positions_get(ticket=ticket)
        )

        if not positions:
            return TradeResult(
                success=False,
                order_id=None,
                price=None,
                volume=None,
                error_code=-1,
                error_message=f"Position {ticket} not found",
            )

        pos = positions[0]

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": sl if sl is not None else pos.sl,
            "tp": tp if tp is not None else pos.tp,
        }

        result = await loop.run_in_executor(None, mt5.order_send, request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = mt5.last_error() if result is None else (result.retcode, result.comment)
            return TradeResult(
                success=False,
                order_id=None,
                price=None,
                volume=None,
                error_code=error[0],
                error_message=str(error[1]),
            )

        return TradeResult(
            success=True,
            order_id=ticket,
            price=None,
            volume=None,
            error_code=None,
            error_message=None,
        )

    async def close_position(self, ticket: int) -> TradeResult:
        """Close an open position.

        Args:
            ticket: Position ticket number

        Returns:
            TradeResult
        """
        if not self._initialized:
            raise RuntimeError("MT5 not connected")

        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(
            None,
            lambda: mt5.positions_get(ticket=ticket)
        )

        if not positions:
            return TradeResult(
                success=False,
                order_id=None,
                price=None,
                volume=None,
                error_code=-1,
                error_message=f"Position {ticket} not found",
            )

        pos = positions[0]
        symbol_info = await self.get_symbol_info(pos.symbol)

        # Determine close price and type
        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            close_price = symbol_info["bid"]
        else:
            close_type = mt5.ORDER_TYPE_BUY
            close_price = symbol_info["ask"]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": close_price,
            "deviation": 20,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = await loop.run_in_executor(None, mt5.order_send, request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = mt5.last_error() if result is None else (result.retcode, result.comment)
            return TradeResult(
                success=False,
                order_id=None,
                price=None,
                volume=None,
                error_code=error[0],
                error_message=str(error[1]),
            )

        logger.info("Position closed", ticket=ticket, profit=pos.profit)

        return TradeResult(
            success=True,
            order_id=result.order,
            price=result.price,
            volume=result.volume,
            error_code=None,
            error_message=None,
        )
