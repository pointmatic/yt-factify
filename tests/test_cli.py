# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for yt_factify.cli."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from yt_factify.cli import (
    EXIT_GENERAL,
    EXIT_LLM,
    EXIT_TRANSCRIPT,
    _classify_error,
    _parse_video_id,
    cli,
)
from yt_factify.models import (
    AuditBundle,
    BiasProfile,
    ExtractedItem,
    ExtractionResult,
    ItemType,
    TopicThread,
    TopicTimeSpan,
    TranscriptEvidence,
    VideoCategory,
    VideoClassification,
    VideoInfo,
)
from yt_factify.pipeline import PipelineError


def _make_extraction_result() -> ExtractionResult:
    return ExtractionResult(
        video=VideoInfo(
            video_id="dQw4w9WgXcQ",
            title="Test Video",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            transcript_hash="hash123",
            fetched_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        ),
        classification=VideoClassification(
            categories=[VideoCategory.TUTORIAL],
            bias_profile=BiasProfile(
                primary_label="neutral",
                confidence=0.9,
                rationale="Technical content.",
            ),
        ),
        items=[
            ExtractedItem(
                id="item_1",
                type=ItemType.TRANSCRIPT_FACT,
                content="Python is a programming language.",
                transcript_evidence=TranscriptEvidence(
                    video_id="dQw4w9WgXcQ",
                    start_ms=0,
                    end_ms=5000,
                    text="Python is a programming language.",
                ),
            ),
        ],
        topic_threads=[
            TopicThread(
                label="python",
                display_name="Python",
                summary="Discussion about Python.",
                item_ids=["item_1"],
                timeline=[TopicTimeSpan(start_ms=0, end_ms=5000)],
            ),
        ],
        audit=AuditBundle(
            model_id="gpt-4o-mini",
            model_version=None,
            prompt_templates_hash="phash",
            processing_timestamp=datetime(2026, 1, 15, 12, 5, 0, tzinfo=UTC),
            segment_hashes=["sh1"],
            yt_factify_version="0.3.1",
        ),
    )


# ---------------------------------------------------------------------------
# _parse_video_id
# ---------------------------------------------------------------------------


class TestParseVideoId:
    def test_plain_id(self) -> None:
        assert _parse_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_full_url(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert _parse_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self) -> None:
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert _parse_video_id(url) == "dQw4w9WgXcQ"

    def test_url_with_params(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"
        assert _parse_video_id(url) == "dQw4w9WgXcQ"

    def test_non_url_passthrough(self) -> None:
        assert _parse_video_id("some_custom_id") == "some_custom_id"


# ---------------------------------------------------------------------------
# _classify_error
# ---------------------------------------------------------------------------


class TestClassifyError:
    def test_transcript_error(self) -> None:
        assert _classify_error("Failed to fetch transcript") == EXIT_TRANSCRIPT

    def test_llm_error(self) -> None:
        assert _classify_error("Failed to classify video") == EXIT_LLM
        assert _classify_error("Failed to extract items") == EXIT_LLM
        assert _classify_error("credibility failed") == EXIT_LLM

    def test_general_error(self) -> None:
        assert _classify_error("Something went wrong") == EXIT_GENERAL


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


class TestVersionCommand:
    def test_version_output(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "yt-factify" in result.output


class TestExtractCommand:
    def test_extract_json_stdout(self) -> None:
        mock_result = _make_extraction_result()

        with patch(
            "yt_factify.cli.asyncio.run",
            return_value=mock_result,
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "extract",
                    "dQw4w9WgXcQ",
                    "--model",
                    "gpt-4o-mini",
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert parsed["video"]["video_id"] == "dQw4w9WgXcQ"

    def test_extract_markdown_stdout(self) -> None:
        mock_result = _make_extraction_result()

        with patch(
            "yt_factify.cli.asyncio.run",
            return_value=mock_result,
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "extract",
                    "dQw4w9WgXcQ",
                    "--model",
                    "gpt-4o-mini",
                    "--format",
                    "markdown",
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == 0
            assert "## Video Info" in result.output
            assert "dQw4w9WgXcQ" in result.output

    def test_extract_output_file(self, tmp_path: Path) -> None:
        mock_result = _make_extraction_result()
        out_file = tmp_path / "output.json"

        with patch(
            "yt_factify.cli.asyncio.run",
            return_value=mock_result,
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "extract",
                    "dQw4w9WgXcQ",
                    "--model",
                    "gpt-4o-mini",
                    "--output",
                    str(out_file),
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == 0
            assert out_file.exists()
            parsed = json.loads(out_file.read_text())
            assert parsed["video"]["video_id"] == "dQw4w9WgXcQ"

    def test_extract_pipeline_error_transcript(self) -> None:
        with patch(
            "yt_factify.cli.asyncio.run",
            side_effect=PipelineError("Failed to fetch/normalize transcript for vid: error"),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "extract",
                    "vid",
                    "--model",
                    "gpt-4o-mini",
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == EXIT_TRANSCRIPT

    def test_extract_pipeline_error_llm(self) -> None:
        with patch(
            "yt_factify.cli.asyncio.run",
            side_effect=PipelineError("Failed to classify video vid: LLM error"),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "extract",
                    "vid",
                    "--model",
                    "gpt-4o-mini",
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == EXIT_LLM

    def test_extract_unexpected_error(self) -> None:
        with patch(
            "yt_factify.cli.asyncio.run",
            side_effect=RuntimeError("Unexpected"),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "extract",
                    "vid",
                    "--model",
                    "gpt-4o-mini",
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == EXIT_GENERAL

    def test_help_output(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["extract", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--format" in result.output
        assert "--output" in result.output
        assert "--modules-dir" in result.output

    def test_extract_with_url(self) -> None:
        mock_result = _make_extraction_result()

        with patch(
            "yt_factify.cli.asyncio.run",
            return_value=mock_result,
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "extract",
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "--model",
                    "gpt-4o-mini",
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert parsed["video"]["video_id"] == "dQw4w9WgXcQ"
