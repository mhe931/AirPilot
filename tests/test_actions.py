import pytest

from airpilot.actions import (
    ActionRouter,
    action_help_lines,
    dispatch_action,
    validate_action_config,
)
from airpilot.config import ActionConfig, GestureConfig, ShortcutConfig
from airpilot.domain.gestures import INDEX_TIP, MIDDLE_TIP, PINKY_TIP, RING_TIP, THUMB_TIP
from airpilot.domain.types import GestureEvents, HandLandmarks, Landmark, TrackingFrame
from airpilot.input import RecordingMouseController


def test_action_help_lines_are_generated_from_config() -> None:
    lines = action_help_lines(ActionConfig())

    assert "PHILOSOPHY" in lines
    assert "CORE MOUSE GESTURES" in lines
    assert "SHORTCUT MODE" in lines
    assert "AVAILABLE SHORTCUT ACTIONS" in lines
    assert any("Thumb + index pinch/release | Left click" in line for line in lines)
    assert any("Copy" in line for line in lines)
    assert any("Clipboard history `Win+V`" in line for line in lines)
    assert any("RISKY ACTIONS" in line for line in lines)


def test_action_help_lines_include_custom_profiles() -> None:
    actions = ActionConfig()
    actions.catalog["custom.action"] = ShortcutConfig(
        label="Custom action",
        keys=("ctrl", "alt", "p"),
        profile="custom",
        enabled=True,
    )

    lines = action_help_lines(actions)

    assert "Custom" in lines
    assert any("Custom action" in line for line in lines)


def test_validate_action_config_rejects_unknown_binding() -> None:
    actions = ActionConfig()
    actions.gesture_actions["unknown"] = "clipboard.copy"

    with pytest.raises(ValueError, match="Unknown AirPilot gesture"):
        validate_action_config(actions)


def test_validate_action_config_rejects_unflagged_risky_shortcut() -> None:
    actions = ActionConfig()
    actions.catalog["custom.close"] = ShortcutConfig(
        label="Close",
        keys=("alt", "f4"),
        enabled=True,
        risky=False,
    )

    with pytest.raises(ValueError, match="Risky AirPilot shortcut"):
        validate_action_config(actions)


def test_validate_action_config_rejects_unflagged_risky_shortcut_alias() -> None:
    actions = ActionConfig()
    actions.catalog["custom.lock"] = ShortcutConfig(
        label="Lock",
        keys=("winleft", "l"),
        enabled=True,
        risky=False,
    )

    with pytest.raises(ValueError, match="Risky AirPilot shortcut"):
        validate_action_config(actions)


def test_validate_action_config_allows_empty_gesture_mappings() -> None:
    validate_action_config(ActionConfig(gesture_actions={}))


def test_dispatch_action_uses_fake_mouse_and_skips_risky_disabled_actions() -> None:
    actions = ActionConfig()
    mouse = RecordingMouseController()

    assert dispatch_action(actions, mouse, "clipboard.copy") == "Copy"
    assert dispatch_action(actions, mouse, "system.lock") is None

    assert mouse.actions == ["hotkey:ctrl+c"]


def test_clipboard_history_uses_fake_win_v_shortcut() -> None:
    actions = ActionConfig()
    mouse = RecordingMouseController()

    assert actions.catalog["clipboard.history"].keys == ("win", "v")
    assert dispatch_action(actions, mouse, "clipboard.history") == "Clipboard history"

    assert mouse.actions == ["hotkey:win+v"]


def test_action_router_requires_two_hand_shortcut_mode_before_shortcut() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(shortcut_mode_hold_ms=100))
    control = _hand(index=(0.51, 0.50))
    secondary = _hand(pinky=(0.51, 0.50))

    pending = router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    assert pending.shortcut_mode
    assert pending.action_id is None

    active = router.process(
        TrackingFrame(
            timestamp_ms=120,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(left_click=True),
    )
    assert active.shortcut_mode
    assert not active.left_click

    released_control = _hand()
    released = router.process(
        TrackingFrame(
            timestamp_ms=250,
            width=640,
            height=480,
            hand=released_control,
            hands=(released_control, secondary),
        ),
        GestureEvents(),
    )
    assert released.action_id == "clipboard.copy"
    assert released.action_label == "Copy"


def test_action_router_middle_hold_triggers_clipboard_history() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(shortcut_mode_hold_ms=0))
    control = _hand(middle=(0.51, 0.50))
    secondary = _hand(pinky=(0.51, 0.50))

    started = router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    held = router.process(
        TrackingFrame(
            timestamp_ms=700,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    released = router.process(
        TrackingFrame(
            timestamp_ms=800,
            width=640,
            height=480,
            hand=_hand(),
            hands=(_hand(), secondary),
        ),
        GestureEvents(),
    )

    assert started.action_id is None
    assert held.action_id == "clipboard.history"
    assert held.action_label == "Clipboard history"
    assert released.action_id is None


def test_action_router_toggles_help_with_secondary_index_hold() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(help_gesture_hold_ms=500))
    control = _hand()
    secondary = _hand(index=(0.51, 0.50))

    pending = router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    assert pending.active_gesture == "help_pending"
    assert pending.action_id is None

    toggled = router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    assert toggled.action_id == "ui.toggle_help"
    assert toggled.action_label == "Toggle help"

    still_held = router.process(
        TrackingFrame(
            timestamp_ms=1300,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(left_click=True, scroll=5),
    )
    assert still_held.action_id is None
    assert not still_held.left_click
    assert still_held.scroll == 0


def test_action_router_help_gesture_suppresses_mouse_events() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(help_gesture_hold_ms=0))
    control = _hand()
    secondary = _hand(index=(0.51, 0.50))

    router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    events = router.process(
        TrackingFrame(
            timestamp_ms=1,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(left_click=True, right_click=True, middle_click=True, scroll=3),
    )

    assert events.action_id == "ui.toggle_help"
    assert not events.shortcut_mode
    assert not events.left_click
    assert not events.right_click
    assert not events.middle_click
    assert events.scroll == 0


def test_action_router_help_gesture_releases_active_drag() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(help_gesture_hold_ms=0))
    control = _hand()
    secondary = _hand(index=(0.51, 0.50))

    router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    events = router.process(
        TrackingFrame(
            timestamp_ms=1,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(active_gesture="dragging", status="dragging"),
    )

    assert events.action_id == "ui.toggle_help"
    assert events.drag_end


def test_action_router_help_gesture_does_not_overlap_shortcut_mode() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(help_gesture_hold_ms=0))
    control = _hand()
    secondary = _hand(index=(0.51, 0.50), pinky=(0.51, 0.50))

    events = router.process(
        TrackingFrame(
            timestamp_ms=1000,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )

    assert events.action_id is None
    assert events.shortcut_mode


def test_action_router_suppresses_mouse_events_during_shortcut_pending() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(shortcut_mode_hold_ms=650))
    control = _hand()
    secondary = _hand(pinky=(0.51, 0.50))

    events = router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(left_click=True, right_click=True, middle_click=True, scroll=3),
    )

    assert events.shortcut_mode
    assert not events.left_click
    assert not events.right_click
    assert not events.middle_click
    assert events.scroll == 0


def test_action_router_preserves_drag_release_during_shortcut_mode() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(shortcut_mode_hold_ms=0))
    control = _hand()
    secondary = _hand(pinky=(0.51, 0.50))

    events = router.process(
        TrackingFrame(
            timestamp_ms=100,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(drag_end=True),
    )

    assert events.shortcut_mode
    assert events.drag_end


def test_action_router_releases_active_drag_when_shortcut_mode_starts() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(shortcut_mode_hold_ms=0))
    control = _hand()
    secondary = _hand(pinky=(0.51, 0.50))

    events = router.process(
        TrackingFrame(
            timestamp_ms=100,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(active_gesture="dragging", status="dragging"),
    )

    assert events.shortcut_mode
    assert events.drag_end


def _hand(
    *,
    thumb: tuple[float, float] = (0.50, 0.50),
    index: tuple[float, float] = (0.70, 0.50),
    middle: tuple[float, float] = (0.50, 0.70),
    ring: tuple[float, float] = (0.40, 0.70),
    pinky: tuple[float, float] = (0.30, 0.70),
) -> HandLandmarks:
    points = [Landmark(x=0.5, y=0.5) for _ in range(21)]
    points[THUMB_TIP] = Landmark(*thumb)
    points[INDEX_TIP] = Landmark(*index)
    points[MIDDLE_TIP] = Landmark(*middle)
    points[RING_TIP] = Landmark(*ring)
    points[PINKY_TIP] = Landmark(*pinky)
    return HandLandmarks(tuple(points))
