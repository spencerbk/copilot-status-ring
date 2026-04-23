# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Shared CDC data channel reference.

boot.py sets ``cdc_data`` during USB enumeration.
main.py reads it to determine the serial input source.
"""

cdc_data = None  # Set by boot.py if USB CDC is available
