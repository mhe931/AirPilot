from __future__ import annotations

from pathlib import Path
from typing import Protocol

import cv2
import mediapipe as mp
from cv2.typing import MatLike
from mediapipe.framework.formats import landmark_pb2

from airpilot.domain.types import Handedness, HandLandmarks, Landmark, TrackingFrame


class HandTracker(Protocol):
    def track(self, image: MatLike, timestamp_ms: int) -> TrackingFrame: ...

    def close(self) -> None: ...


class HandDrawingError(RuntimeError):
    """Raised when preview landmark rendering fails."""


class MediaPipeHandTracker:
    def __init__(
        self,
        *,
        max_num_hands: int = 2,
        min_detection_confidence: float = 0.55,
        min_tracking_confidence: float = 0.55,
        input_is_mirrored: bool = False,
    ) -> None:
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            model_complexity=1,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._input_is_mirrored = input_is_mirrored

    def track(self, image: MatLike, timestamp_ms: int) -> TrackingFrame:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self._hands.process(rgb)
        hands: list[HandLandmarks] = []
        if result.multi_hand_landmarks:
            for index, hand_landmarks in enumerate(result.multi_hand_landmarks):
                landmarks = tuple(
                    Landmark(x=point.x, y=point.y, z=point.z) for point in hand_landmarks.landmark
                )
                handedness = Handedness.UNKNOWN
                confidence = 1.0
                if result.multi_handedness and index < len(result.multi_handedness):
                    category = result.multi_handedness[index].classification[0]
                    confidence = float(category.score)
                    label = str(category.label).lower()
                    handedness = _mediapipe_handedness(label, self._input_is_mirrored)
                hands.append(
                    HandLandmarks(
                        landmarks=landmarks,
                        handedness=handedness,
                        confidence=confidence,
                    )
                )
        control_hand = select_control_hand(tuple(hands))
        return TrackingFrame(
            timestamp_ms=timestamp_ms,
            width=int(image.shape[1]),
            height=int(image.shape[0]),
            hand=control_hand,
            hands=tuple(hands),
        )

    def draw(self, image: MatLike, hand: HandLandmarks | None) -> MatLike:
        if hand is None:
            return image
        try:
            mp_landmarks = landmark_pb2.NormalizedLandmarkList(
                landmark=[
                    landmark_pb2.NormalizedLandmark(
                        x=point.x,
                        y=point.y,
                        z=point.z,
                        visibility=point.visibility,
                    )
                    for point in hand.landmarks
                ]
            )
            mp.solutions.drawing_utils.draw_landmarks(
                image,
                mp_landmarks,
                mp.solutions.hands.HAND_CONNECTIONS,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise HandDrawingError("MediaPipe hand landmark drawing failed") from exc
        return image

    def close(self) -> None:
        self._hands.close()


def resolve_model_path(filename: str) -> Path:
    return Path(__file__).resolve().parent / "models" / filename


def select_control_hand(hands: tuple[HandLandmarks, ...]) -> HandLandmarks | None:
    if not hands:
        return None
    for hand in hands:
        if hand.handedness is Handedness.RIGHT:
            return hand
    for hand in hands:
        if hand.handedness is Handedness.LEFT:
            return hand
    return hands[0]


def _mediapipe_handedness(label: str, input_is_mirrored: bool) -> Handedness:
    if label == "left":
        handedness = Handedness.LEFT
    elif label == "right":
        handedness = Handedness.RIGHT
    else:
        return Handedness.UNKNOWN
    if input_is_mirrored:
        return handedness
    return Handedness.RIGHT if handedness is Handedness.LEFT else Handedness.LEFT
