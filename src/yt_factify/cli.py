# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI entry point for yt-factify."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import click

from yt_factify import __version__
from yt_factify.config import load_config
from yt_factify.logging import get_logger, setup_logging

# Exit codes
EXIT_SUCCESS = 0
EXIT_GENERAL = 1
EXIT_TRANSCRIPT = 2
EXIT_LLM = 3
EXIT_VALIDATION = 4


@click.group()
def cli() -> None:
    """yt-factify: Extract facts and quotes from YouTube videos."""


@cli.command()
def version() -> None:
    """Print yt-factify version."""
    click.echo(f"yt-factify {__version__}")


@cli.command()
@click.argument("video", type=str)
@click.option("--model", default=None, help="LLM model identifier.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default=None,
    help="Output format (default: json).",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(),
    default=None,
    help="Output file path (default: stdout).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Config file path.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Logging verbosity (default: INFO).",
)
@click.option(
    "--modules-dir",
    type=click.Path(exists=True),
    default=None,
    help="Belief system modules directory.",
)
@click.option(
    "--quote-mismatch",
    type=click.Choice(["reject", "downgrade"]),
    default=None,
    help="Quote mismatch behavior (default: reject).",
)
@click.option(
    "--segment-seconds",
    type=int,
    default=None,
    help="Target segment length in seconds (default: 45).",
)
@click.option("--api-base", default=None, help="LLM API base URL.")
@click.option("--api-key", default=None, help="LLM API key (prefer env var YT_FACTIFY_API_KEY).")
@click.option("--temperature", type=float, default=None, help="LLM temperature (default: 0.0).")
@click.option(
    "--max-concurrency",
    type=int,
    default=None,
    help="Maximum concurrent LLM requests (default: 3).",
)
@click.option(
    "--initial-concurrency",
    type=int,
    default=None,
    help="Starting concurrency; promotes to max organically (default: max-concurrency).",
)
@click.option(
    "--language",
    "languages",
    multiple=True,
    help="Transcript language code (repeatable, default: en).",
)
def extract(video: str, **kwargs: Any) -> None:
    """Extract facts, quotes, and claims from a YouTube video."""
    cli_overrides: dict[str, Any] = {}
    if kwargs.get("output_format") is not None:
        cli_overrides["output_format"] = kwargs["output_format"]
    if kwargs.get("output_path") is not None:
        cli_overrides["output_path"] = kwargs["output_path"]
    if kwargs.get("log_level") is not None:
        cli_overrides["log_level"] = kwargs["log_level"]
    if kwargs.get("modules_dir") is not None:
        cli_overrides["modules_dir"] = kwargs["modules_dir"]
    if kwargs.get("quote_mismatch") is not None:
        cli_overrides["quote_mismatch"] = kwargs["quote_mismatch"]
    if kwargs.get("segment_seconds") is not None:
        cli_overrides["segment_seconds"] = kwargs["segment_seconds"]
    if kwargs.get("api_base") is not None:
        cli_overrides["api_base"] = kwargs["api_base"]
    if kwargs.get("api_key") is not None:
        cli_overrides["api_key"] = kwargs["api_key"]
    if kwargs.get("temperature") is not None:
        cli_overrides["temperature"] = kwargs["temperature"]
    if kwargs.get("model") is not None:
        cli_overrides["model"] = kwargs["model"]
    if kwargs.get("max_concurrency") is not None:
        cli_overrides["max_concurrent_requests"] = kwargs["max_concurrency"]
    if kwargs.get("initial_concurrency") is not None:
        cli_overrides["initial_concurrent_requests"] = kwargs["initial_concurrency"]
    if kwargs.get("languages"):
        cli_overrides["languages"] = list(kwargs["languages"])

    config_file = Path(kwargs["config_path"]) if kwargs.get("config_path") else None
    config = load_config(cli_overrides=cli_overrides, config_path=config_file)

    setup_logging(config.log_level)
    log = get_logger("cli")

    log.info("starting extraction", video=video, model=config.model)

    # Resolve video ID from URL or plain ID
    video_id = _parse_video_id(video)

    # Run the pipeline
    from yt_factify.pipeline import PipelineError, run_pipeline
    from yt_factify.rendering import render_json, render_markdown, write_output
    from yt_factify.transcript import EmptyTranscriptError, TranscriptFetchError

    try:
        result = asyncio.run(run_pipeline(video_id, config))
    except PipelineError as exc:
        error_msg = str(exc)
        exit_code = _classify_error(error_msg)
        log.error("pipeline_failed", error=error_msg, exit_code=exit_code)
        click.echo(f"Error: {error_msg}", err=True)
        sys.exit(exit_code)
    except (TranscriptFetchError, EmptyTranscriptError) as exc:
        log.error("transcript_error", error=str(exc))
        click.echo(f"Error: {exc}", err=True)
        sys.exit(EXIT_TRANSCRIPT)
    except Exception as exc:
        log.error("unexpected_error", error=str(exc))
        click.echo(f"Error: {exc}", err=True)
        sys.exit(EXIT_GENERAL)

    # Render output
    fmt = config.output_format
    output = render_markdown(result) if fmt == "markdown" else render_json(result)

    # Write to file or stdout
    if config.output_path:
        out = _resolve_output_path(config.output_path, video_id, fmt)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_output(output, out)
        click.echo(f"Output written to {out}")
    else:
        click.echo(output)


def _resolve_output_path(
    raw: str,
    video_id: str,
    fmt: str,
) -> Path:
    """Resolve the output path, auto-naming when *raw* is a directory.

    Rules:
        - Trailing ``/`` → treat as directory, auto-generate filename.
        - Existing directory → auto-generate filename.
        - Otherwise → use as-is (explicit filename).

    Auto-generated filenames use ``<video_id>.<ext>`` where *ext* is
    ``md`` for markdown and ``json`` for everything else.
    """
    p = Path(raw)
    is_dir = raw.endswith(("/", "\\")) or p.is_dir()
    if is_dir:
        ext = "md" if fmt == "markdown" else "json"
        return p / f"{video_id}.{ext}"
    return p


def _parse_video_id(video: str) -> str:
    """Extract video ID from a YouTube URL or return as-is."""
    import re

    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, video)
        if match:
            return match.group(1)
    return video


def _classify_error(error_msg: str) -> int:
    """Map a PipelineError message to an exit code."""
    lower = error_msg.lower()
    if "transcript" in lower or "fetch" in lower:
        return EXIT_TRANSCRIPT
    if "classify" in lower or "extract" in lower or "credibility" in lower:
        return EXIT_LLM
    if "validat" in lower:
        return EXIT_VALIDATION
    return EXIT_GENERAL
