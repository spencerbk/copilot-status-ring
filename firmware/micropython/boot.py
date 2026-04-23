# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Configure an optional USB CDC data channel before main.py runs.

This keeps host communication on a dedicated CDC endpoint when supported while
leaving the built-in REPL available on its own USB serial interface.
"""

import ring_cdc


def _set_usb_product_string() -> None:
    """Best-effort USB product string update for boards that expose it."""
    try:
        import machine  # type: ignore[import]

        usb_device = getattr(machine, "USBDevice", None)
        if usb_device is None:
            return

        if hasattr(usb_device, "product"):
            usb_device.product = "Copilot Command Ring"
            print("USB product string set to Copilot Command Ring")
            return

        if hasattr(usb_device, "PRODUCT"):
            usb_device.PRODUCT = "Copilot Command Ring"
            print("USB product string set to Copilot Command Ring")
    except Exception as exc:
        print("USB product string not updated:", exc)


_set_usb_product_string()

try:
    import usb.device  # type: ignore[import]
    from usb.device.cdc import CDCInterface  # type: ignore[import]

    cdc = CDCInterface()
    cdc.init(timeout=0)
    usb.device.get().init(cdc, builtin_driver=True)
    ring_cdc.cdc_data = cdc
    print("USB CDC data channel enabled")
except Exception as exc:
    print("USB CDC data channel unavailable:", exc)
