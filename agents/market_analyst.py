"""Market Analyst Agent - Technical Analysis."""

from typing import Any

import pandas as pd

from connectors.gemini_client import GeminiClient
from tools.ta_tools import TATools
from memory.agent_memory import AgentMemory
from config.logging_config import get_logger
from utils.formatters import format_ohlcv_for_prompt, format_indicators_for_prompt
from utils.validators import validate_market_analysis

from .prompts import MARKET_ANALYST_SYSTEM

logger = get_logger(__name__)


class MarketAnalystAgent:
    """Agent that performs technical analysis on price data."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        memory: AgentMemory | None = None,
        model: str = "gemini-2.5-pro",
    ):
        """Initialize market analyst agent.

        Args:
            gemini_client: Gemini API client
            memory: Optional agent memory for context
            model: Gemini model to use
        """
        self.gemini = gemini_client
        self.memory = memory
        self.model = model
        self.ta_tools = TATools()

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: pd.DataFrame,
    ) -> dict[str, Any]:
        """Perform technical analysis on price data.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe string
            ohlcv_data: OHLCV DataFrame

        Returns:
            Analysis result dict
        """
        logger.info("Starting market analysis", symbol=symbol, timeframe=timeframe)

        # Set data for TA tools
        self.ta_tools.set_data(ohlcv_data)

        # Calculate all indicators
        indicators = self.ta_tools.get_full_analysis()

        # Format data for prompt
        price_context = format_ohlcv_for_prompt(ohlcv_data, last_n=20)
        indicator_context = format_indicators_for_prompt(indicators)

        # Get recent memory context if available
        memory_context = ""
        if self.memory:
            recent = await self.memory.get_context_summary(symbol)
            if recent.get("last_decision"):
                memory_context = f"\nRecent Analysis Context:\n{recent['last_decision']}\n"

        # Build prompt
        prompt = f"""
Analyze the following market data for {symbol} on {timeframe} timeframe.

{price_context}

{indicator_context}
{memory_context}
Based on this data, provide your technical analysis in the required JSON format.
Focus on:
1. Overall trend direction and strength
2. Key support and resistance levels
3. Indicator confluence or divergence
4. Any recognizable chart patterns
5. Potential trade opportunities or warnings

Respond ONLY with valid JSON matching the schema.
"""

        # Call Gemini
        response = await self.gemini.generate(
            prompt=prompt,
            model_name=self.model,
            system_instruction=MARKET_ANALYST_SYSTEM,
            temperature=0.3,
            response_format="json",
        )

        # Validate response
        analysis, error = validate_market_analysis(response)

        if error:
            logger.error("Market analysis validation failed", error=error)
            # Return a safe fallback
            analysis = {
                "symbol": symbol,
                "timeframe": timeframe,
                "trend": "sideways",
                "strength": 0.5,
                "key_levels": {
                    "support": float(ohlcv_data["low"].tail(20).min()),
                    "resistance": float(ohlcv_data["high"].tail(20).max()),
                },
                "indicators": {
                    "rsi": indicators["rsi"]["current"],
                    "macd_signal": indicators["macd"]["signal_type"],
                    "bb_position": indicators["bollinger"]["position"],
                },
                "pattern": None,
                "summary": "Analysis validation failed, using neutral assessment.",
            }

        # Store in memory if available
        if self.memory:
            await self.memory.store(
                memory_type="observation",
                content=analysis,
                symbol=symbol,
                ttl_minutes=30,
            )

        logger.info(
            "Market analysis complete",
            symbol=symbol,
            trend=analysis["trend"],
            strength=analysis["strength"],
        )

        return analysis

    async def identify_pattern(
        self,
        symbol: str,
        ohlcv_data: pd.DataFrame,
    ) -> str | None:
        """Attempt to identify chart patterns using AI.

        Args:
            symbol: Trading symbol
            ohlcv_data: OHLCV DataFrame

        Returns:
            Pattern name or None
        """
        price_context = format_ohlcv_for_prompt(ohlcv_data, last_n=50)

        prompt = f"""
Analyze the following price action for {symbol} and identify any chart patterns.

{price_context}

Common patterns to look for:
- Double top/bottom
- Head and shoulders / Inverse head and shoulders
- Triangle (ascending, descending, symmetrical)
- Flag/Pennant
- Channel
- Wedge (rising, falling)

Respond with ONLY the pattern name if found, or "none" if no clear pattern.
Example responses: "double_bottom", "ascending_triangle", "none"
"""

        response = await self.gemini.generate(
            prompt=prompt,
            model_name=self.model,
            system_instruction="You are a chart pattern recognition expert. Respond only with the pattern name or 'none'.",
            temperature=0.2,
            response_format="text",
        )

        pattern = response.strip().lower().replace(" ", "_")

        if pattern == "none" or len(pattern) > 30:
            return None

        return pattern
