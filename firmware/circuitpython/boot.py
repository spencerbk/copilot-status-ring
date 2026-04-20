# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Enable USB CDC data channel and set custom USB identification."""

import supervisor
import usb_cdc

supervisor.set_usb_identification(product="Copilot Command Ring")
usb_cdc.enable(console=True, data=True)
