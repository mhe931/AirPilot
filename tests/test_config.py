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

    assert loaded.schema_version == 1
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
