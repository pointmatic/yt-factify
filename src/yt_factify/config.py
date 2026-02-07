# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Configuration loading for yt-factify.

Precedence (highest to lowest):
1. CLI flag overrides
2. Environment variables (prefixed with YT_FACTIFY_)
3. TOML config file
4. Built-in defaults
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from yt_factify.models import QuoteMismatchBehavior

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "yt-factify" / "config.toml"


class AppConfig(BaseModel):
    """Application configuration."""

    model: str = ""
    api_base: str | None = None
    api_key: str | None = None
    temperature: float = 0.0
    output_format: str = "json"
    output_path: str | None = None
    log_level: str = "INFO"
    modules_dir: str | None = None
    quote_mismatch: QuoteMismatchBehavior = QuoteMismatchBehavior.REJECT
    segment_seconds: int = Field(default=45, ge=1)
    max_concurrent_requests: int = Field(default=3, ge=1)
    max_retries: int = Field(default=3, ge=0)


ENV_PREFIX = "YT_FACTIFY_"

_ENV_FIELD_MAP: dict[str, str] = {
    "YT_FACTIFY_MODEL": "model",
    "YT_FACTIFY_API_BASE": "api_base",
    "YT_FACTIFY_API_KEY": "api_key",
    "YT_FACTIFY_TEMPERATURE": "temperature",
    "YT_FACTIFY_FORMAT": "output_format",
    "YT_FACTIFY_LOG_LEVEL": "log_level",
    "YT_FACTIFY_MODULES_DIR": "modules_dir",
    "YT_FACTIFY_QUOTE_MISMATCH": "quote_mismatch",
    "YT_FACTIFY_SEGMENT_SECONDS": "segment_seconds",
    "YT_FACTIFY_MAX_CONCURRENT": "max_concurrent_requests",
    "YT_FACTIFY_MAX_RETRIES": "max_retries",
}


def _read_toml_config(config_path: Path) -> dict[str, Any]:
    """Read a TOML config file and return its contents as a dict.

    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    if not config_path.is_file():
        return {}
    try:
        with config_path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError, OSError:
        return {}


def _read_env_vars() -> dict[str, Any]:
    """Read configuration from environment variables."""
    result: dict[str, Any] = {}
    for env_key, field_name in _ENV_FIELD_MAP.items():
        value = os.environ.get(env_key)
        if value is not None:
            result[field_name] = value
    return result


def load_config(
    cli_overrides: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> AppConfig:
    """Load configuration with precedence: CLI > env > file > defaults.

    Args:
        cli_overrides: Dict of values from CLI flags. Keys with ``None``
            values are ignored (treated as "not provided").
        config_path: Path to a TOML config file. Falls back to
            ``~/.config/yt-factify/config.toml`` if not specified.

    Returns:
        A validated ``AppConfig`` instance.
    """
    effective_path = config_path or DEFAULT_CONFIG_PATH

    file_values = _read_toml_config(effective_path)
    env_values = _read_env_vars()

    # Merge: file < env < cli  (later dict wins)
    merged: dict[str, Any] = {}
    merged.update(file_values)
    merged.update(env_values)
    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None:
                merged[key] = value

    return AppConfig(**merged)
