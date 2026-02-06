# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI entry point for yt-factify."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from yt_factify import __version__
from yt_factify.config import load_config
from yt_factify.logging import get_logger, setup_logging


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
    "--output", "-o", "output_path",
    type=click.Path(),
    default=None,
    help="Output file path (default: stdout).",
)
@click.option(
    "--config", "config_path",
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

    config_file = Path(kwargs["config_path"]) if kwargs.get("config_path") else None
    config = load_config(cli_overrides=cli_overrides, config_path=config_file)

    setup_logging(config.log_level)
    log = get_logger("cli")

    log.info("starting extraction", video=video, model=config.model)
    # Pipeline execution will be wired in Story D.a
    click.echo(f"[placeholder] Would extract from: {video}")
