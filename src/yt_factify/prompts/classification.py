# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Classification and bias detection prompt templates for yt-factify."""

from __future__ import annotations

from yt_factify.models import NormalizedTranscript, VideoCategory
from yt_factify.prompts import ChatMessage, _system_msg, _user_msg

CLASSIFICATION_SYSTEM_PROMPT = """\
You are a video content classifier. Given a transcript (or representative \
excerpt), determine the video's category and detect any bias or slant.

## Video Categories

Classify the video into one or more of the following categories:
{categories}

## Output Schema

Return a JSON object with:
```json
{{
  "categories": ["<category>", ...],
  "bias_profile": {{
    "primary_label": "<bias label, e.g. neutral, left-leaning, promotional>",
    "confidence": <float 0.0-1.0>,
    "rationale": "<brief explanation>",
    "implicit_bias_notes": ["<note>", ...]
  }}
}}
```

Return ONLY the JSON object. No commentary, no markdown fences.\
"""

BIAS_SYSTEM_PROMPT = """\
You are a media bias analyst. Given a transcript excerpt and the video's \
category, assess the bias and slant of the content.

Focus on:
1. **Political bias** — left/right/center positioning
2. **Commercial bias** — promotional or sponsored content
3. **Sensationalism** — exaggerated claims or emotional manipulation
4. **Selection bias** — cherry-picked facts or one-sided presentation
5. **Implicit bias** — unstated assumptions or framing effects

## Output Schema

Return a JSON object with:
```json
{{
  "primary_label": "<bias label>",
  "confidence": <float 0.0-1.0>,
  "rationale": "<brief explanation>",
  "implicit_bias_notes": ["<note>", ...]
}}
```

Return ONLY the JSON object. No commentary, no markdown fences.\
"""


def _format_categories() -> str:
    """Format all VideoCategory values for inclusion in a prompt."""
    return "\n".join(f"- `{c.value}`" for c in VideoCategory)


def _sample_transcript(transcript: NormalizedTranscript, max_chars: int = 8000) -> str:
    """Extract a representative sample from a transcript.

    For long transcripts, takes the first, middle, and last segments
    plus a random sample to stay within the character budget.
    """
    full = transcript.full_text
    if len(full) <= max_chars:
        return full

    # Take first, middle, and last thirds
    segments = transcript.segments
    n = len(segments)
    if n <= 6:
        # Short enough to include everything, just truncate
        return full[:max_chars]

    first = segments[:2]
    mid_start = n // 2 - 1
    middle = segments[mid_start : mid_start + 2]
    last = segments[-2:]

    sample_segments = first + middle + last
    sample_text = " [...] ".join(seg.text for seg in sample_segments)

    if len(sample_text) > max_chars:
        sample_text = sample_text[:max_chars]

    return sample_text


def build_classification_messages(
    transcript: NormalizedTranscript,
) -> list[ChatMessage]:
    """Build chat messages for video categorization and bias detection.

    Args:
        transcript: Normalized transcript to classify.

    Returns:
        A list of message dicts (system, user) suitable for litellm.completion().
    """
    system = CLASSIFICATION_SYSTEM_PROMPT.format(categories=_format_categories())

    sample = _sample_transcript(transcript)
    user_content = f"Video ID: {transcript.video_id}\n\nTranscript:\n{sample}"

    return [_system_msg(system), _user_msg(user_content)]


def build_bias_messages(
    transcript: NormalizedTranscript,
    categories: list[VideoCategory],
) -> list[ChatMessage]:
    """Build chat messages for detailed bias/slant analysis.

    Args:
        transcript: Normalized transcript to analyze.
        categories: Previously determined video categories.

    Returns:
        A list of message dicts (system, user) suitable for litellm.completion().
    """
    cat_str = ", ".join(c.value for c in categories)
    sample = _sample_transcript(transcript)
    user_content = (
        f"Video ID: {transcript.video_id}\nVideo categories: {cat_str}\n\nTranscript:\n{sample}"
    )

    return [_system_msg(BIAS_SYSTEM_PROMPT), _user_msg(user_content)]
