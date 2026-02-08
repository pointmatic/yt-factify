# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Topic thread clustering — groups extracted items by subject."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from yt_factify.config import AppConfig
from yt_factify.llm import llm_completion
from yt_factify.models import (
    ExtractedItem,
    TopicThread,
    TopicTimeSpan,
)
from yt_factify.prompts.topics import build_topic_threading_messages

if TYPE_CHECKING:
    from gentlify import Throttle

logger = structlog.get_logger()

_MIN_ITEMS_FOR_THREADING = 3


class TopicClusteringError(Exception):
    """Raised when topic thread clustering fails after retries."""


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM response text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(lines)
    return text


def _derive_timeline(
    item_ids: list[str],
    items_by_id: dict[str, ExtractedItem],
) -> list[TopicTimeSpan]:
    """Derive a timeline of time spans from the items in a thread.

    Collects the transcript_evidence time ranges of all referenced items,
    sorts them, and merges overlapping spans.

    Args:
        item_ids: IDs of items in this thread.
        items_by_id: Lookup dict of all items.

    Returns:
        Sorted, merged list of TopicTimeSpan.
    """
    spans: list[tuple[int, int]] = []
    for item_id in item_ids:
        item = items_by_id.get(item_id)
        if item:
            ev = item.transcript_evidence
            spans.append((ev.start_ms, ev.end_ms))

    if not spans:
        return []

    # Sort by start time
    spans.sort()

    # Merge overlapping spans
    merged: list[tuple[int, int]] = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return [TopicTimeSpan(start_ms=s, end_ms=e) for s, e in merged]


def _parse_topic_threads(
    raw_text: str,
    items: list[ExtractedItem],
) -> list[TopicThread]:
    """Parse LLM topic threading response into TopicThread objects.

    Args:
        raw_text: Raw JSON text from LLM.
        items: Original items for cross-referencing IDs and deriving
            timelines.

    Returns:
        List of validated TopicThread objects.

    Raises:
        json.JSONDecodeError: If the response is not valid JSON.
        ValueError: If the JSON is not a list.
    """
    data = json.loads(_strip_fences(raw_text))
    if not isinstance(data, list):
        msg = f"Expected JSON array, got {type(data).__name__}"
        raise ValueError(msg)

    valid_ids = {item.id for item in items}
    items_by_id = {item.id: item for item in items}
    threads: list[TopicThread] = []

    for raw_thread in data:
        try:
            label = raw_thread["label"]
            display_name = raw_thread["display_name"]
            summary = raw_thread["summary"]
            raw_item_ids = raw_thread.get("item_ids", [])

            # Filter to only valid item IDs
            filtered_ids: list[str] = []
            for item_id in raw_item_ids:
                if item_id in valid_ids:
                    filtered_ids.append(item_id)
                else:
                    logger.warning(
                        "topic_thread_unknown_item_id",
                        thread_label=label,
                        item_id=item_id,
                    )

            if not filtered_ids:
                logger.warning(
                    "topic_thread_empty_after_filtering",
                    thread_label=label,
                )
                continue

            timeline = _derive_timeline(filtered_ids, items_by_id)

            threads.append(
                TopicThread(
                    label=label,
                    display_name=display_name,
                    summary=summary,
                    item_ids=filtered_ids,
                    timeline=timeline,
                )
            )
        except (KeyError, TypeError) as exc:
            logger.warning(
                "topic_thread_skipped_invalid",
                raw=raw_thread,
                error=str(exc),
            )

    return threads


async def cluster_topic_threads(
    items: list[ExtractedItem],
    config: AppConfig,
    throttle: Throttle | None = None,
) -> list[TopicThread]:
    """Cluster extracted items into topic threads via LLM.

    Receives all validated extracted items and asks the LLM to identify
    recurring topics and group items by subject. Items may belong to
    multiple threads. The timeline for each thread is derived from the
    transcript_evidence timestamps of its member items.

    For v1, threads are a flat list (no hierarchical sub-topics).

    Args:
        items: Validated extracted items to cluster.
        config: Application configuration.

    Returns:
        List of topic threads. Empty if fewer than
        ``_MIN_ITEMS_FOR_THREADING`` items.

    Raises:
        TopicClusteringError: If clustering fails after retries.
    """
    if len(items) < _MIN_ITEMS_FOR_THREADING:
        logger.info(
            "skipping_topic_threading_few_items",
            item_count=len(items),
            min_required=_MIN_ITEMS_FOR_THREADING,
        )
        return []

    messages = build_topic_threading_messages(items)

    max_attempts = min(config.max_retries, 2)
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            content = await llm_completion(
                messages=messages,
                config=config,
                max_attempts=1,
                context="topic_clustering",
                throttle=throttle,
            )

            threads = _parse_topic_threads(content, items)

            logger.info(
                "topic_threads_clustered",
                thread_count=len(threads),
                item_count=len(items),
                attempt=attempt + 1,
            )
            return threads

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "topic_clustering_parse_error",
                attempt=attempt + 1,
                error=str(exc),
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "topic_clustering_llm_error",
                attempt=attempt + 1,
                error=str(exc),
            )

    raise TopicClusteringError(
        f"Failed to cluster topic threads after {max_attempts} attempts: {last_error}"
    )
