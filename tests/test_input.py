from airpilot.domain.types import CursorPosition, GestureEvents
from airpilot.input import RecordingMouseController, apply_mouse_events


def test_apply_mouse_events_uses_injected_controller() -> None:
    mouse = RecordingMouseController()

    apply_mouse_events(
        mouse,
        GestureEvents(
            move=CursorPosition(10, 20),
            left_click=True,
            right_click=True,
            middle_click=True,
            drag_start=True,
            drag_end=True,
            scroll=-3,
            action_id="clipboard.copy",
        ),
    )

    assert mouse.actions == [
        "move:10,20",
        "drag_start",
        "drag_end",
        "left_click",
        "right_click",
        "middle_click",
        "scroll:-3",
    ]


def test_recording_mouse_records_hotkeys_without_side_effects() -> None:
    mouse = RecordingMouseController()

    mouse.hotkey(("ctrl", "c"))

    assert mouse.actions == ["hotkey:ctrl+c"]


def test_win32_move_allows_airpilot_to_reach_a_virtual_desktop_corner() -> None:
    class FakeUser32:
        called = False

        def GetSystemMetrics(self, metric: int) -> int:
            return {76: -10, 77: -20, 78: 20, 79: 40}[metric]

        def GetCursorPos(self, _point: object) -> bool:
            _point._obj.x = 1
            _point._obj.y = 1
            return True

        def SetCursorPos(self, _x: int, _y: int) -> bool:
            self.called = True
            return True

    controller = object.__new__(
        __import__("airpilot.input", fromlist=["PyAutoGuiMouseController"]).PyAutoGuiMouseController
    )
    controller._user32 = FakeUser32()
    controller._emergency_corner_failsafe = True
    controller._last_airpilot_position = None

    controller.move_to(CursorPosition(-10, -20))

    assert controller._user32.called
    assert controller._last_airpilot_position == CursorPosition(-10, -20)


def test_win32_move_can_recover_from_an_airpilot_generated_corner() -> None:
    class FakeUser32:
        called = False

        def GetSystemMetrics(self, metric: int) -> int:
            return {76: -10, 77: -20, 78: 20, 79: 40}[metric]

        def GetCursorPos(self, point: object) -> bool:
            point._obj.x = -10
            point._obj.y = -20
            return True

        def SetCursorPos(self, _x: int, _y: int) -> bool:
            self.called = True
            return True

    controller = object.__new__(
        __import__("airpilot.input", fromlist=["PyAutoGuiMouseController"]).PyAutoGuiMouseController
    )
    controller._user32 = FakeUser32()
    controller._emergency_corner_failsafe = True
    controller._last_airpilot_position = CursorPosition(-10, -20)

    controller.move_to(CursorPosition(1, 1))

    assert controller._user32.called


def test_win32_move_disarms_when_user_moves_to_a_corner() -> None:
    class FakeUser32:
        called = False

        def GetSystemMetrics(self, metric: int) -> int:
            return {76: -10, 77: -20, 78: 20, 79: 40}[metric]

        def GetCursorPos(self, point: object) -> bool:
            point._obj.x = -10
            point._obj.y = -20
            return True

        def SetCursorPos(self, _x: int, _y: int) -> bool:
            self.called = True
            return True

    controller = object.__new__(
        __import__("airpilot.input", fromlist=["PyAutoGuiMouseController"]).PyAutoGuiMouseController
    )
    controller._user32 = FakeUser32()
    controller._emergency_corner_failsafe = True
    controller._last_airpilot_position = CursorPosition(1, 1)

    try:
        controller.move_to(CursorPosition(2, 2))
    except __import__("pyautogui").FailSafeException:
        pass
    else:
        raise AssertionError("manual failsafe corner did not raise")

    assert not controller._user32.called


def test_failsafe_includes_primary_corner_on_negative_virtual_desktop() -> None:
    class FakeUser32:
        def GetSystemMetrics(self, metric: int) -> int:
            return {76: -1280, 77: 0, 78: 3200, 79: 1080}[metric]

    controller = object.__new__(
        __import__("airpilot.input", fromlist=["PyAutoGuiMouseController"]).PyAutoGuiMouseController
    )
    controller._user32 = FakeUser32()

    assert controller._is_failsafe_position(CursorPosition(0, 0))
