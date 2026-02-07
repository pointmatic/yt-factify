# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""LLM-based item extraction from transcript segments."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING

import structlog

from yt_factify.config import AppConfig
from yt_factify.llm import llm_completion
from yt_factify.models import (
    BeliefSystemModule,
    ExtractedItem,
    TranscriptSegment,
    VideoCategory,
)
from yt_factify.prompts.extraction import (
    build_extraction_messages,
)

if TYPE_CHECKING:
    from yt_factify.throttle import AdaptiveThrottle

logger = structlog.get_logger()


class ExtractionError(Exception):
    """Raised when LLM extraction fails after retries."""


def _parse_items_from_response(
    raw_text: str,
    video_id: str,
    segment: TranscriptSegment,
) -> list[ExtractedItem]:
    """Parse LLM response text into a list of ExtractedItem.

    Args:
        raw_text: Raw text from LLM response (expected JSON array).
        video_id: Video ID for evidence anchoring.
        segment: Source transcript segment for validation context.

    Returns:
        List of validated ExtractedItem instances.

    Raises:
        json.JSONDecodeError: If the response is not valid JSON.
        ValueError: If the JSON is not a list.
    """
    # Strip markdown fences if the LLM included them
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(lines)

    data = json.loads(text)
    if not isinstance(data, list):
        msg = f"Expected JSON array, got {type(data).__name__}"
        raise ValueError(msg)

    items: list[ExtractedItem] = []
    for i, raw_item in enumerate(data):
        try:
            # Ensure video_id is set on transcript_evidence
            if "transcript_evidence" in raw_item:
                raw_item["transcript_evidence"]["video_id"] = video_id

            # Generate ID if not provided
            if "id" not in raw_item or not raw_item["id"]:
                raw_item["id"] = f"{video_id}_seg{segment.start_ms}_{i}"

            item = ExtractedItem.model_validate(raw_item)
            items.append(item)
        except Exception:
            logger.warning(
                "skipping_invalid_item",
                index=i,
                video_id=video_id,
                segment_start=segment.start_ms,
            )

    return items


async def _extract_segment(
    segment: TranscriptSegment,
    video_id: str,
    categories: list[VideoCategory],
    belief_modules: list[BeliefSystemModule],
    config: AppConfig,
    throttle: AdaptiveThrottle | None = None,
) -> list[ExtractedItem]:
    """Extract items from a single segment via LLM.

    Builds the prompt, calls litellm.acompletion(), parses the response.
    Retries once on malformed JSON or schema failure.

    Args:
        segment: Transcript segment to process.
        video_id: YouTube video ID.
        categories: Video categories for context.
        belief_modules: Belief system modules for flagging.
        config: Application configuration.

    Returns:
        List of extracted items from this segment.

    Raises:
        ExtractionError: If extraction fails after retries.
    """
    if not segment.text.strip():
        logger.info(
            "skipping_empty_segment",
            video_id=video_id,
            start_ms=segment.start_ms,
        )
        return []

    messages = build_extraction_messages(
        segment=segment,
        video_id=video_id,
        categories=categories or None,
        belief_modules=belief_modules or None,
    )

    max_attempts = min(config.max_retries, 2)  # At most 2 attempts for extraction
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            content = await llm_completion(
                messages=messages,
                config=config,
                max_attempts=1,  # outer loop handles parse retries
                context=f"extraction_seg{segment.start_ms}",
                throttle=throttle,
            )

            items = _parse_items_from_response(content, video_id, segment)

            logger.info(
                "segment_extracted",
                video_id=video_id,
                start_ms=segment.start_ms,
                item_count=len(items),
                attempt=attempt + 1,
            )
            return items

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "extraction_parse_error",
                video_id=video_id,
                start_ms=segment.start_ms,
                attempt=attempt + 1,
                error=str(exc),
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "extraction_llm_error",
                video_id=video_id,
                start_ms=segment.start_ms,
                attempt=attempt + 1,
                error=str(exc),
            )

    raise ExtractionError(
        f"Failed to extract items from segment at {segment.start_ms}ms "
        f"after {max_attempts} attempts: {last_error}"
    )


async def extract_items(
    segments: list[TranscriptSegment],
    video_id: str,
    categories: list[VideoCategory],
    belief_modules: list[BeliefSystemModule],
    config: AppConfig,
    throttle: AdaptiveThrottle | None = None,
) -> list[ExtractedItem]:
    """Extract structured items from transcript segments via LLM.

    Processes segments concurrently. If a throttle is provided, it
    coordinates dispatch rate and concurrency globally. Otherwise
    falls back to a simple semaphore.

    Args:
        segments: Transcript segments to process.
        video_id: YouTube video ID.
        categories: Video categories for context.
        belief_modules: Belief system modules for flagging.
        config: Application configuration.
        throttle: Optional shared throttle for adaptive rate control.

    Returns:
        Flat list of all extracted items across all segments.
    """
    # When no throttle, use a simple semaphore for backward compatibility
    semaphore = None if throttle else asyncio.Semaphore(config.max_concurrent_requests)

    async def _limited_extract(seg: TranscriptSegment) -> list[ExtractedItem]:
        if semaphore is not None:
            async with semaphore:
                return await _extract_segment(
                    segment=seg,
                    video_id=video_id,
                    categories=categories,
                    belief_modules=belief_modules,
                    config=config,
                    throttle=throttle,
                )
        return await _extract_segment(
            segment=seg,
            video_id=video_id,
            categories=categories,
            belief_modules=belief_modules,
            config=config,
            throttle=throttle,
        )

    results = await asyncio.gather(
        *[_limited_extract(seg) for seg in segments],
        return_exceptions=True,
    )

    all_items: list[ExtractedItem] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.error(
                "segment_extraction_failed",
                video_id=video_id,
                segment_index=i,
                error=str(result),
            )
        else:
            all_items.extend(result)

    # Ensure unique IDs across all items
    seen_ids: set[str] = set()
    for item in all_items:
        if item.id in seen_ids:
            item.id = f"{item.id}_{uuid.uuid4().hex[:8]}"
        seen_ids.add(item.id)

    return all_items
