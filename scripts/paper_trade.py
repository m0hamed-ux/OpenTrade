"""Paper trading mode with real market data."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import os

from config.logging_config import setup_logging, get_logger
from connectors.gemini_client import GeminiClient
from connectors.mt5_connector import MT5Connector
from connectors.news_connector import MockNewsConnector
from risk.circuit_breaker import CircuitBreaker
from risk.position_sizer import PositionSizer
from memory.trade_journal import TradeJournal
from graph.trading_graph import TradingGraph


class PaperTradeExecutor:
    """Mock executor for paper trading."""

    def __init__(self, initial_balance: float = 10000.0):
        self.balance = initial_balance
        self.equity = initial_balance
        self.positions = []
        self.closed_trades = []

    async def execute(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: float,
        tp: float,
    ) -> dict[str, Any]:
        """Simulate order execution."""
        # Get current price (mock)
        entry_price = 1.0850  # Would get from MT5 in real mode

        position = {
            "ticket": len(self.positions) + 1000,
            "symbol": symbol,
            "type": order_type,
            "volume": volume,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "opened_at": datetime.utcnow().isoformat(),
        }

        self.positions.append(position)

        return {
            "success": True,
            "order_id": position["ticket"],
            "executed_price": entry_price,
            "executed_volume": volume,
            "sl_set": sl,
            "tp_set": tp,
        }

    def get_account_state(self) -> dict[str, Any]:
        """Get current account state."""
        return {
            "balance": self.balance,
            "equity": self.equity,
            "margin": 0,
            "free_margin": self.equity,
            "margin_level": 0,
            "profit": self.equity - self.balance,
            "currency": "USD",
            "leverage": 100,
            "open_positions": len(self.positions),
        }


async def run_paper_trading(
    symbols: list[str],
    interval_seconds: int = 60,
    max_cycles: int | None = None,
):
    """Run paper trading simulation.

    Args:
        symbols: List of symbols to trade
        interval_seconds: Cycle interval
        max_cycles: Maximum number of cycles (None for unlimited)
    """
    logger = get_logger(__name__)
    load_dotenv()

    # Initialize components
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY required for paper trading")

    gemini = GeminiClient(api_key=gemini_key)

    # Use MT5 for real price data
    mt5_login = os.getenv("MT5_LOGIN")
    mt5_password = os.getenv("MT5_PASSWORD")
    mt5_server = os.getenv("MT5_SERVER")

    if not all([mt5_login, mt5_password, mt5_server]):
        raise ValueError("MT5 credentials required for real market data")

    mt5 = MT5Connector(
        login=int(mt5_login),
        password=mt5_password,
        server=mt5_server,
    )

    # Paper trade executor
    paper_executor = PaperTradeExecutor(initial_balance=10000.0)

    # Other components
    circuit_breaker = CircuitBreaker(
        max_daily_loss_percent=5.0,
        max_trades_per_day=10,
    )
    circuit_breaker.initialize_day(10000.0)

    position_sizer = PositionSizer()
    news = MockNewsConnector()
    journal = TradeJournal(
        db_path=Path(__file__).parent.parent / "data" / "paper_journal.db"
    )

    settings = {
        "trading": {
            "symbols": symbols,
            "timeframe": "M15",
            "candle_count": 100,
            "cycle_interval_seconds": interval_seconds,
        },
        "risk": {
            "max_risk_percent": 2.0,
            "min_rr_ratio": 1.5,
        },
        "confidence": {
            "min_signal_confidence": 0.65,
        },
        "models": {},
    }

    try:
        # Connect to MT5
        connected = await mt5.connect()
        if not connected:
            raise RuntimeError("Failed to connect to MT5")

        logger.info("Paper trading started", symbols=symbols)

        # Create trading graph
        graph = TradingGraph(
            gemini_client=gemini,
            mt5_connector=mt5,
            news_connector=news,
            circuit_breaker=circuit_breaker,
            position_sizer=position_sizer,
            journal=journal,
            settings=settings,
        )

        cycle_count = 0

        while max_cycles is None or cycle_count < max_cycles:
            cycle_count += 1
            logger.info(f"Paper trade cycle {cycle_count}")

            for symbol in symbols:
                try:
                    # Run the graph
                    result = await graph.run(symbol)

                    # Log result
                    signal = result.get("signal", {})
                    if signal.get("signal") != "FLAT":
                        logger.info(
                            "Signal generated (PAPER)",
                            symbol=symbol,
                            signal=signal.get("signal"),
                            confidence=signal.get("confidence"),
                        )

                        # Simulate execution
                        risk_params = result.get("risk_params", {})
                        if risk_params.get("approved"):
                            exec_result = await paper_executor.execute(
                                symbol=symbol,
                                order_type=signal["signal"],
                                volume=risk_params["lot_size"],
                                sl=risk_params["stop_loss"],
                                tp=risk_params["take_profit"],
                            )
                            logger.info(
                                "Paper trade executed",
                                order_id=exec_result["order_id"],
                                price=exec_result["executed_price"],
                            )

                except Exception as e:
                    logger.error("Cycle error", symbol=symbol, error=str(e))

            # Show paper account state
            state = paper_executor.get_account_state()
            logger.info(
                "Paper account state",
                balance=state["balance"],
                positions=state["open_positions"],
            )

            await asyncio.sleep(interval_seconds)

    finally:
        await mt5.disconnect()
        logger.info("Paper trading stopped")


def main():
    """Run paper trading."""
    import argparse

    parser = argparse.ArgumentParser(description="Paper trading mode")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["EURUSD"],
        help="Symbols to trade",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Cycle interval in seconds",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Maximum cycles (default: unlimited)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    setup_logging(args.log_level)

    try:
        asyncio.run(run_paper_trading(
            symbols=args.symbols,
            interval_seconds=args.interval,
            max_cycles=args.cycles,
        ))
    except KeyboardInterrupt:
        print("\nPaper trading interrupted")


if __name__ == "__main__":
    main()
