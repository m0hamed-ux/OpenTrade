"""Tests for MT5 connection and order operations."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

import pandas as pd

# Mock MT5 before importing connector
with patch.dict("sys.modules", {"MetaTrader5": MagicMock()}):
    from connectors.mt5_connector import MT5Connector, TradeResult, Position


@pytest.fixture
def mock_mt5():
    """Create mock MT5 module."""
    with patch("connectors.mt5_connector.mt5") as mock:
        # Setup common return values
        mock.TIMEFRAME_M15 = 15
        mock.ORDER_TYPE_BUY = 0
        mock.ORDER_TYPE_SELL = 1
        mock.POSITION_TYPE_BUY = 0
        mock.POSITION_TYPE_SELL = 1
        mock.TRADE_ACTION_DEAL = 1
        mock.TRADE_ACTION_SLTP = 6
        mock.ORDER_TIME_GTC = 0
        mock.ORDER_FILLING_IOC = 1
        mock.TRADE_RETCODE_DONE = 10009

        yield mock


@pytest.fixture
def connector(mock_mt5):
    """Create MT5 connector for testing."""
    return MT5Connector(
        login=12345,
        password="test_password",
        server="TestServer",
    )


class TestMT5Connector:
    """Tests for MT5Connector class."""

    @pytest.mark.asyncio
    async def test_connect_success(self, connector, mock_mt5):
        """Test successful connection."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True

        result = await connector.connect()

        assert result is True
        assert connector._initialized is True
        mock_mt5.initialize.assert_called_once()
        mock_mt5.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_init_failure(self, connector, mock_mt5):
        """Test connection failure during initialization."""
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value = (1, "Init failed")

        result = await connector.connect()

        assert result is False
        assert connector._initialized is False

    @pytest.mark.asyncio
    async def test_connect_login_failure(self, connector, mock_mt5):
        """Test connection failure during login."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = False
        mock_mt5.last_error.return_value = (2, "Login failed")

        result = await connector.connect()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_account_info(self, connector, mock_mt5):
        """Test getting account information."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True

        mock_info = MagicMock()
        mock_info.balance = 10000.0
        mock_info.equity = 10500.0
        mock_info.margin = 100.0
        mock_info.margin_free = 10400.0
        mock_info.margin_level = 10500.0
        mock_info.profit = 500.0
        mock_info.currency = "USD"
        mock_info.leverage = 100

        mock_mt5.account_info.return_value = mock_info

        await connector.connect()
        info = await connector.get_account_info()

        assert info["balance"] == 10000.0
        assert info["equity"] == 10500.0
        assert info["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_get_current_price(self, connector, mock_mt5):
        """Test getting current price."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True

        mock_symbol = MagicMock()
        mock_symbol.name = "EURUSD"
        mock_symbol.bid = 1.0850
        mock_symbol.ask = 1.0852
        mock_symbol.spread = 2
        mock_symbol.digits = 5
        mock_symbol.point = 0.00001
        mock_symbol.volume_min = 0.01
        mock_symbol.volume_max = 100.0
        mock_symbol.volume_step = 0.01
        mock_symbol.trade_mode = 0

        mock_mt5.symbol_info.return_value = mock_symbol

        await connector.connect()
        price = await connector.get_current_price("EURUSD")

        assert price["bid"] == 1.0850
        assert price["ask"] == 1.0852
        assert price["spread"] == 2

    @pytest.mark.asyncio
    async def test_place_order_success(self, connector, mock_mt5):
        """Test successful order placement."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True

        mock_symbol = MagicMock()
        mock_symbol.bid = 1.0850
        mock_symbol.ask = 1.0852
        mock_mt5.symbol_info.return_value = mock_symbol

        mock_result = MagicMock()
        mock_result.retcode = 10009  # TRADE_RETCODE_DONE
        mock_result.order = 123456
        mock_result.price = 1.0852
        mock_result.volume = 0.1
        mock_result.comment = ""

        mock_mt5.order_send.return_value = mock_result

        await connector.connect()
        result = await connector.place_order(
            symbol="EURUSD",
            order_type="BUY",
            volume=0.1,
            sl=1.0800,
            tp=1.0900,
        )

        assert result.success is True
        assert result.order_id == 123456
        assert result.price == 1.0852

    @pytest.mark.asyncio
    async def test_place_order_failure(self, connector, mock_mt5):
        """Test failed order placement."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True

        mock_symbol = MagicMock()
        mock_symbol.bid = 1.0850
        mock_symbol.ask = 1.0852
        mock_mt5.symbol_info.return_value = mock_symbol

        mock_result = MagicMock()
        mock_result.retcode = 10006  # Error code
        mock_result.comment = "Insufficient funds"

        mock_mt5.order_send.return_value = mock_result

        await connector.connect()
        result = await connector.place_order(
            symbol="EURUSD",
            order_type="BUY",
            volume=100.0,
        )

        assert result.success is False
        assert "Insufficient funds" in result.error_message


class TestTradeResult:
    """Tests for TradeResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful trade result."""
        result = TradeResult(
            success=True,
            order_id=123456,
            price=1.0850,
            volume=0.1,
            error_code=None,
            error_message=None,
        )

        assert result.success is True
        assert result.order_id == 123456

    def test_failed_result(self):
        """Test creating a failed trade result."""
        result = TradeResult(
            success=False,
            order_id=None,
            price=None,
            volume=None,
            error_code=10006,
            error_message="Insufficient funds",
        )

        assert result.success is False
        assert result.error_code == 10006
