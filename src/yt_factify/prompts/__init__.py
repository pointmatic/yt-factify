# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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
