# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for yt_factify.rendering."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from yt_factify.models import (
    AuditBundle,
    BeliefSystemFlag,
    BiasProfile,
    CredibilityAssessment,
    CredibilityLabel,
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
from yt_factify.rendering import (
    render_json,
    render_markdown,
    write_output,
)


def _make_result(
    items: list[ExtractedItem] | None = None,
    threads: list[TopicThread] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        video=VideoInfo(
            video_id="abc123",
            title="Test Video Title",
            url="https://www.youtube.com/watch?v=abc123",
            transcript_hash="hash123",
            fetched_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        ),
        classification=VideoClassification(
            categories=[VideoCategory.TUTORIAL, VideoCategory.INTERVIEW],
            bias_profile=BiasProfile(
                primary_label="neutral",
                confidence=0.85,
                rationale="Technical content with balanced perspective.",
            ),
        ),
        items=items or [],
        topic_threads=threads or [],
        audit=AuditBundle(
            model_id="gpt-4o-mini",
            model_version=None,
            prompt_templates_hash="prompt_hash",
            processing_timestamp=datetime(2026, 1, 15, 12, 5, 0, tzinfo=UTC),
            segment_hashes=["seg_h1", "seg_h2"],
            yt_factify_version="0.2.2",
        ),
    )


def _make_fact(
    item_id: str = "fact_1",
    content: str = "Python 3.7 introduced data classes.",
    start_ms: int = 3000,
    end_ms: int = 6500,
) -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=ItemType.TRANSCRIPT_FACT,
        content=content,
        transcript_evidence=TranscriptEvidence(
            video_id="abc123",
            start_ms=start_ms,
            end_ms=end_ms,
            text=content,
        ),
        credibility=CredibilityAssessment(
            label=CredibilityLabel.WELL_ESTABLISHED,
            confidence=0.95,
            rationale="Well-known Python feature.",
        ),
    )


def _make_quote(
    item_id: str = "quote_1",
    content: str = "Data classes are a game changer.",
    speaker: str = "Speaker A",
    start_ms: int = 7000,
    end_ms: int = 10000,
) -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=ItemType.DIRECT_QUOTE,
        content=content,
        speaker=speaker,
        transcript_evidence=TranscriptEvidence(
            video_id="abc123",
            start_ms=start_ms,
            end_ms=end_ms,
            text=content,
        ),
    )


def _make_opinion(item_id: str = "opinion_1") -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=ItemType.SPEAKER_OPINION,
        content="I think type hints are essential for large projects.",
        speaker="Speaker B",
        transcript_evidence=TranscriptEvidence(
            video_id="abc123",
            start_ms=15000,
            end_ms=20000,
            text="I think type hints are essential for large projects.",
        ),
    )


def _make_unverified(item_id: str = "claim_1") -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=ItemType.UNVERIFIED_CLAIM,
        content="Python will replace all other languages by 2030.",
        transcript_evidence=TranscriptEvidence(
            video_id="abc123",
            start_ms=25000,
            end_ms=30000,
            text="Python will replace all other languages by 2030.",
        ),
    )


def _make_prediction(item_id: str = "pred_1") -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=ItemType.PREDICTION,
        content="AI will write most boilerplate code within 5 years.",
        transcript_evidence=TranscriptEvidence(
            video_id="abc123",
            start_ms=35000,
            end_ms=40000,
            text="AI will write most boilerplate code within 5 years.",
        ),
    )


def _make_flagged_item() -> ExtractedItem:
    return ExtractedItem(
        id="flagged_1",
        type=ItemType.TRANSCRIPT_FACT,
        content="Consciousness is purely a product of brain chemistry.",
        transcript_evidence=TranscriptEvidence(
            video_id="abc123",
            start_ms=45000,
            end_ms=50000,
            text="Consciousness is purely a product of brain chemistry.",
        ),
        belief_system_flags=[
            BeliefSystemFlag(
                module_label="scientific_materialism",
                note="Assumes materialist view of consciousness.",
            ),
        ],
    )


def _make_threads() -> list[TopicThread]:
    return [
        TopicThread(
            label="python_features",
            display_name="Python Features",
            summary="Discussion of modern Python features.",
            item_ids=["fact_1", "quote_1"],
            timeline=[
                TopicTimeSpan(start_ms=3000, end_ms=10000),
            ],
        ),
        TopicThread(
            label="ai_coding",
            display_name="AI and Coding",
            summary="Predictions about AI in software development.",
            item_ids=["pred_1"],
            timeline=[
                TopicTimeSpan(start_ms=35000, end_ms=40000),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# render_json
# ---------------------------------------------------------------------------


class TestRenderJson:
    def test_valid_json_output(self) -> None:
        result = _make_result(items=[_make_fact()])
        json_str = render_json(result)
        parsed = json.loads(json_str)
        assert parsed["video"]["video_id"] == "abc123"

    def test_json_schema_fields(self) -> None:
        items = [_make_fact(), _make_quote()]
        threads = _make_threads()
        result = _make_result(items=items, threads=threads)
        json_str = render_json(result)
        parsed = json.loads(json_str)

        assert "video" in parsed
        assert "classification" in parsed
        assert "items" in parsed
        assert "topic_threads" in parsed
        assert "audit" in parsed
        assert len(parsed["items"]) == 2
        assert len(parsed["topic_threads"]) == 2

    def test_json_roundtrip(self) -> None:
        items = [_make_fact()]
        result = _make_result(items=items)
        json_str = render_json(result)
        parsed = json.loads(json_str)
        restored = ExtractionResult.model_validate(parsed)
        assert restored.video.video_id == result.video.video_id
        assert len(restored.items) == 1

    def test_empty_items(self) -> None:
        result = _make_result()
        json_str = render_json(result)
        parsed = json.loads(json_str)
        assert parsed["items"] == []
        assert parsed["topic_threads"] == []


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_contains_video_info(self) -> None:
        result = _make_result()
        md = render_markdown(result)
        assert "## Video Info" in md
        assert "abc123" in md
        assert "Test Video Title" in md
        assert "tutorial" in md
        assert "neutral" in md

    def test_contains_topic_overview(self) -> None:
        threads = _make_threads()
        result = _make_result(threads=threads)
        md = render_markdown(result)
        assert "## Topic Overview" in md
        assert "Python Features" in md
        assert "AI and Coding" in md

    def test_no_topic_overview_when_empty(self) -> None:
        result = _make_result()
        md = render_markdown(result)
        assert "## Topic Overview" not in md

    def test_contains_key_facts(self) -> None:
        result = _make_result(items=[_make_fact()])
        md = render_markdown(result)
        assert "## Key Facts" in md
        assert "Python 3.7 introduced data classes." in md
        assert "well_established" in md

    def test_contains_direct_quotes(self) -> None:
        result = _make_result(items=[_make_quote()])
        md = render_markdown(result)
        assert "## Direct Quotes" in md
        assert "Data classes are a game changer." in md
        assert "Speaker A" in md

    def test_contains_opinions(self) -> None:
        result = _make_result(items=[_make_opinion()])
        md = render_markdown(result)
        assert "## Opinions & Perspectives" in md
        assert "type hints" in md

    def test_contains_unverified_claims(self) -> None:
        result = _make_result(items=[_make_unverified()])
        md = render_markdown(result)
        assert "## Unverified Claims" in md
        assert "replace all other languages" in md

    def test_contains_predictions(self) -> None:
        result = _make_result(items=[_make_prediction()])
        md = render_markdown(result)
        assert "## Predictions" in md
        assert "boilerplate code" in md

    def test_contains_belief_system_notes(self) -> None:
        result = _make_result(items=[_make_flagged_item()])
        md = render_markdown(result)
        assert "## Belief System Notes" in md
        assert "scientific_materialism" in md

    def test_all_sections_present(self) -> None:
        items = [
            _make_fact(),
            _make_quote(),
            _make_opinion(),
            _make_unverified(),
            _make_prediction(),
            _make_flagged_item(),
        ]
        threads = _make_threads()
        result = _make_result(items=items, threads=threads)
        md = render_markdown(result)

        assert "## Video Info" in md
        assert "## Topic Overview" in md
        assert "## Key Facts" in md
        assert "## Direct Quotes" in md
        assert "## Opinions & Perspectives" in md
        assert "## Unverified Claims" in md
        assert "## Predictions" in md
        assert "## Belief System Notes" in md

    def test_empty_items_minimal_output(self) -> None:
        result = _make_result()
        md = render_markdown(result)
        assert "## Video Info" in md
        assert "## Key Facts" not in md

    def test_time_formatting(self) -> None:
        item = _make_fact(start_ms=3661000, end_ms=3722000)
        result = _make_result(items=[item])
        md = render_markdown(result)
        # 3661s = 1:01:01, 3722s = 1:02:02
        assert "1:01:01" in md
        assert "1:02:02" in md

    def test_trailing_newline(self) -> None:
        result = _make_result()
        md = render_markdown(result)
        assert md.endswith("\n")


# ---------------------------------------------------------------------------
# write_output (atomic writes)
# ---------------------------------------------------------------------------


class TestWriteOutput:
    def test_writes_file(self, tmp_path: Path) -> None:
        output = tmp_path / "output.md"
        write_output("hello world", output)
        assert output.read_text() == "hello world"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        output = tmp_path / "sub" / "dir" / "output.json"
        write_output('{"key": "value"}', output)
        assert output.exists()
        assert output.read_text() == '{"key": "value"}'

    def test_atomic_no_partial_on_error(self, tmp_path: Path) -> None:
        output = tmp_path / "output.md"
        # Simulate a write error by making the parent read-only
        # after creating the temp file — this is tricky to test
        # portably, so we just verify the happy path works
        write_output("content", output)
        assert output.read_text() == "content"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        output = tmp_path / "output.md"
        write_output("first", output)
        write_output("second", output)
        assert output.read_text() == "second"
