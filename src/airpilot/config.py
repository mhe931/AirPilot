from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


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
    click_cooldown_ms: int = 350
    drag_hold_ms: int = 450
    pause_hold_ms: int = 850
    tracking_loss_grace_ms: int = 250


@dataclass(slots=True)
class CursorConfig:
    screen_width: int = 1920
    screen_height: int = 1080
    camera_min_x: float = 0.12
    camera_max_x: float = 0.88
    camera_min_y: float = 0.10
    camera_max_y: float = 0.86
    sensitivity: float = 1.0
    smoothing_alpha: float = 0.35
    dead_zone_px: int = 4
    mirror_x: bool = True


@dataclass(slots=True)
class RuntimeConfig:
    camera_index: int = 0
    max_camera_index: int = 4
    draw_landmarks: bool = True
    enable_real_mouse: bool = True
    emergency_corner_failsafe: bool = True
    tracker_detection_confidence: float = 0.55
    tracker_tracking_confidence: float = 0.55


@dataclass(slots=True)
class AppConfig:
    schema_version: int = 1
    gestures: GestureConfig = field(default_factory=GestureConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)
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
    if version != 1:
        raise ValueError(f"Unsupported AirPilot config schema_version {version!r}")
    return AppConfig(
        schema_version=version,
        gestures=GestureConfig(**_section(raw, "gestures")),
        cursor=CursorConfig(**_section(raw, "cursor")),
        runtime=RuntimeConfig(**_section(raw, "runtime")),
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    section = raw.get(name, {})
    if not isinstance(section, dict):
        raise ValueError(f"AirPilot config section {name!r} must be an object")
    return section
