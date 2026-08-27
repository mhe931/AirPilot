from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = 10

_V4_CURSOR_DEFAULTS = {
    "camera_min_x": 0.08,
    "camera_max_x": 0.92,
    "camera_min_y": 0.08,
    "camera_max_y": 0.88,
    "sensitivity": 1.0,
    "smoothing_alpha": 0.28,
    "dead_zone_px": 5,
}

_V8_GESTURE_DEFAULTS = {
    "thumb_open_threshold": 0.95,
}

_V5_SCROLL_DEFAULTS = {
    "scroll_pinch_threshold": 0.065,
    "scroll_pinch_release_threshold": 0.085,
    "scroll_activation_y_delta": 0.018,
    "scroll_units_per_step": 3,
}


@dataclass(slots=True)
class GestureConfig:
    min_click_hold_ms: int = 80
    pinch_threshold: float = 0.055
    pinch_release_threshold: float = 0.075
    right_pinch_threshold: float = 0.065
    right_pinch_release_threshold: float = 0.085
    scroll_pinch_threshold: float = 0.085
    scroll_pinch_release_threshold: float = 0.130
    pause_pinch_threshold: float = 0.070
    pause_pinch_release_threshold: float = 0.095
    scroll_activation_y_delta: float = 0.012
    scroll_sensitivity: float = 1.4
    scroll_cooldown_ms: int = 35
    scroll_units_per_step: int = 2
    click_freeze_radius_px: int = 16
    drag_start_movement_px: int = 34
    shortcut_mode_hold_ms: int = 650
    shortcut_action_hold_ms: int = 650
    help_gesture_hold_ms: int = 900
    help_gesture_enabled: bool = True
    arm_gesture_hold_ms: int = 1200
    arm_gesture_enabled: bool = True
    arm_pinch_threshold: float = 0.070
    arm_pinch_release_threshold: float = 0.100
    task_view_navigation_delta: float = 0.070
    task_view_navigation_cooldown_ms: int = 300
    task_view_confirm_on_release: bool = True
    task_view_mirror_x: bool = True
    pause_gesture_enabled: bool = False
    action_cooldown_ms: int = 700
    click_cooldown_ms: int = 350
    drag_hold_ms: int = 450
    pause_hold_ms: int = 850
    tracking_loss_grace_ms: int = 250
    thumb_close_threshold: float = 0.72
    thumb_open_threshold: float = 0.82
    finger_bend_threshold: float = 1.35
    finger_extend_threshold: float = 1.70
    # Angle-based thumb activation (replaces score-based when enabled)
    use_thumb_angle_activation: bool = True
    thumb_angle_target_deg: float = 90.0
    thumb_angle_tolerance_deg: float = 10.0
    thumb_angle_hysteresis_deg: float = 0.0
    # Scroll enhancements
    scroll_natural_direction: bool = False
    scroll_dead_zone: float = 0.004


@dataclass(slots=True)
class CursorConfig:
    screen_left: int = 0
    screen_top: int = 0
    screen_width: int = 1920
    screen_height: int = 1080
    camera_min_x: float = 0.16
    camera_max_x: float = 0.84
    camera_min_y: float = 0.12
    camera_max_y: float = 0.82
    sensitivity: float = 1.35
    smoothing_alpha: float = 0.42
    dead_zone_px: int = 3
    mirror_x: bool = True


@dataclass(slots=True)
class ShortcutConfig:
    label: str
    keys: tuple[str, ...]
    profile: str = "global"
    enabled: bool = True
    risky: bool = False


def _default_shortcut_catalog() -> dict[str, ShortcutConfig]:
    return {
        "ui.toggle_help": ShortcutConfig("Toggle help", (), "ui"),
        "ui.arm": ShortcutConfig("Arm AirPilot", (), "ui"),
        "clipboard.copy": ShortcutConfig("Copy", ("ctrl", "c"), "editing"),
        "clipboard.paste": ShortcutConfig("Paste", ("ctrl", "v"), "editing"),
        "clipboard.cut": ShortcutConfig("Cut", ("ctrl", "x"), "editing", enabled=False),
        "clipboard.history": ShortcutConfig("Clipboard history", ("win", "v"), "editing"),
        "editing.undo": ShortcutConfig("Undo", ("ctrl", "z"), "editing", enabled=False),
        "editing.redo": ShortcutConfig("Redo", ("ctrl", "y"), "editing", enabled=False),
        "editing.select_all": ShortcutConfig("Select all", ("ctrl", "a"), "editing", enabled=False),
        "editing.save": ShortcutConfig("Save", ("ctrl", "s"), "editing", enabled=False),
        "editing.find": ShortcutConfig("Find", ("ctrl", "f"), "editing", enabled=False),
        "browser.new_tab": ShortcutConfig("New tab", ("ctrl", "t"), "browser", enabled=False),
        "browser.close_tab": ShortcutConfig(
            "Close tab",
            ("ctrl", "w"),
            "browser",
            enabled=False,
            risky=True,
        ),
        "browser.reopen_tab": ShortcutConfig(
            "Reopen tab",
            ("ctrl", "shift", "t"),
            "browser",
            enabled=False,
        ),
        "browser.next_tab": ShortcutConfig("Next tab", ("ctrl", "tab"), "browser", enabled=False),
        "browser.previous_tab": ShortcutConfig(
            "Previous tab",
            ("ctrl", "shift", "tab"),
            "browser",
            enabled=False,
        ),
        "browser.refresh": ShortcutConfig("Refresh", ("f5",), "browser", enabled=False),
        "browser.back": ShortcutConfig("Back", ("alt", "left"), "browser", enabled=False),
        "browser.forward": ShortcutConfig("Forward", ("alt", "right"), "browser", enabled=False),
        "presentation.next_slide": ShortcutConfig("Next slide", ("right",), "presentation"),
        "presentation.previous_slide": ShortcutConfig("Previous slide", ("left",), "presentation"),
        "presentation.start": ShortcutConfig(
            "Start slideshow", ("f5",), "presentation", enabled=False
        ),
        "presentation.exit": ShortcutConfig(
            "Exit slideshow", ("esc",), "presentation", enabled=False
        ),
        "window.switch": ShortcutConfig("Switch app", ("alt", "tab"), "windows"),
        "window.switch_reverse": ShortcutConfig(
            "Switch app reverse",
            ("alt", "shift", "tab"),
            "windows",
            enabled=False,
        ),
        "window.close": ShortcutConfig(
            "Close window",
            ("alt", "f4"),
            "windows",
            enabled=False,
            risky=True,
        ),
        "window.minimize": ShortcutConfig("Minimize", ("win", "down"), "windows", enabled=False),
        "window.maximize": ShortcutConfig("Maximize", ("win", "up"), "windows", enabled=False),
        "window.snap_left": ShortcutConfig("Snap left", ("win", "left"), "windows", enabled=False),
        "window.snap_right": ShortcutConfig(
            "Snap right", ("win", "right"), "windows", enabled=False
        ),
        "desktop.next": ShortcutConfig(
            "Next desktop", ("ctrl", "win", "right"), "windows", enabled=False
        ),
        "desktop.previous": ShortcutConfig(
            "Previous desktop",
            ("ctrl", "win", "left"),
            "windows",
            enabled=False,
        ),
        "desktop.task_view": ShortcutConfig("Task view", ("win", "tab"), "windows", enabled=False),
        "system.task_view": ShortcutConfig("Open Task View", ("win", "tab"), "windows"),
        "task_view.next": ShortcutConfig("Task View select right", ("right",), "windows"),
        "task_view.previous": ShortcutConfig("Task View select left", ("left",), "windows"),
        "task_view.confirm": ShortcutConfig("Task View open selection", ("enter",), "windows"),
        "task_view.cancel": ShortcutConfig("Task View cancel", ("esc",), "windows"),
        "system.lock": ShortcutConfig(
            "Lock workstation",
            ("win", "l"),
            "windows",
            enabled=False,
            risky=True,
        ),
        "system.show_desktop": ShortcutConfig(
            "Show desktop", ("win", "d"), "windows", enabled=False
        ),
        "system.explorer": ShortcutConfig("File Explorer", ("win", "e"), "windows", enabled=False),
        "system.search": ShortcutConfig("Search", ("win", "s"), "windows", enabled=False),
        "system.settings": ShortcutConfig("Settings", ("win", "i"), "windows", enabled=False),
        "media.play_pause": ShortcutConfig("Play/pause", ("playpause",), "media", enabled=False),
        "media.mute": ShortcutConfig("Mute", ("volumemute",), "media", enabled=False),
        "media.volume_up": ShortcutConfig("Volume up", ("volumeup",), "media", enabled=False),
        "media.volume_down": ShortcutConfig("Volume down", ("volumedown",), "media", enabled=False),
        "media.next": ShortcutConfig("Next media", ("nexttrack",), "media", enabled=False),
        "media.previous": ShortcutConfig("Previous media", ("prevtrack",), "media", enabled=False),
    }


def _default_gesture_actions() -> dict[str, str]:
    return {
        "arm_secondary_middle_hold": "ui.arm",
        "help_secondary_index_hold": "ui.toggle_help",
        "shortcut_index_release": "clipboard.copy",
        "shortcut_middle_release": "clipboard.paste",
        "shortcut_middle_hold": "clipboard.history",
        "shortcut_ring_release": "presentation.next_slide",
        "shortcut_pinky_release": "presentation.previous_slide",
    }


@dataclass(slots=True)
class ActionConfig:
    enabled: bool = True
    risky_actions_enabled: bool = False
    shortcut_mode_gesture: str = "secondary_thumb_pinky_hold"
    gesture_actions: dict[str, str] = field(default_factory=_default_gesture_actions)
    catalog: dict[str, ShortcutConfig] = field(default_factory=_default_shortcut_catalog)


@dataclass(slots=True)
class RuntimeConfig:
    camera_index: int = 0
    max_camera_index: int = 4
    camera_read_failures_before_error: int = 10
    camera_reconnect_attempts: int = 6
    camera_reconnect_delay_ms: int = 500
    flip_camera_x: bool = False
    draw_landmarks: bool = True
    show_gesture_help: bool = False
    enable_real_mouse: bool = True
    start_armed: bool = False
    emergency_corner_failsafe: bool = True
    tracker_detection_confidence: float = 0.55
    tracker_tracking_confidence: float = 0.55


@dataclass(slots=True)
class AppConfig:
    schema_version: int = CURRENT_SCHEMA_VERSION
    gestures: GestureConfig = field(default_factory=GestureConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)
    actions: ActionConfig = field(default_factory=ActionConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


def default_config_path() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return root / "AirPilot" / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return AppConfig()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("AirPilot config root must be an object")
    return _config_from_dict(raw)


def read_config_schema_version(path: Path) -> int | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("AirPilot config root must be an object")
    version = raw.get("schema_version", 1)
    if not isinstance(version, int):
        raise ValueError("AirPilot config schema_version must be an integer")
    return version


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(asdict(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config_path


def _config_from_dict(raw: dict[str, Any]) -> AppConfig:
    version = raw.get("schema_version", 1)
    if version == 1:
        return _migrate_v1_config(raw)
    if version == 2:
        return _migrate_v2_config(raw)
    if version == 3:
        return _migrate_v3_config(raw)
    if version == 4:
        return _migrate_v4_config(raw)
    if version == 5:
        return _migrate_v5_config(raw)
    if version == 6:
        return _migrate_v6_config(raw)
    if version == 7:
        return _migrate_v7_config(raw)
    if version == 8:
        return _migrate_v8_config(raw)
    if version == 9:
        return _migrate_v9_config(raw)
    if version != CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported AirPilot config schema_version {version!r}")
    return AppConfig(
        schema_version=version,
        gestures=_gestures_from_section(_section(raw, "gestures")),
        cursor=CursorConfig(**_section(raw, "cursor")),
        actions=_actions_from_section(_section(raw, "actions")),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    section = raw.get(name, {})
    if not isinstance(section, dict):
        raise ValueError(f"AirPilot config section {name!r} must be an object")
    return section


def _migrate_v1_config(raw: dict[str, Any]) -> AppConfig:
    cursor_section = dict(_section(raw, "cursor"))
    cursor_section["mirror_x"] = True
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_migrated_v6_gestures(_section(raw, "gestures"))),
        cursor=CursorConfig(**cursor_section),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _migrate_v2_config(raw: dict[str, Any]) -> AppConfig:
    runtime_section = dict(_section(raw, "runtime"))
    runtime_section["flip_camera_x"] = False
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_migrated_v6_gestures(_section(raw, "gestures"))),
        cursor=_migrated_cursor(_section(raw, "cursor")),
        runtime=RuntimeConfig(**runtime_section),
    )


def _migrate_v3_config(raw: dict[str, Any]) -> AppConfig:
    runtime_section = dict(_section(raw, "runtime"))
    runtime_section["flip_camera_x"] = False
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_migrated_v6_gestures(_section(raw, "gestures"))),
        cursor=_migrated_cursor(_section(raw, "cursor")),
        runtime=RuntimeConfig(**runtime_section),
    )


def _migrated_cursor(raw: dict[str, Any]) -> CursorConfig:
    cursor_section = dict(raw)
    if cursor_section.get("mirror_x") is False or "mirror_x" not in cursor_section:
        cursor_section["mirror_x"] = True
    return CursorConfig(**cursor_section)


def _gestures_from_section(raw: dict[str, Any]) -> GestureConfig:
    defaults = GestureConfig()
    section: dict[str, Any] = {
        "min_click_hold_ms": defaults.min_click_hold_ms,
        "pinch_threshold": defaults.pinch_threshold,
        "pinch_release_threshold": defaults.pinch_release_threshold,
        "right_pinch_threshold": defaults.right_pinch_threshold,
        "right_pinch_release_threshold": defaults.right_pinch_release_threshold,
        "scroll_pinch_threshold": defaults.scroll_pinch_threshold,
        "scroll_pinch_release_threshold": defaults.scroll_pinch_release_threshold,
        "pause_pinch_threshold": defaults.pause_pinch_threshold,
        "pause_pinch_release_threshold": defaults.pause_pinch_release_threshold,
        "scroll_activation_y_delta": defaults.scroll_activation_y_delta,
        "scroll_sensitivity": defaults.scroll_sensitivity,
        "scroll_cooldown_ms": defaults.scroll_cooldown_ms,
        "scroll_units_per_step": defaults.scroll_units_per_step,
        "click_freeze_radius_px": defaults.click_freeze_radius_px,
        "drag_start_movement_px": defaults.drag_start_movement_px,
        "shortcut_mode_hold_ms": defaults.shortcut_mode_hold_ms,
        "shortcut_action_hold_ms": defaults.shortcut_action_hold_ms,
        "help_gesture_hold_ms": defaults.help_gesture_hold_ms,
        "help_gesture_enabled": defaults.help_gesture_enabled,
        "arm_gesture_hold_ms": defaults.arm_gesture_hold_ms,
        "arm_gesture_enabled": defaults.arm_gesture_enabled,
        "arm_pinch_threshold": defaults.arm_pinch_threshold,
        "arm_pinch_release_threshold": defaults.arm_pinch_release_threshold,
        "task_view_navigation_delta": defaults.task_view_navigation_delta,
        "task_view_navigation_cooldown_ms": defaults.task_view_navigation_cooldown_ms,
        "task_view_confirm_on_release": defaults.task_view_confirm_on_release,
        "task_view_mirror_x": defaults.task_view_mirror_x,
        "pause_gesture_enabled": defaults.pause_gesture_enabled,
        "action_cooldown_ms": defaults.action_cooldown_ms,
        "click_cooldown_ms": defaults.click_cooldown_ms,
        "drag_hold_ms": defaults.drag_hold_ms,
        "pause_hold_ms": defaults.pause_hold_ms,
        "tracking_loss_grace_ms": defaults.tracking_loss_grace_ms,
        "thumb_close_threshold": defaults.thumb_close_threshold,
        "thumb_open_threshold": defaults.thumb_open_threshold,
        "finger_bend_threshold": defaults.finger_bend_threshold,
        "finger_extend_threshold": defaults.finger_extend_threshold,
        "use_thumb_angle_activation": defaults.use_thumb_angle_activation,
        "thumb_angle_target_deg": defaults.thumb_angle_target_deg,
        "thumb_angle_tolerance_deg": defaults.thumb_angle_tolerance_deg,
        "thumb_angle_hysteresis_deg": defaults.thumb_angle_hysteresis_deg,
        "scroll_natural_direction": defaults.scroll_natural_direction,
        "scroll_dead_zone": defaults.scroll_dead_zone,
    }
    section.update(raw)
    return GestureConfig(**section)


def _migrate_v4_config(raw: dict[str, Any]) -> AppConfig:
    runtime_section = dict(_section(raw, "runtime"))
    runtime_section["show_gesture_help"] = False
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_migrated_v6_gestures(_section(raw, "gestures"))),
        cursor=CursorConfig(**_migrated_v5_cursor(_section(raw, "cursor"))),
        actions=_actions_from_section(_migrated_v7_actions(_section(raw, "actions"))),
        runtime=RuntimeConfig(**runtime_section),
    )


def _migrate_v5_config(raw: dict[str, Any]) -> AppConfig:
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_migrated_v6_gestures(_section(raw, "gestures"))),
        cursor=CursorConfig(**_section(raw, "cursor")),
        actions=_actions_from_section(_migrated_v7_actions(_section(raw, "actions"))),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _migrate_v6_config(raw: dict[str, Any]) -> AppConfig:
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_section(raw, "gestures")),
        cursor=CursorConfig(**_section(raw, "cursor")),
        actions=_actions_from_section(_migrated_v7_actions(_section(raw, "actions"))),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _migrate_v7_config(raw: dict[str, Any]) -> AppConfig:
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_migrated_v9_gestures(_section(raw, "gestures"))),
        cursor=CursorConfig(**_section(raw, "cursor")),
        actions=_actions_from_section(_section(raw, "actions")),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _migrate_v8_config(raw: dict[str, Any]) -> AppConfig:
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_migrated_v9_gestures(_section(raw, "gestures"))),
        cursor=CursorConfig(**_section(raw, "cursor")),
        actions=_actions_from_section(_section(raw, "actions")),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _migrate_v9_config(raw: dict[str, Any]) -> AppConfig:
    """v9 → v10: new thumb-angle and scroll-enhancement fields gain safe defaults."""
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_section(raw, "gestures")),
        cursor=CursorConfig(**_section(raw, "cursor")),
        actions=_actions_from_section(_section(raw, "actions")),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _migrated_v6_gestures(raw: dict[str, Any]) -> dict[str, Any]:
    gesture_section = dict(raw)
    defaults = GestureConfig()
    for field_name, old_value in _V5_SCROLL_DEFAULTS.items():
        if gesture_section.get(field_name) == old_value:
            gesture_section[field_name] = getattr(defaults, field_name)
    return gesture_section


def _migrated_v9_gestures(raw: dict[str, Any]) -> dict[str, Any]:
    gesture_section = dict(raw)
    defaults = GestureConfig()
    for field_name, old_value in _V8_GESTURE_DEFAULTS.items():
        if gesture_section.get(field_name) == old_value:
            gesture_section[field_name] = getattr(defaults, field_name)
    return gesture_section


def _migrated_v5_cursor(raw: dict[str, Any]) -> dict[str, Any]:
    cursor_section = dict(raw)
    defaults = CursorConfig()
    for field_name, old_value in _V4_CURSOR_DEFAULTS.items():
        if cursor_section.get(field_name) == old_value:
            cursor_section[field_name] = getattr(defaults, field_name)
    return cursor_section


def _migrated_v7_actions(raw: dict[str, Any]) -> dict[str, Any]:
    action_section = dict(raw)
    gesture_actions = action_section.get("gesture_actions")
    if isinstance(gesture_actions, dict):
        migrated_gesture_actions = dict(gesture_actions)
        if migrated_gesture_actions.get("shortcut_index_hold") == "window.switch":
            migrated_gesture_actions.pop("shortcut_index_hold")
        action_section["gesture_actions"] = migrated_gesture_actions
    return action_section


def _actions_from_section(raw: dict[str, Any]) -> ActionConfig:
    defaults = ActionConfig()
    catalog_raw = raw.get("catalog", {})
    if not isinstance(catalog_raw, dict):
        raise ValueError("AirPilot config action catalog must be an object")
    catalog: dict[str, ShortcutConfig] = dict(defaults.catalog)
    for action_id, value in catalog_raw.items():
        if isinstance(value, ShortcutConfig):
            catalog[str(action_id)] = value
            continue
        if not isinstance(value, dict):
            raise ValueError(f"AirPilot action {action_id!r} must be an object")
        catalog[str(action_id)] = ShortcutConfig(
            label=str(value["label"]),
            keys=tuple(str(key) for key in value["keys"]),
            profile=str(value.get("profile", "global")),
            enabled=bool(value.get("enabled", True)),
            risky=bool(value.get("risky", False)),
        )
    gesture_actions_raw = raw.get("gesture_actions", {})
    if not isinstance(gesture_actions_raw, dict):
        raise ValueError("AirPilot gesture_actions must be an object")
    gesture_actions = dict(defaults.gesture_actions)
    gesture_actions.update(
        {str(gesture): str(action_id) for gesture, action_id in gesture_actions_raw.items()}
    )
    return ActionConfig(
        enabled=bool(raw.get("enabled", defaults.enabled)),
        risky_actions_enabled=bool(
            raw.get("risky_actions_enabled", defaults.risky_actions_enabled)
        ),
        shortcut_mode_gesture=str(raw.get("shortcut_mode_gesture", defaults.shortcut_mode_gesture)),
        gesture_actions=gesture_actions,
        catalog=catalog,
    )
