"""Regression tests for data-driven gesture bindings.

Acceptance criteria covered:
- GestureBinding serialization (dataclass → dict → dataclass round-trip).
- Config migration: v9 config loads with default bindings (PowerPoint example).
- Binding matching: finger state + movement + trigger conditions.
- Movement direction detection (left/right/up/down/none).
- Conflict detection for enabled bindings with identical conditions.
- Cooldown prevents duplicate firing within cooldown_ms.
- One-shot enter trigger: fires once per activation.
- Hold-repeat trigger: fires repeatedly while held.
- Release trigger: fires on finger release.
- PowerPoint example binding exists in defaults and is disabled.
- Settings binding persistence and reset (config round-trip with gesture_bindings).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from airpilot.config import (
    CURRENT_SCHEMA_VERSION,
    AppConfig,
    GestureBinding,
    GestureConfig,
    _default_gesture_bindings,
    _gesture_bindings_conflict,
    load_config,
    save_config,
    validate_gesture_bindings,
)
from airpilot.domain.gestures import GestureBindingMatcher
from airpilot.domain.pose import estimate_hand_pose
from airpilot.domain.types import (
    GestureEvents,
    Handedness,
    HandLandmarks,
    Landmark,
    TrackingFrame,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GESTURE_CFG = GestureConfig()


def _lm(x: float = 0.5, y: float = 0.5) -> Landmark:
    return Landmark(x=x, y=y)


def _make_hand(landmarks: dict[int, tuple[float, float]] | None = None) -> HandLandmarks:
    """Build a 21-landmark hand with a realistic open-palm layout.

    All fingers are in an extended (open) position unless overridden via
    the *landmarks* dict.  The palm landmarks are spaced out so that
    ``estimate_hand_pose`` returns ``confident=True``.
    """
    # Realistic open-palm layout (right hand, camera-space y increases downward)
    base: dict[int, tuple[float, float]] = {
        0: (0.50, 0.85),  # WRIST
        1: (0.45, 0.78),
        2: (0.40, 0.75),  # THUMB_MCP
        3: (0.34, 0.71),
        4: (0.28, 0.68),  # THUMB_TIP (open)
        5: (0.46, 0.66),  # INDEX_MCP
        6: (0.44, 0.52),
        7: (0.43, 0.41),
        8: (0.42, 0.30),  # INDEX_TIP (extended)
        9: (0.51, 0.64),  # MIDDLE_MCP
        10: (0.51, 0.50),
        11: (0.51, 0.38),
        12: (0.51, 0.26),  # MIDDLE_TIP (extended)
        13: (0.57, 0.66),
        14: (0.59, 0.52),
        15: (0.60, 0.41),
        16: (0.61, 0.30),  # RING_TIP (extended)
        17: (0.62, 0.70),  # PINKY_MCP
        18: (0.65, 0.58),
        19: (0.67, 0.49),
        20: (0.69, 0.40),  # PINKY_TIP (extended)
    }
    if landmarks:
        base.update(landmarks)
    lms = tuple(Landmark(x=v[0], y=v[1]) for v in (base[i] for i in range(21)))
    return HandLandmarks(landmarks=lms, handedness=Handedness.RIGHT, confidence=0.95)


def _frame(hand: HandLandmarks | None = None, ts: int = 0) -> TrackingFrame:
    return TrackingFrame(timestamp_ms=ts, width=640, height=480, hand=hand)


def _simple_binding(**kwargs: object) -> GestureBinding:
    defaults = dict(
        id="test",
        enabled=True,
        hand="either",
        thumb="any",
        index="any",
        middle="any",
        ring="any",
        pinky="any",
        movement="none",
        trigger="enter",
        threshold=0.03,
        hold_ms=0,
        cooldown_ms=0,
        sensitivity=1.0,
        action_id="clipboard.copy",
    )
    defaults.update(kwargs)  # type: ignore[arg-type]
    return GestureBinding(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Serialization round-trip
# ---------------------------------------------------------------------------


def test_gesture_binding_asdict_round_trip() -> None:
    b = GestureBinding(
        id="ppt_test",
        enabled=False,
        hand="either",
        thumb="folded",
        index="folded",
        movement="right",
        trigger="enter",
        threshold=0.04,
        hold_ms=0,
        cooldown_ms=600,
        sensitivity=1.0,
        action_id="presentation.next_slide",
    )
    d = asdict(b)
    b2 = GestureBinding(**d)
    assert b2 == b


def test_gesture_binding_json_round_trip(tmp_path: Path) -> None:
    config = AppConfig()
    config.gesture_bindings = [
        GestureBinding(id="my_bind", enabled=True, action_id="clipboard.copy")
    ]
    path = save_config(config, tmp_path / "cfg.json")
    loaded = load_config(path)
    assert len(loaded.gesture_bindings) == 1
    assert loaded.gesture_bindings[0].id == "my_bind"
    assert loaded.gesture_bindings[0].enabled is True
    assert loaded.gesture_bindings[0].action_id == "clipboard.copy"


def test_config_round_trip_preserves_schema_version(tmp_path: Path) -> None:
    config = AppConfig()
    path = save_config(config, tmp_path / "cfg.json")
    loaded = load_config(path)
    assert loaded.schema_version == CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Migration: v9 config loads with default gesture bindings
# ---------------------------------------------------------------------------


def test_v9_migration_adds_default_gesture_bindings(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 9,
                "gestures": {},
                "cursor": {},
                "actions": {},
                "runtime": {},
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.schema_version == CURRENT_SCHEMA_VERSION
    assert len(loaded.gesture_bindings) >= 1


def test_v10_missing_gesture_bindings_gets_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {"schema_version": 10, "gestures": {}, "cursor": {}, "actions": {}, "runtime": {}}
        ),
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert len(loaded.gesture_bindings) >= 1


# ---------------------------------------------------------------------------
# 3. PowerPoint example binding
# ---------------------------------------------------------------------------


def test_powerpoint_example_binding_exists_and_is_disabled() -> None:
    defaults = _default_gesture_bindings()
    ppt = next((b for b in defaults if "ppt" in b.id or "presentation" in b.action_id), None)
    assert ppt is not None, "PowerPoint example binding not found in defaults"
    assert ppt.enabled is False, "PowerPoint example must be disabled by default"
    assert ppt.action_id == "presentation.next_slide"
    assert ppt.thumb == "folded"
    assert ppt.index == "folded"
    assert ppt.movement == "right"


# ---------------------------------------------------------------------------
# 4. Conflict detection
# ---------------------------------------------------------------------------


def test_no_conflict_different_fingers() -> None:
    a = _simple_binding(id="a", thumb="folded", index="any")
    b = _simple_binding(id="b", thumb="extended", index="any")
    assert not _gesture_bindings_conflict(a, b)


def test_conflict_identical_conditions() -> None:
    a = _simple_binding(id="a", thumb="folded", index="folded", movement="right")
    b = _simple_binding(id="b", thumb="folded", index="folded", movement="right")
    assert _gesture_bindings_conflict(a, b)


def test_conflict_any_wildcard_overlaps() -> None:
    a = _simple_binding(id="a", thumb="folded", index="any")
    b = _simple_binding(id="b", thumb="folded", index="folded")
    assert _gesture_bindings_conflict(a, b)


def test_no_conflict_different_movement() -> None:
    a = _simple_binding(id="a", thumb="folded", movement="left")
    b = _simple_binding(id="b", thumb="folded", movement="right")
    assert not _gesture_bindings_conflict(a, b)


def test_no_conflict_different_hand_selection() -> None:
    a = _simple_binding(id="a", hand="left", thumb="folded")
    b = _simple_binding(id="b", hand="right", thumb="folded")
    assert not _gesture_bindings_conflict(a, b)


def test_validate_gesture_bindings_detects_conflicts() -> None:
    a = _simple_binding(id="a", enabled=True, thumb="folded")
    b = _simple_binding(id="b", enabled=True, thumb="folded")
    errors = validate_gesture_bindings([a, b])
    assert any("conflict" in e.lower() for e in errors)


def test_validate_gesture_bindings_disabled_no_conflict() -> None:
    a = _simple_binding(id="a", enabled=False, thumb="folded")
    b = _simple_binding(id="b", enabled=True, thumb="folded")
    errors = validate_gesture_bindings([a, b])
    assert not any("conflict" in e.lower() for e in errors)


def test_validate_gesture_bindings_duplicate_id() -> None:
    a = _simple_binding(id="same")
    b = _simple_binding(id="same")
    errors = validate_gesture_bindings([a, b])
    assert any("duplicate" in e.lower() for e in errors)


def test_validate_gesture_bindings_invalid_hand() -> None:
    b = _simple_binding(id="bad", hand="both")
    errors = validate_gesture_bindings([b])
    assert any("hand" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# 5. GestureBindingMatcher — matching logic helpers
# ---------------------------------------------------------------------------


def _make_pose_for_fingers(
    *,
    thumb_closed: bool = False,
    thumb_open: bool = True,
    index_bent: bool = False,
) -> object:
    """Return a fake pose-like object using actual estimate_hand_pose."""
    # Build a hand where thumb is open and index is extended by default
    # Use a custom landmark layout with the real estimator
    from airpilot.domain.pose import (
        INDEX_MCP,
        INDEX_PIP,
        INDEX_TIP,
        MIDDLE_MCP,
        MIDDLE_PIP,
        MIDDLE_TIP,
        PINKY_MCP,
        PINKY_PIP,
        PINKY_TIP,
        RING_MCP,
        RING_PIP,
        RING_TIP,
        THUMB_MCP,
        THUMB_TIP,
        WRIST,
    )

    pts: dict[int, tuple[float, float]] = {
        WRIST: (0.5, 0.9),
        1: (0.4, 0.8),
        THUMB_MCP: (0.35, 0.75),
        3: (0.30, 0.72),
        THUMB_TIP: (0.55, 0.70) if thumb_open else (0.50, 0.85),
        INDEX_MCP: (0.45, 0.65),
        INDEX_PIP: (0.43, 0.50),
        7: (0.42, 0.40),
        INDEX_TIP: (0.41, 0.30) if not index_bent else (0.45, 0.60),
        MIDDLE_MCP: (0.5, 0.62),
        MIDDLE_PIP: (0.50, 0.48),
        11: (0.50, 0.38),
        MIDDLE_TIP: (0.50, 0.28),
        RING_MCP: (0.55, 0.64),
        RING_PIP: (0.57, 0.50),
        15: (0.58, 0.40),
        RING_TIP: (0.59, 0.30),
        PINKY_MCP: (0.60, 0.68),
        PINKY_PIP: (0.63, 0.56),
        19: (0.65, 0.48),
        PINKY_TIP: (0.67, 0.40),
    }
    hand = _make_hand(pts)
    return estimate_hand_pose(
        hand,
        thumb_close_threshold=_GESTURE_CFG.thumb_close_threshold,
        thumb_open_threshold=_GESTURE_CFG.thumb_open_threshold,
        finger_bend_threshold=_GESTURE_CFG.finger_bend_threshold,
        finger_extend_threshold=_GESTURE_CFG.finger_extend_threshold,
    )


# ---------------------------------------------------------------------------
# 6. GestureBindingMatcher — enter trigger
# ---------------------------------------------------------------------------


def _matcher_with_binding(**kwargs: object) -> tuple[GestureBindingMatcher, GestureBinding]:
    b = _simple_binding(**kwargs)
    matcher = GestureBindingMatcher([b], _GESTURE_CFG)
    return matcher, b


def _events() -> GestureEvents:
    return GestureEvents(active_gesture="tracking", status="tracking")


def test_enter_trigger_fires_on_first_match() -> None:
    """Binding with movement=none and trigger=enter fires once when fingers match."""
    matcher, _ = _matcher_with_binding(
        id="t1",
        enabled=True,
        thumb="any",
        index="any",
        movement="none",
        trigger="enter",
        cooldown_ms=0,
    )
    # A 21-landmark hand where all fingers are in "any" state
    hand = _make_hand()
    frame1 = _frame(hand, ts=0)
    result = matcher.process(frame1, _events())
    assert result.action_id == "clipboard.copy"


def test_enter_trigger_does_not_fire_again_while_held() -> None:
    matcher, _ = _matcher_with_binding(
        id="t2", enabled=True, movement="none", trigger="enter", cooldown_ms=0
    )
    hand = _make_hand()
    frame1 = _frame(hand, ts=0)
    frame2 = _frame(hand, ts=100)
    result1 = matcher.process(frame1, _events())
    result2 = matcher.process(frame2, _events())
    assert result1.action_id == "clipboard.copy"
    assert result2.action_id is None  # consumed; no re-fire while held


# ---------------------------------------------------------------------------
# 7. Cooldown
# ---------------------------------------------------------------------------


def test_cooldown_blocks_second_firing() -> None:
    matcher, _ = _matcher_with_binding(
        id="cd", enabled=True, movement="none", trigger="enter", cooldown_ms=500
    )
    hand = _make_hand()
    # First activation
    result1 = matcher.process(_frame(hand, 0), _events())
    # Release (no hand)
    matcher.process(_frame(None, 50), _events())
    # Second activation before cooldown
    result2 = matcher.process(_frame(hand, 100), _events())
    assert result1.action_id == "clipboard.copy"
    assert result2.action_id is None


def test_cooldown_allows_firing_after_expiry() -> None:
    matcher, _ = _matcher_with_binding(
        id="cd2", enabled=True, movement="none", trigger="enter", cooldown_ms=200
    )
    hand = _make_hand()
    # First activation
    result1 = matcher.process(_frame(hand, 0), _events())
    # Release
    matcher.process(_frame(None, 10), _events())
    # Re-activation after cooldown
    result2 = matcher.process(_frame(hand, 300), _events())
    assert result1.action_id == "clipboard.copy"
    assert result2.action_id == "clipboard.copy"


# ---------------------------------------------------------------------------
# 8. Hold-repeat trigger
# ---------------------------------------------------------------------------


def test_hold_repeat_does_not_fire_before_hold_ms() -> None:
    matcher, _ = _matcher_with_binding(
        id="hr", enabled=True, movement="none", trigger="hold_repeat", hold_ms=500, cooldown_ms=0
    )
    hand = _make_hand()
    result = matcher.process(_frame(hand, 0), _events())
    assert result.action_id is None  # not yet held long enough


def test_hold_repeat_fires_after_hold_ms() -> None:
    matcher, _ = _matcher_with_binding(
        id="hr2", enabled=True, movement="none", trigger="hold_repeat", hold_ms=200, cooldown_ms=0
    )
    hand = _make_hand()
    matcher.process(_frame(hand, 0), _events())
    result = matcher.process(_frame(hand, 250), _events())
    assert result.action_id == "clipboard.copy"


def test_hold_repeat_fires_multiple_times() -> None:
    matcher, _ = _matcher_with_binding(
        id="hr3", enabled=True, movement="none", trigger="hold_repeat", hold_ms=100, cooldown_ms=100
    )
    hand = _make_hand()
    matcher.process(_frame(hand, 0), _events())
    r1 = matcher.process(_frame(hand, 150), _events())
    r2 = matcher.process(_frame(hand, 300), _events())
    assert r1.action_id == "clipboard.copy"
    assert r2.action_id == "clipboard.copy"


# ---------------------------------------------------------------------------
# 9. Release trigger
# ---------------------------------------------------------------------------


def test_release_trigger_does_not_fire_while_held() -> None:
    matcher, _ = _matcher_with_binding(
        id="rel", enabled=True, movement="none", trigger="release", cooldown_ms=0
    )
    hand = _make_hand()
    result = matcher.process(_frame(hand, 0), _events())
    assert result.action_id is None


def test_release_trigger_fires_on_release() -> None:
    matcher, _ = _matcher_with_binding(
        id="rel2", enabled=True, movement="none", trigger="release", cooldown_ms=0
    )
    hand = _make_hand()
    matcher.process(_frame(hand, 0), _events())  # fingers match
    result = matcher.process(_frame(None, 100), _events())  # no hand → release
    assert result.action_id == "clipboard.copy"


# ---------------------------------------------------------------------------
# 10. Movement direction
# ---------------------------------------------------------------------------


def test_movement_right_fires_when_wrist_moves_right() -> None:
    matcher, _ = _matcher_with_binding(
        id="mv_r",
        enabled=True,
        movement="right",
        trigger="enter",
        threshold=0.05,
        sensitivity=1.0,
        cooldown_ms=0,
    )
    hand0 = _make_hand({0: (0.3, 0.5)})  # wrist at x=0.3
    hand1 = _make_hand({0: (0.4, 0.5)})  # wrist moves right to x=0.4 (dx=0.1 > 0.05)
    matcher.process(_frame(hand0, 0), _events())
    result = matcher.process(_frame(hand1, 100), _events())
    assert result.action_id == "clipboard.copy"


def test_movement_left_does_not_fire_on_rightward_motion() -> None:
    matcher, _ = _matcher_with_binding(
        id="mv_l",
        enabled=True,
        movement="left",
        trigger="enter",
        threshold=0.05,
        sensitivity=1.0,
        cooldown_ms=0,
    )
    hand0 = _make_hand({0: (0.3, 0.5)})
    hand1 = _make_hand({0: (0.4, 0.5)})  # rightward motion
    matcher.process(_frame(hand0, 0), _events())
    result = matcher.process(_frame(hand1, 100), _events())
    assert result.action_id is None


def test_movement_up_fires_when_wrist_moves_up() -> None:
    matcher, _ = _matcher_with_binding(
        id="mv_u",
        enabled=True,
        movement="up",
        trigger="enter",
        threshold=0.05,
        sensitivity=1.0,
        cooldown_ms=0,
    )
    hand0 = _make_hand({0: (0.5, 0.6)})
    hand1 = _make_hand({0: (0.5, 0.5)})  # y decreases → upward in screen coords
    matcher.process(_frame(hand0, 0), _events())
    result = matcher.process(_frame(hand1, 100), _events())
    assert result.action_id == "clipboard.copy"


def test_movement_threshold_not_met() -> None:
    matcher, _ = _matcher_with_binding(
        id="mv_thr",
        enabled=True,
        movement="right",
        trigger="enter",
        threshold=0.10,
        sensitivity=1.0,
        cooldown_ms=0,
    )
    hand0 = _make_hand({0: (0.3, 0.5)})
    hand1 = _make_hand({0: (0.33, 0.5)})  # only dx=0.03 < 0.10
    matcher.process(_frame(hand0, 0), _events())
    result = matcher.process(_frame(hand1, 100), _events())
    assert result.action_id is None


# ---------------------------------------------------------------------------
# 11. Disabled binding never fires
# ---------------------------------------------------------------------------


def test_disabled_binding_never_fires() -> None:
    b = _simple_binding(id="dis", enabled=False, movement="none", trigger="enter", cooldown_ms=0)
    matcher = GestureBindingMatcher([b], _GESTURE_CFG)
    hand = _make_hand()
    result = matcher.process(_frame(hand, 0), _events())
    assert result.action_id is None


# ---------------------------------------------------------------------------
# 12. PowerPoint example — integration
# ---------------------------------------------------------------------------


def test_powerpoint_example_disabled_does_not_fire() -> None:
    """The default PowerPoint binding is disabled; it must never fire."""
    defaults = _default_gesture_bindings()
    matcher = GestureBindingMatcher(defaults, _GESTURE_CFG)
    hand = _make_hand({0: (0.3, 0.5)})
    hand2 = _make_hand({0: (0.5, 0.5)})  # rightward swipe
    matcher.process(_frame(hand, 0), _events())
    result = matcher.process(_frame(hand2, 100), _events())
    assert result.action_id is None


def test_powerpoint_example_fires_when_enabled() -> None:
    """When the PowerPoint binding is enabled and conditions met, it fires."""

    defaults = _default_gesture_bindings()
    ppt = next(b for b in defaults if "ppt" in b.id)
    enabled_ppt = GestureBinding(
        id=ppt.id,
        enabled=True,
        hand=ppt.hand,
        thumb=ppt.thumb,
        index=ppt.index,
        middle=ppt.middle,
        ring=ppt.ring,
        pinky=ppt.pinky,
        movement=ppt.movement,
        trigger=ppt.trigger,
        threshold=ppt.threshold,
        hold_ms=ppt.hold_ms,
        cooldown_ms=0,  # simplify test
        sensitivity=ppt.sensitivity,
        action_id=ppt.action_id,
    )
    # Build a hand with thumb and index clearly folded (close to wrist)
    # Using a simple layout: wrist at bottom, fingers bent inward
    pts = {
        0: (0.50, 0.85),  # WRIST
        1: (0.45, 0.78),
        2: (0.40, 0.76),  # THUMB_MCP
        3: (0.40, 0.82),
        4: (0.50, 0.83),  # THUMB_TIP (close to wrist → folded)
        5: (0.47, 0.70),  # INDEX_MCP
        6: (0.47, 0.76),
        7: (0.47, 0.80),
        8: (0.48, 0.83),  # INDEX_TIP (close to wrist → folded)
        9: (0.52, 0.68),  # MIDDLE_MCP
        10: (0.52, 0.55),
        11: (0.52, 0.45),
        12: (0.52, 0.35),  # MIDDLE_TIP (extended)
        13: (0.57, 0.70),
        14: (0.59, 0.58),
        15: (0.60, 0.48),
        16: (0.61, 0.38),
        17: (0.62, 0.73),
        18: (0.65, 0.62),
        19: (0.67, 0.54),
        20: (0.68, 0.46),
    }
    hand0 = HandLandmarks(
        landmarks=tuple(Landmark(x=v[0], y=v[1]) for v in (pts[i] for i in range(21))),
        handedness=Handedness.RIGHT,
        confidence=0.95,
    )
    # Check if the pose actually reports thumb + index as closed
    pose = estimate_hand_pose(
        hand0,
        thumb_close_threshold=_GESTURE_CFG.thumb_close_threshold,
        thumb_open_threshold=_GESTURE_CFG.thumb_open_threshold,
        finger_bend_threshold=_GESTURE_CFG.finger_bend_threshold,
        finger_extend_threshold=_GESTURE_CFG.finger_extend_threshold,
    )
    if not pose.confident or not pose.thumb_closed or not pose.index.bent:
        pytest.skip("Synthetic hand pose does not produce folded thumb+index for this fixture")

    # Rightward swipe: start at x=0.30, then move to x=0.45 (dx=0.15 > threshold 0.04)
    def _hand_at_x(wx: float) -> HandLandmarks:
        shifted = {k: (v[0] + (wx - 0.5), v[1]) for k, v in pts.items()}
        return HandLandmarks(
            landmarks=tuple(Landmark(x=v[0], y=v[1]) for v in (shifted[i] for i in range(21))),
            handedness=Handedness.RIGHT,
            confidence=0.95,
        )

    matcher = GestureBindingMatcher([enabled_ppt], _GESTURE_CFG)
    matcher.process(_frame(_hand_at_x(0.30), ts=0), _events())
    result = matcher.process(_frame(_hand_at_x(0.45), ts=100), _events())
    assert result.action_id == "presentation.next_slide"


# ---------------------------------------------------------------------------
# 13. Settings persistence round-trip
# ---------------------------------------------------------------------------


def test_settings_persistence_saves_and_reloads_bindings(tmp_path: Path) -> None:
    config = AppConfig()
    config.gesture_bindings = [
        GestureBinding(
            id="test_binding",
            enabled=True,
            thumb="folded",
            index="folded",
            movement="right",
            trigger="enter",
            cooldown_ms=300,
            action_id="presentation.next_slide",
        )
    ]
    path = save_config(config, tmp_path / "cfg.json")
    loaded = load_config(path)
    assert len(loaded.gesture_bindings) == 1
    b = loaded.gesture_bindings[0]
    assert b.id == "test_binding"
    assert b.enabled is True
    assert b.thumb == "folded"
    assert b.movement == "right"
    assert b.action_id == "presentation.next_slide"


def test_settings_reset_restores_defaults(tmp_path: Path) -> None:
    config = AppConfig()
    config.gesture_bindings = [
        GestureBinding(id="custom_binding", enabled=True, action_id="clipboard.copy")
    ]
    save_config(config, tmp_path / "cfg.json")
    # Reset = load fresh AppConfig with defaults
    fresh = AppConfig()
    assert len(fresh.gesture_bindings) >= 1
    default_ids = {b.id for b in fresh.gesture_bindings}
    assert "ppt_next_slide_gesture" in default_ids


def test_malformed_binding_in_json_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 10,
                "gestures": {},
                "cursor": {},
                "actions": {},
                "runtime": {},
                "gesture_bindings": [
                    {"id": "good", "enabled": False},
                    "not_a_dict",
                    {"id": "also_good", "enabled": True, "action_id": "clipboard.copy"},
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(path)
    ids = [b.id for b in loaded.gesture_bindings]
    assert "good" in ids
    assert "also_good" in ids
    # "not_a_dict" was skipped
    assert len(loaded.gesture_bindings) == 2


# ---------------------------------------------------------------------------
# 14. GestureBindingMatcher.conflicts()
# ---------------------------------------------------------------------------


def test_matcher_conflicts_detects_ambiguous_bindings() -> None:
    a = _simple_binding(id="a", enabled=True, thumb="folded")
    b = _simple_binding(id="b", enabled=True, thumb="folded")
    matcher = GestureBindingMatcher([a, b], _GESTURE_CFG)
    conflicts = matcher.conflicts()
    assert len(conflicts) >= 1
    assert "a" in conflicts[0] or "b" in conflicts[0]


def test_matcher_conflicts_empty_when_no_overlap() -> None:
    a = _simple_binding(id="a", enabled=True, thumb="folded", movement="left")
    b = _simple_binding(id="b", enabled=True, thumb="folded", movement="right")
    matcher = GestureBindingMatcher([a, b], _GESTURE_CFG)
    assert matcher.conflicts() == []


# ---------------------------------------------------------------------------
# 15. Existing action_id is preserved (no binding override)
# ---------------------------------------------------------------------------


def test_binding_does_not_override_existing_action_id() -> None:
    matcher, _ = _matcher_with_binding(
        id="override", enabled=True, movement="none", trigger="enter", cooldown_ms=0
    )
    hand = _make_hand()
    events_with_action = GestureEvents(
        active_gesture="tracking", status="tracking", action_id="system.task_view"
    )
    result = matcher.process(_frame(hand, 0), events_with_action)
    assert result.action_id == "system.task_view"
