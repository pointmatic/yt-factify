# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pydantic data models for yt-factify."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Core Enums
# ---------------------------------------------------------------------------


class ItemType(StrEnum):
    DIRECT_QUOTE = "direct_quote"
    TRANSCRIPT_FACT = "transcript_fact"
    GENERAL_KNOWLEDGE = "general_knowledge"
    SPEAKER_OPINION = "speaker_opinion"
    UNVERIFIED_CLAIM = "unverified_claim"
    PREDICTION = "prediction"


class CredibilityLabel(StrEnum):
    WELL_ESTABLISHED = "well_established"
    CREDIBLE = "credible"
    DISPUTED = "disputed"
    DUBIOUS = "dubious"
    UNASSESSABLE = "unassessable"


class VideoCategory(StrEnum):
    NEWS = "news"
    ENTERTAINMENT = "entertainment"
    MUSIC_VIDEO = "music_video"
    COMEDY_SATIRE = "comedy_satire"
    INTERVIEW = "interview"
    DOCUMENTARY = "documentary"
    TUTORIAL = "tutorial"
    OPINION_EDITORIAL = "opinion_editorial"
    POLITICAL_SPEECH = "political_speech"
    PANEL_DISCUSSION = "panel_discussion"
    OTHER = "other"


class QuoteMismatchBehavior(StrEnum):
    REJECT = "reject"
    DOWNGRADE = "downgrade"


# ---------------------------------------------------------------------------
# Transcript Models
# ---------------------------------------------------------------------------


class TranscriptSegmentRaw(BaseModel):
    """A single segment from yt-fetch transcript output."""

    text: str
    start_ms: int
    end_ms: int


class RawTranscript(BaseModel):
    """Raw transcript as received from yt-fetch."""

    video_id: str
    segments: list[TranscriptSegmentRaw]
    language: str | None = None


class NormalizedSegment(BaseModel):
    """A normalized transcript segment with hash."""

    text: str
    start_ms: int
    end_ms: int
    hash: str  # SHA-256 of normalized text


class NormalizedTranscript(BaseModel):
    """Normalized transcript with full-text hash."""

    video_id: str
    full_text: str
    hash: str  # SHA-256 of full normalized text
    segments: list[NormalizedSegment]
    language: str | None = None


class TranscriptSegment(BaseModel):
    """A segment prepared for LLM processing (may span multiple NormalizedSegments)."""

    text: str
    start_ms: int
    end_ms: int
    hash: str
    source_segment_indices: list[int]


# ---------------------------------------------------------------------------
# Extraction Models
# ---------------------------------------------------------------------------


class TranscriptEvidence(BaseModel):
    """Links an extracted item to its transcript source."""

    video_id: str
    start_ms: int
    end_ms: int
    text: str  # Exact transcript span


class BeliefSystemFlag(BaseModel):
    """Flags an item as relying on a specific worldview."""

    module_label: str
    note: str


class CredibilityAssessment(BaseModel):
    """Credibility assessment for an extracted item."""

    label: CredibilityLabel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    relevant_belief_systems: list[str] = Field(default_factory=list)


class ExtractedItem(BaseModel):
    """A single extracted item (fact, quote, opinion, etc.)."""

    id: str
    type: ItemType
    content: str
    speaker: str | None = None
    transcript_evidence: TranscriptEvidence
    credibility: CredibilityAssessment | None = None
    belief_system_flags: list[BeliefSystemFlag] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Classification Models
# ---------------------------------------------------------------------------


class BiasProfile(BaseModel):
    """Bias/slant assessment for a video."""

    primary_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    implicit_bias_notes: list[str] = Field(default_factory=list)


class VideoClassification(BaseModel):
    """Video categorization and bias profile."""

    categories: list[VideoCategory]
    bias_profile: BiasProfile


# ---------------------------------------------------------------------------
# Belief System Module
# ---------------------------------------------------------------------------


class BeliefSystemModule(BaseModel):
    """A pluggable worldview/belief system definition."""

    label: str
    display_name: str
    description: str
    core_assumptions: list[str]
    example_claims: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Topic Thread Models
# ---------------------------------------------------------------------------


class TopicTimeSpan(BaseModel):
    """A time range where a topic appears in the video."""

    start_ms: int
    end_ms: int


class TopicThread(BaseModel):
    """A named cluster of extracted items sharing a common subject."""

    label: str
    display_name: str
    summary: str
    item_ids: list[str]
    timeline: list[TopicTimeSpan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Output Models
# ---------------------------------------------------------------------------


class VideoInfo(BaseModel):
    """Video metadata in the output."""

    video_id: str
    title: str | None = None
    url: str
    transcript_hash: str
    fetched_at: datetime


class AuditBundle(BaseModel):
    """Audit trail for traceability."""

    model_id: str
    model_version: str | None = None
    prompt_templates_hash: str
    processing_timestamp: datetime
    segment_hashes: list[str]
    yt_factify_version: str


class ValidationResult(BaseModel):
    """Result of post-extraction validation."""

    accepted: list[ExtractedItem]
    rejected: list[ExtractedItem] = Field(default_factory=list)
    downgraded: list[ExtractedItem] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Top-level output of the yt-factify pipeline."""

    video: VideoInfo
    classification: VideoClassification
    items: list[ExtractedItem]
    topic_threads: list[TopicThread] = Field(default_factory=list)
    audit: AuditBundle
