# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

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
    EXIT_VALIDATION,
    _classify_error,
    _parse_video_id,
    _resolve_output_path,
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
# _resolve_output_path
# ---------------------------------------------------------------------------


class TestResolveOutputPath:
    def test_explicit_filename(self) -> None:
        result = _resolve_output_path("foo.json", "ABCDEF12345", "json")
        assert result == Path("foo.json")

    def test_explicit_filename_markdown(self) -> None:
        result = _resolve_output_path("report.md", "ABCDEF12345", "markdown")
        assert result == Path("report.md")

    def test_trailing_slash_json(self) -> None:
        result = _resolve_output_path("foo/", "ABCDEF12345", "json")
        assert result == Path("foo/ABCDEF12345.json")

    def test_trailing_slash_markdown(self) -> None:
        result = _resolve_output_path("foo/", "ABCDEF12345", "markdown")
        assert result == Path("foo/ABCDEF12345.md")

    def test_existing_directory(self, tmp_path: Path) -> None:
        result = _resolve_output_path(
            str(tmp_path),
            "ABCDEF12345",
            "json",
        )
        assert result == tmp_path / "ABCDEF12345.json"

    def test_existing_directory_markdown(self, tmp_path: Path) -> None:
        result = _resolve_output_path(
            str(tmp_path),
            "ABCDEF12345",
            "markdown",
        )
        assert result == tmp_path / "ABCDEF12345.md"

    def test_nested_trailing_slash(self) -> None:
        result = _resolve_output_path(
            "a/b/c/",
            "VID_ID_12345",
            "json",
        )
        assert result == Path("a/b/c/VID_ID_12345.json")


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

    def test_extract_output_dir_trailing_slash(self, tmp_path: Path) -> None:
        mock_result = _make_extraction_result()
        out_dir = tmp_path / "results"

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
                    str(out_dir) + "/",
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == 0
            auto_file = out_dir / "dQw4w9WgXcQ.json"
            assert auto_file.exists()
            parsed = json.loads(auto_file.read_text())
            assert parsed["video"]["video_id"] == "dQw4w9WgXcQ"

    def test_extract_output_existing_dir(self, tmp_path: Path) -> None:
        mock_result = _make_extraction_result()
        out_dir = tmp_path / "existing"
        out_dir.mkdir()

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
                    "--output",
                    str(out_dir),
                    "--log-level",
                    "ERROR",
                ],
            )
            assert result.exit_code == 0
            auto_file = out_dir / "dQw4w9WgXcQ.md"
            assert auto_file.exists()
            content = auto_file.read_text()
            assert "dQw4w9WgXcQ" in content

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


# ---------------------------------------------------------------------------
# convert command
# ---------------------------------------------------------------------------


def _write_json_fixture(path: Path) -> None:
    """Write a valid extraction JSON fixture to *path*."""
    from yt_factify.rendering import render_json

    path.write_text(render_json(_make_extraction_result()), encoding="utf-8")


class TestConvertCommand:
    def test_convert_json_to_markdown_stdout(self, tmp_path: Path) -> None:
        src = tmp_path / "input.json"
        _write_json_fixture(src)

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", str(src)])
        assert result.exit_code == 0
        assert "## Video Info" in result.output
        assert "dQw4w9WgXcQ" in result.output

    def test_convert_json_to_markdown_file(self, tmp_path: Path) -> None:
        src = tmp_path / "input.json"
        _write_json_fixture(src)
        out = tmp_path / "report.md"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["convert", str(src), "--output", str(out)],
        )
        assert result.exit_code == 0
        assert out.exists()
        content = out.read_text()
        assert "## Video Info" in content

    def test_convert_json_to_markdown_dir_autoname(self, tmp_path: Path) -> None:
        src = tmp_path / "input.json"
        _write_json_fixture(src)
        out_dir = tmp_path / "reports"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["convert", str(src), "--output", str(out_dir) + "/"],
        )
        assert result.exit_code == 0
        auto_file = out_dir / "dQw4w9WgXcQ.md"
        assert auto_file.exists()
        assert "dQw4w9WgXcQ" in auto_file.read_text()

    def test_convert_json_to_json(self, tmp_path: Path) -> None:
        src = tmp_path / "input.json"
        _write_json_fixture(src)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["convert", str(src), "--format", "json"],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["video"]["video_id"] == "dQw4w9WgXcQ"

    def test_convert_invalid_json(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.json"
        src.write_text("not valid json {{{", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", str(src)])
        assert result.exit_code == EXIT_VALIDATION
        assert "invalid extraction JSON" in result.output

    def test_convert_invalid_schema(self, tmp_path: Path) -> None:
        src = tmp_path / "bad_schema.json"
        src.write_text('{"foo": "bar"}', encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", str(src)])
        assert result.exit_code == EXIT_VALIDATION
        assert "invalid extraction JSON" in result.output

    def test_convert_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["convert", "--help"])
        assert result.exit_code == 0
        assert "Convert an existing extraction JSON" in result.output
