# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Golden tests and edge case tests for yt-factify pipeline."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_factify.config import AppConfig
from yt_factify.models import (
    BiasProfile,
    CredibilityAssessment,
    CredibilityLabel,
    ExtractedItem,
    ExtractionResult,
    ItemType,
    NormalizedSegment,
    NormalizedTranscript,
    RawTranscript,
    TopicThread,
    TopicTimeSpan,
    TranscriptEvidence,
    TranscriptSegment,
    TranscriptSegmentRaw,
    ValidationResult,
    VideoCategory,
    VideoClassification,
)
from yt_factify.pipeline import PipelineError, run_pipeline
from yt_factify.transcript import EmptyTranscriptError

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TRANSCRIPTS_DIR = FIXTURES_DIR / "transcripts"


def _make_config(**overrides: object) -> AppConfig:
    defaults: dict[str, object] = {
        "model": "gpt-4o-mini",
        "max_retries": 2,
        "max_concurrent_requests": 2,
        "segment_seconds": 45,
    }
    defaults.update(overrides)
    return AppConfig(**defaults)  # type: ignore[arg-type]


def _load_transcript_fixture(name: str) -> RawTranscript:
    path = TRANSCRIPTS_DIR / name
    data = json.loads(path.read_text())
    segments = [
        TranscriptSegmentRaw(
            text=s["text"],
            start_ms=s["start_ms"],
            end_ms=s["end_ms"],
        )
        for s in data["segments"]
    ]
    return RawTranscript(
        video_id=data["video_id"],
        segments=segments,
        language=data.get("language"),
    )


def _make_classification(
    categories: list[VideoCategory] | None = None,
    bias_label: str = "neutral",
) -> VideoClassification:
    return VideoClassification(
        categories=categories or [VideoCategory.OTHER],
        bias_profile=BiasProfile(
            primary_label=bias_label,
            confidence=0.8,
            rationale="Test classification.",
        ),
    )


def _make_items_from_transcript(
    raw: RawTranscript,
    item_type: ItemType = ItemType.TRANSCRIPT_FACT,
) -> list[ExtractedItem]:
    items = []
    for i, seg in enumerate(raw.segments):
        items.append(
            ExtractedItem(
                id=f"{raw.video_id}_item_{i}",
                type=item_type,
                content=seg.text,
                transcript_evidence=TranscriptEvidence(
                    video_id=raw.video_id,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    text=seg.text,
                ),
                credibility=CredibilityAssessment(
                    label=CredibilityLabel.CREDIBLE,
                    confidence=0.8,
                    rationale="Test assessment.",
                ),
            )
        )
    return items


def _make_topics_from_items(
    items: list[ExtractedItem],
    label: str = "main_topic",
) -> list[TopicThread]:
    if len(items) < 3:
        return []
    item_ids = [i.id for i in items]
    return [
        TopicThread(
            label=label,
            display_name=label.replace("_", " ").title(),
            summary="Main topic thread.",
            item_ids=item_ids,
            timeline=[
                TopicTimeSpan(
                    start_ms=items[0].transcript_evidence.start_ms,
                    end_ms=items[-1].transcript_evidence.end_ms,
                ),
            ],
        ),
    ]


def _make_normalized(raw: RawTranscript) -> NormalizedTranscript:
    segs = [
        NormalizedSegment(
            text=s.text,
            start_ms=s.start_ms,
            end_ms=s.end_ms,
            hash=f"h{i}",
        )
        for i, s in enumerate(raw.segments)
    ]
    full = " ".join(s.text for s in segs)
    return NormalizedTranscript(
        video_id=raw.video_id,
        full_text=full,
        hash="full_hash",
        segments=segs,
        language=raw.language,
    )


def _make_segments(raw: RawTranscript) -> list[TranscriptSegment]:
    combined = " ".join(s.text for s in raw.segments)
    return [
        TranscriptSegment(
            text=combined,
            start_ms=raw.segments[0].start_ms,
            end_ms=raw.segments[-1].end_ms,
            hash="seg_hash",
            source_segment_indices=list(range(len(raw.segments))),
        ),
    ]


def _make_validation(items: list[ExtractedItem]) -> ValidationResult:
    return ValidationResult(accepted=items)


def _make_builtin_modules() -> list[MagicMock]:
    return [MagicMock()]


def _run_golden_pipeline(
    fixture_name: str,
    categories: list[VideoCategory] | None = None,
    bias_label: str = "neutral",
) -> ExtractionResult:
    raw = _load_transcript_fixture(fixture_name)
    transcript = _make_normalized(raw)
    segments = _make_segments(raw)
    classification = _make_classification(categories, bias_label)
    items = _make_items_from_transcript(raw)
    topics = _make_topics_from_items(items)
    validation = _make_validation(items)

    with (
        patch("yt_factify.pipeline.fetch_transcript", return_value=raw),
        patch(
            "yt_factify.pipeline.normalize_transcript",
            return_value=transcript,
        ),
        patch(
            "yt_factify.pipeline.segment_transcript",
            return_value=segments,
        ),
        patch(
            "yt_factify.pipeline.get_builtin_modules",
            return_value=_make_builtin_modules(),
        ),
        patch(
            "yt_factify.pipeline.classify_video",
            new_callable=AsyncMock,
            return_value=classification,
        ),
        patch(
            "yt_factify.pipeline.extract_items",
            new_callable=AsyncMock,
            return_value=items,
        ),
        patch(
            "yt_factify.pipeline.validate_items",
            return_value=validation,
        ),
        patch(
            "yt_factify.pipeline.assess_credibility",
            new_callable=AsyncMock,
            return_value=items,
        ),
        patch(
            "yt_factify.pipeline.cluster_topic_threads",
            new_callable=AsyncMock,
            return_value=topics,
        ),
    ):
        config = _make_config()
        return asyncio.run(run_pipeline(raw.video_id, config))


# ---------------------------------------------------------------------------
# Golden Tests — Short News Clip
# ---------------------------------------------------------------------------


class TestGoldenNewsClip:
    def test_pipeline_produces_result(self) -> None:
        result = _run_golden_pipeline(
            "short_news_clip.json",
            categories=[VideoCategory.NEWS],
        )
        assert result.video.video_id == "news789"
        assert len(result.items) == 6

    def test_classification_preserved(self) -> None:
        result = _run_golden_pipeline(
            "short_news_clip.json",
            categories=[VideoCategory.NEWS],
        )
        assert VideoCategory.NEWS in result.classification.categories

    def test_audit_bundle_populated(self) -> None:
        result = _run_golden_pipeline("short_news_clip.json")
        assert result.audit.model_id == "gpt-4o-mini"
        assert result.audit.yt_factify_version is not None
        assert len(result.audit.segment_hashes) >= 1

    def test_items_have_evidence(self) -> None:
        result = _run_golden_pipeline("short_news_clip.json")
        for item in result.items:
            assert item.transcript_evidence.video_id == "news789"
            assert item.transcript_evidence.start_ms >= 0
            assert item.transcript_evidence.end_ms > item.transcript_evidence.start_ms

    def test_topic_threads_present(self) -> None:
        result = _run_golden_pipeline("short_news_clip.json")
        assert len(result.topic_threads) >= 1


# ---------------------------------------------------------------------------
# Golden Tests — Long Interview
# ---------------------------------------------------------------------------


class TestGoldenInterview:
    def test_pipeline_produces_result(self) -> None:
        result = _run_golden_pipeline(
            "long_interview.json",
            categories=[VideoCategory.INTERVIEW],
        )
        assert result.video.video_id == "interview456"
        assert len(result.items) == 21

    def test_all_items_have_credibility(self) -> None:
        result = _run_golden_pipeline("long_interview.json")
        for item in result.items:
            assert item.credibility is not None

    def test_video_url_correct(self) -> None:
        result = _run_golden_pipeline("long_interview.json")
        assert "interview456" in result.video.url


# ---------------------------------------------------------------------------
# Golden Tests — Opinion/Editorial
# ---------------------------------------------------------------------------


class TestGoldenOpinionEditorial:
    def test_pipeline_produces_result(self) -> None:
        result = _run_golden_pipeline(
            "opinion_editorial.json",
            categories=[VideoCategory.OPINION_EDITORIAL],
            bias_label="left_leaning",
        )
        assert result.video.video_id == "opinion101"
        assert len(result.items) == 8

    def test_bias_profile_preserved(self) -> None:
        result = _run_golden_pipeline(
            "opinion_editorial.json",
            bias_label="left_leaning",
        )
        assert result.classification.bias_profile.primary_label == "left_leaning"

    def test_json_roundtrip(self) -> None:
        result = _run_golden_pipeline("opinion_editorial.json")
        json_str = result.model_dump_json()
        restored = ExtractionResult.model_validate_json(json_str)
        assert restored.video.video_id == result.video.video_id
        assert len(restored.items) == len(result.items)
        assert len(restored.topic_threads) == len(result.topic_threads)


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCaseEmptyTranscript:
    def test_empty_segments_raises(self) -> None:
        raw = RawTranscript(video_id="empty", segments=[])

        with (
            patch("yt_factify.pipeline.fetch_transcript", return_value=raw),
            patch(
                "yt_factify.pipeline.normalize_transcript",
                side_effect=EmptyTranscriptError("No segments"),
            ),
        ):
            config = _make_config()
            with pytest.raises(PipelineError, match="fetch/normalize"):
                asyncio.run(run_pipeline("empty", config))


class TestEdgeCaseSingleSegment:
    def test_single_segment_succeeds(self) -> None:
        raw = RawTranscript(
            video_id="single",
            segments=[
                TranscriptSegmentRaw(
                    text="Just one segment here.",
                    start_ms=0,
                    end_ms=5000,
                ),
            ],
        )
        transcript = _make_normalized(raw)
        segments = _make_segments(raw)
        classification = _make_classification()
        items = _make_items_from_transcript(raw)
        validation = _make_validation(items)

        with (
            patch(
                "yt_factify.pipeline.fetch_transcript",
                return_value=raw,
            ),
            patch(
                "yt_factify.pipeline.normalize_transcript",
                return_value=transcript,
            ),
            patch(
                "yt_factify.pipeline.segment_transcript",
                return_value=segments,
            ),
            patch(
                "yt_factify.pipeline.get_builtin_modules",
                return_value=[],
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=items,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                return_value=items,
            ),
            patch(
                "yt_factify.pipeline.cluster_topic_threads",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            config = _make_config()
            result = asyncio.run(run_pipeline("single", config))
            assert len(result.items) == 1
            # Too few items for topic threading
            assert result.topic_threads == []


class TestEdgeCaseNoFacts:
    def test_no_items_extracted(self) -> None:
        raw = _load_transcript_fixture("short_tutorial.json")
        transcript = _make_normalized(raw)
        segments = _make_segments(raw)
        classification = _make_classification()
        validation = ValidationResult(accepted=[])

        with (
            patch(
                "yt_factify.pipeline.fetch_transcript",
                return_value=raw,
            ),
            patch(
                "yt_factify.pipeline.normalize_transcript",
                return_value=transcript,
            ),
            patch(
                "yt_factify.pipeline.segment_transcript",
                return_value=segments,
            ),
            patch(
                "yt_factify.pipeline.get_builtin_modules",
                return_value=[],
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "yt_factify.pipeline.cluster_topic_threads",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            config = _make_config()
            result = asyncio.run(run_pipeline("tutorial123", config))
            assert result.items == []
            assert result.topic_threads == []


class TestEdgeCaseAllQuotesFailVerification:
    def test_all_rejected(self) -> None:
        raw = _load_transcript_fixture("short_tutorial.json")
        transcript = _make_normalized(raw)
        segments = _make_segments(raw)
        classification = _make_classification()
        items = _make_items_from_transcript(raw)
        # All items rejected
        validation = ValidationResult(accepted=[], rejected=items)

        with (
            patch(
                "yt_factify.pipeline.fetch_transcript",
                return_value=raw,
            ),
            patch(
                "yt_factify.pipeline.normalize_transcript",
                return_value=transcript,
            ),
            patch(
                "yt_factify.pipeline.segment_transcript",
                return_value=segments,
            ),
            patch(
                "yt_factify.pipeline.get_builtin_modules",
                return_value=[],
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=items,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "yt_factify.pipeline.cluster_topic_threads",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            config = _make_config()
            result = asyncio.run(run_pipeline("tutorial123", config))
            assert result.items == []


class TestEdgeCaseVeryLongTranscript:
    def test_long_transcript_succeeds(self) -> None:
        """Simulate a >2 hour transcript with many segments."""
        num_segments = 500
        segments_raw = [
            TranscriptSegmentRaw(
                text=f"Segment {i} content about various topics.",
                start_ms=i * 15000,
                end_ms=(i + 1) * 15000,
            )
            for i in range(num_segments)
        ]
        raw = RawTranscript(
            video_id="long_vid",
            segments=segments_raw,
        )
        transcript = _make_normalized(raw)
        seg_list = _make_segments(raw)
        classification = _make_classification()
        # Only extract a subset of items
        items = _make_items_from_transcript(
            RawTranscript(
                video_id="long_vid",
                segments=segments_raw[:10],
            )
        )
        topics = _make_topics_from_items(items)
        validation = _make_validation(items)

        with (
            patch(
                "yt_factify.pipeline.fetch_transcript",
                return_value=raw,
            ),
            patch(
                "yt_factify.pipeline.normalize_transcript",
                return_value=transcript,
            ),
            patch(
                "yt_factify.pipeline.segment_transcript",
                return_value=seg_list,
            ),
            patch(
                "yt_factify.pipeline.get_builtin_modules",
                return_value=[],
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=items,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                return_value=items,
            ),
            patch(
                "yt_factify.pipeline.cluster_topic_threads",
                new_callable=AsyncMock,
                return_value=topics,
            ),
        ):
            config = _make_config()
            result = asyncio.run(run_pipeline("long_vid", config))
            assert len(result.items) == 10
            # Verify the transcript was >2 hours (500 * 15s = 7500s = 2h5m)
            total_ms = segments_raw[-1].end_ms
            assert total_ms > 2 * 60 * 60 * 1000


class TestEdgeCaseMalformedLlmResponse:
    def test_extraction_failure_propagates(self) -> None:
        raw = _load_transcript_fixture("short_tutorial.json")
        transcript = _make_normalized(raw)
        segments = _make_segments(raw)
        classification = _make_classification()

        with (
            patch(
                "yt_factify.pipeline.fetch_transcript",
                return_value=raw,
            ),
            patch(
                "yt_factify.pipeline.normalize_transcript",
                return_value=transcript,
            ),
            patch(
                "yt_factify.pipeline.segment_transcript",
                return_value=segments,
            ),
            patch(
                "yt_factify.pipeline.get_builtin_modules",
                return_value=[],
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Malformed JSON from LLM"),
            ),
        ):
            config = _make_config()
            with pytest.raises(PipelineError, match="extract"):
                asyncio.run(run_pipeline("tutorial123", config))
