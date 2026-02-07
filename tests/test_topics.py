# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for yt_factify.topics."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_factify.config import AppConfig
from yt_factify.models import (
    ExtractedItem,
    ItemType,
    TranscriptEvidence,
)
from yt_factify.topics import (
    TopicClusteringError,
    _derive_timeline,
    _parse_topic_threads,
    cluster_topic_threads,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm_responses"


def _make_config(**overrides: object) -> AppConfig:
    defaults: dict[str, object] = {
        "model": "gpt-4o-mini",
        "max_retries": 2,
    }
    defaults.update(overrides)
    return AppConfig(**defaults)  # type: ignore[arg-type]


def _make_item(
    item_id: str = "item_1",
    start_ms: int = 3000,
    end_ms: int = 6500,
    content: str = "Data classes were introduced in Python 3.7.",
) -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=ItemType.TRANSCRIPT_FACT,
        content=content,
        transcript_evidence=TranscriptEvidence(
            video_id="test_vid",
            start_ms=start_ms,
            end_ms=end_ms,
            text=content,
        ),
    )


def _mock_llm_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# _derive_timeline
# ---------------------------------------------------------------------------


class TestDeriveTimeline:
    def test_single_item(self) -> None:
        items = [_make_item("a", start_ms=1000, end_ms=5000)]
        items_by_id = {i.id: i for i in items}
        timeline = _derive_timeline(["a"], items_by_id)
        assert len(timeline) == 1
        assert timeline[0].start_ms == 1000
        assert timeline[0].end_ms == 5000

    def test_non_overlapping_spans(self) -> None:
        items = [
            _make_item("a", start_ms=1000, end_ms=3000),
            _make_item("b", start_ms=5000, end_ms=8000),
        ]
        items_by_id = {i.id: i for i in items}
        timeline = _derive_timeline(["a", "b"], items_by_id)
        assert len(timeline) == 2
        assert timeline[0].start_ms == 1000
        assert timeline[1].start_ms == 5000

    def test_overlapping_spans_merged(self) -> None:
        items = [
            _make_item("a", start_ms=1000, end_ms=5000),
            _make_item("b", start_ms=3000, end_ms=8000),
        ]
        items_by_id = {i.id: i for i in items}
        timeline = _derive_timeline(["a", "b"], items_by_id)
        assert len(timeline) == 1
        assert timeline[0].start_ms == 1000
        assert timeline[0].end_ms == 8000

    def test_adjacent_spans_merged(self) -> None:
        items = [
            _make_item("a", start_ms=1000, end_ms=3000),
            _make_item("b", start_ms=3000, end_ms=5000),
        ]
        items_by_id = {i.id: i for i in items}
        timeline = _derive_timeline(["a", "b"], items_by_id)
        assert len(timeline) == 1
        assert timeline[0].start_ms == 1000
        assert timeline[0].end_ms == 5000

    def test_unknown_ids_ignored(self) -> None:
        items = [_make_item("a", start_ms=1000, end_ms=5000)]
        items_by_id = {i.id: i for i in items}
        timeline = _derive_timeline(["a", "nonexistent"], items_by_id)
        assert len(timeline) == 1

    def test_empty_ids(self) -> None:
        timeline = _derive_timeline([], {})
        assert timeline == []

    def test_sorted_output(self) -> None:
        items = [
            _make_item("b", start_ms=5000, end_ms=8000),
            _make_item("a", start_ms=1000, end_ms=3000),
        ]
        items_by_id = {i.id: i for i in items}
        # Pass in reverse order
        timeline = _derive_timeline(["b", "a"], items_by_id)
        assert timeline[0].start_ms == 1000
        assert timeline[1].start_ms == 5000


# ---------------------------------------------------------------------------
# _parse_topic_threads
# ---------------------------------------------------------------------------


class TestParseTopicThreads:
    def test_valid_response(self) -> None:
        raw = (FIXTURES_DIR / "topics_valid.json").read_text()
        items = [
            _make_item("item_1", start_ms=3000, end_ms=6500),
            _make_item("item_2", start_ms=6500, end_ms=10000),
            _make_item("item_3", start_ms=10000, end_ms=14000),
        ]
        threads = _parse_topic_threads(raw, items)
        assert len(threads) == 2
        assert threads[0].label == "python_data_classes"
        assert threads[0].item_ids == ["item_1", "item_2"]
        assert len(threads[0].timeline) >= 1

    def test_unknown_item_ids_filtered(self) -> None:
        raw = json.dumps([{
            "label": "test",
            "display_name": "Test",
            "summary": "A test thread.",
            "item_ids": ["item_1", "nonexistent"],
        }])
        items = [_make_item("item_1")]
        threads = _parse_topic_threads(raw, items)
        assert len(threads) == 1
        assert threads[0].item_ids == ["item_1"]

    def test_all_ids_unknown_thread_skipped(self) -> None:
        raw = json.dumps([{
            "label": "ghost",
            "display_name": "Ghost",
            "summary": "No valid items.",
            "item_ids": ["nonexistent_1", "nonexistent_2"],
        }])
        items = [_make_item("item_1")]
        threads = _parse_topic_threads(raw, items)
        assert len(threads) == 0

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_topic_threads("not json", [])

    def test_non_array_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected JSON array"):
            _parse_topic_threads("{}", [])

    def test_invalid_thread_skipped(self) -> None:
        raw = json.dumps([
            {
                "label": "good",
                "display_name": "Good",
                "summary": "Valid.",
                "item_ids": ["item_1"],
            },
            {"missing": "fields"},
        ])
        items = [_make_item("item_1")]
        threads = _parse_topic_threads(raw, items)
        assert len(threads) == 1
        assert threads[0].label == "good"

    def test_markdown_fences_stripped(self) -> None:
        raw = (FIXTURES_DIR / "topics_valid.json").read_text()
        fenced = f"```json\n{raw}\n```"
        items = [
            _make_item("item_1", start_ms=3000, end_ms=6500),
            _make_item("item_2", start_ms=6500, end_ms=10000),
            _make_item("item_3", start_ms=10000, end_ms=14000),
        ]
        threads = _parse_topic_threads(fenced, items)
        assert len(threads) == 2

    def test_timeline_derived_from_items(self) -> None:
        raw = json.dumps([{
            "label": "test",
            "display_name": "Test",
            "summary": "Test.",
            "item_ids": ["a", "b"],
        }])
        items = [
            _make_item("a", start_ms=1000, end_ms=3000),
            _make_item("b", start_ms=5000, end_ms=8000),
        ]
        threads = _parse_topic_threads(raw, items)
        assert len(threads) == 1
        assert len(threads[0].timeline) == 2
        assert threads[0].timeline[0].start_ms == 1000
        assert threads[0].timeline[1].start_ms == 5000


# ---------------------------------------------------------------------------
# cluster_topic_threads (mocked LLM)
# ---------------------------------------------------------------------------


class TestClusterTopicThreads:
    def test_successful_clustering(self) -> None:
        fixture = (FIXTURES_DIR / "topics_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        with patch("yt_factify.topics.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            items = [
                _make_item("item_1", start_ms=3000, end_ms=6500),
                _make_item("item_2", start_ms=6500, end_ms=10000),
                _make_item("item_3", start_ms=10000, end_ms=14000),
            ]
            result = asyncio.run(cluster_topic_threads(items, config))

            assert len(result) == 2
            assert result[0].label == "python_data_classes"
            mock_litellm.acompletion.assert_called_once()

    def test_few_items_returns_empty(self) -> None:
        config = _make_config()
        items = [_make_item("item_1"), _make_item("item_2")]
        result = asyncio.run(cluster_topic_threads(items, config))
        assert result == []

    def test_zero_items_returns_empty(self) -> None:
        config = _make_config()
        result = asyncio.run(cluster_topic_threads([], config))
        assert result == []

    def test_retry_on_malformed_json(self) -> None:
        bad_response = _mock_llm_response("not json")
        fixture = (FIXTURES_DIR / "topics_valid.json").read_text()
        good_response = _mock_llm_response(fixture)

        with patch("yt_factify.topics.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[bad_response, good_response]
            )

            config = _make_config()
            items = [
                _make_item("item_1", start_ms=3000, end_ms=6500),
                _make_item("item_2", start_ms=6500, end_ms=10000),
                _make_item("item_3", start_ms=10000, end_ms=14000),
            ]
            result = asyncio.run(cluster_topic_threads(items, config))
            assert len(result) == 2
            assert mock_litellm.acompletion.call_count == 2

    def test_persistent_failure_raises(self) -> None:
        bad_response = _mock_llm_response("not json")

        with patch("yt_factify.topics.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=bad_response)

            config = _make_config()
            items = [
                _make_item("item_1"),
                _make_item("item_2"),
                _make_item("item_3"),
            ]
            with pytest.raises(
                TopicClusteringError, match="Failed to cluster"
            ):
                asyncio.run(cluster_topic_threads(items, config))

    def test_prompt_contains_item_info(self) -> None:
        fixture = (FIXTURES_DIR / "topics_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        with patch("yt_factify.topics.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            items = [
                _make_item("item_1", start_ms=3000, end_ms=6500),
                _make_item("item_2", start_ms=6500, end_ms=10000),
                _make_item("item_3", start_ms=10000, end_ms=14000),
            ]
            asyncio.run(cluster_topic_threads(items, config))

            call_args = mock_litellm.acompletion.call_args
            messages = call_args.kwargs["messages"]
            user_content = messages[1]["content"]
            assert "item_1" in user_content
            assert "item_2" in user_content
            assert "item_3" in user_content
