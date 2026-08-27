"""Authoritative gesture/action registry for AirPilot.

This module is the single source of truth for all gestures, their physical
descriptions, emitted keyboard outputs, help sections, display metadata, and
mode membership.  Recognition mappings, Help content, and sidebar dashboard
rows are all derived from this registry to prevent drift.

Design rules
------------
- ``gesture_text`` describes what the *hand* does (never keyboard key names).
- ``keys`` describes the *emitted keyboard output* (empty tuple if no keys).
- ``section`` matches the uppercase section headers used in Help.
- ``mode`` is ``"default"`` (shown when not in shortcut mode),
  ``"shortcut"`` (shown only in shortcut mode), or ``"any"`` (always shown).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_KEY_LABELS: dict[str, str] = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "win": "Win",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "tab": "Tab",
    "esc": "Esc",
    "enter": "Enter",
    "delete": "Del",
    "f4": "F4",
    "playpause": "Play/Pause",
    "volumeup": "Volume Up",
    "volumedown": "Volume Down",
    "volumemute": "Volume Mute",
    "nexttrack": "Next Track",
    "prevtrack": "Previous Track",
}


@dataclass(frozen=True)
class RegistryEntry:
    """One row in the authoritative gesture registry.

    Attributes
    ----------
    id:
        Unique machine identifier for this entry (used for dedup checks and
        regression tests).
    emoji:
        Display emoji (used in Help Treeview and sidebar header rows).
        Emoji is never the sole meaning — the label/gesture_text carry meaning.
    section:
        Uppercase section heading under which this entry appears in Help and,
        when applicable, the sidebar dashboard.
    action_label:
        Human-readable description of *what happens* (the "Action" Help column).
    gesture_text:
        Physical hand gesture required (the "Gesture" Help column). Must never
        contain keyboard key names.
    keys:
        Tuple of lowercase key names emitted as keyboard output. Empty tuple
        means no keyboard output (mouse-only or UI action).
    mode:
        Dashboard context: ``"default"`` = shown in default mode sidebar;
        ``"shortcut"`` = shown only in shortcut-mode sidebar;
        ``"any"`` = always present (e.g. help, quit).
    action_id:
        Optional link to ``ActionConfig.catalog`` key for state lookup.
    enabled:
        Whether this entry is currently available (default True; may be
        overridden by config state at display time).
    risky:
        Whether this entry involves a potentially harmful action.
    """

    id: str
    emoji: str
    section: str
    action_label: str
    gesture_text: str
    keys: tuple[str, ...] = ()
    mode: str = "default"
    action_id: str | None = None
    enabled: bool = True
    risky: bool = False

    @property
    def keys_label(self) -> str:
        """Return a human-readable keyboard shortcut string, e.g. ``Win+Tab``."""
        if not self.keys:
            return "--"
        return "+".join(
            _KEY_LABELS.get(k, k.upper() if len(k) == 1 else k.title()) for k in self.keys
        )


# ---------------------------------------------------------------------------
# Authoritative registry
# ---------------------------------------------------------------------------
# Entries appear in the order they should be shown within each section.
# Physical gestures (gesture_text) intentionally never mention keyboard keys.
# Keyboard shortcuts (keys) are the emitted outputs only.

GESTURE_REGISTRY: tuple[RegistryEntry, ...] = (
    # ------------------------------------------------------------------ MOUSE
    RegistryEntry(
        id="mouse.move",
        emoji="🖱️",
        section="MOUSE",
        action_label="Move pointer",
        gesture_text="Thumb in range; move the palm/knuckle anchor",
        keys=(),
        mode="default",
    ),
    RegistryEntry(
        id="mouse.freeze",
        emoji="🧊",
        section="MOUSE",
        action_label="Freeze pointer / clutch",
        gesture_text="Close or bend thumb out of activation range",
        keys=(),
        mode="default",
    ),
    RegistryEntry(
        id="mouse.left_click",
        emoji="👆",
        section="MOUSE",
        action_label="Left click",
        gesture_text="While clutched: bend then release index finger",
        keys=(),
        mode="default",
    ),
    RegistryEntry(
        id="mouse.drag",
        emoji="✊",
        section="MOUSE",
        action_label="Drag and drop",
        gesture_text="While clutched: hold bent index and move hand; open index to drop",
        keys=(),
        mode="default",
    ),
    RegistryEntry(
        id="mouse.right_click",
        emoji="☝️",
        section="MOUSE",
        action_label="Right click",
        gesture_text="While clutched: bend then release middle finger",
        keys=(),
        mode="default",
    ),
    RegistryEntry(
        id="mouse.middle_click",
        emoji="🖱️",
        section="MOUSE",
        action_label="Middle click",
        gesture_text="While clutched: hold middle bend, then release",
        keys=(),
        mode="default",
    ),
    RegistryEntry(
        id="mouse.scroll",
        emoji="📜",
        section="MOUSE",
        action_label="Scroll",
        gesture_text="Thumb/ring pinch; move hand up or down",
        keys=(),
        mode="default",
    ),
    # --------------------------------------------------------------- CONTROL
    RegistryEntry(
        id="control.arm_keyboard",
        emoji="✅",
        section="CONTROL",
        action_label="Arm / disarm mouse output",
        gesture_text="Press A in the preview window",
        keys=("a",),
        mode="any",
    ),
    RegistryEntry(
        id="control.arm_gesture",
        emoji="✅",
        section="CONTROL",
        action_label="Arm without keyboard",
        gesture_text="Hold second-hand thumb + middle finger together",
        keys=(),
        mode="default",
        action_id="ui.arm",
    ),
    RegistryEntry(
        id="control.pause_keyboard",
        emoji="⏸️",
        section="CONTROL",
        action_label="Pause / resume gestures",
        gesture_text="Press P in the preview window",
        keys=("p",),
        mode="any",
    ),
    RegistryEntry(
        id="control.help_keyboard",
        emoji="❓",
        section="CONTROL",
        action_label="Toggle Help window",
        gesture_text="Press H in the preview window",
        keys=("h",),
        mode="any",
    ),
    RegistryEntry(
        id="control.help_gesture",
        emoji="❓",
        section="CONTROL",
        action_label="Toggle Help (gesture)",
        gesture_text="Hold second-hand thumb + index finger together",
        keys=(),
        mode="default",
        action_id="ui.toggle_help",
    ),
    RegistryEntry(
        id="control.settings_keyboard",
        emoji="⚙️",
        section="CONTROL",
        action_label="Open Settings window",
        gesture_text="Press S in the preview window",
        keys=("s",),
        mode="any",
    ),
    RegistryEntry(
        id="control.quit_keyboard",
        emoji="❌",
        section="CONTROL",
        action_label="Quit AirPilot",
        gesture_text="Press Q in the preview window",
        keys=("q",),
        mode="any",
    ),
    RegistryEntry(
        id="control.failsafe",
        emoji="🛑",
        section="CONTROL",
        action_label="Emergency stop (disarm)",
        gesture_text="Move pointer into any screen corner",
        keys=(),
        mode="any",
    ),
    RegistryEntry(
        id="control.esc_noop",
        emoji="🔕",
        section="CONTROL",
        action_label="Esc key (ignored)",
        gesture_text="Press Esc — AirPilot ignores it; press Q to quit",
        keys=("esc",),
        mode="any",
    ),
    # ---------------------------------------------------------- SHORTCUT MODE
    RegistryEntry(
        id="shortcut.enter",
        emoji="✌️",
        section="SHORTCUT MODE",
        action_label="Enter Shortcut Mode",
        gesture_text="Hold second-hand thumb + pinky finger together",
        keys=(),
        mode="default",
    ),
    RegistryEntry(
        id="shortcut.index_release",
        emoji="✌️",
        section="SHORTCUT MODE",
        action_label="Shortcut: index pinch",
        gesture_text="Shortcut Mode + pinch and release index finger",
        keys=(),
        mode="shortcut",
        action_id=None,  # resolved from config at display time
    ),
    RegistryEntry(
        id="shortcut.index_hold",
        emoji="✌️",
        section="SHORTCUT MODE",
        action_label="Shortcut: hold index",
        gesture_text="Shortcut Mode + hold index finger pinch",
        keys=(),
        mode="shortcut",
        action_id=None,
    ),
    RegistryEntry(
        id="shortcut.middle_release",
        emoji="✌️",
        section="SHORTCUT MODE",
        action_label="Shortcut: middle pinch",
        gesture_text="Shortcut Mode + pinch and release middle finger",
        keys=(),
        mode="shortcut",
        action_id=None,
    ),
    RegistryEntry(
        id="shortcut.middle_hold",
        emoji="✌️",
        section="SHORTCUT MODE",
        action_label="Shortcut: hold middle",
        gesture_text="Shortcut Mode + hold middle finger pinch",
        keys=(),
        mode="shortcut",
        action_id=None,
    ),
    RegistryEntry(
        id="shortcut.ring_release",
        emoji="✌️",
        section="SHORTCUT MODE",
        action_label="Shortcut: ring pinch",
        gesture_text="Shortcut Mode + pinch and release ring finger",
        keys=(),
        mode="shortcut",
        action_id=None,
    ),
    RegistryEntry(
        id="shortcut.pinky_release",
        emoji="✌️",
        section="SHORTCUT MODE",
        action_label="Shortcut: pinky pinch",
        gesture_text="Shortcut Mode + pinch and release pinky finger",
        keys=(),
        mode="shortcut",
        action_id=None,
    ),
    # -------------------------------------------------------- QUICK START
    RegistryEntry(
        id="quick.switch_apps",
        emoji="↔️",
        section="QUICK START",
        action_label="Switch apps (Task View)",
        gesture_text=(
            "Shortcut Mode + hold index finger; move hand left or right; release to confirm"
        ),
        keys=("win", "tab"),
        mode="shortcut",
        action_id="system.task_view",
    ),
)


def registry_entries_for_section(section: str) -> list[RegistryEntry]:
    """Return all entries for a named section, preserving order."""
    return [e for e in GESTURE_REGISTRY if e.section == section]


def registry_entries_for_mode(mode: str) -> list[RegistryEntry]:
    """Return entries valid in a given dashboard mode (``"default"`` or ``"shortcut"``)."""
    return [e for e in GESTURE_REGISTRY if e.mode in (mode, "any")]


def registry_ids() -> set[str]:
    """Return all registered entry IDs."""
    return {e.id for e in GESTURE_REGISTRY}


def registry_sections() -> list[str]:
    """Return ordered unique section names."""
    seen: set[str] = set()
    result: list[str] = []
    for entry in GESTURE_REGISTRY:
        if entry.section not in seen:
            seen.add(entry.section)
            result.append(entry.section)
    return result
