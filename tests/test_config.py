# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for yt_factify.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from yt_factify.config import AppConfig, load_config
from yt_factify.models import QuoteMismatchBehavior


class TestAppConfigDefaults:
    def test_defaults(self) -> None:
        config = AppConfig()
        assert config.model == ""
        assert config.api_base is None
        assert config.api_key is None
        assert config.temperature == 0.0
        assert config.output_format == "json"
        assert config.output_path is None
        assert config.log_level == "INFO"
        assert config.modules_dir is None
        assert config.quote_mismatch == QuoteMismatchBehavior.REJECT
        assert config.segment_seconds == 45
        assert config.max_concurrent_requests == 3
        assert config.max_retries == 3

    def test_segment_seconds_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            AppConfig(segment_seconds=0)

    def test_max_retries_can_be_zero(self) -> None:
        config = AppConfig(max_retries=0)
        assert config.max_retries == 0


class TestLoadConfigFromFile:
    def test_loads_toml_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'model = "gpt-4o"\ntemperature = 0.5\nlog_level = "DEBUG"\n'
        )
        config = load_config(config_path=config_file)
        assert config.model == "gpt-4o"
        assert config.temperature == 0.5
        assert config.log_level == "DEBUG"

    def test_missing_config_file_uses_defaults(self, tmp_path: Path) -> None:
        config = load_config(config_path=tmp_path / "nonexistent.toml")
        assert config.model == ""
        assert config.temperature == 0.0

    def test_invalid_toml_uses_defaults(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad.toml"
        config_file.write_text("this is not valid toml {{{{")
        config = load_config(config_path=config_file)
        assert config.model == ""


class TestLoadConfigEnvVars:
    def test_env_vars_override_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YT_FACTIFY_MODEL", "claude-3")
        monkeypatch.setenv("YT_FACTIFY_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("YT_FACTIFY_SEGMENT_SECONDS", "60")
        config = load_config(config_path=Path("/nonexistent/path.toml"))
        assert config.model == "claude-3"
        assert config.log_level == "WARNING"
        assert config.segment_seconds == 60

    def test_env_vars_override_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('model = "gpt-4o"\n')
        monkeypatch.setenv("YT_FACTIFY_MODEL", "claude-3")
        config = load_config(config_path=config_file)
        assert config.model == "claude-3"


class TestLoadConfigCLIOverrides:
    def test_cli_overrides_env_and_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('model = "gpt-4o"\nlog_level = "DEBUG"\n')
        monkeypatch.setenv("YT_FACTIFY_MODEL", "claude-3")
        config = load_config(
            cli_overrides={"model": "gemini-pro", "log_level": "ERROR"},
            config_path=config_file,
        )
        assert config.model == "gemini-pro"
        assert config.log_level == "ERROR"

    def test_cli_none_values_ignored(self) -> None:
        config = load_config(
            cli_overrides={"model": None, "log_level": "WARNING"},
            config_path=Path("/nonexistent/path.toml"),
        )
        assert config.model == ""
        assert config.log_level == "WARNING"

    def test_full_precedence_chain(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'model = "file-model"\nlog_level = "DEBUG"\ntemperature = 0.1\n'
        )
        monkeypatch.setenv("YT_FACTIFY_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("YT_FACTIFY_TEMPERATURE", "0.5")
        config = load_config(
            cli_overrides={"temperature": 0.9},
            config_path=config_file,
        )
        # model: file (no env, no cli)
        assert config.model == "file-model"
        # log_level: env overrides file
        assert config.log_level == "WARNING"
        # temperature: cli overrides env overrides file
        assert config.temperature == 0.9
