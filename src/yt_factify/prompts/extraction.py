# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Extraction prompt templates for yt-factify."""

from __future__ import annotations

from yt_factify.models import BeliefSystemModule, TranscriptSegment, VideoCategory
from yt_factify.prompts import ChatMessage, _system_msg, _user_msg

EXTRACTION_SYSTEM_PROMPT = """\
You are a precise fact-extraction engine. Your job is to extract structured \
items from YouTube video transcript segments.

## Item Types

- **direct_quote**: An exact, verbatim quote from the speaker. The `content` \
field MUST be an exact substring of the transcript text.
- **transcript_fact**: A factual claim stated in the transcript that can be \
verified against external sources.
- **general_knowledge**: A widely accepted fact referenced in the transcript.
- **speaker_opinion**: A subjective opinion expressed by the speaker.
- **unverified_claim**: A claim presented as fact but not easily verifiable.
- **prediction**: A forward-looking statement about future events.

## Anchoring Rules

Every extracted item MUST be anchored to the transcript:
1. The `transcript_evidence.text` field must be an exact substring of the \
provided transcript segment.
2. The `transcript_evidence.start_ms` and `transcript_evidence.end_ms` must \
fall within the segment's time range.
3. For `direct_quote` items, the `content` field must ALSO be an exact \
substring of the transcript.

## Output Schema

Return a JSON array of objects, each with:
```json
{
  "id": "<unique_id>",
  "type": "<item_type>",
  "content": "<extracted content>",
  "speaker": "<speaker name or null>",
  "transcript_evidence": {
    "text": "<exact transcript substring>",
    "start_ms": <int>,
    "end_ms": <int>
  }
}
```

Return ONLY the JSON array. No commentary, no markdown fences.\
"""

_CATEGORIES_SECTION = """\

## Video Categories

This video has been classified as: {categories}. \
Use this context to inform your extraction — for example, items from a \
comedy/satire video should be flagged as opinions rather than facts.\
"""

_BELIEF_SYSTEMS_SECTION = """\

## Belief/Value Systems

The following belief/value systems are active for this analysis. Flag items \
that rely on assumptions from these worldviews:

{modules}\
"""


def _format_belief_module(module: BeliefSystemModule) -> str:
    """Format a single belief system module for inclusion in a prompt."""
    assumptions = "\n".join(f"  - {a}" for a in module.core_assumptions)
    header = f"- **{module.display_name}** ({module.label}): {module.description}"
    return f"{header}\n  Core assumptions:\n{assumptions}"


def build_extraction_messages(
    segment: TranscriptSegment,
    video_id: str,
    categories: list[VideoCategory] | None = None,
    belief_modules: list[BeliefSystemModule] | None = None,
) -> list[ChatMessage]:
    """Build the chat messages for item extraction.

    Args:
        segment: Transcript segment to extract items from.
        video_id: YouTube video ID for evidence anchoring.
        categories: Optional video categories for context.
        belief_modules: Optional belief system modules for flagging.

    Returns:
        A list of message dicts (system, user) suitable for litellm.completion().
    """
    system = EXTRACTION_SYSTEM_PROMPT

    if categories:
        cat_str = ", ".join(c.value for c in categories)
        system += _CATEGORIES_SECTION.format(categories=cat_str)

    if belief_modules:
        modules_str = "\n\n".join(_format_belief_module(m) for m in belief_modules)
        system += _BELIEF_SYSTEMS_SECTION.format(modules=modules_str)

    user_content = (
        f"Video ID: {video_id}\n"
        f"Segment time range: {segment.start_ms}ms – {segment.end_ms}ms\n\n"
        f"Transcript:\n{segment.text}"
    )

    return [_system_msg(system), _user_msg(user_content)]
