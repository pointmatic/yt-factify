# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for yt_factify.pipeline."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_factify.config import AppConfig
from yt_factify.models import (
    BeliefSystemModule,
    BiasProfile,
    CredibilityAssessment,
    CredibilityLabel,
    ExtractedItem,
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


def _make_config(**overrides: object) -> AppConfig:
    defaults: dict[str, object] = {
        "model": "gpt-4o-mini",
        "max_retries": 2,
        "max_concurrent_requests": 2,
        "segment_seconds": 45,
    }
    defaults.update(overrides)
    return AppConfig(**defaults)  # type: ignore[arg-type]


def _make_raw_transcript() -> RawTranscript:
    return RawTranscript(
        video_id="test_vid",
        segments=[
            TranscriptSegmentRaw(
                text="Data classes were introduced in Python 3.7.",
                start_ms=0,
                end_ms=5000,
            ),
            TranscriptSegmentRaw(
                text="They reduce boilerplate code significantly.",
                start_ms=5000,
                end_ms=10000,
            ),
            TranscriptSegmentRaw(
                text="You can use frozen=True for immutability.",
                start_ms=10000,
                end_ms=15000,
            ),
        ],
    )


def _make_normalized_transcript() -> NormalizedTranscript:
    segs = [
        NormalizedSegment(
            text="Data classes were introduced in Python 3.7.",
            start_ms=0,
            end_ms=5000,
            hash="h0",
        ),
        NormalizedSegment(
            text="They reduce boilerplate code significantly.",
            start_ms=5000,
            end_ms=10000,
            hash="h1",
        ),
        NormalizedSegment(
            text="You can use frozen=True for immutability.",
            start_ms=10000,
            end_ms=15000,
            hash="h2",
        ),
    ]
    full = " ".join(s.text for s in segs)
    return NormalizedTranscript(
        video_id="test_vid",
        full_text=full,
        hash="full_hash",
        segments=segs,
    )


def _make_segments() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            text=(
                "Data classes were introduced in Python 3.7. "
                "They reduce boilerplate code significantly. "
                "You can use frozen=True for immutability."
            ),
            start_ms=0,
            end_ms=15000,
            hash="seg_hash",
            source_segment_indices=[0, 1, 2],
        ),
    ]


def _make_classification() -> VideoClassification:
    return VideoClassification(
        categories=[VideoCategory.TUTORIAL],
        bias_profile=BiasProfile(
            primary_label="neutral",
            confidence=0.9,
            rationale="Technical tutorial with no political content.",
        ),
    )


def _make_extracted_items() -> list[ExtractedItem]:
    return [
        ExtractedItem(
            id="item_1",
            type=ItemType.TRANSCRIPT_FACT,
            content="Data classes were introduced in Python 3.7.",
            transcript_evidence=TranscriptEvidence(
                video_id="test_vid",
                start_ms=0,
                end_ms=5000,
                text="Data classes were introduced in Python 3.7.",
            ),
        ),
        ExtractedItem(
            id="item_2",
            type=ItemType.TRANSCRIPT_FACT,
            content="They reduce boilerplate code significantly.",
            transcript_evidence=TranscriptEvidence(
                video_id="test_vid",
                start_ms=5000,
                end_ms=10000,
                text="They reduce boilerplate code significantly.",
            ),
        ),
        ExtractedItem(
            id="item_3",
            type=ItemType.TRANSCRIPT_FACT,
            content="You can use frozen=True for immutability.",
            transcript_evidence=TranscriptEvidence(
                video_id="test_vid",
                start_ms=10000,
                end_ms=15000,
                text="You can use frozen=True for immutability.",
            ),
        ),
    ]


def _make_assessed_items() -> list[ExtractedItem]:
    items = _make_extracted_items()
    assessed = []
    for item in items:
        assessed.append(
            item.model_copy(
                update={
                    "credibility": CredibilityAssessment(
                        label=CredibilityLabel.WELL_ESTABLISHED,
                        confidence=0.95,
                        rationale="Well-known Python feature.",
                    )
                }
            )
        )
    return assessed


def _make_topic_threads() -> list[TopicThread]:
    return [
        TopicThread(
            label="python_data_classes",
            display_name="Python Data Classes",
            summary="Discussion of Python data classes.",
            item_ids=["item_1", "item_2", "item_3"],
            timeline=[TopicTimeSpan(start_ms=0, end_ms=15000)],
        ),
    ]


def _make_builtin_modules() -> list[BeliefSystemModule]:
    return [
        BeliefSystemModule(
            label="scientific_materialism",
            display_name="Scientific Materialism",
            description="Empirical evidence worldview.",
            core_assumptions=["Evidence is key."],
        ),
    ]


def _make_validation_result(
    items: list[ExtractedItem],
) -> ValidationResult:
    return ValidationResult(accepted=items)


# ---------------------------------------------------------------------------
# Full pipeline test
# ---------------------------------------------------------------------------


class TestRunPipeline:
    def test_full_pipeline_success(self) -> None:
        raw = _make_raw_transcript()
        transcript = _make_normalized_transcript()
        segments = _make_segments()
        classification = _make_classification()
        extracted = _make_extracted_items()
        assessed = _make_assessed_items()
        threads = _make_topic_threads()
        modules = _make_builtin_modules()
        validation = _make_validation_result(extracted)

        with (
            patch(
                "yt_factify.pipeline.fetch_transcript",
                return_value=raw,
            ) as mock_fetch,
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
                return_value=modules,
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=extracted,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                return_value=assessed,
            ),
            patch(
                "yt_factify.pipeline.cluster_topic_threads",
                new_callable=AsyncMock,
                return_value=threads,
            ),
        ):
            config = _make_config()
            result = asyncio.run(run_pipeline("test_vid", config))

            assert result.video.video_id == "test_vid"
            assert result.video.url == "https://www.youtube.com/watch?v=test_vid"
            assert len(result.items) == 3
            assert len(result.topic_threads) == 1
            assert result.classification.categories == [VideoCategory.TUTORIAL]
            assert result.audit.model_id == "gpt-4o-mini"
            assert result.audit.yt_factify_version is not None
            assert len(result.audit.segment_hashes) == 1

            mock_fetch.assert_called_once_with("test_vid", config)

    def test_transcript_fetch_failure(self) -> None:
        with patch(
            "yt_factify.pipeline.fetch_transcript",
            side_effect=RuntimeError("Network error"),
        ):
            config = _make_config()
            with pytest.raises(PipelineError, match="fetch/normalize"):
                asyncio.run(run_pipeline("test_vid", config))

    def test_classification_failure(self) -> None:
        raw = _make_raw_transcript()
        transcript = _make_normalized_transcript()
        segments = _make_segments()
        modules = _make_builtin_modules()

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
                return_value=modules,
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM down"),
            ),
        ):
            config = _make_config()
            with pytest.raises(PipelineError, match="classify"):
                asyncio.run(run_pipeline("test_vid", config))

    def test_extraction_failure(self) -> None:
        raw = _make_raw_transcript()
        transcript = _make_normalized_transcript()
        segments = _make_segments()
        classification = _make_classification()
        modules = _make_builtin_modules()

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
                return_value=modules,
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Extraction failed"),
            ),
        ):
            config = _make_config()
            with pytest.raises(PipelineError, match="extract"):
                asyncio.run(run_pipeline("test_vid", config))

    def test_validation_failure(self) -> None:
        raw = _make_raw_transcript()
        transcript = _make_normalized_transcript()
        segments = _make_segments()
        classification = _make_classification()
        extracted = _make_extracted_items()
        modules = _make_builtin_modules()

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
                return_value=modules,
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=extracted,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                side_effect=RuntimeError("Validation error"),
            ),
        ):
            config = _make_config()
            with pytest.raises(PipelineError, match="validate"):
                asyncio.run(run_pipeline("test_vid", config))

    def test_audit_bundle_complete(self) -> None:
        raw = _make_raw_transcript()
        transcript = _make_normalized_transcript()
        segments = _make_segments()
        classification = _make_classification()
        extracted = _make_extracted_items()
        assessed = _make_assessed_items()
        threads = _make_topic_threads()
        modules = _make_builtin_modules()
        validation = _make_validation_result(extracted)

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
                return_value=modules,
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=extracted,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                return_value=assessed,
            ),
            patch(
                "yt_factify.pipeline.cluster_topic_threads",
                new_callable=AsyncMock,
                return_value=threads,
            ),
        ):
            config = _make_config()
            result = asyncio.run(run_pipeline("test_vid", config))

            audit = result.audit
            assert audit.model_id == "gpt-4o-mini"
            assert audit.yt_factify_version is not None
            assert audit.processing_timestamp is not None
            assert len(audit.segment_hashes) == 1
            assert audit.segment_hashes[0] == "seg_hash"
            assert audit.prompt_templates_hash == "seg_hash"

    def test_custom_modules_dir(self, tmp_path: MagicMock) -> None:
        """When modules_dir is set, custom modules are loaded."""
        raw = _make_raw_transcript()
        transcript = _make_normalized_transcript()
        segments = _make_segments()
        classification = _make_classification()
        extracted = _make_extracted_items()
        assessed = _make_assessed_items()
        threads = _make_topic_threads()
        modules = _make_builtin_modules()
        validation = _make_validation_result(extracted)

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
                return_value=modules,
            ),
            patch(
                "yt_factify.pipeline.load_belief_modules",
                return_value=[],
            ) as mock_load,
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=extracted,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                return_value=assessed,
            ),
            patch(
                "yt_factify.pipeline.cluster_topic_threads",
                new_callable=AsyncMock,
                return_value=threads,
            ),
        ):
            config = _make_config(modules_dir="/custom/modules")
            asyncio.run(run_pipeline("test_vid", config))
            mock_load.assert_called_once()

    def test_credibility_failure(self) -> None:
        raw = _make_raw_transcript()
        transcript = _make_normalized_transcript()
        segments = _make_segments()
        classification = _make_classification()
        extracted = _make_extracted_items()
        modules = _make_builtin_modules()
        validation = _make_validation_result(extracted)

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
                return_value=modules,
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=extracted,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Credibility failed"),
            ),
        ):
            config = _make_config()
            with pytest.raises(PipelineError, match="credibility"):
                asyncio.run(run_pipeline("test_vid", config))

    def test_topic_threading_failure(self) -> None:
        raw = _make_raw_transcript()
        transcript = _make_normalized_transcript()
        segments = _make_segments()
        classification = _make_classification()
        extracted = _make_extracted_items()
        assessed = _make_assessed_items()
        modules = _make_builtin_modules()
        validation = _make_validation_result(extracted)

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
                return_value=modules,
            ),
            patch(
                "yt_factify.pipeline.classify_video",
                new_callable=AsyncMock,
                return_value=classification,
            ),
            patch(
                "yt_factify.pipeline.extract_items",
                new_callable=AsyncMock,
                return_value=extracted,
            ),
            patch(
                "yt_factify.pipeline.validate_items",
                return_value=validation,
            ),
            patch(
                "yt_factify.pipeline.assess_credibility",
                new_callable=AsyncMock,
                return_value=assessed,
            ),
            patch(
                "yt_factify.pipeline.cluster_topic_threads",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Threading failed"),
            ),
        ):
            config = _make_config()
            with pytest.raises(PipelineError, match="topic threads"):
                asyncio.run(run_pipeline("test_vid", config))
