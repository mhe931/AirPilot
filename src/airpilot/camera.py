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
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        try:
            if capture.isOpened():
                ok, _ = capture.read()
                if ok:
                    devices.append(CameraDevice(index=index, name=f"Camera {index}"))
        finally:
            capture.release()
    return devices


class OpenCVCamera:
    def __init__(self, index: int = 0) -> None:
        self._capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open camera index {index}")

    def frames(self) -> Iterator[CameraFrame]:
        while True:
            ok, image = self._capture.read()
            if not ok:
                raise RuntimeError("Camera frame read failed")
            timestamp_ms = int(cv2.getTickCount() / cv2.getTickFrequency() * 1000)
            yield CameraFrame(image=image, timestamp_ms=timestamp_ms)

    def close(self) -> None:
        self._capture.release()
