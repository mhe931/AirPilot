from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Handedness(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Landmark:
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0


@dataclass(frozen=True, slots=True)
class HandLandmarks:
    landmarks: tuple[Landmark, ...]
    handedness: Handedness = Handedness.UNKNOWN
    confidence: float = 1.0

    def point(self, index: int) -> Landmark | None:
        if index < 0 or index >= len(self.landmarks):
            return None
        return self.landmarks[index]


@dataclass(frozen=True, slots=True)
class TrackingFrame:
    timestamp_ms: int
    width: int
    height: int
    hand: HandLandmarks | None
    hands: tuple[HandLandmarks, ...] = ()

    def __post_init__(self) -> None:
        if not self.hands and self.hand is not None:
            object.__setattr__(self, "hands", (self.hand,))

    @property
    def control_hand(self) -> HandLandmarks | None:
        return self.hand

    @property
    def secondary_hand(self) -> HandLandmarks | None:
        for hand in self.hands:
            if hand is not self.hand:
                return hand
        return None


@dataclass(frozen=True, slots=True)
class CursorPosition:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class GestureEvents:
    move: CursorPosition | None = None
    left_click: bool = False
    right_click: bool = False
    drag_start: bool = False
    drag_end: bool = False
    scroll: int = 0
    paused_changed: bool = False
    paused: bool = False
    tracking_lost: bool = False
    active_gesture: str = "none"
    status: str = "idle"
