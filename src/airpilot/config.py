from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = 4


@dataclass(slots=True)
class GestureConfig:
    min_click_hold_ms: int = 80
    pinch_threshold: float = 0.055
    pinch_release_threshold: float = 0.075
    right_pinch_threshold: float = 0.065
    right_pinch_release_threshold: float = 0.085
    scroll_pinch_threshold: float = 0.065
    scroll_pinch_release_threshold: float = 0.085
    pause_pinch_threshold: float = 0.070
    pause_pinch_release_threshold: float = 0.095
    scroll_activation_y_delta: float = 0.018
    scroll_units_per_step: int = 3
    shortcut_mode_hold_ms: int = 650
    shortcut_action_hold_ms: int = 650
    action_cooldown_ms: int = 700
    click_cooldown_ms: int = 350
    drag_hold_ms: int = 450
    pause_hold_ms: int = 850
    tracking_loss_grace_ms: int = 250


@dataclass(slots=True)
class CursorConfig:
    screen_left: int = 0
    screen_top: int = 0
    screen_width: int = 1920
    screen_height: int = 1080
    camera_min_x: float = 0.08
    camera_max_x: float = 0.92
    camera_min_y: float = 0.08
    camera_max_y: float = 0.88
    sensitivity: float = 1.0
    smoothing_alpha: float = 0.28
    dead_zone_px: int = 5
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
        "clipboard.copy": ShortcutConfig("Copy", ("ctrl", "c"), "editing"),
        "clipboard.paste": ShortcutConfig("Paste", ("ctrl", "v"), "editing"),
        "clipboard.cut": ShortcutConfig("Cut", ("ctrl", "x"), "editing", enabled=False),
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
        "shortcut_index_release": "clipboard.copy",
        "shortcut_index_hold": "window.switch",
        "shortcut_middle_release": "clipboard.paste",
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
    show_gesture_help: bool = True
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
        gestures=_gestures_from_section(_section(raw, "gestures")),
        cursor=CursorConfig(**cursor_section),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _migrate_v2_config(raw: dict[str, Any]) -> AppConfig:
    runtime_section = dict(_section(raw, "runtime"))
    runtime_section["flip_camera_x"] = False
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_section(raw, "gestures")),
        cursor=_migrated_cursor(_section(raw, "cursor")),
        runtime=RuntimeConfig(**runtime_section),
    )


def _migrate_v3_config(raw: dict[str, Any]) -> AppConfig:
    runtime_section = dict(_section(raw, "runtime"))
    runtime_section["flip_camera_x"] = False
    return AppConfig(
        schema_version=CURRENT_SCHEMA_VERSION,
        gestures=_gestures_from_section(_section(raw, "gestures")),
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
        "scroll_units_per_step": defaults.scroll_units_per_step,
        "shortcut_mode_hold_ms": defaults.shortcut_mode_hold_ms,
        "shortcut_action_hold_ms": defaults.shortcut_action_hold_ms,
        "action_cooldown_ms": defaults.action_cooldown_ms,
        "click_cooldown_ms": defaults.click_cooldown_ms,
        "drag_hold_ms": defaults.drag_hold_ms,
        "pause_hold_ms": defaults.pause_hold_ms,
        "tracking_loss_grace_ms": defaults.tracking_loss_grace_ms,
    }
    section.update(raw)
    return GestureConfig(**section)


def _actions_from_section(raw: dict[str, Any]) -> ActionConfig:
    defaults = ActionConfig()
    catalog_raw = raw.get("catalog", defaults.catalog)
    if not isinstance(catalog_raw, dict):
        raise ValueError("AirPilot config action catalog must be an object")
    catalog: dict[str, ShortcutConfig] = {}
    for action_id, value in catalog_raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"AirPilot action {action_id!r} must be an object")
        catalog[str(action_id)] = ShortcutConfig(
            label=str(value["label"]),
            keys=tuple(str(key) for key in value["keys"]),
            profile=str(value.get("profile", "global")),
            enabled=bool(value.get("enabled", True)),
            risky=bool(value.get("risky", False)),
        )
    gesture_actions_raw = raw.get("gesture_actions", defaults.gesture_actions)
    if not isinstance(gesture_actions_raw, dict):
        raise ValueError("AirPilot gesture_actions must be an object")
    return ActionConfig(
        enabled=bool(raw.get("enabled", defaults.enabled)),
        risky_actions_enabled=bool(
            raw.get("risky_actions_enabled", defaults.risky_actions_enabled)
        ),
        shortcut_mode_gesture=str(raw.get("shortcut_mode_gesture", defaults.shortcut_mode_gesture)),
        gesture_actions={
            str(gesture): str(action_id) for gesture, action_id in gesture_actions_raw.items()
        },
        catalog=catalog,
    )
