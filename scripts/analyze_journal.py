"""Analyze trade journal for performance reporting."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.logging_config import setup_logging, get_logger
from memory.trade_journal import TradeJournal


async def generate_report(
    journal: TradeJournal,
    days: int = 30,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Generate performance report from trade journal.

    Args:
        journal: Trade journal instance
        days: Number of days to analyze
        symbol: Optional symbol filter

    Returns:
        Report dict
    """
    await journal.initialize()

    # Get performance summary
    summary = await journal.get_performance_summary(days=days, symbol=symbol)

    # Get recent trades
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    trades = await journal.get_trades_by_date(
        start_date=start_date,
        end_date=end_date,
        symbol=symbol,
    )

    # Calculate additional metrics
    if trades:
        profits = [t["profit"] for t in trades if t.get("profit")]
        if profits:
            avg_win = sum(p for p in profits if p > 0) / max(1, len([p for p in profits if p > 0]))
            avg_loss = sum(p for p in profits if p < 0) / max(1, len([p for p in profits if p < 0]))
            profit_factor = abs(sum(p for p in profits if p > 0) / min(-0.01, sum(p for p in profits if p < 0)))
        else:
            avg_win = avg_loss = profit_factor = 0

        # Analyze by symbol
        by_symbol = {}
        for trade in trades:
            sym = trade.get("symbol", "Unknown")
            if sym not in by_symbol:
                by_symbol[sym] = {"trades": 0, "wins": 0, "profit": 0}
            by_symbol[sym]["trades"] += 1
            if trade.get("profit", 0) > 0:
                by_symbol[sym]["wins"] += 1
            by_symbol[sym]["profit"] += trade.get("profit", 0)

        # Analyze by hour
        by_hour = {}
        for trade in trades:
            created = trade.get("created_at")
            if created:
                hour = datetime.fromisoformat(created).hour
                if hour not in by_hour:
                    by_hour[hour] = {"trades": 0, "wins": 0}
                by_hour[hour]["trades"] += 1
                if trade.get("profit", 0) > 0:
                    by_hour[hour]["wins"] += 1
    else:
        avg_win = avg_loss = profit_factor = 0
        by_symbol = {}
        by_hour = {}

    return {
        "period_days": days,
        "symbol_filter": symbol,
        "summary": summary,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "by_symbol": by_symbol,
        "by_hour": by_hour,
        "total_trades": len(trades),
    }


def print_report(report: dict[str, Any]) -> None:
    """Print formatted performance report."""
    summary = report["summary"]

    print("\n" + "=" * 60)
    print("TRADING PERFORMANCE REPORT")
    print("=" * 60)

    if report["symbol_filter"]:
        print(f"Symbol: {report['symbol_filter']}")
    print(f"Period: Last {report['period_days']} days")
    print("-" * 60)

    print("\nOVERALL STATISTICS")
    print("-" * 40)
    print(f"Total Trades:      {summary['total_trades']}")
    print(f"Winning Trades:    {summary['winning_trades']}")
    print(f"Losing Trades:     {summary['losing_trades']}")
    print(f"Win Rate:          {summary['win_rate']:.1f}%")
    print(f"Total Profit:      ${summary['total_profit']:.2f}")
    print(f"Average Profit:    ${summary['average_profit']:.2f}")
    print(f"Best Trade:        ${summary['best_trade']:.2f}")
    print(f"Worst Trade:       ${summary['worst_trade']:.2f}")

    print("\nRISK METRICS")
    print("-" * 40)
    print(f"Average Win:       ${report['avg_win']:.2f}")
    print(f"Average Loss:      ${report['avg_loss']:.2f}")
    print(f"Profit Factor:     {report['profit_factor']:.2f}")

    if report["by_symbol"]:
        print("\nPERFORMANCE BY SYMBOL")
        print("-" * 40)
        for sym, stats in report["by_symbol"].items():
            win_rate = stats["wins"] / stats["trades"] * 100 if stats["trades"] > 0 else 0
            print(f"{sym}: {stats['trades']} trades, {win_rate:.1f}% win rate, ${stats['profit']:.2f}")

    if report["by_hour"]:
        print("\nBEST TRADING HOURS")
        print("-" * 40)
        sorted_hours = sorted(
            report["by_hour"].items(),
            key=lambda x: x[1]["wins"] / max(1, x[1]["trades"]),
            reverse=True,
        )[:5]
        for hour, stats in sorted_hours:
            win_rate = stats["wins"] / stats["trades"] * 100 if stats["trades"] > 0 else 0
            print(f"{hour:02d}:00 UTC: {stats['trades']} trades, {win_rate:.1f}% win rate")

    print("\n" + "=" * 60)


async def main():
    """Run journal analysis."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze trade journal")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Filter by symbol",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to journal database",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    setup_logging("INFO")

    db_path = args.db or (Path(__file__).parent.parent / "data" / "journal.db")
    journal = TradeJournal(db_path=db_path)

    report = await generate_report(
        journal=journal,
        days=args.days,
        symbol=args.symbol,
    )

    if args.json:
        import json
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)


if __name__ == "__main__":
    asyncio.run(main())
