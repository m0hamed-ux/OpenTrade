"""Schema validation for agent outputs."""

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator
from config.logging_config import get_logger

logger = get_logger(__name__)


class MarketAnalysisOutput(BaseModel):
    """Schema for market analyst output."""
    symbol: str
    timeframe: str
    trend: str = Field(..., pattern="^(bullish|bearish|sideways)$")
    strength: float = Field(..., ge=0.0, le=1.0)
    key_levels: dict[str, float]
    indicators: dict[str, Any]
    pattern: str | None = None
    summary: str

    @field_validator("key_levels")
    @classmethod
    def validate_key_levels(cls, v):
        if "support" not in v or "resistance" not in v:
            raise ValueError("key_levels must contain 'support' and 'resistance'")
        return v


class SentimentOutput(BaseModel):
    """Schema for sentiment agent output."""
    symbol: str
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)
    interpretation: str = Field(
        ...,
        pattern="^(very_bullish|bullish|neutral|bearish|very_bearish)$"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    headline_count: int = Field(..., ge=0)
    key_themes: list[str] = Field(default_factory=list)
    high_impact_events: list[dict] = Field(default_factory=list)
    summary: str


class SignalOutput(BaseModel):
    """Schema for strategy agent output."""
    signal: str = Field(..., pattern="^(BUY|SELL|FLAT)$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    entry_reason: str
    invalidation: str
    suggested_entry: float | None = None

    @field_validator("signal")
    @classmethod
    def validate_signal_confidence(cls, v, info):
        # Access confidence from info.data if available
        data = info.data
        confidence = data.get("confidence", 1.0)
        if confidence < 0.65 and v != "FLAT":
            logger.warning(
                "Signal confidence below threshold, forcing FLAT",
                signal=v,
                confidence=confidence,
            )
            return "FLAT"
        return v


class RiskParamsOutput(BaseModel):
    """Schema for risk manager output."""
    approved: bool
    rejection_reason: str | None = None
    lot_size: float = Field(default=0.0, ge=0.0)
    stop_loss: float = Field(default=0.0, ge=0.0)
    take_profit: float = Field(default=0.0, ge=0.0)
    risk_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    rr_ratio: float = Field(default=0.0, ge=0.0)

    @field_validator("risk_percent")
    @classmethod
    def validate_risk_limit(cls, v):
        # Hard limit: risk must never exceed 2%
        if v > 2.0:
            logger.warning(
                "Risk percent exceeds hard limit, capping at 2%",
                original=v,
            )
            return 2.0
        return v


class ExecutionResultOutput(BaseModel):
    """Schema for execution agent output."""
    success: bool
    order_id: int | None = None
    executed_price: float | None = None
    executed_volume: float | None = None
    sl_set: float | None = None
    tp_set: float | None = None
    error: str | None = None
    timestamp: str | None = None


class OrchestratorDecision(BaseModel):
    """Schema for orchestrator decision."""
    proceed: bool
    reason: str
    symbols_to_analyze: list[str] = Field(default_factory=list)


def validate_json_output(
    json_str: str,
    schema_class: type[BaseModel],
) -> tuple[BaseModel | None, str | None]:
    """Validate JSON output against a Pydantic schema.

    Args:
        json_str: JSON string to validate
        schema_class: Pydantic model class to validate against

    Returns:
        Tuple of (validated_model, error_message)
    """
    try:
        data = json.loads(json_str)
        model = schema_class.model_validate(data)
        return model, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    except Exception as e:
        return None, f"Validation error: {e}"


def extract_json_from_response(response: str) -> str | None:
    """Extract JSON from a potentially mixed response.

    Handles cases where the model includes markdown code blocks
    or additional text around the JSON.

    Args:
        response: Raw response text

    Returns:
        Extracted JSON string or None if not found
    """
    # Try to find JSON in code blocks first
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end > start:
            return response[start:end].strip()

    if "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end > start:
            potential = response[start:end].strip()
            if potential.startswith("{") or potential.startswith("["):
                return potential

    # Try to find raw JSON
    # Look for object
    if "{" in response:
        start = response.find("{")
        # Find matching closing brace
        depth = 0
        for i, c in enumerate(response[start:], start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    potential = response[start:i+1]
                    try:
                        json.loads(potential)
                        return potential
                    except json.JSONDecodeError:
                        pass
                    break

    return None


def validate_market_analysis(response: str) -> tuple[dict | None, str | None]:
    """Validate market analysis response.

    Args:
        response: Raw response from market analyst

    Returns:
        Tuple of (validated_dict, error_message)
    """
    json_str = extract_json_from_response(response)
    if not json_str:
        return None, "No valid JSON found in response"

    result, error = validate_json_output(json_str, MarketAnalysisOutput)
    if result:
        return result.model_dump(), None
    return None, error


def validate_signal(response: str) -> tuple[dict | None, str | None]:
    """Validate strategy signal response.

    Args:
        response: Raw response from strategy agent

    Returns:
        Tuple of (validated_dict, error_message)
    """
    json_str = extract_json_from_response(response)
    if not json_str:
        return None, "No valid JSON found in response"

    result, error = validate_json_output(json_str, SignalOutput)
    if result:
        return result.model_dump(), None
    return None, error


def validate_risk_params(response: str) -> tuple[dict | None, str | None]:
    """Validate risk manager response.

    Args:
        response: Raw response from risk manager

    Returns:
        Tuple of (validated_dict, error_message)
    """
    json_str = extract_json_from_response(response)
    if not json_str:
        return None, "No valid JSON found in response"

    result, error = validate_json_output(json_str, RiskParamsOutput)
    if result:
        return result.model_dump(), None
    return None, error
