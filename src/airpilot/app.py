from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
import traceback
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from tkinter import font as tkfont
from tkinter import ttk
from typing import Literal, Protocol

import cv2
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
from airpilot.display import create_display_provider
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureEngine
from airpilot.domain.types import GestureEvents, TrackingFrame
from airpilot.input import MouseController, PyAutoGuiMouseController
from airpilot.safety import MouseSafetyGate
from airpilot.tracking import HandDrawingError, MediaPipeHandTracker

PREVIEW_WINDOW_TITLE = "AirPilot"


class ExitReason(StrEnum):
    USER_QUIT_Q = "user_quit_q"
    USER_QUIT_ESCAPE = "user_quit_escape"
    MAIN_WINDOW_CLOSED = "main_window_closed"
    CAMERA_UNRECOVERABLE = "camera_unrecoverable"
    FAILSAFE = "failsafe"
    FATAL_EXCEPTION = "fatal_exception"
    EXPLICIT_SHUTDOWN = "explicit_shutdown"
    DIAGNOSTICS_COMPLETE = "diagnostics_complete"
    UNKNOWN = "unknown"


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
    tracking_error_events: int = 0

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
            "tracking_error_events": self.tracking_error_events,
            "max_frame_gap_ms": self.max_frame_gap_ms,
            "hand_observed": self.hand_frames > 0,
        }

    def observe_tracking_error(self) -> None:
        self.tracking_error_events += 1


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
    safety: MouseSafetyGate | None = None
    mouse: MouseController | None = None
    stats = TrackingStats()
    drawing_error: str | None = None
    operator_notice: str | None = None
    exit_reason = ExitReason.UNKNOWN
    exit_detail: str | None = None
    exit_code = 0
    preview_created = False
    preview_visible_once = False
    failsafe_latched = False

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
        safety = MouseSafetyGate(
            armed=(
                config.runtime.enable_real_mouse
                and not mouse_output_locked
                and config.runtime.start_armed
            ),
        )
        for camera_frame in camera.frames():
            image = _prepare_camera_image(camera_frame.image, config)
            try:
                frame = tracker.track(image, camera_frame.timestamp_ms)
            except Exception as exc:
                stats.observe_tracking_error()
                frame = TrackingFrame(
                    timestamp_ms=camera_frame.timestamp_ms,
                    width=camera_frame.width,
                    height=camera_frame.height,
                    hand=None,
                )
                if stats.tracking_error_events <= 3 or stats.tracking_error_events % 30 == 0:
                    print(
                        "AirPilot warning: tracking failed for one frame; "
                        f"continuing ({type(exc).__name__}: {exc}).",
                        file=sys.stderr,
                    )
            events = engine.process(frame)
            events = action_router.process(frame, events)
            if events.action_id == "ui.toggle_help":
                operator_notice = _dispatch_ui_action(events.action_id, help_window)
            elif events.action_id == "ui.arm":
                operator_notice = _dispatch_ui_action(
                    events.action_id,
                    help_window,
                    config=config,
                    safety=safety,
                    mouse_output_locked=mouse_output_locked,
                )
                if safety.armed:
                    failsafe_latched = False
            mouse_output_enabled = config.runtime.enable_real_mouse and not mouse_output_locked
            if mouse_output_enabled:
                try:
                    safety.apply(mouse, events)
                    if (
                        safety.armed
                        and events.action_id is not None
                        and not events.action_id.startswith("ui.")
                    ):
                        action_label = dispatch_action(config.actions, mouse, events.action_id)
                        if action_label is not None:
                            operator_notice = f"ACTION: {action_label}"
                except pyautogui.FailSafeException as exc:
                    safety.disarm(mouse)
                    operator_notice = "Failsafe corner reached; mouse control disarmed"
                    if not failsafe_latched:
                        print(
                            f"AirPilot warning: {exc}. Mouse control disarmed; continuing.",
                            file=sys.stderr,
                        )
                    failsafe_latched = True
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
                cv2.imshow(PREVIEW_WINDOW_TITLE, image)
                preview_created = True
                key_exit_reason, operator_notice = _handle_keypress(
                    cv2.waitKey(1),
                    config=config,
                    engine=engine,
                    safety=safety,
                    mouse=mouse,
                    help_window=help_window,
                    mouse_output_locked=mouse_output_locked,
                )
                if key_exit_reason is not None:
                    exit_reason = key_exit_reason
                    break
                if safety.armed and operator_notice in {
                    "Mouse control enabled",
                    "ARMED by gesture",
                }:
                    failsafe_latched = False
                help_window.update(config)
                preview_visibility = _preview_window_visibility(
                    PREVIEW_WINDOW_TITLE,
                    preview_created=preview_created,
                )
                if preview_visibility is True:
                    preview_visible_once = True
                elif preview_visibility is False and preview_visible_once:
                    exit_reason = ExitReason.MAIN_WINDOW_CLOSED
                    break
            if diagnose_seconds is not None and stats.elapsed_seconds >= diagnose_seconds:
                summary = stats.summary(camera_backend=camera.backend_name)
                summary["camera_reconnects"] = camera.reconnect_count
                print(json.dumps(summary, sort_keys=True))
                exit_reason = ExitReason.DIAGNOSTICS_COMPLETE
                break
            if safety.armed or failsafe_latched:
                try:
                    emergency_stop = mouse.emergency_stop_requested()
                except pyautogui.FailSafeException as exc:
                    emergency_stop = True
                    exit_detail = str(exc)
                if emergency_stop:
                    safety.disarm(mouse)
                    operator_notice = "Failsafe corner reached; mouse control disarmed"
                    if not failsafe_latched:
                        print(
                            "AirPilot warning: failsafe corner reached. "
                            "Mouse control disarmed; continuing.",
                            file=sys.stderr,
                        )
                    failsafe_latched = True
                else:
                    failsafe_latched = False
    except pyautogui.FailSafeException as exc:
        exit_reason = ExitReason.FAILSAFE
        exit_detail = str(exc)
        exit_code = 2
    except RuntimeError as exc:
        exit_reason = (
            ExitReason.CAMERA_UNRECOVERABLE
            if "camera" in str(exc).lower()
            else ExitReason.FATAL_EXCEPTION
        )
        exit_detail = str(exc)
        exit_code = 1
    except Exception as exc:
        exit_reason = ExitReason.FATAL_EXCEPTION
        exit_detail = f"{type(exc).__name__}: {exc}"
        traceback.print_exc(file=sys.stderr)
        exit_code = 1
    finally:
        if camera is not None:
            camera.close()
        if tracker is not None:
            tracker.close()
        if safety is not None and mouse is not None:
            safety.disarm(mouse)
        if "help_window" in locals():
            help_window.close()
        cv2.destroyAllWindows()
        if exit_reason is ExitReason.UNKNOWN:
            exit_reason = ExitReason.EXPLICIT_SHUTDOWN
        _report_exit(exit_reason, exit_detail)
    return exit_code


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
        events=events,
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
        return "escape"
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
) -> tuple[ExitReason | None, str | None]:
    command = _normalized_key(key)
    if command == "q":
        return ExitReason.USER_QUIT_Q, "Quit requested"
    if command == "p":
        pause_events = engine.toggle_pause()
        if config.runtime.enable_real_mouse and not mouse_output_locked:
            safety.apply(mouse, pause_events)
        return None, "Paused" if pause_events.paused else "Resumed"
    if command == "h":
        return None, _dispatch_ui_action("ui.toggle_help", help_window)
    if command == "a":
        if mouse_output_locked:
            return None, "Mouse output disabled for diagnostics/--no-mouse"
        if not config.runtime.enable_real_mouse:
            config.runtime.enable_real_mouse = True
        if safety.armed:
            safety.disarm(mouse)
            return None, "Mouse control disabled"
        safety.toggle()
        return None, "Mouse control enabled"
    if command == "escape":
        return None, "Esc ignored; press Q to quit"
    return None, None


def _preview_window_closed(title: str, *, preview_created: bool) -> bool:
    return _preview_window_visibility(title, preview_created=preview_created) is False


def _preview_window_visibility(title: str, *, preview_created: bool) -> bool | None:
    if not preview_created:
        return None
    try:
        visible = cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE)
    except cv2.error:
        return None
    if visible >= 1:
        return True
    if visible == 0:
        return False
    return None


def _report_exit(reason: ExitReason, detail: str | None = None) -> None:
    message = f"AirPilot exit reason: {reason.value}"
    if detail:
        message = f"{message} ({detail})"
    print(message, file=sys.stderr)


def _dispatch_ui_action(
    action_id: str,
    help_window: HelpWindow | None,
    *,
    config: AppConfig | None = None,
    safety: MouseSafetyGate | None = None,
    mouse_output_locked: bool = False,
) -> str | None:
    if action_id == "ui.toggle_help":
        if help_window is None:
            return None
        visible = help_window.toggle()
        return "Help opened" if visible else "Help closed"
    if action_id == "ui.arm":
        if mouse_output_locked:
            return "Mouse output disabled for diagnostics/--no-mouse"
        if safety is None:
            return "Arm unavailable"
        if safety.armed:
            return "Already armed"
        if config is not None and not config.runtime.enable_real_mouse:
            config.runtime.enable_real_mouse = True
        safety.armed = True
        return "ARMED by gesture"
    return None


def _headline_text(
    *,
    config: AppConfig,
    armed: bool,
    paused: bool,
    events: GestureEvents,
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
        if events.active_gesture == "task_view_pending":
            guidance = "TASK VIEW - hold index pinch"
        elif events.active_gesture == "task_view":
            guidance = "TASK VIEW - move left/right, release to open"
        elif events.active_gesture == "task_view_select_right":
            guidance = "TASK VIEW - next app"
        elif events.active_gesture == "task_view_select_left":
            guidance = "TASK VIEW - previous app"
        elif events.active_gesture == "click_candidate":
            guidance = "CLICK LOCK - release to click, move farther to drag"
        elif events.active_gesture == "clutch":
            guidance = "Thumb folded: pointer frozen. Open thumb to resume."
        else:
            guidance = "Mouse control enabled"
    else:
        headline = "AIRPILOT - DISARMED"
        if events.active_gesture == "arm_pending":
            guidance = "ARMING - hold second-hand thumb + middle"
        else:
            guidance = "Hold second-hand thumb+middle to arm | A = arm | Q = quit"
    if operator_notice is not None:
        guidance = operator_notice
    return headline, guidance


def _controls_text(config: AppConfig, *, mouse_output_locked: bool = False) -> str:
    if mouse_output_locked:
        return "Controls: P pause | H help | Q quit | Click preview for keys"
    return "Controls: A arm | P pause | H help | Q quit | Click preview for keys"


@dataclass(slots=True)
class HelpBounds:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class HelpSection:
    title: str
    lines: tuple[str, ...]


class HelpBackend(Protocol):
    def update(self, config: AppConfig) -> None: ...

    def close(self) -> None: ...

    def is_open(self) -> bool: ...


def _default_help_backend_factory() -> HelpBackend:
    return _TkHelpBackend()


@dataclass(slots=True)
class HelpWindow:
    visible: bool = False
    title: str = "AirPilot Help"
    backend_factory: Callable[[], HelpBackend] = _default_help_backend_factory
    _backend: HelpBackend | None = None

    def toggle(self) -> bool:
        self.visible = not self.visible
        if not self.visible:
            self.close()
        else:
            self._backend = None
        return self.visible

    def update(self, config: AppConfig) -> None:
        if not self.visible:
            return
        if self._backend is not None and not self._backend.is_open():
            self.visible = False
            self._backend = None
            return
        if self._backend is None:
            self._backend = self.backend_factory()
        self._backend.update(config)
        if not self._backend.is_open():
            self.visible = False
            self._backend = None

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()
        self.visible = False
        self._backend = None


class _TkHelpBackend:
    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._window: tk.Toplevel | None = None
        self._text: tk.Text | None = None
        self._search_var: tk.StringVar | None = None
        self._category_list: tk.Listbox | None = None
        self._signature: str | None = None

    def update(self, config: AppConfig) -> None:
        if not self.is_open():
            self._create_window()
        signature = json.dumps(action_help_lines(config.actions, max_actions=None), sort_keys=True)
        filter_text = self._search_var.get().strip().lower() if self._search_var else ""
        signature = f"{signature}\nfilter={filter_text}"
        if signature != self._signature:
            self._populate(config)
            self._signature = signature
        self._pump()

    def close(self) -> None:
        if self._window is not None:
            with suppress(tk.TclError):
                self._window.destroy()
        if self._root is not None:
            with suppress(tk.TclError):
                self._root.destroy()
        self._window = None
        self._root = None
        self._text = None
        self._search_var = None
        self._category_list = None
        self._signature = None

    def is_open(self) -> bool:
        if self._window is None:
            return False
        try:
            return bool(self._window.winfo_exists())
        except tk.TclError:
            return False

    def _create_window(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()
        self._window = tk.Toplevel(self._root)
        self._window.title("AirPilot Help")
        self._window.minsize(640, 420)
        bounds = _help_initial_bounds(_screen_work_area(self._window))
        self._window.geometry(f"{bounds.width}x{bounds.height}+{bounds.left}+{bounds.top}")
        self._window.protocol("WM_DELETE_WINDOW", self.close)

        default_font = tkfont.nametofont("TkDefaultFont")
        heading_font = default_font.copy()
        heading_font.configure(size=max(default_font.cget("size") + 3, 12), weight="bold")

        main = ttk.Frame(self._window, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        self._window.columnconfigure(0, weight=1)
        self._window.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        title = ttk.Label(main, text="AirPilot Help", font=heading_font)
        title.grid(row=0, column=0, columnspan=3, sticky="w")
        intro = ttk.Label(
            main,
            text=(
                "Use AirPilot safely: arm deliberately, move with an open thumb, "
                "fold the thumb to freeze, and keep risky actions disabled until tested."
            ),
            wraplength=max(bounds.width - 80, 480),
        )
        intro.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 10))

        self._category_list = tk.Listbox(
            main, activestyle="dotbox", exportselection=False, width=20
        )
        self._category_list.grid(row=2, column=0, sticky="ns", padx=(0, 10))
        self._category_list.bind("<<ListboxSelect>>", self._jump_to_category)

        text_frame = ttk.Frame(main)
        text_frame.grid(row=2, column=1, columnspan=2, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        self._text = tk.Text(
            text_frame,
            wrap=_help_text_wrap_mode(),
            borderwidth=1,
            relief="solid",
            padx=10,
            pady=8,
            yscrollcommand=scrollbar.set,
            font=default_font,
        )
        scrollbar.configure(command=self._text.yview)
        self._text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._text.tag_configure("section", font=heading_font, spacing1=8, spacing3=4)
        self._text.tag_configure("intro", spacing3=8)
        self._text.configure(state="disabled")

        ttk.Label(main, text="Filter").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self._search_var = tk.StringVar()
        search = ttk.Entry(main, textvariable=self._search_var)
        search.grid(row=3, column=1, sticky="ew", pady=(10, 0))
        search.bind("<KeyRelease>", self._on_search_changed)
        ttk.Button(main, text="Close", command=self.close).grid(
            row=3,
            column=2,
            sticky="e",
            padx=(10, 0),
            pady=(10, 0),
        )

    def _populate(self, config: AppConfig) -> None:
        if self._text is None or self._category_list is None:
            return
        filter_text = self._search_var.get().strip().lower() if self._search_var else ""
        sections = _filter_help_sections(_help_sections(config), filter_text)
        self._category_list.delete(0, tk.END)
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        for section in sections:
            self._category_list.insert(tk.END, section.title.title())
            tag_name = f"section_{section.title}"
            self._text.insert(tk.END, f"{section.title.title()}\n", ("section", tag_name))
            for line in section.lines:
                self._text.insert(
                    tk.END, f"{line}\n", ("intro",) if section.title == "INTRO" else ()
                )
            self._text.insert(tk.END, "\n")
        self._text.configure(state="disabled")

    def _pump(self) -> None:
        if self._root is None:
            return
        try:
            self._root.update_idletasks()
            self._root.update()
        except tk.TclError:
            self.close()

    def _jump_to_category(self, _event: tk.Event[tk.Listbox]) -> None:
        if self._category_list is None or self._text is None:
            return
        selection = self._category_list.curselection()  # type: ignore[no-untyped-call]
        if not selection:
            return
        title = self._category_list.get(selection[0]).upper()
        location = self._text.search(title.title(), "1.0", tk.END)
        if location:
            self._text.see(location)

    def _on_search_changed(self, _event: tk.Event[ttk.Entry]) -> None:
        self._signature = None


def _help_lines(config: AppConfig) -> list[str]:
    return ["AirPilot Help", ""] + action_help_lines(config.actions, max_actions=None)


def _help_sections(config: AppConfig) -> list[HelpSection]:
    lines = action_help_lines(config.actions, max_actions=None)
    sections = [
        HelpSection(
            "INTRO",
            (
                "Most important controls are listed first. Keep AirPilot disarmed until the "
                "preview and hand tracking look stable.",
                "Open thumb: pointer moves with the palm/knuckle anchor.",
                "Thumb folded: pointer frozen. Open thumb to resume.",
            ),
        )
    ]
    current_title: str | None = None
    current_lines: list[str] = []
    for line in lines:
        if not line:
            continue
        if line.isupper():
            if current_title is not None:
                sections.append(HelpSection(current_title, tuple(current_lines)))
            current_title = line
            current_lines = []
            continue
        if line == "What it does | Gesture | Shortcut/Keys | State":
            current_lines.append("What it does    Gesture    Shortcut/Keys    State")
        else:
            current_lines.append(_format_help_row(line))
    if current_title is not None:
        sections.append(HelpSection(current_title, tuple(current_lines)))
    return sections


def _format_help_row(line: str) -> str:
    parts = [part.strip() for part in line.split(" | ")]
    if len(parts) != 4:
        return line
    return f"{parts[0]}: {parts[1]} ({parts[2]}; {parts[3]})"


def _filter_help_sections(sections: Sequence[HelpSection], filter_text: str) -> list[HelpSection]:
    if not filter_text:
        return list(sections)
    filtered: list[HelpSection] = []
    for section in sections:
        matching_lines = tuple(line for line in section.lines if filter_text in line.lower())
        if filter_text in section.title.lower() or matching_lines:
            filtered.append(HelpSection(section.title, matching_lines or section.lines))
    return filtered


def _help_text_wrap_mode() -> Literal["word"]:
    return "word"


def _screen_work_area(window: tk.Toplevel) -> HelpBounds:
    windows_area = _windows_work_area()
    if windows_area is not None:
        return windows_area
    return HelpBounds(
        left=0,
        top=0,
        width=max(int(window.winfo_screenwidth()), 1),
        height=max(int(window.winfo_screenheight()), 1),
    )


def _windows_work_area() -> HelpBounds | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if not ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
            return None
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return None
        return HelpBounds(int(rect.left), int(rect.top), width, height)
    except (AttributeError, OSError, ValueError):
        return None


def _help_initial_bounds(work_area: HelpBounds, *, scale: float = 1.0) -> HelpBounds:
    margin = max(int(48 * scale), 16)
    min_width = min(640, max(work_area.width - margin, 320))
    min_height = min(420, max(work_area.height - margin, 280))
    preferred_width = int(980 * scale)
    preferred_height = int(720 * scale)
    width = min(max(preferred_width, min_width), max(work_area.width - margin, min_width))
    height = min(max(preferred_height, min_height), max(work_area.height - margin, min_height))
    left = work_area.left + max((work_area.width - width) // 2, 0)
    top = work_area.top + max((work_area.height - height) // 2, 0)
    return HelpBounds(left=left, top=top, width=width, height=height)


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
