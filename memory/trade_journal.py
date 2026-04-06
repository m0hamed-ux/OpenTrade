"""Trade journal CRUD operations with SQLite."""

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any

import aiosqlite

from config.logging_config import get_logger

logger = get_logger(__name__)


class TradeJournal:
    """SQLite-based trade journal for recording and analyzing trades."""

    def __init__(self, db_path: Path | str | None = None):
        """Initialize trade journal.

        Args:
            db_path: Path to SQLite database file. Defaults to data/journal.db
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "journal.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database schema."""
        if self._initialized:
            return

        schema_path = Path(__file__).parent / "schema.sql"
        schema = schema_path.read_text()

        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(schema)
            await db.commit()

        self._initialized = True
        logger.info("Trade journal initialized", db_path=str(self.db_path))

    async def record_trade(
        self,
        symbol: str,
        order_type: str,
        entry_price: float,
        volume: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        entry_reason: str | None = None,
        signal_confidence: float | None = None,
        market_analysis: dict | None = None,
        sentiment_data: dict | None = None,
        risk_params: dict | None = None,
        ticket: int | None = None,
        magic_number: int | None = None,
    ) -> int:
        """Record a new trade entry.

        Returns:
            Trade ID
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO trades (
                    symbol, order_type, entry_price, volume, stop_loss, take_profit,
                    entry_reason, signal_confidence, market_analysis, sentiment_data,
                    risk_params, ticket, magic_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    order_type,
                    entry_price,
                    volume,
                    stop_loss,
                    take_profit,
                    entry_reason,
                    signal_confidence,
                    json.dumps(market_analysis) if market_analysis else None,
                    json.dumps(sentiment_data) if sentiment_data else None,
                    json.dumps(risk_params) if risk_params else None,
                    ticket,
                    magic_number,
                ),
            )
            await db.commit()
            trade_id = cursor.lastrowid

        logger.info(
            "Trade recorded",
            trade_id=trade_id,
            symbol=symbol,
            type=order_type,
            entry=entry_price,
        )
        return trade_id

    async def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        profit: float,
        exit_reason: str | None = None,
    ) -> None:
        """Close an open trade.

        Args:
            trade_id: Trade ID to close
            exit_price: Exit price
            profit: Profit/loss amount
            exit_reason: Reason for exit
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE trades
                SET exit_price = ?, profit = ?, exit_reason = ?, status = 'closed'
                WHERE id = ?
                """,
                (exit_price, profit, exit_reason, trade_id),
            )
            await db.commit()

        logger.info(
            "Trade closed",
            trade_id=trade_id,
            exit=exit_price,
            profit=profit,
        )

    async def get_trade(self, trade_id: int) -> dict[str, Any] | None:
        """Get a trade by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM trades WHERE id = ?",
                (trade_id,),
            )
            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_dict(row)

    async def get_open_trades(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get all open trades, optionally filtered by symbol."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            if symbol:
                cursor = await db.execute(
                    "SELECT * FROM trades WHERE status = 'open' AND symbol = ?",
                    (symbol,),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM trades WHERE status = 'open'"
                )

            rows = await cursor.fetchall()

        return [self._row_to_dict(row) for row in rows]

    async def get_trades_by_date(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get trades within a date range."""
        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if start_date:
            query += " AND date(created_at) >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date(created_at) <= ?"
            params.append(end_date.isoformat())
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        query += " ORDER BY created_at DESC"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_dict(row) for row in rows]

    async def log_cycle(
        self,
        symbol: str,
        timeframe: str,
        account_state: dict | None = None,
        market_analysis: dict | None = None,
        sentiment_analysis: dict | None = None,
        signal: dict | None = None,
        risk_params: dict | None = None,
        execution_result: dict | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> str:
        """Log a complete trading cycle.

        Returns:
            Cycle ID
        """
        await self.initialize()

        cycle_id = str(uuid.uuid4())

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO cycle_logs (
                    cycle_id, symbol, timeframe, account_state, market_analysis,
                    sentiment_analysis, signal, risk_params, execution_result,
                    error, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    symbol,
                    timeframe,
                    json.dumps(account_state) if account_state else None,
                    json.dumps(market_analysis) if market_analysis else None,
                    json.dumps(sentiment_analysis) if sentiment_analysis else None,
                    json.dumps(signal) if signal else None,
                    json.dumps(risk_params) if risk_params else None,
                    json.dumps(execution_result) if execution_result else None,
                    error,
                    duration_ms,
                ),
            )
            await db.commit()

        return cycle_id

    async def update_daily_stats(
        self,
        trade_date: date | None = None,
        starting_balance: float | None = None,
        ending_balance: float | None = None,
    ) -> None:
        """Update or create daily statistics."""
        if trade_date is None:
            trade_date = date.today()

        async with aiosqlite.connect(self.db_path) as db:
            # Get today's trades
            cursor = await db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(profit), 0) as total_profit
                FROM trades
                WHERE date(created_at) = ? AND status = 'closed'
                """,
                (trade_date.isoformat(),),
            )
            stats = await cursor.fetchone()

            total, wins, losses, total_profit = stats

            win_rate = wins / total if total > 0 else 0

            # Upsert daily stats
            await db.execute(
                """
                INSERT INTO daily_stats (date, starting_balance, ending_balance,
                    total_trades, winning_trades, losing_trades, total_profit, win_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    ending_balance = COALESCE(excluded.ending_balance, ending_balance),
                    total_trades = excluded.total_trades,
                    winning_trades = excluded.winning_trades,
                    losing_trades = excluded.losing_trades,
                    total_profit = excluded.total_profit,
                    win_rate = excluded.win_rate
                """,
                (
                    trade_date.isoformat(),
                    starting_balance or 0,
                    ending_balance,
                    total,
                    wins or 0,
                    losses or 0,
                    total_profit,
                    win_rate,
                ),
            )
            await db.commit()

    async def get_performance_summary(
        self,
        days: int = 30,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """Get performance summary for the last N days."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get overall stats
            query = """
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as winning,
                    SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losing,
                    COALESCE(SUM(profit), 0) as total_profit,
                    COALESCE(AVG(profit), 0) as avg_profit,
                    COALESCE(MAX(profit), 0) as best_trade,
                    COALESCE(MIN(profit), 0) as worst_trade
                FROM trades
                WHERE status = 'closed'
                AND created_at >= datetime('now', ?)
            """
            params = [f"-{days} days"]

            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)

            cursor = await db.execute(query, params)
            row = await cursor.fetchone()

        total, wins, losses, total_profit, avg_profit, best, worst = row

        return {
            "period_days": days,
            "total_trades": total,
            "winning_trades": wins or 0,
            "losing_trades": losses or 0,
            "win_rate": (wins / total * 100) if total > 0 else 0,
            "total_profit": round(total_profit, 2),
            "average_profit": round(avg_profit, 2),
            "best_trade": round(best, 2),
            "worst_trade": round(worst, 2),
            "profit_factor": abs(best / worst) if worst != 0 else 0,
        }

    def _row_to_dict(self, row: aiosqlite.Row) -> dict[str, Any]:
        """Convert database row to dictionary."""
        d = dict(row)

        # Parse JSON fields
        for field in ["market_analysis", "sentiment_data", "risk_params"]:
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except json.JSONDecodeError:
                    pass

        return d
