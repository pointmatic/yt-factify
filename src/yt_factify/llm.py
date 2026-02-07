# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared LLM call helper with rate-limit-aware retry and backoff."""

from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING

import litellm
import structlog

from yt_factify.config import AppConfig

if TYPE_CHECKING:
    from yt_factify.throttle import AdaptiveThrottle

logger = structlog.get_logger()

# Base delay in seconds for exponential backoff on rate limits.
_RATE_LIMIT_BASE_DELAY = 5.0

# Maximum delay cap in seconds.
_RATE_LIMIT_MAX_DELAY = 120.0

# Maximum number of rate-limit retries (on top of normal retries).
_RATE_LIMIT_MAX_RETRIES = 6


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check whether an exception is a rate-limit error."""
    cls_name = type(exc).__name__
    if "RateLimit" in cls_name:
        return True
    # litellm wraps provider errors; check the string as fallback
    msg = str(exc).lower()
    return "rate_limit" in msg or "rate limit" in msg


def _parse_retry_after(exc: Exception) -> float | None:
    """Try to extract a retry-after hint (seconds) from the error message."""
    msg = str(exc)
    # Look for patterns like "try again in Xs" or "retry after X seconds"
    match = re.search(r"(?:try again in|retry.after)\s+(\d+(?:\.\d+)?)\s*s", msg, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


async def llm_completion(
    *,
    messages: list[dict[str, str]],
    config: AppConfig,
    max_attempts: int = 2,
    context: str = "llm_call",
    throttle: AdaptiveThrottle | None = None,
) -> str:
    """Call litellm.acompletion with rate-limit-aware retry.

    On rate-limit errors, backs off exponentially (5s, 10s, 20s, …)
    up to ``_RATE_LIMIT_MAX_RETRIES`` additional attempts.  On parse
    or other transient errors, retries up to *max_attempts* without
    extra delay.

    If an ``AdaptiveThrottle`` is provided, acquires a slot before
    dispatching and reports successes/failures to coordinate the
    global request rate.

    Args:
        messages: Chat messages for the LLM.
        config: Application configuration.
        max_attempts: Max attempts for non-rate-limit errors.
        context: Label for log messages (e.g. ``"extraction"``).
        throttle: Optional shared throttle for global rate coordination.

    Returns:
        The text content of the first choice.

    Raises:
        The original exception if all retries are exhausted.
    """
    attempt = 0
    rate_limit_retries = 0
    last_error: Exception | None = None

    while True:
        attempt += 1
        call_start = time.monotonic()
        try:
            if throttle is not None:
                async with throttle.acquire():
                    response = await litellm.acompletion(
                        model=config.model,
                        messages=messages,
                        temperature=config.temperature,
                        api_base=config.api_base,
                        api_key=config.api_key,
                    )
            else:
                response = await litellm.acompletion(
                    model=config.model,
                    messages=messages,
                    temperature=config.temperature,
                    api_base=config.api_base,
                    api_key=config.api_key,
                )

            duration = time.monotonic() - call_start
            if throttle is not None:
                throttle.record_success(duration=duration)

            return response.choices[0].message.content or ""

        except Exception as exc:
            last_error = exc

            if _is_rate_limit_error(exc):
                rate_limit_retries += 1

                if throttle is not None:
                    throttle.record_failure()

                if rate_limit_retries > _RATE_LIMIT_MAX_RETRIES:
                    logger.error(
                        f"{context}_rate_limit_exhausted",
                        attempt=attempt,
                        rate_limit_retries=rate_limit_retries,
                        error=str(exc),
                    )
                    raise

                # Use retry-after hint if available, else exponential backoff
                hint = _parse_retry_after(exc)
                delay = (
                    hint
                    if hint
                    else min(
                        _RATE_LIMIT_BASE_DELAY * (2 ** (rate_limit_retries - 1)),
                        _RATE_LIMIT_MAX_DELAY,
                    )
                )
                logger.warning(
                    f"{context}_rate_limited",
                    attempt=attempt,
                    retry_in_seconds=delay,
                    rate_limit_retry=rate_limit_retries,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
                continue  # don't count against max_attempts

            # Non-rate-limit error
            if attempt >= max_attempts:
                raise

            logger.warning(
                f"{context}_error",
                attempt=attempt,
                error=str(exc),
            )

    # Unreachable, but satisfies type checkers
    assert last_error is not None  # noqa: S101
    raise last_error
