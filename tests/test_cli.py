from pathlib import Path

from airpilot import app
from airpilot.config import AppConfig


def test_armed_flag_sets_start_armed(monkeypatch: object) -> None:
    seen: dict[str, bool] = {}

    def fake_run(config: AppConfig) -> int:
        seen["enable_real_mouse"] = config.runtime.enable_real_mouse
        seen["start_armed"] = config.runtime.start_armed
        return 0

    monkeypatch.setattr(app, "load_config", lambda _path=None: AppConfig())
    monkeypatch.setattr(app, "read_config_schema_version", lambda _path: None)
    monkeypatch.setattr(app, "save_config", lambda _config, _path=None: None)
    monkeypatch.setattr(app, "default_config_path", lambda: Path("."))
    monkeypatch.setattr(app, "run", fake_run)

    assert app.main(["--armed"]) == 0
    assert seen == {"enable_real_mouse": True, "start_armed": True}


def test_no_mouse_overrides_armed_gate(monkeypatch: object) -> None:
    seen: dict[str, bool] = {}

    def fake_run(config: AppConfig) -> int:
        seen["enable_real_mouse"] = config.runtime.enable_real_mouse
        seen["start_armed"] = config.runtime.start_armed
        return 0

    monkeypatch.setattr(app, "load_config", lambda _path=None: AppConfig())
    monkeypatch.setattr(app, "read_config_schema_version", lambda _path: None)
    monkeypatch.setattr(app, "save_config", lambda _config, _path=None: None)
    monkeypatch.setattr(app, "default_config_path", lambda: Path("."))
    monkeypatch.setattr(app, "run", fake_run)

    assert app.main(["--no-mouse", "--armed"]) == 0
    assert seen == {"enable_real_mouse": False, "start_armed": True}


def test_diagnostics_disables_real_mouse(monkeypatch: object) -> None:
    seen: dict[str, bool | float | None] = {}

    def fake_run(
        config: AppConfig,
        diagnose_seconds: float | None = None,
        *,
        show_preview: bool = True,
    ) -> int:
        seen["enable_real_mouse"] = config.runtime.enable_real_mouse
        seen["diagnose_seconds"] = diagnose_seconds
        seen["show_preview"] = show_preview
        return 0

    monkeypatch.setattr(app, "load_config", lambda _path=None: AppConfig())
    monkeypatch.setattr(app, "read_config_schema_version", lambda _path: None)
    monkeypatch.setattr(app, "save_config", lambda _config, _path=None: None)
    monkeypatch.setattr(app, "default_config_path", lambda: Path("."))
    monkeypatch.setattr(app, "run", fake_run)

    assert app.main(["--diagnose-seconds", "1"]) == 0
    assert seen == {
        "enable_real_mouse": False,
        "diagnose_seconds": 1.0,
        "show_preview": False,
    }


def test_main_persists_migrated_config(monkeypatch: object) -> None:
    saved: dict[str, AppConfig | None] = {"config": None}

    def fake_run(config: AppConfig) -> int:
        return 0

    def fake_save_config(config: AppConfig, _path: Path | None = None) -> None:
        saved["config"] = config

    monkeypatch.setattr(app, "load_config", lambda _path=None: AppConfig())
    monkeypatch.setattr(app, "read_config_schema_version", lambda _path: 1)
    monkeypatch.setattr(app, "save_config", fake_save_config)
    monkeypatch.setattr(app, "default_config_path", lambda: Path("."))
    monkeypatch.setattr(app, "run", fake_run)

    assert app.main([]) == 0
    assert saved["config"] is not None
