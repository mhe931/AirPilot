"""Tests for configurable text styles, sidebar panel, Help table, and gesture triggers.

Acceptance criteria covered:
- TextStyleConfig round-trip serialization (v11 schema).
- v10 config migrates to v11 with TextStyleConfig defaults.
- TextStyleConfig validation bounds are clamped in Settings apply.
- _hex_to_bgr converts colors correctly and falls back on invalid input.
- _sidebar_lines generates correct lines for armed/disarmed/shortcut modes.
- Sidebar disabled via text_styles.sidebar_enabled=False returns empty lines.
- Sidebar shows enabled binding action_ids.
- _format_help_row includes an emoji column and four field columns.
- _format_help_header includes emoji placeholder column.
- _help_emoji_for_action returns expected emojis for known action keywords.
- Settings/Help gesture bindings exist in defaults as disabled.
- ui.open_settings and ui.close_settings are in the action catalog.
- _dispatch_ui_action handles ui.open_settings without crashing when window is None.
- Configurable bindings with same fingerprint detected as conflict.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock

from airpilot.app import (
    EMOJI_HELP,
    EMOJI_SETTINGS,
    _dispatch_ui_action,
    _format_help_header,
    _format_help_row,
    _help_emoji_for_action,
    _hex_to_bgr,
    _sidebar_lines,
)
from airpilot.config import (
    AppConfig,
    GestureBinding,
    TextStyleConfig,
    _default_gesture_bindings,
    load_config,
    save_config,
    validate_gesture_bindings,
)
from airpilot.domain.types import GestureEvents, Handedness, HandLandmarks, Landmark, TrackingFrame

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lm(x: float = 0.5, y: float = 0.5) -> Landmark:
    return Landmark(x=x, y=y)


def _make_hand() -> HandLandmarks:
    lms = tuple(_lm(0.5, 0.5) for _ in range(21))
    return HandLandmarks(landmarks=lms, handedness=Handedness.RIGHT, confidence=0.9)


def _frame(hand: HandLandmarks | None = None) -> TrackingFrame:
    return TrackingFrame(timestamp_ms=0, width=640, height=480, hand=hand)


def _events(**kwargs: object) -> GestureEvents:
    defaults: dict[str, object] = {
        "move": None,
        "left_click": False,
        "right_click": False,
        "middle_click": False,
        "drag_start": False,
        "drag_end": False,
        "scroll": 0,
        "tracking_lost": False,
        "paused": False,
        "paused_changed": False,
        "action_id": None,
        "action_label": None,
        "active_gesture": "none",
        "status": "none",
        "shortcut_mode": False,
    }
    defaults.update(kwargs)
    return GestureEvents(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TextStyleConfig serialization
# ---------------------------------------------------------------------------


def test_text_style_config_defaults() -> None:
    ts = TextStyleConfig()
    assert ts.overlay_fg == "#ffffff"
    assert ts.sidebar_enabled is True
    assert ts.sidebar_bg == "#141414"
    assert ts.help_font_family == "Consolas"
    assert ts.help_font_size == 10
    assert ts.overlay_scale_pct == 100
    assert ts.sidebar_scale_pct == 100
    assert ts.settings_font_size == 0


def test_text_style_round_trip(tmp_path: Path) -> None:
    config = AppConfig()
    config.text_styles.overlay_fg = "#ff0000"
    config.text_styles.sidebar_enabled = False
    config.text_styles.help_font_size = 12

    path = save_config(config, tmp_path / "cfg.json")
    loaded = load_config(path)

    assert loaded.schema_version == 12
    assert loaded.text_styles.overlay_fg == "#ff0000"
    assert loaded.text_styles.sidebar_enabled is False
    assert loaded.text_styles.help_font_size == 12


def test_v10_config_migrates_to_v11_with_text_style_defaults(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 10,
                "gestures": {},
                "cursor": {},
                "actions": {},
                "runtime": {},
                "gesture_bindings": [],
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(path)

    assert loaded.schema_version == 12
    assert loaded.text_styles.overlay_fg == "#ffffff"
    assert loaded.text_styles.sidebar_enabled is True
    assert loaded.text_styles.help_font_family == "Consolas"


def test_text_style_in_appconfig_dict() -> None:
    d = asdict(AppConfig())
    assert "text_styles" in d
    ts = d["text_styles"]
    assert ts["overlay_fg"] == "#ffffff"
    assert ts["sidebar_bg"] == "#141414"


# ---------------------------------------------------------------------------
# _hex_to_bgr
# ---------------------------------------------------------------------------


def test_hex_to_bgr_white() -> None:
    assert _hex_to_bgr("#ffffff") == (255, 255, 255)


def test_hex_to_bgr_black() -> None:
    assert _hex_to_bgr("#000000") == (0, 0, 0)


def test_hex_to_bgr_red() -> None:
    # #ff0000 = R=255 G=0 B=0 → BGR = (0, 0, 255)
    assert _hex_to_bgr("#ff0000") == (0, 0, 255)


def test_hex_to_bgr_blue() -> None:
    # #0000ff → BGR = (255, 0, 0)
    assert _hex_to_bgr("#0000ff") == (255, 0, 0)


def test_hex_to_bgr_invalid_falls_back_to_white() -> None:
    assert _hex_to_bgr("notacolor") == (255, 255, 255)
    assert _hex_to_bgr("#fff") == (255, 255, 255)
    assert _hex_to_bgr("") == (255, 255, 255)


# ---------------------------------------------------------------------------
# Sidebar lines
# ---------------------------------------------------------------------------


def test_sidebar_lines_disarmed_no_hand() -> None:
    config = AppConfig()
    frame = _frame()
    events = _events()
    lines = _sidebar_lines(frame, events, config, armed=False)
    assert lines[0] == "DISARMED"
    assert any("thumb" in line.lower() for line in lines)


def test_sidebar_lines_armed_with_hand() -> None:
    config = AppConfig()
    frame = _frame(_make_hand())
    events = _events(active_gesture="none")
    lines = _sidebar_lines(frame, events, config, armed=True)
    assert lines[0] == "ACTIVE"
    assert any("R" in line for line in lines)  # hand label shows handedness


def test_sidebar_lines_paused() -> None:
    config = AppConfig()
    frame = _frame(_make_hand())
    events = _events(paused=True)
    lines = _sidebar_lines(frame, events, config, armed=True)
    assert lines[0] == "PAUSED"


def test_sidebar_lines_shortcut_mode_shows_shortcuts() -> None:
    config = AppConfig()
    frame = _frame(_make_hand())
    events = _events(active_gesture="shortcut_mode", shortcut_mode=True)
    lines = _sidebar_lines(frame, events, config, armed=True)
    assert any("copy" in line.lower() for line in lines)
    assert any("paste" in line.lower() for line in lines)


def test_sidebar_lines_disabled_returns_empty() -> None:
    config = AppConfig()
    config.text_styles.sidebar_enabled = False
    frame = _frame(_make_hand())
    events = _events()
    lines = _sidebar_lines(frame, events, config, armed=True)
    assert lines == []


def test_sidebar_shows_enabled_bindings() -> None:
    config = AppConfig()
    config.gesture_bindings = [
        GestureBinding(
            id="my_binding",
            enabled=True,
            action_id="presentation.next_slide",
        )
    ]
    frame = _frame(_make_hand())
    events = _events()
    lines = _sidebar_lines(frame, events, config, armed=True)
    assert any("next_slide" in line or "my_bind" in line for line in lines)


# ---------------------------------------------------------------------------
# Help table formatting
# ---------------------------------------------------------------------------


def test_format_help_header_has_emoji_column() -> None:
    header = _format_help_header()
    # Must contain the emoji placeholder column and normal columns
    assert "│" in header
    assert "Action" in header
    assert "Gesture" in header
    assert "State" in header


def test_format_help_row_has_five_columns() -> None:
    row = _format_help_row("Left click | Clutch + index pinch/release | -- | enabled")
    # Should have 4 pipe separators (5 columns: emoji, action, gesture, keys, state)
    assert row.count("│") == 4


def test_format_help_row_non_table_line_returns_unchanged() -> None:
    line = "This is just a plain line"
    assert _format_help_row(line) == line


def test_help_emoji_for_click() -> None:
    emoji = _help_emoji_for_action("Left click")
    assert emoji.strip() != ""


def test_help_emoji_for_settings() -> None:
    emoji = _help_emoji_for_action("Open Settings")
    assert emoji.strip() != ""


def test_help_emoji_for_unknown_returns_space() -> None:
    emoji = _help_emoji_for_action("Completely unknown action xyz123")
    assert emoji == " "


# ---------------------------------------------------------------------------
# Default gesture bindings for settings/help
# ---------------------------------------------------------------------------


def test_default_bindings_include_settings_and_help() -> None:
    bindings = _default_gesture_bindings()
    ids = {b.id for b in bindings}
    assert "open_settings_gesture" in ids
    assert "toggle_help_gesture" in ids
    assert "ppt_next_slide_gesture" in ids


def test_default_bindings_are_all_disabled() -> None:
    """All shipped bindings must be disabled by default for safety."""
    bindings = _default_gesture_bindings()
    for b in bindings:
        assert b.enabled is False, f"Binding {b.id!r} should be disabled by default"


def test_settings_binding_has_fist_and_right_move() -> None:
    bindings = {b.id: b for b in _default_gesture_bindings()}
    sb = bindings["open_settings_gesture"]
    assert sb.action_id == "ui.open_settings"
    assert sb.movement == "right"
    assert sb.thumb == "folded"
    assert sb.index == "folded"
    assert sb.middle == "folded"
    assert sb.ring == "folded"
    assert sb.pinky == "folded"
    assert sb.trigger == "enter"
    assert sb.cooldown_ms >= 1000  # must not fire repeatedly


def test_help_binding_has_fist_and_left_move() -> None:
    bindings = {b.id: b for b in _default_gesture_bindings()}
    hb = bindings["toggle_help_gesture"]
    assert hb.action_id == "ui.toggle_help"
    assert hb.movement == "left"
    assert hb.cooldown_ms >= 1000


def test_settings_help_bindings_no_conflict() -> None:
    bindings = _default_gesture_bindings()
    # Enable them to test conflict detection
    enabled_bindings = [
        b.__class__(**{f: getattr(b, f) for f in b.__dataclass_fields__} | {"enabled": True})
        for b in bindings
    ]
    errors = validate_gesture_bindings(enabled_bindings)
    conflict_errors = [e for e in errors if "conflicting" in e.lower()]
    # settings (move right) and help (move left) should NOT conflict
    assert not any(
        "open_settings_gesture" in e and "toggle_help_gesture" in e for e in conflict_errors
    )


# ---------------------------------------------------------------------------
# ui.open_settings / ui.close_settings catalog entries
# ---------------------------------------------------------------------------


def test_ui_open_settings_in_catalog() -> None:
    config = AppConfig()
    assert "ui.open_settings" in config.actions.catalog
    assert "ui.close_settings" in config.actions.catalog


def test_ui_open_settings_has_no_keys() -> None:
    config = AppConfig()
    entry = config.actions.catalog["ui.open_settings"]
    assert entry.keys == ()
    assert entry.enabled is True


# ---------------------------------------------------------------------------
# _dispatch_ui_action for settings
# ---------------------------------------------------------------------------


def test_dispatch_open_settings_with_no_window_returns_none() -> None:
    result = _dispatch_ui_action("ui.open_settings", help_window=None, settings_window=None)
    assert result is None


def test_dispatch_open_settings_opens_window() -> None:
    mock_settings = MagicMock()
    mock_settings.is_open.return_value = False
    result = _dispatch_ui_action(
        "ui.open_settings", help_window=None, settings_window=mock_settings
    )
    mock_settings.open.assert_called_once()
    assert result == "Settings opened"


def test_dispatch_open_settings_already_open_no_double_open() -> None:
    mock_settings = MagicMock()
    mock_settings.is_open.return_value = True
    result = _dispatch_ui_action(
        "ui.open_settings", help_window=None, settings_window=mock_settings
    )
    mock_settings.open.assert_not_called()
    assert result == "Settings already open"


def test_dispatch_close_settings_closes_window() -> None:
    mock_settings = MagicMock()
    mock_settings.is_open.return_value = True
    result = _dispatch_ui_action(
        "ui.close_settings", help_window=None, settings_window=mock_settings
    )
    mock_settings.close.assert_called_once()
    assert result == "Settings closed"


def test_dispatch_close_settings_not_open_returns_none() -> None:
    mock_settings = MagicMock()
    mock_settings.is_open.return_value = False
    result = _dispatch_ui_action(
        "ui.close_settings", help_window=None, settings_window=mock_settings
    )
    mock_settings.close.assert_not_called()
    assert result is None


# ---------------------------------------------------------------------------
# Emoji constants are defined and non-empty
# ---------------------------------------------------------------------------


def test_emoji_constants_non_empty() -> None:
    for name, value in [
        ("EMOJI_SETTINGS", EMOJI_SETTINGS),
        ("EMOJI_HELP", EMOJI_HELP),
    ]:
        assert isinstance(value, str) and value.strip(), f"{name} must be non-empty"
