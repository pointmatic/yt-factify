# Copyright (c) 2026 Pointmatic
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Belief/value system module loading and management."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import structlog

from yt_factify.models import BeliefSystemModule

logger = structlog.get_logger()

_BUILTIN_MODULES_PACKAGE = "yt_factify.modules"


def load_belief_modules(modules_dir: Path) -> list[BeliefSystemModule]:
    """Load belief/value system module definitions from JSON files.

    Each file must conform to the ``BeliefSystemModule`` schema.
    Invalid files are logged and skipped.

    Args:
        modules_dir: Directory containing module JSON files.

    Returns:
        List of validated modules. Invalid files are excluded.
    """
    if not modules_dir.is_dir():
        logger.warning("modules_dir_not_found", path=str(modules_dir))
        return []

    modules: list[BeliefSystemModule] = []
    for path in sorted(modules_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            module = BeliefSystemModule.model_validate(raw)
            modules.append(module)
            logger.debug("module_loaded", label=module.label, path=str(path))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "module_skipped_invalid",
                path=str(path),
                error=str(exc),
            )

    logger.info("belief_modules_loaded", count=len(modules))
    return modules


def get_builtin_modules() -> list[BeliefSystemModule]:
    """Return the built-in set of belief/value system modules.

    Built-in modules are shipped as JSON files in the
    ``yt_factify/modules/`` package directory.

    Returns:
        List of built-in modules.
    """
    modules: list[BeliefSystemModule] = []

    try:
        module_files = resources.files(_BUILTIN_MODULES_PACKAGE)
    except (ModuleNotFoundError, TypeError):
        logger.warning("builtin_modules_package_not_found")
        return []

    for item in sorted(module_files.iterdir(), key=lambda f: f.name):
        if not str(item.name).endswith(".json"):
            continue
        try:
            raw_text = item.read_text(encoding="utf-8")
            raw = json.loads(raw_text)
            module = BeliefSystemModule.model_validate(raw)
            modules.append(module)
            logger.debug("builtin_module_loaded", label=module.label)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "builtin_module_skipped_invalid",
                name=str(item.name),
                error=str(exc),
            )

    logger.info("builtin_modules_loaded", count=len(modules))
    return modules
