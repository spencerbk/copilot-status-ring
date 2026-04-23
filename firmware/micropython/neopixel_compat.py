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
        self._colors = [(0, 0, 0)] * num_pixels
        self._brightness = 0.0
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
        self._brightness = value

    def fill(self, color: tuple) -> None:
        """Set every pixel to the same unscaled color."""
        stored = (int(color[0]), int(color[1]), int(color[2]))
        self._colors[:] = [stored] * self._num_pixels
        self._pixels.fill(stored)

    def show(self) -> None:
        """Write the stored colors with brightness scaling applied."""
        brightness = self._brightness
        pixels = self._pixels
        colors = self._colors
        for index in range(self._num_pixels):
            color = colors[index]
            pixels[index] = (
                int(color[0] * brightness),
                int(color[1] * brightness),
                int(color[2] * brightness),
            )
        pixels.write()

    def __setitem__(self, index: int, color: tuple) -> None:
        stored = (int(color[0]), int(color[1]), int(color[2]))
        self._colors[index] = stored
        self._pixels[index] = stored

    def __getitem__(self, index: int) -> tuple:
        return self._colors[index]

    def __len__(self) -> int:
        return self._num_pixels
