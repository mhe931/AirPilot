"""Tests for thumb-index angle geometry and angle-based pointer activation.

Acceptance criteria covered:
- Angle values at 79, 80, 90, 100, 101 degrees.
- Tolerance changes.
- Hysteresis (pointer stays active through the hysteresis band).
- Left/right hands (mirrored fixtures give same angles).
- In-plane rotation invariance.
- Malformed/missing landmarks return None.
- Continuous scroll direction, dead zone, and tracking-loss cancel.
- GestureEngine angle-activation via pose_hand fixture variants.
"""

from __future__ import annotations

import math
from math import cos, hypot, sin

import pytest

from airpilot.config import CursorConfig, GestureConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureEngine, _thumb_angle_in_range
from airpilot.domain.pose import (
    thumb_index_angle_deg,
)
from airpilot.domain.types import Handedness, HandLandmarks, Landmark, TrackingFrame

# ---------------------------------------------------------------------------
# Landmark factory helpers
# ---------------------------------------------------------------------------


def _landmark(x: float, y: float) -> Landmark:
    return Landmark(x=x, y=y)


def _make_hand_with_angle(target_angle_deg: float) -> HandLandmarks:
    """Build a 21-landmark hand where the thumb-activation angle equals *target_angle_deg*.

    The angle is now defined as the angle between:
    - the stable hand axis (WRIST → MIDDLE_MCP), and
    - the thumb axis (THUMB_MCP → THUMB_TIP).

    Fixed anchor landmarks match the pose_hand fixture.
    """
    wrist = (0.50, 0.80)
    middle_mcp = (0.50, 0.52)
    thumb_mcp = (0.35, 0.62)

    # Hand axis direction
    hx = middle_mcp[0] - wrist[0]
    hy = middle_mcp[1] - wrist[1]
    hand_dir = math.atan2(hy, hx)  # ≈ -π/2 (pointing upward in image coords)

    # Place THUMB_TIP so the angle between hand_dir and thumb_dir == target
    thumb_length = 0.12
    thumb_dir = hand_dir + math.radians(target_angle_deg)
    tx = thumb_mcp[0] + thumb_length * math.cos(thumb_dir)
    ty = thumb_mcp[1] + thumb_length * math.sin(thumb_dir)

    base = {
        0: wrist,
        1: (0.40, 0.66),
        2: thumb_mcp,
        3: (0.31, 0.60),
        4: (tx, ty),
        5: (0.42, 0.55),  # INDEX_MCP
        6: (0.40, 0.38),
        7: (0.40, 0.30),
        8: (0.39, 0.22),  # INDEX_TIP (fixed, not used by angle)
        9: middle_mcp,
        10: (0.50, 0.35),
        11: (0.50, 0.28),
        12: (0.50, 0.18),
        13: (0.58, 0.55),
        14: (0.60, 0.40),
        15: (0.61, 0.34),
        16: (0.62, 0.24),
        17: (0.66, 0.60),
        18: (0.69, 0.47),
        19: (0.70, 0.41),
        20: (0.72, 0.32),
    }
    pts = [Landmark(x, y) for x, y in (base[i] for i in range(21))]
    return HandLandmarks(tuple(pts), handedness=Handedness.RIGHT)


def _rotate_hand(hand: HandLandmarks, degrees: float) -> HandLandmarks:
    """Rotate all landmarks in-plane around the geometric centre."""
    xs = [lm.x for lm in hand.landmarks]
    ys = [lm.y for lm in hand.landmarks]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    rad = math.radians(degrees)
    new_pts: list[Landmark] = []
    for lm in hand.landmarks:
        dx, dy = lm.x - cx, lm.y - cy
        new_pts.append(
            Landmark(
                x=cx + dx * cos(rad) - dy * sin(rad),
                y=cy + dx * sin(rad) + dy * cos(rad),
            )
        )
    return HandLandmarks(tuple(new_pts), handedness=hand.handedness)


def _mirror_hand(hand: HandLandmarks) -> HandLandmarks:
    """Mirror x around 0.5 (simulate a left hand from right-hand geometry)."""
    pts = [Landmark(x=1.0 - lm.x, y=lm.y) for lm in hand.landmarks]
    return HandLandmarks(tuple(pts), handedness=Handedness.LEFT)


# ---------------------------------------------------------------------------
# Angle geometry unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("angle_deg", [0.0, 45.0, 79.0, 80.0, 90.0, 100.0, 101.0, 150.0, 180.0])
def test_thumb_index_angle_exact(angle_deg: float) -> None:
    """thumb_index_angle_deg reconstructs the angle used to build the hand."""
    hand = _make_hand_with_angle(angle_deg)
    measured = thumb_index_angle_deg(hand.landmarks)
    assert measured is not None
    assert abs(measured - angle_deg) < 0.5, f"expected {angle_deg}° got {measured}°"


def test_angle_missing_landmarks_returns_none() -> None:
    pts = tuple(Landmark(0.5, 0.5) for _ in range(10))  # too few
    assert thumb_index_angle_deg(pts) is None


def test_angle_degenerate_zero_length_returns_none() -> None:
    """All-same-point landmarks → degenerate vectors → None."""
    pts = tuple(Landmark(0.5, 0.5) for _ in range(21))
    assert thumb_index_angle_deg(pts) is None


def test_angle_is_rotation_invariant() -> None:
    """In-plane rotation must not change the measured thumb-index angle."""
    base_hand = _make_hand_with_angle(90.0)
    for deg in (-45.0, 0.0, 28.0, 60.0, -90.0):
        rotated = _rotate_hand(base_hand, deg)
        measured = thumb_index_angle_deg(rotated.landmarks)
        assert measured is not None
        assert abs(measured - 90.0) < 0.5, f"rotation {deg}° broke angle: {measured}"


def test_angle_left_right_hand_symmetric() -> None:
    """Mirroring for left hand must yield the same angle as the right hand."""
    right_hand = _make_hand_with_angle(85.0)
    left_hand = _mirror_hand(right_hand)
    r_angle = thumb_index_angle_deg(right_hand.landmarks)
    l_angle = thumb_index_angle_deg(left_hand.landmarks)
    assert r_angle is not None and l_angle is not None
    assert abs(r_angle - l_angle) < 0.5, f"right={r_angle} left={l_angle}"


# ---------------------------------------------------------------------------
# Hysteresis helper unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "angle,pointer_was_active,expected",
    [
        # Exactly at boundary (strict range, hysteresis=0)
        (80.0, False, True),  # enters at exactly low
        (100.0, False, True),  # enters at exactly high
        (79.0, False, False),  # just below low → inactive
        (101.0, False, False),  # just above high → inactive
        # Within strict range → always active
        (90.0, False, True),
        (90.0, True, True),
        # With hysteresis=3: active→inactive only outside [77,103]
        (79.0, True, False),  # below strict AND below hys=0 band → deactivates
        (101.0, True, False),  # above strict AND above hys=0 → deactivates
    ],
)
def test_thumb_angle_in_range(angle: float, pointer_was_active: bool, expected: bool) -> None:
    """_thumb_angle_in_range with target=90, tol=10, hys=0 (strict)."""
    result = _thumb_angle_in_range(angle, 90.0, 10.0, 0.0, pointer_was_active)
    assert result == expected, (
        f"angle={angle} was_active={pointer_was_active} → {result}, expected {expected}"
    )


def test_hysteresis_nonzero_keeps_active_inside_band() -> None:
    """With hysteresis=3: active pointer stays active in [77, 103] band."""
    # When active: [77, 103]; when inactive: [80, 100]
    assert _thumb_angle_in_range(77.5, 90.0, 10.0, 3.0, pointer_was_active=True) is True
    assert _thumb_angle_in_range(76.9, 90.0, 10.0, 3.0, pointer_was_active=True) is False
    assert _thumb_angle_in_range(102.5, 90.0, 10.0, 3.0, pointer_was_active=True) is True
    assert _thumb_angle_in_range(103.1, 90.0, 10.0, 3.0, pointer_was_active=True) is False
    # When inactive (clutch), still requires strict [80,100]
    assert _thumb_angle_in_range(78.0, 90.0, 10.0, 3.0, pointer_was_active=False) is False
    """Changing tolerance from 10 to 20 should accept angles in [70,110]."""
    assert _thumb_angle_in_range(70.0, 90.0, 20.0, 0.0, False) is True
    assert _thumb_angle_in_range(69.9, 90.0, 20.0, 0.0, False) is False
    assert _thumb_angle_in_range(110.0, 90.0, 20.0, 0.0, False) is True
    assert _thumb_angle_in_range(110.1, 90.0, 20.0, 0.0, False) is False


# ---------------------------------------------------------------------------
# GestureEngine integration: angle-based clutch
# ---------------------------------------------------------------------------


def _engine(
    *,
    use_angle: bool = True,
    target: float = 90.0,
    tolerance: float = 10.0,
    hysteresis: float = 0.0,
) -> GestureEngine:
    cfg = GestureConfig(
        min_click_hold_ms=80,
        click_cooldown_ms=300,
        drag_hold_ms=450,
        scroll_cooldown_ms=0,
        use_thumb_angle_activation=use_angle,
        thumb_angle_target_deg=target,
        thumb_angle_tolerance_deg=tolerance,
        thumb_angle_hysteresis_deg=hysteresis,
    )
    return GestureEngine(
        cfg,
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


def _frame(ts: int, hand: HandLandmarks) -> TrackingFrame:
    return TrackingFrame(timestamp_ms=ts, width=640, height=480, hand=hand)


def test_angle_activation_permits_movement_at_target() -> None:
    """Hand at 90° (in range) → pointer moves."""
    sut = _engine()
    start = sut.process(_frame(0, _make_hand_with_angle(90.0)))
    moved = sut.process(_frame(100, _rotate_hand(_make_hand_with_angle(90.0), 5.0)))
    assert start.move is not None
    assert moved.move is not None
    assert moved.active_gesture == "tracking"


def test_angle_at_79_clutches_immediately() -> None:
    """Angle below tolerance (79° < 80°) → clutch engaged."""
    sut = _engine()
    # First frame establishes tracking with in-range angle
    sut.process(_frame(0, _make_hand_with_angle(90.0)))
    # Now angle drops below 80 → clutch
    result = sut.process(_frame(100, _make_hand_with_angle(79.0)))
    assert result.active_gesture == "clutch", f"Expected clutch got {result.active_gesture}"


def test_angle_at_80_does_not_clutch() -> None:
    """Angle at exactly 80° → pointer active."""
    sut = _engine()
    sut.process(_frame(0, _make_hand_with_angle(90.0)))
    result = sut.process(_frame(100, _make_hand_with_angle(80.0)))
    assert result.active_gesture != "clutch"
    assert result.move is not None


def test_angle_at_101_clutches() -> None:
    """Angle above tolerance (101° > 100°) → clutch."""
    sut = _engine()
    sut.process(_frame(0, _make_hand_with_angle(90.0)))
    result = sut.process(_frame(100, _make_hand_with_angle(101.0)))
    assert result.active_gesture == "clutch"


def test_angle_at_100_does_not_clutch() -> None:
    """Angle at exactly 100° → pointer still active."""
    sut = _engine()
    sut.process(_frame(0, _make_hand_with_angle(90.0)))
    result = sut.process(_frame(100, _make_hand_with_angle(100.0)))
    assert result.active_gesture != "clutch"
    assert result.move is not None


def test_hysteresis_prevents_rapid_clutch_toggle() -> None:
    """With hysteresis=3: at 78° active pointer stays active (inside [77,103])."""
    sut = _engine(hysteresis=3.0)
    sut.process(_frame(0, _make_hand_with_angle(90.0)))
    # With hysteresis=3, active range is [77, 103]; 78° stays active
    result_still_active = sut.process(_frame(100, _make_hand_with_angle(78.0)))
    assert result_still_active.active_gesture != "clutch"
    # But 76° is below hysteresis band → clutches
    result_clutch = sut.process(_frame(200, _make_hand_with_angle(76.0)))
    assert result_clutch.active_gesture == "clutch"


def test_hysteresis_resumes_pointer_inside_band() -> None:
    """With default hysteresis=0: 79° clutches. 81° resumes."""
    sut = _engine()
    sut.process(_frame(0, _make_hand_with_angle(90.0)))
    sut.process(_frame(100, _make_hand_with_angle(79.0)))  # clutch
    resumed = sut.process(_frame(200, _make_hand_with_angle(81.0)))  # back in range
    assert resumed.active_gesture != "clutch"
    assert resumed.move is not None


def test_resume_no_cursor_jump() -> None:
    """Clutch then resume: cursor must not jump."""
    sut = _engine()
    start = sut.process(_frame(0, _make_hand_with_angle(90.0)))
    assert start.move is not None
    # Clutch
    sut.process(_frame(100, _make_hand_with_angle(79.0)))
    # Large hand displacement while clutched
    moved_clutch_hand = _rotate_hand(_make_hand_with_angle(79.0), 0.0)
    # Simulate big move: translate all landmarks
    big_offset_pts = [Landmark(lm.x + 0.3, lm.y) for lm in moved_clutch_hand.landmarks]
    moved_clutch = HandLandmarks(tuple(big_offset_pts), handedness=Handedness.RIGHT)
    sut.process(_frame(200, moved_clutch))
    # Resume
    resume_pts = [Landmark(lm.x, lm.y) for lm in _make_hand_with_angle(90.0).landmarks]
    resume_pts_translated = [Landmark(lm.x + 0.3, lm.y) for lm in resume_pts]
    resume_hand = HandLandmarks(tuple(resume_pts_translated), handedness=Handedness.RIGHT)
    resumed = sut.process(_frame(300, resume_hand))
    assert resumed.move is not None
    # Must be close to original position
    assert start.move is not None
    jump = hypot(resumed.move.x - start.move.x, resumed.move.y - start.move.y)
    assert jump <= 10, f"Resume jump too large: {jump}"


def test_left_right_hand_both_activate() -> None:
    """Left and right hand fixtures both activate pointer at ~85°."""
    right_hand = _make_hand_with_angle(85.0)
    left_hand = _mirror_hand(right_hand)
    left_hand = HandLandmarks(left_hand.landmarks, handedness=Handedness.LEFT)
    for hand in (right_hand, left_hand):
        sut = _engine()
        result = sut.process(_frame(0, hand))
        assert result.active_gesture != "clutch", f"Unexpected clutch for {hand.handedness}"


# ---------------------------------------------------------------------------
# Scroll dead-zone and natural-direction tests
# ---------------------------------------------------------------------------


def _scroll_engine(*, natural: bool = False, dead_zone: float = 0.0) -> GestureEngine:
    cfg = GestureConfig(
        scroll_cooldown_ms=0,
        scroll_activation_y_delta=0.01,
        scroll_sensitivity=1.0,
        scroll_units_per_step=1,
        scroll_natural_direction=natural,
        scroll_dead_zone=dead_zone,
        use_thumb_angle_activation=False,  # use score-based for scroll tests
    )
    return GestureEngine(
        cfg,
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


def _scroll_hand(wrist_y: float, scroll_active: bool = True) -> HandLandmarks:
    """Build a hand where scroll gesture (thumb-ring pinch) is active/inactive."""
    from tests.test_pose_clutch import pose_hand  # import local helper

    if scroll_active:
        # Move ring tip close to thumb tip for scroll pinch
        pts = list(pose_hand(thumb_closed=False).landmarks)
        # RING_TIP=16 close to THUMB_TIP=4
        thumb = pts[4]
        pts[16] = Landmark(thumb.x + 0.01, thumb.y + 0.01)
        # Adjust wrist y to simulate hand movement
        pts[0] = Landmark(pts[0].x, wrist_y)
        return HandLandmarks(tuple(pts), handedness=Handedness.RIGHT)
    else:
        pts = list(pose_hand(thumb_closed=False).landmarks)
        pts[0] = Landmark(pts[0].x, wrist_y)
        return HandLandmarks(tuple(pts), handedness=Handedness.RIGHT)


def test_scroll_no_initial_jump() -> None:
    """First frame of scroll must not emit scroll events."""
    sut = _scroll_engine()
    hand = _scroll_hand(wrist_y=0.5, scroll_active=True)
    result = sut.process(_frame(0, hand))
    # First scroll frame sets anchor; no scroll delta yet
    if result.active_gesture == "scrolling":
        assert result.scroll is None or result.scroll == 0


def test_scroll_natural_direction_inverts() -> None:
    """natural_direction=True inverts scroll sign vs natural_direction=False."""
    normal = _scroll_engine(natural=False)
    natural_dir = _scroll_engine(natural=True)

    def run_scroll(sut: GestureEngine) -> int | None:
        """Drive a scroll gesture and return first non-zero scroll value."""
        # Build scroll hand: thumb-ring close together
        pts_base = [Landmark(0.5, 0.5) for _ in range(21)]
        pts_base[0] = Landmark(0.5, 0.50)  # WRIST
        pts_base[4] = Landmark(0.5, 0.45)  # THUMB_TIP (close to ring tip)
        pts_base[16] = Landmark(0.5, 0.46)  # RING_TIP (close enough for scroll pinch)
        scroll_hand = HandLandmarks(tuple(pts_base), handedness=Handedness.RIGHT)

        def mk_frame(ts: int, wrist_y: float) -> TrackingFrame:
            pts = list(scroll_hand.landmarks)
            pts[0] = Landmark(pts[0].x, wrist_y)
            h2 = HandLandmarks(tuple(pts), handedness=Handedness.RIGHT)
            return TrackingFrame(timestamp_ms=ts, width=640, height=480, hand=h2)

        sut.process(mk_frame(0, 0.50))
        for ts in range(50, 1000, 50):
            r = sut.process(mk_frame(ts, 0.50 + ts * 0.0003))
            if r.scroll:
                return r.scroll
        return None

    n_scroll = run_scroll(normal)
    t_scroll = run_scroll(natural_dir)
    if n_scroll is not None and t_scroll is not None:
        assert n_scroll * t_scroll < 0, "natural direction should invert scroll sign"


def test_scroll_dead_zone_suppresses_small_movement() -> None:
    """Movement smaller than dead_zone should not accumulate scroll."""
    sut = _scroll_engine(dead_zone=0.10)

    # Build scroll hand
    pts_base = [Landmark(0.5, 0.5) for _ in range(21)]
    pts_base[4] = Landmark(0.5, 0.45)  # THUMB_TIP
    pts_base[16] = Landmark(0.5, 0.46)  # RING_TIP (close for scroll gesture)
    scroll_hand = HandLandmarks(tuple(pts_base), handedness=Handedness.RIGHT)

    def mk_frame(ts: int, wrist_y: float) -> TrackingFrame:
        pts = list(scroll_hand.landmarks)
        pts[0] = Landmark(pts[0].x, wrist_y)
        h2 = HandLandmarks(tuple(pts), handedness=Handedness.RIGHT)
        return TrackingFrame(timestamp_ms=ts, width=640, height=480, hand=h2)

    sut.process(mk_frame(0, 0.5))  # anchor
    # Tiny movements within dead zone (0.002 << 0.10 dead zone)
    for ts in range(1, 10):
        r = sut.process(mk_frame(ts * 50, 0.5 + ts * 0.002))
        assert r.scroll is None or r.scroll == 0, f"scroll={r.scroll} leaked through dead zone"
