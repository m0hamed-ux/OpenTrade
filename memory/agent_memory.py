"""Short-term context store per agent."""

import json
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

from config.logging_config import get_logger

logger = get_logger(__name__)


class AgentMemory:
    """Short-term context store for individual agents.

    Stores observations, decisions, and patterns that agents can reference
    during the current trading session.
    """

    def __init__(self, db_path: str, agent_name: str):
        """Initialize agent memory.

        Args:
            db_path: Path to SQLite database
            agent_name: Name of the agent (e.g., "market_analyst")
        """
        self.db_path = db_path
        self.agent_name = agent_name
        self._cache: dict[str, list[dict]] = {}

    async def store(
        self,
        memory_type: str,
        content: dict[str, Any],
        symbol: str | None = None,
        ttl_minutes: int = 60,
    ) -> int:
        """Store a memory entry.

        Args:
            memory_type: Type of memory (observation, decision, feedback, pattern)
            content: Memory content
            symbol: Optional symbol context
            ttl_minutes: Time-to-live in minutes

        Returns:
            Memory ID
        """
        expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO agent_memory (agent_name, symbol, memory_type, content, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.agent_name,
                    symbol,
                    memory_type,
                    json.dumps(content),
                    expires_at.isoformat(),
                ),
            )
            await db.commit()
            memory_id = cursor.lastrowid

        # Update cache
        cache_key = f"{memory_type}:{symbol or 'all'}"
        if cache_key not in self._cache:
            self._cache[cache_key] = []
        self._cache[cache_key].append({
            "id": memory_id,
            "content": content,
            "expires_at": expires_at,
        })

        return memory_id

    async def recall(
        self,
        memory_type: str | None = None,
        symbol: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Recall recent memories.

        Args:
            memory_type: Optional type filter
            symbol: Optional symbol filter
            limit: Maximum memories to return

        Returns:
            List of memory entries
        """
        query = """
            SELECT id, memory_type, symbol, content, created_at
            FROM agent_memory
            WHERE agent_name = ?
            AND (expires_at IS NULL OR expires_at > datetime('now'))
        """
        params = [self.agent_name]

        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        if symbol:
            query += " AND (symbol = ? OR symbol IS NULL)"
            params.append(symbol)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        memories = []
        for row in rows:
            memory = dict(row)
            try:
                memory["content"] = json.loads(memory["content"])
            except json.JSONDecodeError:
                pass
            memories.append(memory)

        return memories

    async def recall_recent_decisions(
        self,
        symbol: str,
        minutes: int = 30,
    ) -> list[dict[str, Any]]:
        """Recall recent trading decisions for a symbol.

        Args:
            symbol: Trading symbol
            minutes: How far back to look

        Returns:
            List of recent decisions
        """
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT content, created_at
                FROM agent_memory
                WHERE agent_name = ?
                AND memory_type = 'decision'
                AND symbol = ?
                AND created_at > ?
                ORDER BY created_at DESC
                """,
                (self.agent_name, symbol, cutoff.isoformat()),
            )
            rows = await cursor.fetchall()

        decisions = []
        for row in rows:
            try:
                content = json.loads(row["content"])
                content["timestamp"] = row["created_at"]
                decisions.append(content)
            except json.JSONDecodeError:
                pass

        return decisions

    async def get_pattern_history(
        self,
        symbol: str,
        pattern_type: str,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """Get historical pattern occurrences.

        Args:
            symbol: Trading symbol
            pattern_type: Type of pattern to search
            days: Days to look back

        Returns:
            List of pattern occurrences
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT content, created_at
                FROM agent_memory
                WHERE agent_name = ?
                AND memory_type = 'pattern'
                AND symbol = ?
                AND created_at > ?
                AND content LIKE ?
                ORDER BY created_at DESC
                """,
                (
                    self.agent_name,
                    symbol,
                    cutoff.isoformat(),
                    f'%"{pattern_type}"%',
                ),
            )
            rows = await cursor.fetchall()

        patterns = []
        for row in rows:
            try:
                content = json.loads(row["content"])
                content["timestamp"] = row["created_at"]
                patterns.append(content)
            except json.JSONDecodeError:
                pass

        return patterns

    async def store_feedback(
        self,
        symbol: str,
        decision_id: int,
        outcome: str,
        profit: float | None = None,
        notes: str | None = None,
    ) -> int:
        """Store feedback about a past decision.

        Args:
            symbol: Trading symbol
            decision_id: ID of the decision being evaluated
            outcome: Outcome description (e.g., "correct", "incorrect", "partial")
            profit: Associated profit/loss
            notes: Additional notes

        Returns:
            Feedback memory ID
        """
        content = {
            "decision_id": decision_id,
            "outcome": outcome,
            "profit": profit,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat(),
        }

        return await self.store(
            memory_type="feedback",
            content=content,
            symbol=symbol,
            ttl_minutes=60 * 24 * 7,  # Keep feedback for 7 days
        )

    async def cleanup_expired(self) -> int:
        """Remove expired memories.

        Returns:
            Number of memories deleted
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                DELETE FROM agent_memory
                WHERE agent_name = ?
                AND expires_at IS NOT NULL
                AND expires_at < datetime('now')
                """,
                (self.agent_name,),
            )
            await db.commit()
            deleted = cursor.rowcount

        if deleted > 0:
            logger.debug(
                "Cleaned up expired memories",
                agent=self.agent_name,
                deleted=deleted,
            )

        # Clear cache
        self._cache.clear()

        return deleted

    async def get_context_summary(self, symbol: str) -> dict[str, Any]:
        """Get a summary of recent context for prompt injection.

        Args:
            symbol: Trading symbol

        Returns:
            Context summary dict
        """
        recent_decisions = await self.recall_recent_decisions(symbol, minutes=60)
        recent_observations = await self.recall(
            memory_type="observation",
            symbol=symbol,
            limit=5,
        )
        recent_feedback = await self.recall(
            memory_type="feedback",
            symbol=symbol,
            limit=3,
        )

        return {
            "recent_decisions_count": len(recent_decisions),
            "last_decision": recent_decisions[0] if recent_decisions else None,
            "recent_observations": [o.get("content") for o in recent_observations],
            "feedback_summary": [
                {
                    "outcome": f.get("content", {}).get("outcome"),
                    "profit": f.get("content", {}).get("profit"),
                }
                for f in recent_feedback
            ],
        }
