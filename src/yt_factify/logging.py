# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Structured logging setup for yt-factify using structlog."""

from __future__ import annotations

import logging

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON-compatible structured output.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger, optionally bound to a name.

    Args:
        name: Optional logger name (typically the module name).

    Returns:
        A bound structlog logger instance.
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger()
    if name:
        logger = logger.bind(module=name)
    return logger
