# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""yt-factify: Extract auditable facts, quotes, topics, and biases from YouTube transcripts.

Library API
-----------

Async usage::

    from yt_factify import extract, AppConfig

    result = await extract("dQw4w9WgXcQ")

    # With custom config
    config = AppConfig(model="gpt-4o", temperature=0.2)
    result = await extract("dQw4w9WgXcQ", config=config)

Sync usage::

    from yt_factify import extract_sync

    result = extract_sync("dQw4w9WgXcQ")

Output rendering::

    from yt_factify import render_json, render_markdown

    json_str = render_json(result)
    md_str = render_markdown(result)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

__version__ = "0.5.2"


# Re-exports for public API
from yt_factify.config import AppConfig as AppConfig
from yt_factify.models import ExtractionResult as ExtractionResult
from yt_factify.pipeline import PipelineError as PipelineError
from yt_factify.pipeline import run_pipeline
from yt_factify.rendering import render_json as render_json
from yt_factify.rendering import render_markdown as render_markdown


async def extract(
    video_id: str,
    config: AppConfig | None = None,
) -> ExtractionResult:
    """Extract facts, quotes, and claims from a YouTube video.

    This is the primary library API entry point. It wraps
    ``run_pipeline()`` with sensible defaults.

    Args:
        video_id: YouTube video ID (e.g., ``"dQw4w9WgXcQ"``).
        config: Optional ``AppConfig``. If not provided, loads
            configuration from environment variables and defaults.

    Returns:
        An ``ExtractionResult`` containing all extracted items,
        topic threads, classification, and audit bundle.

    Raises:
        PipelineError: If any pipeline stage fails.

    Example::

        result = await extract("dQw4w9WgXcQ")
        for item in result.items:
            print(f"{item.type}: {item.content}")
    """
    if config is None:
        from yt_factify.config import load_config

        config = load_config()

    return await run_pipeline(video_id, config)


def extract_sync(
    video_id: str,
    config: AppConfig | None = None,
) -> ExtractionResult:
    """Synchronous wrapper for :func:`extract`.

    Convenience function for non-async callers. Creates a new event
    loop and runs the async ``extract()`` function.

    Args:
        video_id: YouTube video ID.
        config: Optional ``AppConfig``.

    Returns:
        An ``ExtractionResult``.

    Raises:
        PipelineError: If any pipeline stage fails.

    Example::

        result = extract_sync("dQw4w9WgXcQ")
        print(render_json(result))
    """
    return asyncio.run(extract(video_id, config=config))
