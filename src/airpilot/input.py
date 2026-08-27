from __future__ import annotations

from contextlib import suppress
from ctypes import Structure, byref, c_long
from dataclasses import dataclass, field
from typing import Protocol

import pyautogui

from airpilot.domain.types import CursorPosition, GestureEvents


class _POINT(Structure):
    _fields_ = [
        ("x", c_long),
        ("y", c_long),
    ]


class MouseController(Protocol):
    def move_to(self, position: CursorPosition) -> None: ...

    def left_click(self) -> None: ...

    def right_click(self) -> None: ...

    def middle_click(self) -> None: ...

    def drag_start(self) -> None: ...

    def drag_end(self) -> None: ...

    def scroll(self, units: int) -> None: ...

    def hotkey(self, keys: tuple[str, ...]) -> None: ...

    def release_all_keys(self) -> None: ...

    def emergency_stop_requested(self) -> bool: ...


class PyAutoGuiMouseController:
    def __init__(self, *, emergency_corner_failsafe: bool = True) -> None:
        import ctypes

        pyautogui.FAILSAFE = emergency_corner_failsafe
        pyautogui.PAUSE = 0
        self._user32 = ctypes.windll.user32
        self._emergency_corner_failsafe = emergency_corner_failsafe

    def move_to(self, position: CursorPosition) -> None:
        if self._emergency_corner_failsafe and (
            self._is_failsafe_position(self._current_position())
            or self._is_failsafe_position(position)
        ):
            raise pyautogui.FailSafeException("AirPilot failsafe corner reached")
        if not self._user32.SetCursorPos(position.x, position.y):
            raise OSError("SetCursorPos failed")

    def left_click(self) -> None:
        pyautogui.click(button="left")

    def right_click(self) -> None:
        pyautogui.click(button="right")

    def middle_click(self) -> None:
        pyautogui.click(button="middle")

    def drag_start(self) -> None:
        pyautogui.mouseDown(button="left")

    def drag_end(self) -> None:
        pyautogui.mouseUp(button="left")

    def scroll(self, units: int) -> None:
        pyautogui.scroll(units)

    def hotkey(self, keys: tuple[str, ...]) -> None:
        """Press and release a hotkey combination.

        Uses explicit keyDown/keyUp with a try/finally so that all pressed keys
        are released even if an exception is raised mid-combination.
        """
        pressed: list[str] = []
        try:
            for key in keys:
                pyautogui.keyDown(key)
                pressed.append(key)
            for key in reversed(pressed):
                pyautogui.keyUp(key)
                pressed.pop()
        except Exception:
            for key in reversed(pressed):
                with suppress(Exception):
                    pyautogui.keyUp(key)
            raise

    def release_all_keys(self) -> None:
        """No-op: the hotkey() implementation ensures keys are released on completion.

        Provided for protocol compatibility with mock/fake controllers.
        """

    def emergency_stop_requested(self) -> bool:
        return self._emergency_corner_failsafe and self._is_failsafe_position(
            self._current_position()
        )

    def _current_position(self) -> CursorPosition:
        point = _POINT()
        if not self._user32.GetCursorPos(byref(point)):
            raise OSError("GetCursorPos failed")
        return CursorPosition(x=int(point.x), y=int(point.y))

    def _is_failsafe_position(self, position: CursorPosition) -> bool:
        left = int(self._user32.GetSystemMetrics(76))
        top = int(self._user32.GetSystemMetrics(77))
        width = int(self._user32.GetSystemMetrics(78))
        height = int(self._user32.GetSystemMetrics(79))
        if width <= 0 or height <= 0:
            return position.x == 0 and position.y == 0
        right = left + width - 1
        bottom = top + height - 1
        return (position.x, position.y) in {
            (left, top),
            (left, bottom),
            (right, top),
            (right, bottom),
        } or (position.x, position.y) in {
            (int(point[0]), int(point[1])) for point in pyautogui.FAILSAFE_POINTS
        }


@dataclass(slots=True)
class RecordingMouseController:
    actions: list[str] = field(default_factory=list)

    def move_to(self, position: CursorPosition) -> None:
        self.actions.append(f"move:{position.x},{position.y}")

    def left_click(self) -> None:
        self.actions.append("left_click")

    def right_click(self) -> None:
        self.actions.append("right_click")

    def middle_click(self) -> None:
        self.actions.append("middle_click")

    def drag_start(self) -> None:
        self.actions.append("drag_start")

    def drag_end(self) -> None:
        self.actions.append("drag_end")

    def scroll(self, units: int) -> None:
        self.actions.append(f"scroll:{units}")

    def hotkey(self, keys: tuple[str, ...]) -> None:
        self.actions.append(f"hotkey:{'+'.join(keys)}")

    def release_all_keys(self) -> None:
        self.actions.append("release_all_keys")

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
    if events.middle_click:
        mouse.middle_click()
    if events.scroll:
        mouse.scroll(events.scroll)
    if events.action_id is not None:
        # Keyboard shortcuts are dispatched by the action router, not raw mouse events.
        return
