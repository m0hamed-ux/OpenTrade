"""Technical analysis tools for Gemini function calling."""

from typing import Any

import pandas as pd
import numpy as np
from ta.trend import MACD, SMAIndicator, EMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange


# Tool schemas for Gemini function calling
TA_TOOLS = [
    {
        "name": "calculate_rsi",
        "description": "Calculate RSI (Relative Strength Index) indicator",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "description": "RSI period (default 14)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "calculate_macd",
        "description": "Calculate MACD indicator with signal line and histogram",
        "parameters": {
            "type": "object",
            "properties": {
                "fast": {
                    "type": "integer",
                    "description": "Fast EMA period (default 12)",
                },
                "slow": {
                    "type": "integer",
                    "description": "Slow EMA period (default 26)",
                },
                "signal": {
                    "type": "integer",
                    "description": "Signal line period (default 9)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "calculate_bollinger",
        "description": "Calculate Bollinger Bands",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "description": "Moving average period (default 20)",
                },
                "std": {
                    "type": "number",
                    "description": "Standard deviation multiplier (default 2)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "calculate_atr",
        "description": "Calculate Average True Range for volatility measurement",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "description": "ATR period (default 14)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "calculate_sma",
        "description": "Calculate Simple Moving Average",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "description": "SMA period",
                },
            },
            "required": ["period"],
        },
    },
    {
        "name": "calculate_ema",
        "description": "Calculate Exponential Moving Average",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "description": "EMA period",
                },
            },
            "required": ["period"],
        },
    },
    {
        "name": "find_support_resistance",
        "description": "Find key support and resistance levels",
        "parameters": {
            "type": "object",
            "properties": {
                "lookback": {
                    "type": "integer",
                    "description": "Number of candles to analyze (default 50)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "analyze_trend",
        "description": "Analyze the overall trend direction and strength",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


class TATools:
    """Technical analysis tool executor."""

    def __init__(self, ohlcv_data: pd.DataFrame | None = None):
        """Initialize with OHLCV data.

        Args:
            ohlcv_data: DataFrame with columns: time, open, high, low, close, volume
        """
        self.df = ohlcv_data

    def set_data(self, ohlcv_data: pd.DataFrame) -> None:
        """Set OHLCV data for analysis.

        Args:
            ohlcv_data: DataFrame with OHLCV data
        """
        self.df = ohlcv_data.copy()

    def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        if self.df is None or self.df.empty:
            return {"error": "No OHLCV data available"}

        handlers = {
            "calculate_rsi": self._calculate_rsi,
            "calculate_macd": self._calculate_macd,
            "calculate_bollinger": self._calculate_bollinger,
            "calculate_atr": self._calculate_atr,
            "calculate_sma": self._calculate_sma,
            "calculate_ema": self._calculate_ema,
            "find_support_resistance": self._find_support_resistance,
            "analyze_trend": self._analyze_trend,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return handler(**args)
        except Exception as e:
            return {"error": str(e)}

    def _calculate_rsi(self, period: int = 14) -> dict[str, Any]:
        """Calculate RSI indicator."""
        rsi = RSIIndicator(close=self.df["close"], window=period)
        values = rsi.rsi()

        current = float(values.iloc[-1])
        prev = float(values.iloc[-2])

        # Determine condition
        if current > 70:
            condition = "overbought"
        elif current < 30:
            condition = "oversold"
        else:
            condition = "neutral"

        # Determine divergence
        divergence = None
        if len(values) >= 10:
            price_trend = self.df["close"].iloc[-10:].diff().sum()
            rsi_trend = values.iloc[-10:].diff().sum()
            if price_trend > 0 and rsi_trend < 0:
                divergence = "bearish"
            elif price_trend < 0 and rsi_trend > 0:
                divergence = "bullish"

        return {
            "indicator": "RSI",
            "period": period,
            "current": round(current, 2),
            "previous": round(prev, 2),
            "condition": condition,
            "divergence": divergence,
        }

    def _calculate_macd(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> dict[str, Any]:
        """Calculate MACD indicator."""
        macd = MACD(
            close=self.df["close"],
            window_fast=fast,
            window_slow=slow,
            window_sign=signal,
        )

        macd_line = macd.macd()
        signal_line = macd.macd_signal()
        histogram = macd.macd_diff()

        current_macd = float(macd_line.iloc[-1])
        current_signal = float(signal_line.iloc[-1])
        current_hist = float(histogram.iloc[-1])
        prev_hist = float(histogram.iloc[-2])

        # Determine signal
        if current_macd > current_signal:
            if prev_hist <= 0 and current_hist > 0:
                signal_type = "bullish_crossover"
            else:
                signal_type = "bullish"
        else:
            if prev_hist >= 0 and current_hist < 0:
                signal_type = "bearish_crossover"
            else:
                signal_type = "bearish"

        return {
            "indicator": "MACD",
            "macd": round(current_macd, 5),
            "signal": round(current_signal, 5),
            "histogram": round(current_hist, 5),
            "signal_type": signal_type,
            "momentum": "increasing" if abs(current_hist) > abs(prev_hist) else "decreasing",
        }

    def _calculate_bollinger(
        self,
        period: int = 20,
        std: float = 2.0,
    ) -> dict[str, Any]:
        """Calculate Bollinger Bands."""
        bb = BollingerBands(
            close=self.df["close"],
            window=period,
            window_dev=std,
        )

        upper = float(bb.bollinger_hband().iloc[-1])
        middle = float(bb.bollinger_mavg().iloc[-1])
        lower = float(bb.bollinger_lband().iloc[-1])
        current_price = float(self.df["close"].iloc[-1])

        # Determine position
        band_width = upper - lower
        position_pct = (current_price - lower) / band_width if band_width > 0 else 0.5

        if position_pct > 0.8:
            position = "upper"
        elif position_pct < 0.2:
            position = "lower"
        else:
            position = "middle"

        # Bandwidth for volatility
        bandwidth = (upper - lower) / middle * 100

        return {
            "indicator": "Bollinger Bands",
            "upper": round(upper, 5),
            "middle": round(middle, 5),
            "lower": round(lower, 5),
            "current_price": round(current_price, 5),
            "position": position,
            "position_percent": round(position_pct * 100, 1),
            "bandwidth": round(bandwidth, 2),
        }

    def _calculate_atr(self, period: int = 14) -> dict[str, Any]:
        """Calculate Average True Range."""
        atr = AverageTrueRange(
            high=self.df["high"],
            low=self.df["low"],
            close=self.df["close"],
            window=period,
        )

        current = float(atr.average_true_range().iloc[-1])
        avg_price = float(self.df["close"].iloc[-1])
        atr_percent = (current / avg_price) * 100

        return {
            "indicator": "ATR",
            "period": period,
            "value": round(current, 5),
            "percent": round(atr_percent, 3),
        }

    def _calculate_sma(self, period: int) -> dict[str, Any]:
        """Calculate Simple Moving Average."""
        sma = SMAIndicator(close=self.df["close"], window=period)
        value = float(sma.sma_indicator().iloc[-1])
        current_price = float(self.df["close"].iloc[-1])

        return {
            "indicator": "SMA",
            "period": period,
            "value": round(value, 5),
            "price_relation": "above" if current_price > value else "below",
            "distance_percent": round((current_price - value) / value * 100, 2),
        }

    def _calculate_ema(self, period: int) -> dict[str, Any]:
        """Calculate Exponential Moving Average."""
        ema = EMAIndicator(close=self.df["close"], window=period)
        value = float(ema.ema_indicator().iloc[-1])
        current_price = float(self.df["close"].iloc[-1])

        return {
            "indicator": "EMA",
            "period": period,
            "value": round(value, 5),
            "price_relation": "above" if current_price > value else "below",
            "distance_percent": round((current_price - value) / value * 100, 2),
        }

    def _find_support_resistance(self, lookback: int = 50) -> dict[str, Any]:
        """Find support and resistance levels."""
        data = self.df.tail(lookback)

        # Find local minima and maxima
        highs = data["high"].values
        lows = data["low"].values

        # Simple pivot point detection
        resistance_levels = []
        support_levels = []

        for i in range(2, len(highs) - 2):
            # Local high (resistance)
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
               highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                resistance_levels.append(float(highs[i]))

            # Local low (support)
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
               lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                support_levels.append(float(lows[i]))

        # Get closest levels to current price
        current_price = float(data["close"].iloc[-1])

        # Find nearest support (below current price)
        supports_below = [s for s in support_levels if s < current_price]
        nearest_support = max(supports_below) if supports_below else float(data["low"].min())

        # Find nearest resistance (above current price)
        resistances_above = [r for r in resistance_levels if r > current_price]
        nearest_resistance = min(resistances_above) if resistances_above else float(data["high"].max())

        return {
            "current_price": round(current_price, 5),
            "nearest_support": round(nearest_support, 5),
            "nearest_resistance": round(nearest_resistance, 5),
            "all_supports": [round(s, 5) for s in sorted(support_levels, reverse=True)[:3]],
            "all_resistances": [round(r, 5) for r in sorted(resistance_levels)[:3]],
        }

    def _analyze_trend(self) -> dict[str, Any]:
        """Analyze overall trend direction and strength."""
        # Calculate multiple EMAs
        ema_20 = EMAIndicator(close=self.df["close"], window=20).ema_indicator()
        ema_50 = EMAIndicator(close=self.df["close"], window=50).ema_indicator()

        current_price = float(self.df["close"].iloc[-1])
        ema_20_val = float(ema_20.iloc[-1])
        ema_50_val = float(ema_50.iloc[-1])

        # Trend direction
        if current_price > ema_20_val > ema_50_val:
            trend = "bullish"
        elif current_price < ema_20_val < ema_50_val:
            trend = "bearish"
        else:
            trend = "sideways"

        # Trend strength based on price distance from EMAs
        distance_20 = abs(current_price - ema_20_val) / current_price * 100
        distance_50 = abs(current_price - ema_50_val) / current_price * 100

        if distance_50 > 2:
            strength = "strong"
        elif distance_50 > 1:
            strength = "moderate"
        else:
            strength = "weak"

        # Higher highs / lower lows check
        recent_highs = self.df["high"].tail(10).values
        recent_lows = self.df["low"].tail(10).values

        higher_highs = all(recent_highs[i] >= recent_highs[i-1] for i in range(1, len(recent_highs)))
        lower_lows = all(recent_lows[i] <= recent_lows[i-1] for i in range(1, len(recent_lows)))

        return {
            "trend": trend,
            "strength": strength,
            "price": round(current_price, 5),
            "ema_20": round(ema_20_val, 5),
            "ema_50": round(ema_50_val, 5),
            "higher_highs": higher_highs,
            "lower_lows": lower_lows,
        }

    def get_full_analysis(self) -> dict[str, Any]:
        """Get comprehensive technical analysis summary.

        Returns:
            Dict with all indicator values and analysis
        """
        return {
            "rsi": self._calculate_rsi(),
            "macd": self._calculate_macd(),
            "bollinger": self._calculate_bollinger(),
            "atr": self._calculate_atr(),
            "sma_20": self._calculate_sma(20),
            "ema_50": self._calculate_ema(50),
            "levels": self._find_support_resistance(),
            "trend": self._analyze_trend(),
        }
