from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import hypot

from airpilot.config import GestureConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.types import GestureEvents, HandLandmarks, Landmark, TrackingFrame

WRIST = 0
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
RING_TIP = 16
PINKY_TIP = 20


@dataclass(slots=True)
class _PinchState:
    active: bool = False
    started_ms: int | None = None
    consumed: bool = False


@dataclass(slots=True)
class GestureEngine:
    config: GestureConfig
    cursor_mapper: CursorMapper
    paused: bool = False
    _left: _PinchState = field(default_factory=_PinchState)
    _right: _PinchState = field(default_factory=_PinchState)
    _scroll: _PinchState = field(default_factory=_PinchState)
    _pause: _PinchState = field(default_factory=_PinchState)
    _drag_active: bool = False
    _last_left_click_ms: int = -1_000_000
    _last_right_click_ms: int = -1_000_000
    _last_seen_ms: int | None = None
    _tracking_lost_reported: bool = False
    _scroll_anchor_y: float | None = None

    def process(self, frame: TrackingFrame) -> GestureEvents:
        hand = frame.hand
        if hand is None or not _has_required_points(hand):
            return self._handle_missing_hand(frame.timestamp_ms)

        self._last_seen_ms = frame.timestamp_ms
        self._tracking_lost_reported = False

        pause_changed = self._update_pause(hand, frame.timestamp_ms)
        if self.paused:
            return GestureEvents(
                paused_changed=pause_changed,
                paused=self.paused,
                status="paused",
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

        events = GestureEvents(
            move=None if scroll_now else self.cursor_mapper.map(hand.landmarks[INDEX_TIP]),
            paused_changed=pause_changed,
            paused=self.paused,
            status="tracking",
        )

        events = self._process_left(events, frame.timestamp_ms, left_now)
        events = self._process_right(events, frame.timestamp_ms, right_now)
        events = self._process_scroll(events, hand.landmarks[RING_TIP], scroll_now)
        return events

    def _handle_missing_hand(self, timestamp_ms: int) -> GestureEvents:
        last_seen = self._last_seen_ms
        if last_seen is None:
            self.cursor_mapper.reset()
            return GestureEvents(paused=self.paused, status="searching")
        if self._drag_active:
            self._drag_active = False
            self._left = _PinchState()
            return GestureEvents(
                drag_end=True,
                paused=self.paused,
                tracking_lost=True,
                status="tracking_lost_drag_released",
            )
        self._left = _PinchState()
        self._right = _PinchState()
        self._scroll = _PinchState()
        self._pause = _PinchState()
        self._scroll_anchor_y = None
        if (
            timestamp_ms - last_seen >= self.config.tracking_loss_grace_ms
            and not self._tracking_lost_reported
        ):
            self._tracking_lost_reported = True
            self.cursor_mapper.reset()
            return GestureEvents(
                paused=self.paused,
                tracking_lost=True,
                status="tracking_lost",
            )
        return GestureEvents(paused=self.paused, status="searching")

    def _process_left(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        active_now: bool,
    ) -> GestureEvents:
        if active_now and not self._left.active:
            self._left = _PinchState(active=True, started_ms=timestamp_ms)
            return events

        if active_now and self._left.active:
            started = self._left.started_ms if self._left.started_ms is not None else timestamp_ms
            if not self._drag_active and timestamp_ms - started >= self.config.drag_hold_ms:
                self._drag_active = True
                self._left.consumed = True
                return replace(events, drag_start=True, status="dragging")
            return replace(events, status="dragging" if self._drag_active else events.status)

        if not active_now and self._left.active:
            started = self._left.started_ms if self._left.started_ms is not None else timestamp_ms
            held_ms = timestamp_ms - started
            was_dragging = self._drag_active
            self._left = _PinchState()
            if was_dragging:
                self._drag_active = False
                return replace(events, drag_end=True, status="tracking")
            if (
                held_ms >= self.config.min_click_hold_ms
                and held_ms < self.config.drag_hold_ms
                and timestamp_ms - self._last_left_click_ms >= self.config.click_cooldown_ms
            ):
                self._last_left_click_ms = timestamp_ms
                return replace(events, left_click=True, status="left_click")

        return events

    def _process_right(
        self,
        events: GestureEvents,
        timestamp_ms: int,
        active_now: bool,
    ) -> GestureEvents:
        if active_now and not self._right.active:
            self._right = _PinchState(active=True, started_ms=timestamp_ms)
            return events

        if not active_now and self._right.active:
            started = self._right.started_ms if self._right.started_ms is not None else timestamp_ms
            held_ms = timestamp_ms - started
            self._right = _PinchState()
            if (
                held_ms >= self.config.min_click_hold_ms
                and timestamp_ms - self._last_right_click_ms >= self.config.click_cooldown_ms
            ):
                self._last_right_click_ms = timestamp_ms
                return replace(events, right_click=True, status="right_click")

        return events

    def _process_scroll(
        self,
        events: GestureEvents,
        ring_tip: Landmark,
        active_now: bool,
    ) -> GestureEvents:
        if active_now and not self._scroll.active:
            self._scroll = _PinchState(active=True)
            self._scroll_anchor_y = ring_tip.y
            return replace(events, move=None, status="scrolling")

        if active_now and self._scroll.active:
            anchor = self._scroll_anchor_y
            if anchor is None:
                self._scroll_anchor_y = ring_tip.y
                return replace(events, move=None, status="scrolling")
            delta = ring_tip.y - anchor
            steps = int(delta / self.config.scroll_activation_y_delta)
            if steps:
                self._scroll_anchor_y = ring_tip.y
                return replace(
                    events,
                    move=None,
                    scroll=-steps * self.config.scroll_units_per_step,
                    status="scrolling",
                )
            return replace(events, move=None, status="scrolling")

        if not active_now and self._scroll.active:
            self._scroll = _PinchState()
            self._scroll_anchor_y = None

        return events

    def _update_pause(self, hand: HandLandmarks, timestamp_ms: int) -> bool:
        pause_distance = _distance(hand, THUMB_TIP, PINKY_TIP)
        pause_now = _hysteresis(
            self._pause.active,
            pause_distance,
            self.config.pause_pinch_threshold,
            self.config.pause_pinch_release_threshold,
        )

        if pause_now and not self._pause.active:
            self._pause = _PinchState(active=True, started_ms=timestamp_ms)
            return False

        if pause_now and self._pause.active and not self._pause.consumed:
            started = self._pause.started_ms if self._pause.started_ms is not None else timestamp_ms
            if timestamp_ms - started >= self.config.pause_hold_ms:
                self.paused = not self.paused
                self._pause.consumed = True
                self._left = _PinchState()
                self._right = _PinchState()
                self._scroll = _PinchState()
                self._drag_active = False
                self._scroll_anchor_y = None
                return True

        if not pause_now and self._pause.active:
            self._pause = _PinchState()

        return False


def _distance(hand: HandLandmarks, a: int, b: int) -> float:
    first = hand.landmarks[a]
    second = hand.landmarks[b]
    return hypot(first.x - second.x, first.y - second.y)


def _hysteresis(active: bool, distance: float, threshold: float, release: float) -> bool:
    return distance <= (release if active else threshold)


def _has_required_points(hand: HandLandmarks) -> bool:
    return (
        hand.confidence > 0
        and len(hand.landmarks) >= 21
        and all(0.0 <= point.visibility <= 1.0 for point in hand.landmarks)
    )
