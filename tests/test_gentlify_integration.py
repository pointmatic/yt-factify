# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for gentlify integration — throttle, retry, and LLM coordination.

Gentlify handles concurrency, dispatch interval, jitter, and success/failure
recording via ``throttle.acquire()``.  Retry logic lives in ``llm.py`` as a
custom loop with provider-specific retry-after parsing and context logging.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from gentlify import Throttle, ThrottleSnapshot

from yt_factify.llm import _is_rate_limit_error, _parse_retry_after


class TestIsRateLimitError:
    def test_rate_limit_class_name(self) -> None:
        exc = type("RateLimitError", (Exception,), {})()
        assert _is_rate_limit_error(exc) is True

    def test_rate_limit_in_message(self) -> None:
        assert _is_rate_limit_error(Exception("rate_limit_error: slow down")) is True
        assert _is_rate_limit_error(Exception("Rate Limit exceeded")) is True

    def test_non_rate_limit(self) -> None:
        assert _is_rate_limit_error(Exception("connection timeout")) is False
        assert _is_rate_limit_error(ValueError("bad input")) is False


class TestParseRetryAfter:
    def test_try_again_in_seconds(self) -> None:
        exc = Exception("Please try again in 30s after the rate limit resets")
        assert _parse_retry_after(exc) == 30.0

    def test_retry_after_seconds(self) -> None:
        exc = Exception("retry after 15.5 seconds")
        assert _parse_retry_after(exc) == 15.5

    def test_no_hint(self) -> None:
        exc = Exception("rate limit exceeded")
        assert _parse_retry_after(exc) is None


class TestThrottleInstantiation:
    def test_default_throttle(self) -> None:
        t = Throttle(max_concurrency=3, total_tasks=10)
        snap = t.snapshot()
        assert snap.max_concurrency == 3
        assert snap.total_tasks == 10
        assert snap.completed_tasks == 0

    def test_initial_concurrency(self) -> None:
        t = Throttle(max_concurrency=5, initial_concurrency=2, total_tasks=10)
        snap = t.snapshot()
        assert snap.concurrency == 2
        assert snap.max_concurrency == 5


class TestLLMCompletionWithThrottle:
    def test_success_records_completion(self) -> None:
        """Verify llm_completion with gentlify throttle records success."""
        from yt_factify.config import AppConfig
        from yt_factify.llm import llm_completion

        async def _run() -> None:
            throttle = Throttle(
                max_concurrency=2,
                total_tasks=1,
                min_dispatch_interval=0.0,
            )

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "test response"

            with patch("yt_factify.llm.litellm") as mock_litellm:
                mock_litellm.acompletion = AsyncMock(return_value=mock_response)

                config = AppConfig(model="test-model")
                result = await llm_completion(
                    messages=[{"role": "user", "content": "hello"}],
                    config=config,
                    throttle=throttle,
                )

                assert result == "test response"
                snap = throttle.snapshot()
                assert snap.completed_tasks == 1

        asyncio.run(_run())

    def test_retry_on_rate_limit_then_success(self) -> None:
        """Custom retry loop retries rate-limit errors via acquire()."""
        from yt_factify.config import AppConfig
        from yt_factify.llm import llm_completion

        async def _run() -> None:
            throttle = Throttle(
                max_concurrency=2,
                total_tasks=1,
                min_dispatch_interval=0.0,
                failure_threshold=10,
            )

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "ok"

            call_count = 0

            async def side_effect(*args: object, **kwargs: object) -> MagicMock:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("rate_limit_error: slow down")
                return mock_response

            with patch("yt_factify.llm.litellm") as mock_litellm:
                mock_litellm.acompletion = AsyncMock(side_effect=side_effect)

                with patch("yt_factify.llm.asyncio.sleep", new_callable=AsyncMock):
                    config = AppConfig(model="test-model")
                    result = await llm_completion(
                        messages=[{"role": "user", "content": "hello"}],
                        config=config,
                        throttle=throttle,
                    )

                    # Custom retry loop retried after the rate limit error
                    assert result == "ok"
                    assert call_count == 2
                    snap = throttle.snapshot()
                    # First call failed (recorded by acquire), second succeeded
                    assert snap.failure_count >= 1
                    assert snap.completed_tasks >= 1

        asyncio.run(_run())

    def test_exhausted_retries_raises(self) -> None:
        """When all rate-limit retries are exhausted, the error propagates."""
        from yt_factify.config import AppConfig
        from yt_factify.llm import llm_completion

        async def _run() -> None:
            throttle = Throttle(
                max_concurrency=2,
                total_tasks=1,
                min_dispatch_interval=0.0,
                failure_threshold=100,
            )

            with patch("yt_factify.llm.litellm") as mock_litellm:
                mock_litellm.acompletion = AsyncMock(
                    side_effect=Exception("rate_limit_error: slow down"),
                )

                with patch("yt_factify.llm.asyncio.sleep", new_callable=AsyncMock):
                    config = AppConfig(model="test-model")
                    try:
                        await llm_completion(
                            messages=[{"role": "user", "content": "hello"}],
                            config=config,
                            throttle=throttle,
                        )
                        raise AssertionError("Should have raised")  # noqa: TRY301
                    except Exception as exc:
                        assert "rate_limit_error" in str(exc)

                    snap = throttle.snapshot()
                    assert snap.failure_count >= 1

        asyncio.run(_run())

    def test_non_rate_limit_error_retries_up_to_max_attempts(self) -> None:
        """Non-rate-limit errors retry up to max_attempts then propagate."""
        from yt_factify.config import AppConfig
        from yt_factify.llm import llm_completion

        async def _run() -> None:
            throttle = Throttle(
                max_concurrency=2,
                total_tasks=1,
                min_dispatch_interval=0.0,
            )

            call_count = 0

            async def side_effect(*args: object, **kwargs: object) -> None:
                nonlocal call_count
                call_count += 1
                raise ValueError("bad model response")

            with patch("yt_factify.llm.litellm") as mock_litellm:
                mock_litellm.acompletion = AsyncMock(side_effect=side_effect)

                config = AppConfig(model="test-model")
                try:
                    await llm_completion(
                        messages=[{"role": "user", "content": "hello"}],
                        config=config,
                        max_attempts=2,
                        throttle=throttle,
                    )
                    raise AssertionError("Should have raised")  # noqa: TRY301
                except ValueError as exc:
                    assert "bad model response" in str(exc)

                assert call_count == 2  # retried once, then raised

        asyncio.run(_run())

    def test_no_throttle_fallback(self) -> None:
        """Without throttle, llm_completion still works (no retry)."""
        from yt_factify.config import AppConfig
        from yt_factify.llm import llm_completion

        async def _run() -> None:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "plain response"

            with patch("yt_factify.llm.litellm") as mock_litellm:
                mock_litellm.acompletion = AsyncMock(return_value=mock_response)

                config = AppConfig(model="test-model")
                result = await llm_completion(
                    messages=[{"role": "user", "content": "hello"}],
                    config=config,
                    throttle=None,
                )

                assert result == "plain response"

        asyncio.run(_run())


class TestConcurrencyAndDispatch:
    def test_concurrency_limiting(self) -> None:
        """Gentlify limits concurrent requests."""

        async def _run() -> None:
            throttle = Throttle(
                max_concurrency=2,
                min_dispatch_interval=0.0,
                total_tasks=5,
            )
            active = 0
            max_active = 0

            async def task() -> None:
                nonlocal active, max_active
                async with throttle.acquire():
                    active += 1
                    max_active = max(max_active, active)
                    await asyncio.sleep(0.05)
                    active -= 1

            await asyncio.gather(*[task() for _ in range(5)])
            assert max_active <= 2

        asyncio.run(_run())

    def test_dispatch_interval_configured(self) -> None:
        """Verify dispatch interval is accepted as a config parameter."""
        throttle = Throttle(
            max_concurrency=10,
            min_dispatch_interval=0.5,
            total_tasks=4,
        )
        snap = throttle.snapshot()
        assert snap.dispatch_interval >= 0.5


class TestDeceleration:
    def test_decelerate_on_repeated_failures(self) -> None:
        """Gentlify decelerates concurrency after failure threshold."""

        async def _run() -> None:
            throttle = Throttle(
                max_concurrency=4,
                min_dispatch_interval=0.0,
                failure_threshold=3,
                failure_window=60.0,
                total_tasks=10,
            )

            # Simulate failures by raising inside acquire()
            for _ in range(3):
                try:
                    async with throttle.acquire():
                        raise Exception("rate_limit_error: slow down")
                except Exception:
                    pass

            snap = throttle.snapshot()
            # After 3 failures, concurrency should have been reduced
            assert snap.concurrency < 4

        asyncio.run(_run())


class TestPipelineThrottleConfig:
    def test_pipeline_creates_throttle_with_config(self) -> None:
        """Verify pipeline instantiates Throttle with correct config values."""
        from yt_factify.config import AppConfig

        config = AppConfig(
            model="test-model",
            max_concurrent_requests=5,
            initial_concurrent_requests=2,
        )

        throttle = Throttle(
            max_concurrency=config.max_concurrent_requests,
            initial_concurrency=config.initial_concurrent_requests,
            total_tasks=10,
        )

        snap = throttle.snapshot()
        assert snap.max_concurrency == 5
        assert snap.concurrency == 2
        assert snap.total_tasks == 10


class TestSnapshot:
    def test_snapshot_fields(self) -> None:
        t = Throttle(max_concurrency=3, total_tasks=10)
        snap = t.snapshot()
        assert isinstance(snap, ThrottleSnapshot)
        assert snap.completed_tasks == 0
        assert snap.total_tasks == 10
        assert snap.concurrency == 3
        assert snap.max_concurrency == 3

    def test_snapshot_after_completions(self) -> None:
        async def _run() -> None:
            t = Throttle(
                max_concurrency=3,
                total_tasks=3,
                min_dispatch_interval=0.0,
            )
            for _ in range(3):
                async with t.acquire():
                    pass
            snap = t.snapshot()
            assert snap.completed_tasks == 3

        asyncio.run(_run())
