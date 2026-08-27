from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import hypot

from airpilot.config import ActionConfig, GestureConfig, ShortcutConfig
from airpilot.domain.gestures import INDEX_TIP, MIDDLE_TIP, PINKY_TIP, RING_TIP, THUMB_TIP
from airpilot.domain.types import GestureEvents, HandLandmarks, TrackingFrame
from airpilot.input import MouseController

SHORTCUT_GESTURES = {
    "help_secondary_index_hold",
    "shortcut_index_release",
    "shortcut_index_hold",
    "shortcut_middle_release",
    "shortcut_ring_release",
    "shortcut_pinky_release",
}
RESERVED_SHORTCUTS = {
    ("ctrl", "alt", "delete"),
}
RISKY_SHORTCUTS = {
    ("alt", "f4"),
    ("win", "l"),
}


@dataclass(slots=True)
class _ActionPinchState:
    active: bool = False
    started_ms: int | None = None
    consumed: bool = False


@dataclass(slots=True)
class ActionRouter:
    actions: ActionConfig
    gestures: GestureConfig
    _mode_started_ms: int | None = None
    _pinches: dict[str, _ActionPinchState] = field(
        default_factory=lambda: {
            "index": _ActionPinchState(),
            "middle": _ActionPinchState(),
            "ring": _ActionPinchState(),
            "pinky": _ActionPinchState(),
        }
    )
    _last_action_ms: int = -1_000_000
    _released_drag_for_mode: bool = False
    _released_drag_for_help: bool = False
    _help: _ActionPinchState = field(default_factory=_ActionPinchState)

    def process(self, frame: TrackingFrame, events: GestureEvents) -> GestureEvents:
        if not self.actions.enabled or events.paused:
            self._reset()
            return events

        mode_held = _shortcut_mode_held(frame.secondary_hand, self.gestures)
        help_held = _help_held(frame.secondary_hand, self.gestures) and not mode_held
        help_events = self._process_help(events, frame.timestamp_ms, help_held)
        if help_events.action_id is not None or help_events.active_gesture == "help_pending":
            return help_events
        if not mode_held:
            self._reset_shortcut()
            return events

        if self._mode_started_ms is None:
            self._mode_started_ms = frame.timestamp_ms

        shortcut_mode = (
            frame.timestamp_ms - self._mode_started_ms >= self.gestures.shortcut_mode_hold_ms
        )
        if not shortcut_mode:
            return self._suppress_mouse(events, active_gesture="shortcut_pending")

        routed = self._suppress_mouse(events, active_gesture="shortcut_mode")
        if (events.drag_start or events.status == "dragging") and not self._released_drag_for_mode:
            routed = replace(routed, drag_end=True)
            self._released_drag_for_mode = True
        if events.drag_end:
            self._released_drag_for_mode = False
        routed = replace(
            routed,
            shortcut_mode=True,
            active_gesture="shortcut_mode",
            status="shortcut_mode",
        )
        hand = frame.control_hand
        if hand is None or len(hand.landmarks) < 21:
            return routed

        for name, tip_index in (
            ("index", INDEX_TIP),
            ("middle", MIDDLE_TIP),
            ("ring", RING_TIP),
            ("pinky", PINKY_TIP),
        ):
            routed = self._process_action_pinch(
                routed,
                frame.timestamp_ms,
                name,
                _distance(hand, THUMB_TIP, tip_index) <= self.gestures.pinch_threshold,
            )
            if routed.action_id is not None:
                return routed
        return routed

    def _process_action_pinch(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        name: str,
        active_now: bool,
    ) -> GestureEvents:
        state = self._pinches[name]
        if active_now and not state.active:
            self._pinches[name] = _ActionPinchState(active=True, started_ms=timestamp_ms)
            return replace(events, active_gesture=f"shortcut_{name}")

        if active_now and state.active:
            started = state.started_ms if state.started_ms is not None else timestamp_ms
            if (
                name == "index"
                and not state.consumed
                and timestamp_ms - started >= self.gestures.shortcut_action_hold_ms
            ):
                state.consumed = True
                return self._emit(events, "shortcut_index_hold", timestamp_ms)
            return replace(events, active_gesture=f"shortcut_{name}")

        if not active_now and state.active:
            started = state.started_ms if state.started_ms is not None else timestamp_ms
            held_ms = timestamp_ms - started
            consumed = state.consumed
            self._pinches[name] = _ActionPinchState()
            if held_ms >= self.gestures.min_click_hold_ms and not consumed:
                return self._emit(events, f"shortcut_{name}_release", timestamp_ms)
        return events

    def _emit(self, events: GestureEvents, gesture_id: str, timestamp_ms: int) -> GestureEvents:
        if timestamp_ms - self._last_action_ms < self.gestures.action_cooldown_ms:
            return events
        action_id = self.actions.gesture_actions.get(gesture_id)
        if action_id is None:
            return events
        entry = self.actions.catalog.get(action_id)
        if (
            entry is None
            or not entry.enabled
            or (entry.risky and not self.actions.risky_actions_enabled)
        ):
            return events
        self._last_action_ms = timestamp_ms
        return replace(
            events,
            action_id=action_id,
            action_label=entry.label,
            active_gesture=gesture_id,
            status="action",
        )

    def _process_help(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        active_now: bool,
    ) -> GestureEvents:
        if not self.gestures.help_gesture_enabled:
            self._help = _ActionPinchState()
            self._released_drag_for_help = False
            return events
        if active_now and not self._help.active:
            self._help = _ActionPinchState(active=True, started_ms=timestamp_ms)
            return self._suppress_help_mouse(events)
        if active_now and self._help.active:
            started = self._help.started_ms if self._help.started_ms is not None else timestamp_ms
            suppressed = self._suppress_help_mouse(events)
            if (
                not self._help.consumed
                and timestamp_ms - started >= self.gestures.help_gesture_hold_ms
            ):
                self._help.consumed = True
                return self._emit(suppressed, "help_secondary_index_hold", timestamp_ms)
            return suppressed
        if not active_now and self._help.active:
            self._help = _ActionPinchState()
            self._released_drag_for_help = False
        return events

    def _reset(self) -> None:
        self._reset_shortcut()
        self._help = _ActionPinchState()
        self._released_drag_for_help = False

    def _reset_shortcut(self) -> None:
        self._mode_started_ms = None
        self._released_drag_for_mode = False
        for key in self._pinches:
            self._pinches[key] = _ActionPinchState()

    @staticmethod
    def _suppress_mouse(
        events: GestureEvents,
        *,
        active_gesture: str,
        shortcut_mode: bool = True,
    ) -> GestureEvents:
        return replace(
            events,
            move=None,
            left_click=False,
            right_click=False,
            middle_click=False,
            drag_start=False,
            scroll=0,
            shortcut_mode=shortcut_mode,
            active_gesture=active_gesture,
            status=active_gesture,
        )

    def _suppress_help_mouse(self, events: GestureEvents) -> GestureEvents:
        suppressed = self._suppress_mouse(
            events,
            active_gesture="help_pending",
            shortcut_mode=False,
        )
        if (events.drag_start or events.status == "dragging") and not self._released_drag_for_help:
            suppressed = replace(suppressed, drag_end=True)
            self._released_drag_for_help = True
        if events.drag_end:
            self._released_drag_for_help = False
        return suppressed


def dispatch_action(actions: ActionConfig, mouse: MouseController, action_id: str) -> str | None:
    entry = actions.catalog.get(action_id)
    if entry is None or not entry.enabled:
        return None
    if entry.risky and not actions.risky_actions_enabled:
        return None
    if not entry.keys:
        return entry.label
    mouse.hotkey(entry.keys)
    return entry.label


def validate_action_config(actions: ActionConfig) -> None:
    for gesture_id, action_id in actions.gesture_actions.items():
        if gesture_id not in SHORTCUT_GESTURES:
            raise ValueError(f"Unknown AirPilot gesture binding {gesture_id!r}")
        if action_id not in actions.catalog:
            raise ValueError(f"Unknown AirPilot action {action_id!r}")
    for action_id, entry in actions.catalog.items():
        _validate_shortcut(action_id, entry)


def action_help_lines(actions: ActionConfig, *, max_actions: int = 5) -> list[str]:
    lines = [
        "Mouse",
        "Thumb + index pinch/release - Left click",
        "Hold thumb + index - Drag; release to drop",
        "Thumb + middle pinch/release - Right click",
        "Hold thumb + middle - Middle click",
        "Thumb + ring pinch + vertical movement - Scroll",
        "Control",
        "A - Arm/disarm mouse output",
        "P - Pause/resume",
        "H - Toggle this Help window",
        "Q or Esc - Quit",
        "Two-hand help gesture: hold second-hand thumb + index",
    ]
    if actions.enabled:
        enabled = [
            f"{_gesture_label(gesture)} - {actions.catalog[action_id].label}"
            for gesture, action_id in actions.gesture_actions.items()
            if action_id in actions.catalog
            and actions.catalog[action_id].enabled
            and action_id != "ui.toggle_help"
        ]
        if enabled:
            lines.append("Shortcut mode: hold second-hand thumb + pinky")
            lines.extend(enabled[:max_actions])
        risky = [
            entry.label
            for entry in actions.catalog.values()
            if entry.risky and (not entry.enabled or not actions.risky_actions_enabled)
        ]
        if risky:
            lines.append("Risky actions disabled by default: " + ", ".join(risky[:4]))
    return lines


def _validate_shortcut(action_id: str, entry: ShortcutConfig) -> None:
    keys = tuple(_canonical_key(key) for key in entry.keys)
    if keys in RESERVED_SHORTCUTS:
        raise ValueError(f"Reserved AirPilot shortcut for {action_id!r}: {'+'.join(keys)}")
    if keys in RISKY_SHORTCUTS and not entry.risky:
        raise ValueError(f"Risky AirPilot shortcut must be flagged for {action_id!r}")


def _canonical_key(key: str) -> str:
    normalized = key.lower()
    aliases = {
        "altleft": "alt",
        "altright": "alt",
        "ctrlleft": "ctrl",
        "ctrlright": "ctrl",
        "control": "ctrl",
        "controlleft": "ctrl",
        "controlright": "ctrl",
        "winleft": "win",
        "winright": "win",
        "command": "win",
        "cmd": "win",
        "shiftleft": "shift",
        "shiftright": "shift",
        "del": "delete",
    }
    return aliases.get(normalized, normalized)


def _gesture_label(gesture_id: str) -> str:
    labels = {
        "shortcut_index_release": "Shortcut mode + thumb/index pinch",
        "shortcut_index_hold": "Shortcut mode + hold thumb/index",
        "shortcut_middle_release": "Shortcut mode + thumb/middle pinch",
        "shortcut_ring_release": "Shortcut mode + thumb/ring pinch",
        "shortcut_pinky_release": "Shortcut mode + thumb/pinky pinch",
        "help_secondary_index_hold": "Second-hand thumb/index hold",
    }
    return labels.get(gesture_id, gesture_id.removeprefix("shortcut_").replace("_", " "))


def _shortcut_mode_held(hand: HandLandmarks | None, gestures: GestureConfig) -> bool:
    if hand is None or len(hand.landmarks) < 21:
        return False
    return _distance(hand, THUMB_TIP, PINKY_TIP) <= gestures.pause_pinch_threshold


def _help_held(hand: HandLandmarks | None, gestures: GestureConfig) -> bool:
    if hand is None or len(hand.landmarks) < 21:
        return False
    return _distance(hand, THUMB_TIP, INDEX_TIP) <= gestures.pinch_threshold


def _distance(hand: HandLandmarks, a: int, b: int) -> float:
    first = hand.landmarks[a]
    second = hand.landmarks[b]
    return hypot(first.x - second.x, first.y - second.y)
