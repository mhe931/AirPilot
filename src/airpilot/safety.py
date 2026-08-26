from __future__ import annotations

from dataclasses import dataclass

from airpilot.domain.types import GestureEvents
from airpilot.input import MouseController, apply_mouse_events


@dataclass(slots=True)
class MouseSafetyGate:
    armed: bool = False
    _drag_pressed: bool = False

    def toggle(self) -> bool:
        self.armed = not self.armed
        return self.armed

    def disarm(self, mouse: MouseController | None = None) -> bool:
        self.armed = False
        if self._drag_pressed and mouse is not None:
            mouse.drag_end()
            self._drag_pressed = False
            return True
        self._drag_pressed = False
        return False

    def apply(self, mouse: MouseController, events: GestureEvents) -> bool:
        if not self.armed:
            return False
        if events.drag_start:
            self._drag_pressed = True
        if events.drag_end:
            self._drag_pressed = False
        apply_mouse_events(mouse, events)
        return True
