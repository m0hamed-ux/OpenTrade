"""LangGraph workflow for the trading system."""

import asyncio
from datetime import datetime
from typing import Any, Literal

import pandas as pd
from langgraph.graph import StateGraph, END

from config.logging_config import get_logger
from connectors.gemini_client import GeminiClient
from connectors.mt5_connector import MT5Connector
from connectors.news_connector import NewsConnector
from risk.circuit_breaker import CircuitBreaker
from risk.position_sizer import PositionSizer
from memory.trade_journal import TradeJournal
from tools.account_tools import AccountTools
from agents.market_analyst import MarketAnalystAgent
from agents.sentiment_agent import SentimentAgent
from agents.strategy_agent import StrategyAgent
from agents.risk_manager import RiskManagerAgent
from agents.execution_agent import ExecutionAgent
from utils.time_utils import should_trade_now

from .state import TradingState, create_initial_state, update_state

logger = get_logger(__name__)


class TradingGraph:
    """LangGraph workflow for trading operations."""

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
        """Initialize the trading graph.

        Args:
            gemini_client: Gemini API client
            mt5_connector: MT5 connector
            news_connector: News connector
            circuit_breaker: Circuit breaker
            position_sizer: Position sizer
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

        self.account_tools = AccountTools(mt5_connector)

        # Initialize agents
        models = settings.get("models", {})

        self.market_analyst = MarketAnalystAgent(
            gemini_client=gemini_client,
            model=models.get("market_analyst", "gemini-2.5-pro"),
        )

        self.sentiment_agent = SentimentAgent(
            gemini_client=gemini_client,
            news_connector=news_connector,
            model=models.get("sentiment_agent", "gemini-2.5-flash"),
        )

        self.strategy_agent = StrategyAgent(
            gemini_client=gemini_client,
            model=models.get("strategy_agent", "gemini-2.5-pro"),
            min_confidence=settings.get("confidence", {}).get("min_signal_confidence", 0.65),
        )

        self.risk_manager = RiskManagerAgent(
            gemini_client=gemini_client,
            position_sizer=position_sizer,
            circuit_breaker=circuit_breaker,
            model=models.get("risk_manager", "gemini-2.5-flash"),
            max_risk_percent=settings.get("risk", {}).get("max_risk_percent", 2.0),
        )

        self.execution_agent = ExecutionAgent(
            mt5_connector=mt5_connector,
        )

        # Build the graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph.

        Returns:
            Compiled StateGraph
        """
        # Create the graph
        workflow = StateGraph(TradingState)

        # Add nodes
        workflow.add_node("check_preconditions", self._check_preconditions)
        workflow.add_node("run_analysis", self._run_analysis)
        workflow.add_node("generate_signal", self._generate_signal)
        workflow.add_node("validate_risk", self._validate_risk)
        workflow.add_node("execute_trade", self._execute_trade)
        workflow.add_node("log_cycle", self._log_cycle)

        # Set entry point
        workflow.set_entry_point("check_preconditions")

        # Add edges
        workflow.add_conditional_edges(
            "check_preconditions",
            self._should_continue_after_preconditions,
            {
                "continue": "run_analysis",
                "end": "log_cycle",
            },
        )

        workflow.add_edge("run_analysis", "generate_signal")

        workflow.add_conditional_edges(
            "generate_signal",
            self._should_continue_after_signal,
            {
                "continue": "validate_risk",
                "end": "log_cycle",
            },
        )

        workflow.add_conditional_edges(
            "validate_risk",
            self._should_continue_after_risk,
            {
                "continue": "execute_trade",
                "end": "log_cycle",
            },
        )

        workflow.add_edge("execute_trade", "log_cycle")
        workflow.add_edge("log_cycle", END)

        return workflow.compile()

    async def _check_preconditions(self, state: TradingState) -> TradingState:
        """Check if trading should proceed."""
        logger.debug("Checking preconditions", symbol=state["symbol"])

        # Check market hours
        can_trade, reason = should_trade_now()
        if not can_trade:
            return update_state(
                state,
                should_continue=False,
                error=reason,
                node_name="check_preconditions",
            )

        # Initialize circuit breaker
        self.circuit_breaker.initialize_day(state["account"]["balance"])

        # Check circuit breaker
        positions = await self.mt5.get_positions()
        allowed, cb_reason = self.circuit_breaker.check_preconditions(
            current_equity=state["account"]["equity"],
            open_position_count=len(positions),
        )

        if not allowed:
            return update_state(
                state,
                should_continue=False,
                error=cb_reason,
                node_name="check_preconditions",
            )

        return update_state(
            state,
            should_continue=True,
            node_name="check_preconditions",
        )

    def _should_continue_after_preconditions(
        self,
        state: TradingState,
    ) -> Literal["continue", "end"]:
        """Route after preconditions check."""
        return "continue" if state["should_continue"] else "end"

    async def _run_analysis(self, state: TradingState) -> TradingState:
        """Run market and sentiment analysis in parallel."""
        logger.debug("Running analysis", symbol=state["symbol"])

        try:
            # Convert OHLCV list to DataFrame
            ohlcv_df = pd.DataFrame(state["ohlcv"])
            if "time" in ohlcv_df.columns:
                ohlcv_df["time"] = pd.to_datetime(ohlcv_df["time"])

            # Run analysis in parallel
            market_task = self.market_analyst.analyze(
                symbol=state["symbol"],
                timeframe=state["timeframe"],
                ohlcv_data=ohlcv_df,
            )
            sentiment_task = self.sentiment_agent.analyze(state["symbol"])

            market_analysis, sentiment = await asyncio.gather(
                market_task,
                sentiment_task,
            )

            return update_state(
                state,
                market_analysis=market_analysis,
                sentiment=sentiment,
                node_name="run_analysis",
            )

        except Exception as e:
            logger.error("Analysis failed", error=str(e))
            return update_state(
                state,
                error=str(e),
                should_continue=False,
                node_name="run_analysis",
            )

    async def _generate_signal(self, state: TradingState) -> TradingState:
        """Generate trading signal from analysis."""
        logger.debug("Generating signal", symbol=state["symbol"])

        try:
            signal = await self.strategy_agent.generate_signal(
                symbol=state["symbol"],
                market_analysis=state["market_analysis"],
                sentiment_analysis=state["sentiment"],
                account_state=state["account"],
            )

            should_continue = signal["signal"] != "FLAT"

            return update_state(
                state,
                signal=signal,
                should_continue=should_continue,
                node_name="generate_signal",
            )

        except Exception as e:
            logger.error("Signal generation failed", error=str(e))
            return update_state(
                state,
                error=str(e),
                should_continue=False,
                node_name="generate_signal",
            )

    def _should_continue_after_signal(
        self,
        state: TradingState,
    ) -> Literal["continue", "end"]:
        """Route after signal generation."""
        if not state["should_continue"]:
            return "end"
        if state.get("signal", {}).get("signal") == "FLAT":
            return "end"
        return "continue"

    async def _validate_risk(self, state: TradingState) -> TradingState:
        """Validate and size the trade."""
        logger.debug("Validating risk", symbol=state["symbol"])

        try:
            # Get current price
            current_price = await self.mt5.get_current_price(state["symbol"])

            risk_params = await self.risk_manager.validate_and_size(
                symbol=state["symbol"],
                signal=state["signal"],
                market_analysis=state["market_analysis"],
                account_state=state["account"],
                current_price=current_price,
            )

            should_continue = risk_params.get("approved", False)

            return update_state(
                state,
                risk_params=risk_params,
                should_continue=should_continue,
                node_name="validate_risk",
            )

        except Exception as e:
            logger.error("Risk validation failed", error=str(e))
            return update_state(
                state,
                error=str(e),
                should_continue=False,
                node_name="validate_risk",
            )

    def _should_continue_after_risk(
        self,
        state: TradingState,
    ) -> Literal["continue", "end"]:
        """Route after risk validation."""
        if not state["should_continue"]:
            return "end"
        if not state.get("risk_params", {}).get("approved", False):
            return "end"
        return "continue"

    async def _execute_trade(self, state: TradingState) -> TradingState:
        """Execute the trade."""
        logger.debug("Executing trade", symbol=state["symbol"])

        try:
            execution_result = await self.execution_agent.execute_trade(
                symbol=state["symbol"],
                signal=state["signal"],
                risk_params=state["risk_params"],
            )

            # Record in circuit breaker if successful
            if execution_result.get("success"):
                self.circuit_breaker.record_trade()

            return update_state(
                state,
                execution_result=execution_result,
                node_name="execute_trade",
            )

        except Exception as e:
            logger.error("Execution failed", error=str(e))
            return update_state(
                state,
                execution_result={"success": False, "error": str(e)},
                error=str(e),
                node_name="execute_trade",
            )

    async def _log_cycle(self, state: TradingState) -> TradingState:
        """Log the complete cycle."""
        logger.debug("Logging cycle", symbol=state["symbol"])

        # Calculate duration
        started_at = state["cycle_log"].get("started_at")
        if started_at:
            start = datetime.fromisoformat(started_at)
            duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        else:
            duration_ms = 0

        # Log to journal
        await self.journal.log_cycle(
            symbol=state["symbol"],
            timeframe=state["timeframe"],
            account_state=state["account"],
            market_analysis=state["market_analysis"],
            sentiment_analysis=state["sentiment"],
            signal=state["signal"],
            risk_params=state["risk_params"],
            execution_result=state["execution_result"],
            error=state["error"],
            duration_ms=duration_ms,
        )

        # Record trade if executed
        if state.get("execution_result", {}).get("success"):
            await self.journal.record_trade(
                symbol=state["symbol"],
                order_type=state["signal"]["signal"],
                entry_price=state["execution_result"]["executed_price"],
                volume=state["execution_result"]["executed_volume"],
                stop_loss=state["risk_params"]["stop_loss"],
                take_profit=state["risk_params"]["take_profit"],
                entry_reason=state["signal"]["entry_reason"],
                signal_confidence=state["signal"]["confidence"],
                market_analysis=state["market_analysis"],
                sentiment_data=state["sentiment"],
                risk_params=state["risk_params"],
                ticket=state["execution_result"].get("order_id"),
            )

        # Update cycle log
        state["cycle_log"]["completed_at"] = datetime.utcnow().isoformat()
        state["cycle_log"]["duration_ms"] = duration_ms

        return update_state(state, node_name="log_cycle")

    async def run(
        self,
        symbol: str,
        timeframe: str | None = None,
    ) -> TradingState:
        """Run the trading graph for a symbol.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (uses settings if None)

        Returns:
            Final state after graph execution
        """
        if timeframe is None:
            timeframe = self.settings.get("trading", {}).get("timeframe", "M15")

        # Get initial data
        account = await self.account_tools.get_full_state()

        candle_count = self.settings.get("trading", {}).get("candle_count", 100)
        ohlcv_df = await self.mt5.get_ohlcv(symbol, timeframe, candle_count)

        # Convert DataFrame to list of dicts for state
        ohlcv_list = ohlcv_df.to_dict("records")
        for candle in ohlcv_list:
            if hasattr(candle.get("time"), "isoformat"):
                candle["time"] = candle["time"].isoformat()

        # Create initial state
        initial_state = create_initial_state(
            symbol=symbol,
            timeframe=timeframe,
            account=account,
            ohlcv=ohlcv_list,
        )

        # Initialize journal
        await self.journal.initialize()

        # Run the graph
        final_state = await self.graph.ainvoke(initial_state)

        return final_state
