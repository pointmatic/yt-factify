# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Shared LLM call helper with rate-limit-aware retry via gentlify."""

from __future__ import annotations

from typing import TYPE_CHECKING

import litellm
import structlog

from yt_factify.config import AppConfig

if TYPE_CHECKING:
    from gentlify import Throttle

logger = structlog.get_logger()


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Check whether an exception is a rate-limit error.

    Used as the ``retryable`` predicate for :class:`gentlify.RetryConfig`.
    """
    cls_name = type(exc).__name__
    if "RateLimit" in cls_name:
        return True
    # litellm wraps provider errors; check the string as fallback
    msg = str(exc).lower()
    return "rate_limit" in msg or "rate limit" in msg


async def llm_completion(
    *,
    messages: list[dict[str, str]],
    config: AppConfig,
    max_attempts: int = 2,
    context: str = "llm_call",
    throttle: Throttle | None = None,
) -> str:
    """Call litellm.acompletion with adaptive throttling and retry via gentlify.

    When a :class:`gentlify.Throttle` is provided, the call is wrapped
    with ``@throttle.wrap``.  Gentlify handles concurrency limiting,
    dispatch interval gating, stochastic jitter, retry with exponential
    backoff, and automatic success/failure recording.

    When *throttle* is ``None``, falls back to a plain
    ``litellm.acompletion()`` call with no retry or rate coordination
    (preserves backward compatibility for library users who don't need
    throttling).

    Args:
        messages: Chat messages for the LLM.
        config: Application configuration.
        max_attempts: Max attempts for non-rate-limit errors (unused when
            throttle is provided — gentlify's RetryConfig governs retries).
        context: Label for log messages (e.g. ``"extraction"``).
        throttle: Optional shared :class:`gentlify.Throttle` for adaptive
            rate coordination and retry.

    Returns:
        The text content of the first choice.

    Raises:
        The original exception if all retries are exhausted.
    """

    async def _call() -> str:
        response = await litellm.acompletion(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            api_base=config.api_base,
            api_key=config.api_key,
        )
        content: str = response.choices[0].message.content or ""
        return content

    if throttle is not None:
        wrapped = throttle.wrap(_call)
        result: str = await wrapped()
        return result

    # No throttle — plain call, no retry
    return await _call()
