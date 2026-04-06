"""Orchestrator Agent - Master Controller."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from connectors.gemini_client import GeminiClient
from connectors.mt5_connector import MT5Connector
from connectors.news_connector import NewsConnector
from risk.circuit_breaker import CircuitBreaker
from risk.position_sizer import PositionSizer
from tools.account_tools import AccountTools
from memory.trade_journal import TradeJournal
from memory.agent_memory import AgentMemory
from config.logging_config import get_logger
from utils.time_utils import should_trade_now, get_session_info
from utils.validators import extract_json_from_response

from .prompts import ORCHESTRATOR_SYSTEM
from .market_analyst import MarketAnalystAgent
from .sentiment_agent import SentimentAgent
from .strategy_agent import StrategyAgent
from .risk_manager import RiskManagerAgent
from .execution_agent import ExecutionAgent

logger = get_logger(__name__)


class OrchestratorAgent:
    """Master agent that coordinates the trading system."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        mt5_connector: MT5Connector,
        news_connector: NewsConnector,
        circuit_breaker: CircuitBreaker,
        position_sizer: PositionSizer,
        journal: TradeJournal,
        settings: dict[str, Any],
    ):
        """Initialize orchestrator with all dependencies.

        Args:
            gemini_client: Gemini API client
            mt5_connector: MT5 connector
            news_connector: News API connector
            circuit_breaker: Circuit breaker instance
            position_sizer: Position sizer instance
            journal: Trade journal
            settings: Configuration settings
        """
        self.gemini = gemini_client
        self.mt5 = mt5_connector
        self.news = news_connector
        self.circuit_breaker = circuit_breaker
        self.sizer = position_sizer
        self.journal = journal
        self.settings = settings

        # Get database path for agent memory
        db_path = str(Path(__file__).parent.parent / "data" / "journal.db")

        # Initialize account tools
        self.account_tools = AccountTools(mt5_connector)

        # Initialize sub-agents
        models = settings.get("models", {})

        self.market_analyst = MarketAnalystAgent(
            gemini_client=gemini_client,
            memory=AgentMemory(db_path, "market_analyst"),
            model=models.get("market_analyst", "gemini-2.5-pro"),
        )

        self.sentiment_agent = SentimentAgent(
            gemini_client=gemini_client,
            news_connector=news_connector,
            memory=AgentMemory(db_path, "sentiment_agent"),
            model=models.get("sentiment_agent", "gemini-2.5-flash"),
        )

        self.strategy_agent = StrategyAgent(
            gemini_client=gemini_client,
            memory=AgentMemory(db_path, "strategy_agent"),
            model=models.get("strategy_agent", "gemini-2.5-pro"),
            min_confidence=settings.get("confidence", {}).get("min_signal_confidence", 0.65),
        )

        self.risk_manager = RiskManagerAgent(
            gemini_client=gemini_client,
            position_sizer=position_sizer,
            circuit_breaker=circuit_breaker,
            memory=AgentMemory(db_path, "risk_manager"),
            model=models.get("risk_manager", "gemini-2.5-flash"),
            max_risk_percent=settings.get("risk", {}).get("max_risk_percent", 2.0),
        )

        self.execution_agent = ExecutionAgent(
            mt5_connector=mt5_connector,
            memory=AgentMemory(db_path, "execution_agent"),
        )

        self._running = False

    async def run_cycle(self, symbol: str) -> dict[str, Any]:
        """Run a single trading cycle for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Cycle result dict
        """
        start_time = datetime.utcnow()
        cycle_result = {
            "symbol": symbol,
            "timestamp": start_time.isoformat(),
            "market_analysis": None,
            "sentiment": None,
            "signal": None,
            "risk_params": None,
            "execution": None,
            "error": None,
        }

        try:
            # Get account state
            account_state = await self.account_tools.get_full_state()

            # Get OHLCV data
            timeframe = self.settings.get("trading", {}).get("timeframe", "M15")
            candle_count = self.settings.get("trading", {}).get("candle_count", 100)

            ohlcv = await self.mt5.get_ohlcv(symbol, timeframe, candle_count)

            # Run market analysis and sentiment in parallel
            market_task = self.market_analyst.analyze(symbol, timeframe, ohlcv)
            sentiment_task = self.sentiment_agent.analyze(symbol)

            market_analysis, sentiment = await asyncio.gather(
                market_task,
                sentiment_task,
            )

            cycle_result["market_analysis"] = market_analysis
            cycle_result["sentiment"] = sentiment

            # Generate signal
            signal = await self.strategy_agent.generate_signal(
                symbol=symbol,
                market_analysis=market_analysis,
                sentiment_analysis=sentiment,
                account_state=account_state,
            )
            cycle_result["signal"] = signal

            # If signal is FLAT, skip risk management and execution
            if signal["signal"] == "FLAT":
                logger.info("No trade signal", symbol=symbol)
                return cycle_result

            # Get current price
            current_price = await self.mt5.get_current_price(symbol)

            # Validate and size position
            risk_params = await self.risk_manager.validate_and_size(
                symbol=symbol,
                signal=signal,
                market_analysis=market_analysis,
                account_state=account_state,
                current_price=current_price,
            )
            cycle_result["risk_params"] = risk_params

            # If not approved, skip execution
            if not risk_params.get("approved", False):
                logger.info(
                    "Trade rejected by risk manager",
                    symbol=symbol,
                    reason=risk_params.get("rejection_reason"),
                )
                return cycle_result

            # Execute trade
            execution = await self.execution_agent.execute_trade(
                symbol=symbol,
                signal=signal,
                risk_params=risk_params,
            )
            cycle_result["execution"] = execution

            # Record in journal
            if execution.get("success"):
                self.circuit_breaker.record_trade()
                self.account_tools.record_trade(execution)

                await self.journal.record_trade(
                    symbol=symbol,
                    order_type=signal["signal"],
                    entry_price=execution["executed_price"],
                    volume=execution["executed_volume"],
                    stop_loss=risk_params["stop_loss"],
                    take_profit=risk_params["take_profit"],
                    entry_reason=signal["entry_reason"],
                    signal_confidence=signal["confidence"],
                    market_analysis=market_analysis,
                    sentiment_data=sentiment,
                    risk_params=risk_params,
                    ticket=execution.get("order_id"),
                )

        except Exception as e:
            logger.error("Cycle error", symbol=symbol, error=str(e))
            cycle_result["error"] = str(e)

        # Log cycle
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        await self.journal.log_cycle(
            symbol=symbol,
            timeframe=timeframe,
            account_state=account_state,
            market_analysis=cycle_result["market_analysis"],
            sentiment_analysis=cycle_result["sentiment"],
            signal=cycle_result["signal"],
            risk_params=cycle_result["risk_params"],
            execution_result=cycle_result["execution"],
            error=cycle_result["error"],
            duration_ms=int(duration),
        )

        return cycle_result

    async def check_preconditions(self) -> tuple[bool, str]:
        """Check if trading should proceed.

        Returns:
            Tuple of (should_proceed, reason)
        """
        # Check market hours
        can_trade, reason = should_trade_now()
        if not can_trade:
            return False, reason

        # Get account state
        account_state = await self.account_tools.get_full_state()

        # Initialize circuit breaker for the day
        self.circuit_breaker.initialize_day(account_state["balance"])

        # Check circuit breaker
        positions = await self.mt5.get_positions()
        allowed, cb_reason = self.circuit_breaker.check_preconditions(
            current_equity=account_state["equity"],
            open_position_count=len(positions),
        )

        if not allowed:
            return False, cb_reason

        return True, "All preconditions met"

    async def decide_symbols(self, account_state: dict[str, Any]) -> list[str]:
        """Use AI to decide which symbols to analyze.

        Args:
            account_state: Current account state

        Returns:
            List of symbols to analyze
        """
        configured_symbols = self.settings.get("trading", {}).get("symbols", ["EURUSD"])

        # Get current positions
        positions = await self.mt5.get_positions()
        position_symbols = [p.symbol for p in positions]

        session_info = get_session_info()

        prompt = f"""
Given the current trading conditions, decide which symbols to analyze:

Available Symbols: {configured_symbols}
Currently Holding: {position_symbols}

Account State:
- Balance: ${account_state.get('balance', 0):.2f}
- Equity: ${account_state.get('equity', 0):.2f}
- Open Positions: {len(positions)}
- Max Allowed Positions: {self.settings.get('risk', {}).get('max_open_positions', 3)}

Market Session:
- Active Sessions: {session_info.get('active_sessions', [])}
- Is Overlap: {session_info.get('is_overlap', False)}

Daily Stats:
- Trade Count: {self.circuit_breaker.status.get('trade_count', 0)}
- Max Trades: {self.circuit_breaker.status.get('max_trades', 10)}

Rules:
1. Don't analyze symbols we already have positions in (unless evaluating exit)
2. Prioritize symbols active in current session
3. If near max positions, be selective
4. If low on daily trade count, can analyze more symbols

Respond with JSON: {{"proceed": boolean, "reason": "explanation", "symbols_to_analyze": ["SYMBOL1", "SYMBOL2"]}}
"""

        response = await self.gemini.generate(
            prompt=prompt,
            model_name=self.settings.get("models", {}).get("orchestrator", "gemini-2.5-pro"),
            system_instruction=ORCHESTRATOR_SYSTEM,
            temperature=0.3,
            response_format="json",
        )

        try:
            json_str = extract_json_from_response(response)
            if json_str:
                decision = json.loads(json_str)
                if decision.get("proceed", False):
                    return decision.get("symbols_to_analyze", configured_symbols[:1])
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Symbol decision parse error", error=str(e))

        # Default to first symbol
        return [s for s in configured_symbols if s not in position_symbols][:1]

    async def run(self, interval_seconds: int | None = None) -> None:
        """Run the orchestrator loop.

        Args:
            interval_seconds: Cycle interval in seconds (uses settings if None)
        """
        if interval_seconds is None:
            interval_seconds = self.settings.get("trading", {}).get("cycle_interval_seconds", 60)

        self._running = True
        logger.info("Orchestrator starting", interval=interval_seconds)

        # Initialize journal
        await self.journal.initialize()

        while self._running:
            try:
                # Check preconditions
                should_proceed, reason = await self.check_preconditions()

                if not should_proceed:
                    logger.info("Trading paused", reason=reason)
                    await asyncio.sleep(interval_seconds)
                    continue

                # Get account state and decide symbols
                account_state = await self.account_tools.get_full_state()
                symbols = await self.decide_symbols(account_state)

                if not symbols:
                    logger.info("No symbols to analyze")
                    await asyncio.sleep(interval_seconds)
                    continue

                # Run cycles for each symbol
                for symbol in symbols:
                    logger.info("Running cycle", symbol=symbol)
                    result = await self.run_cycle(symbol)

                    if result.get("execution", {}).get("success"):
                        logger.info(
                            "Trade executed",
                            symbol=symbol,
                            order_id=result["execution"]["order_id"],
                        )

            except Exception as e:
                logger.error("Orchestrator error", error=str(e))

            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        """Stop the orchestrator loop."""
        logger.info("Stopping orchestrator")
        self._running = False
