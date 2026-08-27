from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Protocol

import cv2
import numpy as np
import pyautogui
from cv2.typing import MatLike

from airpilot.actions import (
    ActionRouter,
    action_help_lines,
    dispatch_action,
    validate_action_config,
)
from airpilot.camera import OpenCVCamera, list_cameras
from airpilot.config import (
    AppConfig,
    default_config_path,
    load_config,
    read_config_schema_version,
    save_config,
)
from airpilot.cursor_feedback import CursorFeedbackController, create_cursor_feedback
from airpilot.display import create_display_provider
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureEngine
from airpilot.domain.types import GestureEvents, TrackingFrame
from airpilot.input import MouseController, PyAutoGuiMouseController
from airpilot.safety import MouseSafetyGate
from airpilot.tracking import HandDrawingError, MediaPipeHandTracker


@dataclass(slots=True)
class TrackingStats:
    started_at: float = field(default_factory=perf_counter)
    frames: int = 0
    hand_frames: int = 0
    tracking_lost_events: int = 0
    first_hand_ms: int | None = None
    last_timestamp_ms: int | None = None
    max_frame_gap_ms: int = 0
    frame_width: int = 0
    frame_height: int = 0

    def observe(self, frame: TrackingFrame, events: GestureEvents) -> None:
        self.frames += 1
        self.frame_width = frame.width
        self.frame_height = frame.height
        if self.last_timestamp_ms is not None:
            gap_ms = max(frame.timestamp_ms - self.last_timestamp_ms, 0)
            self.max_frame_gap_ms = max(self.max_frame_gap_ms, gap_ms)
        self.last_timestamp_ms = frame.timestamp_ms
        if frame.hand is not None:
            self.hand_frames += 1
            if self.first_hand_ms is None:
                self.first_hand_ms = frame.timestamp_ms
        if events.tracking_lost:
            self.tracking_lost_events += 1

    @property
    def elapsed_seconds(self) -> float:
        return max(perf_counter() - self.started_at, 0.001)

    @property
    def fps(self) -> float:
        return self.frames / self.elapsed_seconds

    @property
    def hand_acquisition_rate(self) -> float:
        if self.frames == 0:
            return 0.0
        return self.hand_frames / self.frames

    def summary(self, *, camera_backend: str = "unknown") -> dict[str, int | float | bool | str]:
        return {
            "camera_backend": camera_backend,
            "frames": self.frames,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "hand_frames": self.hand_frames,
            "hand_acquisition_rate": round(self.hand_acquisition_rate, 3),
            "fps": round(self.fps, 1),
            "tracking_lost_events": self.tracking_lost_events,
            "max_frame_gap_ms": self.max_frame_gap_ms,
            "hand_observed": self.hand_frames > 0,
        }


class PauseController(Protocol):
    def toggle_pause(self) -> GestureEvents: ...


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AirPilot Windows gesture mouse")
    parser.add_argument("--camera", type=int, default=None, help="camera index")
    parser.add_argument("--list-cameras", action="store_true", help="list available cameras")
    parser.add_argument(
        "--no-mouse",
        action="store_true",
        help="run tracker UI without moving the mouse",
    )
    parser.add_argument(
        "--armed",
        action="store_true",
        help="start real mouse control armed instead of safe",
    )
    parser.add_argument(
        "--diagnose-seconds",
        type=float,
        default=None,
        help="run camera/tracker diagnostics for N seconds without mouse control",
    )
    parser.add_argument(
        "--show-preview",
        action="store_true",
        help="show preview window during diagnostics",
    )
    parser.add_argument("--config", type=str, default=None, help="config file path")
    args = parser.parse_args(argv)

    config_path = None if args.config is None else Path(args.config)
    persisted_path = default_config_path() if config_path is None else config_path
    stored_schema_version = read_config_schema_version(persisted_path)
    config = load_config(config_path)
    validate_action_config(config.actions)
    if stored_schema_version != config.schema_version:
        save_config(config, config_path)

    if args.camera is not None:
        config.runtime.camera_index = args.camera
    if args.no_mouse:
        config.runtime.enable_real_mouse = False
    if args.armed:
        config.runtime.start_armed = True

    if args.list_cameras:
        for device in list_cameras(config.runtime.max_camera_index):
            print(f"{device.index}: {device.name} ({device.backend})")
        return 0

    if args.diagnose_seconds is not None:
        config.runtime.enable_real_mouse = False
        return run(
            config,
            diagnose_seconds=args.diagnose_seconds,
            show_preview=args.show_preview,
            mouse_output_locked=True,
        )

    return run(config, mouse_output_locked=args.no_mouse)


def run(
    config: AppConfig,
    diagnose_seconds: float | None = None,
    *,
    show_preview: bool = True,
    mouse_output_locked: bool = False,
) -> int:
    camera: OpenCVCamera | None = None
    tracker: MediaPipeHandTracker | None = None
    cursor_feedback: CursorFeedbackController | None = None
    safety: MouseSafetyGate | None = None
    mouse: MouseController | None = None
    stats = TrackingStats()
    drawing_error: str | None = None
    operator_notice: str | None = None

    try:
        camera = OpenCVCamera(
            config.runtime.camera_index,
            read_failures_before_error=config.runtime.camera_read_failures_before_error,
            reconnect_attempts=config.runtime.camera_reconnect_attempts,
            reconnect_delay_ms=config.runtime.camera_reconnect_delay_ms,
        )
        tracker = MediaPipeHandTracker(
            min_detection_confidence=config.runtime.tracker_detection_confidence,
            min_tracking_confidence=config.runtime.tracker_tracking_confidence,
            input_is_mirrored=config.runtime.flip_camera_x,
        )
        desktop = create_display_provider().virtual_desktop()
        config.cursor.screen_left = desktop.left
        config.cursor.screen_top = desktop.top
        config.cursor.screen_width = desktop.width
        config.cursor.screen_height = desktop.height
        engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
        action_router = ActionRouter(config.actions, config.gestures)
        help_window = HelpWindow(visible=config.runtime.show_gesture_help)
        mouse = PyAutoGuiMouseController(
            emergency_corner_failsafe=config.runtime.emergency_corner_failsafe,
        )
        cursor_feedback = create_cursor_feedback()
        safety = MouseSafetyGate(
            armed=(
                config.runtime.enable_real_mouse
                and not mouse_output_locked
                and config.runtime.start_armed
            ),
        )
        for camera_frame in camera.frames():
            image = _prepare_camera_image(camera_frame.image, config)
            frame = tracker.track(image, camera_frame.timestamp_ms)
            events = engine.process(frame)
            events = action_router.process(frame, events)
            if events.action_id == "ui.toggle_help":
                operator_notice = _dispatch_ui_action(events.action_id, help_window)
            mouse_output_enabled = config.runtime.enable_real_mouse and not mouse_output_locked
            if mouse_output_enabled:
                safety.apply(mouse, events)
                if (
                    safety.armed
                    and events.action_id is not None
                    and not events.action_id.startswith("ui.")
                ):
                    action_label = dispatch_action(config.actions, mouse, events.action_id)
                    if action_label is not None:
                        operator_notice = f"ACTION: {action_label}"
            cursor_feedback.set_control_active(
                mouse_output_enabled
                and safety.armed
                and not events.paused
                and frame.hand is not None
            )
            stats.observe(frame, events)

            if show_preview:
                if config.runtime.draw_landmarks:
                    try:
                        tracker.draw(image, frame.hand)
                    except HandDrawingError as exc:
                        config.runtime.draw_landmarks = False
                        drawing_error = "landmarks disabled"
                        print(
                            f"AirPilot warning: {exc}. Preview landmarks disabled.",
                            file=sys.stderr,
                        )
                        operator_notice = "Preview landmarks disabled"
                _draw_status(
                    image,
                    frame,
                    events,
                    config,
                    armed=safety.armed,
                    fps=stats.fps,
                    drawing_error=drawing_error,
                    operator_notice=operator_notice,
                    mouse_output_locked=mouse_output_locked,
                )
                cv2.imshow("AirPilot", image)
                should_exit, operator_notice = _handle_keypress(
                    cv2.waitKey(1),
                    config=config,
                    engine=engine,
                    safety=safety,
                    mouse=mouse,
                    help_window=help_window,
                    mouse_output_locked=mouse_output_locked,
                )
                if should_exit:
                    break
                help_window.update(config)
            if diagnose_seconds is not None and stats.elapsed_seconds >= diagnose_seconds:
                summary = stats.summary(camera_backend=camera.backend_name)
                summary["camera_reconnects"] = camera.reconnect_count
                print(json.dumps(summary, sort_keys=True))
                break
            if mouse.emergency_stop_requested():
                break
    except pyautogui.FailSafeException:
        print("AirPilot stopped by PyAutoGUI failsafe corner.", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"AirPilot runtime error: {exc}", file=sys.stderr)
        return 1
    finally:
        if camera is not None:
            camera.close()
        if tracker is not None:
            tracker.close()
        if safety is not None and mouse is not None:
            safety.disarm(mouse)
        if cursor_feedback is not None:
            cursor_feedback.restore()
        if "help_window" in locals():
            help_window.close()
        cv2.destroyAllWindows()
    return 0


def status_lines(
    frame: TrackingFrame,
    events: GestureEvents,
    config: AppConfig,
    *,
    armed: bool,
    fps: float,
    drawing_error: str | None = None,
    operator_notice: str | None = None,
    mouse_output_locked: bool = False,
) -> list[str]:
    hand = frame.hand
    tracking = "hand" if hand is not None else "searching"
    hand_score = f"{hand.confidence:.2f}" if hand is not None else "--"
    control_hand = hand.handedness.value if hand is not None else "--"
    headline, guidance = _headline_text(
        config=config,
        armed=armed,
        paused=events.paused,
        operator_notice=operator_notice,
        mouse_output_locked=mouse_output_locked,
    )
    controls = _controls_text(config, mouse_output_locked=mouse_output_locked)
    hand_count = len(frame.hands)
    lines = [
        headline,
        guidance,
        (
            f"tracking {tracking} | gesture {events.active_gesture} | "
            f"hands {hand_count} | control {control_hand} | score {hand_score} | {fps:.1f} fps"
        ),
        controls,
    ]
    if events.action_label is not None:
        lines.append(f"action {events.action_label}")
    if drawing_error is not None:
        lines.append(f"preview {drawing_error}")
    return lines


def _draw_status(
    image: MatLike,
    frame: TrackingFrame,
    events: GestureEvents,
    config: AppConfig,
    *,
    armed: bool,
    fps: float,
    drawing_error: str | None = None,
    operator_notice: str | None = None,
    mouse_output_locked: bool = False,
) -> None:
    _draw_calibration_region(image, config)
    lines = status_lines(
        frame,
        events,
        config,
        armed=armed,
        fps=fps,
        drawing_error=drawing_error,
        operator_notice=operator_notice,
        mouse_output_locked=mouse_output_locked,
    )
    layout = _layout_overlay(lines, int(image.shape[1]))
    _draw_banner(
        image,
        layout,
        config=config,
        armed=armed,
        paused=events.paused,
        mouse_output_locked=mouse_output_locked,
    )
    detail_color = (255, 255, 255)
    for line in layout[2:]:
        cv2.putText(
            image,
            line.text,
            (line.x, line.y),
            cv2.FONT_HERSHEY_SIMPLEX,
            line.scale,
            detail_color,
            2,
            cv2.LINE_AA,
        )


def _draw_calibration_region(image: MatLike, config: AppConfig) -> None:
    height = int(image.shape[0])
    width = int(image.shape[1])
    cursor = config.cursor
    x1 = int(width * cursor.camera_min_x)
    y1 = int(height * cursor.camera_min_y)
    x2 = int(width * cursor.camera_max_x)
    y2 = int(height * cursor.camera_max_y)
    cv2.rectangle(image, (x1, y1), (x2, y2), (255, 200, 0), 1)
    cv2.putText(
        image,
        "control region",
        (x1 + 6, max(y1 + 22, 22)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 200, 0),
        1,
        cv2.LINE_AA,
    )


def _prepare_camera_image(image: MatLike, config: AppConfig) -> MatLike:
    if config.runtime.flip_camera_x:
        return cv2.flip(image, 1)
    return image


def _normalized_key(key: int) -> str | None:
    normalized = key & 0xFF
    if normalized == 27:
        return "quit"
    if 32 <= normalized <= 126:
        return chr(normalized).lower()
    return None


def _handle_keypress(
    key: int,
    *,
    config: AppConfig,
    engine: PauseController,
    safety: MouseSafetyGate,
    mouse: MouseController,
    help_window: HelpWindow | None = None,
    mouse_output_locked: bool = False,
) -> tuple[bool, str | None]:
    command = _normalized_key(key)
    if command == "q":
        return True, "Quit requested"
    if command == "p":
        pause_events = engine.toggle_pause()
        if config.runtime.enable_real_mouse and not mouse_output_locked:
            safety.apply(mouse, pause_events)
        return False, "Paused" if pause_events.paused else "Resumed"
    if command == "h":
        return False, _dispatch_ui_action("ui.toggle_help", help_window)
    if command == "a":
        if mouse_output_locked:
            return False, "Mouse output disabled for diagnostics/--no-mouse"
        if not config.runtime.enable_real_mouse:
            config.runtime.enable_real_mouse = True
        if safety.armed:
            safety.disarm(mouse)
            return False, "Mouse control disabled"
        safety.toggle()
        return False, "Mouse control enabled"
    if command == "quit":
        return True, "Quit requested"
    return False, None


def _dispatch_ui_action(action_id: str, help_window: HelpWindow | None) -> str | None:
    if action_id != "ui.toggle_help" or help_window is None:
        return None
    visible = help_window.toggle()
    return "Help opened" if visible else "Help closed"


def _headline_text(
    *,
    config: AppConfig,
    armed: bool,
    paused: bool,
    operator_notice: str | None,
    mouse_output_locked: bool = False,
) -> tuple[str, str]:
    if mouse_output_locked:
        headline = "AIRPILOT - PREVIEW ONLY"
        guidance = "Mouse output disabled for diagnostics/--no-mouse"
    elif paused:
        headline = "AIRPILOT - PAUSED"
        guidance = "Press P to resume gesture control"
    elif armed:
        headline = "AIRPILOT - ACTIVE"
        guidance = "Mouse control enabled"
    else:
        headline = "AIRPILOT - DISARMED"
        guidance = "A = Enable Mouse | Q = Quit"
    if operator_notice is not None:
        guidance = operator_notice
    return headline, guidance


def _controls_text(config: AppConfig, *, mouse_output_locked: bool = False) -> str:
    if mouse_output_locked:
        return "Controls: P pause | H help | Q quit | Click preview for keys"
    return "Controls: A arm | P pause | H help | Q quit | Click preview for keys"


@dataclass(slots=True)
class HelpWindow:
    visible: bool = False
    title: str = "AirPilot Help"
    _created: bool = False

    def toggle(self) -> bool:
        self.visible = not self.visible
        if not self.visible:
            self._destroy()
        else:
            self._created = False
        return self.visible

    def update(self, config: AppConfig) -> None:
        if not self.visible:
            return
        if self._created and not self._window_is_open():
            self.visible = False
            self._created = False
            return
        cv2.imshow(self.title, _help_image(_help_lines(config)))
        self._created = True

    def close(self) -> None:
        if self.visible or self._created:
            self._destroy()
            self.visible = False
            self._created = False

    def _window_is_open(self) -> bool:
        try:
            visible = cv2.getWindowProperty(self.title, cv2.WND_PROP_VISIBLE)
        except cv2.error:
            return False
        return visible >= 1

    def _destroy(self) -> None:
        try:
            cv2.destroyWindow(self.title)
        except cv2.error:
            return
        self._created = False


def _help_lines(config: AppConfig) -> list[str]:
    return ["AirPilot Help", ""] + action_help_lines(config.actions, max_actions=12)


def _help_image(lines: Sequence[str]) -> MatLike:
    width = 1480 if len(lines) > 48 else 860
    line_height = 20
    column_count = 3 if len(lines) > 72 else 2 if len(lines) > 48 else 1
    column_width = width // column_count
    render_lines = _wrap_help_lines(lines, column_width - 32)
    rows = (len(render_lines) + column_count - 1) // column_count
    height = max(320, 42 + line_height * rows)
    image = np.full((height, width, 3), 32, dtype=np.uint8)
    for index, line in enumerate(render_lines):
        column = index // rows
        row = index % rows
        x = 16 + column * column_width
        y = 36 + row * line_height
        scale = 0.75 if index == 0 else 0.55
        color = (255, 255, 255) if line else (180, 180, 180)
        if (
            line.isupper()
            or line in {"Mouse", "Control"}
            or line.startswith("Shortcut mode")
            or line.startswith("Risky")
        ):
            color = (120, 220, 255)
        cv2.putText(
            image,
            _fit_text(line, column_width - 32, scale=scale),
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            2 if index == 0 else 1,
            cv2.LINE_AA,
        )
    return image


def _wrap_help_lines(lines: Sequence[str], max_width: int) -> list[str]:
    wrapped: list[str] = []
    for index, line in enumerate(lines):
        scale = 0.75 if index == 0 else 0.55
        wrapped.extend(_wrap_help_line(line, max_width, scale=scale))
    return wrapped


def _wrap_help_line(line: str, max_width: int, *, scale: float) -> list[str]:
    if not line or _text_width(line, scale) <= max_width:
        return [line]
    if " | " not in line:
        return _wrap_text_units(line, max_width, scale=scale)

    parts = line.split(" | ")
    current = ""
    wrapped: list[str] = []
    continuation_prefix = "  "
    continuation_width = max_width - _text_width(continuation_prefix, scale)
    for part in parts:
        candidate = part if not current else f"{current} | {part}"
        if _text_width(candidate, scale) <= max_width:
            current = candidate
            continue
        if current:
            wrapped.append(current)
        part_lines = _wrap_text_units(part, continuation_width, scale=scale)
        if len(part_lines) == 1:
            current = f"{continuation_prefix}{part_lines[0]}"
        else:
            wrapped.extend(f"{continuation_prefix}{part_line}" for part_line in part_lines[:-1])
            current = f"{continuation_prefix}{part_lines[-1]}"
    if current:
        wrapped.append(current)
    return wrapped


def _wrap_text_units(text: str, max_width: int, *, scale: float) -> list[str]:
    words = text.split(" ")
    wrapped: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if _text_width(candidate, scale) <= max_width:
            current = candidate
            continue
        if current:
            wrapped.append(current)
            current = ""
        if _text_width(word, scale) <= max_width:
            current = word
            continue
        chunks = _wrap_long_token(word, max_width, scale=scale)
        wrapped.extend(chunks[:-1])
        current = chunks[-1] if chunks else ""
    if current:
        wrapped.append(current)
    return wrapped


def _wrap_long_token(text: str, max_width: int, *, scale: float) -> list[str]:
    chunks: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and _text_width(candidate, scale) > max_width:
            chunks.append(current)
            current = character
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


@dataclass(frozen=True, slots=True)
class OverlayLine:
    text: str
    x: int
    y: int
    scale: float


def _layout_overlay(lines: Sequence[str], width: int) -> list[OverlayLine]:
    padded_width = max(width - 24, 40)
    layout: list[OverlayLine] = []
    y = 30
    for index, text in enumerate(lines):
        scale = 0.72 if index == 0 else 0.52
        line_height = 26 if index == 0 else 22
        layout.append(
            OverlayLine(
                text=_fit_text(text, padded_width, scale=scale),
                x=12,
                y=y,
                scale=scale,
            )
        )
        y += line_height
    return layout


def _fit_text(text: str, max_width: int, *, scale: float) -> str:
    if _text_width(text, scale) <= max_width:
        return text
    suffix = "..."
    fitted = text
    while fitted and _text_width(fitted + suffix, scale) > max_width:
        fitted = fitted[:-1]
    return (fitted.rstrip() + suffix) if fitted else suffix


def _text_width(text: str, scale: float) -> int:
    size, _baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    return int(size[0])


def _draw_banner(
    image: MatLike,
    layout: Sequence[OverlayLine],
    *,
    config: AppConfig,
    armed: bool,
    paused: bool,
    mouse_output_locked: bool = False,
) -> None:
    if mouse_output_locked:
        color = (120, 80, 0)
    elif paused:
        color = (0, 0, 180)
    elif armed:
        color = (0, 140, 0)
    else:
        color = (0, 80, 180)
    banner_height = min(max(layout[-1].y + 12 if layout else 64, 78), int(image.shape[0]))
    cv2.rectangle(image, (0, 0), (int(image.shape[1]), banner_height), color, thickness=-1)
    for line in layout[:2]:
        cv2.putText(
            image,
            line.text,
            (line.x, line.y),
            cv2.FONT_HERSHEY_SIMPLEX,
            line.scale,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )


if __name__ == "__main__":
    raise SystemExit(main())
