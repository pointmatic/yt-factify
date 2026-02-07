# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Output rendering — JSON and Markdown formats."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

import structlog

from yt_factify.models import (
    ExtractedItem,
    ExtractionResult,
    ItemType,
    TopicThread,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# JSON rendering
# ---------------------------------------------------------------------------


def render_json(result: ExtractionResult, *, indent: int = 2) -> str:
    """Serialize an ExtractionResult to a JSON string.

    Args:
        result: The pipeline output to serialize.
        indent: JSON indentation level.

    Returns:
        JSON string representation.
    """
    return result.model_dump_json(indent=indent)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _format_ms(ms: int) -> str:
    """Format milliseconds as HH:MM:SS or MM:SS."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _render_video_info(result: ExtractionResult) -> str:
    """Render the Video Info section."""
    lines = ["## Video Info", ""]
    lines.append(f"- **Video ID:** {result.video.video_id}")
    if result.video.title:
        lines.append(f"- **Title:** {result.video.title}")
    lines.append(f"- **URL:** {result.video.url}")
    cats = ", ".join(c.value for c in result.classification.categories)
    lines.append(f"- **Categories:** {cats}")
    bp = result.classification.bias_profile
    lines.append(f"- **Bias:** {bp.primary_label} (confidence: {bp.confidence:.0%})")
    if bp.rationale:
        lines.append(f"- **Bias Rationale:** {bp.rationale}")
    return "\n".join(lines)


def _render_topic_overview(threads: list[TopicThread]) -> str:
    """Render the Topic Overview section."""
    if not threads:
        return ""
    lines = ["## Topic Overview", ""]
    for thread in threads:
        timeline_str = ", ".join(
            f"{_format_ms(span.start_ms)}–{_format_ms(span.end_ms)}" for span in thread.timeline
        )
        lines.append(f"### {thread.display_name}")
        lines.append("")
        lines.append(f"{thread.summary}")
        lines.append("")
        if timeline_str:
            lines.append(f"- **Timeline:** {timeline_str}")
        lines.append(f"- **Items:** {len(thread.item_ids)}")
        lines.append("")
    return "\n".join(lines)


def _render_items_section(
    title: str,
    items: list[ExtractedItem],
) -> str:
    """Render a section of extracted items."""
    if not items:
        return ""
    lines = [f"## {title}", ""]
    for item in items:
        time_range = (
            f"{_format_ms(item.transcript_evidence.start_ms)}–"
            f"{_format_ms(item.transcript_evidence.end_ms)}"
        )
        speaker = f" ({item.speaker})" if item.speaker else ""

        if item.type == ItemType.DIRECT_QUOTE:
            lines.append(f'> "{item.content}"{speaker}')
        else:
            lines.append(f"- {item.content}{speaker}")

        lines.append(f"  *[{time_range}]*")

        if item.credibility:
            cred = item.credibility
            lines.append(f"  Credibility: **{cred.label.value}** ({cred.confidence:.0%})")

        if item.belief_system_flags:
            flags = ", ".join(f"{f.module_label}: {f.note}" for f in item.belief_system_flags)
            lines.append(f"  Belief systems: {flags}")

        lines.append("")
    return "\n".join(lines)


def _render_belief_system_notes(result: ExtractionResult) -> str:
    """Render the Belief System Notes section."""
    flagged = [item for item in result.items if item.belief_system_flags]
    if not flagged:
        return ""
    lines = ["## Belief System Notes", ""]
    lines.append("The following items were flagged as relying on specific worldview assumptions:")
    lines.append("")
    for item in flagged:
        for flag in item.belief_system_flags:
            lines.append(f"- **{flag.module_label}:** {flag.note} (item: {item.id})")
    lines.append("")
    return "\n".join(lines)


def render_markdown(result: ExtractionResult) -> str:
    """Render an ExtractionResult as a human-readable Markdown summary.

    Sections:
        - Video Info
        - Topic Overview
        - Key Facts
        - Direct Quotes
        - Opinions & Perspectives
        - Unverified Claims
        - Predictions
        - Belief System Notes

    Args:
        result: The pipeline output to render.

    Returns:
        Markdown string.
    """
    # Group items by type
    facts: list[ExtractedItem] = []
    quotes: list[ExtractedItem] = []
    opinions: list[ExtractedItem] = []
    unverified: list[ExtractedItem] = []
    predictions: list[ExtractedItem] = []

    for item in result.items:
        match item.type:
            case ItemType.TRANSCRIPT_FACT | ItemType.GENERAL_KNOWLEDGE:
                facts.append(item)
            case ItemType.DIRECT_QUOTE:
                quotes.append(item)
            case ItemType.SPEAKER_OPINION:
                opinions.append(item)
            case ItemType.UNVERIFIED_CLAIM:
                unverified.append(item)
            case ItemType.PREDICTION:
                predictions.append(item)

    sections = [
        f"# yt-factify Report: {result.video.video_id}",
        "",
        _render_video_info(result),
        "",
        _render_topic_overview(result.topic_threads),
        _render_items_section("Key Facts", facts),
        _render_items_section("Direct Quotes", quotes),
        _render_items_section("Opinions & Perspectives", opinions),
        _render_items_section("Unverified Claims", unverified),
        _render_items_section("Predictions", predictions),
        _render_belief_system_notes(result),
    ]

    # Filter empty sections and join
    content = "\n".join(s for s in sections if s)

    # Ensure trailing newline
    if not content.endswith("\n"):
        content += "\n"

    return content


# ---------------------------------------------------------------------------
# Atomic file writing
# ---------------------------------------------------------------------------


def write_output(content: str, output_path: Path) -> None:
    """Write content to a file atomically.

    Writes to a temporary file in the same directory, then renames
    to the target path. This ensures the output file is never in a
    partial state.

    Args:
        content: String content to write.
        output_path: Destination file path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=output_path.parent,
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, output_path)
        logger.info("output_written", path=str(output_path))
    except BaseException:
        # Clean up temp file on failure
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
