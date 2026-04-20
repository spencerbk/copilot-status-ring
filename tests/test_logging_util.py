# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Unit tests for the logging utility module."""

from __future__ import annotations

import logging
from unittest.mock import patch

import copilot_command_ring.logging_util as logging_util


class TestInvalidLogLevel:
    """Invalid COPILOT_RING_LOG_LEVEL falls back to WARNING."""

    def test_invalid_level_defaults_to_warning(self) -> None:
        # Reset cached logger so setup_logging runs again
        logging_util._logger = None

        with patch.dict(
            "os.environ",
            {"COPILOT_RING_LOG_LEVEL": "BOGUS_LEVEL"},
        ):
            logger = logging_util.get_logger()

        assert logger.level == logging.WARNING

        # Cleanup: reset so other tests get a fresh logger
        logging_util._logger = None
