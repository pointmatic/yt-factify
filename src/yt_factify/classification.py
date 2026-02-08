# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Video categorization, bias detection, and credibility assessment."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from yt_factify.config import AppConfig
from yt_factify.llm import llm_completion
from yt_factify.models import (
    BeliefSystemModule,
    BiasProfile,
    CredibilityAssessment,
    CredibilityLabel,
    ExtractedItem,
    NormalizedTranscript,
    VideoCategory,
    VideoClassification,
)
from yt_factify.prompts.classification import (
    build_classification_messages,
)
from yt_factify.prompts.credibility import build_credibility_messages

if TYPE_CHECKING:
    from gentlify import Throttle

logger = structlog.get_logger()


class ClassificationError(Exception):
    """Raised when video classification fails after retries."""


class CredibilityError(Exception):
    """Raised when credibility assessment fails after retries."""


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM response text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(lines)
    return text


def _parse_classification(raw_text: str) -> VideoClassification:
    """Parse LLM classification response into a VideoClassification.

    Args:
        raw_text: Raw JSON text from LLM.

    Returns:
        Validated VideoClassification instance.

    Raises:
        json.JSONDecodeError: If the response is not valid JSON.
        ValueError: If the JSON doesn't match the expected schema.
    """
    data = json.loads(_strip_fences(raw_text))
    if not isinstance(data, dict):
        msg = f"Expected JSON object, got {type(data).__name__}"
        raise ValueError(msg)

    # Validate categories
    raw_categories = data.get("categories", [])
    categories: list[VideoCategory] = []
    for cat in raw_categories:
        try:
            categories.append(VideoCategory(cat))
        except ValueError:
            logger.warning("unknown_category_skipped", category=cat)

    if not categories:
        categories = [VideoCategory.OTHER]

    # Validate bias profile
    raw_bias = data.get("bias_profile", {})
    bias_profile = BiasProfile(
        primary_label=raw_bias.get("primary_label", "unknown"),
        confidence=float(raw_bias.get("confidence", 0.5)),
        rationale=raw_bias.get("rationale", ""),
        implicit_bias_notes=raw_bias.get("implicit_bias_notes", []),
    )

    return VideoClassification(
        categories=categories,
        bias_profile=bias_profile,
    )


def _parse_credibility_assessments(
    raw_text: str,
    items: list[ExtractedItem],
) -> dict[str, CredibilityAssessment]:
    """Parse LLM credibility response into a mapping of item_id to assessment.

    Args:
        raw_text: Raw JSON text from LLM.
        items: Original items for cross-referencing.

    Returns:
        Dict mapping item_id to CredibilityAssessment.

    Raises:
        json.JSONDecodeError: If the response is not valid JSON.
        ValueError: If the JSON is not a list.
    """
    data = json.loads(_strip_fences(raw_text))
    if not isinstance(data, list):
        msg = f"Expected JSON array, got {type(data).__name__}"
        raise ValueError(msg)

    item_ids = {item.id for item in items}
    assessments: dict[str, CredibilityAssessment] = {}

    for raw_assessment in data:
        try:
            item_id = raw_assessment.get("item_id", "")
            if item_id not in item_ids:
                logger.warning(
                    "credibility_unknown_item_id",
                    item_id=item_id,
                )
                continue

            label = CredibilityLabel(raw_assessment["label"])
            assessment = CredibilityAssessment(
                label=label,
                confidence=float(raw_assessment.get("confidence", 0.5)),
                rationale=raw_assessment.get("rationale", ""),
                relevant_belief_systems=raw_assessment.get("relevant_belief_systems", []),
            )
            assessments[item_id] = assessment
        except KeyError, ValueError:
            logger.warning(
                "skipping_invalid_credibility_assessment",
                raw=raw_assessment,
            )

    return assessments


async def classify_video(
    transcript: NormalizedTranscript,
    config: AppConfig,
    throttle: Throttle | None = None,
) -> VideoClassification:
    """Classify video category and detect bias/slant via LLM.

    For very long transcripts, the prompt builder automatically samples
    representative segments (first, middle, last).

    Args:
        transcript: Normalized transcript to classify.
        config: Application configuration.

    Returns:
        VideoClassification with categories and bias profile.

    Raises:
        ClassificationError: If classification fails after retries.
    """
    messages = build_classification_messages(transcript)

    max_attempts = min(config.max_retries, 2)
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            content = await llm_completion(
                messages=messages,
                config=config,
                max_attempts=1,
                context="classification",
                throttle=throttle,
            )

            result = _parse_classification(content)

            logger.info(
                "video_classified",
                video_id=transcript.video_id,
                categories=[c.value for c in result.categories],
                bias_label=result.bias_profile.primary_label,
                attempt=attempt + 1,
            )
            return result

        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_error = exc
            logger.warning(
                "classification_parse_error",
                video_id=transcript.video_id,
                attempt=attempt + 1,
                error=str(exc),
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "classification_llm_error",
                video_id=transcript.video_id,
                attempt=attempt + 1,
                error=str(exc),
            )

    raise ClassificationError(
        f"Failed to classify video {transcript.video_id} "
        f"after {max_attempts} attempts: {last_error}"
    )


async def assess_credibility(
    items: list[ExtractedItem],
    belief_modules: list[BeliefSystemModule],
    config: AppConfig,
    throttle: Throttle | None = None,
) -> list[ExtractedItem]:
    """Add credibility assessments to extracted items via LLM.

    Args:
        items: Extracted items to assess.
        belief_modules: Belief system modules for context.
        config: Application configuration.

    Returns:
        Items with credibility field populated. Items that could not
        be assessed retain ``credibility=None``.

    Raises:
        CredibilityError: If assessment fails after retries.
    """
    if not items:
        return []

    messages = build_credibility_messages(
        items=items,
        belief_modules=belief_modules or None,
    )

    max_attempts = min(config.max_retries, 2)
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            content = await llm_completion(
                messages=messages,
                config=config,
                max_attempts=1,
                context="credibility",
                throttle=throttle,
            )

            assessments = _parse_credibility_assessments(content, items)

            # Apply assessments to items
            result: list[ExtractedItem] = []
            for item in items:
                if item.id in assessments:
                    updated = item.model_copy(update={"credibility": assessments[item.id]})
                    result.append(updated)
                else:
                    logger.warning(
                        "no_credibility_for_item",
                        item_id=item.id,
                    )
                    result.append(item)

            logger.info(
                "credibility_assessed",
                total_items=len(items),
                assessed=len(assessments),
                attempt=attempt + 1,
            )
            return result

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "credibility_parse_error",
                attempt=attempt + 1,
                error=str(exc),
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "credibility_llm_error",
                attempt=attempt + 1,
                error=str(exc),
            )

    raise CredibilityError(
        f"Failed to assess credibility after {max_attempts} attempts: {last_error}"
    )
