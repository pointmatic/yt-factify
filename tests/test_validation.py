# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for yt_factify.validation."""

from __future__ import annotations

from yt_factify.config import AppConfig
from yt_factify.models import (
    ExtractedItem,
    ItemType,
    NormalizedSegment,
    NormalizedTranscript,
    QuoteMismatchBehavior,
    TranscriptEvidence,
)
from yt_factify.validation import (
    _check_timestamp_bounds,
    validate_items,
    verify_quote,
)


def _make_transcript() -> NormalizedTranscript:
    """Create a sample transcript for testing."""
    return NormalizedTranscript(
        video_id="test_vid",
        full_text=(
            "Welcome to this tutorial. "
            "Data classes were introduced in Python 3.7. "
            "They reduce boilerplate code significantly. "
            "Let me show you an example."
        ),
        hash="test_hash",
        segments=[
            NormalizedSegment(
                text="Welcome to this tutorial.",
                start_ms=0,
                end_ms=3000,
                hash="h1",
            ),
            NormalizedSegment(
                text="Data classes were introduced in Python 3.7.",
                start_ms=3000,
                end_ms=6500,
                hash="h2",
            ),
            NormalizedSegment(
                text="They reduce boilerplate code significantly.",
                start_ms=6500,
                end_ms=10000,
                hash="h3",
            ),
            NormalizedSegment(
                text="Let me show you an example.",
                start_ms=10000,
                end_ms=14000,
                hash="h4",
            ),
        ],
    )


def _make_item(
    item_id: str = "item_1",
    item_type: ItemType = ItemType.TRANSCRIPT_FACT,
    content: str = "Data classes were introduced in Python 3.7.",
    evidence_text: str = "Data classes were introduced in Python 3.7.",
    start_ms: int = 3000,
    end_ms: int = 6500,
) -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        type=item_type,
        content=content,
        transcript_evidence=TranscriptEvidence(
            video_id="test_vid",
            start_ms=start_ms,
            end_ms=end_ms,
            text=evidence_text,
        ),
    )


def _make_config(
    quote_mismatch: QuoteMismatchBehavior = QuoteMismatchBehavior.REJECT,
) -> AppConfig:
    return AppConfig(model="test", quote_mismatch=quote_mismatch)


# ---------------------------------------------------------------------------
# verify_quote
# ---------------------------------------------------------------------------


class TestVerifyQuote:
    def test_exact_match_in_segment(self) -> None:
        transcript = _make_transcript()
        assert verify_quote(
            "Data classes were introduced in Python 3.7.",
            transcript,
            start_ms=3000,
            end_ms=6500,
        )

    def test_substring_match(self) -> None:
        transcript = _make_transcript()
        assert verify_quote(
            "introduced in Python 3.7",
            transcript,
            start_ms=3000,
            end_ms=6500,
        )

    def test_no_match(self) -> None:
        transcript = _make_transcript()
        assert not verify_quote(
            "This text does not exist in the transcript",
            transcript,
            start_ms=3000,
            end_ms=6500,
        )

    def test_match_outside_time_range(self) -> None:
        transcript = _make_transcript()
        # "Data classes..." is at 3000-6500, but we search 0-3000
        assert not verify_quote(
            "Data classes were introduced in Python 3.7.",
            transcript,
            start_ms=0,
            end_ms=3000,
        )

    def test_match_spanning_segments(self) -> None:
        transcript = _make_transcript()
        # Search across segments 2 and 3 (3000-10000)
        # Combined text: "Data classes... They reduce..."
        assert verify_quote(
            "Data classes were introduced in Python 3.7.",
            transcript,
            start_ms=3000,
            end_ms=10000,
        )

    def test_empty_quote(self) -> None:
        transcript = _make_transcript()
        # Empty string is a substring of everything
        assert verify_quote("", transcript, start_ms=0, end_ms=14000)

    def test_no_overlapping_segments(self) -> None:
        transcript = _make_transcript()
        # Time range beyond transcript
        assert not verify_quote("anything", transcript, start_ms=20000, end_ms=25000)


# ---------------------------------------------------------------------------
# _check_timestamp_bounds
# ---------------------------------------------------------------------------


class TestCheckTimestampBounds:
    def test_valid_bounds(self) -> None:
        transcript = _make_transcript()
        item = _make_item(start_ms=3000, end_ms=6500)
        assert _check_timestamp_bounds(item, transcript)

    def test_negative_start(self) -> None:
        transcript = _make_transcript()
        item = _make_item(start_ms=-100, end_ms=6500)
        assert not _check_timestamp_bounds(item, transcript)

    def test_start_equals_end(self) -> None:
        transcript = _make_transcript()
        item = _make_item(start_ms=3000, end_ms=3000)
        assert not _check_timestamp_bounds(item, transcript)

    def test_start_after_end(self) -> None:
        transcript = _make_transcript()
        item = _make_item(start_ms=6500, end_ms=3000)
        assert not _check_timestamp_bounds(item, transcript)

    def test_beyond_transcript_end(self) -> None:
        transcript = _make_transcript()
        item = _make_item(start_ms=10000, end_ms=20000)
        assert not _check_timestamp_bounds(item, transcript)

    def test_before_transcript_start(self) -> None:
        transcript = _make_transcript()
        # Transcript starts at 0, but if segments started later...
        # Our transcript starts at 0 so this is fine
        item = _make_item(start_ms=0, end_ms=3000)
        assert _check_timestamp_bounds(item, transcript)

    def test_empty_transcript(self) -> None:
        transcript = NormalizedTranscript(
            video_id="empty",
            full_text="",
            hash="h",
            segments=[],
        )
        item = _make_item(start_ms=0, end_ms=5000)
        assert not _check_timestamp_bounds(item, transcript)


# ---------------------------------------------------------------------------
# validate_items
# ---------------------------------------------------------------------------


class TestValidateItems:
    def test_valid_transcript_fact_accepted(self) -> None:
        transcript = _make_transcript()
        config = _make_config()
        item = _make_item()
        result = validate_items([item], transcript, config)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 0
        assert len(result.downgraded) == 0

    def test_valid_direct_quote_accepted(self) -> None:
        transcript = _make_transcript()
        config = _make_config()
        item = _make_item(
            item_type=ItemType.DIRECT_QUOTE,
            content="Data classes were introduced in Python 3.7.",
        )
        result = validate_items([item], transcript, config)
        assert len(result.accepted) == 1

    def test_quote_mismatch_reject_mode(self) -> None:
        transcript = _make_transcript()
        config = _make_config(
            quote_mismatch=QuoteMismatchBehavior.REJECT,
        )
        item = _make_item(
            item_type=ItemType.DIRECT_QUOTE,
            content="This quote does not exist in the transcript.",
            evidence_text="Data classes were introduced in Python 3.7.",
        )
        result = validate_items([item], transcript, config)
        assert len(result.accepted) == 0
        assert len(result.rejected) == 1
        assert len(result.downgraded) == 0

    def test_quote_mismatch_downgrade_mode(self) -> None:
        transcript = _make_transcript()
        config = _make_config(
            quote_mismatch=QuoteMismatchBehavior.DOWNGRADE,
        )
        item = _make_item(
            item_type=ItemType.DIRECT_QUOTE,
            content="This quote does not exist in the transcript.",
            evidence_text="Data classes were introduced in Python 3.7.",
        )
        result = validate_items([item], transcript, config)
        assert len(result.accepted) == 0
        assert len(result.rejected) == 0
        assert len(result.downgraded) == 1
        assert result.downgraded[0].type == ItemType.UNVERIFIED_CLAIM

    def test_invalid_timestamps_rejected(self) -> None:
        transcript = _make_transcript()
        config = _make_config()
        item = _make_item(start_ms=50000, end_ms=60000)
        result = validate_items([item], transcript, config)
        assert len(result.rejected) == 1
        assert len(result.accepted) == 0

    def test_non_quote_items_skip_quote_check(self) -> None:
        transcript = _make_transcript()
        config = _make_config()
        # speaker_opinion doesn't need quote verification
        item = _make_item(
            item_type=ItemType.SPEAKER_OPINION,
            content="I think Python is the best language.",
            evidence_text="Data classes were introduced in Python 3.7.",
        )
        result = validate_items([item], transcript, config)
        assert len(result.accepted) == 1

    def test_evidence_text_mismatch_rejected(self) -> None:
        transcript = _make_transcript()
        config = _make_config()
        # Non-quote item but evidence text doesn't match transcript
        item = _make_item(
            item_type=ItemType.TRANSCRIPT_FACT,
            content="Some fact",
            evidence_text="This evidence text is not in the transcript.",
        )
        result = validate_items([item], transcript, config)
        assert len(result.rejected) == 1

    def test_multiple_items_mixed_results(self) -> None:
        transcript = _make_transcript()
        config = _make_config()
        items = [
            # Valid fact
            _make_item(item_id="good"),
            # Bad timestamps
            _make_item(item_id="bad_ts", start_ms=50000, end_ms=60000),
            # Valid opinion
            _make_item(
                item_id="opinion",
                item_type=ItemType.SPEAKER_OPINION,
                content="Great stuff",
                evidence_text="They reduce boilerplate code significantly.",
                start_ms=6500,
                end_ms=10000,
            ),
        ]
        result = validate_items(items, transcript, config)
        assert len(result.accepted) == 2
        assert len(result.rejected) == 1
        assert result.rejected[0].id == "bad_ts"

    def test_empty_items_list(self) -> None:
        transcript = _make_transcript()
        config = _make_config()
        result = validate_items([], transcript, config)
        assert result.accepted == []
        assert result.rejected == []
        assert result.downgraded == []
