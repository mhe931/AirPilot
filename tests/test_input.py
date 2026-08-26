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
            drag_start=True,
            drag_end=True,
            scroll=-3,
        ),
    )

    assert mouse.actions == [
        "move:10,20",
        "drag_start",
        "drag_end",
        "left_click",
        "right_click",
        "scroll:-3",
    ]
