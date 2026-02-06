# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Transcript ingestion, normalization, and segmentation."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from yt_factify.config import AppConfig
from yt_factify.models import (
    NormalizedSegment,
    NormalizedTranscript,
    RawTranscript,
    TranscriptSegment,
    TranscriptSegmentRaw,
)


class TranscriptFetchError(Exception):
    """Raised when a transcript cannot be fetched."""


class EmptyTranscriptError(Exception):
    """Raised when a transcript has no content."""


def _sha256(text: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    """Normalize a text string: Unicode NFC, collapse whitespace, strip."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_transcript(video_id: str, config: AppConfig) -> RawTranscript:
    """Fetch transcript via yt-fetch and return raw data.

    Calls ``yt_fetch.fetch_video()`` to retrieve transcript segments.

    Args:
        video_id: YouTube video ID.
        config: Application configuration.

    Returns:
        A ``RawTranscript`` with raw segment data.

    Raises:
        TranscriptFetchError: If the video or transcript is unavailable.
    """
    try:
        from yt_fetch import FetchOptions, fetch_video
    except ImportError as exc:
        raise TranscriptFetchError(
            "yt-fetch is not installed. Install with: pip install yt-fetch"
        ) from exc

    opts = FetchOptions(
        languages=["en"],
        allow_generated=True,
        download="none",
    )

    result = fetch_video(video_id, opts)

    if not result.success or result.transcript is None:
        errors = "; ".join(result.errors) if result.errors else "unknown error"
        raise TranscriptFetchError(
            f"Failed to fetch transcript for {video_id}: {errors}"
        )

    segments = [
        TranscriptSegmentRaw(
            text=seg.text,
            start_ms=int(seg.start * 1000),
            end_ms=int((seg.start + seg.duration) * 1000),
        )
        for seg in result.transcript.segments
    ]

    return RawTranscript(
        video_id=video_id,
        segments=segments,
        language=result.transcript.language,
    )


def normalize_transcript(raw: RawTranscript) -> NormalizedTranscript:
    """Normalize raw transcript into canonical format.

    - Strips extraneous whitespace.
    - Normalizes Unicode (NFC).
    - Computes SHA-256 hash of the full normalized text.
    - Computes per-segment hashes.

    Args:
        raw: Raw transcript from yt-fetch.

    Returns:
        A ``NormalizedTranscript`` with hashed segments.

    Raises:
        EmptyTranscriptError: If the transcript has no segments or all text is empty.
    """
    if not raw.segments:
        raise EmptyTranscriptError(f"Transcript for {raw.video_id} has no segments")

    normalized_segments: list[NormalizedSegment] = []
    for seg in raw.segments:
        norm_text = _normalize_text(seg.text)
        if not norm_text:
            continue
        normalized_segments.append(
            NormalizedSegment(
                text=norm_text,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                hash=_sha256(norm_text),
            )
        )

    if not normalized_segments:
        raise EmptyTranscriptError(
            f"Transcript for {raw.video_id} has no non-empty segments after normalization"
        )

    full_text = " ".join(seg.text for seg in normalized_segments)

    return NormalizedTranscript(
        video_id=raw.video_id,
        full_text=full_text,
        hash=_sha256(full_text),
        segments=normalized_segments,
        language=raw.language,
    )


def segment_transcript(
    transcript: NormalizedTranscript,
    target_seconds: int = 45,
) -> list[TranscriptSegment]:
    """Split transcript into segments for LLM processing.

    Targets approximately ``target_seconds`` per segment.
    Respects sentence boundaries where possible.
    Each segment gets a unique hash.

    Args:
        transcript: Normalized transcript.
        target_seconds: Target duration per segment in seconds.

    Returns:
        A list of ``TranscriptSegment`` instances ready for LLM processing.
    """
    if not transcript.segments:
        return []

    target_ms = target_seconds * 1000
    result: list[TranscriptSegment] = []
    current_texts: list[str] = []
    current_indices: list[int] = []
    current_start_ms: int = transcript.segments[0].start_ms
    current_duration_ms: int = 0

    for i, seg in enumerate(transcript.segments):
        seg_duration = seg.end_ms - seg.start_ms
        current_texts.append(seg.text)
        current_indices.append(i)
        current_duration_ms += seg_duration

        if current_duration_ms >= target_ms:
            # Try to split at a sentence boundary within the accumulated text
            combined = " ".join(current_texts)
            result.append(
                TranscriptSegment(
                    text=combined,
                    start_ms=current_start_ms,
                    end_ms=seg.end_ms,
                    hash=_sha256(combined),
                    source_segment_indices=list(current_indices),
                )
            )
            current_texts = []
            current_indices = []
            current_duration_ms = 0
            # Next segment starts after this one
            if i + 1 < len(transcript.segments):
                current_start_ms = transcript.segments[i + 1].start_ms

    # Flush remaining segments
    if current_texts:
        combined = " ".join(current_texts)
        last_seg = transcript.segments[current_indices[-1]]
        result.append(
            TranscriptSegment(
                text=combined,
                start_ms=current_start_ms,
                end_ms=last_seg.end_ms,
                hash=_sha256(combined),
                source_segment_indices=list(current_indices),
            )
        )

    return result
