# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Compatibility layer exposing a CircuitPython-like NeoPixel API on MicroPython."""

# pylint: disable=import-error
import neopixel  # type: ignore[import]
from machine import Pin  # type: ignore[import]

GRB = (1, 0, 2)


class NeoPixelCompat:
    """Wrap MicroPython's NeoPixel with stored brightness and pixel access."""

    def __init__(
        self,
        pin_number: int,
        num_pixels: int,
        brightness: float = 0.04,
        pixel_order=GRB,
    ) -> None:
        self._num_pixels = num_pixels
        self._pixel_order = pixel_order
        self._pixels = neopixel.NeoPixel(Pin(pin_number), num_pixels)
        self._colors = bytearray(num_pixels * 3)
        self._brightness = 0.0
        self._brightness_dirty = False
        self._cached_r = -1
        self._cached_g = -1
        self._cached_b = -1
        self._cached_scaled = (0, 0, 0)
        self.brightness = brightness

    @property
    def brightness(self) -> float:
        """Return the stored brightness scalar."""
        return self._brightness

    @brightness.setter
    def brightness(self, value: float) -> None:
        if value < 0.0:
            value = 0.0
        elif value > 1.0:
            value = 1.0
        if value == self._brightness:
            return
        self._brightness = value
        self._brightness_dirty = True
        self._cached_r = -1

    def _store_rgb(self, index: int, red: int, green: int, blue: int) -> None:
        offset = index * 3
        self._colors[offset] = red
        self._colors[offset + 1] = green
        self._colors[offset + 2] = blue

    def _scale_rgb(self, red: int, green: int, blue: int) -> tuple:
        if red == 0 and green == 0 and blue == 0:
            return (0, 0, 0)
        if red == self._cached_r and green == self._cached_g and blue == self._cached_b:
            return self._cached_scaled
        brightness = self._brightness
        self._cached_r = red
        self._cached_g = green
        self._cached_b = blue
        self._cached_scaled = (
            int(red * brightness),
            int(green * brightness),
            int(blue * brightness),
        )
        return self._cached_scaled

    def fill(self, color: tuple) -> None:
        """Set every pixel to the same unscaled color."""
        red = int(color[0])
        green = int(color[1])
        blue = int(color[2])
        for index in range(self._num_pixels):
            self._store_rgb(index, red, green, blue)
        self._pixels.fill(self._scale_rgb(red, green, blue))
        self._brightness_dirty = False

    def show(self) -> None:
        """Write the stored colors with brightness scaling applied."""
        if self._brightness_dirty:
            offset = 0
            for index in range(self._num_pixels):
                self._pixels[index] = self._scale_rgb(
                    self._colors[offset],
                    self._colors[offset + 1],
                    self._colors[offset + 2],
                )
                offset += 3
            self._brightness_dirty = False
        self._pixels.write()

    def __setitem__(self, index: int, color: tuple) -> None:
        red = int(color[0])
        green = int(color[1])
        blue = int(color[2])
        self._store_rgb(index, red, green, blue)
        self._pixels[index] = self._scale_rgb(red, green, blue)

    def __getitem__(self, index: int) -> tuple:
        offset = index * 3
        return (
            self._colors[offset],
            self._colors[offset + 1],
            self._colors[offset + 2],
        )

    def __len__(self) -> int:
        return self._num_pixels
