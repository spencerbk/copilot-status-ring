# MicroPython Libraries

This directory is for micropython-lib packages installed on the board.

## Required packages

Install via `mpremote`:

```
mpremote mip install usb-device-cdc
```

This installs the USB CDC device support needed for the dedicated serial data channel. On boards without native USB device support (ESP32-C3/C6), this package is optional — the firmware falls back to `sys.stdin`.
