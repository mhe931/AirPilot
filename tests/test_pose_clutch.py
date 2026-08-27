from __future__ import annotations

from math import cos, hypot, sin

from airpilot.config import CursorConfig, GestureConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureEngine
from airpilot.domain.pose import estimate_hand_pose
from airpilot.domain.types import CursorPosition, Handedness, HandLandmarks, Landmark, TrackingFrame


def test_pose_detects_thumb_and_finger_states_without_touching() -> None:
    hand = pose_hand(thumb_closed=True, index_bent=True, middle_bent=False)

    pose = estimate_hand_pose(
        hand,
        thumb_close_threshold=0.72,
        thumb_open_threshold=0.95,
        finger_bend_threshold=1.35,
        finger_extend_threshold=1.70,
    )

    assert pose.confident
    assert pose.thumb_closed
    assert pose.index_bent
    assert pose.middle.extended


def test_pose_is_scale_invariant() -> None:
    small = pose_hand(thumb_closed=True, index_bent=True, scale=0.7)
    large = pose_hand(thumb_closed=True, index_bent=True, scale=1.4)

    small_pose = _estimate(small)
    large_pose = _estimate(large)

    assert small_pose.thumb_closed
    assert large_pose.thumb_closed
    assert small_pose.index_bent
    assert large_pose.index_bent


def test_pointer_reference_ignores_index_bending() -> None:
    sut = engine()

    neutral = sut.process(frame(0, pose_hand()))
    bent = sut.process(frame(100, pose_hand(index_bent=True, index_tip=(0.86, 0.86))))
    hand_moved = sut.process(
        frame(200, pose_hand(index_bent=True, index_tip=(0.86, 0.86), offset=(0.24, 0.0)))
    )

    assert neutral.move is not None
    assert bent.move is not None
    assert _cursor_distance(neutral.move, bent.move) <= 1.0
    assert hand_moved.move is not None
    assert hand_moved.move.x > neutral.move.x + 30


def test_pointer_reference_ignores_middle_bending() -> None:
    sut = engine()

    neutral = sut.process(frame(0, pose_hand()))
    bent = sut.process(frame(100, pose_hand(middle_bent=True)))
    hand_moved = sut.process(frame(200, pose_hand(middle_bent=True, offset=(0.0, 0.24))))

    assert neutral.move is not None
    assert bent.move is not None
    assert _cursor_distance(neutral.move, bent.move) <= 1.0
    assert hand_moved.move is not None
    assert hand_moved.move.y > neutral.move.y + 20


def test_thumb_open_permits_pointer_movement_with_index_and_middle_bent() -> None:
    sut = engine()

    start = sut.process(frame(0, pose_hand()))
    bent = sut.process(frame(100, pose_hand(index_bent=True, middle_bent=True, offset=(0.20, 0.0))))

    assert start.move is not None
    assert bent.move is not None
    assert bent.move.x > start.move.x + 30
    assert bent.active_gesture == "tracking"


def test_thumb_clutch_freezes_and_releases_pointer_without_jump() -> None:
    sut = engine()

    moving = sut.process(frame(0, pose_hand()))
    clutch = sut.process(frame(100, pose_hand(thumb_closed=True)))
    moved_while_closed = sut.process(frame(200, pose_hand(thumb_closed=True, offset=(0.30, 0.0))))
    released = sut.process(frame(300, pose_hand(offset=(0.30, 0.0))))
    resumed_stationary = sut.process(frame(400, pose_hand(offset=(0.30, 0.0))))
    resumed_nudged = sut.process(frame(500, pose_hand(offset=(0.33, 0.0))))

    assert moving.move is not None
    assert clutch.active_gesture == "clutch"
    assert clutch.move == moving.move
    assert moved_while_closed.move == moving.move
    assert released.move == moving.move
    assert resumed_stationary.move == moving.move
    assert resumed_nudged.move is not None
    assert 0 < resumed_nudged.move.x - moving.move.x <= 8


def test_thumb_folded_freezes_even_when_index_and_middle_are_straight() -> None:
    sut = engine()

    moving = sut.process(frame(0, pose_hand()))
    folded = sut.process(frame(100, pose_hand(thumb_closed=True)))
    moved = sut.process(frame(200, pose_hand(thumb_closed=True, offset=(0.25, 0.20))))

    assert moving.move is not None
    assert folded.move == moving.move
    assert moved.move == moving.move
    assert folded.active_gesture == "clutch"


def test_post_clutch_resume_jump_is_bounded_after_large_hand_translation() -> None:
    sut = GestureEngine(GestureConfig(), CursorMapper(CursorConfig()))

    moving = sut.process(frame(0, pose_hand()))
    sut.process(frame(100, pose_hand(thumb_closed=True)))
    moved_while_closed = sut.process(frame(200, pose_hand(thumb_closed=True, offset=(0.30, 0.0))))
    released = sut.process(frame(300, pose_hand(offset=(0.30, 0.0))))
    resumed_stationary = sut.process(frame(400, pose_hand(offset=(0.30, 0.0))))
    resumed_nudged = sut.process(frame(500, pose_hand(offset=(0.32, 0.0))))

    assert moving.move is not None
    assert moved_while_closed.move == moving.move
    assert released.move == moving.move
    assert resumed_stationary.move is not None
    assert (
        _cursor_distance(released.move, resumed_stationary.move)
        <= sut.config.click_freeze_radius_px
    )
    assert resumed_nudged.move is not None
    assert 0 < _cursor_distance(resumed_stationary.move, resumed_nudged.move) <= 80


def test_clutch_index_bend_clicks_once_at_frozen_location() -> None:
    sut = engine()

    start = sut.process(frame(0, pose_hand(index_tip=(0.36, 0.22))))
    assert start.move is not None
    held = sut.process(frame(100, pose_hand(thumb_closed=True, index_bent=True)))
    jitter = sut.process(
        frame(170, pose_hand(thumb_closed=True, index_bent=True, index_tip=(0.62, 0.44)))
    )
    clicked = sut.process(frame(230, pose_hand(thumb_closed=True)))
    duplicate = sut.process(frame(260, pose_hand(thumb_closed=True)))

    assert held.active_gesture == "click_candidate"
    assert held.move == start.move
    assert jitter.move == start.move
    assert clicked.left_click
    assert clicked.move == start.move
    assert not duplicate.left_click


def test_clutch_middle_bend_right_and_middle_click_are_distinct() -> None:
    right = engine()
    assert not right.process(frame(0, pose_hand(thumb_closed=True, middle_bent=True))).right_click
    assert right.process(frame(120, pose_hand(thumb_closed=True))).right_click

    middle = engine()
    assert not middle.process(frame(0, pose_hand(thumb_closed=True, middle_bent=True))).middle_click
    result = middle.process(frame(750, pose_hand(thumb_closed=True)))
    assert result.middle_click
    assert not result.right_click


def test_thumb_detection_supports_left_and_right_hands() -> None:
    right_open = _estimate(pose_hand(handedness=Handedness.RIGHT))
    right_closed = _estimate(pose_hand(thumb_closed=True, handedness=Handedness.RIGHT))
    left_open = _estimate(pose_hand(handedness=Handedness.LEFT, mirror=True))
    left_closed = _estimate(pose_hand(thumb_closed=True, handedness=Handedness.LEFT, mirror=True))

    assert right_open.thumb_open
    assert not right_open.thumb_closed
    assert right_closed.thumb_closed
    assert left_open.thumb_open
    assert not left_open.thumb_closed
    assert left_closed.thumb_closed


def test_thumb_detection_is_stable_under_in_plane_rotation() -> None:
    open_pose = _estimate(pose_hand(rotation_degrees=28))
    closed_pose = _estimate(pose_hand(thumb_closed=True, rotation_degrees=-31))

    assert open_pose.thumb_open
    assert closed_pose.thumb_closed


def test_clutch_drag_resumes_movement_after_deliberate_hold() -> None:
    sut = engine()

    start = sut.process(frame(0, pose_hand(index_tip=(0.36, 0.22))))
    assert start.move is not None
    sut.process(frame(100, pose_hand(thumb_closed=True, index_bent=True)))
    drag = sut.process(
        frame(650, pose_hand(thumb_closed=True, index_bent=True, offset=(0.30, 0.08)))
    )
    released = sut.process(frame(720, pose_hand(thumb_closed=True)))

    assert drag.drag_start
    assert drag.move is not None
    assert drag.move != start.move
    assert released.drag_end


def _estimate(hand: HandLandmarks):
    return estimate_hand_pose(
        hand,
        thumb_close_threshold=0.72,
        thumb_open_threshold=0.95,
        finger_bend_threshold=1.35,
        finger_extend_threshold=1.70,
    )


def engine() -> GestureEngine:
    return GestureEngine(
        GestureConfig(
            min_click_hold_ms=80,
            click_cooldown_ms=300,
            drag_hold_ms=450,
            scroll_cooldown_ms=0,
        ),
        CursorMapper(
            CursorConfig(
                screen_width=200,
                screen_height=100,
                camera_min_x=0.0,
                camera_max_x=1.0,
                camera_min_y=0.0,
                camera_max_y=1.0,
                smoothing_alpha=1.0,
                dead_zone_px=0,
                mirror_x=False,
            )
        ),
    )


def frame(timestamp_ms: int, hand: HandLandmarks) -> TrackingFrame:
    return TrackingFrame(timestamp_ms=timestamp_ms, width=640, height=480, hand=hand)


def pose_hand(
    *,
    thumb_closed: bool = False,
    index_bent: bool = False,
    middle_bent: bool = False,
    index_tip: tuple[float, float] | None = None,
    scale: float = 1.0,
    offset: tuple[float, float] = (0.0, 0.0),
    handedness: Handedness = Handedness.RIGHT,
    mirror: bool = False,
    rotation_degrees: float = 0.0,
) -> HandLandmarks:
    points = [Landmark(0.5, 0.5) for _ in range(21)]
    coords = {
        0: (0.50, 0.80),
        1: (0.40, 0.66),
        2: (0.35, 0.62),
        3: (0.31, 0.60),
        4: (0.44, 0.62) if thumb_closed else (0.26, 0.62),
        5: (0.42, 0.55),
        6: (0.40, 0.38),
        7: (0.40, 0.30),
        8: index_tip or ((0.41, 0.46) if index_bent else (0.39, 0.22)),
        9: (0.50, 0.52),
        10: (0.50, 0.35),
        11: (0.50, 0.28),
        12: (0.51, 0.43) if middle_bent else (0.50, 0.18),
        13: (0.58, 0.55),
        14: (0.60, 0.40),
        15: (0.61, 0.34),
        16: (0.62, 0.24),
        17: (0.66, 0.60),
        18: (0.69, 0.47),
        19: (0.70, 0.41),
        20: (0.72, 0.32),
    }
    center = (0.50, 0.55)
    rotation = rotation_degrees * 3.141592653589793 / 180.0
    for index, (x, y) in coords.items():
        if mirror:
            x = center[0] - (x - center[0])
        dx = (x - center[0]) * scale
        dy = (y - center[1]) * scale
        rotated_x = dx * cos(rotation) - dy * sin(rotation)
        rotated_y = dx * sin(rotation) + dy * cos(rotation)
        points[index] = Landmark(
            center[0] + rotated_x + offset[0],
            center[1] + rotated_y + offset[1],
        )
    return HandLandmarks(tuple(points), handedness=handedness)


def _cursor_distance(first: CursorPosition, second: CursorPosition) -> float:
    return hypot(first.x - second.x, first.y - second.y)
