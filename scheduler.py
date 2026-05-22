"""
Rate-limit-aware submission scheduler for MonsterLab ClipIt.

Manages a background queue that processes clip submissions
while respecting API rate limits (100/min, 6000/hr, 144000/day).
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Optional, Awaitable

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding window rate limiter tracking multiple time windows."""

    def __init__(self, per_minute: int = 80, per_hour: int = 5000, min_interval: float = 2.0):
        self.per_minute = per_minute
        self.per_hour = per_hour
        self.min_interval = min_interval  # seconds between requests

        # Timestamps of recent submissions
        self._timestamps: deque[float] = deque()
        self._last_submission: float = 0.0

    def _cleanup(self):
        """Remove timestamps older than 1 hour."""
        cutoff = time.time() - 3600
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    @property
    def minute_count(self) -> int:
        """Number of submissions in the last 60 seconds."""
        cutoff = time.time() - 60
        return sum(1 for t in self._timestamps if t >= cutoff)

    @property
    def hour_count(self) -> int:
        """Number of submissions in the last 3600 seconds."""
        self._cleanup()
        return len(self._timestamps)

    def can_submit(self) -> bool:
        """Check if a submission is allowed right now."""
        now = time.time()

        # Check minimum interval
        if now - self._last_submission < self.min_interval:
            return False

        # Check per-minute limit
        if self.minute_count >= self.per_minute:
            return False

        # Check per-hour limit
        if self.hour_count >= self.per_hour:
            return False

        return True

    def seconds_until_available(self) -> float:
        """Calculate seconds until next submission is allowed."""
        now = time.time()
        waits = []

        # Wait for minimum interval
        interval_wait = self.min_interval - (now - self._last_submission)
        if interval_wait > 0:
            waits.append(interval_wait)

        # Wait for per-minute window to free up
        if self.minute_count >= self.per_minute:
            cutoff = now - 60
            minute_timestamps = [t for t in self._timestamps if t >= cutoff]
            if minute_timestamps:
                # Wait until the oldest one in the minute window expires
                oldest_in_minute = min(minute_timestamps)
                waits.append(oldest_in_minute + 60 - now + 0.5)

        # Wait for per-hour window to free up
        if self.hour_count >= self.per_hour:
            if self._timestamps:
                oldest = self._timestamps[0]
                waits.append(oldest + 3600 - now + 0.5)

        return max(waits) if waits else 0.0

    def record_submission(self):
        """Record that a submission was made now."""
        now = time.time()
        self._timestamps.append(now)
        self._last_submission = now
        self._cleanup()

    def get_stats(self) -> dict:
        """Get current rate limit stats."""
        return {
            "minute_count": self.minute_count,
            "minute_limit": self.per_minute,
            "hour_count": self.hour_count,
            "hour_limit": self.per_hour,
            "seconds_until_available": round(self.seconds_until_available(), 1),
            "can_submit_now": self.can_submit(),
        }


# Type for the callback that gets called when a submission completes
SubmissionCallback = Callable[[int, str, bool, dict], Awaitable[None]]
# Args: (queue_id, url, success, result_data)


class SubmissionScheduler:
    """
    Background task that processes the submission queue,
    respecting rate limits and sending status updates.
    """

    def __init__(
        self,
        api_client,       # MonsterLabAPI instance
        database,         # Database instance
        rate_limiter: RateLimiter,
        on_submission: Optional[SubmissionCallback] = None,
    ):
        self.api = api_client
        self.db = database
        self.rate_limiter = rate_limiter
        self.on_submission = on_submission  # callback for Telegram notifications

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._event = asyncio.Event()  # signal when new items are added

    async def start(self):
        """Start the background processing loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Submission scheduler started")

    async def stop(self):
        """Stop the background processing loop."""
        self._running = False
        self._event.set()  # wake up the loop so it can exit
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Submission scheduler stopped")

    def notify_new_item(self):
        """Signal that a new item was added to the queue."""
        self._event.set()

    async def _process_loop(self):
        """Main processing loop — runs forever until stopped."""
        logger.info("Scheduler loop running...")

        while self._running:
            try:
                # Check if there are items in the queue
                item = await self.db.get_next_in_queue()

                if item is None:
                    # No items — wait for notification or timeout
                    self._event.clear()
                    try:
                        await asyncio.wait_for(self._event.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

                # We have an item — check rate limits
                if not self.rate_limiter.can_submit():
                    wait_time = self.rate_limiter.seconds_until_available()
                    logger.info(f"Rate limit active, waiting {wait_time:.1f}s")
                    await asyncio.sleep(min(wait_time, 30.0))
                    continue

                # Process the item
                queue_id = item["id"]
                url = item["url"]
                campaign_id = item.get("campaign_id")
                label = item.get("label")
                notes = item.get("notes")

                logger.info(f"Processing queue item #{queue_id}: {url}")

                # Mark as processing
                await self.db.mark_queue_item(queue_id, "processing")

                try:
                    # Submit to MonsterLab
                    result = await self.api.submit_clip(
                        url=url,
                        campaign_id=campaign_id,
                        label=label,
                        notes=notes,
                    )

                    # Record the submission
                    self.rate_limiter.record_submission()

                    if result.get("success"):
                        data = result.get("data", {})
                        await self.db.record_submission(
                            url=url,
                            platform=data.get("platform", "unknown"),
                            campaign_id=campaign_id,
                            submission_id=data.get("submissionId"),
                            status="success",
                            handle=data.get("handle"),
                            response_data=result,
                        )
                        await self.db.mark_queue_item(queue_id, "completed")
                        logger.info(f"✅ Submitted: {url} -> {data.get('submissionId')}")

                        # Notify via callback
                        if self.on_submission:
                            await self.on_submission(queue_id, url, True, result)
                    else:
                        error_msg = result.get("error", result.get("message", "Unknown error"))
                        await self.db.record_submission(
                            url=url,
                            platform=None,
                            campaign_id=campaign_id,
                            submission_id=None,
                            status="failed",
                            handle=None,
                            response_data=result,
                        )
                        await self.db.mark_queue_item(queue_id, "failed", error_message=str(error_msg))
                        logger.warning(f"❌ Failed: {url} -> {error_msg}")

                        if self.on_submission:
                            await self.on_submission(queue_id, url, False, result)

                except Exception as e:
                    error_str = str(e)
                    logger.error(f"❌ Error submitting {url}: {error_str}")
                    await self.db.mark_queue_item(queue_id, "failed", error_message=error_str)

                    if self.on_submission:
                        await self.on_submission(queue_id, url, False, {"error": error_str})

                # Small delay between submissions even if rate limiter allows
                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("Scheduler loop exited")

    async def get_queue_status(self) -> dict:
        """Get current queue and rate limit status."""
        pending = await self.db.get_queue_count()
        stats = self.rate_limiter.get_stats()

        # Estimate completion time
        if pending > 0 and stats["can_submit_now"]:
            eta_seconds = pending * self.rate_limiter.min_interval
        elif pending > 0:
            eta_seconds = stats["seconds_until_available"] + (pending * self.rate_limiter.min_interval)
        else:
            eta_seconds = 0

        return {
            "pending": pending,
            "rate_limit": stats,
            "eta_seconds": round(eta_seconds, 0),
            "is_running": self._running,
        }
