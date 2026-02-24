"""Chat history persistence layer using SQLite."""

import aiosqlite
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Ensure data directory exists
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "chat_history.db")


class ChatDatabase:
    """Manages chat message persistence and retrieval."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """Initialize database connection path.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path

    async def initialize(self) -> None:
        """Create database tables if they don't exist."""
        try:
            async with aiosqlite.connect(
                self.db_path,
                timeout=20.0,
            ) as db:
                # Enable WAL mode for better concurrency
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL")
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT,
                        tool_calls TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await db.commit()
                logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str],
        tool_calls: Optional[dict] = None,
    ) -> None:
        """Store a chat message in the database.

        Args:
            session_id: Unique session identifier.
            role: Message role (user, assistant, tool, system).
            content: Message text content.
            tool_calls: Optional tool function calls in JSON format.
        """
        if not session_id or not role:
            raise ValueError("session_id and role are required")

        try:
            async with aiosqlite.connect(
                self.db_path,
                timeout=20.0,
            ) as db:
                tool_calls_json = json.dumps(tool_calls) if tool_calls else None
                await db.execute(
                    """
                    INSERT INTO messages (session_id, role, content, tool_calls)
                    VALUES (?, ?, ?, ?)
                    """,
                    (session_id, role, content, tool_calls_json),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            raise

    async def get_conversation_history(self, session_id: str) -> list[dict]:
        """Retrieve chat history for a session.

        Args:
            session_id: Session to retrieve history for.

        Returns:
            List of message dictionaries with role and content.
        """
        try:
            async with aiosqlite.connect(
                self.db_path,
                timeout=20.0,
            ) as db:
                async with db.execute(
                    """
                    SELECT role, content, tool_calls FROM messages
                    WHERE session_id = ? ORDER BY created_at
                    """,
                    (session_id,),
                ) as cursor:
                    rows = await cursor.fetchall()

            messages = []
            for role, content, tool_calls_raw in rows:
                if role == "tool":
                    continue

                message = {"role": role, "content": content or ""}
                if tool_calls_raw:
                    message["tool_calls"] = json.loads(tool_calls_raw)
                messages.append(message)

            return messages
        except Exception as e:
            logger.error(f"Failed to retrieve conversation history: {e}")
            raise


# Global instance for backward compatibility
_db_instance = ChatDatabase()


async def init_db() -> None:
    """Initialize the default database instance."""
    await _db_instance.initialize()


async def save_message(
    session_id: str, role: str, content: Optional[str], tool_calls=None
) -> None:
    """Save message using default database instance."""
    await _db_instance.save_message(session_id, role, content, tool_calls)


async def get_chat_history(session_id: str) -> list[dict]:
    """Get chat history using default database instance."""
    return await _db_instance.get_conversation_history(session_id)
