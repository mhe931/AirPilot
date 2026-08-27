from __future__ import annotations

from airpilot.config import CursorConfig, GestureConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureEngine
from airpilot.domain.pose import estimate_hand_pose
from airpilot.domain.types import HandLandmarks, Landmark, TrackingFrame


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


def test_thumb_clutch_freezes_and_releases_pointer_without_jump() -> None:
    sut = engine()

    moving = sut.process(frame(0, pose_hand(index_tip=(0.36, 0.22))))
    clutch = sut.process(frame(100, pose_hand(thumb_closed=True, index_tip=(0.36, 0.22))))
    moved_while_closed = sut.process(
        frame(200, pose_hand(thumb_closed=True, index_tip=(0.70, 0.22)))
    )
    resumed = sut.process(frame(300, pose_hand(index_tip=(0.70, 0.22))))

    assert moving.move is not None
    assert clutch.active_gesture == "clutch"
    assert clutch.move == moving.move
    assert moved_while_closed.move == moving.move
    assert resumed.move is not None
    assert resumed.move.x > moving.move.x


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
    for index, (x, y) in coords.items():
        points[index] = Landmark(
            center[0] + (x - center[0]) * scale + offset[0],
            center[1] + (y - center[1]) * scale + offset[1],
        )
    return HandLandmarks(tuple(points))
