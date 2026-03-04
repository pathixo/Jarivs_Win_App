"""
Database Module — Centralized SQLite Database Manager
======================================================
Provides a thread-safe, migration-aware SQLite database layer for Jarvis.
All persistent state (user profiles, preferences, memories, conversation
history) flows through this single manager.

Schema is evolved via numbered migrations that run automatically on startup.
All tables include `user_id` and timing columns for future cloud-sync readiness.

Usage:
    from Jarvis.core.database import get_database
    db = get_database()
    db.execute("INSERT INTO users ...", (...))
    rows = db.fetch_all("SELECT * FROM users WHERE id = ?", (uid,))
"""

import logging
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Optional

from Jarvis.config import DATA_DIR

logger = logging.getLogger("jarvis.database")

# ─────────────────────────── Singleton ──────────────────────────────────────

_instance: Optional["DatabaseManager"] = None
_instance_lock = threading.Lock()


def get_database() -> "DatabaseManager":
    """Return the global DatabaseManager singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DatabaseManager()
    return _instance


# ─────────────────────────── DatabaseManager ────────────────────────────────

class DatabaseManager:
    """
    Thread-safe SQLite database manager with automatic migrations.

    • WAL mode for concurrent read/write
    • One connection per thread via threading.local()
    • Sequential migration system (v0 → v1 → v2 → ...)
    """

    DB_FILENAME = "jarvis.db"

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or os.path.join(DATA_DIR, self.DB_FILENAME)
        self._local = threading.local()
        self._write_lock = threading.Lock()

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

        # Run migrations on the main thread connection
        self._run_migrations()

        logger.info("DatabaseManager ready — %s", self._db_path)

    # ── Connection Management ────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a connection for the current thread."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    # ── Public API ───────────────────────────────────────────────────────

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a write query (INSERT/UPDATE/DELETE) with thread safety."""
        with self._write_lock:
            conn = self._get_conn()
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor

    def execute_many(self, sql: str, param_list: list[tuple]) -> None:
        """Execute a batch of write queries."""
        with self._write_lock:
            conn = self._get_conn()
            conn.executemany(sql, param_list)
            conn.commit()

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row (read-only, no lock needed with WAL)."""
        conn = self._get_conn()
        return conn.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Fetch all matching rows."""
        conn = self._get_conn()
        return conn.execute(sql, params).fetchall()

    def fetch_scalar(self, sql: str, params: tuple = (), default: Any = None) -> Any:
        """Fetch a single scalar value (first column of first row)."""
        row = self.fetch_one(sql, params)
        return row[0] if row else default

    @property
    def path(self) -> str:
        return self._db_path

    # ── Migration System ─────────────────────────────────────────────────

    def _run_migrations(self) -> None:
        """Run all pending migrations sequentially."""
        conn = self._get_conn()

        # Create the schema_version table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at REAL NOT NULL
            )
        """)
        conn.commit()

        current = self.fetch_scalar(
            "SELECT MAX(version) FROM schema_version", default=0
        ) or 0

        migrations = [
            (1, self._migrate_v1),
            (2, self._migrate_v2),
        ]

        for version, migrate_fn in migrations:
            if version > current:
                logger.info("Running migration v%d ...", version)
                try:
                    migrate_fn(conn)
                    conn.execute(
                        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                        (version, time.time()),
                    )
                    conn.commit()
                    logger.info("Migration v%d complete.", version)
                except Exception as e:
                    logger.error("Migration v%d FAILED: %s", version, e)
                    conn.rollback()
                    raise

    # ── Migration v1: Core tables ────────────────────────────────────────

    @staticmethod
    def _migrate_v1(conn: sqlite3.Connection) -> None:
        """
        v1 — Create users, preferences, and memories tables.
        """
        conn.executescript("""
            -- Users table (profile)
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT    PRIMARY KEY,
                sync_token  TEXT,
                display_name TEXT   DEFAULT '',
                email       TEXT    DEFAULT '',
                mobile      TEXT    DEFAULT '',
                avatar_path TEXT    DEFAULT '',
                avatar_url  TEXT    DEFAULT '',
                created_at  REAL   NOT NULL,
                updated_at  REAL   NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

            -- Preferences table (key-value per user per category)
            CREATE TABLE IF NOT EXISTS preferences (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category    TEXT    NOT NULL,
                key         TEXT    NOT NULL,
                value       TEXT    DEFAULT '',
                updated_at  REAL   NOT NULL,
                UNIQUE(user_id, category, key)
            );
            CREATE INDEX IF NOT EXISTS idx_prefs_user_cat ON preferences(user_id, category);

            -- Memories table (AI personalization facts)
            CREATE TABLE IF NOT EXISTS memories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                fact        TEXT    NOT NULL,
                source      TEXT    NOT NULL DEFAULT 'explicit',
                context     TEXT    DEFAULT '',
                confidence  REAL   DEFAULT 1.0,
                active      INTEGER DEFAULT 1,
                created_at  REAL   NOT NULL,
                updated_at  REAL   NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_user_active ON memories(user_id, active);
        """)

    # ── Migration v2: Add user_id to conversation history ────────────────

    @staticmethod
    def _migrate_v2(conn: sqlite3.Connection) -> None:
        """
        v2 — Create a conversations table in the unified DB.
        The legacy ConversationMemory in brain.py manages its own DB file;
        this mirrors the schema so new code can optionally use it.
        """
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    REFERENCES users(id) ON DELETE SET NULL,
                session     TEXT    NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                ts          REAL   NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conv_session_ts ON conversations(session, ts);
            CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
        """)

    # ── Helper: generate IDs ─────────────────────────────────────────────

    @staticmethod
    def new_id() -> str:
        """Generate a new UUID4 string."""
        return str(uuid.uuid4())
