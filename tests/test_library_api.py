# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for yt_factify public library API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from yt_factify import (
    AppConfig,
    ExtractionResult,
    PipelineError,
    extract,
    extract_sync,
    render_json,
    render_markdown,
)
from yt_factify.models import (
    AuditBundle,
    BiasProfile,
    ExtractedItem,
    ItemType,
    TopicThread,
    TopicTimeSpan,
    TranscriptEvidence,
    VideoCategory,
    VideoClassification,
    VideoInfo,
)


def _make_result() -> ExtractionResult:
    return ExtractionResult(
        video=VideoInfo(
            video_id="test_vid",
            title="Test",
            url="https://www.youtube.com/watch?v=test_vid",
            transcript_hash="h",
            fetched_at=datetime(2026, 1, 15, tzinfo=UTC),
        ),
        classification=VideoClassification(
            categories=[VideoCategory.TUTORIAL],
            bias_profile=BiasProfile(
                primary_label="neutral",
                confidence=0.9,
                rationale="Technical.",
            ),
        ),
        items=[
            ExtractedItem(
                id="item_1",
                type=ItemType.TRANSCRIPT_FACT,
                content="Python is great.",
                transcript_evidence=TranscriptEvidence(
                    video_id="test_vid",
                    start_ms=0,
                    end_ms=5000,
                    text="Python is great.",
                ),
            ),
        ],
        topic_threads=[
            TopicThread(
                label="python",
                display_name="Python",
                summary="About Python.",
                item_ids=["item_1"],
                timeline=[TopicTimeSpan(start_ms=0, end_ms=5000)],
            ),
        ],
        audit=AuditBundle(
            model_id="gpt-4o-mini",
            model_version=None,
            prompt_templates_hash="ph",
            processing_timestamp=datetime(2026, 1, 15, tzinfo=UTC),
            segment_hashes=["sh"],
            yt_factify_version="0.3.2",
        ),
    )


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------


class TestReExports:
    def test_appconfig_importable(self) -> None:
        assert AppConfig is not None

    def test_extraction_result_importable(self) -> None:
        assert ExtractionResult is not None

    def test_pipeline_error_importable(self) -> None:
        assert PipelineError is not None

    def test_render_json_importable(self) -> None:
        assert callable(render_json)

    def test_render_markdown_importable(self) -> None:
        assert callable(render_markdown)

    def test_extract_importable(self) -> None:
        assert callable(extract)

    def test_extract_sync_importable(self) -> None:
        assert callable(extract_sync)


# ---------------------------------------------------------------------------
# extract() — async
# ---------------------------------------------------------------------------


class TestExtractAsync:
    def test_returns_extraction_result(self) -> None:
        mock_result = _make_result()

        with patch(
            "yt_factify.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            config = AppConfig(model="gpt-4o-mini")
            result = asyncio.run(extract("test_vid", config=config))
            assert isinstance(result, ExtractionResult)
            assert result.video.video_id == "test_vid"
            assert len(result.items) == 1

    def test_with_default_config(self) -> None:
        mock_result = _make_result()

        with (
            patch(
                "yt_factify.run_pipeline",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "yt_factify.config.load_config",
                return_value=AppConfig(model="gpt-4o-mini"),
            ),
        ):
            result = asyncio.run(extract("test_vid"))
            assert isinstance(result, ExtractionResult)

    def test_pipeline_error_propagates(self) -> None:
        with patch(
            "yt_factify.run_pipeline",
            new_callable=AsyncMock,
            side_effect=PipelineError("Pipeline failed"),
        ):
            config = AppConfig(model="gpt-4o-mini")
            with pytest.raises(PipelineError, match="Pipeline failed"):
                asyncio.run(extract("test_vid", config=config))


# ---------------------------------------------------------------------------
# extract_sync()
# ---------------------------------------------------------------------------


class TestExtractSync:
    def test_returns_extraction_result(self) -> None:
        mock_result = _make_result()

        with patch(
            "yt_factify.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            config = AppConfig(model="gpt-4o-mini")
            result = extract_sync("test_vid", config=config)
            assert isinstance(result, ExtractionResult)
            assert result.video.video_id == "test_vid"

    def test_pipeline_error_propagates(self) -> None:
        with patch(
            "yt_factify.run_pipeline",
            new_callable=AsyncMock,
            side_effect=PipelineError("Sync failed"),
        ):
            config = AppConfig(model="gpt-4o-mini")
            with pytest.raises(PipelineError, match="Sync failed"):
                extract_sync("test_vid", config=config)


# ---------------------------------------------------------------------------
# Rendering from public API
# ---------------------------------------------------------------------------


class TestRenderingFromApi:
    def test_render_json_from_result(self) -> None:
        result = _make_result()
        json_str = render_json(result)
        assert '"video_id": "test_vid"' in json_str

    def test_render_markdown_from_result(self) -> None:
        result = _make_result()
        md = render_markdown(result)
        assert "## Video Info" in md
        assert "test_vid" in md
