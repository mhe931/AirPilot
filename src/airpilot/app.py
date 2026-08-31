from __future__ import annotations

import argparse
import faulthandler
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
    SHORTCUT_GESTURES,
    ActionRouter,
    _gesture_label,
    action_help_lines,
    dispatch_action,
    validate_action_config,
)
from airpilot.camera import OpenCVCamera, list_cameras
from airpilot.config import (
    ActionConfig,
    AppConfig,
    GestureBinding,
    TextStyleConfig,
    default_config_path,
    load_config,
    read_config_schema_version,
    save_config,
    validate_gesture_bindings,
)
from airpilot.display import create_display_provider
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureBindingMatcher, GestureEngine
from airpilot.domain.pose import thumb_index_angle_deg
from airpilot.domain.types import GestureEvents, TrackingFrame
from airpilot.input import MouseController, PyAutoGuiMouseController
from airpilot.safety import MouseSafetyGate
from airpilot.shortcut_recorder import (
    detect_shortcut_conflicts,
    normalize_shortcut,
    shortcut_label,
    sync_custom_shortcuts,
    validate_shortcut,
)
from airpilot.tracking import HandDrawingError, MediaPipeHandTracker

PREVIEW_WINDOW_TITLE = "AirPilot"

# ---------------------------------------------------------------------------
# Emoji registry – consistent across sidebar, Help, and status overlays.
# OpenCV does not render Unicode emoji in cv2.putText; these are used only in
# the Tkinter Help window and Settings where the font supports them.
# ---------------------------------------------------------------------------

EMOJI_HAND = "🖐"
EMOJI_POINTER_ON = "🖱️"
EMOJI_POINTER_FROZEN = "🧊"
EMOJI_LEFT_CLICK = "👆"
EMOJI_RIGHT_CLICK = "☝️"
EMOJI_DRAG = "✊"
EMOJI_SCROLL = "📜"
EMOJI_SHORTCUT = "✌️"
EMOJI_HELP = "❓"
EMOJI_SETTINGS = "⚙️"
EMOJI_ARM = "✅"
EMOJI_COPY = "📋"
EMOJI_PASTE = "📌"
EMOJI_NEXT_SLIDE = "▶️"
EMOJI_PREV_SLIDE = "◀️"
EMOJI_FIST = "👊"
EMOJI_MOVE_LEFT = "←"
EMOJI_MOVE_RIGHT = "→"
EMOJI_MOVE_UP = "↑"
EMOJI_MOVE_DOWN = "↓"


# ---------------------------------------------------------------------------
# Shared Tkinter root – one Tk() per process.
#
# Python's Tkinter only supports one Tk() interpreter per process. Creating
# multiple Tk() instances (e.g., one for Help and one for Settings) corrupts
# the shared Tcl state, causing crashes – especially on Windows when the
# OpenCV message pump (cv2.waitKey) interleaves with Tk event handling.
#
# _TkSharedRoot is a reference-counted module singleton. Both HelpWindow and
# SettingsWindow acquire/release it; the root is withdrawn (invisible) and
# never shown directly.
# ---------------------------------------------------------------------------


class _TkSharedRoot:
    """Thread-safe singleton wrapper for the one hidden ``tk.Tk`` root."""

    _root: tk.Tk | None = None
    _refcount: int = 0

    @classmethod
    def acquire(cls) -> tk.Tk:
        """Increment the reference count and return the shared root.

        Creates the root the first time it is requested.
        """
        if cls._root is None:
            cls._root = tk.Tk()
            with suppress(tk.TclError):
                cls._root.withdraw()
        cls._refcount += 1
        return cls._root

    @classmethod
    def release(cls) -> None:
        """Decrement the reference count; destroy the root when it reaches 0."""
        cls._refcount = max(cls._refcount - 1, 0)
        if cls._refcount == 0 and cls._root is not None:
            with suppress(tk.TclError, Exception):
                cls._root.destroy()
            cls._root = None

    @classmethod
    def pump(cls) -> None:
        """Process pending Tk events without blocking; no-op if not alive."""
        if cls._root is None:
            return
        try:
            cls._root.update_idletasks()
            cls._root.update()
        except tk.TclError:
            pass

    @classmethod
    def force_close(cls) -> None:
        """Destroy root and reset counter unconditionally (used in teardown)."""
        if cls._root is not None:
            with suppress(tk.TclError, Exception):
                cls._root.destroy()
            cls._root = None
        cls._refcount = 0


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    """Convert a CSS hex color (``#rrggbb``) to an OpenCV BGR tuple.

    Falls back to white on malformed input so callers never receive a crash.
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return (255, 255, 255)
    return (b, g, r)


def _sidebar_lines(
    frame: TrackingFrame,
    events: GestureEvents,
    config: AppConfig,
    *,
    armed: bool,
) -> list[str]:
    """Return compact sidebar lines for the live preview panel.

    Lines are ASCII-safe because cv2.putText cannot render Unicode.
    Returns an empty list when the sidebar is disabled in text_styles.
    Shows gesture name, mapped action, mode, and availability live.
    """
    if not config.text_styles.sidebar_enabled:
        return []

    hand = frame.hand
    hand_label = "hand: -"
    if hand is not None:
        side = hand.handedness.value[0].upper()
        hand_label = f"hand: {side}"
    if frame.secondary_hand is not None:
        sec_side = frame.secondary_hand.handedness.value[0].upper()
        hand_label += f"+{sec_side}"

    mode = "DISARMED"
    if events.paused:
        mode = "PAUSED"
    elif armed:
        mode = "ACTIVE"

    gesture_abbrev = {
        "clutch": "frozen",
        "click_candidate": "click?",
        "left_click": "click!",
        "dragging": "drag",
        "scroll": "scroll",
        "shortcut_mode": "shortcuts",
        "shortcut_pending": "shortcut?",
        "arm_pending": "arming...",
        "help_pending": "help?",
        "task_view_pending": "taskview?",
        "task_view": "taskview",
        "none": "",
    }
    gesture = gesture_abbrev.get(events.active_gesture, events.active_gesture or "")

    lines = [mode, hand_label]
    if gesture:
        lines.append(gesture)

    # Gesture→action dashboard – replace rows by mode (no stale entries).
    # When in shortcut mode, only shortcut-mode gestures are relevant.
    # When in default mode, only default-mode gestures are shown.
    lines.append("---")
    if events.shortcut_mode:
        lines.append("=SHORTCUT MODE=")
        # Resolve configured shortcut actions from config
        ga = config.actions.gesture_actions
        _sc_label = config.actions.catalog

        def _sc(key: str) -> str:
            action_id = ga.get(key, "")
            sc = _sc_label.get(action_id)
            return sc.label[:10] if sc else action_id.split(".")[-1][:10]

        lines.append(f"[idx]  {_sc('shortcut_index_release')}")
        lines.append(f"[mid]  {_sc('shortcut_middle_release')}")
        lines.append(f"[mid-h]{_sc('shortcut_middle_hold')}")
        lines.append(f"[ring] {_sc('shortcut_ring_release')}")
        lines.append(f"[pinky]{_sc('shortcut_pinky_release')}")
        lines.append("[hold-idx] task view")
        lines.append("[release 2nd] exit")
    else:
        lines.append("[thumb open] move")
        lines.append("[thumb fold] freeze")
        lines.append("[pinch idx]  click")
        lines.append("[pinch mid]  r-click")
        lines.append("[ring+wrist] scroll")
        lines.append("[arm gesture] arm")
        lines.append("[help gesture] help")
        lines.append("[2nd thumb+pinky] shortcuts")
    # Configurable bindings – show enabled ones with shortcut label or action id
    for b in config.gesture_bindings:
        if not b.enabled:
            continue
        if b.shortcut_keys:
            label = shortcut_label(tuple(b.shortcut_keys))[:14]
        elif b.action_id and not b.action_id.startswith("custom."):
            label = b.action_id.split(".")[-1][:10]
        else:
            continue
        lines.append(f"[{b.id[:8]}]:{label}")
    return lines


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
    # Enable C-level fault handler so any native crash (e.g. GIL violations
    # from native extensions) prints a stack trace to stderr before the
    # process dies.  This is a no-op once the process is healthy but vital
    # for post-crash diagnosis.
    faulthandler.enable(file=sys.stderr)
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
    sync_custom_shortcuts(config)
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
    preview_maximize_disabled = False
    failsafe_latched = False
    # Consecutive tracker exception counter.  After _TRACKER_RESET_THRESHOLD
    # back-to-back exceptions (e.g. from a corrupt MediaPipe pipeline state
    # signalled by landmark_projection_calculator NORM_RECT warnings), the
    # tracker is closed and recreated to restore a clean pipeline.  This
    # prevents the stale C++ thread-state that causes the Python 3.11 GIL
    # assertion "PyEval_RestoreThread: the function must be called with the
    # GIL held" during the next cv2.waitKey() call.
    _tracker_error_streak = 0
    _TRACKER_RESET_THRESHOLD = 5

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
        binding_matcher = GestureBindingMatcher(config.gesture_bindings, config.gestures)
        help_window = HelpWindow(visible=config.runtime.show_gesture_help)
        last_frame: TrackingFrame | None = None

        def _on_settings_applied() -> None:
            if last_frame is not None:
                engine.rebase_to_current_hand(last_frame)
            help_window.refresh(config)

        settings_window = SettingsWindow(config, None, on_apply=_on_settings_applied)
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
                last_frame = frame
                _tracker_error_streak = 0
            except Exception as exc:
                _tracker_error_streak += 1
                stats.observe_tracking_error()
                frame = TrackingFrame(
                    timestamp_ms=camera_frame.timestamp_ms,
                    width=camera_frame.width,
                    height=camera_frame.height,
                    hand=None,
                )
                last_frame = frame
                if stats.tracking_error_events <= 3 or stats.tracking_error_events % 30 == 0:
                    print(
                        "AirPilot warning: tracking failed for one frame; "
                        f"continuing ({type(exc).__name__}: {exc}).",
                        file=sys.stderr,
                    )
                if _tracker_error_streak >= _TRACKER_RESET_THRESHOLD:
                    # Reset the MediaPipe pipeline to clear corrupt internal
                    # state (e.g. from landmark_projection_calculator
                    # NORM_RECT errors).  Without this, MediaPipe background
                    # threads can hold stale Python thread states that crash
                    # Python 3.11's strict PyEval_RestoreThread assertion
                    # when cv2.waitKey() next releases the GIL.
                    with suppress(Exception):
                        tracker.close()
                    tracker = MediaPipeHandTracker(
                        min_detection_confidence=config.runtime.tracker_detection_confidence,
                        min_tracking_confidence=config.runtime.tracker_tracking_confidence,
                        input_is_mirrored=config.runtime.flip_camera_x,
                    )
                    _tracker_error_streak = 0
                    print(
                        "AirPilot warning: tracker restarted after consecutive errors.",
                        file=sys.stderr,
                    )
            events = engine.process(frame)
            events = action_router.process(frame, events)
            events = binding_matcher.process(frame, events)
            if events.action_id == "ui.toggle_help":
                operator_notice = _dispatch_ui_action(events.action_id, help_window)
            elif events.action_id in ("ui.open_settings", "ui.close_settings"):
                operator_notice = _dispatch_ui_action(
                    events.action_id,
                    help_window,
                    settings_window=settings_window,
                )
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
                # Pump Tkinter events BEFORE cv2.imshow / cv2.waitKey.
                #
                # On Windows, cv2.waitKey() runs a Win32 PeekMessage loop that
                # dispatches messages to ALL windows owned by the calling
                # thread, including any hidden Tkinter root window.  If Tkinter
                # callbacks fire while Python's GIL is in the partially-
                # released state that OpenCV uses internally, Python 3.11's
                # strict PyEval_RestoreThread assertion triggers the fatal
                # "the function must be called with the GIL held" crash.
                #
                # Draining the Tk queue here (while the GIL is fully held)
                # means the queue is empty when waitKey runs its own loop,
                # eliminating the re-entrant callback window.
                help_window.update(config)
                settings_window.update()
                cv2.imshow(PREVIEW_WINDOW_TITLE, image)
                preview_created = True
                if not preview_maximize_disabled:
                    _disable_cv2_window_maximize(PREVIEW_WINDOW_TITLE)
                    preview_maximize_disabled = True
                key_exit_reason, operator_notice = _handle_keypress(
                    cv2.waitKey(1),
                    config=config,
                    engine=engine,
                    safety=safety,
                    mouse=mouse,
                    help_window=help_window,
                    settings_window=settings_window,
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
        # Destroy the OpenCV window first to stop its message pump before
        # touching any Tkinter state. On Windows, cv2.waitKey() runs an
        # abbreviated Windows message loop; destroying OpenCV windows before
        # Tk prevents cross-pump corruption that causes the native crash.
        with suppress(Exception):
            cv2.destroyAllWindows()
        if camera is not None:
            with suppress(Exception):
                camera.close()
        if tracker is not None:
            with suppress(Exception):
                tracker.close()
        if safety is not None and mouse is not None:
            with suppress(Exception):
                safety.disarm(mouse)
        if "help_window" in locals():
            with suppress(Exception):
                help_window.close()
        if "settings_window" in locals():
            with suppress(Exception):
                settings_window.close()
        # Release the shared Tk root after all Toplevel windows are gone.
        with suppress(Exception):
            _TkSharedRoot.force_close()
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
    control_hand = hand.handedness.value[0].upper() if hand is not None else "-"
    headline, guidance = _headline_text(
        config=config,
        armed=armed,
        paused=events.paused,
        events=events,
        operator_notice=operator_notice,
        mouse_output_locked=mouse_output_locked,
    )
    controls = _controls_text(config, mouse_output_locked=mouse_output_locked)
    # Compact angle field
    angle_str = "--"
    if hand is not None and config.gestures.use_thumb_angle_activation:
        ang = thumb_index_angle_deg(hand.landmarks)
        if ang is not None:
            angle_str = f"{ang:.0f}\u00b0"
    gesture_label = events.active_gesture
    detail = (
        f"{tracking} | {gesture_label} | "
        f"{control_hand} hand | \u03b8{angle_str} | score {hand_score} | {fps:.0f}fps"
    )
    lines = [headline, guidance, detail, controls]
    if events.action_label is not None:
        lines.append(f"action {events.action_label}")
    if drawing_error is not None:
        lines.append(f"preview {drawing_error}")
    return lines


def _compute_sidebar_width(
    frame: TrackingFrame,
    events: GestureEvents,
    config: AppConfig,
    *,
    armed: bool,
    image_width: int,
) -> int:
    """Return the pixel width the sidebar will occupy, or 0 if it is disabled.

    Mirrors the panel-width logic in :func:`_draw_sidebar` so that
    :func:`_layout_overlay` can reserve an equal left margin, preventing
    the status text from being rendered behind the sidebar.
    """
    if not config.text_styles.sidebar_enabled:
        return 0
    lines = _sidebar_lines(frame, events, config, armed=armed)
    if not lines:
        return 0
    scale_factor = max(config.text_styles.sidebar_scale_pct, 10) / 100.0
    text_scale = 0.35 * scale_factor
    padding_x = 4
    panel_width = 2 * padding_x
    for line in lines:
        tw, _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, text_scale, 1)
        panel_width = max(panel_width, tw[0] + 2 * padding_x)
    return min(panel_width, image_width // 3)


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
    # Measure the sidebar width so the overlay text starts to the right of it
    # and is never rendered behind the sidebar panel.
    sidebar_width = _compute_sidebar_width(
        frame, events, config, armed=armed, image_width=int(image.shape[1])
    )
    layout = _layout_overlay(lines, int(image.shape[1]), sidebar_width=sidebar_width)
    _draw_banner(
        image,
        layout,
        config=config,
        armed=armed,
        paused=events.paused,
        mouse_output_locked=mouse_output_locked,
    )
    # Compute the banner height so the sidebar starts below it.
    if len(layout) >= 2:
        banner_height = layout[1].y + 10
    elif layout:
        banner_height = layout[0].y + 10
    else:
        banner_height = 40
    banner_height = min(max(banner_height, 32), int(image.shape[0]))
    # Detail lines (index 2+) drawn below the banner with shadow for contrast
    for line in layout[2:]:
        # Black shadow pass first
        cv2.putText(
            image,
            line.text,
            (line.x + 1, line.y + 1),
            cv2.FONT_HERSHEY_SIMPLEX,
            line.scale,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        # White text on top
        cv2.putText(
            image,
            line.text,
            (line.x, line.y),
            cv2.FONT_HERSHEY_SIMPLEX,
            line.scale,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )
    # Left-side contextual gesture/action sidebar (starts below the banner)
    _draw_sidebar(image, frame, events, config, armed=armed, top_offset=banner_height)


def _draw_sidebar(
    image: MatLike,
    frame: TrackingFrame,
    events: GestureEvents,
    config: AppConfig,
    *,
    armed: bool,
    top_offset: int = 0,
) -> None:
    """Draw a compact contextual gesture/action sidebar on the left edge.

    The sidebar lists available gestures and their current actions, updating
    live based on active mode, shortcut state, and gesture bindings.
    It uses a solid dark background strip so text is always readable even over
    bright camera frames.  ``top_offset`` reserves the banner region so the
    sidebar starts below the top status bar (no overlap).
    """
    lines = _sidebar_lines(frame, events, config, armed=armed)
    if not lines:
        return

    height = int(image.shape[0])
    scale_factor = max(config.text_styles.sidebar_scale_pct, 10) / 100.0
    text_scale = 0.35 * scale_factor
    line_height = int(14 * scale_factor)
    padding_x = 4
    padding_y = 6

    # Determine panel width from longest line
    panel_width = 2 * padding_x
    for line in lines:
        tw, _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, text_scale, 1)
        panel_width = max(panel_width, tw[0] + 2 * padding_x)
    panel_width = min(panel_width, int(image.shape[1] // 3))

    # Draw background panel (starts at top_offset to avoid banner overlap)
    bg = _hex_to_bgr(config.text_styles.sidebar_bg)
    bg_alpha = max(0.0, min(1.0, config.text_styles.sidebar_bg_opacity))
    if bg_alpha >= 1.0:
        cv2.rectangle(image, (0, top_offset), (panel_width, height), bg, thickness=-1)
    elif bg_alpha > 0.0:
        overlay = image.copy()
        cv2.rectangle(overlay, (0, top_offset), (panel_width, height), bg, thickness=-1)
        cv2.addWeighted(overlay, bg_alpha, image, 1.0 - bg_alpha, 0, image)

    # Draw separator line
    cv2.line(image, (panel_width, top_offset), (panel_width, height), (60, 60, 60), 1)

    fg = _hex_to_bgr(config.text_styles.sidebar_fg)
    y = top_offset + padding_y + line_height
    for idx, line in enumerate(lines):
        if y > height - padding_y:
            break
        if line == "---":
            cv2.line(
                image,
                (padding_x, y - line_height // 2),
                (panel_width - padding_x, y - line_height // 2),
                (80, 80, 80),
                1,
            )
            y += line_height // 2
            continue
        # Highlight header lines
        color = fg
        if idx == 0:
            color = (200, 200, 255)  # lighter for mode
        cv2.putText(
            image,
            line,
            (padding_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            text_scale,
            color,
            1,
            cv2.LINE_AA,
        )
        y += line_height


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


def _disable_cv2_window_maximize(title: str) -> None:
    """Remove the maximize button from a cv2 preview window on Windows.

    Uses the Win32 ``GetWindowLongW`` / ``SetWindowLongW`` API to clear the
    ``WS_MAXIMIZEBOX`` style so the title-bar button is hidden.  Silently
    no-ops on non-Windows platforms or when the window cannot be found.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import ctypes.wintypes

        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if not hwnd:
            return
        GWL_STYLE = -16
        WS_MAXIMIZEBOX = 0x00010000
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_MAXIMIZEBOX)
    except (AttributeError, OSError):
        pass


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
    settings_window: SettingsWindow | None = None,
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
    if command == "s":
        if settings_window is not None and not settings_window.is_open():
            settings_window.open()
            return None, "Settings opened"
        return None, None
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
    settings_window: SettingsWindow | None = None,
    mouse_output_locked: bool = False,
) -> str | None:
    if action_id == "ui.toggle_help":
        if help_window is None:
            return None
        visible = help_window.toggle()
        return "Help opened" if visible else "Help closed"
    if action_id == "ui.open_settings":
        if settings_window is None:
            return None
        if settings_window.is_open():
            return "Settings already open"
        settings_window.open()
        return "Settings opened"
    if action_id == "ui.close_settings":
        if settings_window is None:
            return None
        if not settings_window.is_open():
            return None
        settings_window.close()
        return "Settings closed"
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
        return "Controls: P pause | H help | S settings | Q quit"
    return "Controls: A arm | P pause | H help | S settings | Q quit"


_SHORTCUT_GESTURE_ORDER: tuple[str, ...] = (
    "arm_secondary_middle_hold",
    "help_secondary_index_hold",
    "shortcut_index_release",
    "shortcut_index_hold",
    "shortcut_middle_release",
    "shortcut_middle_hold",
    "shortcut_ring_release",
    "shortcut_pinky_release",
)


def _editable_shortcut_gesture_ids() -> tuple[str, ...]:
    ordered = [
        gesture_id for gesture_id in _SHORTCUT_GESTURE_ORDER if gesture_id in SHORTCUT_GESTURES
    ]
    ordered.extend(sorted(SHORTCUT_GESTURES.difference(ordered)))
    return tuple(ordered)


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

    def force_refresh(self) -> None: ...


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

    def refresh(self, config: AppConfig) -> None:
        if self._backend is not None:
            self._backend.force_refresh()
        self.update(config)

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()
        self.visible = False
        self._backend = None


class SettingsWindow:
    """Windows-style modal-like settings dialog for AirPilot.

    Accessible via the 'S' key while the preview is focused.
    Apply persists to the config file; Cancel discards; Reset restores defaults.
    """

    def __init__(
        self,
        config: AppConfig,
        config_path: Path | None = None,
        *,
        on_apply: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._config_path = config_path
        self._on_apply = on_apply
        self._root: tk.Tk | None = None
        self._window: tk.Toplevel | None = None

    def open(self) -> None:
        if self.is_open():
            return
        self._root = _TkSharedRoot.acquire()
        self._window = tk.Toplevel(self._root)
        self._window.title("AirPilot Settings")
        self._window.resizable(True, True)
        self._window.minsize(560, 440)
        self._window.protocol("WM_DELETE_WINDOW", self.close)
        # Apply configured opacity (bounded 0.1–1.0)
        opacity = max(0.1, min(1.0, self._config.text_styles.settings_opacity))
        with suppress(tk.TclError):
            self._window.attributes("-alpha", opacity)
        self._build_ui()

    def is_open(self) -> bool:
        if self._window is None:
            return False
        try:
            return bool(self._window.winfo_exists())
        except tk.TclError:
            return False

    def update(self) -> None:
        if not self.is_open():
            return
        try:
            _TkSharedRoot.pump()
        except tk.TclError:
            self.close()

    def close(self) -> None:
        with suppress(tk.TclError):
            if self._window is not None:
                self._window.destroy()
        self._window = None
        if self._root is not None:
            _TkSharedRoot.release()
            self._root = None

    # ------------------------------------------------------------------
    # Private UI construction helpers
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        win = self._window
        assert win is not None

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # --- Mouse / activation tab ---
        mouse_frame = ttk.Frame(nb, padding=10)
        nb.add(mouse_frame, text="Mouse & Activation")
        self._mouse_vars: dict[str, tk.Variable] = {}
        self._build_mouse_tab(mouse_frame)

        # --- Scroll tab ---
        scroll_frame = ttk.Frame(nb, padding=10)
        nb.add(scroll_frame, text="Scroll")
        self._scroll_vars: dict[str, tk.Variable] = {}
        self._build_scroll_tab(scroll_frame)

        # --- Gesture Bindings tab ---
        bindings_frame = ttk.Frame(nb, padding=10)
        nb.add(bindings_frame, text="Gesture Bindings")
        self._build_bindings_tab(bindings_frame)

        # --- Shortcut-mode mappings tab ---
        shortcuts_frame = ttk.Frame(nb, padding=10)
        nb.add(shortcuts_frame, text="Shortcut Mode")
        self._shortcut_action_vars: dict[str, tk.StringVar] = {}
        self._build_shortcut_actions_tab(shortcuts_frame)

        # --- Typography tab ---
        typo_frame = ttk.Frame(nb, padding=10)
        nb.add(typo_frame, text="Typography")
        self._typo_vars: dict[str, tk.Variable] = {}
        self._build_typography_tab(typo_frame)

        # --- Buttons ---
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="Apply", command=self._apply).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Cancel", command=self.close).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Reset to defaults", command=self._reset).pack(
            side="left", padx=(0, 4)
        )

    def _build_mouse_tab(self, frame: ttk.Frame) -> None:
        g = self._config.gestures
        c = self._config.cursor
        rows: list[tuple[str, str, tk.Variable, tuple[str, ...]]] = [
            (
                "Thumb angle target (°)",
                "Target thumb-to-hand angle for activation (0–180)",
                tk.DoubleVar(value=g.thumb_angle_target_deg),
                ("from_", "to", "increment"),
            ),
            (
                "Thumb angle tolerance (°)",
                "±degrees around target; active range is target±tolerance",
                tk.DoubleVar(value=g.thumb_angle_tolerance_deg),
                ("from_", "to", "increment"),
            ),
            (
                "Activation hysteresis (°)",
                "Extra tolerance while pointer is active (prevents jitter at boundary)",
                tk.DoubleVar(value=g.thumb_angle_hysteresis_deg),
                ("from_", "to", "increment"),
            ),
            (
                "Pointer sensitivity",
                "Speed multiplier for cursor movement (0.1–10.0)",
                tk.DoubleVar(value=c.sensitivity),
                ("from_", "to", "increment"),
            ),
            (
                "Horizontal hand range %",
                "Camera width used to reach screen edges (20–100; lower = faster)",
                tk.IntVar(value=int(round((c.camera_max_x - c.camera_min_x) * 100))),
                ("from_", "to", "increment"),
            ),
            (
                "Vertical hand range %",
                "Camera height used to reach screen edges (20–100; lower = faster)",
                tk.IntVar(value=int(round((c.camera_max_y - c.camera_min_y) * 100))),
                ("from_", "to", "increment"),
            ),
            (
                "Pointer smoothing (0–1)",
                "Alpha for EMA smoothing; 1.0 = instant, 0.1 = very smooth",
                tk.DoubleVar(value=c.smoothing_alpha),
                ("from_", "to", "increment"),
            ),
            (
                "Pointer dead zone (px)",
                "Minimum pixel displacement to move cursor",
                tk.IntVar(value=c.dead_zone_px),
                ("from_", "to", "increment"),
            ),
        ]
        spin_ranges = {
            "Thumb angle target (°)": (0.0, 180.0, 1.0),
            "Thumb angle tolerance (°)": (1.0, 45.0, 0.5),
            "Activation hysteresis (°)": (0.0, 30.0, 0.5),
            "Pointer sensitivity": (0.1, 10.0, 0.05),
            "Horizontal hand range %": (20, 100, 1),
            "Vertical hand range %": (20, 100, 1),
            "Pointer smoothing (0–1)": (0.05, 1.0, 0.01),
            "Pointer dead zone (px)": (0, 20, 1),
        }
        for row_idx, (label, hint, var, _) in enumerate(rows):
            lo, hi, inc = spin_ranges[label]
            ttk.Label(frame, text=label, anchor="w").grid(row=row_idx, column=0, sticky="w", pady=3)
            sb = ttk.Spinbox(frame, textvariable=var, from_=lo, to=hi, increment=inc, width=10)
            sb.grid(row=row_idx, column=1, sticky="w", padx=(8, 0), pady=3)
            ttk.Label(frame, text=hint, foreground="gray", anchor="w").grid(
                row=row_idx, column=2, sticky="w", padx=(12, 0), pady=3
            )
            self._mouse_vars[label] = var
        frame.columnconfigure(2, weight=1)

        # Use angle activation checkbox
        self._use_angle_var = tk.BooleanVar(value=g.use_thumb_angle_activation)
        cb_row = len(rows)
        ttk.Checkbutton(
            frame,
            text="Use angle-based activation (recommended)",
            variable=self._use_angle_var,
        ).grid(row=cb_row, column=0, columnspan=3, sticky="w", pady=(8, 3))

    def _build_shortcut_actions_tab(self, frame: ttk.Frame) -> None:
        ttk.Label(
            frame,
            text=(
                "Edit the built-in two-hand Shortcut Mode gesture mappings. "
                "Choose an enabled catalog action, or leave blank to disable a mapping."
            ),
            wraplength=520,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        action_ids = sorted(
            action_id
            for action_id, entry in self._config.actions.catalog.items()
            if not action_id.startswith("custom.")
            and (entry.enabled or action_id.startswith("ui."))
        )
        values = [""] + action_ids
        for row_idx, gesture_id in enumerate(_editable_shortcut_gesture_ids(), start=1):
            ttk.Label(frame, text=_gesture_label(gesture_id) + ":", anchor="e").grid(
                row=row_idx, column=0, sticky="e", pady=3, padx=(0, 8)
            )
            var = tk.StringVar(value=self._config.actions.gesture_actions.get(gesture_id, ""))
            ttk.Combobox(frame, textvariable=var, values=values, state="readonly", width=28).grid(
                row=row_idx, column=1, sticky="ew", pady=3
            )
            self._shortcut_action_vars[gesture_id] = var
            ttk.Label(frame, text=gesture_id, foreground="gray", anchor="w").grid(
                row=row_idx, column=2, sticky="w", padx=(10, 0), pady=3
            )
        frame.columnconfigure(1, weight=1)

    def _build_scroll_tab(self, frame: ttk.Frame) -> None:
        g = self._config.gestures
        rows = [
            (
                "Scroll sensitivity",
                "Speed of scroll (0.1–10.0)",
                tk.DoubleVar(value=g.scroll_sensitivity),
                0.1,
                10.0,
                0.1,
            ),
            (
                "Scroll dead zone",
                "Min hand displacement before scrolling starts (0–0.1)",
                tk.DoubleVar(value=g.scroll_dead_zone),
                0.0,
                0.1,
                0.002,
            ),
            (
                "Units per step",
                "Scroll wheel units per gesture step (1–20)",
                tk.IntVar(value=g.scroll_units_per_step),
                1,
                20,
                1,
            ),
        ]
        for row_idx, (label, hint, var, lo, hi, inc) in enumerate(rows):
            ttk.Label(frame, text=label, anchor="w").grid(row=row_idx, column=0, sticky="w", pady=3)
            ttk.Spinbox(frame, textvariable=var, from_=lo, to=hi, increment=inc, width=10).grid(
                row=row_idx, column=1, sticky="w", padx=(8, 0), pady=3
            )
            ttk.Label(frame, text=hint, foreground="gray", anchor="w").grid(
                row=row_idx, column=2, sticky="w", padx=(12, 0), pady=3
            )
            self._scroll_vars[label] = var

        self._natural_dir_var = tk.BooleanVar(value=g.scroll_natural_direction)
        nd_row = len(rows)
        ttk.Checkbutton(
            frame,
            text="Natural scroll direction (reverses scroll sign)",
            variable=self._natural_dir_var,
        ).grid(row=nd_row, column=0, columnspan=3, sticky="w", pady=(8, 3))
        frame.columnconfigure(2, weight=1)

    # ------------------------------------------------------------------
    # Typography tab
    # ------------------------------------------------------------------

    def _build_typography_tab(self, frame: ttk.Frame) -> None:
        """Build the text style settings tab."""
        ts = self._config.text_styles
        rows: list[tuple[str, str, tk.Variable, float, float, float]] = [
            (
                "Overlay scale %",
                "Scale overlay text (50–200; 100 = default)",
                tk.IntVar(value=ts.overlay_scale_pct),
                50,
                200,
                5,
            ),
            (
                "Sidebar scale %",
                "Scale sidebar text (50–200; 100 = default)",
                tk.IntVar(value=ts.sidebar_scale_pct),
                50,
                200,
                5,
            ),
            (
                "Help font size",
                "Help window font size in pt (6–24)",
                tk.IntVar(value=ts.help_font_size),
                6,
                24,
                1,
            ),
            (
                "Settings font size",
                "Settings window font size (0 = system default)",
                tk.IntVar(value=ts.settings_font_size),
                0,
                24,
                1,
            ),
            (
                "Help opacity",
                "Help window opacity (0.1–1.0; 1.0 = fully opaque)",
                tk.DoubleVar(value=ts.help_opacity),
                0.1,
                1.0,
                0.05,
            ),
            (
                "Settings opacity",
                "Settings window opacity (0.1–1.0; 1.0 = fully opaque)",
                tk.DoubleVar(value=ts.settings_opacity),
                0.1,
                1.0,
                0.05,
            ),
            (
                "Overlay bg opacity",
                "Overlay/status background opacity (0.0 = off, 1.0 = solid)",
                tk.DoubleVar(value=ts.overlay_bg_opacity),
                0.0,
                1.0,
                0.05,
            ),
            (
                "Sidebar bg opacity",
                "Sidebar/dashboard background opacity (0.0 = off, 1.0 = solid)",
                tk.DoubleVar(value=ts.sidebar_bg_opacity),
                0.0,
                1.0,
                0.05,
            ),
        ]
        for row_idx, (label, hint, var, lo, hi, inc) in enumerate(rows):
            ttk.Label(frame, text=label, anchor="w").grid(row=row_idx, column=0, sticky="w", pady=3)
            ttk.Spinbox(frame, textvariable=var, from_=lo, to=hi, increment=inc, width=10).grid(
                row=row_idx, column=1, sticky="w", padx=(8, 0), pady=3
            )
            ttk.Label(frame, text=hint, foreground="gray", anchor="w").grid(
                row=row_idx, column=2, sticky="w", padx=(12, 0), pady=3
            )
            self._typo_vars[label] = var

        # Text entry fields for font family and hex colors
        str_rows: list[tuple[str, str, tk.StringVar]] = [
            (
                "Overlay fg color",
                "#ffffff format; white = #ffffff",
                tk.StringVar(value=ts.overlay_fg),
            ),
            ("Sidebar fg color", "#e6e6e6 format", tk.StringVar(value=ts.sidebar_fg)),
            (
                "Sidebar bg color",
                "#141414 format; dark panel bg",
                tk.StringVar(value=ts.sidebar_bg),
            ),
            (
                "Help font family",
                "e.g. Consolas, Courier, monospace",
                tk.StringVar(value=ts.help_font_family),
            ),
            (
                "Settings font family",
                "Leave empty for system default",
                tk.StringVar(value=ts.settings_font_family),
            ),
        ]
        base_row = len(rows)
        for row_idx, (label, hint, var) in enumerate(str_rows):
            ttk.Label(frame, text=label, anchor="w").grid(
                row=base_row + row_idx, column=0, sticky="w", pady=3
            )
            ttk.Entry(frame, textvariable=var, width=18).grid(
                row=base_row + row_idx, column=1, sticky="w", padx=(8, 0), pady=3
            )
            ttk.Label(frame, text=hint, foreground="gray", anchor="w").grid(
                row=base_row + row_idx, column=2, sticky="w", padx=(12, 0), pady=3
            )
            self._typo_vars[label] = var

        # Sidebar enabled toggle
        self._sidebar_enabled_var = tk.BooleanVar(value=ts.sidebar_enabled)
        en_row = base_row + len(str_rows)
        ttk.Checkbutton(
            frame,
            text="Show gesture sidebar in preview",
            variable=self._sidebar_enabled_var,
        ).grid(row=en_row, column=0, columnspan=3, sticky="w", pady=(8, 3))
        frame.columnconfigure(2, weight=1)

    _FINGER_OPTIONS = ("any", "folded", "extended")
    _MOVEMENT_OPTIONS = ("none", "left", "right", "up", "down")
    _TRIGGER_OPTIONS = ("enter", "hold_repeat", "release")
    _HAND_OPTIONS = ("either", "control", "secondary", "left", "right")

    def _build_bindings_tab(self, frame: ttk.Frame) -> None:
        """Build a list + detail form UI for editing gesture bindings."""
        # Working copy so Cancel discards changes
        import copy

        self._bindings_work: list[GestureBinding] = copy.deepcopy(self._config.gesture_bindings)

        # Left: binding list
        list_frame = ttk.Frame(frame)
        list_frame.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(list_frame, text="Bindings", font=("TkDefaultFont", 0, "bold")).pack(anchor="w")
        self._binding_listbox = tk.Listbox(
            list_frame, activestyle="dotbox", exportselection=False, width=22, height=12
        )
        self._binding_listbox.pack(fill="y", expand=True)
        self._binding_listbox.bind("<<ListboxSelect>>", self._on_binding_select)

        btn_row = ttk.Frame(list_frame)
        btn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_row, text="New", command=self._binding_new, width=6).pack(
            side="left", padx=(0, 2)
        )
        ttk.Button(btn_row, text="Delete", command=self._binding_delete, width=6).pack(side="left")

        # Right: detail form
        detail = ttk.LabelFrame(frame, text="Binding details", padding=8)
        detail.grid(row=0, column=1, sticky="nsew")

        rows_def: list[tuple[str, str]] = [
            ("ID", "id"),
            ("Hand", "hand"),
            ("Thumb", "thumb"),
            ("Index", "index"),
            ("Middle", "middle"),
            ("Ring", "ring"),
            ("Pinky", "pinky"),
            ("Movement", "movement"),
            ("Trigger", "trigger"),
            ("Threshold", "threshold"),
            ("Hold (ms)", "hold_ms"),
            ("Cooldown (ms)", "cooldown_ms"),
            ("Sensitivity", "sensitivity"),
        ]
        self._bfield_vars: dict[str, tk.Variable] = {}
        combo_options: dict[str, tuple[str, ...]] = {
            "hand": self._HAND_OPTIONS,
            "thumb": self._FINGER_OPTIONS,
            "index": self._FINGER_OPTIONS,
            "middle": self._FINGER_OPTIONS,
            "ring": self._FINGER_OPTIONS,
            "pinky": self._FINGER_OPTIONS,
            "movement": self._MOVEMENT_OPTIONS,
            "trigger": self._TRIGGER_OPTIONS,
        }
        for row_idx, (label, attr) in enumerate(rows_def):
            ttk.Label(detail, text=label + ":", anchor="e").grid(
                row=row_idx, column=0, sticky="e", pady=2, padx=(0, 6)
            )
            if attr in ("threshold", "sensitivity"):
                var: tk.Variable = tk.DoubleVar()
                ttk.Spinbox(
                    detail, textvariable=var, from_=0.0, to=5.0, increment=0.01, width=12
                ).grid(row=row_idx, column=1, sticky="w", pady=2)
            elif attr in ("hold_ms", "cooldown_ms"):
                var = tk.IntVar()
                ttk.Spinbox(
                    detail, textvariable=var, from_=0, to=10000, increment=50, width=12
                ).grid(row=row_idx, column=1, sticky="w", pady=2)
            elif attr in combo_options:
                var = tk.StringVar()
                ttk.Combobox(
                    detail,
                    textvariable=var,
                    values=combo_options[attr],
                    state="readonly",
                    width=12,
                ).grid(row=row_idx, column=1, sticky="w", pady=2)
            else:
                var = tk.StringVar()
                ttk.Entry(detail, textvariable=var, width=18).grid(
                    row=row_idx, column=1, sticky="ew", pady=2
                )
            self._bfield_vars[attr] = var

        # Shortcut recorder — replaces the old free-text Action ID entry
        shortcut_row = len(rows_def)
        ttk.Label(detail, text="Shortcut:", anchor="e").grid(
            row=shortcut_row, column=0, sticky="e", pady=2, padx=(0, 6)
        )
        self._shortcut_display_var = tk.StringVar(value="—")
        self._recorded_shortcut_keys: tuple[str, ...] = ()
        self._recording_modifiers: set[str] = set()
        self._recording_active = False
        sc_frame = ttk.Frame(detail)
        sc_frame.grid(row=shortcut_row, column=1, sticky="ew", pady=2)
        self._shortcut_display_lbl = ttk.Label(
            sc_frame,
            textvariable=self._shortcut_display_var,
            relief="sunken",
            width=18,
            anchor="w",
        )
        self._shortcut_display_lbl.pack(side="left", padx=(0, 4))
        self._record_btn = ttk.Button(sc_frame, text="Record…", command=self._start_recording)
        self._record_btn.pack(side="left", padx=(0, 2))
        ttk.Button(sc_frame, text="Clear", command=self._clear_shortcut).pack(side="left")

        # Catalog action selector
        catalog_row = shortcut_row + 1
        ttk.Label(detail, text="Catalog action:", anchor="e").grid(
            row=catalog_row, column=0, sticky="e", pady=2, padx=(0, 6)
        )
        catalog_ids = sorted(
            aid for aid, e in self._config.actions.catalog.items() if not aid.startswith("custom.")
        )
        self._catalog_action_var = tk.StringVar(value="")
        catalog_combo = ttk.Combobox(
            detail,
            textvariable=self._catalog_action_var,
            values=[""] + catalog_ids,
            state="readonly",
            width=22,
        )
        catalog_combo.grid(row=catalog_row, column=1, sticky="ew", pady=2)
        catalog_combo.bind("<<ComboboxSelected>>", self._on_catalog_action_selected)

        # Conflict warning label
        self._shortcut_conflict_var = tk.StringVar()
        ttk.Label(
            detail,
            textvariable=self._shortcut_conflict_var,
            foreground="orange",
            wraplength=260,
            justify="left",
        ).grid(row=catalog_row + 1, column=0, columnspan=2, sticky="w", pady=(0, 2))

        # Enabled checkbox
        en_row = catalog_row + 2
        self._binding_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(
            detail,
            text="Enabled (activate this binding)",
            variable=self._binding_enabled_var,
        ).grid(row=en_row, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Button(detail, text="Save binding", command=self._binding_save).grid(
            row=en_row + 1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        detail.columnconfigure(1, weight=1)

        # Validation error label at bottom
        self._binding_error_var = tk.StringVar()
        ttk.Label(
            frame,
            textvariable=self._binding_error_var,
            foreground="red",
            wraplength=380,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self._refresh_binding_list()
        self._current_binding_idx: int | None = None

    # ------------------------------------------------------------------
    # Shortcut recorder methods
    # ------------------------------------------------------------------

    def _start_recording(self) -> None:
        """Enter keyboard-shortcut recording mode."""
        self._recording_active = True
        self._recording_modifiers = set()
        self._recorded_shortcut_keys = ()
        self._shortcut_display_var.set("Waiting for shortcut…")
        self._shortcut_conflict_var.set("")
        self._record_btn.configure(state="disabled")
        win = self._window
        if win is not None:
            win.bind("<KeyPress>", self._on_record_keypress)
            win.bind("<KeyRelease>", self._on_record_keyrelease)
            win.focus_set()

    def _on_record_keypress(self, event: tk.Event[tk.Misc]) -> None:
        if not self._recording_active:
            return
        from airpilot.shortcut_recorder import MODIFIER_KEYS, keysym_to_canonical

        canonical = keysym_to_canonical(event.keysym)
        if canonical is None:
            return
        if canonical == "esc":
            self._cancel_recording()
            return
        if canonical in MODIFIER_KEYS:
            self._recording_modifiers.add(canonical)
            # Show live modifiers while waiting for a non-modifier key
            partial = sorted(
                self._recording_modifiers,
                key=lambda k: {"ctrl": 0, "shift": 1, "alt": 2, "win": 3}.get(k, 99),
            )
            self._shortcut_display_var.set("+".join(shortcut_label((k,)) for k in partial) + "+…")
        else:
            # Non-modifier key completes the recording
            keys_raw = tuple(self._recording_modifiers) + (canonical,)
            self._finish_recording(keys_raw)

    def _on_record_keyrelease(self, event: tk.Event[tk.Misc]) -> None:
        if not self._recording_active:
            return
        from airpilot.shortcut_recorder import MODIFIER_KEYS, keysym_to_canonical

        canonical = keysym_to_canonical(event.keysym)
        if canonical in MODIFIER_KEYS:
            self._recording_modifiers.discard(canonical)

    def _finish_recording(self, keys_raw: tuple[str, ...]) -> None:
        self._recording_active = False
        self._unbind_recording()
        self._record_btn.configure(state="normal")
        normalized = normalize_shortcut(keys_raw)
        risky_ok = self._config.actions.risky_actions_enabled
        error = validate_shortcut(normalized, risky_ok=risky_ok)
        if error:
            self._shortcut_display_var.set(f"⚠ {error}")
            self._recorded_shortcut_keys = ()
            return
        self._recorded_shortcut_keys = normalized
        self._shortcut_display_var.set(shortcut_label(normalized))
        self._catalog_action_var.set("")
        self._update_conflict_warning(normalized)

    def _cancel_recording(self) -> None:
        self._recording_active = False
        self._unbind_recording()
        self._record_btn.configure(state="normal")
        if self._recorded_shortcut_keys:
            self._shortcut_display_var.set(shortcut_label(self._recorded_shortcut_keys))
        else:
            self._shortcut_display_var.set("—")

    def _unbind_recording(self) -> None:
        win = self._window
        if win is not None:
            with suppress(tk.TclError):
                win.unbind("<KeyPress>")
            with suppress(tk.TclError):
                win.unbind("<KeyRelease>")

    def _clear_shortcut(self) -> None:
        self._recorded_shortcut_keys = ()
        self._shortcut_display_var.set("—")
        self._shortcut_conflict_var.set("")
        self._catalog_action_var.set("")

    def _on_catalog_action_selected(self, _event: object = None) -> None:
        """When a catalog action is selected, clear any recorded shortcut."""
        action_id = str(self._catalog_action_var.get())
        if action_id:
            self._recorded_shortcut_keys = ()
            self._shortcut_display_var.set("—")
            self._shortcut_conflict_var.set("")

    def _update_conflict_warning(self, keys: tuple[str, ...]) -> None:
        idx = self._current_binding_idx
        conflicts = detect_shortcut_conflicts(keys, self._bindings_work, skip_index=idx)
        if conflicts:
            names = ", ".join(f"'{c.conflicting_binding_id}'" for c in conflicts[:3])
            self._shortcut_conflict_var.set(
                f"⚠ Conflict with {names} — overlapping gesture / same shortcut. "
                "Saving will override."
            )
        else:
            self._shortcut_conflict_var.set("")

    def _refresh_binding_list(self) -> None:
        lb = self._binding_listbox
        lb.delete(0, tk.END)
        # Detect per-binding conflicts for visual indicators
        conflict_ids: set[str] = set()
        for i, b in enumerate(self._bindings_work):
            if b.shortcut_keys:
                matches = detect_shortcut_conflicts(
                    tuple(b.shortcut_keys), self._bindings_work, skip_index=i
                )
                if matches:
                    conflict_ids.add(b.id)
        for b in self._bindings_work:
            prefix = "[on] " if b.enabled else "[off]"
            warn = " ⚠" if b.id in conflict_ids else ""
            lb.insert(tk.END, f"{prefix} {b.id or '(unnamed)'}{warn}")
        self._validate_bindings_display()

    def _validate_bindings_display(self) -> None:
        errors = validate_gesture_bindings(self._bindings_work)
        if errors:
            self._binding_error_var.set(
                "Validation: " + "; ".join(errors[:3]) + (" (…more)" if len(errors) > 3 else "")
            )
        else:
            self._binding_error_var.set("")

    def _on_binding_select(self, _event: tk.Event[tk.Listbox]) -> None:
        sel = self._binding_listbox.curselection()  # type: ignore[no-untyped-call]
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._bindings_work):
            return
        self._current_binding_idx = idx
        b = self._bindings_work[idx]
        fv = self._bfield_vars
        fv["id"].set(b.id)
        fv["hand"].set(b.hand)
        fv["thumb"].set(b.thumb)
        fv["index"].set(b.index)
        fv["middle"].set(b.middle)
        fv["ring"].set(b.ring)
        fv["pinky"].set(b.pinky)
        fv["movement"].set(b.movement)
        fv["trigger"].set(b.trigger)
        fv["threshold"].set(b.threshold)
        fv["hold_ms"].set(b.hold_ms)
        fv["cooldown_ms"].set(b.cooldown_ms)
        fv["sensitivity"].set(b.sensitivity)
        self._binding_enabled_var.set(b.enabled)
        # Load shortcut recorder state
        if b.shortcut_keys:
            self._recorded_shortcut_keys = tuple(b.shortcut_keys)
            self._shortcut_display_var.set(shortcut_label(self._recorded_shortcut_keys))
            self._catalog_action_var.set("")
        else:
            self._recorded_shortcut_keys = ()
            self._shortcut_display_var.set("—")
            # Show catalog action if binding uses one and it's not a custom auto-entry
            if b.action_id and not b.action_id.startswith("custom."):
                self._catalog_action_var.set(b.action_id)
            else:
                self._catalog_action_var.set("")
        self._shortcut_conflict_var.set("")

    def _binding_save(self) -> None:
        idx = self._current_binding_idx
        if idx is None or idx >= len(self._bindings_work):
            return
        fv = self._bfield_vars
        try:
            # Determine shortcut_keys and action_id from recorder / catalog selector
            recorded = self._recorded_shortcut_keys
            catalog_sel = str(self._catalog_action_var.get()).strip()
            if recorded:
                shortcut_keys: tuple[str, ...] = recorded
                action_id_val = ""
            elif catalog_sel:
                shortcut_keys = ()
                action_id_val = catalog_sel
            else:
                shortcut_keys = ()
                action_id_val = ""
            new_b = GestureBinding(
                id=str(fv["id"].get()).strip(),  # type: ignore[no-untyped-call]
                enabled=bool(self._binding_enabled_var.get()),
                hand=str(fv["hand"].get()),  # type: ignore[no-untyped-call]
                thumb=str(fv["thumb"].get()),  # type: ignore[no-untyped-call]
                index=str(fv["index"].get()),  # type: ignore[no-untyped-call]
                middle=str(fv["middle"].get()),  # type: ignore[no-untyped-call]
                ring=str(fv["ring"].get()),  # type: ignore[no-untyped-call]
                pinky=str(fv["pinky"].get()),  # type: ignore[no-untyped-call]
                movement=str(fv["movement"].get()),  # type: ignore[no-untyped-call]
                trigger=str(fv["trigger"].get()),  # type: ignore[no-untyped-call]
                threshold=float(fv["threshold"].get()),  # type: ignore[no-untyped-call]
                hold_ms=int(fv["hold_ms"].get()),  # type: ignore[no-untyped-call]
                cooldown_ms=int(fv["cooldown_ms"].get()),  # type: ignore[no-untyped-call]
                sensitivity=float(fv["sensitivity"].get()),  # type: ignore[no-untyped-call]
                action_id=action_id_val,
                shortcut_keys=shortcut_keys,
            )
        except (ValueError, tk.TclError):
            self._binding_error_var.set("Invalid field value — check numeric fields.")
            return

        # Conflict detection with confirmation
        if shortcut_keys:
            conflicts = detect_shortcut_conflicts(
                shortcut_keys, self._bindings_work, skip_index=idx
            )
            if conflicts:
                from tkinter import messagebox

                names = "\n".join(
                    f"  • '{c.conflicting_binding_id}' ({c.conflicting_context})"
                    for c in conflicts[:5]
                )
                msg = (
                    f"The shortcut {shortcut_label(shortcut_keys)!r} is already assigned in:\n"
                    f"{names}\n\n"
                    "Override those assignments?"
                )
                if not messagebox.askyesno("Shortcut Conflict", msg, icon="warning"):
                    return
                # Atomically clear the conflicting bindings' shortcut_keys
                for c in conflicts:
                    for j, other in enumerate(self._bindings_work):
                        if other.id == c.conflicting_binding_id and j != idx:
                            self._bindings_work[j] = GestureBinding(
                                id=other.id,
                                enabled=other.enabled,
                                hand=other.hand,
                                thumb=other.thumb,
                                index=other.index,
                                middle=other.middle,
                                ring=other.ring,
                                pinky=other.pinky,
                                movement=other.movement,
                                trigger=other.trigger,
                                threshold=other.threshold,
                                hold_ms=other.hold_ms,
                                cooldown_ms=other.cooldown_ms,
                                sensitivity=other.sensitivity,
                                action_id=other.action_id,
                                shortcut_keys=(),
                            )
                            break

        self._bindings_work[idx] = new_b
        self._shortcut_conflict_var.set("")
        self._refresh_binding_list()

    def _binding_new(self) -> None:
        import uuid

        new_b = GestureBinding(id=f"binding_{uuid.uuid4().hex[:6]}", enabled=False)
        self._bindings_work.append(new_b)
        self._refresh_binding_list()
        self._binding_listbox.selection_clear(0, tk.END)
        last_idx = len(self._bindings_work) - 1
        self._binding_listbox.selection_set(last_idx)
        self._binding_listbox.see(last_idx)
        self._current_binding_idx = last_idx
        self._on_binding_select(tk.Event())

    def _binding_delete(self) -> None:
        sel = self._binding_listbox.curselection()  # type: ignore[no-untyped-call]
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._bindings_work):
            del self._bindings_work[idx]
            self._current_binding_idx = None
            self._refresh_binding_list()

    def _apply(self) -> None:
        """Write UI values into the live config and persist."""
        g = self._config.gestures
        c = self._config.cursor
        try:
            if hasattr(self, "_bindings_work"):
                binding_errors = validate_gesture_bindings(self._bindings_work)
                if binding_errors:
                    self._binding_error_var.set(
                        "Validation: "
                        + "; ".join(binding_errors[:3])
                        + (" (…more)" if len(binding_errors) > 3 else "")
                    )
                    return
            updated_mappings: dict[str, str] | None = None
            if hasattr(self, "_shortcut_action_vars"):
                updated_mappings = {
                    gesture_id: str(var.get()).strip()
                    for gesture_id, var in self._shortcut_action_vars.items()
                    if str(var.get()).strip()
                }
                validate_action_config(
                    ActionConfig(
                        enabled=self._config.actions.enabled,
                        risky_actions_enabled=self._config.actions.risky_actions_enabled,
                        shortcut_mode_gesture=self._config.actions.shortcut_mode_gesture,
                        gesture_actions=dict(updated_mappings),
                        catalog=dict(self._config.actions.catalog),
                    )
                )

            mv = self._mouse_vars
            g.thumb_angle_target_deg = float(mv["Thumb angle target (°)"].get())  # type: ignore[no-untyped-call]
            g.thumb_angle_tolerance_deg = float(mv["Thumb angle tolerance (°)"].get())  # type: ignore[no-untyped-call]
            g.thumb_angle_hysteresis_deg = float(mv["Activation hysteresis (°)"].get())  # type: ignore[no-untyped-call]
            g.use_thumb_angle_activation = bool(self._use_angle_var.get())
            c.sensitivity = float(mv["Pointer sensitivity"].get())  # type: ignore[no-untyped-call]
            horizontal_range_pct = int(mv["Horizontal hand range %"].get())  # type: ignore[no-untyped-call]
            vertical_range_pct = int(mv["Vertical hand range %"].get())  # type: ignore[no-untyped-call]
            c.smoothing_alpha = float(mv["Pointer smoothing (0–1)"].get())  # type: ignore[no-untyped-call]
            c.dead_zone_px = int(mv["Pointer dead zone (px)"].get())  # type: ignore[no-untyped-call]

            sv = self._scroll_vars
            g.scroll_sensitivity = float(sv["Scroll sensitivity"].get())  # type: ignore[no-untyped-call]
            g.scroll_dead_zone = float(sv["Scroll dead zone"].get())  # type: ignore[no-untyped-call]
            g.scroll_units_per_step = int(sv["Units per step"].get())  # type: ignore[no-untyped-call]
            g.scroll_natural_direction = bool(self._natural_dir_var.get())

            # Clamp to safe ranges
            g.thumb_angle_target_deg = max(0.0, min(180.0, g.thumb_angle_target_deg))
            g.thumb_angle_tolerance_deg = max(1.0, min(45.0, g.thumb_angle_tolerance_deg))
            g.thumb_angle_hysteresis_deg = max(0.0, min(30.0, g.thumb_angle_hysteresis_deg))
            c.sensitivity = max(0.1, min(10.0, c.sensitivity))
            horizontal_range = max(20, min(100, horizontal_range_pct)) / 100.0
            vertical_range = max(20, min(100, vertical_range_pct)) / 100.0
            c.camera_min_x = 0.5 - horizontal_range / 2.0
            c.camera_max_x = 0.5 + horizontal_range / 2.0
            c.camera_min_y = 0.5 - vertical_range / 2.0
            c.camera_max_y = 0.5 + vertical_range / 2.0
            c.smoothing_alpha = max(0.05, min(1.0, c.smoothing_alpha))
            c.dead_zone_px = max(0, min(20, c.dead_zone_px))
            g.scroll_sensitivity = max(0.1, min(10.0, g.scroll_sensitivity))
            g.scroll_dead_zone = max(0.0, min(0.1, g.scroll_dead_zone))
            g.scroll_units_per_step = max(1, min(20, g.scroll_units_per_step))

            # Gesture bindings — update list in-place so GestureBindingMatcher reference stays valid
            if hasattr(self, "_bindings_work"):
                del self._config.gesture_bindings[:]
                self._config.gesture_bindings.extend(self._bindings_work)
                sync_custom_shortcuts(self._config)

            if updated_mappings is not None:
                self._config.actions.gesture_actions.clear()
                self._config.actions.gesture_actions.update(updated_mappings)

            # Typography settings
            if hasattr(self, "_typo_vars"):
                ts = self._config.text_styles
                tv = self._typo_vars
                ts.overlay_scale_pct = max(50, min(200, int(tv["Overlay scale %"].get())))  # type: ignore[no-untyped-call]
                ts.sidebar_scale_pct = max(50, min(200, int(tv["Sidebar scale %"].get())))  # type: ignore[no-untyped-call]
                ts.help_font_size = max(6, min(24, int(tv["Help font size"].get())))  # type: ignore[no-untyped-call]
                ts.settings_font_size = max(0, min(24, int(tv["Settings font size"].get())))  # type: ignore[no-untyped-call]
                ts.overlay_fg = str(tv["Overlay fg color"].get()).strip() or "#ffffff"  # type: ignore[no-untyped-call]
                ts.sidebar_fg = str(tv["Sidebar fg color"].get()).strip() or "#e6e6e6"  # type: ignore[no-untyped-call]
                ts.sidebar_bg = str(tv["Sidebar bg color"].get()).strip() or "#141414"  # type: ignore[no-untyped-call]
                ts.help_font_family = str(tv["Help font family"].get()).strip()  # type: ignore[no-untyped-call]
                ts.settings_font_family = str(tv["Settings font family"].get()).strip()  # type: ignore[no-untyped-call]
                ts.sidebar_enabled = bool(self._sidebar_enabled_var.get())
                if "Help opacity" in tv:
                    ts.help_opacity = max(0.1, min(1.0, float(tv["Help opacity"].get())))  # type: ignore[no-untyped-call]
                if "Settings opacity" in tv:
                    ts.settings_opacity = max(0.1, min(1.0, float(tv["Settings opacity"].get())))  # type: ignore[no-untyped-call]
                if "Overlay bg opacity" in tv:
                    ts.overlay_bg_opacity = max(
                        0.0,
                        min(1.0, float(tv["Overlay bg opacity"].get())),  # type: ignore[no-untyped-call]
                    )
                if "Sidebar bg opacity" in tv:
                    ts.sidebar_bg_opacity = max(
                        0.0,
                        min(1.0, float(tv["Sidebar bg opacity"].get())),  # type: ignore[no-untyped-call]
                    )

            validate_action_config(self._config.actions)
            save_config(self._config, self._config_path)
            if self._on_apply is not None:
                self._on_apply()
        except (ValueError, tk.TclError) as exc:
            if hasattr(self, "_binding_error_var"):
                self._binding_error_var.set(f"Settings not saved: {exc}")
            return
        self.close()

    def _reset(self) -> None:
        """Reload defaults into the UI widgets (does not persist until Apply)."""
        from airpilot.config import CursorConfig, GestureConfig, _default_gesture_bindings

        dg = GestureConfig()
        dc = CursorConfig()
        mv = self._mouse_vars
        mv["Thumb angle target (°)"].set(dg.thumb_angle_target_deg)
        mv["Thumb angle tolerance (°)"].set(dg.thumb_angle_tolerance_deg)
        mv["Activation hysteresis (°)"].set(dg.thumb_angle_hysteresis_deg)
        mv["Pointer sensitivity"].set(dc.sensitivity)
        mv["Horizontal hand range %"].set(int(round((dc.camera_max_x - dc.camera_min_x) * 100)))
        mv["Vertical hand range %"].set(int(round((dc.camera_max_y - dc.camera_min_y) * 100)))
        mv["Pointer smoothing (0–1)"].set(dc.smoothing_alpha)
        mv["Pointer dead zone (px)"].set(dc.dead_zone_px)
        self._use_angle_var.set(dg.use_thumb_angle_activation)

        sv = self._scroll_vars
        sv["Scroll sensitivity"].set(dg.scroll_sensitivity)
        sv["Scroll dead zone"].set(dg.scroll_dead_zone)
        sv["Units per step"].set(dg.scroll_units_per_step)
        self._natural_dir_var.set(dg.scroll_natural_direction)

        if hasattr(self, "_bindings_work"):
            import copy

            self._bindings_work = copy.deepcopy(_default_gesture_bindings())
            self._current_binding_idx = None
            self._refresh_binding_list()

        if hasattr(self, "_shortcut_action_vars"):
            defaults = ActionConfig()
            for gesture_id, var in self._shortcut_action_vars.items():
                var.set(defaults.gesture_actions.get(gesture_id, ""))

        if hasattr(self, "_typo_vars"):
            dt = TextStyleConfig()
            tv = self._typo_vars
            tv["Overlay scale %"].set(dt.overlay_scale_pct)
            tv["Sidebar scale %"].set(dt.sidebar_scale_pct)
            tv["Help font size"].set(dt.help_font_size)
            tv["Settings font size"].set(dt.settings_font_size)
            tv["Overlay fg color"].set(dt.overlay_fg)
            tv["Sidebar fg color"].set(dt.sidebar_fg)
            tv["Sidebar bg color"].set(dt.sidebar_bg)
            tv["Help font family"].set(dt.help_font_family)
            tv["Settings font family"].set(dt.settings_font_family)
            self._sidebar_enabled_var.set(dt.sidebar_enabled)
            if "Help opacity" in tv:
                tv["Help opacity"].set(dt.help_opacity)
            if "Settings opacity" in tv:
                tv["Settings opacity"].set(dt.settings_opacity)
            if "Overlay bg opacity" in tv:
                tv["Overlay bg opacity"].set(dt.overlay_bg_opacity)
            if "Sidebar bg opacity" in tv:
                tv["Sidebar bg opacity"].set(dt.sidebar_bg_opacity)


class _TkHelpBackend:
    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._window: tk.Toplevel | None = None
        self._tree: ttk.Treeview | None = None
        self._search_var: tk.StringVar | None = None
        self._category_list: tk.Listbox | None = None
        self._signature: str | None = None
        # Maps lowercase category title → Treeview item iid for jump
        self._section_iids: dict[str, str] = {}

    def update(self, config: AppConfig) -> None:
        if not self.is_open():
            self._create_window(config)
        # Apply opacity live
        if self._window is not None:
            opacity = max(0.1, min(1.0, config.text_styles.help_opacity))
            with suppress(tk.TclError):
                self._window.attributes("-alpha", opacity)
        sections = _help_sections(config)
        signature = json.dumps(
            [(section.title, section.lines) for section in sections],
            sort_keys=True,
        )
        filter_text = self._search_var.get().strip().lower() if self._search_var else ""
        signature = f"{signature}\nfilter={filter_text}"
        if signature != self._signature:
            self._populate_sections(sections, filter_text)
            self._signature = signature
        self._pump()

    def close(self) -> None:
        if self._window is not None:
            with suppress(tk.TclError):
                self._window.destroy()
        self._window = None
        if self._root is not None:
            _TkSharedRoot.release()
            self._root = None
        self._tree = None
        self._search_var = None
        self._category_list = None
        self._signature = None
        self._section_iids = {}

    def is_open(self) -> bool:
        if self._window is None:
            return False
        try:
            return bool(self._window.winfo_exists())
        except tk.TclError:
            return False

    def force_refresh(self) -> None:
        self._signature = None

    def _create_window(self, config: AppConfig) -> None:
        self._root = _TkSharedRoot.acquire()
        self._window = tk.Toplevel(self._root)
        self._window.title("AirPilot Help")
        self._window.minsize(640, 420)
        bounds = _help_initial_bounds(_screen_work_area(self._window))
        self._window.geometry(f"{bounds.width}x{bounds.height}+{bounds.left}+{bounds.top}")
        self._window.protocol("WM_DELETE_WINDOW", self.close)
        # Apply initial opacity
        opacity = max(0.1, min(1.0, config.text_styles.help_opacity))
        with suppress(tk.TclError):
            self._window.attributes("-alpha", opacity)

        default_font = tkfont.nametofont("TkDefaultFont")
        heading_font = default_font.copy()
        heading_font.configure(size=max(default_font.cget("size") + 3, 12), weight="bold")
        section_font = default_font.copy()
        section_font.configure(weight="bold")

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

        tree_frame = ttk.Frame(main)
        tree_frame.grid(row=2, column=1, columnspan=2, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        tree_cols = ("action", "gesture", "keys", "state")
        self._tree = ttk.Treeview(
            tree_frame,
            columns=tree_cols,
            show="tree headings",
            selectmode="none",
        )
        self._tree.heading("#0", text="✦", anchor="center")
        self._tree.column("#0", width=32, stretch=False, anchor="center", minwidth=28)
        self._tree.heading("action", text="Action")
        self._tree.column("action", width=210, stretch=True, minwidth=120)
        self._tree.heading("gesture", text="Gesture")
        self._tree.column("gesture", width=260, stretch=True, minwidth=160)
        self._tree.heading("keys", text="Keys / Shortcut")
        self._tree.column("keys", width=140, stretch=True, minwidth=80)
        self._tree.heading("state", text="State")
        self._tree.column("state", width=80, stretch=False, minwidth=60)
        self._tree.tag_configure("section", background="#d8e4f0", font=section_font)
        self._tree.tag_configure("intro_row", foreground="#444444")
        scrollbar_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        scrollbar_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

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

    def _populate_sections(self, sections: Sequence[HelpSection], filter_text: str) -> None:
        if self._tree is None or self._category_list is None:
            return
        sections = _filter_help_sections(sections, filter_text)

        # Clear existing content
        self._tree.delete(*self._tree.get_children())
        self._category_list.delete(0, tk.END)
        self._section_iids = {}

        for section in sections:
            if section.title == "INTRO":
                # INTRO content shown as a wrapped label above the table — skip from tree rows.
                continue
            # Insert collapsible section heading row
            sec_iid = self._tree.insert(
                "",
                "end",
                text="",
                values=(section.title.title(), "", "", ""),
                tags=("section",),
                open=True,
            )
            self._section_iids[section.title.lower()] = sec_iid
            self._category_list.insert(tk.END, section.title.title())

            header_text = _format_help_header()
            for line in section.lines:
                if line == header_text:
                    # Skip — column headers are shown by Treeview headings
                    continue
                if "│" in line:
                    # Formatted row: "  emoji  │ action  │ gesture  │ keys  │ state"
                    parts = [p.strip() for p in line.split("│")]
                    if len(parts) >= 5:
                        emoji = parts[0].strip()
                        action = parts[1].strip()
                        gesture = parts[2].strip()
                        keys = parts[3].strip()
                        state = parts[4].strip()
                        self._tree.insert(
                            sec_iid,
                            "end",
                            text=emoji,
                            values=(action, gesture, keys, state),
                        )
                        continue
                if line:
                    # Intro / free-text line — span all columns
                    self._tree.insert(
                        sec_iid,
                        "end",
                        text="",
                        values=(line, "", "", ""),
                        tags=("intro_row",),
                    )

    def _pump(self) -> None:
        if self._root is None:
            return
        try:
            _TkSharedRoot.pump()
        except tk.TclError:
            self.close()

    def _jump_to_category(self, _event: tk.Event[tk.Listbox]) -> None:
        if self._category_list is None or self._tree is None:
            return
        selection = self._category_list.curselection()  # type: ignore[no-untyped-call]
        if not selection:
            return
        title = self._category_list.get(selection[0]).lower()
        iid = self._section_iids.get(title)
        if iid:
            with suppress(tk.TclError):
                self._tree.see(iid)

    def _on_search_changed(self, _event: tk.Event[ttk.Entry]) -> None:
        self._signature = None


def _help_lines(config: AppConfig) -> list[str]:
    lines = ["AirPilot Help", ""] + action_help_lines(config.actions, max_actions=None)
    binding_lines = _gesture_binding_help_lines(config)
    if binding_lines:
        lines.extend(
            ["", "CUSTOM GESTURE BINDINGS", "What it does | Gesture | Shortcut/Keys | State"]
        )
        lines.extend(binding_lines)
    return lines


def _help_sections(config: AppConfig) -> list[HelpSection]:
    lines = action_help_lines(config.actions, max_actions=None)
    # Include angle config in the intro description
    tgt = config.gestures.thumb_angle_target_deg
    tol = config.gestures.thumb_angle_tolerance_deg
    activation_note = (
        f"Thumb angle activation: target {tgt:.0f}\u00b0 \u00b1{tol:.0f}\u00b0 "
        f"({tgt - tol:.0f}\u00b0\u2013{tgt + tol:.0f}\u00b0)."
        if config.gestures.use_thumb_angle_activation
        else "Thumb activation: score-based (classic mode)."
    )
    sections = [
        HelpSection(
            "INTRO",
            (
                "Most important controls are listed first. Keep AirPilot disarmed until the "
                "preview and hand tracking look stable.",
                activation_note,
                "Thumb in range: pointer moves with the palm/knuckle anchor.",
                "Thumb out of range: pointer frozen. Return thumb to range to resume.",
                "Press S to open Settings; H to toggle this Help window.",
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
            # Table header
            current_lines.append(_format_help_header())
        else:
            current_lines.append(_format_help_row(line))
    if current_title is not None:
        sections.append(HelpSection(current_title, tuple(current_lines)))
    binding_lines = _gesture_binding_help_lines(config)
    if binding_lines:
        sections.append(
            HelpSection(
                "CUSTOM GESTURE BINDINGS",
                tuple([_format_help_header(), *(_format_help_row(line) for line in binding_lines)]),
            )
        )
    return sections


def _gesture_binding_help_lines(config: AppConfig) -> list[str]:
    rows: list[str] = []
    for binding in config.gesture_bindings:
        action_label = _binding_action_label(config, binding)
        keys = shortcut_label(tuple(binding.shortcut_keys)) if binding.shortcut_keys else "--"
        state = "enabled" if binding.enabled else "available"
        if not action_label:
            state = "unassigned"
        rows.append(
            _raw_help_row(
                action_label or binding.id or "(unnamed)",
                _binding_gesture_label(binding),
                keys,
                state,
            )
        )
    return rows


def _binding_action_label(config: AppConfig, binding: GestureBinding) -> str:
    if binding.shortcut_keys:
        return shortcut_label(tuple(binding.shortcut_keys))
    entry = config.actions.catalog.get(binding.action_id)
    if entry is not None:
        return entry.label
    return binding.action_id


def _binding_gesture_label(binding: GestureBinding) -> str:
    fingers = [
        f"{name} {state}"
        for name, state in (
            ("thumb", binding.thumb),
            ("index", binding.index),
            ("middle", binding.middle),
            ("ring", binding.ring),
            ("pinky", binding.pinky),
        )
        if state != "any"
    ]
    parts = [binding.hand, *fingers]
    if binding.movement != "none":
        parts.append(f"move {binding.movement}")
    if binding.trigger != "enter":
        parts.append(binding.trigger.replace("_", " "))
    return "; ".join(parts) if parts else binding.id


def _format_help_header() -> str:
    """Format the table header row with emoji + clear column separators."""
    return "  ✦  │ Action                   │ Gesture           │ Keys              │ State"


def _raw_help_row(what: str, gesture: str, keys: str, state: str) -> str:
    return f"{what} | {gesture} | {keys} | {state}"


# Emoji lookup by action keyword for the Help table
_HELP_ACTION_EMOJIS: dict[str, str] = {
    "arm": "✅",
    "move": "🖱️",
    "pointer": "🖱️",
    "click": "👆",
    "drag": "✊",
    "scroll": "📜",
    "right click": "☝️",
    "middle click": "🖱️",
    "switch": "↔️",
    "quit": "❌",
    "help": "❓",
    "settings": "⚙️",
    "copy": "📋",
    "paste": "📌",
    "cut": "✂️",
    "undo": "↩️",
    "redo": "↪️",
    "save": "💾",
    "find": "🔍",
    "next": "▶️",
    "previous": "◀️",
    "play": "▶️",
    "pause": "⏸️",
    "mute": "🔇",
    "volume": "🔊",
    "tab": "📑",
    "lock": "🔒",
    "desktop": "🖥️",
    "task": "📋",
    "explore": "📁",
    "search": "🔍",
    "refresh": "🔄",
    "back": "⬅️",
    "forward": "➡️",
    "minimize": "🔽",
    "maximize": "🔼",
    "snap": "📐",
}


def _help_emoji_for_action(action_text: str) -> str:
    """Return the best-matching emoji for an action description."""
    lower = action_text.lower()
    for keyword, emoji in _HELP_ACTION_EMOJIS.items():
        if keyword in lower:
            return emoji
    return " "


def _format_help_row(line: str) -> str:
    """Convert a pipe-delimited help row to a │-separated Treeview row.

    No column values are truncated – the Treeview uses ``stretch=True`` columns
    and handles layout.  Truncation was the root cause of the
    ``Switch apps | Shortcut Mode + h`` display bug.
    """
    parts = [part.strip() for part in line.split(" | ")]
    if len(parts) != 4:
        return line
    emoji = _help_emoji_for_action(parts[0])
    return f"  {emoji}  │ {parts[0]}  │ {parts[1]}  │ {parts[2]}  │ {parts[3]}"


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


def _layout_overlay(
    lines: Sequence[str], width: int, *, sidebar_width: int = 0
) -> list[OverlayLine]:
    """Lay out overlay text lines with compact scales for 640×480 readability.

    Line 0 (headline): scale 0.52, height 22 px.
    Line 1 (guidance): scale 0.40, height 18 px.
    Lines 2+ (detail): scale 0.38, height 18 px.
    The banner covers only the first two lines; detail lines are drawn below
    via shadow text so they remain readable over the camera image.

    ``sidebar_width`` reserves space for the left-side gesture dashboard so
    that all overlay text is positioned to the right of the sidebar and never
    rendered behind it.
    """
    x_offset = sidebar_width + 10
    padded_width = max(width - x_offset - 14, 40)
    layout: list[OverlayLine] = []
    y = 22
    for index, text in enumerate(lines):
        if index == 0:
            scale = 0.52
            line_height = 22
        elif index == 1:
            scale = 0.40
            line_height = 18
        else:
            scale = 0.38
            line_height = 18
        layout.append(
            OverlayLine(
                text=_fit_text(text, padded_width, scale=scale),
                x=x_offset,
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
    """Draw the compact state banner covering only headline + guidance lines.

    The banner is intentionally small (≈ first-two-lines height) so that
    most of the 640×480 camera frame remains visible.  Detail lines are
    rendered outside the banner via shadow text in :func:`_draw_status`.
    """
    if mouse_output_locked:
        color = (120, 80, 0)
    elif paused:
        color = (0, 0, 180)
    elif armed:
        color = (0, 140, 0)
    else:
        color = (0, 80, 180)
    # Cover only lines 0 and 1 so the banner stays compact.
    if len(layout) >= 2:
        banner_height = layout[1].y + 10
    elif layout:
        banner_height = layout[0].y + 10
    else:
        banner_height = 40
    banner_height = min(max(banner_height, 32), int(image.shape[0]))
    bg_alpha = max(0.0, min(1.0, config.text_styles.overlay_bg_opacity))
    if bg_alpha >= 1.0:
        cv2.rectangle(image, (0, 0), (int(image.shape[1]), banner_height), color, thickness=-1)
    elif bg_alpha > 0.0:
        overlay = image.copy()
        cv2.rectangle(overlay, (0, 0), (int(image.shape[1]), banner_height), color, thickness=-1)
        cv2.addWeighted(overlay, bg_alpha, image, 1.0 - bg_alpha, 0, image)
    else:
        # bg_alpha == 0: no background drawn; still need text readable (shadow pass below)
        pass
    for line in layout[:2]:
        # Add shadow when background is semi-transparent or absent for readability
        if bg_alpha < 1.0:
            cv2.putText(
                image,
                line.text,
                (line.x + 1, line.y + 1),
                cv2.FONT_HERSHEY_SIMPLEX,
                line.scale,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )
        cv2.putText(
            image,
            line.text,
            (line.x, line.y),
            cv2.FONT_HERSHEY_SIMPLEX,
            line.scale,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )


if __name__ == "__main__":
    raise SystemExit(main())
