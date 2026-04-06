"""News API connector for fetching market headlines."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx

from config.logging_config import get_logger

logger = get_logger(__name__)


class NewsConnector:
    """News API connector for market sentiment data."""

    # Symbol to search term mapping
    SYMBOL_KEYWORDS = {
        "EURUSD": ["EUR/USD", "euro dollar", "EURUSD", "euro", "ECB"],
        "GBPUSD": ["GBP/USD", "pound dollar", "GBPUSD", "sterling", "BOE"],
        "USDJPY": ["USD/JPY", "dollar yen", "USDJPY", "yen", "BOJ"],
        "XAUUSD": ["gold", "XAUUSD", "gold price", "precious metals"],
        "BTCUSD": ["bitcoin", "BTC", "crypto", "cryptocurrency"],
    }

    def __init__(
        self,
        api_key: str | None = None,
        enabled: bool = True,
        base_url: str = "https://newsapi.org/v2",
    ):
        """Initialize news connector.

        Args:
            api_key: NewsAPI key (optional if disabled)
            enabled: Whether news fetching is enabled
            base_url: API base URL
        """
        self.api_key = api_key
        self.enabled = enabled and api_key is not None
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"X-Api-Key": self.api_key} if self.api_key else {},
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_headlines(
        self,
        symbol: str,
        hours_back: int = 24,
        max_articles: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent news headlines for a symbol.

        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            hours_back: How far back to search
            max_articles: Maximum articles to return

        Returns:
            List of article dicts with title, description, source, publishedAt
        """
        if not self.enabled:
            logger.debug("News API disabled, returning empty headlines")
            return []

        # Get search keywords for symbol
        keywords = self.SYMBOL_KEYWORDS.get(symbol.upper(), [symbol])
        query = " OR ".join(f'"{kw}"' for kw in keywords[:3])

        from_date = (datetime.utcnow() - timedelta(hours=hours_back)).isoformat()

        params = {
            "q": query,
            "from": from_date,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": max_articles,
        }

        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/everything", params=params)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "ok":
                logger.warning("NewsAPI error", error=data.get("message"))
                return []

            articles = []
            for article in data.get("articles", [])[:max_articles]:
                articles.append({
                    "title": article.get("title", ""),
                    "description": article.get("description", ""),
                    "source": article.get("source", {}).get("name", "Unknown"),
                    "published_at": article.get("publishedAt", ""),
                    "url": article.get("url", ""),
                })

            logger.info(
                "Fetched news headlines",
                symbol=symbol,
                count=len(articles),
            )

            return articles

        except httpx.HTTPError as e:
            logger.error("News API request failed", error=str(e))
            return []

    async def get_economic_calendar(
        self,
        days_ahead: int = 1,
    ) -> list[dict[str, Any]]:
        """Get upcoming economic events.

        Note: This is a placeholder. In production, you would integrate
        with a proper economic calendar API (e.g., Forex Factory, Investing.com).

        Args:
            days_ahead: Days to look ahead

        Returns:
            List of economic events
        """
        # Placeholder - would integrate with economic calendar API
        logger.debug("Economic calendar not implemented, returning empty")
        return []


class MockNewsConnector(NewsConnector):
    """Mock news connector for testing without API key."""

    def __init__(self):
        super().__init__(api_key=None, enabled=True)

    async def fetch_headlines(
        self,
        symbol: str,
        hours_back: int = 24,
        max_articles: int = 10,
    ) -> list[dict[str, Any]]:
        """Return mock headlines for testing."""
        return [
            {
                "title": f"Markets steady as traders await economic data",
                "description": f"The {symbol} pair showed limited movement...",
                "source": "Mock Financial News",
                "published_at": datetime.utcnow().isoformat(),
                "url": "https://example.com/news/1",
            },
            {
                "title": f"Central bank officials signal cautious approach",
                "description": "Policy makers indicated continued data dependency...",
                "source": "Mock Financial Times",
                "published_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                "url": "https://example.com/news/2",
            },
        ]
