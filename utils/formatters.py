"""Data formatters for Gemini prompts."""

import json
from typing import Any

import pandas as pd


def format_ohlcv_for_prompt(
    df: pd.DataFrame,
    last_n: int = 20,
) -> str:
    """Format OHLCV data as a readable string for LLM prompts.

    Args:
        df: DataFrame with OHLCV data
        last_n: Number of recent candles to include

    Returns:
        Formatted string representation
    """
    recent = df.tail(last_n)

    lines = ["Recent Price Action (newest first):"]
    lines.append("-" * 60)
    lines.append(f"{'Time':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10}")
    lines.append("-" * 60)

    for _, row in recent.iloc[::-1].iterrows():
        time_str = row["time"].strftime("%Y-%m-%d %H:%M") if hasattr(row["time"], "strftime") else str(row["time"])[:16]
        lines.append(
            f"{time_str:<20} {row['open']:>10.5f} {row['high']:>10.5f} "
            f"{row['low']:>10.5f} {row['close']:>10.5f}"
        )

    # Add summary stats
    lines.append("-" * 60)
    lines.append(f"Period High: {recent['high'].max():.5f}")
    lines.append(f"Period Low: {recent['low'].min():.5f}")
    lines.append(f"Current Price: {recent['close'].iloc[-1]:.5f}")
    lines.append(f"Price Change: {(recent['close'].iloc[-1] - recent['open'].iloc[0]):.5f}")

    return "\n".join(lines)


def format_indicators_for_prompt(indicators: dict[str, Any]) -> str:
    """Format technical indicators for LLM prompt.

    Args:
        indicators: Dict of indicator results from TATools

    Returns:
        Formatted string
    """
    lines = ["Technical Indicators:"]
    lines.append("-" * 40)

    # RSI
    if "rsi" in indicators:
        rsi = indicators["rsi"]
        lines.append(f"RSI({rsi.get('period', 14)}): {rsi.get('current', 'N/A'):.1f} [{rsi.get('condition', 'N/A')}]")
        if rsi.get("divergence"):
            lines.append(f"  Divergence: {rsi['divergence']}")

    # MACD
    if "macd" in indicators:
        macd = indicators["macd"]
        lines.append(f"MACD: {macd.get('macd', 'N/A'):.5f}")
        lines.append(f"  Signal: {macd.get('signal', 'N/A'):.5f}")
        lines.append(f"  Histogram: {macd.get('histogram', 'N/A'):.5f} ({macd.get('signal_type', 'N/A')})")

    # Bollinger Bands
    if "bollinger" in indicators:
        bb = indicators["bollinger"]
        lines.append(f"Bollinger Bands:")
        lines.append(f"  Upper: {bb.get('upper', 'N/A'):.5f}")
        lines.append(f"  Middle: {bb.get('middle', 'N/A'):.5f}")
        lines.append(f"  Lower: {bb.get('lower', 'N/A'):.5f}")
        lines.append(f"  Position: {bb.get('position', 'N/A')} ({bb.get('position_percent', 'N/A'):.1f}%)")

    # ATR
    if "atr" in indicators:
        atr = indicators["atr"]
        lines.append(f"ATR({atr.get('period', 14)}): {atr.get('value', 'N/A'):.5f} ({atr.get('percent', 'N/A'):.2f}%)")

    # Moving Averages
    for key in ["sma_20", "ema_50"]:
        if key in indicators:
            ma = indicators[key]
            lines.append(f"{ma.get('indicator', key).upper()}({ma.get('period', '?')}): {ma.get('value', 'N/A'):.5f} (price {ma.get('price_relation', 'N/A')})")

    # Support/Resistance
    if "levels" in indicators:
        levels = indicators["levels"]
        lines.append(f"Key Levels:")
        lines.append(f"  Nearest Support: {levels.get('nearest_support', 'N/A'):.5f}")
        lines.append(f"  Nearest Resistance: {levels.get('nearest_resistance', 'N/A'):.5f}")

    # Trend
    if "trend" in indicators:
        trend = indicators["trend"]
        lines.append(f"Trend: {trend.get('trend', 'N/A').upper()} ({trend.get('strength', 'N/A')})")

    return "\n".join(lines)


def format_sentiment_for_prompt(sentiment: dict[str, Any]) -> str:
    """Format sentiment data for LLM prompt.

    Args:
        sentiment: Sentiment analysis results

    Returns:
        Formatted string
    """
    lines = ["Market Sentiment:"]
    lines.append("-" * 40)

    score = sentiment.get("sentiment", {}).get("score", 0)
    interpretation = sentiment.get("sentiment", {}).get("interpretation", "neutral")
    confidence = sentiment.get("sentiment", {}).get("confidence", 0)

    lines.append(f"Overall Score: {score:+.2f} ({interpretation})")
    lines.append(f"Confidence: {confidence:.1%}")
    lines.append(f"Headlines Analyzed: {sentiment.get('headline_count', 0)}")

    # Recent headlines
    headlines = sentiment.get("headlines", [])
    if headlines:
        lines.append("\nRecent Headlines:")
        for i, headline in enumerate(headlines[:3], 1):
            # Truncate long headlines
            if len(headline) > 70:
                headline = headline[:67] + "..."
            lines.append(f"  {i}. {headline}")

    # Upcoming events
    events = sentiment.get("upcoming_events", [])
    if events:
        lines.append("\nUpcoming Economic Events:")
        for event in events[:3]:
            lines.append(f"  - {event.get('name', 'Unknown Event')}")

    return "\n".join(lines)


def format_account_for_prompt(account: dict[str, Any]) -> str:
    """Format account state for LLM prompt.

    Args:
        account: Account information dict

    Returns:
        Formatted string
    """
    lines = ["Account State:"]
    lines.append("-" * 40)

    lines.append(f"Balance: {account.get('balance', 0):.2f} {account.get('currency', 'USD')}")
    lines.append(f"Equity: {account.get('equity', 0):.2f}")
    lines.append(f"Free Margin: {account.get('free_margin', 0):.2f}")
    lines.append(f"Margin Level: {account.get('margin_level', 0):.1f}%")
    lines.append(f"Floating P/L: {account.get('floating_pnl', 0):+.2f}")
    lines.append(f"Open Positions: {account.get('open_positions', 0)}")

    # Daily stats if available
    daily = account.get("daily_stats", {})
    if daily:
        lines.append(f"\nToday's Performance:")
        lines.append(f"  Starting Balance: {daily.get('starting_balance', 0):.2f}")
        lines.append(f"  Realized P/L: {daily.get('realized_pnl', 0):+.2f}")
        lines.append(f"  Trades: {daily.get('trade_count', 0)}")

    return "\n".join(lines)


def format_signal_for_prompt(signal: dict[str, Any]) -> str:
    """Format a trading signal for display.

    Args:
        signal: Signal dict from strategy agent

    Returns:
        Formatted string
    """
    lines = ["Trading Signal:"]
    lines.append("-" * 40)

    direction = signal.get("signal", "FLAT")
    confidence = signal.get("confidence", 0)

    lines.append(f"Direction: {direction}")
    lines.append(f"Confidence: {confidence:.1%}")
    lines.append(f"Entry Reason: {signal.get('entry_reason', 'N/A')}")
    lines.append(f"Invalidation: {signal.get('invalidation', 'N/A')}")

    if signal.get("suggested_entry"):
        lines.append(f"Suggested Entry: {signal['suggested_entry']:.5f}")

    return "\n".join(lines)


def format_risk_params_for_prompt(params: dict[str, Any]) -> str:
    """Format risk parameters for display.

    Args:
        params: Risk manager output

    Returns:
        Formatted string
    """
    lines = ["Risk Parameters:"]
    lines.append("-" * 40)

    if not params.get("approved", False):
        lines.append(f"REJECTED: {params.get('rejection_reason', 'Unknown reason')}")
        return "\n".join(lines)

    lines.append(f"Lot Size: {params.get('lot_size', 0):.2f}")
    lines.append(f"Stop Loss: {params.get('stop_loss', 0):.5f}")
    lines.append(f"Take Profit: {params.get('take_profit', 0):.5f}")
    lines.append(f"Risk: {params.get('risk_percent', 0):.2f}%")
    lines.append(f"R:R Ratio: {params.get('rr_ratio', 0):.2f}")

    return "\n".join(lines)


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """Safely convert object to JSON string.

    Args:
        obj: Object to serialize
        **kwargs: Additional json.dumps arguments

    Returns:
        JSON string
    """
    def default(o):
        if hasattr(o, "isoformat"):
            return o.isoformat()
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)

    return json.dumps(obj, default=default, **kwargs)
