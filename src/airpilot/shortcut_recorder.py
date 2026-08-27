"""Shortcut recorder: capture, normalize, and validate keyboard shortcuts.

This module is platform-independent.  All Tkinter integration lives in app.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Key sets
# ---------------------------------------------------------------------------

MODIFIER_KEYS: frozenset[str] = frozenset({"ctrl", "shift", "alt", "win"})

_SPECIAL_KEYS: frozenset[str] = frozenset(
    {
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "f10",
        "f11",
        "f12",
        "tab",
        "enter",
        "space",
        "backspace",
        "delete",
        "insert",
        "home",
        "end",
        "pageup",
        "pagedown",
        "left",
        "right",
        "up",
        "down",
        "esc",
        "playpause",
        "volumeup",
        "volumedown",
        "volumemute",
        "nexttrack",
        "prevtrack",
        "capslock",
        "numlock",
        "scrolllock",
        "printscreen",
        "pause",
    }
)

SUPPORTED_KEYS: frozenset[str] = frozenset(
    {chr(c) for c in range(ord("a"), ord("z") + 1)}
    | {str(n) for n in range(10)}
    | _SPECIAL_KEYS
    | MODIFIER_KEYS
)

# Reserved: must never be emitted
RESERVED_SHORTCUTS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("ctrl", "alt", "delete"),
    }
)

# Risky: require explicit risky flag (see RISKY_SHORTCUTS in actions.py)
RISKY_SHORTCUT_TUPLES: frozenset[tuple[str, ...]] = frozenset(
    {
        ("alt", "f4"),
        ("win", "l"),
    }
)

# ---------------------------------------------------------------------------
# Tkinter keysym → canonical key mapping
# ---------------------------------------------------------------------------

_KEYSYM_MAP: dict[str, str] = {
    "Control_L": "ctrl",
    "Control_R": "ctrl",
    "Shift_L": "shift",
    "Shift_R": "shift",
    "Alt_L": "alt",
    "Alt_R": "alt",
    "Meta_L": "win",
    "Meta_R": "win",
    "Super_L": "win",
    "Super_R": "win",
    "Return": "enter",
    "KP_Enter": "enter",
    "BackSpace": "backspace",
    "Delete": "delete",
    "Insert": "insert",
    "Home": "home",
    "End": "end",
    "Prior": "pageup",
    "Next": "pagedown",
    "Left": "left",
    "Right": "right",
    "Up": "up",
    "Down": "down",
    "Escape": "esc",
    "Tab": "tab",
    "space": "space",
    "F1": "f1",
    "F2": "f2",
    "F3": "f3",
    "F4": "f4",
    "F5": "f5",
    "F6": "f6",
    "F7": "f7",
    "F8": "f8",
    "F9": "f9",
    "F10": "f10",
    "F11": "f11",
    "F12": "f12",
    "Print": "printscreen",
    "Pause": "pause",
    "Caps_Lock": "capslock",
    "Num_Lock": "numlock",
    "Scroll_Lock": "scrolllock",
}

# ---------------------------------------------------------------------------
# Key normalization helpers
# ---------------------------------------------------------------------------

_KEY_LABELS: dict[str, str] = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "win": "Win",
    "tab": "Tab",
    "enter": "Enter",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Del",
    "insert": "Ins",
    "home": "Home",
    "end": "End",
    "pageup": "PgUp",
    "pagedown": "PgDn",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "esc": "Esc",
    "playpause": "Play/Pause",
    "volumeup": "Vol+",
    "volumedown": "Vol-",
    "volumemute": "Mute",
    "nexttrack": "Next",
    "prevtrack": "Prev",
    "printscreen": "PrtSc",
    "pause": "Pause",
    "capslock": "CapsLock",
    "numlock": "NumLock",
    "scrolllock": "ScrollLock",
}


def keysym_to_canonical(keysym: str) -> str | None:
    """Convert a Tkinter keysym to a canonical key name, or ``None`` if unsupported.

    Returns lowercase canonical names such as ``"ctrl"``, ``"a"``, ``"f5"``.
    """
    if keysym in _KEYSYM_MAP:
        return _KEYSYM_MAP[keysym]
    if len(keysym) == 1 and keysym.isalpha():
        return keysym.lower()
    if len(keysym) == 1 and keysym.isdigit():
        return keysym
    lower = keysym.lower()
    if lower in SUPPORTED_KEYS:
        return lower
    return None


def normalize_shortcut(keys: tuple[str, ...]) -> tuple[str, ...]:
    """Return *keys* with modifiers first then non-modifiers, all lowercase.

    Modifier order: ctrl → shift → alt → win.
    """
    mod_order = {"ctrl": 0, "shift": 1, "alt": 2, "win": 3}
    mods = sorted([k for k in keys if k in MODIFIER_KEYS], key=lambda k: mod_order.get(k, 99))
    non_mods = [k for k in keys if k not in MODIFIER_KEYS]
    return tuple(mods + non_mods)


def shortcut_label(keys: tuple[str, ...]) -> str:
    """Return a human-readable shortcut string, e.g. ``"Ctrl+Shift+P"``."""
    parts: list[str] = []
    for k in keys:
        if k.startswith("f") and k[1:].isdigit():
            parts.append(k.upper())
        elif k in _KEY_LABELS:
            parts.append(_KEY_LABELS[k])
        elif len(k) == 1:
            parts.append(k.upper())
        else:
            parts.append(k.title())
    return "+".join(parts)


def validate_shortcut(
    keys: tuple[str, ...],
    *,
    risky_ok: bool = False,
) -> str | None:
    """Validate a shortcut tuple. Returns an error string or ``None`` if valid.

    Args:
        keys: Tuple of canonical lowercase key names.
        risky_ok: If ``True`` risky shortcuts (e.g. Alt+F4) are permitted.
    """
    if not keys:
        return "No keys recorded."

    unknown = [k for k in keys if k not in SUPPORTED_KEYS]
    if unknown:
        return f"Unsupported key(s): {', '.join(unknown)}."

    non_mods = [k for k in keys if k not in MODIFIER_KEYS]
    if not non_mods:
        return "Modifier-only shortcuts (Ctrl, Shift, Alt, Win alone) are not allowed."

    normalized = normalize_shortcut(keys)
    if normalized in RESERVED_SHORTCUTS:
        return f"Reserved system shortcut: {shortcut_label(normalized)} — cannot be assigned."

    if normalized in RISKY_SHORTCUT_TUPLES and not risky_ok:
        label = shortcut_label(normalized)
        return f"Risky shortcut {label!r} — enable risky actions in config before assigning."

    return None


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShortcutConflict:
    """Describes a conflict between a new shortcut assignment and an existing one."""

    conflicting_binding_id: str
    conflicting_shortcut_label: str
    conflicting_context: str


def detect_shortcut_conflicts(
    keys: tuple[str, ...],
    all_bindings: Sequence[object],
    *,
    skip_index: int | None = None,
) -> list[ShortcutConflict]:
    """Return bindings that use *keys* and whose gesture conditions can overlap.

    Args:
        keys: Normalized shortcut to check.
        all_bindings: All configured :class:`~airpilot.config.GestureBinding` objects.
        skip_index: Index in *all_bindings* to exclude (the binding being edited).
    """
    from airpilot.config import GestureBinding, _gesture_bindings_conflict

    if not keys:
        return []

    # Identify the current binding for gesture-condition overlap checking
    current: GestureBinding | None = None
    if skip_index is not None and 0 <= skip_index < len(all_bindings):
        b = all_bindings[skip_index]
        if isinstance(b, GestureBinding):
            current = b

    conflicts: list[ShortcutConflict] = []
    for i, raw in enumerate(all_bindings):
        if i == skip_index:
            continue
        if not isinstance(raw, GestureBinding):
            continue
        other: GestureBinding = raw
        if not other.shortcut_keys:
            continue
        other_keys = tuple(other.shortcut_keys)
        if normalize_shortcut(other_keys) != normalize_shortcut(keys):
            continue
        if current is not None and not _gesture_bindings_conflict(current, other):
            continue
        ctx = f"binding '{other.id}': {other.hand} hand" + (
            f", move {other.movement}" if other.movement != "none" else ""
        )
        conflicts.append(
            ShortcutConflict(
                conflicting_binding_id=other.id,
                conflicting_shortcut_label=shortcut_label(other_keys),
                conflicting_context=ctx,
            )
        )
    return conflicts


# ---------------------------------------------------------------------------
# Config catalog helpers
# ---------------------------------------------------------------------------


def custom_action_id(binding_id: str) -> str:
    """Return the deterministic catalog key for a binding's recorded shortcut."""
    return f"custom.{binding_id}"


def sync_custom_shortcuts(config: object) -> None:
    """Inject / update catalog entries for bindings that have recorded ``shortcut_keys``.

    This must be called whenever gesture bindings change (after load, after apply).
    Entries whose binding is removed are pruned from the catalog.
    """
    from airpilot.config import AppConfig, ShortcutConfig

    cfg: AppConfig = config  # type: ignore[assignment]

    # Collect IDs that should exist
    wanted: dict[str, tuple[str, ...]] = {}
    for b in cfg.gesture_bindings:
        if b.shortcut_keys:
            wanted[custom_action_id(b.id)] = tuple(b.shortcut_keys)
            # Mirror into action_id so the binding fires via catalog dispatch
            if b.action_id != custom_action_id(b.id):
                b.action_id = custom_action_id(b.id)

    # Prune stale custom entries (whose binding was deleted or cleared)
    stale = [k for k in list(cfg.actions.catalog) if k.startswith("custom.") and k not in wanted]
    for k in stale:
        del cfg.actions.catalog[k]

    # Insert / update wanted entries
    for action_id, keys in wanted.items():
        existing = cfg.actions.catalog.get(action_id)
        needs_update = existing is None or existing.keys != keys
        if needs_update:
            from airpilot.actions import RISKY_SHORTCUTS

            is_risky = normalize_shortcut(keys) in RISKY_SHORTCUTS
            cfg.actions.catalog[action_id] = ShortcutConfig(
                label=shortcut_label(keys),
                keys=keys,
                profile="custom",
                enabled=True,
                risky=is_risky,
            )
