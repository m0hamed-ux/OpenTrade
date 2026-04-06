"""OpenTrade - Multi-Agent Trading System Entry Point."""

import asyncio
import json
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv
import os

# Add trading_bot to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config.logging_config import setup_logging, get_logger
from connectors.gemini_client import GeminiClient
from connectors.mt5_connector import MT5Connector
from connectors.news_connector import NewsConnector, MockNewsConnector
from risk.circuit_breaker import CircuitBreaker
from risk.position_sizer import PositionSizer
from memory.trade_journal import TradeJournal
from agents.orchestrator import OrchestratorAgent
from graph.trading_graph import TradingGraph


def load_settings() -> dict:
    """Load settings from config file."""
    settings_path = Path(__file__).parent / "config" / "settings.json"
    with open(settings_path) as f:
        return json.load(f)


def create_components(settings: dict) -> tuple:
    """Create all system components.

    Args:
        settings: Configuration settings

    Returns:
        Tuple of (gemini_client, mt5_connector, news_connector, circuit_breaker, position_sizer, journal)
    """
    # Load environment variables
    load_dotenv()

    # Gemini client
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")

    gemini_client = GeminiClient(api_key=gemini_api_key)

    # MT5 connector
    mt5_login = os.getenv("MT5_LOGIN")
    mt5_password = os.getenv("MT5_PASSWORD")
    mt5_server = os.getenv("MT5_SERVER")
    mt5_path = os.getenv("MT5_PATH")

    if not all([mt5_login, mt5_password, mt5_server]):
        raise ValueError("MT5 credentials not found in environment")

    mt5_connector = MT5Connector(
        login=int(mt5_login),
        password=mt5_password,
        server=mt5_server,
        path=mt5_path,
    )

    # News connector
    news_enabled = os.getenv("NEWS_API_ENABLED", "false").lower() == "true"
    news_api_key = os.getenv("NEWS_API_KEY")

    if news_enabled and news_api_key:
        news_connector = NewsConnector(api_key=news_api_key, enabled=True)
    else:
        news_connector = MockNewsConnector()

    # Risk components
    risk_settings = settings.get("risk", {})

    circuit_breaker = CircuitBreaker(
        max_daily_loss_percent=risk_settings.get("max_daily_loss_percent", 5.0),
        max_trades_per_day=risk_settings.get("max_trades_per_day", 10),
        max_open_positions=risk_settings.get("max_open_positions", 3),
        max_risk_percent=risk_settings.get("max_risk_percent", 2.0),
        state_file=Path(__file__).parent / "data" / "circuit_breaker.json",
    )

    position_sizer = PositionSizer(
        default_risk_percent=risk_settings.get("max_risk_percent", 2.0) / 2,
        min_lot_size=risk_settings.get("default_lot_size", 0.01),
        min_rr_ratio=risk_settings.get("min_rr_ratio", 1.5),
    )

    # Trade journal
    journal = TradeJournal()

    return (
        gemini_client,
        mt5_connector,
        news_connector,
        circuit_breaker,
        position_sizer,
        journal,
    )


async def run_single_cycle(symbol: str, settings: dict) -> dict:
    """Run a single trading cycle using the LangGraph workflow.

    Args:
        symbol: Trading symbol
        settings: Configuration settings

    Returns:
        Final state dict
    """
    logger = get_logger(__name__)
    logger.info("Running single cycle", symbol=symbol)

    components = create_components(settings)
    gemini, mt5, news, circuit_breaker, sizer, journal = components

    try:
        # Connect to MT5
        connected = await mt5.connect()
        if not connected:
            raise RuntimeError("Failed to connect to MT5")

        # Create trading graph
        graph = TradingGraph(
            gemini_client=gemini,
            mt5_connector=mt5,
            news_connector=news,
            circuit_breaker=circuit_breaker,
            position_sizer=sizer,
            journal=journal,
            settings=settings,
        )

        # Run the graph
        result = await graph.run(symbol)

        return result

    finally:
        await mt5.disconnect()
        if hasattr(news, "close"):
            await news.close()


async def run_orchestrator(settings: dict) -> None:
    """Run the full orchestrator loop.

    Args:
        settings: Configuration settings
    """
    logger = get_logger(__name__)
    logger.info("Starting orchestrator")

    components = create_components(settings)
    gemini, mt5, news, circuit_breaker, sizer, journal = components

    orchestrator = None

    try:
        # Connect to MT5
        connected = await mt5.connect()
        if not connected:
            raise RuntimeError("Failed to connect to MT5")

        logger.info("MT5 connected successfully")

        # Create orchestrator
        orchestrator = OrchestratorAgent(
            gemini_client=gemini,
            mt5_connector=mt5,
            news_connector=news,
            circuit_breaker=circuit_breaker,
            position_sizer=sizer,
            journal=journal,
            settings=settings,
        )

        # Setup signal handlers for graceful shutdown
        def handle_shutdown(signum, frame):
            logger.info("Shutdown signal received")
            if orchestrator:
                orchestrator.stop()

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        # Run the orchestrator
        await orchestrator.run()

    except Exception as e:
        logger.error("Orchestrator error", error=str(e))
        raise

    finally:
        await mt5.disconnect()
        if hasattr(news, "close"):
            await news.close()
        logger.info("Orchestrator stopped")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="OpenTrade Multi-Agent Trading System")
    parser.add_argument(
        "--mode",
        choices=["live", "single", "paper"],
        default="paper",
        help="Trading mode: live (full loop), single (one cycle), paper (simulation)",
    )
    parser.add_argument(
        "--symbol",
        default="EURUSD",
        help="Symbol for single cycle mode",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(log_level=args.log_level)
    logger = get_logger(__name__)

    # Load settings
    settings = load_settings()

    logger.info(
        "OpenTrade starting",
        mode=args.mode,
        symbols=settings.get("trading", {}).get("symbols", []),
    )

    try:
        if args.mode == "single":
            result = await run_single_cycle(args.symbol, settings)
            logger.info("Cycle complete", result=result)

        elif args.mode in ["live", "paper"]:
            if args.mode == "paper":
                logger.warning("Paper trading mode - no real orders will be placed")
                # In paper mode, you would typically use a mock execution agent
                # For now, this is handled by checking TRADING_MODE env var

            await run_orchestrator(settings)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error("Fatal error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
