# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for yt_factify.classification."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_factify.classification import (
    ClassificationError,
    CredibilityError,
    _parse_classification,
    _parse_credibility_assessments,
    assess_credibility,
    classify_video,
)
from yt_factify.config import AppConfig
from yt_factify.models import (
    BeliefSystemModule,
    CredibilityLabel,
    ExtractedItem,
    ItemType,
    NormalizedSegment,
    NormalizedTranscript,
    TranscriptEvidence,
    VideoCategory,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm_responses"


def _make_config(**overrides: object) -> AppConfig:
    defaults: dict[str, object] = {
        "model": "gpt-4o-mini",
        "max_retries": 2,
    }
    defaults.update(overrides)
    return AppConfig(**defaults)  # type: ignore[arg-type]


def _make_transcript(
    video_id: str = "test_vid",
    num_segments: int = 3,
) -> NormalizedTranscript:
    texts = [
        "Welcome to this tutorial on Python data classes.",
        "Data classes were introduced in Python 3.7.",
        "They reduce boilerplate code significantly.",
    ]
    segments = []
    for i in range(num_segments):
        text = texts[i % len(texts)]
        segments.append(
            NormalizedSegment(
                text=text,
                start_ms=i * 5000,
                end_ms=(i + 1) * 5000,
                hash=f"h{i}",
            )
        )
    full_text = " ".join(seg.text for seg in segments)
    return NormalizedTranscript(
        video_id=video_id,
        full_text=full_text,
        hash="full_hash",
        segments=segments,
    )


def _make_long_transcript(num_segments: int = 20) -> NormalizedTranscript:
    """Create a long transcript to test sampling logic."""
    # Each segment ~500 chars so 20 segments > 8000 char threshold
    filler = "This is filler content about various topics. " * 10
    segments = []
    for i in range(num_segments):
        segments.append(
            NormalizedSegment(
                text=f"Segment {i}: {filler.strip()}",
                start_ms=i * 5000,
                end_ms=(i + 1) * 5000,
                hash=f"h{i}",
            )
        )
    full_text = " ".join(seg.text for seg in segments)
    return NormalizedTranscript(
        video_id="long_vid",
        full_text=full_text,
        hash="long_hash",
        segments=segments,
    )


def _make_item(item_id: str = "item_1") -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=ItemType.TRANSCRIPT_FACT,
        content="Data classes were introduced in Python 3.7.",
        transcript_evidence=TranscriptEvidence(
            video_id="test_vid",
            start_ms=5000,
            end_ms=10000,
            text="Data classes were introduced in Python 3.7.",
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
# _parse_classification
# ---------------------------------------------------------------------------


class TestParseClassification:
    def test_valid_response(self) -> None:
        raw = (FIXTURES_DIR / "classification_valid.json").read_text()
        result = _parse_classification(raw)
        assert VideoCategory.TUTORIAL in result.categories
        assert VideoCategory.INTERVIEW in result.categories
        assert result.bias_profile.primary_label == "neutral"
        assert result.bias_profile.confidence == 0.85

    def test_unknown_category_falls_back_to_other(self) -> None:
        raw = json.dumps(
            {
                "categories": ["unknown_category"],
                "bias_profile": {
                    "primary_label": "neutral",
                    "confidence": 0.5,
                    "rationale": "test",
                },
            }
        )
        result = _parse_classification(raw)
        assert result.categories == [VideoCategory.OTHER]

    def test_empty_categories_defaults_to_other(self) -> None:
        raw = json.dumps(
            {
                "categories": [],
                "bias_profile": {
                    "primary_label": "neutral",
                    "confidence": 0.5,
                    "rationale": "test",
                },
            }
        )
        result = _parse_classification(raw)
        assert result.categories == [VideoCategory.OTHER]

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_classification("not json")

    def test_non_object_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected JSON object"):
            _parse_classification("[]")

    def test_markdown_fences_stripped(self) -> None:
        raw = (FIXTURES_DIR / "classification_valid.json").read_text()
        fenced = f"```json\n{raw}\n```"
        result = _parse_classification(fenced)
        assert VideoCategory.TUTORIAL in result.categories


# ---------------------------------------------------------------------------
# _parse_credibility_assessments
# ---------------------------------------------------------------------------


class TestParseCredibilityAssessments:
    def test_valid_response(self) -> None:
        raw = (FIXTURES_DIR / "credibility_valid.json").read_text()
        items = [_make_item("item_1"), _make_item("item_2"), _make_item("item_3")]
        assessments = _parse_credibility_assessments(raw, items)
        assert len(assessments) == 3
        assert assessments["item_1"].label == CredibilityLabel.WELL_ESTABLISHED
        assert assessments["item_2"].label == CredibilityLabel.CREDIBLE
        assert assessments["item_3"].label == CredibilityLabel.UNASSESSABLE

    def test_unknown_item_id_skipped(self) -> None:
        raw = json.dumps(
            [
                {
                    "item_id": "nonexistent",
                    "label": "credible",
                    "confidence": 0.5,
                    "rationale": "test",
                }
            ]
        )
        items = [_make_item("item_1")]
        assessments = _parse_credibility_assessments(raw, items)
        assert len(assessments) == 0

    def test_invalid_label_skipped(self) -> None:
        raw = json.dumps(
            [
                {
                    "item_id": "item_1",
                    "label": "totally_invalid_label",
                    "confidence": 0.5,
                    "rationale": "test",
                }
            ]
        )
        items = [_make_item("item_1")]
        assessments = _parse_credibility_assessments(raw, items)
        assert len(assessments) == 0

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_credibility_assessments("not json", [])

    def test_non_array_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected JSON array"):
            _parse_credibility_assessments("{}", [])


# ---------------------------------------------------------------------------
# classify_video (mocked LLM)
# ---------------------------------------------------------------------------


class TestClassifyVideo:
    def test_successful_classification(self) -> None:
        fixture = (FIXTURES_DIR / "classification_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            transcript = _make_transcript()
            result = asyncio.run(classify_video(transcript, config))

            assert VideoCategory.TUTORIAL in result.categories
            assert result.bias_profile.primary_label == "neutral"
            mock_litellm.acompletion.assert_called_once()

    def test_retry_on_malformed_json(self) -> None:
        bad_response = _mock_llm_response("not json")
        fixture = (FIXTURES_DIR / "classification_valid.json").read_text()
        good_response = _mock_llm_response(fixture)

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=[bad_response, good_response])

            config = _make_config()
            transcript = _make_transcript()
            result = asyncio.run(classify_video(transcript, config))

            assert VideoCategory.TUTORIAL in result.categories
            assert mock_litellm.acompletion.call_count == 2

    def test_persistent_failure_raises(self) -> None:
        bad_response = _mock_llm_response("not json")

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=bad_response)

            config = _make_config()
            transcript = _make_transcript()
            with pytest.raises(ClassificationError, match="Failed to classify"):
                asyncio.run(classify_video(transcript, config))

    def test_long_transcript_sampling(self) -> None:
        """Verify that long transcripts are sampled (prompt is shorter)."""
        fixture = (FIXTURES_DIR / "classification_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            transcript = _make_long_transcript(num_segments=20)
            result = asyncio.run(classify_video(transcript, config))

            # Should still succeed
            assert result.categories is not None

            # Check that the user message doesn't contain all segments
            call_args = mock_litellm.acompletion.call_args
            messages = call_args.kwargs["messages"]
            user_content = messages[1]["content"]
            # With 20 segments, sampling should use [...] separator
            assert "[...]" in user_content


# ---------------------------------------------------------------------------
# assess_credibility (mocked LLM)
# ---------------------------------------------------------------------------


class TestAssessCredibility:
    def test_successful_assessment(self) -> None:
        fixture = (FIXTURES_DIR / "credibility_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            items = [
                _make_item("item_1"),
                _make_item("item_2"),
                _make_item("item_3"),
            ]
            result = asyncio.run(assess_credibility(items, [], config))

            assert len(result) == 3
            assert result[0].credibility is not None
            assert result[0].credibility.label == CredibilityLabel.WELL_ESTABLISHED
            mock_litellm.acompletion.assert_called_once()

    def test_empty_items_returns_empty(self) -> None:
        config = _make_config()
        result = asyncio.run(assess_credibility([], [], config))
        assert result == []

    def test_partial_assessment(self) -> None:
        """Items without assessments retain credibility=None."""
        raw = json.dumps(
            [
                {
                    "item_id": "item_1",
                    "label": "credible",
                    "confidence": 0.8,
                    "rationale": "test",
                    "relevant_belief_systems": [],
                }
            ]
        )
        mock_response = _mock_llm_response(raw)

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            items = [_make_item("item_1"), _make_item("item_2")]
            result = asyncio.run(assess_credibility(items, [], config))

            assert len(result) == 2
            assert result[0].credibility is not None
            assert result[1].credibility is None

    def test_retry_on_malformed_json(self) -> None:
        bad_response = _mock_llm_response("not json")
        fixture = (FIXTURES_DIR / "credibility_valid.json").read_text()
        good_response = _mock_llm_response(fixture)

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=[bad_response, good_response])

            config = _make_config()
            items = [
                _make_item("item_1"),
                _make_item("item_2"),
                _make_item("item_3"),
            ]
            result = asyncio.run(assess_credibility(items, [], config))
            assert len(result) == 3
            assert mock_litellm.acompletion.call_count == 2

    def test_persistent_failure_raises(self) -> None:
        bad_response = _mock_llm_response("not json")

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=bad_response)

            config = _make_config()
            items = [_make_item()]
            with pytest.raises(CredibilityError, match="Failed to assess"):
                asyncio.run(assess_credibility(items, [], config))

    def test_belief_modules_passed_to_prompt(self) -> None:
        fixture = (FIXTURES_DIR / "credibility_valid.json").read_text()
        mock_response = _mock_llm_response(fixture)

        module = BeliefSystemModule(
            label="test_module",
            display_name="Test Module",
            description="A test worldview",
            core_assumptions=["Assumption 1"],
        )

        with patch("yt_factify.llm.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            config = _make_config()
            items = [
                _make_item("item_1"),
                _make_item("item_2"),
                _make_item("item_3"),
            ]
            asyncio.run(assess_credibility(items, [module], config))

            call_args = mock_litellm.acompletion.call_args
            messages = call_args.kwargs["messages"]
            system_content = messages[0]["content"]
            assert "Test Module" in system_content
