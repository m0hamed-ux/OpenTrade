"""Simple historical backtest runner."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# Add trading_bot to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.logging_config import setup_logging, get_logger
from tools.ta_tools import TATools


def load_historical_data(csv_path: str) -> pd.DataFrame:
    """Load historical OHLCV data from CSV.

    Expected columns: time, open, high, low, close, volume

    Args:
        csv_path: Path to CSV file

    Returns:
        DataFrame with OHLCV data
    """
    df = pd.read_csv(csv_path)
    df["time"] = pd.to_datetime(df["time"])
    return df


def generate_signals(
    df: pd.DataFrame,
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
) -> pd.DataFrame:
    """Generate trading signals based on technical analysis.

    Simple strategy:
    - BUY when RSI < oversold and MACD crosses above signal
    - SELL when RSI > overbought and MACD crosses below signal

    Args:
        df: OHLCV DataFrame
        rsi_oversold: RSI oversold threshold
        rsi_overbought: RSI overbought threshold

    Returns:
        DataFrame with signals added
    """
    ta_tools = TATools(df)

    # Calculate indicators
    rsi_result = ta_tools._calculate_rsi()
    macd_result = ta_tools._calculate_macd()

    # Store in dataframe (simplified - using last values)
    df = df.copy()
    df["signal"] = "FLAT"

    # Simple rule-based signals (for backtesting purposes)
    # In production, the agents would generate these
    for i in range(50, len(df)):
        window = df.iloc[:i+1]
        ta_tools.set_data(window)

        rsi = ta_tools._calculate_rsi()
        macd = ta_tools._calculate_macd()

        rsi_val = rsi["current"]
        macd_signal = macd["signal_type"]

        if rsi_val < rsi_oversold and "bullish" in macd_signal:
            df.loc[df.index[i], "signal"] = "BUY"
        elif rsi_val > rsi_overbought and "bearish" in macd_signal:
            df.loc[df.index[i], "signal"] = "SELL"

    return df


def simulate_trades(
    df: pd.DataFrame,
    initial_balance: float = 10000.0,
    risk_percent: float = 1.0,
    sl_pips: float = 20,
    tp_pips: float = 40,
) -> dict[str, Any]:
    """Simulate trades based on signals.

    Args:
        df: DataFrame with signals
        initial_balance: Starting balance
        risk_percent: Risk per trade as percentage
        sl_pips: Stop loss in pips
        tp_pips: Take profit in pips

    Returns:
        Backtest results dict
    """
    pip_size = 0.0001
    pip_value = 10.0  # USD per pip per lot

    balance = initial_balance
    trades = []
    position = None
    max_balance = initial_balance
    max_drawdown = 0.0

    for i, row in df.iterrows():
        price = row["close"]
        signal = row["signal"]

        # Check if position hit SL/TP
        if position:
            if position["type"] == "BUY":
                if row["low"] <= position["sl"]:
                    # Stop loss hit
                    pnl = -position["risk_amount"]
                    balance += pnl
                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": row["time"],
                        "type": "BUY",
                        "entry": position["entry"],
                        "exit": position["sl"],
                        "pnl": pnl,
                        "result": "loss",
                    })
                    position = None
                elif row["high"] >= position["tp"]:
                    # Take profit hit
                    pnl = position["risk_amount"] * (tp_pips / sl_pips)
                    balance += pnl
                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": row["time"],
                        "type": "BUY",
                        "entry": position["entry"],
                        "exit": position["tp"],
                        "pnl": pnl,
                        "result": "win",
                    })
                    position = None

            elif position["type"] == "SELL":
                if row["high"] >= position["sl"]:
                    # Stop loss hit
                    pnl = -position["risk_amount"]
                    balance += pnl
                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": row["time"],
                        "type": "SELL",
                        "entry": position["entry"],
                        "exit": position["sl"],
                        "pnl": pnl,
                        "result": "loss",
                    })
                    position = None
                elif row["low"] <= position["tp"]:
                    # Take profit hit
                    pnl = position["risk_amount"] * (tp_pips / sl_pips)
                    balance += pnl
                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": row["time"],
                        "type": "SELL",
                        "entry": position["entry"],
                        "exit": position["tp"],
                        "pnl": pnl,
                        "result": "win",
                    })
                    position = None

        # Update max drawdown
        if balance > max_balance:
            max_balance = balance
        drawdown = (max_balance - balance) / max_balance * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        # Open new position if no current position
        if position is None and signal != "FLAT":
            risk_amount = balance * (risk_percent / 100)

            if signal == "BUY":
                entry = price
                sl = entry - (sl_pips * pip_size)
                tp = entry + (tp_pips * pip_size)
            else:
                entry = price
                sl = entry + (sl_pips * pip_size)
                tp = entry - (tp_pips * pip_size)

            position = {
                "type": signal,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "entry_time": row["time"],
                "risk_amount": risk_amount,
            }

    # Calculate statistics
    total_trades = len(trades)
    winning_trades = sum(1 for t in trades if t["result"] == "win")
    losing_trades = sum(1 for t in trades if t["result"] == "loss")
    win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
    total_pnl = sum(t["pnl"] for t in trades)

    return {
        "initial_balance": initial_balance,
        "final_balance": balance,
        "total_return": (balance - initial_balance) / initial_balance * 100,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "max_drawdown": max_drawdown,
        "trades": trades,
    }


def print_results(results: dict[str, Any]) -> None:
    """Print backtest results."""
    print("\n" + "=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)
    print(f"Initial Balance: ${results['initial_balance']:.2f}")
    print(f"Final Balance:   ${results['final_balance']:.2f}")
    print(f"Total Return:    {results['total_return']:.2f}%")
    print(f"Total P/L:       ${results['total_pnl']:.2f}")
    print("-" * 50)
    print(f"Total Trades:    {results['total_trades']}")
    print(f"Winning Trades:  {results['winning_trades']}")
    print(f"Losing Trades:   {results['losing_trades']}")
    print(f"Win Rate:        {results['win_rate']:.1f}%")
    print(f"Max Drawdown:    {results['max_drawdown']:.2f}%")
    print("=" * 50)


def main():
    """Run backtest."""
    import argparse

    parser = argparse.ArgumentParser(description="Run backtest on historical data")
    parser.add_argument(
        "--data",
        required=True,
        help="Path to CSV file with OHLCV data",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=10000.0,
        help="Initial balance",
    )
    parser.add_argument(
        "--risk",
        type=float,
        default=1.0,
        help="Risk per trade (%)",
    )
    parser.add_argument(
        "--sl",
        type=float,
        default=20,
        help="Stop loss in pips",
    )
    parser.add_argument(
        "--tp",
        type=float,
        default=40,
        help="Take profit in pips",
    )
    parser.add_argument(
        "--output",
        help="Output JSON file for results",
    )

    args = parser.parse_args()

    setup_logging("INFO")
    logger = get_logger(__name__)

    logger.info("Loading data", path=args.data)
    df = load_historical_data(args.data)
    logger.info("Data loaded", rows=len(df))

    logger.info("Generating signals")
    df = generate_signals(df)
    signal_count = len(df[df["signal"] != "FLAT"])
    logger.info("Signals generated", count=signal_count)

    logger.info("Running simulation")
    results = simulate_trades(
        df,
        initial_balance=args.balance,
        risk_percent=args.risk,
        sl_pips=args.sl,
        tp_pips=args.tp,
    )

    print_results(results)

    if args.output:
        # Remove trades list for JSON (can be large)
        output_results = {k: v for k, v in results.items() if k != "trades"}
        with open(args.output, "w") as f:
            json.dump(output_results, f, indent=2, default=str)
        logger.info("Results saved", path=args.output)


if __name__ == "__main__":
    main()
