# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Logging utilities — stderr only.

stdout must NEVER be used for logging because Copilot CLI hooks
interpret stdout as control output for preToolUse and permissionRequest events.
"""

import logging
import os
import sys

_LOGGER_NAME = "copilot_command_ring"
_ENV_LOG_LEVEL = "COPILOT_RING_LOG_LEVEL"
_DEFAULT_LEVEL = "WARNING"
_FORMAT = "[copilot-ring] %(levelname)s: %(message)s"

_logger: logging.Logger | None = None


def setup_logging() -> logging.Logger:
    """Configure and return a logger that writes only to stderr."""
    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)

    level_name = os.environ.get(_ENV_LOG_LEVEL, _DEFAULT_LEVEL).upper()
    numeric_level = getattr(logging, level_name, None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.WARNING
        logger.setLevel(numeric_level)
        logger.warning(
            "Invalid %s value %r, defaulting to WARNING",
            _ENV_LOG_LEVEL,
            level_name,
        )
    else:
        logger.setLevel(numeric_level)

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    """Get or create the module logger (lazy initialization)."""
    global _logger  # noqa: PLW0603
    if _logger is None:
        _logger = setup_logging()
    return _logger
