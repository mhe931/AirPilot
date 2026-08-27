from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pyautogui


@dataclass(frozen=True, slots=True)
class VirtualDesktop:
    left: int
    top: int
    width: int
    height: int


class DisplayProvider(Protocol):
    def virtual_desktop(self) -> VirtualDesktop: ...


class WindowsDisplayProvider:
    def __init__(self) -> None:
        import ctypes

        self._user32 = ctypes.windll.user32

    def virtual_desktop(self) -> VirtualDesktop:
        left = int(self._user32.GetSystemMetrics(76))
        top = int(self._user32.GetSystemMetrics(77))
        width = int(self._user32.GetSystemMetrics(78))
        height = int(self._user32.GetSystemMetrics(79))
        if width <= 0 or height <= 0:
            raise OSError("Windows virtual desktop metrics are unavailable")
        return VirtualDesktop(left=left, top=top, width=width, height=height)


class PyAutoGuiDisplayProvider:
    def virtual_desktop(self) -> VirtualDesktop:
        width, height = pyautogui.size()
        return VirtualDesktop(left=0, top=0, width=int(width), height=int(height))


def create_display_provider() -> DisplayProvider:
    try:
        return WindowsDisplayProvider()
    except (AttributeError, OSError):
        return PyAutoGuiDisplayProvider()
