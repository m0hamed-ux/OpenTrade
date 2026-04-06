"""Time utilities for market hours and session detection."""

from datetime import datetime, time, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo


# Major forex market sessions (in their local timezones)
SESSIONS = {
    "sydney": {
        "timezone": "Australia/Sydney",
        "open": time(7, 0),
        "close": time(16, 0),
    },
    "tokyo": {
        "timezone": "Asia/Tokyo",
        "open": time(9, 0),
        "close": time(18, 0),
    },
    "london": {
        "timezone": "Europe/London",
        "open": time(8, 0),
        "close": time(16, 0),
    },
    "newyork": {
        "timezone": "America/New_York",
        "open": time(8, 0),
        "close": time(17, 0),
    },
}


def get_current_utc() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def is_forex_market_open() -> bool:
    """Check if forex market is open.

    Forex market is open 24/5 - from Sunday 5pm ET to Friday 5pm ET.
    """
    now = datetime.now(ZoneInfo("America/New_York"))

    # Weekend check
    if now.weekday() == 5:  # Saturday
        return False
    if now.weekday() == 6:  # Sunday
        return now.hour >= 17  # Opens at 5pm Sunday
    if now.weekday() == 4:  # Friday
        return now.hour < 17  # Closes at 5pm Friday

    return True


def get_active_sessions() -> list[str]:
    """Get list of currently active trading sessions.

    Returns:
        List of active session names (e.g., ["london", "newyork"])
    """
    active = []
    now_utc = get_current_utc()

    for session_name, session_info in SESSIONS.items():
        tz = ZoneInfo(session_info["timezone"])
        local_time = now_utc.astimezone(tz).time()

        open_time = session_info["open"]
        close_time = session_info["close"]

        if open_time <= local_time <= close_time:
            active.append(session_name)

    return active


def is_session_overlap() -> bool:
    """Check if we're in a session overlap period.

    Session overlaps typically have higher liquidity and volatility.
    """
    active = get_active_sessions()
    return len(active) >= 2


def get_session_info() -> dict[str, Any]:
    """Get comprehensive session information.

    Returns:
        Dict with market status and session details
    """
    active_sessions = get_active_sessions()
    is_overlap = len(active_sessions) >= 2

    # Determine primary session
    if "london" in active_sessions and "newyork" in active_sessions:
        primary = "london_newyork_overlap"
    elif "tokyo" in active_sessions and "london" in active_sessions:
        primary = "tokyo_london_overlap"
    elif active_sessions:
        primary = active_sessions[0]
    else:
        primary = "off_hours"

    return {
        "market_open": is_forex_market_open(),
        "active_sessions": active_sessions,
        "is_overlap": is_overlap,
        "primary_session": primary,
        "utc_time": get_current_utc().isoformat(),
    }


def time_until_session_open(session: str) -> timedelta | None:
    """Calculate time until a specific session opens.

    Args:
        session: Session name (sydney, tokyo, london, newyork)

    Returns:
        Timedelta until session opens, or None if session is open/invalid
    """
    if session not in SESSIONS:
        return None

    session_info = SESSIONS[session]
    tz = ZoneInfo(session_info["timezone"])
    now = datetime.now(tz)
    open_time = session_info["open"]
    close_time = session_info["close"]
    current_time = now.time()

    # If session is currently open
    if open_time <= current_time <= close_time:
        return None

    # Calculate time until open
    open_datetime = now.replace(
        hour=open_time.hour,
        minute=open_time.minute,
        second=0,
        microsecond=0,
    )

    if current_time > close_time:
        # Session closed for today, calculate until tomorrow
        open_datetime += timedelta(days=1)

    return open_datetime - now


def is_high_impact_time() -> bool:
    """Check if current time is typically high-impact.

    High-impact times include session opens, closes, and major
    economic release windows.
    """
    now_utc = get_current_utc()

    # Check for common high-impact windows (UTC times)
    # London open: 7-9 UTC
    # US data releases: 12:30-13:30 UTC
    # NY open: 13-15 UTC

    hour = now_utc.hour

    high_impact_windows = [
        (7, 9),    # London open
        (12, 14),  # US data + NY open
        (18, 19),  # FOMC minutes (sometimes)
    ]

    return any(start <= hour < end for start, end in high_impact_windows)


def format_duration(td: timedelta) -> str:
    """Format a timedelta as human-readable string.

    Args:
        td: Timedelta to format

    Returns:
        Formatted string (e.g., "2h 30m")
    """
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")

    return " ".join(parts)


def get_candle_close_time(timeframe: str) -> datetime:
    """Get the next candle close time for a timeframe.

    Args:
        timeframe: Timeframe string (M1, M5, M15, H1, etc.)

    Returns:
        Datetime of next candle close
    """
    now = get_current_utc()

    # Map timeframe to minutes
    tf_minutes = {
        "M1": 1,
        "M5": 5,
        "M15": 15,
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
    }

    minutes = tf_minutes.get(timeframe.upper(), 15)

    # Calculate next close
    current_minute = now.minute
    candle_start_minute = (current_minute // minutes) * minutes
    candle_end_minute = candle_start_minute + minutes

    if candle_end_minute >= 60:
        # Rolls to next hour
        next_close = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        next_close = next_close.replace(minute=candle_end_minute - 60)
    else:
        next_close = now.replace(minute=candle_end_minute, second=0, microsecond=0)

    return next_close


def should_trade_now(
    allowed_sessions: list[str] | None = None,
    avoid_high_impact: bool = True,
) -> tuple[bool, str]:
    """Determine if trading should occur now.

    Args:
        allowed_sessions: List of allowed session names (None = any)
        avoid_high_impact: Whether to avoid high-impact times

    Returns:
        Tuple of (should_trade, reason)
    """
    if not is_forex_market_open():
        return False, "Forex market is closed (weekend)"

    active = get_active_sessions()

    if not active:
        return False, "No major sessions currently active"

    if allowed_sessions:
        matching = [s for s in active if s in allowed_sessions]
        if not matching:
            return False, f"Current sessions {active} not in allowed list {allowed_sessions}"

    if avoid_high_impact and is_high_impact_time():
        return False, "Currently in high-impact time window"

    return True, f"Trading allowed - active sessions: {', '.join(active)}"
