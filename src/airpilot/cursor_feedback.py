from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CursorFeedbackController(Protocol):
    def set_control_active(self, active: bool) -> None: ...

    def restore(self) -> None: ...


@dataclass(slots=True)
class NoOpCursorFeedback:
    active: bool = False

    def set_control_active(self, active: bool) -> None:
        self.active = active

    def restore(self) -> None:
        self.active = False


class WindowsCursorFeedback:
    def __init__(self) -> None:
        import ctypes

        self._user32 = ctypes.windll.user32
        self._hand = self._user32.LoadCursorW(None, 32649)
        self._arrow = self._user32.LoadCursorW(None, 32512)
        self._active = False

    def set_control_active(self, active: bool) -> None:
        if active or active != self._active:
            self._user32.SetCursor(self._hand if active else self._arrow)
        self._active = active

    def restore(self) -> None:
        self._user32.SetCursor(self._arrow)
        self._active = False


def create_cursor_feedback() -> CursorFeedbackController:
    try:
        return WindowsCursorFeedback()
    except (AttributeError, OSError):
        return NoOpCursorFeedback()
