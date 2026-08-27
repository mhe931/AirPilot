from airpilot.domain.types import CursorPosition, GestureEvents
from airpilot.input import RecordingMouseController
from airpilot.safety import MouseSafetyGate


def test_mouse_safety_gate_blocks_actions_until_armed() -> None:
    mouse = RecordingMouseController()
    gate = MouseSafetyGate(armed=False)
    events = GestureEvents(move=CursorPosition(10, 10), left_click=True)

    assert not gate.apply(mouse, events)
    assert mouse.actions == []

    assert gate.toggle()
    assert gate.apply(mouse, events)
    assert mouse.actions == ["move:10,10", "left_click"]


def test_mouse_safety_gate_can_disarm() -> None:
    mouse = RecordingMouseController()
    gate = MouseSafetyGate(armed=True)

    gate.disarm()
    assert not gate.apply(mouse, GestureEvents(right_click=True))
    assert mouse.actions == []


def test_disarm_releases_active_drag() -> None:
    mouse = RecordingMouseController()
    gate = MouseSafetyGate(armed=True)

    gate.apply(mouse, GestureEvents(drag_start=True))
    assert gate.disarm(mouse)

    assert mouse.actions == ["drag_start", "drag_end", "release_all_keys"]


def test_disarm_calls_release_all_keys() -> None:
    mouse = RecordingMouseController()
    gate = MouseSafetyGate(armed=True)

    gate.disarm(mouse)

    assert "release_all_keys" in mouse.actions
