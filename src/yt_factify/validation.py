# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Post-extraction validation — quote verification, timestamp checks."""

from __future__ import annotations

import structlog

from yt_factify.config import AppConfig
from yt_factify.models import (
    ExtractedItem,
    ItemType,
    NormalizedTranscript,
    QuoteMismatchBehavior,
    ValidationResult,
)

logger = structlog.get_logger()


def verify_quote(
    quote_text: str,
    transcript: NormalizedTranscript,
    start_ms: int,
    end_ms: int,
) -> bool:
    """Check that quote_text is an exact substring within the given time range.

    Searches the normalized segments that overlap with [start_ms, end_ms]
    and checks whether ``quote_text`` appears as a substring of their
    combined text.

    Args:
        quote_text: The quote text to verify.
        transcript: The normalized transcript to search.
        start_ms: Start of the time range (inclusive).
        end_ms: End of the time range (inclusive).

    Returns:
        True if the quote is found within the time range.
    """
    # Collect text from segments that overlap with the time range
    overlapping_texts: list[str] = []
    for seg in transcript.segments:
        if seg.end_ms > start_ms and seg.start_ms < end_ms:
            overlapping_texts.append(seg.text)

    if not overlapping_texts:
        return False

    combined = " ".join(overlapping_texts)
    return quote_text in combined


def _check_timestamp_bounds(
    item: ExtractedItem,
    transcript: NormalizedTranscript,
) -> bool:
    """Verify that an item's timestamps fall within the transcript bounds.

    Args:
        item: The extracted item to check.
        transcript: The normalized transcript.

    Returns:
        True if timestamps are valid.
    """
    evidence = item.transcript_evidence
    if evidence.start_ms < 0 or evidence.end_ms < 0:
        return False
    if evidence.start_ms >= evidence.end_ms:
        return False

    if not transcript.segments:
        return False

    transcript_start = transcript.segments[0].start_ms
    transcript_end = transcript.segments[-1].end_ms

    if evidence.start_ms < transcript_start:
        return False
    return evidence.end_ms <= transcript_end


def validate_items(
    items: list[ExtractedItem],
    transcript: NormalizedTranscript,
    config: AppConfig,
) -> ValidationResult:
    """Validate extracted items against the transcript.

    Checks:
    - ``direct_quote`` text is an exact substring of transcript.
    - Timestamp bounds are valid.
    - All required fields are present and well-typed (via Pydantic).

    Returns ``ValidationResult`` with accepted items, rejected items,
    and downgraded items (depending on ``quote_mismatch`` config).

    Args:
        items: Extracted items to validate.
        transcript: The normalized transcript for verification.
        config: Application configuration (controls quote_mismatch behavior).

    Returns:
        A ``ValidationResult`` with categorized items.
    """
    accepted: list[ExtractedItem] = []
    rejected: list[ExtractedItem] = []
    downgraded: list[ExtractedItem] = []

    for item in items:
        # Check timestamp bounds
        if not _check_timestamp_bounds(item, transcript):
            logger.warning(
                "item_rejected_invalid_timestamps",
                item_id=item.id,
                start_ms=item.transcript_evidence.start_ms,
                end_ms=item.transcript_evidence.end_ms,
            )
            rejected.append(item)
            continue

        # Check quote verification for direct_quote items
        if item.type == ItemType.DIRECT_QUOTE:
            quote_ok = verify_quote(
                quote_text=item.content,
                transcript=transcript,
                start_ms=item.transcript_evidence.start_ms,
                end_ms=item.transcript_evidence.end_ms,
            )
            if not quote_ok:
                if config.quote_mismatch == QuoteMismatchBehavior.REJECT:
                    logger.warning(
                        "quote_rejected_mismatch",
                        item_id=item.id,
                        content=item.content[:80],
                    )
                    rejected.append(item)
                else:
                    # Downgrade: change type from direct_quote to
                    # unverified_claim
                    downgraded_item = item.model_copy(
                        update={"type": ItemType.UNVERIFIED_CLAIM}
                    )
                    logger.info(
                        "quote_downgraded",
                        item_id=item.id,
                        content=item.content[:80],
                    )
                    downgraded.append(downgraded_item)
                continue

        # Check that transcript_evidence.text is a substring of the
        # transcript within the time range
        evidence_ok = verify_quote(
            quote_text=item.transcript_evidence.text,
            transcript=transcript,
            start_ms=item.transcript_evidence.start_ms,
            end_ms=item.transcript_evidence.end_ms,
        )
        if not evidence_ok:
            logger.warning(
                "item_rejected_evidence_mismatch",
                item_id=item.id,
                evidence_text=item.transcript_evidence.text[:80],
            )
            rejected.append(item)
            continue

        accepted.append(item)

    logger.info(
        "validation_complete",
        total=len(items),
        accepted=len(accepted),
        rejected=len(rejected),
        downgraded=len(downgraded),
    )

    return ValidationResult(
        accepted=accepted,
        rejected=rejected,
        downgraded=downgraded,
    )
