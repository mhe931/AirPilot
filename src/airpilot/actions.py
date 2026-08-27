from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import hypot

from airpilot.config import ActionConfig, GestureConfig, ShortcutConfig
from airpilot.domain.gestures import INDEX_TIP, MIDDLE_TIP, PINKY_TIP, RING_TIP, THUMB_TIP
from airpilot.domain.types import GestureEvents, HandLandmarks, TrackingFrame
from airpilot.input import MouseController

SHORTCUT_GESTURES = {
    "arm_secondary_middle_hold",
    "help_secondary_index_hold",
    "shortcut_index_release",
    "shortcut_index_hold",
    "shortcut_middle_release",
    "shortcut_middle_hold",
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
class _TaskViewState:
    active: bool = False
    pending: bool = False
    started_ms: int | None = None
    anchor_x: float | None = None
    last_navigation_ms: int = -1_000_000
    opened: bool = False


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
    _arm: _ActionPinchState = field(default_factory=_ActionPinchState)
    _task_view: _TaskViewState = field(default_factory=_TaskViewState)
    _suppress_index_click_until_release: bool = False

    def process(self, frame: TrackingFrame, events: GestureEvents) -> GestureEvents:
        if not self.actions.enabled or events.paused:
            self._reset()
            return events

        if self._suppress_index_click_until_release:
            if not _valid_action_hand(frame.control_hand):
                return self._suppress_mouse(
                    events,
                    active_gesture="shortcut_cancel_pending",
                    shortcut_mode=False,
                )
            if _task_view_index_released(frame.control_hand, self.gestures):
                self._suppress_index_click_until_release = False
                return self._suppress_mouse(
                    events,
                    active_gesture="shortcut_cancel_release",
                    shortcut_mode=False,
                )
            return self._suppress_mouse(
                events,
                active_gesture="shortcut_cancel_pending",
                shortcut_mode=False,
            )

        mode_held = _shortcut_mode_held(frame.secondary_hand, self.gestures)
        if self._task_view.active and not mode_held:
            index_still_held = _task_view_index_held(frame.control_hand, self.gestures)
            if index_still_held:
                self._suppress_index_click_until_release = True
            return self._finish_task_view(
                events,
                confirm=self.gestures.task_view_confirm_on_release and not index_still_held,
            )

        arm_held = _arm_held(frame.secondary_hand, self.gestures) and not mode_held
        arm_events = self._process_arm(events, frame.timestamp_ms, arm_held)
        if arm_events.action_id is not None or arm_events.active_gesture == "arm_pending":
            return arm_events

        help_held = _help_held(frame.secondary_hand, self.gestures) and not mode_held
        help_events = self._process_help(events, frame.timestamp_ms, help_held)
        if help_events.action_id is not None or help_events.active_gesture == "help_pending":
            return help_events
        if not mode_held:
            self._reset_shortcut()
            if self._task_view.pending:
                if _task_view_index_held(frame.control_hand, self.gestures):
                    self._suppress_index_click_until_release = True
                    self._task_view = _TaskViewState()
                    return self._suppress_mouse(
                        events,
                        active_gesture="shortcut_cancel_pending",
                        shortcut_mode=False,
                    )
                self._task_view = _TaskViewState()
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

        if self.actions.gesture_actions.get("shortcut_index_hold") in (None, "system.task_view"):
            task_view_events = self._process_task_view(routed, frame.timestamp_ms, hand)
            if (
                self._task_view.active
                or task_view_events.action_id is not None
                or task_view_events.active_gesture
                in {"task_view_pending", "task_view", "task_view_disabled"}
            ):
                return task_view_events

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
            hold_gesture = f"shortcut_{name}_hold"
            if (
                hold_gesture in self.actions.gesture_actions
                and not state.consumed
                and timestamp_ms - started >= self.gestures.shortcut_action_hold_ms
            ):
                state.consumed = True
                return self._emit(events, hold_gesture, timestamp_ms)
            return replace(events, active_gesture=f"shortcut_{name}")

        if not active_now and state.active:
            started = state.started_ms if state.started_ms is not None else timestamp_ms
            held_ms = timestamp_ms - started
            consumed = state.consumed
            self._pinches[name] = _ActionPinchState()
            if held_ms >= self.gestures.min_click_hold_ms and not consumed:
                return self._emit(events, f"shortcut_{name}_release", timestamp_ms)
        return events

    def _process_arm(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        active_now: bool,
    ) -> GestureEvents:
        if not self.gestures.arm_gesture_enabled:
            self._arm = _ActionPinchState()
            return events
        if active_now and not self._arm.active:
            self._arm = _ActionPinchState(active=True, started_ms=timestamp_ms)
            return self._suppress_mouse(events, active_gesture="arm_pending", shortcut_mode=False)
        if active_now and self._arm.active:
            suppressed = self._suppress_mouse(
                events,
                active_gesture="arm_pending",
                shortcut_mode=False,
            )
            started = self._arm.started_ms if self._arm.started_ms is not None else timestamp_ms
            if (
                not self._arm.consumed
                and timestamp_ms - started >= self.gestures.arm_gesture_hold_ms
            ):
                self._arm.consumed = True
                return self._emit(suppressed, "arm_secondary_middle_hold", timestamp_ms)
            return suppressed
        if not active_now and self._arm.active:
            self._arm = _ActionPinchState()
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
        self._arm = _ActionPinchState()
        self._task_view = _TaskViewState()
        self._suppress_index_click_until_release = False
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

    def _process_task_view(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        hand: HandLandmarks,
    ) -> GestureEvents:
        index_held = _task_view_index_held(hand, self.gestures)
        if index_held and not self._task_view.active:
            if not self._task_view.pending:
                self._task_view = _TaskViewState(
                    pending=True,
                    started_ms=timestamp_ms,
                    anchor_x=hand.landmarks[INDEX_TIP].x,
                )
                return self._suppress_mouse(events, active_gesture="task_view_pending")
            started_anchor = self._task_view.anchor_x
            if started_anchor is None:
                self._task_view.anchor_x = hand.landmarks[INDEX_TIP].x
            started = self._task_view.started_ms
            if started is None:
                self._task_view.started_ms = timestamp_ms
                started = timestamp_ms
            if timestamp_ms - started >= self.gestures.shortcut_action_hold_ms:
                if not self._task_view_action_enabled("system.task_view"):
                    self._task_view = _TaskViewState()
                    self._pinches["index"] = _ActionPinchState(
                        active=True,
                        started_ms=timestamp_ms,
                        consumed=True,
                    )
                    return self._suppress_mouse(events, active_gesture="task_view_disabled")
                self._task_view = _TaskViewState(
                    active=True,
                    pending=False,
                    started_ms=timestamp_ms,
                    anchor_x=hand.landmarks[INDEX_TIP].x,
                    opened=True,
                )
                return self._emit_task_view(events, "system.task_view", active_gesture="task_view")
            return self._suppress_mouse(events, active_gesture="task_view_pending")

        if self._task_view.active:
            if not index_held:
                return self._finish_task_view(
                    events,
                    confirm=self.gestures.task_view_confirm_on_release,
                )
            return self._navigate_task_view(events, timestamp_ms, hand.landmarks[INDEX_TIP].x)

        if self._task_view.pending and not index_held:
            started = (
                self._task_view.started_ms
                if self._task_view.started_ms is not None
                else timestamp_ms
            )
            held_ms = timestamp_ms - started
            self._task_view = _TaskViewState()
            self._pinches["index"] = _ActionPinchState()
            if held_ms >= self.gestures.min_click_hold_ms:
                return self._emit(events, "shortcut_index_release", timestamp_ms)
        return events

    def _navigate_task_view(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        current_x: float,
    ) -> GestureEvents:
        suppressed = self._suppress_mouse(events, active_gesture="task_view")
        anchor = self._task_view.anchor_x
        if anchor is None:
            self._task_view.anchor_x = current_x
            return suppressed
        delta = current_x - anchor
        if self.gestures.task_view_mirror_x:
            delta = -delta
        if abs(delta) < self.gestures.task_view_navigation_delta:
            return replace(suppressed, status="task_view_release_to_open")
        if (
            timestamp_ms - self._task_view.last_navigation_ms
            < self.gestures.task_view_navigation_cooldown_ms
        ):
            return replace(suppressed, status="task_view_cooldown")
        self._task_view.anchor_x = current_x
        self._task_view.last_navigation_ms = timestamp_ms
        action_id = "task_view.next" if delta > 0 else "task_view.previous"
        active_gesture = "task_view_select_right" if delta > 0 else "task_view_select_left"
        return self._emit_task_view(suppressed, action_id, active_gesture=active_gesture)

    def _finish_task_view(self, events: GestureEvents, *, confirm: bool) -> GestureEvents:
        action_id = "task_view.confirm" if confirm else "task_view.cancel"
        self._task_view = _TaskViewState()
        self._pinches["index"] = _ActionPinchState()
        return self._emit_task_view(events, action_id, active_gesture="task_view_confirm")

    def _emit_task_view(
        self,
        events: GestureEvents,
        action_id: str,
        *,
        active_gesture: str,
    ) -> GestureEvents:
        if not self._task_view_action_enabled(action_id):
            return self._suppress_mouse(events, active_gesture=active_gesture)
        return replace(
            self._suppress_mouse(events, active_gesture=active_gesture),
            action_id=action_id,
            action_label=self.actions.catalog[action_id].label,
            status=active_gesture,
        )

    def _task_view_action_enabled(self, action_id: str) -> bool:
        entry = self.actions.catalog.get(action_id)
        return (
            entry is not None
            and entry.enabled
            and (not entry.risky or self.actions.risky_actions_enabled)
        )


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


def action_help_lines(actions: ActionConfig, *, max_actions: int | None = None) -> list[str]:
    lines = [
        "QUICK START",
        "1. Arm: hold second-hand thumb + middle, or press A.",
        "2. Point: move the control-hand index fingertip.",
        "3. Click: pinch thumb + index, hold still, then release.",
        "4. Drag: pinch thumb + index, hold, move deliberately, release.",
        "5. Task View: hold Shortcut Mode, hold thumb + index, move left/right, release.",
        "",
        "STATUS CARDS",
        "Disarmed | Safe startup | Hold arm gesture or press A",
        "Active | Mouse output enabled | Emergency: corner failsafe or Q",
        "Shortcut Mode | Second-hand thumb + pinky | Suppresses mouse output",
        "Task View | Win+Tab app picker | Left/right selects, release opens",
        "",
        "PHILOSOPHY",
        "- Frequent actions use easy one-hand gestures.",
        "- Commands use deliberate two-hand Shortcut Mode.",
        "- Risky/system actions stay disabled unless explicitly enabled.",
        "- Continuous actions, such as scroll, stay active only while held.",
        "",
        "CORE MOUSE GESTURES",
        "Move control hand / index reference | Move pointer | Continuous",
        "Thumb + index pinch/release | Left click | Primary click",
        "Thumb + index hold + move | Drag/drop | Release to drop",
        "Thumb + middle pinch/release | Right click | Context menu",
        "Thumb + middle long hold | Middle click | Consumes right click",
        "Thumb + ring pinch + vertical hand movement | Scroll wheel | Move hand up/down",
        "Open / neutral hand | Normal pointer state | Release active holds",
        "",
        "CONTROL",
        "A | Arm/disarm mouse output",
        "Arm gesture | Hold second-hand thumb + middle",
        "P | Pause/resume",
        "H | Toggle this Help window",
        "Q or Esc | Quit",
        "Help gesture | Hold second-hand thumb + index",
        "Shortcut Mode | Hold second-hand thumb + pinky",
    ]
    if actions.enabled:
        lines.extend(["", "SHORTCUT MODE", "Enter: hold second-hand thumb + pinky."])
        mappings = _shortcut_mapping_lines(actions)
        lines.extend(mappings if max_actions is None else mappings[:max_actions])
    lines.extend(["", "AVAILABLE SHORTCUT ACTIONS"])
    lines.extend(_catalog_lines(actions))
    risky = _risky_lines(actions)
    if risky:
        lines.extend(["", "RISKY ACTIONS", *risky])
    return lines


def _shortcut_mapping_lines(actions: ActionConfig) -> list[str]:
    lines: list[str] = []
    for gesture, action_id in actions.gesture_actions.items():
        if action_id == "ui.toggle_help":
            continue
        entry = actions.catalog.get(action_id)
        if entry is None:
            continue
        state = "enabled" if entry.enabled else "disabled"
        lines.append(
            f"{_gesture_label(gesture)} | {entry.label} | {_format_keys(entry.keys)} | {state}"
        )
    return lines


def _catalog_lines(actions: ActionConfig) -> list[str]:
    profile_labels = {
        "editing": "Clipboard / Editing",
        "windows": "Windows / System",
        "browser": "Browser",
        "presentation": "Presentation",
        "media": "Media",
        "ui": "UI",
    }
    by_profile: dict[str, list[str]] = {}
    for entry in actions.catalog.values():
        if entry.profile == "ui":
            continue
        state = "enabled" if entry.enabled else "available"
        if entry.risky and (not entry.enabled or not actions.risky_actions_enabled):
            state = "risky disabled"
        by_profile.setdefault(entry.profile, []).append(
            f"- {entry.label} `{_format_keys(entry.keys)}` ({state})"
        )

    lines: list[str] = []
    known_profiles = ("editing", "windows", "browser", "presentation", "media")
    for profile in known_profiles:
        entries = by_profile.get(profile)
        if not entries:
            continue
        lines.append(profile_labels.get(profile, profile.title()))
        lines.extend(entries)
    for profile in sorted(key for key in by_profile if key not in known_profiles):
        entries = by_profile[profile]
        lines.append(profile_labels.get(profile, profile.title()))
        lines.extend(entries)
    return lines


def _risky_lines(actions: ActionConfig) -> list[str]:
    lines: list[str] = []
    for entry in actions.catalog.values():
        if entry.risky:
            state = (
                "enabled"
                if entry.enabled and actions.risky_actions_enabled
                else "disabled by default"
            )
            lines.append(f"- {entry.label} `{_format_keys(entry.keys)}` - {state}")
    return lines


def _format_keys(keys: tuple[str, ...]) -> str:
    labels = {
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
    }
    return "+".join(labels.get(key, key.upper() if len(key) == 1 else key.title()) for key in keys)


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
        "shortcut_middle_hold": "Shortcut mode + hold thumb/middle",
        "shortcut_ring_release": "Shortcut mode + thumb/ring pinch",
        "shortcut_pinky_release": "Shortcut mode + thumb/pinky pinch",
        "arm_secondary_middle_hold": "Second-hand thumb/middle hold",
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


def _arm_held(hand: HandLandmarks | None, gestures: GestureConfig) -> bool:
    if hand is None or len(hand.landmarks) < 21:
        return False
    return _distance(hand, THUMB_TIP, MIDDLE_TIP) <= gestures.arm_pinch_threshold


def _task_view_index_held(hand: HandLandmarks | None, gestures: GestureConfig) -> bool:
    if not _valid_action_hand(hand):
        return False
    assert hand is not None
    return _distance(hand, THUMB_TIP, INDEX_TIP) <= gestures.pinch_threshold


def _task_view_index_released(hand: HandLandmarks | None, gestures: GestureConfig) -> bool:
    if not _valid_action_hand(hand):
        return False
    assert hand is not None
    return _distance(hand, THUMB_TIP, INDEX_TIP) >= gestures.pinch_release_threshold


def _valid_action_hand(hand: HandLandmarks | None) -> bool:
    return hand is not None and len(hand.landmarks) >= 21


def _distance(hand: HandLandmarks, a: int, b: int) -> float:
    first = hand.landmarks[a]
    second = hand.landmarks[b]
    return hypot(first.x - second.x, first.y - second.y)
