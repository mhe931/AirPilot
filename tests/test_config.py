import json
from dataclasses import asdict
from pathlib import Path

import pytest

from airpilot.config import AppConfig, load_config, save_config


def test_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = AppConfig()
    config.cursor.sensitivity = 1.4
    config.runtime.camera_index = 2

    save_config(config, path)
    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.cursor.sensitivity == 1.4
    assert loaded.runtime.camera_index == 2


def test_missing_config_uses_defaults(tmp_path: Path) -> None:
    loaded = load_config(tmp_path / "missing.json")

    assert loaded.runtime.camera_index == 0
    assert loaded.gestures.click_cooldown_ms > 0


def test_rejects_unknown_config_schema(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version": 999}', encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported"):
        load_config(path)


def test_v1_config_migrates_legacy_mirrored_cursor_default(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cursor": {"mirror_x": True, "sensitivity": 1.2},
                "runtime": {"camera_index": 1},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.cursor.mirror_x is True
    assert loaded.cursor.sensitivity == 1.2
    assert loaded.runtime.camera_index == 1


def test_v1_config_preserves_equivalent_horizontal_behavior_when_unmirrored(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cursor": {"mirror_x": False},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.runtime.flip_camera_x is False
    assert loaded.cursor.mirror_x is True


def test_v2_config_migrates_to_actual_camera_orientation(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "cursor": {"mirror_x": False},
                "runtime": {"flip_camera_x": True},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.runtime.flip_camera_x is False
    assert loaded.cursor.mirror_x is True


def test_v4_config_hides_help_overlay_after_migration(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "gestures": {
                    "scroll_pinch_threshold": 0.065,
                    "scroll_pinch_release_threshold": 0.085,
                    "scroll_activation_y_delta": 0.018,
                    "scroll_units_per_step": 3,
                },
                "runtime": {"show_gesture_help": True},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.runtime.show_gesture_help is False
    assert loaded.gestures.pause_gesture_enabled is False
    assert loaded.gestures.help_gesture_enabled is True
    assert loaded.gestures.scroll_pinch_threshold == 0.085
    assert loaded.gestures.scroll_pinch_release_threshold == 0.130
    assert loaded.gestures.scroll_activation_y_delta == 0.012
    assert loaded.gestures.scroll_units_per_step == 2
    assert loaded.actions.gesture_actions["help_secondary_index_hold"] == "ui.toggle_help"
    assert loaded.actions.gesture_actions["arm_secondary_middle_hold"] == "ui.arm"
    assert loaded.actions.gesture_actions["shortcut_middle_hold"] == "clipboard.history"
    assert "shortcut_index_hold" not in loaded.actions.gesture_actions
    assert "ui.toggle_help" in loaded.actions.catalog
    assert "ui.arm" in loaded.actions.catalog
    assert loaded.actions.catalog["clipboard.history"].keys == ("win", "v")
    assert loaded.actions.catalog["system.task_view"].keys == ("win", "tab")


def test_v4_config_updates_untouched_cursor_defaults_for_responsiveness(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "cursor": {
                    "screen_left": 0,
                    "screen_top": 0,
                    "screen_width": 1920,
                    "screen_height": 1080,
                    "camera_min_x": 0.08,
                    "camera_max_x": 0.92,
                    "camera_min_y": 0.08,
                    "camera_max_y": 0.88,
                    "sensitivity": 1.0,
                    "smoothing_alpha": 0.28,
                    "dead_zone_px": 5,
                    "mirror_x": True,
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.cursor.camera_min_x == 0.16
    assert loaded.cursor.camera_max_x == 0.84
    assert loaded.cursor.camera_min_y == 0.12
    assert loaded.cursor.camera_max_y == 0.82
    assert loaded.cursor.sensitivity == 1.35
    assert loaded.cursor.smoothing_alpha == 0.42
    assert loaded.cursor.dead_zone_px == 3


def test_v4_config_preserves_custom_cursor_tuning(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "cursor": {
                    "camera_min_x": 0.10,
                    "camera_max_x": 0.90,
                    "camera_min_y": 0.11,
                    "camera_max_y": 0.91,
                    "sensitivity": 1.2,
                    "smoothing_alpha": 0.5,
                    "dead_zone_px": 7,
                    "mirror_x": True,
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.cursor.camera_min_x == 0.10
    assert loaded.cursor.camera_max_x == 0.90
    assert loaded.cursor.camera_min_y == 0.11
    assert loaded.cursor.camera_max_y == 0.91
    assert loaded.cursor.sensitivity == 1.2
    assert loaded.cursor.smoothing_alpha == 0.5
    assert loaded.cursor.dead_zone_px == 7


def test_v3_config_migrates_to_actual_orientation_and_operator_direction(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "cursor": {"mirror_x": False},
                "runtime": {"flip_camera_x": True},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.runtime.flip_camera_x is False
    assert loaded.cursor.mirror_x is True


def test_v5_config_adds_scroll_tuning_and_clipboard_history(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "gestures": {
                    "scroll_activation_y_delta": 0.018,
                    "scroll_units_per_step": 3,
                },
                "actions": {
                    "gesture_actions": {
                        "shortcut_index_release": "clipboard.copy",
                    },
                    "catalog": {
                        "clipboard.copy": {
                            "label": "Copy",
                            "keys": ["ctrl", "c"],
                            "profile": "editing",
                            "enabled": True,
                            "risky": False,
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.gestures.scroll_sensitivity == 1.4
    assert loaded.gestures.scroll_cooldown_ms == 35
    assert loaded.gestures.scroll_pinch_threshold == 0.085
    assert loaded.gestures.scroll_pinch_release_threshold == 0.130
    assert loaded.gestures.scroll_activation_y_delta == 0.012
    assert loaded.gestures.scroll_units_per_step == 2
    assert loaded.actions.catalog["clipboard.history"].keys == ("win", "v")
    assert loaded.actions.gesture_actions["shortcut_middle_hold"] == "clipboard.history"
    assert loaded.actions.gesture_actions["arm_secondary_middle_hold"] == "ui.arm"
    assert "shortcut_index_hold" not in loaded.actions.gesture_actions


def test_v5_config_preserves_custom_scroll_tuning(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "gestures": {
                    "scroll_pinch_threshold": 0.090,
                    "scroll_pinch_release_threshold": 0.140,
                    "scroll_activation_y_delta": 0.020,
                    "scroll_units_per_step": 4,
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.gestures.scroll_pinch_threshold == 0.090
    assert loaded.gestures.scroll_pinch_release_threshold == 0.140
    assert loaded.gestures.scroll_activation_y_delta == 0.020
    assert loaded.gestures.scroll_units_per_step == 4


def test_v7_config_adds_pose_clutch_thresholds(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 7,
                "gestures": {
                    "click_cooldown_ms": 250,
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 8
    assert loaded.gestures.click_cooldown_ms == 250
    assert loaded.gestures.thumb_close_threshold == 0.72
    assert loaded.gestures.thumb_open_threshold == 0.95
    assert loaded.gestures.finger_bend_threshold == 1.35
    assert loaded.gestures.finger_extend_threshold == 1.70


def test_default_config_file_matches_dataclass_defaults() -> None:
    defaults_path = Path(__file__).resolve().parents[1] / "config" / "defaults.json"
    raw = json.loads(defaults_path.read_text(encoding="utf-8"))

    assert raw == json.loads(json.dumps(asdict(AppConfig())))
