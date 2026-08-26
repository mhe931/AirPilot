from collections.abc import Iterable

import numpy as np
import pytest

from airpilot import camera


class FakeCapture:
    def __init__(self, reads: Iterable[bool]) -> None:
        self.reads = list(reads)
        self.released = False

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, object]:
        if not self.reads:
            return False, None
        ok = self.reads.pop(0)
        image = np.zeros((2, 3, 3), dtype=np.uint8) if ok else None
        return ok, image

    def release(self) -> None:
        self.released = True


def test_camera_retries_transient_read_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = FakeCapture([True, True, True, False, False, True])
    monkeypatch.setattr(camera.cv2, "VideoCapture", lambda *_args: capture)
    monkeypatch.setattr(camera, "_WINDOWS_BACKENDS", ((1, "fake"),))

    sut = camera.OpenCVCamera(read_failures_before_error=3)
    frame = next(sut.frames())

    assert frame.width == 3
    assert frame.height == 2
    sut.close()
    assert capture.released


def test_camera_fails_after_consecutive_read_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = FakeCapture([True, True, True, False, False])
    monkeypatch.setattr(camera.cv2, "VideoCapture", lambda *_args: capture)
    monkeypatch.setattr(camera, "_WINDOWS_BACKENDS", ((1, "fake"),))

    sut = camera.OpenCVCamera(read_failures_before_error=2)

    with pytest.raises(RuntimeError, match="2 consecutive"):
        next(sut.frames())
