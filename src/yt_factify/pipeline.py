# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Pipeline orchestration — wires all services into the full extraction flow."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from yt_factify import __version__
from yt_factify.belief_systems import get_builtin_modules, load_belief_modules
from yt_factify.classification import assess_credibility, classify_video
from yt_factify.config import AppConfig
from yt_factify.extraction import extract_items
from yt_factify.models import (
    AuditBundle,
    ExtractionResult,
    VideoInfo,
)
from yt_factify.throttle import AdaptiveThrottle
from yt_factify.topics import cluster_topic_threads
from yt_factify.transcript import (
    fetch_transcript,
    normalize_transcript,
    segment_transcript,
)
from yt_factify.validation import validate_items

logger = structlog.get_logger()


class PipelineError(Exception):
    """Raised when the extraction pipeline fails."""


async def run_pipeline(
    video_id: str,
    config: AppConfig,
) -> ExtractionResult:
    """Run the full yt-factify extraction pipeline.

    Steps:
        1. Fetch and normalize transcript.
        2. Segment transcript.
        3. Load belief/value system modules.
        4. Classify video (category + bias).
        5. Extract items from segments (concurrent).
        6. Validate items.
        7. Assess credibility of validated items.
        8. Cluster topic threads from validated items.
        9. Build audit bundle.
        10. Return ExtractionResult.

    Args:
        video_id: YouTube video ID to process.
        config: Application configuration.

    Returns:
        Complete ExtractionResult with all pipeline outputs.

    Raises:
        PipelineError: If any pipeline stage fails unrecoverably.
    """
    logger.info("pipeline_started", video_id=video_id)

    # 1. Fetch and normalize transcript
    try:
        raw_transcript = fetch_transcript(video_id, config)
        video_metadata = raw_transcript.metadata
        transcript = normalize_transcript(raw_transcript)
        logger.info(
            "transcript_ready",
            video_id=video_id,
            segment_count=len(transcript.segments),
            title=video_metadata.title if video_metadata else None,
            channel=video_metadata.channel_title if video_metadata else None,
        )
    except Exception as exc:
        raise PipelineError(f"Failed to fetch/normalize transcript for {video_id}: {exc}") from exc

    # 2. Segment transcript
    try:
        segments = segment_transcript(transcript, target_seconds=config.segment_seconds)
        logger.info(
            "transcript_segmented",
            video_id=video_id,
            segment_count=len(segments),
        )
    except Exception as exc:
        raise PipelineError(f"Failed to segment transcript for {video_id}: {exc}") from exc

    # 3. Load belief/value system modules
    belief_modules = get_builtin_modules()
    if config.modules_dir:
        custom = load_belief_modules(Path(config.modules_dir))
        belief_modules.extend(custom)
    logger.info(
        "belief_modules_ready",
        builtin_count=len(belief_modules),
    )

    # 4. Initialize adaptive throttle for LLM calls
    throttle = AdaptiveThrottle(
        max_concurrency=config.max_concurrent_requests,
        initial_concurrency=config.initial_concurrent_requests,
        total_tasks=len(segments),
    )

    # 5. Classify video (category + bias)
    try:
        classification = await classify_video(transcript, config, throttle=throttle)
    except Exception as exc:
        raise PipelineError(f"Failed to classify video {video_id}: {exc}") from exc

    # 6. Extract items from segments (concurrent)
    try:
        raw_items = await extract_items(
            segments=segments,
            video_id=video_id,
            categories=classification.categories,
            belief_modules=belief_modules,
            config=config,
            throttle=throttle,
        )
        logger.info(
            "items_extracted",
            video_id=video_id,
            item_count=len(raw_items),
        )
    except Exception as exc:
        raise PipelineError(f"Failed to extract items for {video_id}: {exc}") from exc

    # 7. Validate items
    try:
        validation_result = validate_items(raw_items, transcript, config)
        validated_items = validation_result.accepted
        logger.info(
            "items_validated",
            video_id=video_id,
            accepted=len(validation_result.accepted),
            rejected=len(validation_result.rejected),
            downgraded=len(validation_result.downgraded),
        )
    except Exception as exc:
        raise PipelineError(f"Failed to validate items for {video_id}: {exc}") from exc

    # 8. Assess credibility of validated items
    try:
        assessed_items = await assess_credibility(
            validated_items, belief_modules, config, throttle=throttle
        )
    except Exception as exc:
        raise PipelineError(f"Failed to assess credibility for {video_id}: {exc}") from exc

    # 9. Cluster topic threads from validated items
    try:
        topic_threads = await cluster_topic_threads(assessed_items, config, throttle=throttle)
    except Exception as exc:
        raise PipelineError(f"Failed to cluster topic threads for {video_id}: {exc}") from exc

    # 10. Build audit bundle
    segment_hashes = [seg.hash for seg in segments]
    prompt_hashes = "|".join(segment_hashes)
    audit = AuditBundle(
        model_id=config.model,
        model_version=None,
        prompt_templates_hash=prompt_hashes,
        processing_timestamp=datetime.now(tz=UTC),
        segment_hashes=segment_hashes,
        yt_factify_version=__version__,
    )

    # 11. Build and return ExtractionResult
    video_info = VideoInfo(
        video_id=video_id,
        title=video_metadata.title if video_metadata else None,
        url=f"https://www.youtube.com/watch?v={video_id}",
        transcript_hash=transcript.hash,
        fetched_at=datetime.now(tz=UTC),
    )

    result = ExtractionResult(
        video=video_info,
        classification=classification,
        items=assessed_items,
        topic_threads=topic_threads,
        audit=audit,
    )

    logger.info(
        "pipeline_complete",
        video_id=video_id,
        item_count=len(assessed_items),
        topic_thread_count=len(topic_threads),
    )

    return result
