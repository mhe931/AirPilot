from __future__ import annotations

import numpy as np
import pytest

from airpilot import app, tracking
from airpilot.camera import CameraFrame
from airpilot.config import AppConfig
from airpilot.display import VirtualDesktop
from airpilot.domain.types import (
    CursorPosition,
    GestureEvents,
    Handedness,
    HandLandmarks,
    Landmark,
    TrackingFrame,
)


def test_draw_uses_installed_mediapipe_api() -> None:
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    hand = HandLandmarks(tuple(Landmark(0.5, 0.5) for _ in range(21)))
    tracker_instance = tracking.MediaPipeHandTracker()

    try:
        drawn = tracker_instance.draw(image, hand)
    finally:
        tracker_instance.close()

    assert drawn is image


def test_run_disables_preview_landmarks_after_draw_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)

    class FakeCamera:
        backend_name = "fake"
        reconnect_count = 0

        def frames(self) -> list[CameraFrame]:
            return [CameraFrame(image=image, timestamp_ms=1)]

        def close(self) -> None:
            return None

    class FakeTracker:
        def track(self, _image: object, timestamp_ms: int) -> TrackingFrame:
            hand = HandLandmarks(tuple(Landmark(0.5, 0.5) for _ in range(21)))
            return TrackingFrame(timestamp_ms=timestamp_ms, width=8, height=8, hand=hand)

        def draw(self, _image: object, _hand: HandLandmarks | None) -> object:
            raise tracking.HandDrawingError("MediaPipe hand landmark drawing failed")

        def close(self) -> None:
            return None

    class FakeMouse:
        def emergency_stop_requested(self) -> bool:
            return False

    monkeypatch.setattr(app, "OpenCVCamera", lambda *_args, **_kwargs: FakeCamera())
    monkeypatch.setattr(app, "MediaPipeHandTracker", lambda **_kwargs: FakeTracker())
    monkeypatch.setattr(app, "PyAutoGuiMouseController", lambda **_kwargs: FakeMouse())
    monkeypatch.setattr(app.pyautogui, "size", lambda: (100, 100))
    monkeypatch.setattr(app.cv2, "imshow", lambda *_args: None)
    monkeypatch.setattr(app.cv2, "waitKey", lambda _delay: -1)
    monkeypatch.setattr(app.cv2, "destroyAllWindows", lambda: None)

    config = AppConfig()
    assert app.run(config, diagnose_seconds=0.0, show_preview=True) == 0
    assert not config.runtime.draw_landmarks
    captured = capsys.readouterr()
    assert "Preview landmarks disabled" in captured.err


def test_prepare_camera_image_preserves_actual_orientation_by_default() -> None:
    image = np.array([[[1, 0, 0]], [[2, 0, 0]], [[3, 0, 0]]], dtype=np.uint8).transpose((1, 0, 2))
    config = AppConfig()

    prepared = app._prepare_camera_image(image, config)

    assert prepared[0, 0, 0] == 1
    assert prepared[0, 2, 0] == 3


def test_handle_keypress_accepts_uppercase_arm_toggle() -> None:
    class StubEngine:
        def toggle_pause(self) -> GestureEvents:
            raise AssertionError("pause should not be triggered")

    class StubMouse:
        def move_to(self, _position: CursorPosition) -> None:
            return None

        def left_click(self) -> None:
            return None

        def right_click(self) -> None:
            return None

        def drag_start(self) -> None:
            return None

        def drag_end(self) -> None:
            return None

        def scroll(self, _units: int) -> None:
            return None

        def emergency_stop_requested(self) -> bool:
            return False

    config = AppConfig()
    safety = app.MouseSafetyGate(armed=False)

    should_exit, notice = app._handle_keypress(
        ord("A"),
        config=config,
        engine=StubEngine(),
        safety=safety,
        mouse=StubMouse(),
    )

    assert not should_exit
    assert safety.armed is True
    assert notice == "Mouse control enabled"


def test_handle_keypress_reports_preview_only_arming_failure() -> None:
    class StubEngine:
        def toggle_pause(self) -> GestureEvents:
            raise AssertionError("pause should not be triggered")

    class StubMouse:
        def move_to(self, _position: CursorPosition) -> None:
            return None

        def left_click(self) -> None:
            return None

        def right_click(self) -> None:
            return None

        def drag_start(self) -> None:
            return None

        def drag_end(self) -> None:
            return None

        def scroll(self, _units: int) -> None:
            return None

        def emergency_stop_requested(self) -> bool:
            return False

    config = AppConfig()
    config.runtime.enable_real_mouse = False
    safety = app.MouseSafetyGate(armed=False)

    should_exit, notice = app._handle_keypress(
        ord("a"),
        config=config,
        engine=StubEngine(),
        safety=safety,
        mouse=StubMouse(),
        mouse_output_locked=True,
    )

    assert not should_exit
    assert safety.armed is False
    assert notice == "Mouse output disabled for diagnostics/--no-mouse"


def test_handle_keypress_enables_loaded_preview_only_config() -> None:
    class StubEngine:
        def toggle_pause(self) -> GestureEvents:
            raise AssertionError("pause should not be triggered")

    class StubMouse:
        def move_to(self, _position: CursorPosition) -> None:
            return None

        def left_click(self) -> None:
            return None

        def right_click(self) -> None:
            return None

        def drag_start(self) -> None:
            return None

        def drag_end(self) -> None:
            return None

        def scroll(self, _units: int) -> None:
            return None

        def emergency_stop_requested(self) -> bool:
            return False

    config = AppConfig()
    config.runtime.enable_real_mouse = False
    safety = app.MouseSafetyGate(armed=False)

    should_exit, notice = app._handle_keypress(
        ord("a"),
        config=config,
        engine=StubEngine(),
        safety=safety,
        mouse=StubMouse(),
    )

    assert not should_exit
    assert config.runtime.enable_real_mouse is True
    assert safety.armed is True
    assert notice == "Mouse control enabled"


def test_tracking_frame_exposes_secondary_hand() -> None:
    control = HandLandmarks((Landmark(0.2, 0.2),), handedness=Handedness.RIGHT)
    secondary = HandLandmarks((Landmark(0.8, 0.8),), handedness=Handedness.LEFT)

    frame = TrackingFrame(
        timestamp_ms=1,
        width=10,
        height=10,
        hand=control,
        hands=(control, secondary),
    )

    assert frame.control_hand is control
    assert frame.secondary_hand is secondary


def test_select_control_hand_prefers_right_hand_regardless_of_order() -> None:
    left = HandLandmarks((Landmark(0.2, 0.2),), handedness=Handedness.LEFT)
    right = HandLandmarks((Landmark(0.8, 0.8),), handedness=Handedness.RIGHT)

    assert tracking.select_control_hand((left, right)) is right
    assert tracking.select_control_hand((right, left)) is right


def test_mediapipe_handedness_matches_actual_orientation() -> None:
    assert tracking._mediapipe_handedness("left", input_is_mirrored=False) is Handedness.RIGHT
    assert tracking._mediapipe_handedness("right", input_is_mirrored=False) is Handedness.LEFT
    assert tracking._mediapipe_handedness("left", input_is_mirrored=True) is Handedness.LEFT
    assert tracking._mediapipe_handedness("right", input_is_mirrored=True) is Handedness.RIGHT
    assert tracking._mediapipe_handedness("unknown", input_is_mirrored=False) is Handedness.UNKNOWN


def test_run_blocks_pointer_until_armed_then_restores_cursor_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    points = [Landmark(0.5, 0.5) for _ in range(21)]
    points[4] = Landmark(0.8, 0.8)
    points[8] = Landmark(0.2, 0.2)
    points[12] = Landmark(0.2, 0.8)
    points[16] = Landmark(0.8, 0.2)
    points[20] = Landmark(0.2, 0.5)
    hand = HandLandmarks(tuple(points))

    class FakeCamera:
        backend_name = "fake"
        reconnect_count = 0

        def frames(self) -> list[CameraFrame]:
            return [
                CameraFrame(image=image.copy(), timestamp_ms=1),
                CameraFrame(image=image.copy(), timestamp_ms=2),
            ]

        def close(self) -> None:
            return None

    class FakeTracker:
        def track(self, _image: object, timestamp_ms: int) -> TrackingFrame:
            return TrackingFrame(timestamp_ms=timestamp_ms, width=8, height=8, hand=hand)

        def draw(self, image: object, _hand: HandLandmarks | None) -> object:
            return image

        def close(self) -> None:
            return None

    class FakeMouse:
        actions: list[str] = []

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

        def emergency_stop_requested(self) -> bool:
            return False

    class FakeDisplayProvider:
        def virtual_desktop(self) -> VirtualDesktop:
            return VirtualDesktop(left=0, top=0, width=100, height=100)

    class FakeCursorFeedback:
        states: list[bool] = []
        restored = False

        def set_control_active(self, active: bool) -> None:
            self.states.append(active)

        def restore(self) -> None:
            self.restored = True

    mouse = FakeMouse()
    feedback = FakeCursorFeedback()
    keys = iter([ord("a"), ord("q")])

    monkeypatch.setattr(app, "OpenCVCamera", lambda *_args, **_kwargs: FakeCamera())
    monkeypatch.setattr(app, "MediaPipeHandTracker", lambda **_kwargs: FakeTracker())
    monkeypatch.setattr(app, "PyAutoGuiMouseController", lambda **_kwargs: mouse)
    monkeypatch.setattr(app, "create_cursor_feedback", lambda: feedback)
    monkeypatch.setattr(app, "create_display_provider", lambda: FakeDisplayProvider())
    monkeypatch.setattr(app.pyautogui, "size", lambda: (100, 100))
    monkeypatch.setattr(app.cv2, "imshow", lambda *_args: None)
    monkeypatch.setattr(app.cv2, "waitKey", lambda _delay: next(keys))
    monkeypatch.setattr(app.cv2, "destroyAllWindows", lambda: None)

    config = AppConfig()
    config.cursor.smoothing_alpha = 1.0
    assert app.run(config, show_preview=True) == 0

    assert mouse.actions == ["move:93,11"]
    assert feedback.states == [False, True]
    assert feedback.restored is True


def test_run_releases_drag_on_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    points = [Landmark(0.5, 0.5) for _ in range(21)]
    points[4] = Landmark(0.50, 0.50)
    points[8] = Landmark(0.51, 0.50)
    points[12] = Landmark(0.50, 0.80)
    points[16] = Landmark(0.20, 0.80)
    points[20] = Landmark(0.80, 0.80)
    hand = HandLandmarks(tuple(points))
    moved_points = list(points)
    moved_points[4] = Landmark(0.79, 0.50)
    moved_points[8] = Landmark(0.80, 0.50)
    moved_hand = HandLandmarks(tuple(moved_points))

    class FakeCamera:
        backend_name = "fake"
        reconnect_count = 0

        def frames(self) -> list[CameraFrame]:
            return [
                CameraFrame(image=image.copy(), timestamp_ms=1),
                CameraFrame(image=image.copy(), timestamp_ms=600),
            ]

        def close(self) -> None:
            return None

    class FakeTracker:
        def track(self, _image: object, timestamp_ms: int) -> TrackingFrame:
            tracked_hand = hand if timestamp_ms < 600 else moved_hand
            return TrackingFrame(timestamp_ms=timestamp_ms, width=8, height=8, hand=tracked_hand)

        def draw(self, image: object, _hand: HandLandmarks | None) -> object:
            return image

        def close(self) -> None:
            return None

    mouse = __import__(
        "airpilot.input", fromlist=["RecordingMouseController"]
    ).RecordingMouseController()
    feedback = __import__(
        "airpilot.cursor_feedback", fromlist=["NoOpCursorFeedback"]
    ).NoOpCursorFeedback()
    keys = iter([-1, ord("q")])

    class FakeDisplayProvider:
        def virtual_desktop(self) -> VirtualDesktop:
            return VirtualDesktop(left=0, top=0, width=100, height=100)

    monkeypatch.setattr(app, "OpenCVCamera", lambda *_args, **_kwargs: FakeCamera())
    monkeypatch.setattr(app, "MediaPipeHandTracker", lambda **_kwargs: FakeTracker())
    monkeypatch.setattr(app, "PyAutoGuiMouseController", lambda **_kwargs: mouse)
    monkeypatch.setattr(app, "create_cursor_feedback", lambda: feedback)
    monkeypatch.setattr(app, "create_display_provider", lambda: FakeDisplayProvider())
    monkeypatch.setattr(app.cv2, "imshow", lambda *_args: None)
    monkeypatch.setattr(app.cv2, "waitKey", lambda _delay: next(keys))
    monkeypatch.setattr(app.cv2, "destroyAllWindows", lambda: None)

    config = AppConfig()
    config.runtime.start_armed = True

    assert app.run(config, show_preview=True) == 0
    assert "drag_start" in mouse.actions
    assert mouse.actions[-1] == "drag_end"
