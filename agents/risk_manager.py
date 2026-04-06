"""Risk Manager Agent - Position Sizing and Trade Validation."""

from typing import Any

from connectors.gemini_client import GeminiClient
from risk.position_sizer import PositionSizer, PositionSize
from risk.circuit_breaker import CircuitBreaker
from memory.agent_memory import AgentMemory
from config.logging_config import get_logger
from utils.validators import validate_risk_params

from .prompts import RISK_MANAGER_SYSTEM

logger = get_logger(__name__)


class RiskManagerAgent:
    """Agent that validates trades and calculates position sizing."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        position_sizer: PositionSizer,
        circuit_breaker: CircuitBreaker,
        memory: AgentMemory | None = None,
        model: str = "gemini-2.5-flash",
        max_risk_percent: float = 2.0,
    ):
        """Initialize risk manager agent.

        Args:
            gemini_client: Gemini API client
            position_sizer: Position sizing calculator
            circuit_breaker: Circuit breaker for hard limits
            memory: Optional agent memory for context
            model: Gemini model to use
            max_risk_percent: Maximum risk per trade (hard limit)
        """
        self.gemini = gemini_client
        self.sizer = position_sizer
        self.circuit_breaker = circuit_breaker
        self.memory = memory
        self.model = model
        self.max_risk_percent = max_risk_percent

    async def validate_and_size(
        self,
        symbol: str,
        signal: dict[str, Any],
        market_analysis: dict[str, Any],
        account_state: dict[str, Any],
        current_price: dict[str, float],
    ) -> dict[str, Any]:
        """Validate a trading signal and calculate position parameters.

        Args:
            symbol: Trading symbol
            signal: Strategy agent output
            market_analysis: Market analysis data
            account_state: Current account state
            current_price: Current bid/ask prices

        Returns:
            Risk parameters dict
        """
        logger.info("Validating trade", symbol=symbol, signal=signal["signal"])

        # Quick reject if signal is FLAT
        if signal["signal"] == "FLAT":
            return {
                "approved": False,
                "rejection_reason": "No trade signal (FLAT)",
                "lot_size": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "risk_percent": 0.0,
                "rr_ratio": 0.0,
            }

        # Check circuit breaker preconditions
        positions = account_state.get("open_positions", 0)
        equity = account_state.get("equity", 0)

        allowed, reason = self.circuit_breaker.check_preconditions(equity, positions)
        if not allowed:
            return {
                "approved": False,
                "rejection_reason": f"Circuit breaker: {reason}",
                "lot_size": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "risk_percent": 0.0,
                "rr_ratio": 0.0,
            }

        # Get entry price based on signal direction
        if signal["signal"] == "BUY":
            entry_price = current_price.get("ask", current_price.get("bid", 0))
        else:
            entry_price = current_price.get("bid", current_price.get("ask", 0))

        # Use ATR for SL/TP if available in market analysis
        atr = market_analysis.get("indicators", {}).get("atr", {}).get("value")

        if atr:
            stop_loss, take_profit = self.sizer.calculate_sl_tp_from_atr(
                entry_price=entry_price,
                atr=atr,
                order_type=signal["signal"],
                sl_multiplier=1.5,
                tp_multiplier=2.5,
            )
        else:
            # Fall back to key levels
            levels = market_analysis.get("key_levels", {})
            if signal["signal"] == "BUY":
                stop_loss = levels.get("support", entry_price * 0.995)
                take_profit = levels.get("resistance", entry_price * 1.01)
            else:
                stop_loss = levels.get("resistance", entry_price * 1.005)
                take_profit = levels.get("support", entry_price * 0.99)

        # Calculate position size
        balance = account_state.get("balance", 0)

        # Adjust risk based on signal confidence
        confidence = signal.get("confidence", 0.65)
        if confidence >= 0.8:
            risk_percent = min(1.5, self.max_risk_percent)
        elif confidence >= 0.7:
            risk_percent = min(1.0, self.max_risk_percent)
        else:
            risk_percent = min(0.5, self.max_risk_percent)

        position = self.sizer.calculate_fixed_fractional(
            account_balance=balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            symbol=symbol,
            risk_percent=risk_percent,
        )

        # Validate position
        valid, validation_error = self.sizer.validate_position(position)

        if not valid:
            return {
                "approved": False,
                "rejection_reason": validation_error,
                "lot_size": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "risk_percent": 0.0,
                "rr_ratio": 0.0,
            }

        # Final circuit breaker validation
        valid, cb_error = self.circuit_breaker.validate_trade(
            account_balance=balance,
            risk_amount=position.risk_amount,
            stop_loss_pips=position.stop_loss_pips,
        )

        if not valid:
            return {
                "approved": False,
                "rejection_reason": cb_error,
                "lot_size": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "risk_percent": 0.0,
                "rr_ratio": 0.0,
            }

        # Use AI for final sanity check
        ai_validation = await self._ai_validate(
            symbol=symbol,
            signal=signal,
            position=position,
            account_state=account_state,
            market_analysis=market_analysis,
        )

        if not ai_validation.get("approved", True):
            return ai_validation

        result = {
            "approved": True,
            "rejection_reason": None,
            "lot_size": position.lot_size,
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_percent": round(position.risk_percent, 2),
            "rr_ratio": position.risk_reward_ratio,
        }

        # Store decision in memory
        if self.memory:
            await self.memory.store(
                memory_type="decision",
                content={
                    "type": "risk_approval",
                    "signal": signal["signal"],
                    **result,
                },
                symbol=symbol,
                ttl_minutes=60,
            )

        logger.info(
            "Trade approved",
            symbol=symbol,
            lot_size=position.lot_size,
            risk_percent=position.risk_percent,
            rr_ratio=position.risk_reward_ratio,
        )

        return result

    async def _ai_validate(
        self,
        symbol: str,
        signal: dict[str, Any],
        position: PositionSize,
        account_state: dict[str, Any],
        market_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """Use AI for additional trade validation.

        Args:
            symbol: Trading symbol
            signal: Strategy signal
            position: Calculated position size
            account_state: Account state
            market_analysis: Market analysis

        Returns:
            Validation result
        """
        prompt = f"""
Validate the following trade setup for {symbol}:

Signal: {signal['signal']} (confidence: {signal['confidence']:.2f})
Entry Reason: {signal['entry_reason']}

Position Parameters:
- Lot Size: {position.lot_size}
- Risk: {position.risk_percent:.2f}%
- Risk Amount: ${position.risk_amount:.2f}
- Stop Loss: {position.stop_loss_pips:.1f} pips
- Take Profit: {position.take_profit_pips:.1f} pips
- R:R Ratio: {position.risk_reward_ratio:.2f}

Account State:
- Balance: ${account_state.get('balance', 0):.2f}
- Equity: ${account_state.get('equity', 0):.2f}
- Open Positions: {account_state.get('open_positions', 0)}
- Floating P/L: ${account_state.get('floating_pnl', 0):.2f}

Market Context:
- Trend: {market_analysis.get('trend', 'N/A')}
- Trend Strength: {market_analysis.get('strength', 0):.2f}

Should this trade be APPROVED or REJECTED?
Consider:
1. Is the risk appropriate for current account conditions?
2. Does the R:R ratio justify the trade?
3. Are there any red flags in the setup?

Respond with JSON: {{"approved": boolean, "rejection_reason": string or null}}
"""

        response = await self.gemini.generate(
            prompt=prompt,
            model_name=self.model,
            system_instruction=RISK_MANAGER_SYSTEM,
            temperature=0.2,
            response_format="json",
        )

        import json
        from utils.validators import extract_json_from_response

        try:
            json_str = extract_json_from_response(response)
            if json_str:
                result = json.loads(json_str)
                if not result.get("approved", True):
                    return {
                        "approved": False,
                        "rejection_reason": result.get("rejection_reason", "AI validation failed"),
                        "lot_size": 0.0,
                        "stop_loss": 0.0,
                        "take_profit": 0.0,
                        "risk_percent": 0.0,
                        "rr_ratio": 0.0,
                    }
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("AI validation parse error, allowing trade", error=str(e))

        return {"approved": True}

    async def assess_portfolio_risk(
        self,
        positions: list[dict[str, Any]],
        account_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Assess overall portfolio risk.

        Args:
            positions: List of open positions
            account_state: Current account state

        Returns:
            Portfolio risk assessment
        """
        if not positions:
            return {
                "total_exposure": 0.0,
                "correlation_risk": "low",
                "recommendations": [],
            }

        total_profit = sum(p.get("profit", 0) for p in positions)
        total_volume = sum(p.get("volume", 0) for p in positions)

        # Check for correlated positions
        symbols = [p.get("symbol", "") for p in positions]
        usd_pairs = sum(1 for s in symbols if "USD" in s)
        eur_pairs = sum(1 for s in symbols if "EUR" in s)

        correlation_risk = "low"
        if usd_pairs > 2 or eur_pairs > 2:
            correlation_risk = "high"
        elif usd_pairs > 1 or eur_pairs > 1:
            correlation_risk = "medium"

        recommendations = []
        if correlation_risk == "high":
            recommendations.append("Consider reducing correlated positions")
        if total_profit < 0 and abs(total_profit) > account_state.get("balance", 1) * 0.03:
            recommendations.append("Portfolio in significant drawdown - consider reducing exposure")

        return {
            "total_exposure": total_volume,
            "floating_pnl": total_profit,
            "position_count": len(positions),
            "correlation_risk": correlation_risk,
            "recommendations": recommendations,
        }
