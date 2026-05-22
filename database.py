"""
database.py — Async SQLite database layer for ML AutoSubmit.

Manages two tables:
  • submissions – tracks every URL submitted to MonsterLab
  • queue       – holds URLs waiting to be processed

Uses aiosqlite for non-blocking I/O and exposes a clean async API
consumed by the Telegram bot handlers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_SUBMISSIONS = """
CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    platform        TEXT,
    campaign_id     TEXT,
    submission_id   TEXT,
    status          TEXT    DEFAULT 'pending',
    handle          TEXT,
    label           TEXT,
    notes           TEXT,
    error_message   TEXT,
    response_data   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at    TIMESTAMP,
    UNIQUE(url)
);
"""

_CREATE_QUEUE = """
CREATE TABLE IF NOT EXISTS queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    campaign_id     TEXT,
    label           TEXT,
    notes           TEXT,
    priority        INTEGER DEFAULT 0,
    status          TEXT    DEFAULT 'pending',
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at    TIMESTAMP
);
"""


class Database:
    """Async SQLite wrapper for the submissions / queue workflow.

    Usage::

        db = Database("bot.db")
        await db.init()
        # … use db methods …
        await db.close()

    Or as an async context manager::

        async with Database("bot.db") as db:
            await db.add_to_queue("https://example.com")
    """

    def __init__(self, db_path: str = "bot.db") -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Context-manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "Database":
        await self.init()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Open the database connection and create tables if they don't exist."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute(_CREATE_SUBMISSIONS)
        await self._db.execute(_CREATE_QUEUE)
        await self._db.commit()
        logger.info("Database initialised (%s)", self.db_path)

    async def close(self) -> None:
        """Close the database connection gracefully."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.info("Database connection closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _conn(self) -> aiosqlite.Connection:
        """Return the active connection or raise if not initialised."""
        if self._db is None:
            raise RuntimeError("Database not initialised — call init() first")
        return self._db

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
        """Convert an aiosqlite.Row to a plain dict (or *None*)."""
        if row is None:
            return None
        return dict(row)

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    async def add_to_queue(
        self,
        url: str,
        campaign_id: str | None = None,
        label: str | None = None,
        notes: str | None = None,
        priority: int = 0,
    ) -> int:
        """Add a single URL to the processing queue.

        Returns:
            The new queue-row ID.

        Raises:
            ValueError: If the URL has already been submitted (exists in
                        the *submissions* table with a non-failed status).
        """
        if await self.is_duplicate(url):
            raise ValueError(f"URL already submitted: {url}")

        db = self._conn()
        cursor = await db.execute(
            """
            INSERT INTO queue (url, campaign_id, label, notes, priority)
            VALUES (?, ?, ?, ?, ?)
            """,
            (url, campaign_id, label, notes, priority),
        )
        await db.commit()
        queue_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.info("Queued URL (id=%d): %s", queue_id, url)
        return queue_id

    async def add_bulk_to_queue(
        self,
        urls: list[str],
        campaign_id: str | None = None,
    ) -> tuple[int, int]:
        """Add multiple URLs to the queue, silently skipping duplicates.

        Returns:
            A tuple of ``(added_count, duplicate_count)``.
        """
        added = 0
        duplicated = 0
        for url in urls:
            try:
                await self.add_to_queue(url, campaign_id=campaign_id)
                added += 1
            except ValueError:
                duplicated += 1
                logger.debug("Skipped duplicate URL: %s", url)
        logger.info(
            "Bulk queue: %d added, %d duplicates skipped", added, duplicated
        )
        return added, duplicated

    async def get_next_in_queue(self) -> dict[str, Any] | None:
        """Return the highest-priority pending queue item, or *None*.

        Items are ordered by ``priority DESC, created_at ASC`` so that
        higher-priority items come first and ties are broken by age.
        """
        db = self._conn()
        cursor = await db.execute(
            """
            SELECT * FROM queue
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
            """
        )
        row = await cursor.fetchone()
        return self._row_to_dict(row)

    async def mark_queue_item(
        self,
        queue_id: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Update a queue item's status and (optionally) its error message.

        ``processed_at`` is set automatically when the status is no longer
        ``'pending'``.
        """
        db = self._conn()
        processed_at = (
            datetime.now(timezone.utc).isoformat()
            if status != "pending"
            else None
        )
        await db.execute(
            """
            UPDATE queue
            SET status = ?, error_message = ?, processed_at = ?
            WHERE id = ?
            """,
            (status, error_message, processed_at, queue_id),
        )
        await db.commit()
        logger.debug("Queue item %d → %s", queue_id, status)

    async def get_queue_count(self) -> int:
        """Return the number of pending items in the queue."""
        db = self._conn()
        cursor = await db.execute(
            "SELECT COUNT(*) FROM queue WHERE status = 'pending'"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def cancel_all_pending(self) -> int:
        """Cancel every pending queue item and return the count affected."""
        db = self._conn()
        cursor = await db.execute(
            """
            UPDATE queue
            SET status = 'cancelled',
                processed_at = ?
            WHERE status = 'pending'
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        await db.commit()
        count: int = cursor.rowcount  # type: ignore[assignment]
        logger.info("Cancelled %d pending queue items", count)
        return count

    # ------------------------------------------------------------------
    # Submission operations
    # ------------------------------------------------------------------

    async def record_submission(
        self,
        url: str,
        platform: str | None,
        campaign_id: str | None,
        submission_id: str | None,
        status: str,
        handle: str | None,
        response_data: dict[str, Any] | str | None = None,
    ) -> None:
        """Insert (or update on conflict) a row in the submissions table.

        ``response_data`` can be a dict (auto-serialised to JSON) or a
        pre-serialised JSON string.
        """
        if isinstance(response_data, dict):
            response_data = json.dumps(response_data)

        submitted_at = datetime.now(timezone.utc).isoformat()
        db = self._conn()
        await db.execute(
            """
            INSERT INTO submissions
                (url, platform, campaign_id, submission_id,
                 status, handle, response_data, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                platform      = excluded.platform,
                campaign_id   = excluded.campaign_id,
                submission_id = excluded.submission_id,
                status        = excluded.status,
                handle        = excluded.handle,
                response_data = excluded.response_data,
                submitted_at  = excluded.submitted_at
            """,
            (
                url,
                platform,
                campaign_id,
                submission_id,
                status,
                handle,
                response_data,
                submitted_at,
            ),
        )
        await db.commit()
        logger.info("Recorded submission for %s → %s", url, status)

    async def is_duplicate(self, url: str) -> bool:
        """Return *True* if the URL already exists in **submissions**
        with a status that is not ``'failed'``."""
        db = self._conn()
        cursor = await db.execute(
            """
            SELECT 1 FROM submissions
            WHERE url = ? AND status != 'failed'
            LIMIT 1
            """,
            (url,),
        )
        return (await cursor.fetchone()) is not None

    async def get_submission_by_url(self, url: str) -> dict[str, Any] | None:
        """Look up a single submission by its URL."""
        db = self._conn()
        cursor = await db.execute(
            "SELECT * FROM submissions WHERE url = ?", (url,)
        )
        row = await cursor.fetchone()
        return self._row_to_dict(row)

    async def get_recent_submissions(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return the *limit* most-recent submissions (newest first)."""
        db = self._conn()
        cursor = await db.execute(
            "SELECT * FROM submissions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_today_stats(self) -> dict[str, int]:
        """Aggregate today's submission statistics.

        Returns a dict with keys ``submitted``, ``pending``, ``failed``,
        and ``total``.
        """
        db = self._conn()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN status IN ('submitted', 'success') THEN 1 ELSE 0 END), 0) AS submitted,
                COALESCE(SUM(CASE WHEN status = 'pending'                THEN 1 ELSE 0 END), 0) AS pending,
                COALESCE(SUM(CASE WHEN status = 'failed'                 THEN 1 ELSE 0 END), 0) AS failed,
                COUNT(*) AS total
            FROM submissions
            WHERE DATE(created_at) = ?
            """,
            (today,),
        )
        row = await cursor.fetchone()
        if row is None:
            return {"submitted": 0, "pending": 0, "failed": 0, "total": 0}
        return {
            "submitted": row["submitted"],
            "pending": row["pending"],
            "failed": row["failed"],
            "total": row["total"],
        }
