# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for yt_factify.models."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from yt_factify.models import (
    AuditBundle,
    BeliefSystemFlag,
    BeliefSystemModule,
    BiasProfile,
    CredibilityAssessment,
    CredibilityLabel,
    ExtractedItem,
    ExtractionResult,
    ItemType,
    NormalizedSegment,
    NormalizedTranscript,
    QuoteMismatchBehavior,
    RawTranscript,
    TranscriptEvidence,
    TranscriptSegment,
    TranscriptSegmentRaw,
    ValidationResult,
    VideoCategory,
    VideoClassification,
    VideoInfo,
)

# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestItemType:
    def test_values(self) -> None:
        assert ItemType.DIRECT_QUOTE == "direct_quote"
        assert ItemType.TRANSCRIPT_FACT == "transcript_fact"
        assert ItemType.GENERAL_KNOWLEDGE == "general_knowledge"
        assert ItemType.SPEAKER_OPINION == "speaker_opinion"
        assert ItemType.UNVERIFIED_CLAIM == "unverified_claim"
        assert ItemType.PREDICTION == "prediction"

    def test_member_count(self) -> None:
        assert len(ItemType) == 6


class TestCredibilityLabel:
    def test_values(self) -> None:
        assert CredibilityLabel.WELL_ESTABLISHED == "well_established"
        assert CredibilityLabel.CREDIBLE == "credible"
        assert CredibilityLabel.DISPUTED == "disputed"
        assert CredibilityLabel.DUBIOUS == "dubious"
        assert CredibilityLabel.UNASSESSABLE == "unassessable"

    def test_member_count(self) -> None:
        assert len(CredibilityLabel) == 5


class TestVideoCategory:
    def test_values(self) -> None:
        assert VideoCategory.NEWS == "news"
        assert VideoCategory.ENTERTAINMENT == "entertainment"
        assert VideoCategory.MUSIC_VIDEO == "music_video"
        assert VideoCategory.COMEDY_SATIRE == "comedy_satire"
        assert VideoCategory.INTERVIEW == "interview"
        assert VideoCategory.DOCUMENTARY == "documentary"
        assert VideoCategory.TUTORIAL == "tutorial"
        assert VideoCategory.OPINION_EDITORIAL == "opinion_editorial"
        assert VideoCategory.POLITICAL_SPEECH == "political_speech"
        assert VideoCategory.PANEL_DISCUSSION == "panel_discussion"
        assert VideoCategory.OTHER == "other"

    def test_member_count(self) -> None:
        assert len(VideoCategory) == 11


class TestQuoteMismatchBehavior:
    def test_values(self) -> None:
        assert QuoteMismatchBehavior.REJECT == "reject"
        assert QuoteMismatchBehavior.DOWNGRADE == "downgrade"

    def test_member_count(self) -> None:
        assert len(QuoteMismatchBehavior) == 2


# ---------------------------------------------------------------------------
# Transcript Model Tests
# ---------------------------------------------------------------------------


class TestTranscriptSegmentRaw:
    def test_valid(self) -> None:
        seg = TranscriptSegmentRaw(text="hello world", start_ms=0, end_ms=5000)
        assert seg.text == "hello world"
        assert seg.start_ms == 0
        assert seg.end_ms == 5000

    def test_missing_field(self) -> None:
        with pytest.raises(ValueError):
            TranscriptSegmentRaw(text="hello", start_ms=0)  # type: ignore[call-arg]


class TestRawTranscript:
    def test_valid(self) -> None:
        raw = RawTranscript(
            video_id="abc123",
            segments=[TranscriptSegmentRaw(text="hi", start_ms=0, end_ms=1000)],
            language="en",
        )
        assert raw.video_id == "abc123"
        assert len(raw.segments) == 1
        assert raw.language == "en"

    def test_language_optional(self) -> None:
        raw = RawTranscript(video_id="abc123", segments=[])
        assert raw.language is None

    def test_empty_segments(self) -> None:
        raw = RawTranscript(video_id="abc123", segments=[])
        assert raw.segments == []


class TestNormalizedSegment:
    def test_valid(self) -> None:
        seg = NormalizedSegment(
            text="normalized text",
            start_ms=0,
            end_ms=5000,
            hash="abc123hash",
        )
        assert seg.hash == "abc123hash"


class TestNormalizedTranscript:
    def test_valid(self) -> None:
        nt = NormalizedTranscript(
            video_id="v1",
            full_text="full text here",
            hash="fullhash",
            segments=[
                NormalizedSegment(text="seg1", start_ms=0, end_ms=5000, hash="h1"),
            ],
        )
        assert nt.video_id == "v1"
        assert nt.full_text == "full text here"
        assert len(nt.segments) == 1


class TestTranscriptSegment:
    def test_valid(self) -> None:
        seg = TranscriptSegment(
            text="combined text",
            start_ms=0,
            end_ms=45000,
            hash="seghash",
            source_segment_indices=[0, 1, 2],
        )
        assert seg.source_segment_indices == [0, 1, 2]


# ---------------------------------------------------------------------------
# Extraction Model Tests
# ---------------------------------------------------------------------------


def _make_evidence() -> TranscriptEvidence:
    return TranscriptEvidence(
        video_id="v1", start_ms=1000, end_ms=5000, text="some transcript text"
    )


class TestTranscriptEvidence:
    def test_valid(self) -> None:
        ev = _make_evidence()
        assert ev.video_id == "v1"
        assert ev.text == "some transcript text"


class TestBeliefSystemFlag:
    def test_valid(self) -> None:
        flag = BeliefSystemFlag(module_label="libertarian", note="assumes free market")
        assert flag.module_label == "libertarian"


class TestCredibilityAssessment:
    def test_valid(self) -> None:
        ca = CredibilityAssessment(
            label=CredibilityLabel.CREDIBLE,
            confidence=0.85,
            rationale="Well-sourced claim",
        )
        assert ca.label == CredibilityLabel.CREDIBLE
        assert ca.confidence == 0.85

    def test_confidence_too_high(self) -> None:
        with pytest.raises(ValueError):
            CredibilityAssessment(
                label=CredibilityLabel.CREDIBLE,
                confidence=1.5,
                rationale="bad",
            )

    def test_confidence_too_low(self) -> None:
        with pytest.raises(ValueError):
            CredibilityAssessment(
                label=CredibilityLabel.CREDIBLE,
                confidence=-0.1,
                rationale="bad",
            )

    def test_confidence_boundary_values(self) -> None:
        low = CredibilityAssessment(
            label=CredibilityLabel.UNASSESSABLE, confidence=0.0, rationale="min"
        )
        high = CredibilityAssessment(
            label=CredibilityLabel.WELL_ESTABLISHED, confidence=1.0, rationale="max"
        )
        assert low.confidence == 0.0
        assert high.confidence == 1.0

    def test_relevant_belief_systems_default(self) -> None:
        ca = CredibilityAssessment(label=CredibilityLabel.CREDIBLE, confidence=0.5, rationale="ok")
        assert ca.relevant_belief_systems == []


class TestExtractedItem:
    def test_valid_minimal(self) -> None:
        item = ExtractedItem(
            id="item-1",
            type=ItemType.DIRECT_QUOTE,
            content="The sky is blue.",
            transcript_evidence=_make_evidence(),
        )
        assert item.id == "item-1"
        assert item.type == ItemType.DIRECT_QUOTE
        assert item.speaker is None
        assert item.credibility is None
        assert item.belief_system_flags == []

    def test_valid_full(self) -> None:
        item = ExtractedItem(
            id="item-2",
            type=ItemType.SPEAKER_OPINION,
            content="I think this is great",
            speaker="John Doe",
            transcript_evidence=_make_evidence(),
            credibility=CredibilityAssessment(
                label=CredibilityLabel.UNASSESSABLE,
                confidence=0.5,
                rationale="Opinion",
            ),
            belief_system_flags=[
                BeliefSystemFlag(module_label="optimism", note="positive outlook")
            ],
        )
        assert item.speaker == "John Doe"
        assert item.credibility is not None
        assert len(item.belief_system_flags) == 1

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValueError):
            ExtractedItem(
                id="item-3",
                type=ItemType.TRANSCRIPT_FACT,
                content="fact",
                # missing transcript_evidence
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Classification Model Tests
# ---------------------------------------------------------------------------


class TestBiasProfile:
    def test_valid(self) -> None:
        bp = BiasProfile(
            primary_label="center-left",
            confidence=0.7,
            rationale="Leans progressive on social issues",
        )
        assert bp.primary_label == "center-left"
        assert bp.implicit_bias_notes == []

    def test_confidence_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            BiasProfile(primary_label="x", confidence=2.0, rationale="bad")


class TestVideoClassification:
    def test_valid(self) -> None:
        vc = VideoClassification(
            categories=[VideoCategory.NEWS, VideoCategory.INTERVIEW],
            bias_profile=BiasProfile(
                primary_label="neutral", confidence=0.9, rationale="balanced"
            ),
        )
        assert len(vc.categories) == 2
        assert vc.bias_profile.primary_label == "neutral"


# ---------------------------------------------------------------------------
# Belief System Module Tests
# ---------------------------------------------------------------------------


class TestBeliefSystemModule:
    def test_valid(self) -> None:
        mod = BeliefSystemModule(
            label="free_market",
            display_name="Free Market Economics",
            description="Assumes markets self-correct",
            core_assumptions=["Markets are efficient", "Minimal regulation is ideal"],
        )
        assert mod.label == "free_market"
        assert len(mod.core_assumptions) == 2
        assert mod.example_claims == []

    def test_missing_required(self) -> None:
        with pytest.raises(ValueError):
            BeliefSystemModule(
                label="x",
                display_name="X",
                # missing description and core_assumptions
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Output Model Tests
# ---------------------------------------------------------------------------


NOW = datetime.now(tz=UTC)


class TestVideoInfo:
    def test_valid(self) -> None:
        vi = VideoInfo(
            video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
            transcript_hash="sha256hash",
            fetched_at=NOW,
        )
        assert vi.video_id == "abc123"
        assert vi.title == "Test Video"

    def test_title_optional(self) -> None:
        vi = VideoInfo(
            video_id="abc123",
            url="https://youtube.com/watch?v=abc123",
            transcript_hash="sha256hash",
            fetched_at=NOW,
        )
        assert vi.title is None


class TestAuditBundle:
    def test_valid(self) -> None:
        ab = AuditBundle(
            model_id="gpt-4o",
            prompt_templates_hash="prompthash",
            processing_timestamp=NOW,
            segment_hashes=["h1", "h2"],
            yt_factify_version="0.0.3",
        )
        assert ab.model_id == "gpt-4o"
        assert ab.model_version is None
        assert len(ab.segment_hashes) == 2


class TestValidationResult:
    def test_valid(self) -> None:
        item = ExtractedItem(
            id="i1",
            type=ItemType.TRANSCRIPT_FACT,
            content="fact",
            transcript_evidence=_make_evidence(),
        )
        vr = ValidationResult(accepted=[item])
        assert len(vr.accepted) == 1
        assert vr.rejected == []
        assert vr.downgraded == []


class TestExtractionResult:
    def test_valid(self) -> None:
        result = ExtractionResult(
            video=VideoInfo(
                video_id="v1",
                url="https://youtube.com/watch?v=v1",
                transcript_hash="th",
                fetched_at=NOW,
            ),
            classification=VideoClassification(
                categories=[VideoCategory.TUTORIAL],
                bias_profile=BiasProfile(
                    primary_label="neutral",
                    confidence=0.95,
                    rationale="Educational content",
                ),
            ),
            items=[
                ExtractedItem(
                    id="i1",
                    type=ItemType.TRANSCRIPT_FACT,
                    content="Python is great",
                    transcript_evidence=_make_evidence(),
                )
            ],
            audit=AuditBundle(
                model_id="gpt-4o",
                prompt_templates_hash="ph",
                processing_timestamp=NOW,
                segment_hashes=["s1"],
                yt_factify_version="0.0.3",
            ),
        )
        assert result.video.video_id == "v1"
        assert len(result.items) == 1


# ---------------------------------------------------------------------------
# JSON Serialization Round-Trip Tests
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    def test_extracted_item_round_trip(self) -> None:
        item = ExtractedItem(
            id="rt-1",
            type=ItemType.DIRECT_QUOTE,
            content="Round trip test",
            speaker="Speaker A",
            transcript_evidence=_make_evidence(),
            credibility=CredibilityAssessment(
                label=CredibilityLabel.CREDIBLE,
                confidence=0.8,
                rationale="Solid source",
                relevant_belief_systems=["empiricism"],
            ),
            belief_system_flags=[
                BeliefSystemFlag(module_label="empiricism", note="evidence-based")
            ],
        )
        json_str = item.model_dump_json()
        parsed = json.loads(json_str)
        restored = ExtractedItem.model_validate(parsed)
        assert restored == item

    def test_extraction_result_round_trip(self) -> None:
        result = ExtractionResult(
            video=VideoInfo(
                video_id="v1",
                url="https://youtube.com/watch?v=v1",
                transcript_hash="th",
                fetched_at=NOW,
            ),
            classification=VideoClassification(
                categories=[VideoCategory.NEWS],
                bias_profile=BiasProfile(
                    primary_label="center",
                    confidence=0.6,
                    rationale="Mixed coverage",
                    implicit_bias_notes=["Omits opposing view"],
                ),
            ),
            items=[],
            audit=AuditBundle(
                model_id="claude-3",
                model_version="20240101",
                prompt_templates_hash="ph",
                processing_timestamp=NOW,
                segment_hashes=[],
                yt_factify_version="0.0.3",
            ),
        )
        json_str = result.model_dump_json()
        parsed = json.loads(json_str)
        restored = ExtractionResult.model_validate(parsed)
        assert restored == result

    def test_belief_system_module_round_trip(self) -> None:
        mod = BeliefSystemModule(
            label="test",
            display_name="Test Module",
            description="For testing",
            core_assumptions=["A1", "A2"],
            example_claims=["C1"],
        )
        json_str = mod.model_dump_json()
        parsed = json.loads(json_str)
        restored = BeliefSystemModule.model_validate(parsed)
        assert restored == mod
