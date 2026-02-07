# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Prompt template utilities for yt-factify."""

from __future__ import annotations

import hashlib

# Message type used by litellm: list of {"role": ..., "content": ...} dicts.
type ChatMessage = dict[str, str]


def hash_prompts(*prompt_texts: str) -> str:
    """Compute SHA-256 of concatenated prompt templates for audit trail.

    Args:
        *prompt_texts: One or more prompt template strings.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    combined = "\n---\n".join(prompt_texts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _system_msg(content: str) -> ChatMessage:
    """Create a system message dict."""
    return {"role": "system", "content": content}


def _user_msg(content: str) -> ChatMessage:
    """Create a user message dict."""
    return {"role": "user", "content": content}
