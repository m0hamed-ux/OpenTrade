"""Tests for trading agents."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
import numpy as np


class TestMarketAnalystAgent:
    """Tests for MarketAnalystAgent."""

    @pytest.fixture
    def mock_gemini(self):
        """Create mock Gemini client."""
        mock = MagicMock()
        mock.generate = AsyncMock(return_value='{"symbol": "EURUSD", "timeframe": "M15", "trend": "bullish", "strength": 0.75, "key_levels": {"support": 1.0850, "resistance": 1.0920}, "indicators": {"rsi": 55.0, "macd_signal": "buy", "bb_position": "mid"}, "pattern": null, "summary": "Bullish trend"}')
        return mock

    @pytest.fixture
    def sample_ohlcv(self):
        """Create sample OHLCV data."""
        dates = pd.date_range(start="2024-01-01", periods=100, freq="15min")
        return pd.DataFrame({
            "time": dates,
            "open": np.random.uniform(1.08, 1.09, 100),
            "high": np.random.uniform(1.085, 1.095, 100),
            "low": np.random.uniform(1.075, 1.085, 100),
            "close": np.random.uniform(1.08, 1.09, 100),
            "volume": np.random.randint(100, 1000, 100),
        })

    @pytest.mark.asyncio
    async def test_analyze_returns_valid_structure(self, mock_gemini, sample_ohlcv):
        """Test that analyze returns expected structure."""
        from agents.market_analyst import MarketAnalystAgent

        agent = MarketAnalystAgent(gemini_client=mock_gemini)
        result = await agent.analyze("EURUSD", "M15", sample_ohlcv)

        assert "symbol" in result
        assert "trend" in result
        assert "strength" in result
        assert "key_levels" in result
        assert result["trend"] in ["bullish", "bearish", "sideways"]
        assert 0 <= result["strength"] <= 1


class TestStrategyAgent:
    """Tests for StrategyAgent."""

    @pytest.fixture
    def mock_gemini(self):
        """Create mock Gemini client."""
        mock = MagicMock()
        mock.generate = AsyncMock(return_value='{"signal": "BUY", "confidence": 0.75, "entry_reason": "Strong bullish trend", "invalidation": "Break below support", "suggested_entry": 1.0855}')
        return mock

    @pytest.mark.asyncio
    async def test_generate_signal_buy(self, mock_gemini):
        """Test generating a BUY signal."""
        from agents.strategy_agent import StrategyAgent

        agent = StrategyAgent(gemini_client=mock_gemini)

        market_analysis = {
            "trend": "bullish",
            "strength": 0.8,
            "key_levels": {"support": 1.0850, "resistance": 1.0920},
            "indicators": {"rsi": 55, "macd_signal": "buy"},
            "summary": "Strong bullish momentum",
        }

        sentiment = {
            "sentiment_score": 0.3,
            "interpretation": "bullish",
            "confidence": 0.7,
        }

        result = await agent.generate_signal("EURUSD", market_analysis, sentiment)

        assert result["signal"] in ["BUY", "SELL", "FLAT"]
        assert 0 <= result["confidence"] <= 1
        assert "entry_reason" in result

    @pytest.mark.asyncio
    async def test_low_confidence_forces_flat(self, mock_gemini):
        """Test that low confidence forces FLAT signal."""
        mock_gemini.generate = AsyncMock(return_value='{"signal": "BUY", "confidence": 0.5, "entry_reason": "Weak signal", "invalidation": "N/A", "suggested_entry": null}')

        from agents.strategy_agent import StrategyAgent

        agent = StrategyAgent(gemini_client=mock_gemini, min_confidence=0.65)

        result = await agent.generate_signal(
            "EURUSD",
            {"trend": "sideways", "strength": 0.3, "key_levels": {}, "indicators": {}},
            {"sentiment_score": 0, "interpretation": "neutral", "confidence": 0.3},
        )

        assert result["signal"] == "FLAT"


class TestRiskManagerAgent:
    """Tests for RiskManagerAgent."""

    @pytest.fixture
    def mock_components(self):
        """Create mock components."""
        gemini = MagicMock()
        gemini.generate = AsyncMock(return_value='{"approved": true}')

        from risk.position_sizer import PositionSizer
        from risk.circuit_breaker import CircuitBreaker

        sizer = PositionSizer(
            default_risk_percent=1.0,
            min_rr_ratio=1.5,
        )

        circuit_breaker = CircuitBreaker(
            max_daily_loss_percent=5.0,
            max_trades_per_day=10,
        )
        circuit_breaker.initialize_day(10000.0)

        return gemini, sizer, circuit_breaker

    @pytest.mark.asyncio
    async def test_validate_approved_trade(self, mock_components):
        """Test approving a valid trade."""
        gemini, sizer, circuit_breaker = mock_components

        from agents.risk_manager import RiskManagerAgent

        agent = RiskManagerAgent(
            gemini_client=gemini,
            position_sizer=sizer,
            circuit_breaker=circuit_breaker,
        )

        result = await agent.validate_and_size(
            symbol="EURUSD",
            signal={"signal": "BUY", "confidence": 0.8, "entry_reason": "Test"},
            market_analysis={
                "indicators": {"atr": {"value": 0.001}},
                "key_levels": {"support": 1.0850, "resistance": 1.0920},
            },
            account_state={"balance": 10000, "equity": 10000, "open_positions": 0},
            current_price={"bid": 1.0850, "ask": 1.0852},
        )

        assert result["approved"] is True
        assert result["lot_size"] > 0
        assert result["risk_percent"] <= 2.0

    @pytest.mark.asyncio
    async def test_reject_flat_signal(self, mock_components):
        """Test rejecting a FLAT signal."""
        gemini, sizer, circuit_breaker = mock_components

        from agents.risk_manager import RiskManagerAgent

        agent = RiskManagerAgent(
            gemini_client=gemini,
            position_sizer=sizer,
            circuit_breaker=circuit_breaker,
        )

        result = await agent.validate_and_size(
            symbol="EURUSD",
            signal={"signal": "FLAT", "confidence": 0.3, "entry_reason": "No setup"},
            market_analysis={},
            account_state={"balance": 10000, "equity": 10000, "open_positions": 0},
            current_price={"bid": 1.0850, "ask": 1.0852},
        )

        assert result["approved"] is False
        assert "FLAT" in result["rejection_reason"]


class TestSentimentAgent:
    """Tests for SentimentAgent."""

    @pytest.fixture
    def mock_components(self):
        """Create mock components."""
        gemini = MagicMock()
        gemini.generate = AsyncMock(return_value='{"symbol": "EURUSD", "sentiment_score": 0.3, "interpretation": "bullish", "confidence": 0.6, "headline_count": 5, "key_themes": ["central_bank"], "high_impact_events": [], "summary": "Bullish sentiment"}')

        news = MagicMock()
        news.fetch_headlines = AsyncMock(return_value=[
            {"title": "Markets rally on positive data", "description": "..."},
        ])
        news.get_economic_calendar = AsyncMock(return_value=[])

        return gemini, news

    @pytest.mark.asyncio
    async def test_analyze_sentiment(self, mock_components):
        """Test sentiment analysis."""
        gemini, news = mock_components

        from agents.sentiment_agent import SentimentAgent

        agent = SentimentAgent(gemini_client=gemini, news_connector=news)
        result = await agent.analyze("EURUSD")

        assert "sentiment_score" in result
        assert -1 <= result["sentiment_score"] <= 1
        assert result["interpretation"] in [
            "very_bullish", "bullish", "neutral", "bearish", "very_bearish"
        ]
