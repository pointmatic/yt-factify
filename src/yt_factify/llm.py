# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Shared LLM call helper with rate-limit-aware retry and gentlify throttling."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import litellm
import structlog

from yt_factify.config import AppConfig

if TYPE_CHECKING:
    from gentlify import Throttle

logger = structlog.get_logger()

# Base delay in seconds for exponential backoff on rate limits.
# Set to 15s because most provider limits are per-minute token budgets;
# a 5s retry just wastes an attempt before the window rolls over.
_RATE_LIMIT_BASE_DELAY = 15.0

# Maximum delay cap in seconds.
_RATE_LIMIT_MAX_DELAY = 120.0

# Maximum number of rate-limit retries (on top of normal retries).
_RATE_LIMIT_MAX_RETRIES = 6


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Check whether an exception is a rate-limit error."""
    cls_name = type(exc).__name__
    if "RateLimit" in cls_name:
        return True
    # litellm wraps provider errors; check the string as fallback
    msg = str(exc).lower()
    return "rate_limit" in msg or "rate limit" in msg


def _parse_retry_after(exc: BaseException) -> float | None:
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
    throttle: Throttle | None = None,
) -> str:
    """Call litellm.acompletion with rate-limit-aware retry.

    Uses :meth:`gentlify.Throttle.acquire` for concurrency limiting,
    dispatch interval gating, and stochastic jitter.  The retry loop
    is managed here (not by gentlify's ``RetryConfig``) so that we can:

    - Parse provider-specific ``retry-after`` hints.
    - Log context-specific messages per retry attempt.
    - Maintain separate counters for rate-limit retries vs.
      non-rate-limit retries.

    On rate-limit errors, backs off exponentially (15s, 30s, 60s, …)
    up to ``_RATE_LIMIT_MAX_RETRIES`` additional attempts.  On other
    transient errors, retries up to *max_attempts* without extra delay.

    When *throttle* is ``None``, falls back to a plain
    ``litellm.acompletion()`` call with no retry or rate coordination
    (preserves backward compatibility for library users who don't need
    throttling).

    Args:
        messages: Chat messages for the LLM.
        config: Application configuration.
        max_attempts: Max attempts for non-rate-limit errors.
        context: Label for log messages (e.g. ``"extraction"``).
        throttle: Optional shared :class:`gentlify.Throttle` for adaptive
            rate coordination.

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

            content: str = response.choices[0].message.content or ""
            return content

        except Exception as exc:
            last_error = exc

            if _is_rate_limit_error(exc):
                rate_limit_retries += 1

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
