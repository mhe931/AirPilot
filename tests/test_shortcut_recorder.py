"""Tests for the shortcut recorder module and related integration."""

from __future__ import annotations

import json
from pathlib import Path

from airpilot.config import AppConfig, GestureBinding, load_config, save_config
from airpilot.input import RecordingMouseController
from airpilot.safety import MouseSafetyGate
from airpilot.shortcut_recorder import (
    MODIFIER_KEYS,
    SUPPORTED_KEYS,
    ShortcutConflict,
    detect_shortcut_conflicts,
    keysym_to_canonical,
    normalize_shortcut,
    shortcut_label,
    sync_custom_shortcuts,
    validate_shortcut,
)

# ---------------------------------------------------------------------------
# keysym_to_canonical
# ---------------------------------------------------------------------------


def test_keysym_to_canonical_letters() -> None:
    assert keysym_to_canonical("a") == "a"
    assert keysym_to_canonical("Z") == "z"
    assert keysym_to_canonical("P") == "p"


def test_keysym_to_canonical_digits() -> None:
    assert keysym_to_canonical("9") == "9"
    assert keysym_to_canonical("0") == "0"


def test_keysym_to_canonical_special_keys() -> None:
    assert keysym_to_canonical("Control_L") == "ctrl"
    assert keysym_to_canonical("Control_R") == "ctrl"
    assert keysym_to_canonical("Shift_L") == "shift"
    assert keysym_to_canonical("Alt_L") == "alt"
    assert keysym_to_canonical("Return") == "enter"
    assert keysym_to_canonical("Escape") == "esc"
    assert keysym_to_canonical("F5") == "f5"
    assert keysym_to_canonical("F12") == "f12"
    assert keysym_to_canonical("Left") == "left"
    assert keysym_to_canonical("Up") == "up"
    assert keysym_to_canonical("Prior") == "pageup"
    assert keysym_to_canonical("Next") == "pagedown"
    assert keysym_to_canonical("Tab") == "tab"


def test_keysym_to_canonical_unknown_returns_none() -> None:
    assert keysym_to_canonical("XF86AudioPlay") is None
    assert keysym_to_canonical("yen") is None


def test_keysym_to_canonical_meta_as_win() -> None:
    assert keysym_to_canonical("Super_L") == "win"
    assert keysym_to_canonical("Meta_L") == "win"


# ---------------------------------------------------------------------------
# normalize_shortcut
# ---------------------------------------------------------------------------


def test_normalize_shortcut_modifiers_first() -> None:
    result = normalize_shortcut(("p", "ctrl", "shift"))
    assert result == ("ctrl", "shift", "p")


def test_normalize_shortcut_modifier_order() -> None:
    # ctrl < shift < alt < win
    result = normalize_shortcut(("win", "alt", "shift", "ctrl", "x"))
    assert result == ("ctrl", "shift", "alt", "win", "x")


def test_normalize_shortcut_single_key() -> None:
    assert normalize_shortcut(("a",)) == ("a",)


def test_normalize_shortcut_already_normalized() -> None:
    assert normalize_shortcut(("ctrl", "9")) == ("ctrl", "9")


def test_normalize_shortcut_ctrl_shift_p() -> None:
    assert normalize_shortcut(("shift", "ctrl", "p")) == ("ctrl", "shift", "p")


# ---------------------------------------------------------------------------
# shortcut_label
# ---------------------------------------------------------------------------


def test_shortcut_label_simple() -> None:
    assert shortcut_label(("ctrl", "c")) == "Ctrl+C"


def test_shortcut_label_function_key() -> None:
    assert shortcut_label(("f5",)) == "F5"


def test_shortcut_label_combo() -> None:
    assert shortcut_label(("ctrl", "shift", "p")) == "Ctrl+Shift+P"


def test_shortcut_label_digit() -> None:
    assert shortcut_label(("ctrl", "9")) == "Ctrl+9"


def test_shortcut_label_alt_w() -> None:
    assert shortcut_label(("alt", "w")) == "Alt+W"


def test_shortcut_label_special_names() -> None:
    assert "Ctrl" in shortcut_label(("ctrl", "a"))
    assert "Shift" in shortcut_label(("shift", "tab"))
    assert "Win" in shortcut_label(("win", "v"))


def test_shortcut_label_empty() -> None:
    assert shortcut_label(()) == ""


# ---------------------------------------------------------------------------
# validate_shortcut
# ---------------------------------------------------------------------------


def test_validate_shortcut_valid_combos() -> None:
    assert validate_shortcut(("ctrl", "c")) is None
    assert validate_shortcut(("ctrl", "shift", "p")) is None
    assert validate_shortcut(("alt", "w")) is None
    assert validate_shortcut(("ctrl", "9")) is None
    assert validate_shortcut(("f5",)) is None


def test_validate_shortcut_empty_is_error() -> None:
    assert validate_shortcut(()) is not None
    assert "No keys" in (validate_shortcut(()) or "")


def test_validate_shortcut_modifier_only_is_error() -> None:
    err = validate_shortcut(("ctrl",))
    assert err is not None
    assert "Modifier" in err

    err = validate_shortcut(("ctrl", "shift"))
    assert err is not None


def test_validate_shortcut_unsupported_key() -> None:
    err = validate_shortcut(("ctrl", "yen"))
    assert err is not None
    assert "yen" in err


def test_validate_shortcut_reserved() -> None:
    err = validate_shortcut(("ctrl", "alt", "delete"))
    assert err is not None
    assert "Reserved" in err or "eserved" in err


def test_validate_shortcut_risky_blocked_by_default() -> None:
    err = validate_shortcut(("alt", "f4"))
    assert err is not None
    assert "Risky" in err or "risky" in err


def test_validate_shortcut_risky_allowed_with_flag() -> None:
    assert validate_shortcut(("alt", "f4"), risky_ok=True) is None
    assert validate_shortcut(("win", "l"), risky_ok=True) is None


def test_validate_shortcut_supported_keys_includes_letters_and_digits() -> None:
    for char in "abcdefghijklmnopqrstuvwxyz0123456789":
        assert char in SUPPORTED_KEYS

    for mod in ("ctrl", "shift", "alt", "win"):
        assert mod in MODIFIER_KEYS


# ---------------------------------------------------------------------------
# detect_shortcut_conflicts
# ---------------------------------------------------------------------------


def _binding(
    binding_id: str,
    shortcut: tuple[str, ...] = (),
    *,
    hand: str = "either",
    movement: str = "none",
) -> GestureBinding:
    return GestureBinding(
        id=binding_id,
        enabled=True,
        hand=hand,
        shortcut_keys=shortcut,
        movement=movement,
    )


def test_detect_conflicts_no_conflicts() -> None:
    bindings = [
        _binding("a", ("ctrl", "c")),
        _binding("b", ("ctrl", "v")),
    ]
    assert detect_shortcut_conflicts(("ctrl", "c"), bindings, skip_index=0) == []


def test_detect_conflicts_finds_exact_match() -> None:
    bindings = [
        _binding("a", ("ctrl", "c")),
        _binding("b", ("ctrl", "c")),
    ]
    result = detect_shortcut_conflicts(("ctrl", "c"), bindings, skip_index=0)
    assert len(result) == 1
    assert result[0].conflicting_binding_id == "b"


def test_detect_conflicts_skips_self() -> None:
    bindings = [
        _binding("a", ("ctrl", "c")),
    ]
    result = detect_shortcut_conflicts(("ctrl", "c"), bindings, skip_index=0)
    assert result == []


def test_detect_conflicts_normalizes_key_order() -> None:
    """Conflict is detected even when key order differs."""
    bindings = [
        _binding("a", ("shift", "ctrl", "p")),
        _binding("b", ("ctrl", "shift", "p")),
    ]
    result = detect_shortcut_conflicts(("ctrl", "shift", "p"), bindings, skip_index=0)
    assert len(result) == 1
    assert result[0].conflicting_binding_id == "b"


def test_detect_conflicts_non_overlapping_hands_allowed() -> None:
    """Bindings on different non-overlapping hands should not conflict."""
    bindings = [
        _binding("a", ("ctrl", "c"), hand="left"),
        _binding("b", ("ctrl", "c"), hand="right"),
    ]
    # skip_index=0 → current is 'a' (left hand), other is 'b' (right hand)
    result = detect_shortcut_conflicts(("ctrl", "c"), bindings, skip_index=0)
    # Left and right hands don't overlap → no conflict
    assert result == []


def test_detect_conflicts_overlapping_hands_conflict() -> None:
    bindings = [
        _binding("a", ("ctrl", "c"), hand="either"),
        _binding("b", ("ctrl", "c"), hand="either"),
    ]
    result = detect_shortcut_conflicts(("ctrl", "c"), bindings, skip_index=0)
    assert len(result) == 1


def test_detect_conflicts_empty_keys_returns_empty() -> None:
    bindings = [_binding("a", ("ctrl", "c"))]
    assert detect_shortcut_conflicts((), bindings, skip_index=None) == []


def test_detect_conflicts_binding_without_shortcut_ignored() -> None:
    bindings = [
        _binding("a"),  # no shortcut_keys
        _binding("b", ("ctrl", "c")),
    ]
    result = detect_shortcut_conflicts(("ctrl", "c"), bindings, skip_index=1)
    # 'a' has no shortcut, only 'b' has it, but 'b' is skipped
    assert result == []


def test_detect_conflicts_returns_conflict_object_fields() -> None:
    bindings = [
        _binding("a", ("ctrl", "v"), hand="control"),
        _binding("b", ("ctrl", "v"), hand="control"),
    ]
    result = detect_shortcut_conflicts(("ctrl", "v"), bindings, skip_index=0)
    assert len(result) == 1
    c = result[0]
    assert isinstance(c, ShortcutConflict)
    assert c.conflicting_binding_id == "b"
    assert "Ctrl" in c.conflicting_shortcut_label
    assert c.conflicting_context != ""


# ---------------------------------------------------------------------------
# sync_custom_shortcuts
# ---------------------------------------------------------------------------


def test_sync_custom_shortcuts_creates_catalog_entry() -> None:
    config = AppConfig()
    config.gesture_bindings[0].shortcut_keys = ("ctrl", "9")
    config.gesture_bindings[0].action_id = ""

    sync_custom_shortcuts(config)

    action_id = f"custom.{config.gesture_bindings[0].id}"
    assert action_id in config.actions.catalog
    entry = config.actions.catalog[action_id]
    assert entry.keys == ("ctrl", "9")
    assert entry.profile == "custom"


def test_sync_custom_shortcuts_sets_action_id() -> None:
    config = AppConfig()
    b = config.gesture_bindings[0]
    b.shortcut_keys = ("alt", "w")
    b.action_id = ""

    sync_custom_shortcuts(config)

    assert b.action_id == f"custom.{b.id}"


def test_sync_custom_shortcuts_prunes_stale_entries() -> None:
    config = AppConfig()
    # Manually add a stale custom entry
    from airpilot.config import ShortcutConfig

    config.actions.catalog["custom.gone_binding"] = ShortcutConfig(
        label="Gone", keys=("ctrl", "z"), profile="custom"
    )
    # No binding has id 'gone_binding', so sync should prune it
    sync_custom_shortcuts(config)

    assert "custom.gone_binding" not in config.actions.catalog


def test_sync_custom_shortcuts_preserves_non_custom_entries() -> None:
    config = AppConfig()
    # Standard catalog entries should survive
    assert "clipboard.copy" in config.actions.catalog
    sync_custom_shortcuts(config)
    assert "clipboard.copy" in config.actions.catalog


# ---------------------------------------------------------------------------
# Config migration: v11 → v12 preserves shortcut_keys
# ---------------------------------------------------------------------------


def test_v11_config_migrates_shortcut_keys_field(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 11,
                "gestures": {},
                "cursor": {},
                "actions": {},
                "runtime": {},
                "gesture_bindings": [
                    {
                        "id": "my_binding",
                        "enabled": True,
                        "shortcut_keys": ["ctrl", "9"],
                        "action_id": "",
                    }
                ],
                "text_styles": {},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 12
    b = next(b for b in loaded.gesture_bindings if b.id == "my_binding")
    assert b.shortcut_keys == ("ctrl", "9")


def test_v11_config_without_shortcut_keys_defaults_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 11,
                "gestures": {},
                "cursor": {},
                "actions": {},
                "runtime": {},
                "gesture_bindings": [
                    {
                        "id": "old_binding",
                        "enabled": False,
                        "action_id": "presentation.next_slide",
                    }
                ],
                "text_styles": {},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.schema_version == 12
    b = next(b for b in loaded.gesture_bindings if b.id == "old_binding")
    assert b.shortcut_keys == ()
    assert b.action_id == "presentation.next_slide"


def test_config_round_trip_preserves_shortcut_keys(tmp_path: Path) -> None:
    config = AppConfig()
    config.gesture_bindings[0].shortcut_keys = ("ctrl", "shift", "p")
    sync_custom_shortcuts(config)

    path = save_config(config, tmp_path / "cfg.json")
    loaded = load_config(path)

    b = loaded.gesture_bindings[0]
    assert b.shortcut_keys == ("ctrl", "shift", "p")


# ---------------------------------------------------------------------------
# Exact shortcut emission via RecordingMouseController
# ---------------------------------------------------------------------------


def test_recording_mouse_controller_hotkey_records_correctly() -> None:
    mouse = RecordingMouseController()
    mouse.hotkey(("ctrl", "c"))
    assert "hotkey:ctrl+c" in mouse.actions


def test_recording_mouse_controller_release_all_keys_records() -> None:
    mouse = RecordingMouseController()
    mouse.release_all_keys()
    assert "release_all_keys" in mouse.actions


# ---------------------------------------------------------------------------
# Forced key release on disarm
# ---------------------------------------------------------------------------


def test_disarm_calls_release_all_keys_no_drag() -> None:
    mouse = RecordingMouseController()
    gate = MouseSafetyGate(armed=True)

    gate.disarm(mouse)

    assert "release_all_keys" in mouse.actions


def test_disarm_calls_release_all_keys_after_drag_end() -> None:
    from airpilot.domain.types import GestureEvents

    mouse = RecordingMouseController()
    gate = MouseSafetyGate(armed=True)
    gate.apply(mouse, GestureEvents(drag_start=True))

    gate.disarm(mouse)

    # drag_end must precede release_all_keys
    assert "drag_end" in mouse.actions
    drag_idx = mouse.actions.index("drag_end")
    release_idx = mouse.actions.index("release_all_keys")
    assert drag_idx < release_idx


# ---------------------------------------------------------------------------
# sync_custom_shortcuts updates catalog label from shortcut_label
# ---------------------------------------------------------------------------


def test_sync_custom_shortcuts_label_is_human_readable() -> None:
    config = AppConfig()
    config.gesture_bindings[0].shortcut_keys = ("ctrl", "shift", "p")
    config.gesture_bindings[0].action_id = ""

    sync_custom_shortcuts(config)

    action_id = f"custom.{config.gesture_bindings[0].id}"
    label = config.actions.catalog[action_id].label
    assert label == "Ctrl+Shift+P"


# ---------------------------------------------------------------------------
# Help/dashboard refresh: catalog is updated immediately on sync
# ---------------------------------------------------------------------------


def test_help_lines_include_custom_shortcut_after_sync() -> None:
    from airpilot.actions import action_help_lines

    config = AppConfig()
    config.gesture_bindings[0].shortcut_keys = ("ctrl", "9")
    config.gesture_bindings[0].action_id = ""
    sync_custom_shortcuts(config)

    lines = action_help_lines(config.actions)

    # The custom action should appear somewhere in the help text
    assert any("Ctrl+9" in line for line in lines)
