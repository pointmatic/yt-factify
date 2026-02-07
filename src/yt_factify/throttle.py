# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Adaptive rate throttle for LLM API calls.

Coordinates all concurrent requests through a shared throttle that
decelerates on high failure rates and reaccelerates after a cooling
period with sustained success.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Minimum interval between dispatches (seconds).
_DEFAULT_MIN_DISPATCH_INTERVAL = 0.2

# Failure threshold: number of failures in the sliding window to trigger deceleration.
_DEFAULT_FAILURE_THRESHOLD = 3

# Sliding window size for failure tracking (seconds).
_DEFAULT_FAILURE_WINDOW = 60.0

# Cooling period: seconds of zero failures before reacceleration (seconds).
_DEFAULT_COOLING_PERIOD = 60.0

# Minimum concurrency (never go below 1).
_MIN_CONCURRENCY = 1

# Maximum dispatch interval cap (seconds).
_MAX_DISPATCH_INTERVAL = 30.0


@dataclass
class ThrottleSnapshot:
    """Point-in-time snapshot of throttle state for progress reporting."""

    completed: int
    total: int
    concurrency: int
    dispatch_interval: float
    eta_seconds: float | None


class AdaptiveThrottle:
    """Global adaptive throttle for coordinating LLM API request rates.

    Controls concurrency and dispatch interval. Decelerates when failures
    accumulate, reaccelerates after a cooling period with no failures.

    Usage::

        throttle = AdaptiveThrottle(max_concurrency=3, total_tasks=40)

        async with throttle.acquire():
            result = await make_api_call()

        throttle.record_success()
        # or
        throttle.record_failure()

    Args:
        max_concurrency: Initial (and maximum) number of concurrent requests.
        total_tasks: Total number of tasks for progress tracking.
        min_dispatch_interval: Minimum seconds between consecutive dispatches.
        failure_threshold: Number of failures in the window to trigger deceleration.
        failure_window: Sliding window size in seconds for failure counting.
        cooling_period: Seconds of zero failures before reacceleration.
    """

    def __init__(
        self,
        max_concurrency: int = 3,
        total_tasks: int = 0,
        min_dispatch_interval: float = _DEFAULT_MIN_DISPATCH_INTERVAL,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        failure_window: float = _DEFAULT_FAILURE_WINDOW,
        cooling_period: float = _DEFAULT_COOLING_PERIOD,
    ) -> None:
        # Concurrency control
        self._max_concurrency = max(max_concurrency, _MIN_CONCURRENCY)
        self._current_concurrency = self._max_concurrency
        self._semaphore = asyncio.Semaphore(self._current_concurrency)

        # Dispatch interval control
        self._min_dispatch_interval = min_dispatch_interval
        self._current_dispatch_interval = min_dispatch_interval
        self._last_dispatch_time: float = 0.0
        self._dispatch_lock = asyncio.Lock()

        # Failure tracking (sliding window)
        self._failure_threshold = failure_threshold
        self._failure_window = failure_window
        self._failure_timestamps: list[float] = []

        # Cooling / reacceleration
        self._cooling_period = cooling_period
        self._last_failure_time: float = 0.0
        self._cooling_start: float | None = None
        self._safe_ceiling = self._max_concurrency

        # Progress tracking
        self._total_tasks = total_tasks
        self._completed_tasks = 0
        self._start_time = time.monotonic()

        # Track average task duration for ETA
        self._task_durations: list[float] = []

        logger.info(
            "throttle_initialized",
            max_concurrency=self._max_concurrency,
            dispatch_interval=self._current_dispatch_interval,
            total_tasks=total_tasks,
        )

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        """Acquire a slot from the throttle.

        Waits for both a concurrency slot and the dispatch interval
        before yielding. Use as an async context manager.
        """
        await self._semaphore.acquire()
        try:
            # Enforce minimum dispatch interval
            async with self._dispatch_lock:
                now = time.monotonic()
                elapsed = now - self._last_dispatch_time
                if elapsed < self._current_dispatch_interval:
                    await asyncio.sleep(self._current_dispatch_interval - elapsed)
                self._last_dispatch_time = time.monotonic()

            yield
        finally:
            self._semaphore.release()

    def record_success(self, duration: float = 0.0) -> None:
        """Record a successful API call.

        Increments completed count, tracks duration for ETA, and
        checks whether cooling period has elapsed for reacceleration.

        Args:
            duration: How long the call took in seconds (for ETA estimation).
        """
        self._completed_tasks += 1
        if duration > 0:
            self._task_durations.append(duration)

        # Check for reacceleration
        self._maybe_reaccelerate()

        self._log_progress()

    def record_failure(self) -> None:
        """Record a rate-limit failure.

        Adds to the sliding window. If the threshold is breached,
        triggers deceleration. Resets the cooling timer.
        """
        now = time.monotonic()
        self._failure_timestamps.append(now)
        self._last_failure_time = now
        self._cooling_start = None  # reset cooling

        # Prune old failures outside the window
        cutoff = now - self._failure_window
        self._failure_timestamps = [t for t in self._failure_timestamps if t > cutoff]

        if len(self._failure_timestamps) >= self._failure_threshold:
            self._decelerate()

    def progress(self) -> ThrottleSnapshot:
        """Return a snapshot of current throttle state and progress."""
        eta = self._estimate_eta()
        return ThrottleSnapshot(
            completed=self._completed_tasks,
            total=self._total_tasks,
            concurrency=self._current_concurrency,
            dispatch_interval=self._current_dispatch_interval,
            eta_seconds=eta,
        )

    @property
    def completed(self) -> int:
        """Number of completed tasks."""
        return self._completed_tasks

    @property
    def total(self) -> int:
        """Total number of tasks."""
        return self._total_tasks

    @total.setter
    def total(self, value: int) -> None:
        """Update total task count (useful when total isn't known at init)."""
        self._total_tasks = value

    def _decelerate(self) -> None:
        """Halve concurrency and double dispatch interval."""
        old_concurrency = self._current_concurrency
        old_interval = self._current_dispatch_interval

        # Halve concurrency (min 1)
        new_concurrency = max(self._current_concurrency // 2, _MIN_CONCURRENCY)

        # Double dispatch interval (capped)
        new_interval = min(self._current_dispatch_interval * 2, _MAX_DISPATCH_INTERVAL)

        # Record the safe ceiling: don't reaccelerate past where we failed
        self._safe_ceiling = min(self._safe_ceiling, old_concurrency)

        # Rebuild semaphore with new concurrency
        if new_concurrency != old_concurrency:
            self._current_concurrency = new_concurrency
            self._semaphore = asyncio.Semaphore(new_concurrency)

        self._current_dispatch_interval = new_interval

        # Clear failure window after deceleration
        self._failure_timestamps.clear()

        # Start cooling timer
        self._cooling_start = time.monotonic()

        logger.warning(
            "throttle_decelerated",
            old_concurrency=old_concurrency,
            new_concurrency=new_concurrency,
            old_interval=old_interval,
            new_interval=new_interval,
            safe_ceiling=self._safe_ceiling,
        )

    def _maybe_reaccelerate(self) -> None:
        """Step concurrency back up if cooling period has elapsed with no failures."""
        if self._cooling_start is None:
            # Not in cooling mode — check if we should enter it
            # (only relevant if we've previously decelerated)
            if self._current_concurrency < self._safe_ceiling:
                self._cooling_start = time.monotonic()
            return

        elapsed = time.monotonic() - self._cooling_start
        if elapsed < self._cooling_period:
            return

        # Cooling period elapsed with no failures — step up
        old_concurrency = self._current_concurrency
        old_interval = self._current_dispatch_interval

        new_concurrency = min(self._current_concurrency + 1, self._safe_ceiling)
        new_interval = max(
            self._current_dispatch_interval / 2,
            self._min_dispatch_interval,
        )

        if new_concurrency != old_concurrency or new_interval != old_interval:
            self._current_concurrency = new_concurrency
            self._semaphore = asyncio.Semaphore(new_concurrency)
            self._current_dispatch_interval = new_interval

            # Reset cooling timer for next potential step
            self._cooling_start = time.monotonic()

            logger.info(
                "throttle_reaccelerated",
                old_concurrency=old_concurrency,
                new_concurrency=new_concurrency,
                old_interval=old_interval,
                new_interval=new_interval,
                safe_ceiling=self._safe_ceiling,
            )

    def _estimate_eta(self) -> float | None:
        """Estimate time remaining based on average task duration."""
        remaining = self._total_tasks - self._completed_tasks
        if remaining <= 0:
            return 0.0

        if not self._task_durations:
            # Fall back to elapsed time per completed task
            if self._completed_tasks == 0:
                return None
            elapsed = time.monotonic() - self._start_time
            avg = elapsed / self._completed_tasks
        else:
            # Use recent durations (last 10) for more responsive ETA
            recent = self._task_durations[-10:]
            avg = sum(recent) / len(recent)

        # Account for concurrency
        effective_rate = self._current_concurrency / max(avg, 0.01)
        return remaining / effective_rate

    def _log_progress(self) -> None:
        """Log progress at meaningful intervals."""
        if self._total_tasks == 0:
            return

        pct = (self._completed_tasks / self._total_tasks) * 100
        eta = self._estimate_eta()

        # Log every 10% or on completion
        should_log = (
            self._completed_tasks == self._total_tasks
            or self._completed_tasks == 1
            or (self._completed_tasks % max(self._total_tasks // 10, 1) == 0)
        )

        if should_log:
            logger.info(
                "throttle_progress",
                completed=self._completed_tasks,
                total=self._total_tasks,
                percent=round(pct, 1),
                concurrency=self._current_concurrency,
                dispatch_interval=round(self._current_dispatch_interval, 2),
                eta_seconds=round(eta, 1) if eta is not None else None,
            )
