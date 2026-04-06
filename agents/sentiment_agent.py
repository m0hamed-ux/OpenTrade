"""Sentiment Agent - News and Market Sentiment Analysis."""

from typing import Any

from connectors.gemini_client import GeminiClient
from connectors.news_connector import NewsConnector
from tools.news_tools import NewsTools
from memory.agent_memory import AgentMemory
from config.logging_config import get_logger
from utils.formatters import format_sentiment_for_prompt
from utils.validators import extract_json_from_response

from .prompts import SENTIMENT_SYSTEM

logger = get_logger(__name__)


class SentimentAgent:
    """Agent that analyzes news and market sentiment."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        news_connector: NewsConnector,
        memory: AgentMemory | None = None,
        model: str = "gemini-2.5-flash",
    ):
        """Initialize sentiment agent.

        Args:
            gemini_client: Gemini API client
            news_connector: News API connector
            memory: Optional agent memory for context
            model: Gemini model to use
        """
        self.gemini = gemini_client
        self.news_tools = NewsTools(news_connector)
        self.memory = memory
        self.model = model

    async def analyze(self, symbol: str) -> dict[str, Any]:
        """Analyze sentiment for a trading symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Sentiment analysis dict
        """
        logger.info("Starting sentiment analysis", symbol=symbol)

        # Get full sentiment data from news tools
        sentiment_data = await self.news_tools.get_full_sentiment(symbol)

        # If no headlines available, return neutral sentiment
        if sentiment_data["headline_count"] == 0:
            logger.info("No headlines available, returning neutral sentiment", symbol=symbol)
            return {
                "symbol": symbol,
                "sentiment_score": 0.0,
                "interpretation": "neutral",
                "confidence": 0.1,
                "headline_count": 0,
                "key_themes": [],
                "high_impact_events": [],
                "summary": "No recent news available for sentiment analysis.",
            }

        # Format for AI analysis
        sentiment_context = format_sentiment_for_prompt(sentiment_data)

        # Build prompt for deeper analysis
        prompt = f"""
Analyze the following sentiment data for {symbol}:

{sentiment_context}

Raw sentiment score from keyword analysis: {sentiment_data['sentiment']['score']:.2f}

Based on the headlines and context, provide a refined sentiment analysis.
Consider:
1. The actual impact of the headlines on the currency pair
2. Whether the keyword-based score seems accurate
3. Any themes or patterns in the news
4. Upcoming events that could impact sentiment

Respond ONLY with valid JSON matching the required schema.
"""

        response = await self.gemini.generate(
            prompt=prompt,
            model_name=self.model,
            system_instruction=SENTIMENT_SYSTEM,
            temperature=0.3,
            response_format="json",
        )

        # Parse response
        import json
        try:
            json_str = extract_json_from_response(response)
            if json_str:
                analysis = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Sentiment analysis parse failed, using keyword scores", error=str(e))
            analysis = {
                "symbol": symbol,
                "sentiment_score": sentiment_data["sentiment"]["score"],
                "interpretation": sentiment_data["sentiment"]["interpretation"],
                "confidence": sentiment_data["sentiment"]["confidence"],
                "headline_count": sentiment_data["headline_count"],
                "key_themes": [],
                "high_impact_events": [],
                "summary": "Using keyword-based sentiment analysis.",
            }

        # Ensure required fields
        analysis.setdefault("symbol", symbol)
        analysis.setdefault("sentiment_score", 0.0)
        analysis.setdefault("interpretation", "neutral")
        analysis.setdefault("confidence", 0.5)
        analysis.setdefault("headline_count", sentiment_data["headline_count"])
        analysis.setdefault("key_themes", [])
        analysis.setdefault("high_impact_events", [])
        analysis.setdefault("summary", "")

        # Store in memory if available
        if self.memory:
            await self.memory.store(
                memory_type="observation",
                content=analysis,
                symbol=symbol,
                ttl_minutes=60,  # Sentiment valid for 1 hour
            )

        logger.info(
            "Sentiment analysis complete",
            symbol=symbol,
            score=analysis["sentiment_score"],
            interpretation=analysis["interpretation"],
        )

        return analysis

    async def check_high_impact_events(self, symbol: str) -> list[dict[str, Any]]:
        """Check for upcoming high-impact events.

        Args:
            symbol: Trading symbol

        Returns:
            List of high-impact events
        """
        # Get economic calendar
        calendar = await self.news_tools.execute(
            "get_economic_calendar",
            {"days_ahead": 1}
        )

        events = calendar.get("events", [])

        # Filter for relevant events based on symbol
        currencies = self._get_currencies(symbol)
        relevant_events = []

        for event in events:
            event_currency = event.get("currency", "")
            if event_currency in currencies:
                relevant_events.append(event)

        return relevant_events

    def _get_currencies(self, symbol: str) -> list[str]:
        """Extract currency codes from a symbol.

        Args:
            symbol: Trading symbol like EURUSD

        Returns:
            List of currency codes
        """
        symbol = symbol.upper()
        if len(symbol) >= 6:
            return [symbol[:3], symbol[3:6]]
        return [symbol]
