# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Transcript ingestion, normalization, and segmentation."""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from datetime import date

import structlog

from yt_factify.config import AppConfig
from yt_factify.models import (
    NormalizedSegment,
    NormalizedTranscript,
    RawTranscript,
    TranscriptSegment,
    TranscriptSegmentRaw,
    VideoMetadata,
)

logger = structlog.get_logger()


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


def _upload_date_hint(metadata: VideoMetadata | None) -> str:
    """Return a human-readable hint based on video upload date."""
    if metadata is None or metadata.upload_date is None:
        return "The video may lack captions or they may be disabled."

    try:
        upload = date.fromisoformat(metadata.upload_date)
    except ValueError:
        return "The video may lack captions or they may be disabled."

    age_days = (date.today() - upload).days

    if age_days < 1:
        return (
            "This video was uploaded within the last 24 hours — "
            "captions may not be available yet. Try again later."
        )
    elif age_days <= 7:
        return (
            "This video was uploaded recently — auto-generated captions may still be processing."
        )
    else:
        return "The video may lack captions or they may be disabled."


def _build_video_metadata(result: object) -> VideoMetadata | None:
    """Build a VideoMetadata from a yt-fetch FetchResult, if metadata is present."""
    meta = getattr(result, "metadata", None)
    if meta is None:
        return None
    return VideoMetadata(
        title=getattr(meta, "title", None),
        channel_id=getattr(meta, "channel_id", None),
        channel_title=getattr(meta, "channel_title", None),
        upload_date=getattr(meta, "upload_date", None),
        duration_seconds=getattr(meta, "duration_seconds", None),
        fetched_at=str(getattr(meta, "fetched_at", None)),
    )


def fetch_transcript(video_id: str, config: AppConfig) -> RawTranscript:
    """Fetch transcript via yt-fetch and return raw data.

    Calls ``yt_fetch.fetch_video()`` to retrieve transcript segments
    and video metadata.

    Args:
        video_id: YouTube video ID.
        config: Application configuration.

    Returns:
        A ``RawTranscript`` with raw segment data and optional metadata.

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
        languages=config.languages,
        allow_generated=True,
        download="none",
        force_transcript=True,
        force_metadata=True,
    )

    # Retry once on transient failures (e.g. YouTube throttling after
    # heavy use).  A hard API error with explicit error messages is
    # not retried.
    max_fetch_attempts = 2
    retry_delay = 5.0

    for attempt in range(1, max_fetch_attempts + 1):
        result = fetch_video(video_id, opts)
        video_metadata = _build_video_metadata(result)

        # Hard failure with explicit errors — don't retry
        if not result.success and result.errors:
            errors = "; ".join(result.errors)
            raise TranscriptFetchError(f"Failed to fetch transcript for {video_id}: {errors}")

        # Transcript present — success
        if result.transcript is not None:
            break

        # Transient failure: success=True but no transcript, or
        # success=False with no error details.  Retry after a delay.
        if attempt < max_fetch_attempts:
            logger.warning(
                "transcript_fetch_retry",
                video_id=video_id,
                attempt=attempt,
                retry_in_seconds=retry_delay,
                reason="no transcript returned — may be a transient YouTube block",
            )
            time.sleep(retry_delay)
            continue

        # Final attempt still failed
        if not result.success:
            raise TranscriptFetchError(f"Failed to fetch transcript for {video_id}: unknown error")
        hint = _upload_date_hint(video_metadata)
        raise TranscriptFetchError(f"No transcript available for {video_id}. {hint}")

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
        metadata=video_metadata,
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
