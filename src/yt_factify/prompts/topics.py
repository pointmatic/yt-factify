# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Topic threading prompt templates for yt-factify."""

from __future__ import annotations

from yt_factify.models import ExtractedItem
from yt_factify.prompts import ChatMessage, _system_msg, _user_msg

TOPIC_THREADING_SYSTEM_PROMPT = """\
You are a topic analyst. Given a list of extracted items from a YouTube \
video transcript, cluster them into topic threads — named groups of items \
that share a common subject.

## Rules

1. Each thread should represent a distinct topic or subject discussed in \
the video.
2. An item may belong to multiple threads if it spans multiple topics.
3. Items that do not fit any clear topic may be excluded from all threads.
4. Use short, descriptive labels in snake_case (e.g., `ai_safety`, \
`python_data_classes`).
5. Provide a human-readable display name and a 1–2 sentence summary for \
each thread.
6. Reference items by their `id` field.

## Output Schema

Return a JSON array of topic thread objects:
```json
[
  {{
    "label": "<snake_case_identifier>",
    "display_name": "<Human-Readable Name>",
    "summary": "<1-2 sentence description of this topic thread>",
    "item_ids": ["<item_id>", ...]
  }}
]
```

Return ONLY the JSON array. No commentary, no markdown fences.\
"""


def _format_item_for_clustering(item: ExtractedItem) -> str:
    """Format a single extracted item for the topic clustering prompt."""
    speaker_str = f" (speaker: {item.speaker})" if item.speaker else ""
    return (
        f"- ID: {item.id}\n"
        f"  Type: {item.type.value}{speaker_str}\n"
        f"  Content: {item.content}\n"
        f"  Time: {item.transcript_evidence.start_ms}ms"
        f"–{item.transcript_evidence.end_ms}ms"
    )


def build_topic_threading_messages(
    items: list[ExtractedItem],
) -> list[ChatMessage]:
    """Build chat messages for topic thread clustering.

    Args:
        items: Extracted items to cluster into topics.

    Returns:
        A list of message dicts (system, user) suitable for
        litellm.completion().
    """
    items_str = "\n\n".join(
        _format_item_for_clustering(item) for item in items
    )
    user_content = (
        f"Cluster these {len(items)} extracted items into topic threads:"
        f"\n\n{items_str}"
    )

    return [_system_msg(TOPIC_THREADING_SYSTEM_PROMPT), _user_msg(user_content)]
