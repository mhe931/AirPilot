from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pyautogui

from airpilot.domain.types import CursorPosition, GestureEvents


class MouseController(Protocol):
    def move_to(self, position: CursorPosition) -> None: ...

    def left_click(self) -> None: ...

    def right_click(self) -> None: ...

    def drag_start(self) -> None: ...

    def drag_end(self) -> None: ...

    def scroll(self, units: int) -> None: ...

    def emergency_stop_requested(self) -> bool: ...


class PyAutoGuiMouseController:
    def __init__(self, *, emergency_corner_failsafe: bool = True) -> None:
        pyautogui.FAILSAFE = emergency_corner_failsafe
        pyautogui.PAUSE = 0

    def move_to(self, position: CursorPosition) -> None:
        pyautogui.moveTo(position.x, position.y, duration=0)

    def left_click(self) -> None:
        pyautogui.click(button="left")

    def right_click(self) -> None:
        pyautogui.click(button="right")

    def drag_start(self) -> None:
        pyautogui.mouseDown(button="left")

    def drag_end(self) -> None:
        pyautogui.mouseUp(button="left")

    def scroll(self, units: int) -> None:
        pyautogui.scroll(units)

    def emergency_stop_requested(self) -> bool:
        return False


@dataclass(slots=True)
class RecordingMouseController:
    actions: list[str] = field(default_factory=list)

    def move_to(self, position: CursorPosition) -> None:
        self.actions.append(f"move:{position.x},{position.y}")

    def left_click(self) -> None:
        self.actions.append("left_click")

    def right_click(self) -> None:
        self.actions.append("right_click")

    def drag_start(self) -> None:
        self.actions.append("drag_start")

    def drag_end(self) -> None:
        self.actions.append("drag_end")

    def scroll(self, units: int) -> None:
        self.actions.append(f"scroll:{units}")

    def emergency_stop_requested(self) -> bool:
        return False


def apply_mouse_events(mouse: MouseController, events: GestureEvents) -> None:
    if events.move is not None:
        mouse.move_to(events.move)
    if events.drag_start:
        mouse.drag_start()
    if events.drag_end:
        mouse.drag_end()
    if events.left_click:
        mouse.left_click()
    if events.right_click:
        mouse.right_click()
    if events.scroll:
        mouse.scroll(events.scroll)
