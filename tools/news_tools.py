"""News and sentiment analysis tools."""

from typing import Any

from connectors.news_connector import NewsConnector


# Tool schemas for Gemini function calling
NEWS_TOOLS = [
    {
        "name": "fetch_headlines",
        "description": "Fetch recent news headlines for a trading symbol",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol (e.g., EURUSD)",
                },
                "hours_back": {
                    "type": "integer",
                    "description": "How many hours back to search (default 24)",
                },
                "max_articles": {
                    "type": "integer",
                    "description": "Maximum articles to return (default 10)",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "score_sentiment",
        "description": "Analyze sentiment of text and return a score",
        "parameters": {
            "type": "object",
            "properties": {
                "headlines": {
                    "type": "array",
                    "description": "List of headline strings to analyze",
                },
            },
            "required": ["headlines"],
        },
    },
    {
        "name": "get_economic_calendar",
        "description": "Get upcoming high-impact economic events",
        "parameters": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "Days to look ahead (default 1)",
                },
            },
            "required": [],
        },
    },
]


class NewsTools:
    """News and sentiment tool executor."""

    # Sentiment keywords with weights
    BULLISH_KEYWORDS = {
        "rally": 0.8,
        "surge": 0.9,
        "gain": 0.6,
        "rise": 0.5,
        "bullish": 0.9,
        "growth": 0.6,
        "positive": 0.5,
        "strong": 0.5,
        "beat": 0.7,
        "exceed": 0.6,
        "optimism": 0.7,
        "recovery": 0.6,
        "upgrade": 0.7,
        "buy": 0.6,
    }

    BEARISH_KEYWORDS = {
        "crash": 0.9,
        "plunge": 0.9,
        "fall": 0.6,
        "drop": 0.6,
        "bearish": 0.9,
        "decline": 0.6,
        "negative": 0.5,
        "weak": 0.5,
        "miss": 0.7,
        "concern": 0.5,
        "fear": 0.7,
        "recession": 0.8,
        "downgrade": 0.7,
        "sell": 0.6,
        "crisis": 0.8,
    }

    def __init__(self, news_connector: NewsConnector):
        """Initialize with news connector.

        Args:
            news_connector: NewsConnector instance
        """
        self.news = news_connector

    async def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        handlers = {
            "fetch_headlines": self._fetch_headlines,
            "score_sentiment": self._score_sentiment,
            "get_economic_calendar": self._get_economic_calendar,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return await handler(**args)
        except Exception as e:
            return {"error": str(e)}

    async def _fetch_headlines(
        self,
        symbol: str,
        hours_back: int = 24,
        max_articles: int = 10,
    ) -> dict[str, Any]:
        """Fetch news headlines for a symbol."""
        articles = await self.news.fetch_headlines(
            symbol=symbol,
            hours_back=hours_back,
            max_articles=max_articles,
        )

        return {
            "symbol": symbol,
            "article_count": len(articles),
            "articles": articles,
        }

    async def _score_sentiment(self, headlines: list[str]) -> dict[str, Any]:
        """Score sentiment of headlines using keyword analysis.

        Returns a score from -1 (very bearish) to +1 (very bullish).
        """
        if not headlines:
            return {
                "score": 0.0,
                "interpretation": "neutral",
                "confidence": 0.0,
                "details": "No headlines to analyze",
            }

        total_score = 0.0
        keyword_hits = []

        for headline in headlines:
            headline_lower = headline.lower()

            # Check bullish keywords
            for word, weight in self.BULLISH_KEYWORDS.items():
                if word in headline_lower:
                    total_score += weight
                    keyword_hits.append({"word": word, "type": "bullish", "weight": weight})

            # Check bearish keywords
            for word, weight in self.BEARISH_KEYWORDS.items():
                if word in headline_lower:
                    total_score -= weight
                    keyword_hits.append({"word": word, "type": "bearish", "weight": -weight})

        # Normalize score to -1 to +1 range
        if keyword_hits:
            avg_score = total_score / len(headlines)
            normalized = max(-1.0, min(1.0, avg_score))
        else:
            normalized = 0.0

        # Determine interpretation
        if normalized > 0.5:
            interpretation = "very_bullish"
        elif normalized > 0.2:
            interpretation = "bullish"
        elif normalized > -0.2:
            interpretation = "neutral"
        elif normalized > -0.5:
            interpretation = "bearish"
        else:
            interpretation = "very_bearish"

        # Confidence based on number of hits
        confidence = min(1.0, len(keyword_hits) / (len(headlines) * 2))

        return {
            "score": round(normalized, 3),
            "interpretation": interpretation,
            "confidence": round(confidence, 3),
            "headline_count": len(headlines),
            "keyword_hits": len(keyword_hits),
        }

    async def _get_economic_calendar(self, days_ahead: int = 1) -> dict[str, Any]:
        """Get upcoming economic events."""
        events = await self.news.get_economic_calendar(days_ahead=days_ahead)

        return {
            "days_ahead": days_ahead,
            "event_count": len(events),
            "events": events,
        }

    async def get_full_sentiment(self, symbol: str) -> dict[str, Any]:
        """Get comprehensive sentiment analysis for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Full sentiment analysis including headlines and score
        """
        # Fetch headlines
        headlines_result = await self._fetch_headlines(symbol)
        articles = headlines_result.get("articles", [])

        # Extract headline texts
        headline_texts = [a.get("title", "") for a in articles if a.get("title")]

        # Score sentiment
        sentiment_result = await self._score_sentiment(headline_texts)

        # Get economic calendar
        calendar_result = await self._get_economic_calendar()

        return {
            "symbol": symbol,
            "headline_count": len(articles),
            "headlines": headline_texts[:5],  # Top 5 headlines
            "sentiment": sentiment_result,
            "upcoming_events": calendar_result.get("events", []),
        }
