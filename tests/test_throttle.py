# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for yt_factify.throttle."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from yt_factify.throttle import AdaptiveThrottle


class TestAdaptiveThrottleInit:
    def test_default_init(self) -> None:
        t = AdaptiveThrottle()
        assert t._max_concurrency == 3
        assert t._current_concurrency == 3
        assert t._total_tasks == 0
        assert t._completed_tasks == 0

    def test_custom_init(self) -> None:
        t = AdaptiveThrottle(max_concurrency=5, total_tasks=20)
        assert t._max_concurrency == 5
        assert t._current_concurrency == 5
        assert t._total_tasks == 20

    def test_min_concurrency_enforced(self) -> None:
        t = AdaptiveThrottle(max_concurrency=0)
        assert t._current_concurrency == 1


class TestDeceleration:
    def test_decelerate_on_threshold(self) -> None:
        t = AdaptiveThrottle(
            max_concurrency=4,
            failure_threshold=3,
            failure_window=60.0,
        )
        assert t._current_concurrency == 4

        # Record 3 failures to trigger deceleration
        t.record_failure()
        t.record_failure()
        assert t._current_concurrency == 4  # not yet

        t.record_failure()
        assert t._current_concurrency == 2  # halved
        assert t._current_dispatch_interval > 0.2  # doubled from default

    def test_decelerate_clears_failure_window(self) -> None:
        t = AdaptiveThrottle(
            max_concurrency=4,
            failure_threshold=2,
        )
        t.record_failure()
        t.record_failure()
        # After deceleration, failure window should be cleared
        assert len(t._failure_timestamps) == 0

    def test_decelerate_never_below_one(self) -> None:
        t = AdaptiveThrottle(
            max_concurrency=2,
            failure_threshold=2,
        )
        # First deceleration: 2 -> 1
        t.record_failure()
        t.record_failure()
        assert t._current_concurrency == 1

        # Second deceleration: stays at 1
        t.record_failure()
        t.record_failure()
        assert t._current_concurrency == 1

    def test_dispatch_interval_caps(self) -> None:
        t = AdaptiveThrottle(
            max_concurrency=8,
            failure_threshold=1,
            min_dispatch_interval=10.0,
        )
        # Trigger many decelerations
        for _ in range(10):
            t.record_failure()

        # Dispatch interval should be capped at 30s
        assert t._current_dispatch_interval <= 30.0

    def test_safe_ceiling_tracks_failure_level(self) -> None:
        t = AdaptiveThrottle(
            max_concurrency=8,
            failure_threshold=2,
        )
        # Decelerate from 8
        t.record_failure()
        t.record_failure()
        assert t._safe_ceiling <= 8


class TestReacceleration:
    def test_reaccelerate_after_cooling(self) -> None:
        async def _run() -> None:
            t = AdaptiveThrottle(
                max_concurrency=4,
                failure_threshold=2,
                cooling_period=0.1,  # very short for testing
            )
            # Decelerate: 4 -> 2
            t.record_failure()
            t.record_failure()
            assert t._current_concurrency == 2

            # Wait for cooling period
            await asyncio.sleep(0.15)

            # A success should trigger reacceleration
            t.record_success(duration=0.5)
            assert t._current_concurrency == 3  # stepped up by 1

        asyncio.run(_run())

    def test_failure_resets_cooling(self) -> None:
        async def _run() -> None:
            t = AdaptiveThrottle(
                max_concurrency=4,
                failure_threshold=2,
                cooling_period=0.1,
            )
            # Decelerate: 4 -> 2
            t.record_failure()
            t.record_failure()
            assert t._current_concurrency == 2

            # Wait partway through cooling
            await asyncio.sleep(0.05)

            # A failure resets cooling
            t.record_failure()
            assert t._cooling_start is None

            # Wait for what would have been the full cooling period
            await asyncio.sleep(0.12)

            # No reacceleration because cooling was reset
            # Record success — it should start a new cooling period, not reaccelerate
            t.record_success(duration=0.5)
            # Concurrency should still be at the decelerated level
            assert t._current_concurrency <= 2

        asyncio.run(_run())

    def test_never_exceed_safe_ceiling(self) -> None:
        async def _run() -> None:
            t = AdaptiveThrottle(
                max_concurrency=4,
                failure_threshold=2,
                cooling_period=0.05,
            )
            # Decelerate: 4 -> 2
            t.record_failure()
            t.record_failure()
            assert t._current_concurrency == 2
            assert t._safe_ceiling <= 4

            # Reaccelerate multiple times
            for _ in range(10):
                await asyncio.sleep(0.06)
                t.record_success(duration=0.1)

            # Should never exceed safe ceiling
            assert t._current_concurrency <= t._safe_ceiling

        asyncio.run(_run())


class TestAcquireRelease:
    def test_acquire_limits_concurrency(self) -> None:
        async def _run() -> None:
            t = AdaptiveThrottle(
                max_concurrency=2,
                min_dispatch_interval=0.0,
            )
            active = 0
            max_active = 0

            async def task() -> None:
                nonlocal active, max_active
                async with t.acquire():
                    active += 1
                    max_active = max(max_active, active)
                    await asyncio.sleep(0.05)
                    active -= 1

            await asyncio.gather(*[task() for _ in range(5)])
            assert max_active <= 2

        asyncio.run(_run())

    def test_dispatch_interval_enforced(self) -> None:
        async def _run() -> None:
            t = AdaptiveThrottle(
                max_concurrency=10,
                min_dispatch_interval=0.05,
            )
            timestamps: list[float] = []

            async def task() -> None:
                async with t.acquire():
                    timestamps.append(time.monotonic())

            await asyncio.gather(*[task() for _ in range(4)])

            # Check that consecutive dispatches are at least ~50ms apart
            for i in range(1, len(timestamps)):
                gap = timestamps[i] - timestamps[i - 1]
                assert gap >= 0.04  # allow small tolerance

        asyncio.run(_run())


class TestProgress:
    def test_progress_snapshot(self) -> None:
        t = AdaptiveThrottle(max_concurrency=3, total_tasks=10)
        snap = t.progress()
        assert snap.completed == 0
        assert snap.total == 10
        assert snap.concurrency == 3

    def test_progress_after_completions(self) -> None:
        t = AdaptiveThrottle(max_concurrency=3, total_tasks=10)
        t.record_success(duration=1.0)
        t.record_success(duration=1.0)
        snap = t.progress()
        assert snap.completed == 2
        assert snap.total == 10
        assert snap.eta_seconds is not None
        assert snap.eta_seconds > 0

    def test_progress_all_done(self) -> None:
        t = AdaptiveThrottle(max_concurrency=3, total_tasks=3)
        for _ in range(3):
            t.record_success(duration=0.5)
        snap = t.progress()
        assert snap.completed == 3
        assert snap.eta_seconds == 0.0

    def test_total_setter(self) -> None:
        t = AdaptiveThrottle(max_concurrency=3)
        assert t.total == 0
        t.total = 42
        assert t.total == 42

    def test_eta_none_when_no_completions(self) -> None:
        t = AdaptiveThrottle(max_concurrency=3, total_tasks=10)
        snap = t.progress()
        assert snap.eta_seconds is None


class TestIntegrationWithLLM:
    def test_llm_completion_with_throttle(self) -> None:
        """Verify llm_completion accepts and uses the throttle parameter."""
        from yt_factify.config import AppConfig
        from yt_factify.llm import llm_completion

        async def _run() -> None:
            throttle = AdaptiveThrottle(
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
                assert throttle.completed == 1

        asyncio.run(_run())

    def test_llm_completion_records_failure_on_rate_limit(self) -> None:
        """Verify throttle.record_failure() is called on rate limit errors."""
        from yt_factify.config import AppConfig
        from yt_factify.llm import llm_completion

        async def _run() -> None:
            throttle = AdaptiveThrottle(
                max_concurrency=2,
                total_tasks=1,
                min_dispatch_interval=0.0,
                failure_threshold=10,  # high so we don't decelerate during test
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

                assert result == "ok"
                assert len(throttle._failure_timestamps) >= 1

        asyncio.run(_run())
