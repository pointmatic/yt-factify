# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for yt_factify.prompts."""

from __future__ import annotations

from yt_factify.models import (
    BeliefSystemModule,
    ExtractedItem,
    ItemType,
    NormalizedSegment,
    NormalizedTranscript,
    TranscriptEvidence,
    TranscriptSegment,
    VideoCategory,
)
from yt_factify.prompts import hash_prompts
from yt_factify.prompts.classification import (
    build_bias_messages,
    build_classification_messages,
)
from yt_factify.prompts.credibility import build_credibility_messages
from yt_factify.prompts.extraction import build_extraction_messages


def _make_segment(
    text: str = "Hello world",
    start_ms: int = 0,
    end_ms: int = 5000,
) -> TranscriptSegment:
    return TranscriptSegment(
        text=text,
        start_ms=start_ms,
        end_ms=end_ms,
        hash="abc123",
        source_segment_indices=[0],
    )


def _make_transcript(
    video_id: str = "test123",
    text: str = "This is a test transcript about science and technology.",
) -> NormalizedTranscript:
    return NormalizedTranscript(
        video_id=video_id,
        full_text=text,
        hash="hash123",
        segments=[
            NormalizedSegment(text=text, start_ms=0, end_ms=10000, hash="seg_hash"),
        ],
    )


def _make_belief_module() -> BeliefSystemModule:
    return BeliefSystemModule(
        label="scientific_materialism",
        display_name="Scientific Materialism",
        description="A worldview grounded in empirical evidence and the scientific method.",
        core_assumptions=[
            "Observable, repeatable evidence is the gold standard for truth claims.",
            "Supernatural explanations are outside the scope of scientific inquiry.",
        ],
        example_claims=["Evolution is a well-established scientific theory."],
    )


def _make_item(item_id: str = "item_1") -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=ItemType.TRANSCRIPT_FACT,
        content="The Earth orbits the Sun.",
        speaker="narrator",
        transcript_evidence=TranscriptEvidence(
            video_id="test123",
            start_ms=0,
            end_ms=5000,
            text="The Earth orbits the Sun.",
        ),
    )


# ---------------------------------------------------------------------------
# hash_prompts
# ---------------------------------------------------------------------------


class TestHashPrompts:
    def test_deterministic(self) -> None:
        h1 = hash_prompts("prompt A", "prompt B")
        h2 = hash_prompts("prompt A", "prompt B")
        assert h1 == h2

    def test_different_inputs(self) -> None:
        h1 = hash_prompts("prompt A")
        h2 = hash_prompts("prompt B")
        assert h1 != h2

    def test_returns_hex_sha256(self) -> None:
        h = hash_prompts("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_order_matters(self) -> None:
        h1 = hash_prompts("A", "B")
        h2 = hash_prompts("B", "A")
        assert h1 != h2


# ---------------------------------------------------------------------------
# Extraction prompts
# ---------------------------------------------------------------------------


class TestBuildExtractionMessages:
    def test_basic_structure(self) -> None:
        seg = _make_segment()
        msgs = build_extraction_messages(seg, video_id="vid1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_system_prompt_not_empty(self) -> None:
        seg = _make_segment()
        msgs = build_extraction_messages(seg, video_id="vid1")
        assert len(msgs[0]["content"]) > 100

    def test_user_prompt_contains_transcript(self) -> None:
        seg = _make_segment(text="Python is great")
        msgs = build_extraction_messages(seg, video_id="vid1")
        assert "Python is great" in msgs[1]["content"]

    def test_user_prompt_contains_video_id(self) -> None:
        seg = _make_segment()
        msgs = build_extraction_messages(seg, video_id="abc123")
        assert "abc123" in msgs[1]["content"]

    def test_user_prompt_contains_timestamps(self) -> None:
        seg = _make_segment(start_ms=1000, end_ms=5000)
        msgs = build_extraction_messages(seg, video_id="vid1")
        assert "1000" in msgs[1]["content"]
        assert "5000" in msgs[1]["content"]

    def test_categories_included(self) -> None:
        seg = _make_segment()
        msgs = build_extraction_messages(
            seg,
            video_id="vid1",
            categories=[VideoCategory.TUTORIAL, VideoCategory.INTERVIEW],
        )
        assert "tutorial" in msgs[0]["content"]
        assert "interview" in msgs[0]["content"]

    def test_belief_modules_included(self) -> None:
        seg = _make_segment()
        module = _make_belief_module()
        msgs = build_extraction_messages(
            seg,
            video_id="vid1",
            belief_modules=[module],
        )
        assert "Scientific Materialism" in msgs[0]["content"]
        assert "scientific_materialism" in msgs[0]["content"]

    def test_no_categories_no_section(self) -> None:
        seg = _make_segment()
        msgs = build_extraction_messages(seg, video_id="vid1")
        assert "Video Categories" not in msgs[0]["content"]

    def test_no_belief_modules_no_section(self) -> None:
        seg = _make_segment()
        msgs = build_extraction_messages(seg, video_id="vid1")
        assert "Belief/Value Systems" not in msgs[0]["content"]

    def test_item_types_in_system_prompt(self) -> None:
        seg = _make_segment()
        msgs = build_extraction_messages(seg, video_id="vid1")
        system = msgs[0]["content"]
        assert "direct_quote" in system
        assert "transcript_fact" in system
        assert "general_knowledge" in system
        assert "speaker_opinion" in system
        assert "unverified_claim" in system
        assert "prediction" in system


# ---------------------------------------------------------------------------
# Classification prompts
# ---------------------------------------------------------------------------


class TestBuildClassificationMessages:
    def test_basic_structure(self) -> None:
        transcript = _make_transcript()
        msgs = build_classification_messages(transcript)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_system_prompt_contains_categories(self) -> None:
        transcript = _make_transcript()
        msgs = build_classification_messages(transcript)
        system = msgs[0]["content"]
        assert "news" in system
        assert "tutorial" in system
        assert "entertainment" in system

    def test_user_prompt_contains_transcript(self) -> None:
        transcript = _make_transcript(text="AI is transforming the world")
        msgs = build_classification_messages(transcript)
        assert "AI is transforming the world" in msgs[1]["content"]

    def test_user_prompt_contains_video_id(self) -> None:
        transcript = _make_transcript(video_id="xyz789")
        msgs = build_classification_messages(transcript)
        assert "xyz789" in msgs[1]["content"]


class TestBuildBiasMessages:
    def test_basic_structure(self) -> None:
        transcript = _make_transcript()
        msgs = build_bias_messages(transcript, categories=[VideoCategory.NEWS])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_categories_in_user_prompt(self) -> None:
        transcript = _make_transcript()
        msgs = build_bias_messages(
            transcript,
            categories=[VideoCategory.NEWS, VideoCategory.INTERVIEW],
        )
        assert "news" in msgs[1]["content"]
        assert "interview" in msgs[1]["content"]

    def test_system_prompt_covers_bias_types(self) -> None:
        transcript = _make_transcript()
        msgs = build_bias_messages(transcript, categories=[VideoCategory.NEWS])
        system = msgs[0]["content"]
        assert "Political bias" in system
        assert "Commercial bias" in system
        assert "Sensationalism" in system


# ---------------------------------------------------------------------------
# Credibility prompts
# ---------------------------------------------------------------------------


class TestBuildCredibilityMessages:
    def test_basic_structure(self) -> None:
        item = _make_item()
        msgs = build_credibility_messages([item])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_system_prompt_contains_labels(self) -> None:
        item = _make_item()
        msgs = build_credibility_messages([item])
        system = msgs[0]["content"]
        assert "well_established" in system
        assert "credible" in system
        assert "disputed" in system
        assert "dubious" in system
        assert "unassessable" in system

    def test_user_prompt_contains_item(self) -> None:
        item = _make_item(item_id="fact_42")
        msgs = build_credibility_messages([item])
        user = msgs[1]["content"]
        assert "fact_42" in user
        assert "The Earth orbits the Sun." in user

    def test_multiple_items(self) -> None:
        items = [_make_item("item_1"), _make_item("item_2")]
        msgs = build_credibility_messages(items)
        user = msgs[1]["content"]
        assert "item_1" in user
        assert "item_2" in user

    def test_belief_modules_included(self) -> None:
        item = _make_item()
        module = _make_belief_module()
        msgs = build_credibility_messages([item], belief_modules=[module])
        system = msgs[0]["content"]
        assert "Scientific Materialism" in system
        assert "scientific_materialism" in system

    def test_no_belief_modules_no_section(self) -> None:
        item = _make_item()
        msgs = build_credibility_messages([item])
        assert "Active Belief/Value Systems" not in msgs[0]["content"]

    def test_speaker_included_when_present(self) -> None:
        item = _make_item()
        msgs = build_credibility_messages([item])
        assert "narrator" in msgs[1]["content"]
