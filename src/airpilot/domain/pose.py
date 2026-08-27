from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from airpilot.domain.types import HandLandmarks, Landmark

WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_TIP = 20


@dataclass(frozen=True, slots=True)
class FingerState:
    extended: bool
    bent: bool
    flexion: float


@dataclass(frozen=True, slots=True)
class HandPose:
    confident: bool
    scale: float
    thumb_closed_score: float
    thumb_open: bool
    thumb_closed: bool
    index: FingerState
    middle: FingerState
    ring: FingerState
    pinky: FingerState

    @property
    def index_bent(self) -> bool:
        return self.index.bent

    @property
    def middle_bent(self) -> bool:
        return self.middle.bent

    @property
    def ring_bent(self) -> bool:
        return self.ring.bent

    @property
    def pinky_bent(self) -> bool:
        return self.pinky.bent

    @property
    def fist(self) -> bool:
        return self.index.bent and self.middle.bent and self.ring.bent and self.pinky.bent

    @property
    def open_palm(self) -> bool:
        return (
            self.thumb_open
            and self.index.extended
            and self.middle.extended
            and self.ring.extended
            and self.pinky.extended
        )


def stable_pointer_anchor(hand: HandLandmarks) -> Landmark | None:
    """Return a palm/knuckle anchor that is stable while fingertips bend."""
    if len(hand.landmarks) < 21:
        return None
    landmarks = hand.landmarks
    if _distance(landmarks[INDEX_MCP], landmarks[PINKY_MCP]) <= 0.001:
        return None
    if _hand_scale(landmarks) <= 0.001:
        return None

    weighted_points = (
        (landmarks[WRIST], 1.0),
        (landmarks[INDEX_MCP], 2.0),
        (landmarks[MIDDLE_MCP], 2.0),
        (landmarks[RING_MCP], 1.5),
        (landmarks[PINKY_MCP], 1.0),
    )
    total_weight = sum(weight for _point, weight in weighted_points)
    return Landmark(
        x=sum(point.x * weight for point, weight in weighted_points) / total_weight,
        y=sum(point.y * weight for point, weight in weighted_points) / total_weight,
        z=sum(point.z * weight for point, weight in weighted_points) / total_weight,
        visibility=min(point.visibility for point, _weight in weighted_points),
    )


def estimate_hand_pose(
    hand: HandLandmarks,
    *,
    thumb_close_threshold: float,
    thumb_open_threshold: float,
    finger_bend_threshold: float,
    finger_extend_threshold: float,
) -> HandPose:
    neutral = FingerState(extended=False, bent=False, flexion=0.0)
    if len(hand.landmarks) < 21:
        return HandPose(False, 0.0, 0.0, False, False, neutral, neutral, neutral, neutral)

    scale = _hand_scale(hand.landmarks)
    if scale <= 0.001 or not _has_usable_finger_joints(hand.landmarks):
        return HandPose(False, scale, 0.0, False, False, neutral, neutral, neutral, neutral)

    palm = _palm_center(hand.landmarks)
    thumb_score = _distance(hand.landmarks[THUMB_TIP], palm) / scale
    thumb_closed = thumb_score <= thumb_close_threshold
    thumb_open = thumb_score >= thumb_open_threshold
    return HandPose(
        confident=True,
        scale=scale,
        thumb_closed_score=thumb_score,
        thumb_open=thumb_open,
        thumb_closed=thumb_closed,
        index=_finger_state(
            hand.landmarks,
            INDEX_MCP,
            INDEX_PIP,
            INDEX_TIP,
            finger_bend_threshold,
            finger_extend_threshold,
        ),
        middle=_finger_state(
            hand.landmarks,
            MIDDLE_MCP,
            MIDDLE_PIP,
            MIDDLE_TIP,
            finger_bend_threshold,
            finger_extend_threshold,
        ),
        ring=_finger_state(
            hand.landmarks,
            RING_MCP,
            RING_PIP,
            RING_TIP,
            finger_bend_threshold,
            finger_extend_threshold,
        ),
        pinky=_finger_state(
            hand.landmarks,
            PINKY_MCP,
            PINKY_PIP,
            PINKY_TIP,
            finger_bend_threshold,
            finger_extend_threshold,
        ),
    )


def _finger_state(
    landmarks: tuple[Landmark, ...],
    mcp: int,
    pip: int,
    tip: int,
    bend_threshold: float,
    extend_threshold: float,
) -> FingerState:
    base_to_pip = _distance(landmarks[mcp], landmarks[pip])
    base_to_tip = _distance(landmarks[mcp], landmarks[tip])
    if base_to_pip <= 0.001:
        return FingerState(extended=False, bent=False, flexion=0.0)
    flexion = base_to_tip / base_to_pip
    return FingerState(
        extended=flexion >= extend_threshold,
        bent=flexion <= bend_threshold,
        flexion=flexion,
    )


def _has_usable_finger_joints(landmarks: tuple[Landmark, ...]) -> bool:
    for mcp, pip in (
        (INDEX_MCP, INDEX_PIP),
        (MIDDLE_MCP, MIDDLE_PIP),
        (RING_MCP, RING_PIP),
        (PINKY_MCP, PINKY_PIP),
    ):
        if _distance(landmarks[mcp], landmarks[pip]) <= 0.001:
            return False
    return True


def _hand_scale(landmarks: tuple[Landmark, ...]) -> float:
    palm_width = _distance(landmarks[INDEX_MCP], landmarks[PINKY_MCP])
    palm_height = _distance(landmarks[WRIST], landmarks[MIDDLE_MCP])
    return max(palm_width, palm_height)


def _palm_center(landmarks: tuple[Landmark, ...]) -> Landmark:
    points = (
        landmarks[WRIST],
        landmarks[INDEX_MCP],
        landmarks[MIDDLE_MCP],
        landmarks[RING_MCP],
        landmarks[PINKY_MCP],
    )
    return Landmark(
        x=sum(point.x for point in points) / len(points),
        y=sum(point.y for point in points) / len(points),
        z=sum(point.z for point in points) / len(points),
        visibility=min(point.visibility for point in points),
    )


def _distance(first: Landmark, second: Landmark) -> float:
    return hypot(first.x - second.x, first.y - second.y)
