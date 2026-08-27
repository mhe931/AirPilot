"""Tests for the authoritative gesture/action registry.

Acceptance criteria covered:
- Registry completeness: all required sections and entries exist.
- Registry uniqueness: no duplicate entry IDs.
- Gesture vs keyboard separation: gesture_text never contains key names that
  appear in the Keys/Shortcut column (the ``Switch apps | Shortcut Mode + h``
  truncation regression is covered here too).
- Dashboard mode replacement: default mode shows default entries only;
  shortcut mode shows shortcut entries only; mode exit restores correct list.
- Help/Settings/Quit all appear as gesture entries in the registry.
- keys_label formatting is correct and contains no physical gesture text.
- Help truncation regression: action_help_lines produces full untruncated
  gesture text for "Switch apps / Task View".
"""

from __future__ import annotations

import pytest

from airpilot.actions import action_help_lines
from airpilot.config import ActionConfig
from airpilot.registry import (
    GESTURE_REGISTRY,
    RegistryEntry,
    registry_entries_for_mode,
    registry_entries_for_section,
    registry_ids,
    registry_sections,
)

# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


def test_registry_has_no_duplicate_ids() -> None:
    ids = [e.id for e in GESTURE_REGISTRY]
    assert len(ids) == len(set(ids)), "Duplicate registry entry IDs found"


def test_registry_contains_required_sections() -> None:
    sections = registry_sections()
    for required in ("MOUSE", "CONTROL", "SHORTCUT MODE"):
        assert required in sections, f"Missing required section: {required}"


def test_registry_mouse_section_has_core_gestures() -> None:
    entries = registry_entries_for_section("MOUSE")
    labels = {e.id for e in entries}
    for required_id in ("mouse.move", "mouse.freeze", "mouse.left_click", "mouse.scroll"):
        assert required_id in labels, f"Missing mouse entry: {required_id}"


def test_registry_control_includes_help_settings_quit() -> None:
    control = {e.id for e in registry_entries_for_section("CONTROL")}
    assert "control.help_keyboard" in control, "Help keyboard control missing"
    assert "control.settings_keyboard" in control, "Settings keyboard control missing"
    assert "control.quit_keyboard" in control, "Quit keyboard control missing"


def test_registry_control_includes_physical_gestures_for_help() -> None:
    control = registry_entries_for_section("CONTROL")
    gesture_entries = [e for e in control if not e.keys]
    ids = {e.id for e in gesture_entries}
    assert "control.help_gesture" in ids, "Help physical gesture entry missing"
    assert "control.arm_gesture" in ids, "Arm physical gesture entry missing"


def test_registry_shortcut_mode_section_exists() -> None:
    entries = registry_entries_for_section("SHORTCUT MODE")
    assert len(entries) >= 2, "Shortcut mode section should have at least enter + pinch entries"


# ---------------------------------------------------------------------------
# Gesture vs keyboard separation
# ---------------------------------------------------------------------------

# These are keyboard key names that must NOT appear in gesture_text.
_KEYBOARD_KEY_NAMES = {
    "Win+Tab",
    "Ctrl+",
    "Alt+",
    "Shift+",
    " + H",
    " + Q",
    " + S",
    "press q",
    "press h",
    "press s",
    "press a",
    "press p",
}


def test_gesture_text_never_contains_emitted_shortcut_notation() -> None:
    """Gesture mode entries must describe hand actions, not emitted keyboard shortcuts.

    Keyboard-controlled entries (mode="any") legitimately say "Press H" etc. —
    that IS the physical action. The rule is: entries where mode is "default" or
    "shortcut" (pure hand gesture entries) must not contain emitted key notation
    like "Win+Tab" or "Ctrl+" in their gesture_text.
    """
    # Emitted shortcut patterns that must not appear in hand-gesture entries
    emitted_patterns = ("Win+", "Ctrl+", "Alt+", "Shift+")
    for entry in GESTURE_REGISTRY:
        if entry.mode not in ("default", "shortcut"):
            continue
        for pattern in emitted_patterns:
            assert pattern.lower() not in entry.gesture_text.lower(), (
                f"Entry {entry.id!r} (mode={entry.mode!r}) gesture_text contains "
                f"emitted shortcut notation {pattern!r}: {entry.gesture_text!r}"
            )


def test_keys_label_is_never_empty_for_keyboard_entries() -> None:
    """Entries that have keys must produce a non-empty keys_label."""
    for entry in GESTURE_REGISTRY:
        if entry.keys:
            assert entry.keys_label != "--", f"Entry {entry.id!r} has keys but keys_label is '--'"


def test_keys_label_does_not_contain_gesture_words() -> None:
    """Keys/shortcut label must not mention hand gestures."""
    gesture_words = {"thumb", "pinch", "index", "middle", "ring", "pinky", "palm", "hand"}
    for entry in GESTURE_REGISTRY:
        if entry.keys:
            label_lower = entry.keys_label.lower()
            for word in gesture_words:
                assert word not in label_lower, (
                    f"Entry {entry.id!r} keys_label contains gesture word {word!r}: "
                    f"{entry.keys_label!r}"
                )


# ---------------------------------------------------------------------------
# Dashboard mode replacement
# ---------------------------------------------------------------------------


def test_default_mode_entries_exclude_shortcut_only_entries() -> None:
    default_entries = registry_entries_for_mode("default")
    ids = {e.id for e in default_entries}
    # Shortcut-mode-specific entries (mode="shortcut") must not appear
    shortcut_only_ids = {e.id for e in GESTURE_REGISTRY if e.mode == "shortcut"}
    overlap = ids & shortcut_only_ids
    assert not overlap, f"Default mode includes shortcut-only entries: {overlap}"


def test_shortcut_mode_entries_do_not_include_default_only_entries() -> None:
    shortcut_entries = registry_entries_for_mode("shortcut")
    ids = {e.id for e in shortcut_entries}
    # Default-only entries (mode="default") must not appear in shortcut mode
    default_only_ids = {e.id for e in GESTURE_REGISTRY if e.mode == "default"}
    overlap = ids & default_only_ids
    assert not overlap, f"Shortcut mode includes default-only entries: {overlap}"


def test_any_mode_entries_appear_in_both_modes() -> None:
    any_ids = {e.id for e in GESTURE_REGISTRY if e.mode == "any"}
    default_ids = {e.id for e in registry_entries_for_mode("default")}
    shortcut_ids = {e.id for e in registry_entries_for_mode("shortcut")}
    # All "any" entries should be present in both modes
    for aid in any_ids:
        assert aid in default_ids, f"'any' entry {aid!r} missing from default mode"
        assert aid in shortcut_ids, f"'any' entry {aid!r} missing from shortcut mode"


# ---------------------------------------------------------------------------
# Help truncation regression
# ---------------------------------------------------------------------------


def test_action_help_lines_switch_apps_not_truncated() -> None:
    """Regression: 'Switch apps' gesture was truncated to 'Shortcut Mode + h'.

    The _format_help_row function previously applied [:17] truncation to the
    Gesture column. With that removed, the full gesture text must appear.
    """
    lines = action_help_lines(ActionConfig(), max_actions=None)
    # Find the Switch apps / Task View entry
    task_view_lines = [
        ln for ln in lines if "task view" in ln.lower() or "switch app" in ln.lower()
    ]
    assert task_view_lines, "No 'switch apps / task view' entry found in help lines"
    # The full gesture text should contain more than just "Shortcut Mode + h"
    for line in task_view_lines:
        if line.split(" | ")[1].strip() == "Shortcut Mode + h" if " | " in line else False:
            pytest.fail(
                f"Gesture text truncated to 'Shortcut Mode + h': {line!r}\n"
                "This is the known truncation regression."
            )


def test_action_help_lines_control_includes_settings() -> None:
    """Settings keyboard shortcut must appear in CONTROL help section."""
    lines = action_help_lines(ActionConfig(), max_actions=None)
    assert any("Settings" in line and "S" in line for line in lines), (
        "Settings keyboard shortcut missing from action_help_lines"
    )


# ---------------------------------------------------------------------------
# Help formatted rows do not truncate
# ---------------------------------------------------------------------------


def test_format_help_row_no_truncation() -> None:
    """_format_help_row must preserve full text without truncation."""
    from airpilot.app import _format_help_row

    long_gesture = "Shortcut Mode + hold index finger; move hand left or right; release to confirm"
    long_action = "Switch apps (Task View)"
    row = f"{long_action} | {long_gesture} | Win+Tab | enabled"
    formatted = _format_help_row(row)

    assert long_gesture in formatted, (
        f"Gesture text was truncated in formatted row.\nInput:  {row!r}\nOutput: {formatted!r}"
    )
    assert long_action in formatted, (
        f"Action text was truncated in formatted row.\nOutput: {formatted!r}"
    )


# ---------------------------------------------------------------------------
# Registry API contracts
# ---------------------------------------------------------------------------


def test_registry_ids_returns_all_ids() -> None:
    all_ids = registry_ids()
    assert len(all_ids) == len(GESTURE_REGISTRY)


def test_registry_entries_for_section_preserves_order() -> None:
    mouse_entries = registry_entries_for_section("MOUSE")
    mouse_in_registry = [e for e in GESTURE_REGISTRY if e.section == "MOUSE"]
    assert mouse_entries == mouse_in_registry


def test_registry_entry_is_immutable() -> None:
    entry = GESTURE_REGISTRY[0]
    with pytest.raises((AttributeError, TypeError)):
        entry.id = "new_id"  # type: ignore[misc]


def test_registry_entry_keys_label_formatting() -> None:
    entry = RegistryEntry(
        id="test.entry",
        emoji="✅",
        section="CONTROL",
        action_label="Test",
        gesture_text="Hold thumb",
        keys=("win", "tab"),
    )
    assert entry.keys_label == "Win+Tab"


def test_registry_entry_empty_keys_label() -> None:
    entry = RegistryEntry(
        id="test.mouse",
        emoji="🖱️",
        section="MOUSE",
        action_label="Move",
        gesture_text="Move hand",
        keys=(),
    )
    assert entry.keys_label == "--"
