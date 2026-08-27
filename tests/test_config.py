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

    assert loaded.schema_version == 4
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

    assert loaded.schema_version == 4
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

    assert loaded.schema_version == 4
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

    assert loaded.schema_version == 4
    assert loaded.runtime.flip_camera_x is False
    assert loaded.cursor.mirror_x is True


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

    assert loaded.schema_version == 4
    assert loaded.runtime.flip_camera_x is False
    assert loaded.cursor.mirror_x is True


def test_default_config_file_matches_dataclass_defaults() -> None:
    defaults_path = Path(__file__).resolve().parents[1] / "config" / "defaults.json"
    raw = json.loads(defaults_path.read_text(encoding="utf-8"))

    assert raw == json.loads(json.dumps(asdict(AppConfig())))
