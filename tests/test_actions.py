import pytest

from airpilot.actions import (
    ActionRouter,
    action_help_lines,
    dispatch_action,
    validate_action_config,
)
from airpilot.config import ActionConfig, GestureConfig, ShortcutConfig
from airpilot.domain.gestures import INDEX_TIP, MIDDLE_TIP, PINKY_TIP, RING_TIP, THUMB_TIP
from airpilot.domain.types import (
    CursorPosition,
    GestureEvents,
    HandLandmarks,
    Landmark,
    TrackingFrame,
)
from airpilot.input import RecordingMouseController


def test_action_help_lines_are_generated_from_config() -> None:
    lines = action_help_lines(ActionConfig())

    assert "QUICK START" in lines
    assert "MOUSE" in lines
    assert "CONTROL" in lines
    assert "SHORTCUT MODE" in lines
    assert "WINDOWS/APPS" in lines
    assert "BROWSER" in lines
    assert "PRESENTATION" in lines
    assert "MEDIA" in lines
    assert "RISKY" in lines
    assert lines.count("What it does | Gesture | Shortcut/Keys | State") >= 8
    assert any("Move pointer | Thumb open; move palm/knuckle" in line for line in lines)
    assert any("Left click | While clutched, bend/release index" in line for line in lines)
    assert any(
        "Clipboard history | Shortcut mode + hold thumb/middle | Win+V" in line for line in lines
    )
    assert any(
        "Open Task View | Shortcut Mode + hold thumb/index | Win+Tab" in line for line in lines
    )
    assert all(
        line.split(" | ")[0] != "Shortcut mode + hold thumb/middle"
        for line in lines
        if "Clipboard history" in line
    )


def test_action_help_lines_include_custom_profiles() -> None:
    actions = ActionConfig()
    actions.catalog["custom.action"] = ShortcutConfig(
        label="Custom action",
        keys=("ctrl", "alt", "p"),
        profile="custom",
        enabled=True,
    )

    lines = action_help_lines(actions)

    assert any("Custom action | Configure in action catalog | Ctrl+Alt+P" in line for line in lines)


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


def test_default_actions_use_task_view_instead_of_alt_tab_gesture() -> None:
    actions = ActionConfig()

    assert actions.gesture_actions["arm_secondary_middle_hold"] == "ui.arm"
    assert "shortcut_index_hold" not in actions.gesture_actions
    assert actions.catalog["system.task_view"].keys == ("win", "tab")
    assert actions.catalog["window.switch"].keys == ("alt", "tab")


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


def test_action_router_arms_with_secondary_middle_hold() -> None:
    router = ActionRouter(ActionConfig(), GestureConfig(arm_gesture_hold_ms=500))
    control = _hand()
    secondary = _hand(middle=(0.51, 0.50))

    pending = router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(left_click=True),
    )
    assert pending.active_gesture == "arm_pending"
    assert not pending.left_click
    assert pending.action_id is None

    armed = router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    assert armed.action_id == "ui.arm"
    assert armed.action_label == "Arm AirPilot"

    still_held = router.process(
        TrackingFrame(
            timestamp_ms=1300,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    assert still_held.action_id is None


def test_action_router_task_view_opens_navigates_and_confirms() -> None:
    router = ActionRouter(
        ActionConfig(),
        GestureConfig(
            shortcut_mode_hold_ms=0,
            shortcut_action_hold_ms=500,
            task_view_navigation_delta=0.05,
            task_view_navigation_cooldown_ms=250,
            task_view_mirror_x=False,
        ),
    )
    secondary = _hand(pinky=(0.51, 0.50))
    pending_control = _hand(index=(0.51, 0.50))

    pending = router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=pending_control,
            hands=(pending_control, secondary),
        ),
        GestureEvents(move=CursorPosition(10, 10)),
    )
    assert pending.active_gesture == "task_view_pending"
    assert pending.move is None

    held_control = _hand(index=(0.51, 0.50))
    opened = router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=held_control,
            hands=(held_control, secondary),
        ),
        GestureEvents(),
    )
    assert opened.action_id == "system.task_view"

    right_control = _hand(thumb=(0.59, 0.50), index=(0.60, 0.50))
    next_app = router.process(
        TrackingFrame(
            timestamp_ms=900,
            width=640,
            height=480,
            hand=right_control,
            hands=(right_control, secondary),
        ),
        GestureEvents(left_click=True),
    )
    assert next_app.action_id == "task_view.next"
    assert not next_app.left_click

    cooldown_control = _hand(thumb=(0.69, 0.50), index=(0.70, 0.50))
    cooldown = router.process(
        TrackingFrame(
            timestamp_ms=950,
            width=640,
            height=480,
            hand=cooldown_control,
            hands=(cooldown_control, secondary),
        ),
        GestureEvents(),
    )
    assert cooldown.action_id is None
    assert cooldown.status == "task_view_cooldown"

    release_control = _hand(index=(0.70, 0.50))
    confirmed = router.process(
        TrackingFrame(
            timestamp_ms=1300,
            width=640,
            height=480,
            hand=release_control,
            hands=(release_control, secondary),
        ),
        GestureEvents(),
    )
    assert confirmed.action_id == "task_view.confirm"


def test_action_router_task_view_confirms_when_both_hands_release() -> None:
    router = ActionRouter(
        ActionConfig(),
        GestureConfig(
            shortcut_mode_hold_ms=0,
            shortcut_action_hold_ms=500,
            task_view_confirm_on_release=True,
        ),
    )
    secondary = _hand(pinky=(0.51, 0.50))
    control = _hand(index=(0.51, 0.50))

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
    router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    released = router.process(
        TrackingFrame(timestamp_ms=700, width=640, height=480, hand=_hand()),
        GestureEvents(),
    )

    assert released.action_id == "task_view.confirm"


def test_action_router_task_view_confirms_and_suppresses_after_tracking_loss_release() -> None:
    router = ActionRouter(
        ActionConfig(),
        GestureConfig(
            shortcut_mode_hold_ms=0,
            shortcut_action_hold_ms=500,
            task_view_confirm_on_release=True,
        ),
    )
    secondary = _hand(pinky=(0.51, 0.50))
    control = _hand(index=(0.51, 0.50))

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
    router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    confirmed = router.process(
        TrackingFrame(timestamp_ms=700, width=640, height=480, hand=None),
        GestureEvents(),
    )
    release = router.process(
        TrackingFrame(timestamp_ms=800, width=640, height=480, hand=_hand()),
        GestureEvents(left_click=True),
    )

    assert confirmed.action_id == "task_view.confirm"
    assert release.action_id is None
    assert not release.left_click


def test_action_router_task_view_cancels_when_shortcut_mode_drops_but_index_stays_held() -> None:
    router = ActionRouter(
        ActionConfig(),
        GestureConfig(
            shortcut_mode_hold_ms=0,
            shortcut_action_hold_ms=500,
            task_view_confirm_on_release=True,
        ),
    )
    secondary = _hand(pinky=(0.51, 0.50))
    control = _hand(index=(0.51, 0.50))

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
    router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=control,
            hands=(control, secondary),
        ),
        GestureEvents(),
    )
    cancelled = router.process(
        TrackingFrame(timestamp_ms=700, width=640, height=480, hand=control),
        GestureEvents(),
    )

    assert cancelled.action_id == "task_view.cancel"

    release = router.process(
        TrackingFrame(timestamp_ms=800, width=640, height=480, hand=_hand()),
        GestureEvents(left_click=True),
    )
    assert release.action_id is None
    assert not release.left_click


def test_action_router_task_view_cancel_suppression_survives_missing_hand() -> None:
    router = ActionRouter(
        ActionConfig(),
        GestureConfig(
            shortcut_mode_hold_ms=0,
            shortcut_action_hold_ms=500,
            task_view_confirm_on_release=True,
        ),
    )
    secondary = _hand(pinky=(0.51, 0.50))
    held_control = _hand(index=(0.51, 0.50))

    router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=held_control,
            hands=(held_control, secondary),
        ),
        GestureEvents(),
    )
    router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=held_control,
            hands=(held_control, secondary),
        ),
        GestureEvents(),
    )
    router.process(
        TrackingFrame(timestamp_ms=700, width=640, height=480, hand=held_control),
        GestureEvents(),
    )
    missing = router.process(
        TrackingFrame(timestamp_ms=720, width=640, height=480, hand=None),
        GestureEvents(),
    )
    reappeared = router.process(
        TrackingFrame(timestamp_ms=740, width=640, height=480, hand=held_control),
        GestureEvents(),
    )
    release = router.process(
        TrackingFrame(timestamp_ms=800, width=640, height=480, hand=_hand()),
        GestureEvents(left_click=True),
    )

    assert missing.active_gesture == "shortcut_cancel_pending"
    assert reappeared.active_gesture == "shortcut_cancel_pending"
    assert release.action_id is None
    assert not release.left_click


def test_action_router_task_view_cancel_suppression_waits_for_release_threshold() -> None:
    router = ActionRouter(
        ActionConfig(),
        GestureConfig(
            shortcut_mode_hold_ms=0,
            shortcut_action_hold_ms=500,
            pinch_threshold=0.055,
            pinch_release_threshold=0.075,
            task_view_confirm_on_release=True,
        ),
    )
    secondary = _hand(pinky=(0.51, 0.50))
    held_control = _hand(index=(0.51, 0.50))
    between_thresholds = _hand(index=(0.565, 0.50))

    router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=held_control,
            hands=(held_control, secondary),
        ),
        GestureEvents(),
    )
    router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=held_control,
            hands=(held_control, secondary),
        ),
        GestureEvents(),
    )
    router.process(
        TrackingFrame(timestamp_ms=700, width=640, height=480, hand=held_control),
        GestureEvents(),
    )
    router.process(
        TrackingFrame(timestamp_ms=720, width=640, height=480, hand=None),
        GestureEvents(),
    )
    still_suppressed = router.process(
        TrackingFrame(timestamp_ms=740, width=640, height=480, hand=between_thresholds),
        GestureEvents(left_click=True),
    )
    released = router.process(
        TrackingFrame(timestamp_ms=800, width=640, height=480, hand=_hand()),
        GestureEvents(left_click=True),
    )

    assert still_suppressed.active_gesture == "shortcut_cancel_pending"
    assert not still_suppressed.left_click
    assert released.active_gesture == "shortcut_cancel_release"
    assert not released.left_click


def test_action_router_clears_pending_task_view_when_shortcut_mode_cancels() -> None:
    router = ActionRouter(
        ActionConfig(),
        GestureConfig(shortcut_mode_hold_ms=0, shortcut_action_hold_ms=500),
    )
    secondary = _hand(pinky=(0.51, 0.50))
    held_control = _hand(index=(0.51, 0.50))

    router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=held_control,
            hands=(held_control, secondary),
        ),
        GestureEvents(),
    )
    cancelled = router.process(
        TrackingFrame(timestamp_ms=100, width=640, height=480, hand=held_control),
        GestureEvents(),
    )
    released_outside_mode = router.process(
        TrackingFrame(timestamp_ms=200, width=640, height=480, hand=_hand()),
        GestureEvents(left_click=True),
    )
    neutral_reentry = router.process(
        TrackingFrame(
            timestamp_ms=300,
            width=640,
            height=480,
            hand=_hand(),
            hands=(_hand(), secondary),
        ),
        GestureEvents(),
    )

    assert cancelled.action_id is None
    assert released_outside_mode.action_id is None
    assert not released_outside_mode.left_click
    assert neutral_reentry.action_id is None


def test_action_router_pending_task_view_cancel_waits_for_release_threshold() -> None:
    router = ActionRouter(
        ActionConfig(),
        GestureConfig(
            shortcut_mode_hold_ms=0,
            shortcut_action_hold_ms=500,
            pinch_threshold=0.055,
            pinch_release_threshold=0.075,
        ),
    )
    secondary = _hand(pinky=(0.51, 0.50))
    held_control = _hand(index=(0.51, 0.50))
    between_thresholds = _hand(index=(0.565, 0.50))

    router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=held_control,
            hands=(held_control, secondary),
        ),
        GestureEvents(),
    )
    cancelled = router.process(
        TrackingFrame(timestamp_ms=100, width=640, height=480, hand=between_thresholds),
        GestureEvents(left_click=True),
    )
    release = router.process(
        TrackingFrame(timestamp_ms=200, width=640, height=480, hand=_hand()),
        GestureEvents(left_click=True),
    )

    assert cancelled.active_gesture == "shortcut_cancel_pending"
    assert not cancelled.left_click
    assert release.active_gesture == "shortcut_cancel_release"
    assert not release.left_click


def test_action_router_disabled_task_view_does_not_emit_navigation_or_confirm() -> None:
    actions = ActionConfig()
    actions.catalog["system.task_view"].enabled = False
    router = ActionRouter(
        actions,
        GestureConfig(
            shortcut_mode_hold_ms=0,
            shortcut_action_hold_ms=500,
            task_view_navigation_delta=0.05,
            task_view_navigation_cooldown_ms=0,
            task_view_mirror_x=False,
        ),
    )
    secondary = _hand(pinky=(0.51, 0.50))

    start_control = _hand(index=(0.51, 0.50))
    router.process(
        TrackingFrame(
            timestamp_ms=0,
            width=640,
            height=480,
            hand=start_control,
            hands=(start_control, secondary),
        ),
        GestureEvents(),
    )
    disabled = router.process(
        TrackingFrame(
            timestamp_ms=600,
            width=640,
            height=480,
            hand=start_control,
            hands=(start_control, secondary),
        ),
        GestureEvents(),
    )

    move_control = _hand(thumb=(0.69, 0.50), index=(0.70, 0.50))
    moved = router.process(
        TrackingFrame(
            timestamp_ms=800,
            width=640,
            height=480,
            hand=move_control,
            hands=(move_control, secondary),
        ),
        GestureEvents(),
    )
    released = router.process(
        TrackingFrame(
            timestamp_ms=1000,
            width=640,
            height=480,
            hand=_hand(),
            hands=(_hand(), secondary),
        ),
        GestureEvents(),
    )

    assert disabled.active_gesture == "task_view_disabled"
    assert disabled.action_id is None
    assert moved.action_id is None
    assert released.action_id is None


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
