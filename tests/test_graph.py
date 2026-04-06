"""Tests for the LangGraph trading workflow."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
import numpy as np


class TestTradingState:
    """Tests for TradingState schema."""

    def test_create_initial_state(self):
        """Test creating initial state."""
        from graph.state import create_initial_state

        state = create_initial_state(
            symbol="EURUSD",
            timeframe="M15",
            account={"balance": 10000, "equity": 10000},
            ohlcv=[{"time": "2024-01-01", "open": 1.08, "close": 1.09}],
        )

        assert state["symbol"] == "EURUSD"
        assert state["timeframe"] == "M15"
        assert state["account"]["balance"] == 10000
        assert len(state["ohlcv"]) == 1
        assert state["market_analysis"] is None
        assert state["should_continue"] is True

    def test_update_state(self):
        """Test updating state."""
        from graph.state import create_initial_state, update_state

        state = create_initial_state(
            symbol="EURUSD",
            timeframe="M15",
            account={"balance": 10000},
            ohlcv=[],
        )

        updated = update_state(
            state,
            market_analysis={"trend": "bullish"},
            node_name="test_node",
        )

        assert updated["market_analysis"]["trend"] == "bullish"
        assert "test_node" in updated["cycle_log"]["nodes_visited"]


class TestTradingGraph:
    """Tests for TradingGraph workflow."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for the graph."""
        gemini = MagicMock()
        gemini.generate = AsyncMock(return_value='{"approved": true}')

        # Mock MT5
        mt5 = MagicMock()
        mt5.connect = AsyncMock(return_value=True)
        mt5.disconnect = AsyncMock()
        mt5.get_account_info = AsyncMock(return_value={
            "balance": 10000,
            "equity": 10000,
            "margin": 0,
            "free_margin": 10000,
            "margin_level": 0,
            "profit": 0,
            "currency": "USD",
            "leverage": 100,
        })
        mt5.get_positions = AsyncMock(return_value=[])
        mt5.get_current_price = AsyncMock(return_value={
            "bid": 1.0850,
            "ask": 1.0852,
            "spread": 2,
        })
        mt5.get_ohlcv = AsyncMock(return_value=pd.DataFrame({
            "time": pd.date_range(start="2024-01-01", periods=100, freq="15min"),
            "open": np.random.uniform(1.08, 1.09, 100),
            "high": np.random.uniform(1.085, 1.095, 100),
            "low": np.random.uniform(1.075, 1.085, 100),
            "close": np.random.uniform(1.08, 1.09, 100),
            "volume": np.random.randint(100, 1000, 100),
        }))
        mt5.place_order = AsyncMock(return_value=MagicMock(
            success=True,
            order_id=123456,
            price=1.0852,
            volume=0.1,
            error_code=None,
            error_message=None,
        ))

        # Mock news
        news = MagicMock()
        news.fetch_headlines = AsyncMock(return_value=[])
        news.get_economic_calendar = AsyncMock(return_value=[])

        # Risk components
        from risk.circuit_breaker import CircuitBreaker
        from risk.position_sizer import PositionSizer

        circuit_breaker = CircuitBreaker()
        circuit_breaker.initialize_day(10000.0)

        position_sizer = PositionSizer()

        # Journal
        journal = MagicMock()
        journal.initialize = AsyncMock()
        journal.log_cycle = AsyncMock()
        journal.record_trade = AsyncMock()

        settings = {
            "trading": {
                "symbols": ["EURUSD"],
                "timeframe": "M15",
                "candle_count": 100,
            },
            "risk": {
                "max_risk_percent": 2.0,
                "min_rr_ratio": 1.5,
            },
            "confidence": {
                "min_signal_confidence": 0.65,
            },
            "models": {},
        }

        return {
            "gemini": gemini,
            "mt5": mt5,
            "news": news,
            "circuit_breaker": circuit_breaker,
            "position_sizer": position_sizer,
            "journal": journal,
            "settings": settings,
        }

    def test_graph_creation(self, mock_dependencies):
        """Test that the graph can be created."""
        from graph.trading_graph import TradingGraph

        graph = TradingGraph(
            gemini_client=mock_dependencies["gemini"],
            mt5_connector=mock_dependencies["mt5"],
            news_connector=mock_dependencies["news"],
            circuit_breaker=mock_dependencies["circuit_breaker"],
            position_sizer=mock_dependencies["position_sizer"],
            journal=mock_dependencies["journal"],
            settings=mock_dependencies["settings"],
        )

        assert graph.graph is not None

    @pytest.mark.asyncio
    async def test_should_continue_routing(self, mock_dependencies):
        """Test conditional routing based on should_continue."""
        from graph.trading_graph import TradingGraph
        from graph.state import create_initial_state

        graph = TradingGraph(
            gemini_client=mock_dependencies["gemini"],
            mt5_connector=mock_dependencies["mt5"],
            news_connector=mock_dependencies["news"],
            circuit_breaker=mock_dependencies["circuit_breaker"],
            position_sizer=mock_dependencies["position_sizer"],
            journal=mock_dependencies["journal"],
            settings=mock_dependencies["settings"],
        )

        # Test continue path
        state_continue = create_initial_state(
            symbol="EURUSD",
            timeframe="M15",
            account={"balance": 10000, "equity": 10000},
            ohlcv=[],
        )
        state_continue["should_continue"] = True

        result = graph._should_continue_after_preconditions(state_continue)
        assert result == "continue"

        # Test end path
        state_end = create_initial_state(
            symbol="EURUSD",
            timeframe="M15",
            account={"balance": 10000, "equity": 10000},
            ohlcv=[],
        )
        state_end["should_continue"] = False

        result = graph._should_continue_after_preconditions(state_end)
        assert result == "end"

    @pytest.mark.asyncio
    async def test_flat_signal_ends_early(self, mock_dependencies):
        """Test that FLAT signal causes early termination."""
        from graph.trading_graph import TradingGraph
        from graph.state import create_initial_state

        graph = TradingGraph(
            gemini_client=mock_dependencies["gemini"],
            mt5_connector=mock_dependencies["mt5"],
            news_connector=mock_dependencies["news"],
            circuit_breaker=mock_dependencies["circuit_breaker"],
            position_sizer=mock_dependencies["position_sizer"],
            journal=mock_dependencies["journal"],
            settings=mock_dependencies["settings"],
        )

        state = create_initial_state(
            symbol="EURUSD",
            timeframe="M15",
            account={"balance": 10000, "equity": 10000},
            ohlcv=[],
        )
        state["signal"] = {"signal": "FLAT", "confidence": 0.3}

        result = graph._should_continue_after_signal(state)
        assert result == "end"
