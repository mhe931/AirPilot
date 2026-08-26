from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

import cv2
from cv2.typing import MatLike


@dataclass(frozen=True, slots=True)
class CameraDevice:
    index: int
    name: str
    backend: str


@dataclass(frozen=True, slots=True)
class CameraFrame:
    image: MatLike
    timestamp_ms: int

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


class Camera(Protocol):
    def frames(self) -> Iterator[CameraFrame]: ...

    def close(self) -> None: ...


def list_cameras(max_index: int = 4) -> list[CameraDevice]:
    devices: list[CameraDevice] = []
    for index in range(max_index + 1):
        for backend, name in _WINDOWS_BACKENDS:
            capture = cv2.VideoCapture(index, backend)
            try:
                if capture.isOpened():
                    ok, _ = capture.read()
                    if ok:
                        devices.append(
                            CameraDevice(index=index, name=f"Camera {index}", backend=name)
                        )
                        break
            finally:
                capture.release()
    return devices


class OpenCVCamera:
    def __init__(self, index: int = 0, *, read_failures_before_error: int = 10) -> None:
        self.backend_name = "unknown"
        self._read_failures_before_error = read_failures_before_error
        self._capture = self._open(index)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open camera index {index}")
        self._warm_up()

    def frames(self) -> Iterator[CameraFrame]:
        failures = 0
        while True:
            ok, image = self._capture.read()
            if not ok:
                failures += 1
                if failures >= self._read_failures_before_error:
                    raise RuntimeError(f"Camera frame read failed {failures} consecutive times")
                continue
            failures = 0
            timestamp_ms = int(cv2.getTickCount() / cv2.getTickFrequency() * 1000)
            yield CameraFrame(image=image, timestamp_ms=timestamp_ms)

    def close(self) -> None:
        self._capture.release()

    def _open(self, index: int) -> cv2.VideoCapture:
        for backend, name in _WINDOWS_BACKENDS:
            capture = cv2.VideoCapture(index, backend)
            if capture.isOpened():
                self.backend_name = name
                return capture
            capture.release()
        self.backend_name = "default"
        return cv2.VideoCapture(index)

    def _warm_up(self) -> None:
        for _ in range(3):
            self._capture.read()


_WINDOWS_BACKENDS = (
    (cv2.CAP_DSHOW, "DirectShow"),
    (cv2.CAP_MSMF, "Media Foundation"),
)
