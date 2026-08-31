from airpilot.config import CursorConfig, GestureConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import (
    INDEX_TIP,
    MIDDLE_TIP,
    PINKY_TIP,
    RING_TIP,
    THUMB_TIP,
    WRIST,
    GestureEngine,
)
from airpilot.domain.types import HandLandmarks, Landmark, TrackingFrame

_DEFAULT_HAND = object()


def engine() -> GestureEngine:
    return GestureEngine(
        GestureConfig(
            min_click_hold_ms=80,
            click_cooldown_ms=300,
            drag_hold_ms=450,
            pause_hold_ms=800,
            tracking_loss_grace_ms=200,
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


def pause_engine() -> GestureEngine:
    sut = engine()
    sut.config.pause_gesture_enabled = True
    return sut


def test_left_click_requires_hold_release_and_cooldown() -> None:
    sut = engine()
    assert not sut.process(frame(0)).left_click
    active = sut.process(frame(100, index=(0.51, 0.50)))
    assert not active.left_click
    assert active.active_gesture == "click_candidate"
    clicked = sut.process(frame(220))
    assert clicked.left_click
    assert clicked.active_gesture == "left_click"

    assert not sut.process(frame(260, index=(0.51, 0.50))).left_click
    assert not sut.process(frame(310)).left_click

    assert not sut.process(frame(600, index=(0.51, 0.50))).left_click
    assert sut.process(frame(710)).left_click


def test_no_click_on_single_noisy_frame() -> None:
    sut = engine()

    assert not sut.process(frame(100, index=(0.51, 0.50))).left_click
    assert not sut.process(frame(120)).left_click


def test_drag_lifecycle_consumes_click() -> None:
    sut = engine()

    assert not sut.process(frame(0, index=(0.51, 0.50))).drag_start
    drag = sut.process(frame(500, thumb=(0.69, 0.50), index=(0.70, 0.50)))
    assert drag.drag_start
    assert drag.active_gesture == "dragging"

    release = sut.process(frame(560))
    assert release.drag_end
    assert release.active_gesture == "tracking"
    assert not release.left_click


def test_left_click_freezes_pointer_during_candidate_jitter() -> None:
    sut = engine()

    start = sut.process(frame(0, index=(0.40, 0.50)))
    candidate = sut.process(frame(100, index=(0.51, 0.50)))
    jitter = sut.process(frame(180, index=(0.53, 0.50)))
    clicked = sut.process(frame(240, index=(0.70, 0.50)))

    assert start.move is not None
    assert candidate.move == start.move
    assert jitter.move == start.move
    assert clicked.move == start.move
    assert clicked.left_click


def test_long_left_hold_without_movement_remains_click_candidate() -> None:
    sut = engine()

    sut.process(frame(0, index=(0.51, 0.50)))
    held = sut.process(frame(700, index=(0.51, 0.50)))
    released = sut.process(frame(760))

    assert held.active_gesture == "click_candidate"
    assert not held.drag_start
    assert released.left_click


def test_pause_during_drag_releases_drag() -> None:
    sut = pause_engine()

    sut.process(frame(0, index=(0.51, 0.50)))
    assert sut.process(frame(500, thumb=(0.69, 0.50), index=(0.70, 0.50))).drag_start
    sut.process(frame(600, pinky=(0.51, 0.50)))
    paused = sut.process(frame(1500, pinky=(0.51, 0.50)))

    assert paused.paused
    assert paused.drag_end
    assert paused.active_gesture == "paused"


def test_keyboard_pause_toggle_releases_drag() -> None:
    sut = engine()

    sut.process(frame(0, index=(0.51, 0.50)))
    assert sut.process(frame(500, thumb=(0.69, 0.50), index=(0.70, 0.50))).drag_start
    toggled = sut.toggle_pause()

    assert toggled.paused
    assert toggled.drag_end


def test_conflicting_new_pinches_cancel_without_clicks() -> None:
    sut = engine()

    conflict = sut.process(
        frame(
            0,
            index=(0.51, 0.50),
            middle=(0.51, 0.50),
        )
    )

    assert conflict.status == "gesture_conflict"
    assert conflict.active_gesture == "conflict"
    released = sut.process(frame(120))
    assert not released.left_click
    assert not released.right_click


def test_right_click_uses_middle_finger_pinch() -> None:
    sut = engine()

    assert not sut.process(frame(0, middle=(0.51, 0.50))).right_click
    assert sut.process(frame(120)).right_click


def test_middle_click_uses_held_middle_finger_pinch() -> None:
    sut = engine()

    assert not sut.process(frame(0, middle=(0.51, 0.50))).middle_click
    middle_click = sut.process(frame(750))

    assert middle_click.middle_click
    assert middle_click.active_gesture == "middle_click"


def test_scrolling_suppresses_pointer_move() -> None:
    sut = engine()

    start = sut.process(frame(0, ring=(0.51, 0.50)))
    assert start.move is None
    assert start.active_gesture == "scrolling"
    scroll = sut.process(frame(100, ring=(0.51, 0.50), wrist=(0.50, 0.56)))
    assert scroll.scroll < 0
    assert scroll.move is None
    assert scroll.active_gesture == "scrolling"


def test_scroll_up_and_down_direction() -> None:
    sut = engine()

    sut.process(frame(0, ring=(0.51, 0.50), wrist=(0.50, 0.50)))
    up = sut.process(frame(100, ring=(0.51, 0.50), wrist=(0.50, 0.44)))
    down = sut.process(frame(200, ring=(0.51, 0.50), wrist=(0.50, 0.56)))

    assert up.scroll > 0
    assert down.scroll < 0


def test_scroll_accumulates_small_deltas_and_ignores_under_threshold() -> None:
    sut = engine()

    sut.process(frame(0, ring=(0.51, 0.50), wrist=(0.50, 0.50)))
    small = sut.process(frame(100, ring=(0.51, 0.50), wrist=(0.50, 0.503)))
    accumulated = sut.process(frame(200, ring=(0.51, 0.50), wrist=(0.50, 0.509)))

    assert small.scroll == 0
    assert accumulated.scroll < 0


def test_scroll_cooldown_accumulates_for_repeated_output() -> None:
    sut = engine()
    sut.config.scroll_cooldown_ms = 100

    sut.process(frame(0, ring=(0.51, 0.50), wrist=(0.50, 0.50)))
    first = sut.process(frame(100, ring=(0.51, 0.50), wrist=(0.50, 0.53)))
    suppressed = sut.process(frame(120, ring=(0.51, 0.50), wrist=(0.50, 0.56)))
    repeated = sut.process(frame(220, ring=(0.51, 0.50), wrist=(0.50, 0.59)))

    assert first.scroll < 0
    assert suppressed.scroll == 0
    assert repeated.scroll < 0


def test_scroll_release_resets_anchor() -> None:
    sut = engine()

    sut.process(frame(0, ring=(0.51, 0.50), wrist=(0.50, 0.50)))
    assert sut.process(frame(100, ring=(0.51, 0.50), wrist=(0.50, 0.56))).scroll < 0
    released = sut.process(frame(200, wrist=(0.50, 0.56)))
    restarted = sut.process(frame(300, ring=(0.51, 0.50), wrist=(0.50, 0.56)))

    assert released.scroll == 0
    assert restarted.scroll == 0
    assert restarted.active_gesture == "scrolling"


def test_scroll_conflict_does_not_emit_clicks_or_middle_click() -> None:
    sut = engine()

    conflict = sut.process(frame(0, index=(0.51, 0.50), middle=(0.51, 0.50), ring=(0.51, 0.50)))

    assert conflict.status == "gesture_conflict"
    assert not conflict.left_click
    assert not conflict.right_click
    assert not conflict.middle_click
    assert conflict.scroll == 0


def test_scroll_sensitivity_is_configurable() -> None:
    slow = engine()
    fast = engine()
    slow.config.scroll_sensitivity = 0.5
    fast.config.scroll_sensitivity = 2.0

    slow.process(frame(0, ring=(0.51, 0.50), wrist=(0.50, 0.50)))
    fast.process(frame(0, ring=(0.51, 0.50), wrist=(0.50, 0.50)))
    slow_scroll = slow.process(frame(100, ring=(0.51, 0.50), wrist=(0.50, 0.53))).scroll
    fast_scroll = fast.process(frame(100, ring=(0.51, 0.50), wrist=(0.50, 0.53))).scroll

    assert abs(fast_scroll) > abs(slow_scroll)


def test_pause_resume_blocks_actions() -> None:
    sut = pause_engine()

    assert not sut.process(frame(0, pinky=(0.51, 0.50))).paused_changed
    assert sut.process(frame(100, pinky=(0.51, 0.50))).active_gesture == "pause_hold"
    paused = sut.process(frame(900, pinky=(0.51, 0.50)))
    assert paused.paused_changed
    assert paused.paused

    blocked = sut.process(frame(1100, index=(0.51, 0.50)))
    assert blocked.paused
    assert blocked.move is None
    assert not blocked.left_click

    sut.process(frame(1200, pinky=(0.70, 0.50)))
    sut.process(frame(1300, pinky=(0.51, 0.50)))
    resumed = sut.process(frame(2200, pinky=(0.51, 0.50)))
    assert resumed.paused_changed
    assert not resumed.paused


def test_default_single_hand_pinky_pinch_does_not_pause() -> None:
    sut = engine()

    assert not sut.process(frame(0, pinky=(0.51, 0.50))).paused_changed
    held = sut.process(frame(1200, pinky=(0.51, 0.50)))

    assert not held.paused
    assert held.active_gesture != "paused"


def test_click_and_scroll_gestures_do_not_pause_by_default() -> None:
    sut = engine()

    assert not sut.process(frame(0, index=(0.51, 0.50))).paused
    assert not sut.process(frame(120)).paused
    assert not sut.process(frame(200, ring=(0.51, 0.50))).paused
    assert not sut.process(frame(300, ring=(0.51, 0.56))).paused


def test_tracking_loss_and_recovery() -> None:
    sut = engine()

    assert sut.process(frame(0)).status == "tracking"
    assert sut.process(frame(100, hand=None)).status == "searching"
    lost = sut.process(frame(250, hand=None))
    assert lost.tracking_lost
    assert lost.status == "tracking_lost"

    recovered = sut.process(frame(300))
    assert recovered.status == "tracking"
    assert not recovered.tracking_lost
    assert recovered.move is None

    resumed = sut.process(frame(360, wrist=(0.55, 0.50)))
    assert resumed.move is not None


def test_tracking_loss_releases_drag() -> None:
    sut = engine()

    sut.process(frame(0, index=(0.51, 0.50)))
    assert sut.process(frame(500, thumb=(0.69, 0.50), index=(0.70, 0.50))).drag_start
    lost = sut.process(frame(510, hand=None))
    assert lost.drag_end
    assert lost.tracking_lost


def test_invalid_landmarks_do_not_emit_actions() -> None:
    sut = engine()

    events = sut.process(
        TrackingFrame(timestamp_ms=0, width=640, height=480, hand=HandLandmarks(()))
    )
    assert not events.left_click
    assert not events.right_click
    assert not events.drag_start
    assert events.status == "searching"


def frame(
    timestamp_ms: int,
    *,
    hand: HandLandmarks | None | object = _DEFAULT_HAND,
    thumb: tuple[float, float] = (0.50, 0.50),
    wrist: tuple[float, float] = (0.50, 0.50),
    index: tuple[float, float] = (0.70, 0.50),
    middle: tuple[float, float] = (0.50, 0.70),
    ring: tuple[float, float] = (0.40, 0.70),
    pinky: tuple[float, float] = (0.30, 0.70),
) -> TrackingFrame:
    if hand is None:
        parsed_hand = None
    elif isinstance(hand, HandLandmarks):
        parsed_hand = hand
    elif hand is _DEFAULT_HAND:
        points = [Landmark(x=0.5, y=0.5) for _ in range(21)]
        points[WRIST] = Landmark(*wrist)
        points[THUMB_TIP] = Landmark(*thumb)
        points[INDEX_TIP] = Landmark(*index)
        points[MIDDLE_TIP] = Landmark(*middle)
        points[RING_TIP] = Landmark(*ring)
        points[PINKY_TIP] = Landmark(*pinky)
        parsed_hand = HandLandmarks(tuple(points))
    else:
        raise TypeError(f"Unsupported hand value: {hand!r}")
    return TrackingFrame(timestamp_ms=timestamp_ms, width=640, height=480, hand=parsed_hand)
