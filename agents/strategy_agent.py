"""Strategy Agent - Signal Generation."""

from typing import Any

from connectors.gemini_client import GeminiClient
from memory.agent_memory import AgentMemory
from config.logging_config import get_logger
from utils.formatters import (
    format_indicators_for_prompt,
    format_sentiment_for_prompt,
    format_account_for_prompt,
)
from utils.validators import validate_signal

from .prompts import STRATEGY_SYSTEM

logger = get_logger(__name__)


class StrategyAgent:
    """Agent that generates trading signals from analysis data."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        memory: AgentMemory | None = None,
        model: str = "gemini-2.5-pro",
        min_confidence: float = 0.65,
    ):
        """Initialize strategy agent.

        Args:
            gemini_client: Gemini API client
            memory: Optional agent memory for context
            model: Gemini model to use
            min_confidence: Minimum confidence for non-FLAT signals
        """
        self.gemini = gemini_client
        self.memory = memory
        self.model = model
        self.min_confidence = min_confidence

    async def generate_signal(
        self,
        symbol: str,
        market_analysis: dict[str, Any],
        sentiment_analysis: dict[str, Any],
        account_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a trading signal from analysis data.

        Args:
            symbol: Trading symbol
            market_analysis: Output from market analyst
            sentiment_analysis: Output from sentiment agent
            account_state: Optional current account state

        Returns:
            Signal dict with direction, confidence, and reasoning
        """
        logger.info("Generating signal", symbol=symbol)

        # Format inputs for prompt
        market_summary = self._format_market_analysis(market_analysis)
        sentiment_summary = self._format_sentiment(sentiment_analysis)

        account_context = ""
        if account_state:
            account_context = f"\nAccount State:\n{format_account_for_prompt(account_state)}\n"

        # Get recent decision history from memory
        memory_context = ""
        if self.memory:
            recent_decisions = await self.memory.recall_recent_decisions(symbol, minutes=60)
            if recent_decisions:
                memory_context = "\nRecent Decisions:\n"
                for decision in recent_decisions[:3]:
                    memory_context += f"- {decision.get('signal', 'N/A')}: {decision.get('entry_reason', 'N/A')[:50]}\n"

        prompt = f"""
Generate a trading signal for {symbol} based on the following analysis:

TECHNICAL ANALYSIS:
{market_summary}

SENTIMENT ANALYSIS:
{sentiment_summary}
{account_context}
{memory_context}

CRITICAL: Your confidence score determines the signal validity.
- confidence < 0.65 MUST result in signal = "FLAT"
- Only output BUY or SELL with high conviction

Consider:
1. Do technical and sentiment analysis AGREE?
2. Is the trend clear and strong?
3. Are we at a good entry level (support/resistance)?
4. Are there any warning signs (divergences, overbought/oversold)?
5. Any upcoming high-impact events that add risk?

Respond ONLY with valid JSON matching the required schema.
"""

        response = await self.gemini.generate(
            prompt=prompt,
            model_name=self.model,
            system_instruction=STRATEGY_SYSTEM,
            temperature=0.4,
            response_format="json",
        )

        # Validate response
        signal, error = validate_signal(response)

        if error:
            logger.error("Signal validation failed", error=error)
            signal = {
                "signal": "FLAT",
                "confidence": 0.0,
                "entry_reason": f"Signal generation error: {error}",
                "invalidation": "N/A",
                "suggested_entry": None,
            }

        # Enforce minimum confidence rule
        if signal["confidence"] < self.min_confidence and signal["signal"] != "FLAT":
            logger.warning(
                "Signal below confidence threshold, forcing FLAT",
                original_signal=signal["signal"],
                confidence=signal["confidence"],
            )
            signal["signal"] = "FLAT"
            signal["entry_reason"] = f"Original signal {signal['signal']} rejected: confidence {signal['confidence']:.2f} < {self.min_confidence}"

        # Store decision in memory
        if self.memory:
            await self.memory.store(
                memory_type="decision",
                content=signal,
                symbol=symbol,
                ttl_minutes=120,
            )

        logger.info(
            "Signal generated",
            symbol=symbol,
            signal=signal["signal"],
            confidence=signal["confidence"],
        )

        return signal

    def _format_market_analysis(self, analysis: dict[str, Any]) -> str:
        """Format market analysis for prompt."""
        lines = []
        lines.append(f"Trend: {analysis.get('trend', 'N/A')} (strength: {analysis.get('strength', 0):.2f})")

        levels = analysis.get("key_levels", {})
        lines.append(f"Support: {levels.get('support', 'N/A')}")
        lines.append(f"Resistance: {levels.get('resistance', 'N/A')}")

        indicators = analysis.get("indicators", {})
        lines.append(f"RSI: {indicators.get('rsi', 'N/A')}")
        lines.append(f"MACD Signal: {indicators.get('macd_signal', 'N/A')}")
        lines.append(f"BB Position: {indicators.get('bb_position', 'N/A')}")

        if analysis.get("pattern"):
            lines.append(f"Pattern: {analysis['pattern']}")

        lines.append(f"Summary: {analysis.get('summary', 'N/A')}")

        return "\n".join(lines)

    def _format_sentiment(self, sentiment: dict[str, Any]) -> str:
        """Format sentiment analysis for prompt."""
        lines = []
        lines.append(f"Score: {sentiment.get('sentiment_score', 0):+.2f}")
        lines.append(f"Interpretation: {sentiment.get('interpretation', 'neutral')}")
        lines.append(f"Confidence: {sentiment.get('confidence', 0):.2f}")
        lines.append(f"Headlines Analyzed: {sentiment.get('headline_count', 0)}")

        themes = sentiment.get("key_themes", [])
        if themes:
            lines.append(f"Key Themes: {', '.join(themes)}")

        events = sentiment.get("high_impact_events", [])
        if events:
            lines.append("Upcoming Events:")
            for event in events[:2]:
                lines.append(f"  - {event.get('event', 'Unknown')}")

        lines.append(f"Summary: {sentiment.get('summary', 'N/A')}")

        return "\n".join(lines)

    async def evaluate_exit(
        self,
        symbol: str,
        position: dict[str, Any],
        market_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate whether to exit an existing position.

        Args:
            symbol: Trading symbol
            position: Current position details
            market_analysis: Latest market analysis

        Returns:
            Exit recommendation
        """
        prompt = f"""
Evaluate whether to exit the following position for {symbol}:

Position:
- Type: {position.get('type', 'N/A')}
- Entry Price: {position.get('price_open', 'N/A')}
- Current Price: {position.get('price_current', 'N/A')}
- Unrealized P/L: {position.get('profit', 0):.2f}
- Stop Loss: {position.get('sl', 'N/A')}
- Take Profit: {position.get('tp', 'N/A')}

Current Market Analysis:
- Trend: {market_analysis.get('trend', 'N/A')}
- Strength: {market_analysis.get('strength', 0):.2f}

Should this position be:
1. HOLD - Keep position open, let SL/TP work
2. CLOSE - Exit now regardless of SL/TP
3. TRAIL - Tighten stop loss to lock in profits

Respond with JSON: {{"action": "HOLD|CLOSE|TRAIL", "reason": "explanation", "new_sl": float or null}}
"""

        response = await self.gemini.generate(
            prompt=prompt,
            model_name=self.model,
            system_instruction="You are a position management expert. Be conservative with winning trades.",
            temperature=0.3,
            response_format="json",
        )

        import json
        from utils.validators import extract_json_from_response

        try:
            json_str = extract_json_from_response(response)
            if json_str:
                return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass

        return {"action": "HOLD", "reason": "Unable to evaluate, defaulting to hold", "new_sl": None}
