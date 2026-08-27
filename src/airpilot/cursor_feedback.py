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


def create_cursor_feedback() -> CursorFeedbackController:
    return NoOpCursorFeedback()
