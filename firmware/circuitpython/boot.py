# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Enable USB CDC data channel for serial communication with the host."""

import usb_cdc

usb_cdc.enable(console=True, data=True)
