from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

import cv2
import pyautogui
from cv2.typing import MatLike

from airpilot.camera import OpenCVCamera, list_cameras
from airpilot.config import AppConfig, default_config_path, load_config, save_config
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureEngine
from airpilot.domain.types import GestureEvents, TrackingFrame
from airpilot.input import PyAutoGuiMouseController
from airpilot.safety import MouseSafetyGate
from airpilot.tracking import MediaPipeHandTracker


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
    config = load_config(config_path)
    if not persisted_path.exists():
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
        )

    return run(config)


def run(
    config: AppConfig,
    diagnose_seconds: float | None = None,
    *,
    show_preview: bool = True,
) -> int:
    camera: OpenCVCamera | None = None
    tracker: MediaPipeHandTracker | None = None
    stats = TrackingStats()

    try:
        camera = OpenCVCamera(
            config.runtime.camera_index,
            read_failures_before_error=config.runtime.camera_read_failures_before_error,
        )
        tracker = MediaPipeHandTracker(
            min_detection_confidence=config.runtime.tracker_detection_confidence,
            min_tracking_confidence=config.runtime.tracker_tracking_confidence,
        )
        config.cursor.screen_width, config.cursor.screen_height = pyautogui.size()
        engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
        mouse = PyAutoGuiMouseController(
            emergency_corner_failsafe=config.runtime.emergency_corner_failsafe,
        )
        safety = MouseSafetyGate(
            armed=config.runtime.enable_real_mouse and config.runtime.start_armed,
        )
        for camera_frame in camera.frames():
            frame = tracker.track(camera_frame.image, camera_frame.timestamp_ms)
            events = engine.process(frame)
            if config.runtime.enable_real_mouse:
                safety.apply(mouse, events)
            stats.observe(frame, events)

            image = camera_frame.image
            if show_preview:
                if config.runtime.draw_landmarks:
                    tracker.draw(image, frame.hand)
                _draw_status(
                    image,
                    frame,
                    events,
                    config,
                    armed=safety.armed,
                    fps=stats.fps,
                )
                cv2.imshow("AirPilot", image)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key == ord("p"):
                    pause_events = engine.toggle_pause()
                    if config.runtime.enable_real_mouse:
                        safety.apply(mouse, pause_events)
                if key == ord("a") and config.runtime.enable_real_mouse:
                    if safety.armed:
                        safety.disarm(mouse)
                    else:
                        safety.toggle()
            if diagnose_seconds is not None and stats.elapsed_seconds >= diagnose_seconds:
                print(json.dumps(stats.summary(camera_backend=camera.backend_name), sort_keys=True))
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
        cv2.destroyAllWindows()
    return 0


def status_lines(
    frame: TrackingFrame,
    events: GestureEvents,
    config: AppConfig,
    *,
    armed: bool,
    fps: float,
) -> list[str]:
    hand = frame.hand
    tracking = "hand" if hand is not None else "searching"
    hand_score = f"{hand.confidence:.2f}" if hand is not None else "--"
    mouse_state = "off"
    if config.runtime.enable_real_mouse:
        mouse_state = "armed" if armed else "safe"
    return [
        f"AirPilot {events.status} | {tracking} | hand score {hand_score} | {fps:.1f} fps",
        f"gesture {events.active_gesture} | mouse {mouse_state} | p pause | a arm | q stop",
    ]


def _draw_status(
    image: MatLike,
    frame: TrackingFrame,
    events: GestureEvents,
    config: AppConfig,
    *,
    armed: bool,
    fps: float,
) -> None:
    color = (0, 0, 255) if events.paused else (0, 160, 255) if not armed else (0, 180, 0)
    _draw_calibration_region(image, config)
    for index, text in enumerate(status_lines(frame, events, config, armed=armed, fps=fps)):
        y = 30 + index * 28
        cv2.putText(
            image,
            text,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            color,
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


if __name__ == "__main__":
    raise SystemExit(main())
