# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for yt_factify.extraction."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_factify.config import AppConfig
from yt_factify.extraction import (
    ExtractionError,
    _extract_segment,
    _parse_items_from_response,
    extract_items,
)
from yt_factify.models import (
    BeliefSystemModule,
    TranscriptSegment,
    VideoCategory,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm_responses"


def _make_config(**overrides: object) -> AppConfig:
    defaults: dict[str, object] = {
        "model": "gpt-4o-mini",
        "max_retries": 2,
        "max_concurrent_requests": 2,
    }
    defaults.update(overrides)
    return AppConfig(**defaults)  # type: ignore[arg-type]


def _make_segment(
    text: str = "Data classes were introduced in Python 3.7.",
    start_ms: int = 6500,
    end_ms: int = 10000,
) -> TranscriptSegment:
    return TranscriptSegment(
        text=text,
        start_ms=start_ms,
        end_ms=end_ms,
        hash="abc123",
        source_segment_indices=[0],
    )


def _mock_llm_response(content: str) -> MagicMock:
    """Create a mock litellm response with the given content."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# _parse_items_from_response
# ---------------------------------------------------------------------------


class TestParseItemsFromResponse:
    def test_valid_response(self) -> None:
        raw = (FIXTURES_DIR / "extraction_valid.json").read_text()
        seg = _make_segment()
        items = _parse_items_from_response(raw, "test_vid", seg)
        assert len(items) == 3
        assert items[0].type.value == "transcript_fact"
        assert items[1].type.value == "speaker_opinion"
        assert items[2].type.value == "direct_quote"

    def test_video_id_injected(self) -> None:
        raw = (FIXTURES_DIR / "extraction_valid.json").read_text()
        seg = _make_segment()
        items = _parse_items_from_response(raw, "my_video", seg)
        for item in items:
            assert item.transcript_evidence.video_id == "my_video"

    def test_markdown_fences_stripped(self) -> None:
        raw = (FIXTURES_DIR / "extraction_with_fences.json").read_text()
        seg = _make_segment(start_ms=41000, end_ms=45000)
        items = _parse_items_from_response(raw, "test_vid", seg)
        assert len(items) == 1
        assert items[0].content == "The scaling laws paper was a turning point."

    def test_partial_invalid_skips_bad_items(self) -> None:
        raw = (FIXTURES_DIR / "extraction_partial_invalid.json").read_text()
        seg = _make_segment(start_ms=65000, end_ms=69000)
        items = _parse_items_from_response(raw, "test_vid", seg)
        # Only the valid item should be returned
        assert len(items) == 1
        assert items[0].id == "good_item"

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_items_from_response("not json at all", "vid", _make_segment())

    def test_non_array_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected JSON array"):
            _parse_items_from_response('{"key": "value"}', "vid", _make_segment())

    def test_empty_array(self) -> None:
        items = _parse_items_from_response("[]", "vid", _make_segment())
        assert items == []

    def test_id_generated_when_missing(self) -> None:
        raw = json.dumps(
            [
                {
                    "type": "transcript_fact",
                    "content": "Test fact",
                    "transcript_evidence": {
                        "text": "Test fact",
                        "start_ms": 0,
                        "end_ms": 5000,
                    },
                }
            ]
        )
        seg = _make_segment(start_ms=0, end_ms=5000)
        items = _parse_items_from_response(raw, "vid123", seg)
        assert len(items) == 1
        assert items[0].id.startswith("vid123_seg0_")


# ---------------------------------------------------------------------------
# _extract_segment (mocked LLM)
# ---------------------------------------------------------------------------


class TestExtractSegment:
    def test_successful_extraction(self) -> None:
        fixture = (FIXTURES_DIR / "extraction_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            seg = _make_segment()
            items = asyncio.run(_extract_segment(seg, "vid1", [], [], config))
            assert len(items) == 3
            mock_litellm.acompletion.assert_called_once()

    def test_empty_segment_skipped(self) -> None:
        config = _make_config()
        seg = _make_segment(text="   ")
        items = asyncio.run(_extract_segment(seg, "vid1", [], [], config))
        assert items == []

    def test_retry_on_malformed_json(self) -> None:
        bad_response = _mock_llm_response("not json")
        good_fixture = (FIXTURES_DIR / "extraction_valid.json").read_text()
        good_response = _mock_llm_response(good_fixture)

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=[bad_response, good_response])

            config = _make_config()
            seg = _make_segment()
            items = asyncio.run(_extract_segment(seg, "vid1", [], [], config))
            assert len(items) == 3
            assert mock_litellm.acompletion.call_count == 2

    def test_persistent_failure_raises(self) -> None:
        bad_response = _mock_llm_response("not json")

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=bad_response)

            config = _make_config()
            seg = _make_segment()
            with pytest.raises(ExtractionError, match="Failed to extract"):
                asyncio.run(_extract_segment(seg, "vid1", [], [], config))

    def test_llm_api_error_retries(self) -> None:
        good_fixture = (FIXTURES_DIR / "extraction_valid.json").read_text()
        good_response = _mock_llm_response(good_fixture)

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[RuntimeError("API timeout"), good_response]
            )

            config = _make_config()
            seg = _make_segment()
            items = asyncio.run(_extract_segment(seg, "vid1", [], [], config))
            assert len(items) == 3

    def test_categories_and_modules_passed(self) -> None:
        fixture = (FIXTURES_DIR / "extraction_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        module = BeliefSystemModule(
            label="test_module",
            display_name="Test Module",
            description="A test module",
            core_assumptions=["Assumption 1"],
        )

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            seg = _make_segment()
            asyncio.run(
                _extract_segment(
                    seg,
                    "vid1",
                    [VideoCategory.TUTORIAL],
                    [module],
                    config,
                )
            )

            call_args = mock_litellm.acompletion.call_args
            messages = call_args.kwargs["messages"]
            system_content = messages[0]["content"]
            assert "tutorial" in system_content
            assert "Test Module" in system_content


# ---------------------------------------------------------------------------
# extract_items (concurrency)
# ---------------------------------------------------------------------------


class TestExtractItems:
    def test_multiple_segments(self) -> None:
        fixture = (FIXTURES_DIR / "extraction_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            segments = [
                _make_segment(start_ms=0, end_ms=5000),
                _make_segment(start_ms=5000, end_ms=10000),
            ]
            items = asyncio.run(extract_items(segments, "vid1", [], [], config))
            # 3 items per segment × 2 segments = 6
            assert len(items) == 6
            assert mock_litellm.acompletion.call_count == 2

    def test_unique_ids_enforced(self) -> None:
        fixture = (FIXTURES_DIR / "extraction_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            segments = [
                _make_segment(start_ms=0, end_ms=5000),
                _make_segment(start_ms=5000, end_ms=10000),
            ]
            items = asyncio.run(extract_items(segments, "vid1", [], [], config))
            ids = [item.id for item in items]
            assert len(ids) == len(set(ids))

    def test_partial_failure_continues(self) -> None:
        fixture = (FIXTURES_DIR / "extraction_valid.json").read_text()
        good_response = _mock_llm_response(fixture)
        bad_response = _mock_llm_response("not json")

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            # First segment always fails, second succeeds
            mock_litellm.acompletion = AsyncMock(
                side_effect=[
                    bad_response,
                    bad_response,  # seg 0: fail both retries
                    good_response,  # seg 1: succeed
                ]
            )

            config = _make_config()
            segments = [
                _make_segment(start_ms=0, end_ms=5000),
                _make_segment(start_ms=5000, end_ms=10000),
            ]
            items = asyncio.run(extract_items(segments, "vid1", [], [], config))
            # Only second segment's items should be returned
            assert len(items) == 3

    def test_empty_segments_list(self) -> None:
        config = _make_config()
        items = asyncio.run(extract_items([], "vid1", [], [], config))
        assert items == []

    def test_concurrency_limited(self) -> None:
        """Verify the semaphore limits concurrent requests."""
        fixture = (FIXTURES_DIR / "extraction_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)
        max_concurrent = 0
        current_concurrent = 0

        original_acompletion = AsyncMock(return_value=mock_response)

        async def tracked_acompletion(**kwargs: object) -> MagicMock:
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)  # Simulate latency
            result = await original_acompletion(**kwargs)
            current_concurrent -= 1
            return result

        with patch("yt_factify.extraction.litellm") as mock_litellm:
            mock_litellm.acompletion = tracked_acompletion

            config = _make_config(max_concurrent_requests=2)
            segments = [_make_segment(start_ms=i * 1000, end_ms=(i + 1) * 1000) for i in range(5)]
            asyncio.run(extract_items(segments, "vid1", [], [], config))
            assert max_concurrent <= 2
