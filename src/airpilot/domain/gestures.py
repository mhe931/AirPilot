from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import hypot

from airpilot.config import GestureConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.types import (
    CursorPosition,
    GestureEvents,
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

        left_distance = _distance(hand, THUMB_TIP, INDEX_TIP)
        right_distance = _distance(hand, THUMB_TIP, MIDDLE_TIP)
        scroll_distance = _distance(hand, THUMB_TIP, RING_TIP)

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
        if not scroll_now and not left_now:
            move = self.cursor_mapper.map(hand.landmarks[INDEX_TIP])
        events = GestureEvents(
            move=move,
            paused_changed=pause_changed,
            paused=self.paused,
            active_gesture="conflict" if conflict else "tracking",
            status="gesture_conflict" if conflict else "tracking",
        )
        if conflict:
            return events

        events = self._process_left(events, frame.timestamp_ms, hand.landmarks[INDEX_TIP], left_now)
        events = self._process_right(events, frame.timestamp_ms, right_now)
        events = self._process_scroll(
            events,
            frame.timestamp_ms,
            hand.landmarks[WRIST],
            scroll_now,
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

    def _process_left(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        index_tip: Landmark,
        active_now: bool,
    ) -> GestureEvents:
        if active_now and not self._left.active:
            self._click_anchor_position = self.cursor_mapper.current or self.cursor_mapper.map(
                index_tip
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
            projected = self.cursor_mapper.project(index_tip)
            drag_distance = _position_distance(anchor, projected) if anchor is not None else 0.0
            if (
                not self._drag_active
                and timestamp_ms - started >= self.config.drag_hold_ms
                and drag_distance
                >= max(self.config.drag_start_movement_px, self.config.click_freeze_radius_px)
            ):
                self._drag_active = True
                self._left.consumed = True
                move = self.cursor_mapper.map(index_tip)
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
                    self.cursor_mapper.map(index_tip)
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
            self._scroll.anchor_y = reference.y
            self._scroll.accumulated_y += delta
            steps = int(self._scroll.accumulated_y / self.config.scroll_activation_y_delta)
            if steps and timestamp_ms - self._scroll.last_emit_ms >= self.config.scroll_cooldown_ms:
                self._scroll.accumulated_y -= steps * self.config.scroll_activation_y_delta
                self._scroll.last_emit_ms = timestamp_ms
                return replace(
                    events,
                    move=None,
                    scroll=-steps * self.config.scroll_units_per_step,
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


def _distance(hand: HandLandmarks, a: int, b: int) -> float:
    first = hand.landmarks[a]
    second = hand.landmarks[b]
    return hypot(first.x - second.x, first.y - second.y)


def _position_distance(first: CursorPosition | None, second: CursorPosition | None) -> float:
    if first is None or second is None:
        return 0.0
    return hypot(first.x - second.x, first.y - second.y)


def _freeze_anchor(
    anchor: CursorPosition | None, fallback: CursorPosition | None
) -> CursorPosition | None:
    return anchor if anchor is not None else fallback


def _hysteresis(active: bool, distance: float, threshold: float, release: float) -> bool:
    return distance <= (release if active else threshold)


def _has_required_points(hand: HandLandmarks) -> bool:
    return (
        hand.confidence > 0
        and len(hand.landmarks) >= 21
        and all(0.0 <= point.visibility <= 1.0 for point in hand.landmarks)
    )
