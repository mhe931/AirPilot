from __future__ import annotations

import numpy as np
import pytest

from airpilot import app, tracking
from airpilot.camera import CameraFrame
from airpilot.config import AppConfig
from airpilot.domain.types import HandLandmarks, Landmark, TrackingFrame


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
