from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import hypot

from airpilot.config import GestureBinding, GestureConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.pose import (
    HandPose,
    estimate_hand_pose,
    stable_pointer_anchor,
    thumb_index_angle_deg,
)
from airpilot.domain.types import (
    CursorPosition,
    GestureEvents,
    Handedness,
    HandLandmarks,
    Landmark,
    TrackingFrame,
)

WRIST = 0
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_TIP = 12
RING_TIP = 16
PINKY_TIP = 20


@dataclass(slots=True)
class _PinchState:
    active: bool = False
    started_ms: int | None = None
    consumed: bool = False


@dataclass(slots=True)
class _ScrollState:
    active: bool = False
    anchor_y: float | None = None
    accumulated_y: float = 0.0
    last_emit_ms: int = -1_000_000


@dataclass(slots=True)
class GestureEngine:
    config: GestureConfig
    cursor_mapper: CursorMapper
    paused: bool = False
    _left: _PinchState = field(default_factory=_PinchState)
    _right: _PinchState = field(default_factory=_PinchState)
    _scroll: _ScrollState = field(default_factory=_ScrollState)
    _pause: _PinchState = field(default_factory=_PinchState)
    _drag_active: bool = False
    _last_left_click_ms: int = -1_000_000
    _last_right_click_ms: int = -1_000_000
    _last_middle_click_ms: int = -1_000_000
    _last_seen_ms: int | None = None
    _tracking_lost_reported: bool = False
    _click_anchor_position: CursorPosition | None = None
    _clutch_active: bool = False
    _clutch_anchor_position: CursorPosition | None = None
    _suppress_next_pointer_move: bool = False

    def process(self, frame: TrackingFrame) -> GestureEvents:
        hand = frame.hand
        if hand is None or not _has_required_points(hand):
            return self._handle_missing_hand(frame.timestamp_ms)

        self._last_seen_ms = frame.timestamp_ms
        self._tracking_lost_reported = False

        pause_changed, pause_active, drag_end = self._update_pause(hand, frame.timestamp_ms)
        if self.paused or pause_active:
            return GestureEvents(
                drag_end=drag_end,
                paused_changed=pause_changed,
                paused=self.paused,
                active_gesture="paused" if self.paused else "pause_hold",
                status="paused" if self.paused else "pause_pending",
            )

        pose = estimate_hand_pose(
            hand,
            thumb_close_threshold=self.config.thumb_close_threshold,
            thumb_open_threshold=self.config.thumb_open_threshold,
            finger_bend_threshold=self.config.finger_bend_threshold,
            finger_extend_threshold=self.config.finger_extend_threshold,
        )
        pointer_reference = _pointer_reference(hand)
        clutch_was_active = self._clutch_active
        clutch_now = self._resolve_clutch(pose, pointer_reference, hand)
        clutch_releasing = clutch_was_active and not clutch_now
        scroll_distance = _distance(hand, THUMB_TIP, RING_TIP)

        if pose.confident:
            left_now = clutch_now and _finger_bent(
                self._left.active, pose.index.flexion, self.config
            )
            right_now = clutch_now and _finger_bent(
                self._right.active,
                pose.middle.flexion,
                self.config,
            )
        else:
            left_distance = _distance(hand, THUMB_TIP, INDEX_TIP)
            right_distance = _distance(hand, THUMB_TIP, MIDDLE_TIP)
            left_now = _hysteresis(
                self._left.active,
                left_distance,
                self.config.pinch_threshold,
                self.config.pinch_release_threshold,
            )
            right_now = _hysteresis(
                self._right.active,
                right_distance,
                self.config.right_pinch_threshold,
                self.config.right_pinch_release_threshold,
            )
        scroll_now = _hysteresis(
            self._scroll.active,
            scroll_distance,
            self.config.scroll_pinch_threshold,
            self.config.scroll_pinch_release_threshold,
        )
        left_now, right_now, scroll_now, conflict = self._resolve_conflicts(
            left_now,
            right_now,
            scroll_now,
        )

        move = None
        if scroll_now:
            move = None
        elif self._drag_active:
            move = self._map_pointer(pointer_reference)
        elif self._clutch_active:
            move = self._clutch_anchor_position
        elif not left_now:
            move = self._map_pointer(pointer_reference)
        events = GestureEvents(
            move=move,
            paused_changed=pause_changed,
            paused=self.paused,
            active_gesture="conflict"
            if conflict
            else "clutch"
            if self._clutch_active
            else "tracking",
            status="gesture_conflict"
            if conflict
            else "clutch"
            if self._clutch_active
            else "tracking",
        )
        if conflict:
            return events

        events = self._process_left(events, frame.timestamp_ms, pointer_reference, left_now)
        events = self._process_right(events, frame.timestamp_ms, right_now)
        events = self._process_scroll(
            events,
            frame.timestamp_ms,
            hand.landmarks[WRIST],
            scroll_now,
        )
        if clutch_releasing:
            release_anchor = events.move or self._clutch_anchor_position
            self._release_clutch(pointer_reference)
            if not (
                events.left_click
                or events.right_click
                or events.middle_click
                or events.drag_end
                or events.scroll
            ):
                return replace(
                    events,
                    move=release_anchor,
                    active_gesture="tracking",
                    status="tracking",
                )
        return events

    def _handle_missing_hand(self, timestamp_ms: int) -> GestureEvents:
        last_seen = self._last_seen_ms
        if last_seen is None:
            self.cursor_mapper.reset()
            return GestureEvents(paused=self.paused, active_gesture="none", status="searching")
        if self._drag_active:
            self._drag_active = False
            self._left = _PinchState()
            self._click_anchor_position = None
            self._release_clutch()
            return GestureEvents(
                drag_end=True,
                paused=self.paused,
                tracking_lost=True,
                active_gesture="tracking_lost",
                status="tracking_lost_drag_released",
            )
        if timestamp_ms - last_seen < self.config.tracking_loss_grace_ms:
            return GestureEvents(paused=self.paused, active_gesture="none", status="searching")
        if (
            timestamp_ms - last_seen >= self.config.tracking_loss_grace_ms
            and not self._tracking_lost_reported
        ):
            self._reset_gesture_state()
            self._tracking_lost_reported = True
            self.cursor_mapper.reset()
            self._suppress_next_pointer_move = True
            return GestureEvents(
                paused=self.paused,
                tracking_lost=True,
                active_gesture="tracking_lost",
                status="tracking_lost",
            )
        return GestureEvents(paused=self.paused, active_gesture="none", status="searching")

    def toggle_pause(self) -> GestureEvents:
        self.paused = not self.paused
        drag_end = self._drag_active
        self._reset_gesture_state()
        return GestureEvents(
            drag_end=drag_end,
            paused_changed=True,
            paused=self.paused,
            active_gesture="paused" if self.paused else "none",
            status="paused" if self.paused else "tracking",
        )

    def rebase_to_current_hand(self, frame: TrackingFrame) -> None:
        """Keep the current cursor target stable after live cursor setting changes."""
        hand = frame.hand
        target = self.cursor_mapper.current
        if hand is None or target is None or not _has_required_points(hand):
            self._suppress_next_pointer_move = True
            return
        self.cursor_mapper.rebase(_pointer_reference(hand), target)
        self._suppress_next_pointer_move = False

    def _map_pointer(self, pointer_reference: Landmark) -> CursorPosition | None:
        mapped = self.cursor_mapper.map(pointer_reference)
        if self._suppress_next_pointer_move:
            self._suppress_next_pointer_move = False
            return None
        return mapped

    def _process_left(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        pointer_reference: Landmark,
        active_now: bool,
    ) -> GestureEvents:
        if active_now and not self._left.active:
            self._click_anchor_position = (
                self._clutch_anchor_position
                or self.cursor_mapper.current
                or self.cursor_mapper.map(pointer_reference)
            )
            self._left = _PinchState(active=True, started_ms=timestamp_ms)
            return replace(
                events,
                move=self._click_anchor_position,
                active_gesture="click_candidate",
                status="click_candidate",
            )

        if active_now and self._left.active:
            started = self._left.started_ms if self._left.started_ms is not None else timestamp_ms
            anchor = self._click_anchor_position
            projected = self.cursor_mapper.project(pointer_reference)
            drag_distance = _position_distance(anchor, projected) if anchor is not None else 0.0
            if (
                not self._drag_active
                and timestamp_ms - started >= self.config.drag_hold_ms
                and drag_distance
                >= max(self.config.drag_start_movement_px, self.config.click_freeze_radius_px)
            ):
                self._drag_active = True
                self._left.consumed = True
                move = self.cursor_mapper.map(pointer_reference)
                return replace(
                    events,
                    move=move,
                    drag_start=True,
                    active_gesture="dragging",
                    status="dragging",
                )
            return replace(
                events,
                move=(
                    self.cursor_mapper.map(pointer_reference)
                    if self._drag_active
                    else _freeze_anchor(anchor, events.move)
                ),
                active_gesture="dragging" if self._drag_active else "click_candidate",
                status="dragging" if self._drag_active else events.status,
            )

        if not active_now and self._left.active:
            started = self._left.started_ms if self._left.started_ms is not None else timestamp_ms
            held_ms = timestamp_ms - started
            was_dragging = self._drag_active
            anchor = self._click_anchor_position
            self._left = _PinchState()
            self._click_anchor_position = None
            if was_dragging:
                self._drag_active = False
                return replace(events, drag_end=True, status="tracking")
            if (
                held_ms >= self.config.min_click_hold_ms
                and timestamp_ms - self._last_left_click_ms >= self.config.click_cooldown_ms
            ):
                self._last_left_click_ms = timestamp_ms
                return replace(
                    events,
                    move=_freeze_anchor(anchor, events.move),
                    left_click=True,
                    active_gesture="left_click",
                    status="left_click",
                )

        return events

    def _process_right(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        active_now: bool,
    ) -> GestureEvents:
        if active_now and not self._right.active:
            self._right = _PinchState(active=True, started_ms=timestamp_ms)
            return replace(events, active_gesture="right_pinch")

        if not active_now and self._right.active:
            started = self._right.started_ms if self._right.started_ms is not None else timestamp_ms
            held_ms = timestamp_ms - started
            self._right = _PinchState()
            if (
                held_ms >= self.config.min_click_hold_ms
                and timestamp_ms - self._last_right_click_ms >= self.config.click_cooldown_ms
            ):
                if (
                    held_ms >= self.config.shortcut_action_hold_ms
                    and timestamp_ms - self._last_middle_click_ms >= self.config.click_cooldown_ms
                ):
                    self._last_middle_click_ms = timestamp_ms
                    return replace(
                        events,
                        middle_click=True,
                        active_gesture="middle_click",
                        status="middle_click",
                    )
                self._last_right_click_ms = timestamp_ms
                return replace(
                    events,
                    right_click=True,
                    active_gesture="right_click",
                    status="right_click",
                )

        return events

    def _process_scroll(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        reference: Landmark,
        active_now: bool,
    ) -> GestureEvents:
        if active_now and not self._scroll.active:
            self._scroll = _ScrollState(active=True, anchor_y=reference.y)
            return replace(
                events,
                move=None,
                active_gesture="scrolling",
                status="scrolling",
            )

        if active_now and self._scroll.active:
            anchor = self._scroll.anchor_y
            if anchor is None:
                self._scroll.anchor_y = reference.y
                return replace(
                    events,
                    move=None,
                    active_gesture="scrolling",
                    status="scrolling",
                )
            delta = (reference.y - anchor) * self.config.scroll_sensitivity
            # Apply dead zone: skip tiny jitter without advancing the anchor
            if abs(reference.y - anchor) < self.config.scroll_dead_zone:
                return replace(events, move=None, active_gesture="scrolling", status="scrolling")
            self._scroll.anchor_y = reference.y
            self._scroll.accumulated_y += delta
            steps = int(self._scroll.accumulated_y / self.config.scroll_activation_y_delta)
            if steps and timestamp_ms - self._scroll.last_emit_ms >= self.config.scroll_cooldown_ms:
                self._scroll.accumulated_y -= steps * self.config.scroll_activation_y_delta
                self._scroll.last_emit_ms = timestamp_ms
                direction = 1 if self.config.scroll_natural_direction else -1
                return replace(
                    events,
                    move=None,
                    scroll=direction * steps * self.config.scroll_units_per_step,
                    active_gesture="scrolling",
                    status="scrolling",
                )
            return replace(
                events,
                move=None,
                active_gesture="scrolling",
                status="scrolling",
            )
        if not active_now and self._scroll.active:
            self._scroll = _ScrollState()

        return events

    def _update_pause(self, hand: HandLandmarks, timestamp_ms: int) -> tuple[bool, bool, bool]:
        if not self.config.pause_gesture_enabled:
            self._pause = _PinchState()
            return False, False, False

        pause_distance = _distance(hand, THUMB_TIP, PINKY_TIP)
        pause_now = _hysteresis(
            self._pause.active,
            pause_distance,
            self.config.pause_pinch_threshold,
            self.config.pause_pinch_release_threshold,
        )

        if pause_now and not self._pause.active:
            self._pause = _PinchState(active=True, started_ms=timestamp_ms)
            return False, True, False

        if pause_now and self._pause.active and not self._pause.consumed:
            started = self._pause.started_ms if self._pause.started_ms is not None else timestamp_ms
            if timestamp_ms - started >= self.config.pause_hold_ms:
                events = self.toggle_pause()
                self._pause = _PinchState(active=True, started_ms=started, consumed=True)
                return True, True, events.drag_end

        if not pause_now and self._pause.active:
            self._pause = _PinchState()

        return False, pause_now, False

    def _resolve_conflicts(
        self,
        left_now: bool,
        right_now: bool,
        scroll_now: bool,
    ) -> tuple[bool, bool, bool, bool]:
        active_count = sum((left_now, right_now, scroll_now))
        if active_count <= 1:
            return left_now, right_now, scroll_now, False
        if self._left.active and left_now:
            return True, False, False, False
        if self._right.active and right_now:
            return False, True, False, False
        if self._scroll.active and scroll_now:
            return False, False, True, False
        self._left = _PinchState()
        self._right = _PinchState()
        self._scroll = _ScrollState()
        self._click_anchor_position = None
        return False, False, False, True

    def _reset_gesture_state(self) -> None:
        self._left = _PinchState()
        self._right = _PinchState()
        self._scroll = _ScrollState()
        self._pause = _PinchState()
        self._drag_active = False
        self._click_anchor_position = None
        self._release_clutch()

    def _resolve_clutch(
        self, pose: HandPose, pointer_reference: Landmark, hand: HandLandmarks
    ) -> bool:
        if not pose.confident:
            return self._clutch_active
        if self.config.use_thumb_angle_activation:
            angle = thumb_index_angle_deg(hand.landmarks)
            if angle is None:
                return self._clutch_active
            # pointer_active = angle in range → clutch = NOT pointer_active
            pointer_was_active = not self._clutch_active
            pointer_active = _thumb_angle_in_range(
                angle,
                self.config.thumb_angle_target_deg,
                self.config.thumb_angle_tolerance_deg,
                self.config.thumb_angle_hysteresis_deg,
                pointer_was_active,
            )
            clutch_now = not pointer_active
        else:
            clutch_now = not pose.thumb_open if self._clutch_active else pose.thumb_closed
        if clutch_now and not self._clutch_active:
            self._clutch_anchor_position = self.cursor_mapper.current or self.cursor_mapper.map(
                pointer_reference
            )
            self._clutch_active = True
        return clutch_now

    def _release_clutch(self, pointer_reference: Landmark | None = None) -> None:
        if self._clutch_anchor_position is not None:
            if pointer_reference is None:
                self.cursor_mapper.set_current(self._clutch_anchor_position)
            else:
                self.cursor_mapper.rebase(pointer_reference, self._clutch_anchor_position)
        self._clutch_active = False
        self._clutch_anchor_position = None


def _distance(hand: HandLandmarks, a: int, b: int) -> float:
    first = hand.landmarks[a]
    second = hand.landmarks[b]
    return hypot(first.x - second.x, first.y - second.y)


def _pointer_reference(hand: HandLandmarks) -> Landmark:
    return stable_pointer_anchor(hand) or hand.landmarks[INDEX_TIP]


def _position_distance(first: CursorPosition | None, second: CursorPosition | None) -> float:
    if first is None or second is None:
        return 0.0
    return hypot(first.x - second.x, first.y - second.y)


def _freeze_anchor(
    anchor: CursorPosition | None, fallback: CursorPosition | None
) -> CursorPosition | None:
    return anchor if anchor is not None else fallback


def _thumb_angle_in_range(
    angle_deg: float,
    target: float,
    tolerance: float,
    hysteresis: float,
    pointer_was_active: bool,
) -> bool:
    """Return True if thumb angle keeps (or enters) the pointer-active state.

    *pointer_was_active* is True when the pointer was moving on the previous
    frame (i.e. the clutch was NOT engaged).  When already active, the range
    is widened by *hysteresis* on both sides to prevent jitter at the edge.
    When inactive, the angle must enter the strict [target±tolerance] window.
    """
    if pointer_was_active:
        low = target - tolerance - hysteresis
        high = target + tolerance + hysteresis
    else:
        low = target - tolerance
        high = target + tolerance
    # Small epsilon guards against floating-point representation errors at the
    # boundary (e.g. 80.000 is represented as 79.999999999...)
    _EPS = 1e-9
    return (low - _EPS) <= angle_deg <= (high + _EPS)


def _hysteresis(active: bool, distance: float, threshold: float, release: float) -> bool:
    return distance <= (release if active else threshold)


def _finger_bent(active: bool, flexion: float, config: GestureConfig) -> bool:
    return flexion < (config.finger_extend_threshold if active else config.finger_bend_threshold)


def _has_required_points(hand: HandLandmarks) -> bool:
    return (
        hand.confidence > 0
        and len(hand.landmarks) >= 21
        and all(0.0 <= point.visibility <= 1.0 for point in hand.landmarks)
    )


# ---------------------------------------------------------------------------
# Data-driven gesture binding matcher
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _BindingRunState:
    """Per-binding runtime state tracked across frames."""

    finger_active: bool = False
    movement_met: bool = False
    movement_anchor: tuple[float, float] | None = None
    started_ms: int | None = None
    last_triggered_ms: int = -1_000_000
    consumed: bool = False  # prevents re-firing enter/release within the same activation


class GestureBindingMatcher:
    """Evaluates data-driven :class:`~airpilot.config.GestureBinding` objects.

    Call :meth:`process` once per frame *after* :class:`GestureEngine` and
    :class:`~airpilot.actions.ActionRouter`.  If no other action has been
    dispatched this frame and a binding's conditions are met, the binding's
    ``action_id`` is written into the returned :class:`GestureEvents`.

    Conflict detection is available via :meth:`conflicts`.
    """

    def __init__(
        self,
        bindings: list[GestureBinding],
        gesture_config: GestureConfig,
    ) -> None:
        self._bindings = bindings
        self._config = gesture_config
        self._states: dict[str, _BindingRunState] = {b.id: _BindingRunState() for b in bindings}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, frame: TrackingFrame, events: GestureEvents) -> GestureEvents:
        """Update internal state and maybe fire a binding action."""
        can_fire = events.action_id is None and not events.paused
        return self._tick(frame, events, can_fire=can_fire)

    def conflicts(self) -> list[str]:
        """Return human-readable conflict descriptions (empty list = clean)."""
        from airpilot.config import _gesture_bindings_conflict

        enabled = [b for b in self._bindings if b.enabled]
        result: list[str] = []
        for i, a in enumerate(enabled):
            for other in enabled[i + 1 :]:
                if _gesture_bindings_conflict(a, other):
                    result.append(
                        f"Binding {a.id!r} conflicts with {other.id!r}: "
                        "identical match conditions — only one will fire."
                    )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _tick(
        self,
        frame: TrackingFrame,
        events: GestureEvents,
        *,
        can_fire: bool,
    ) -> GestureEvents:
        for binding in self._bindings:
            if not binding.enabled:
                continue
            state = self._states.setdefault(binding.id, _BindingRunState())
            hand = _select_hand(binding.hand, frame)

            if hand is None or not _has_required_points(hand):
                events = self._handle_no_hand(binding, state, frame.timestamp_ms, events, can_fire)
                if events.action_id is not None:
                    can_fire = False
                continue

            pose = estimate_hand_pose(
                hand,
                thumb_close_threshold=self._config.thumb_close_threshold,
                thumb_open_threshold=self._config.thumb_open_threshold,
                finger_bend_threshold=self._config.finger_bend_threshold,
                finger_extend_threshold=self._config.finger_extend_threshold,
            )

            wrist_x = hand.landmarks[WRIST].x
            wrist_y = hand.landmarks[WRIST].y
            fingers_ok = _binding_fingers_match(binding, pose)

            if fingers_ok:
                if not state.finger_active:
                    state.finger_active = True
                    state.movement_anchor = (wrist_x, wrist_y)
                    state.started_ms = frame.timestamp_ms
                    state.movement_met = False
                    state.consumed = False

                prev_movement = state.movement_met
                movement_ok = _binding_movement_met(binding, state, wrist_x, wrist_y)
                state.movement_met = movement_ok

                # After detecting movement, reset anchor to allow retriggering
                # on continuous motion (only for enter/hold_repeat, not release)
                if movement_ok and binding.movement != "none" and binding.trigger != "release":
                    state.movement_anchor = (wrist_x, wrist_y)

                ts = frame.timestamp_ms
                if can_fire:
                    fired = self._maybe_fire(binding, state, ts, prev_movement, movement_ok)
                    if fired:
                        can_fire = False
                        events = replace(events, action_id=binding.action_id or None)
            else:
                events = self._handle_release(binding, state, frame.timestamp_ms, events, can_fire)
                if events.action_id is not None:
                    can_fire = False
                state.finger_active = False
                state.movement_met = False
                state.movement_anchor = None
                state.started_ms = None
                state.consumed = False

        return events

    def _handle_no_hand(
        self,
        binding: GestureBinding,
        state: _BindingRunState,
        ts: int,
        events: GestureEvents,
        can_fire: bool,
    ) -> GestureEvents:
        if state.finger_active:
            # Treat tracking loss as a release
            events = self._handle_release(binding, state, ts, events, can_fire)
            state.finger_active = False
            state.movement_met = False
            state.movement_anchor = None
            state.started_ms = None
            state.consumed = False
        return events

    def _handle_release(
        self,
        binding: GestureBinding,
        state: _BindingRunState,
        ts: int,
        events: GestureEvents,
        can_fire: bool,
    ) -> GestureEvents:
        if (
            can_fire
            and binding.trigger == "release"
            and state.finger_active
            and state.movement_met
            and not state.consumed
            and ts - state.last_triggered_ms >= binding.cooldown_ms
        ):
            state.last_triggered_ms = ts
            state.consumed = True
            return replace(events, action_id=binding.action_id or None)
        return events

    def _maybe_fire(
        self,
        binding: GestureBinding,
        state: _BindingRunState,
        ts: int,
        prev_movement: bool,
        movement_ok: bool,
    ) -> bool:
        cooldown_ok = ts - state.last_triggered_ms >= binding.cooldown_ms
        if binding.trigger == "enter":
            if movement_ok and not prev_movement and not state.consumed and cooldown_ok:
                state.last_triggered_ms = ts
                state.consumed = True
                return True
        elif binding.trigger == "hold_repeat":
            started = state.started_ms if state.started_ms is not None else ts
            if movement_ok and cooldown_ok and ts - started >= binding.hold_ms:
                state.last_triggered_ms = ts
                return True
        return False


# ---------------------------------------------------------------------------
# GestureBindingMatcher private helpers
# ---------------------------------------------------------------------------


def _select_hand(hand_sel: str, frame: TrackingFrame) -> HandLandmarks | None:
    if hand_sel == "control":
        return frame.control_hand
    if hand_sel == "secondary":
        return frame.secondary_hand
    if hand_sel == "either":
        return frame.control_hand
    if hand_sel == "left":
        for h in frame.hands:
            if h.handedness == Handedness.LEFT:
                return h
        return None
    if hand_sel == "right":
        for h in frame.hands:
            if h.handedness == Handedness.RIGHT:
                return h
        return None
    return frame.control_hand


def _binding_fingers_match(binding: GestureBinding, pose: HandPose) -> bool:
    if not pose.confident:
        return False
    return (
        _fstate_matches(binding.thumb, pose.thumb_closed, pose.thumb_open)
        and _fstate_matches(binding.index, pose.index.bent, pose.index.extended)
        and _fstate_matches(binding.middle, pose.middle.bent, pose.middle.extended)
        and _fstate_matches(binding.ring, pose.ring.bent, pose.ring.extended)
        and _fstate_matches(binding.pinky, pose.pinky.bent, pose.pinky.extended)
    )


def _fstate_matches(state: str, bent: bool, extended: bool) -> bool:
    if state == "any":
        return True
    if state == "folded":
        return bent
    if state == "extended":
        return extended
    return True


def _binding_movement_met(
    binding: GestureBinding,
    state: _BindingRunState,
    x: float,
    y: float,
) -> bool:
    if binding.movement == "none":
        return True
    anchor = state.movement_anchor
    if anchor is None:
        return False
    dx = x - anchor[0]
    dy = y - anchor[1]
    thresh = max(binding.threshold * binding.sensitivity, 1e-6)
    if binding.movement == "right":
        return dx > thresh
    if binding.movement == "left":
        return dx < -thresh
    if binding.movement == "down":
        return dy > thresh
    if binding.movement == "up":
        return dy < -thresh
    return False
