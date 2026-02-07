# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for yt_factify.transcript."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yt_factify.config import AppConfig
from yt_factify.models import (
    NormalizedTranscript,
    RawTranscript,
    TranscriptSegmentRaw,
    VideoMetadata,
)
from yt_factify.transcript import (
    EmptyTranscriptError,
    TranscriptFetchError,
    _normalize_text,
    _sha256,
    _upload_date_hint,
    fetch_transcript,
    normalize_transcript,
    segment_transcript,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "transcripts"


def _load_fixture(name: str) -> RawTranscript:
    """Load a transcript fixture JSON file into a RawTranscript."""
    data = json.loads((FIXTURES_DIR / name).read_text())
    return RawTranscript(**data)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_strips_whitespace(self) -> None:
        assert _normalize_text("  hello   world  ") == "hello world"

    def test_collapses_internal_whitespace(self) -> None:
        assert _normalize_text("hello\t\n  world") == "hello world"

    def test_unicode_normalization(self) -> None:
        # é as combining characters vs precomposed
        combining = "e\u0301"  # e + combining acute accent
        precomposed = "\u00e9"  # é precomposed
        assert _normalize_text(combining) == _normalize_text(precomposed)

    def test_empty_string(self) -> None:
        assert _normalize_text("") == ""

    def test_whitespace_only(self) -> None:
        assert _normalize_text("   \t\n  ") == ""


class TestSha256:
    def test_deterministic(self) -> None:
        assert _sha256("hello") == _sha256("hello")

    def test_different_inputs(self) -> None:
        assert _sha256("hello") != _sha256("world")


# ---------------------------------------------------------------------------
# normalize_transcript
# ---------------------------------------------------------------------------


class TestNormalizeTranscript:
    def test_short_tutorial(self) -> None:
        raw = _load_fixture("short_tutorial.json")
        result = normalize_transcript(raw)
        assert result.video_id == "tutorial123"
        assert result.language == "en"
        assert len(result.segments) == 8
        assert result.hash  # non-empty hash
        assert result.full_text  # non-empty full text

    def test_long_interview(self) -> None:
        raw = _load_fixture("long_interview.json")
        result = normalize_transcript(raw)
        assert result.video_id == "interview456"
        assert len(result.segments) == 21

    def test_per_segment_hashes_unique(self) -> None:
        raw = _load_fixture("short_tutorial.json")
        result = normalize_transcript(raw)
        hashes = [seg.hash for seg in result.segments]
        assert len(hashes) == len(set(hashes))

    def test_full_text_is_joined_segments(self) -> None:
        raw = _load_fixture("short_tutorial.json")
        result = normalize_transcript(raw)
        expected = " ".join(seg.text for seg in result.segments)
        assert result.full_text == expected

    def test_whitespace_normalization(self) -> None:
        raw = RawTranscript(
            video_id="test",
            segments=[
                TranscriptSegmentRaw(text="  hello   world  ", start_ms=0, end_ms=5000),
                TranscriptSegmentRaw(text="foo\t\nbar", start_ms=5000, end_ms=10000),
            ],
        )
        result = normalize_transcript(raw)
        assert result.segments[0].text == "hello world"
        assert result.segments[1].text == "foo bar"

    def test_unicode_normalization(self) -> None:
        raw = RawTranscript(
            video_id="test",
            segments=[
                TranscriptSegmentRaw(text="caf\u00e9", start_ms=0, end_ms=5000),
                TranscriptSegmentRaw(text="cafe\u0301", start_ms=5000, end_ms=10000),
            ],
        )
        result = normalize_transcript(raw)
        # Both should normalize to the same text
        assert result.segments[0].text == result.segments[1].text
        assert result.segments[0].hash == result.segments[1].hash

    def test_empty_segments_raises(self) -> None:
        raw = RawTranscript(video_id="empty", segments=[])
        with pytest.raises(EmptyTranscriptError):
            normalize_transcript(raw)

    def test_all_whitespace_segments_raises(self) -> None:
        raw = RawTranscript(
            video_id="blank",
            segments=[
                TranscriptSegmentRaw(text="   ", start_ms=0, end_ms=5000),
                TranscriptSegmentRaw(text="\t\n", start_ms=5000, end_ms=10000),
            ],
        )
        with pytest.raises(EmptyTranscriptError):
            normalize_transcript(raw)


# ---------------------------------------------------------------------------
# segment_transcript
# ---------------------------------------------------------------------------


class TestSegmentTranscript:
    def test_short_video_single_segment(self) -> None:
        raw = _load_fixture("short_tutorial.json")
        normalized = normalize_transcript(raw)
        # 27s total, target 45s → single segment
        segments = segment_transcript(normalized, target_seconds=45)
        assert len(segments) == 1
        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 27000
        assert len(segments[0].source_segment_indices) == 8

    def test_long_video_multiple_segments(self) -> None:
        raw = _load_fixture("long_interview.json")
        normalized = normalize_transcript(raw)
        # 85s total, target 45s → should produce 2 segments
        segments = segment_transcript(normalized, target_seconds=45)
        assert len(segments) == 2
        # First segment should cover roughly 45s
        assert segments[0].end_ms >= 40000
        # All source indices should be covered
        all_indices = []
        for seg in segments:
            all_indices.extend(seg.source_segment_indices)
        assert sorted(all_indices) == list(range(len(normalized.segments)))

    def test_each_segment_has_hash(self) -> None:
        raw = _load_fixture("long_interview.json")
        normalized = normalize_transcript(raw)
        segments = segment_transcript(normalized, target_seconds=45)
        for seg in segments:
            assert seg.hash
            assert len(seg.hash) == 64  # SHA-256 hex digest

    def test_small_target_many_segments(self) -> None:
        raw = _load_fixture("short_tutorial.json")
        normalized = normalize_transcript(raw)
        # Very small target → more segments
        segments = segment_transcript(normalized, target_seconds=5)
        assert len(segments) >= 3

    def test_empty_transcript_returns_empty(self) -> None:
        nt = NormalizedTranscript(
            video_id="empty",
            full_text="",
            hash=_sha256(""),
            segments=[],
        )
        assert segment_transcript(nt) == []

    def test_segment_text_combines_sources(self) -> None:
        raw = _load_fixture("short_tutorial.json")
        normalized = normalize_transcript(raw)
        segments = segment_transcript(normalized, target_seconds=45)
        # Single segment should contain all text
        for norm_seg in normalized.segments:
            assert norm_seg.text in segments[0].text


# ---------------------------------------------------------------------------
# fetch_transcript (mocked yt-fetch)
# ---------------------------------------------------------------------------


class TestFetchTranscript:
    def test_successful_fetch(self) -> None:
        mock_segment = MagicMock()
        mock_segment.text = "Hello world"
        mock_segment.start = 0.0
        mock_segment.duration = 5.0

        mock_transcript = MagicMock()
        mock_transcript.segments = [mock_segment]
        mock_transcript.language = "en"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.transcript = mock_transcript
        mock_result.errors = []
        mock_result.metadata = None

        mock_yt_fetch = MagicMock()
        mock_yt_fetch.fetch_video.return_value = mock_result
        mock_yt_fetch.FetchOptions = MagicMock()

        with patch.dict("sys.modules", {"yt_fetch": mock_yt_fetch}):
            config = AppConfig()
            result = fetch_transcript("test123", config)
            assert result.video_id == "test123"
            assert len(result.segments) == 1
            assert result.segments[0].text == "Hello world"
            assert result.segments[0].start_ms == 0
            assert result.segments[0].end_ms == 5000
            assert result.language == "en"
            assert result.metadata is None

    def test_failed_fetch_raises(self) -> None:
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.transcript = None
        mock_result.errors = ["Video not found"]
        mock_result.metadata = None

        mock_yt_fetch = MagicMock()
        mock_yt_fetch.fetch_video.return_value = mock_result
        mock_yt_fetch.FetchOptions = MagicMock()

        with patch.dict("sys.modules", {"yt_fetch": mock_yt_fetch}):
            config = AppConfig()
            with pytest.raises(TranscriptFetchError, match="Video not found"):
                fetch_transcript("bad_id", config)

    def test_no_transcript_raises(self) -> None:
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.transcript = None
        mock_result.errors = []
        mock_result.metadata = None

        mock_yt_fetch = MagicMock()
        mock_yt_fetch.fetch_video.return_value = mock_result
        mock_yt_fetch.FetchOptions = MagicMock()

        with patch.dict("sys.modules", {"yt_fetch": mock_yt_fetch}):
            config = AppConfig()
            with pytest.raises(TranscriptFetchError):
                fetch_transcript("no_transcript", config)

    def test_metadata_passthrough(self) -> None:
        mock_segment = MagicMock()
        mock_segment.text = "Hello"
        mock_segment.start = 0.0
        mock_segment.duration = 5.0

        mock_transcript = MagicMock()
        mock_transcript.segments = [mock_segment]
        mock_transcript.language = "en"

        mock_metadata = MagicMock()
        mock_metadata.title = "Test Video"
        mock_metadata.channel_id = "UC123"
        mock_metadata.channel_title = "Test Channel"
        mock_metadata.upload_date = "2025-06-15"
        mock_metadata.duration_seconds = 120.0
        mock_metadata.fetched_at = "2025-06-15T12:00:00Z"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.transcript = mock_transcript
        mock_result.errors = []
        mock_result.metadata = mock_metadata

        mock_yt_fetch = MagicMock()
        mock_yt_fetch.fetch_video.return_value = mock_result
        mock_yt_fetch.FetchOptions = MagicMock()

        with patch.dict("sys.modules", {"yt_fetch": mock_yt_fetch}):
            config = AppConfig()
            result = fetch_transcript("test123", config)
            assert result.metadata is not None
            assert result.metadata.title == "Test Video"
            assert result.metadata.channel_id == "UC123"
            assert result.metadata.channel_title == "Test Channel"
            assert result.metadata.upload_date == "2025-06-15"
            assert result.metadata.duration_seconds == 120.0

    def test_configurable_languages(self) -> None:
        mock_segment = MagicMock()
        mock_segment.text = "Bonjour"
        mock_segment.start = 0.0
        mock_segment.duration = 3.0

        mock_transcript = MagicMock()
        mock_transcript.segments = [mock_segment]
        mock_transcript.language = "fr"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.transcript = mock_transcript
        mock_result.errors = []
        mock_result.metadata = None

        mock_yt_fetch = MagicMock()
        mock_yt_fetch.fetch_video.return_value = mock_result
        mock_yt_fetch.FetchOptions = MagicMock()

        with patch.dict("sys.modules", {"yt_fetch": mock_yt_fetch}):
            config = AppConfig(languages=["fr"])
            result = fetch_transcript("french_vid", config)
            assert result.language == "fr"
            # Verify FetchOptions was called with the right languages
            call_kwargs = mock_yt_fetch.FetchOptions.call_args
            assert call_kwargs.kwargs["languages"] == ["fr"]


class TestUploadDateHint:
    def test_no_metadata(self) -> None:
        assert "may lack captions" in _upload_date_hint(None)

    def test_no_upload_date(self) -> None:
        meta = VideoMetadata()
        assert "may lack captions" in _upload_date_hint(meta)

    def test_invalid_upload_date(self) -> None:
        meta = VideoMetadata(upload_date="not-a-date")
        assert "may lack captions" in _upload_date_hint(meta)

    def test_recent_upload_under_24h(self) -> None:
        from datetime import date

        today = date.today().isoformat()
        meta = VideoMetadata(upload_date=today)
        hint = _upload_date_hint(meta)
        assert "within the last 24 hours" in hint

    def test_recent_upload_within_week(self) -> None:
        from datetime import date, timedelta

        three_days_ago = (date.today() - timedelta(days=3)).isoformat()
        meta = VideoMetadata(upload_date=three_days_ago)
        hint = _upload_date_hint(meta)
        assert "uploaded recently" in hint

    def test_old_upload(self) -> None:
        meta = VideoMetadata(upload_date="2020-01-01")
        hint = _upload_date_hint(meta)
        assert "may lack captions" in hint
