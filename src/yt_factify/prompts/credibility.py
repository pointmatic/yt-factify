# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Credibility assessment prompt templates for yt-factify."""

from __future__ import annotations

from yt_factify.models import BeliefSystemModule, ExtractedItem
from yt_factify.prompts import ChatMessage, _system_msg, _user_msg

CREDIBILITY_SYSTEM_PROMPT = """\
You are a credibility analyst. Given a list of extracted items from a YouTube \
video transcript, assess the credibility of each item using your general \
knowledge.

## Credibility Labels

- **well_established**: Widely accepted, supported by strong evidence and \
scientific consensus.
- **credible**: Plausible and consistent with available evidence, but not \
universally established.
- **disputed**: Actively debated among experts or contradicted by some evidence.
- **dubious**: Likely false, contradicted by strong evidence, or based on \
known misinformation.
- **unassessable**: Cannot be evaluated — too vague, subjective, or outside \
the scope of general knowledge.

## Assessment Rules

1. `direct_quote` items: Assess the factual accuracy of the quoted claim, \
not whether the person said it.
2. `speaker_opinion` items: Generally label as `unassessable` unless the \
opinion contains a verifiable factual claim.
3. `prediction` items: Label as `unassessable` unless the prediction \
contradicts established knowledge.
4. Consider belief system context when provided — note if an item's \
credibility depends on a particular worldview.

## Output Schema

Return a JSON array with one object per item:
```json
[
  {{
    "item_id": "<id of the extracted item>",
    "label": "<credibility_label>",
    "confidence": <float 0.0-1.0>,
    "rationale": "<brief explanation>",
    "relevant_belief_systems": ["<module_label>", ...]
  }}
]
```

Return ONLY the JSON array. No commentary, no markdown fences.\
"""

_BELIEF_SYSTEMS_SECTION = """\

## Active Belief/Value Systems

Consider these worldviews when assessing credibility. If an item's truth \
value depends on assumptions from one of these systems, note it in \
`relevant_belief_systems`:

{modules}\
"""


def _format_belief_module(module: BeliefSystemModule) -> str:
    """Format a single belief system module for inclusion in a prompt."""
    assumptions = "\n".join(f"  - {a}" for a in module.core_assumptions)
    return (
        f"- **{module.display_name}** ({module.label}): "
        f"{module.description}\n  Core assumptions:\n{assumptions}"
    )


def _format_item_for_prompt(item: ExtractedItem) -> str:
    """Format a single extracted item for inclusion in the user prompt."""
    speaker_str = f" (speaker: {item.speaker})" if item.speaker else ""
    return (
        f"- ID: {item.id}\n"
        f"  Type: {item.type.value}{speaker_str}\n"
        f"  Content: {item.content}\n"
        f'  Evidence: "{item.transcript_evidence.text}"'
    )


def build_credibility_messages(
    items: list[ExtractedItem],
    belief_modules: list[BeliefSystemModule] | None = None,
) -> list[ChatMessage]:
    """Build chat messages for credibility assessment.

    Args:
        items: Extracted items to assess.
        belief_modules: Optional belief system modules for context.

    Returns:
        A list of message dicts (system, user) suitable for litellm.completion().
    """
    system = CREDIBILITY_SYSTEM_PROMPT

    if belief_modules:
        modules_str = "\n\n".join(_format_belief_module(m) for m in belief_modules)
        system += _BELIEF_SYSTEMS_SECTION.format(modules=modules_str)

    items_str = "\n\n".join(_format_item_for_prompt(item) for item in items)
    user_content = f"Assess the credibility of these extracted items:\n\n{items_str}"

    return [_system_msg(system), _user_msg(user_content)]
