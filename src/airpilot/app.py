from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import cv2
import pyautogui
from cv2.typing import MatLike

from airpilot.camera import OpenCVCamera, list_cameras
from airpilot.config import AppConfig, load_config, save_config
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureEngine
from airpilot.input import PyAutoGuiMouseController, apply_mouse_events
from airpilot.tracking import MediaPipeHandTracker


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AirPilot Windows gesture mouse")
    parser.add_argument("--camera", type=int, default=None, help="camera index")
    parser.add_argument("--list-cameras", action="store_true", help="list available cameras")
    parser.add_argument(
        "--no-mouse",
        action="store_true",
        help="run tracker UI without moving the mouse",
    )
    parser.add_argument("--config", type=str, default=None, help="config file path")
    args = parser.parse_args(argv)

    config = load_config(None if args.config is None else Path(args.config))
    if args.camera is not None:
        config.runtime.camera_index = args.camera
    if args.no_mouse:
        config.runtime.enable_real_mouse = False

    if args.list_cameras:
        for device in list_cameras(config.runtime.max_camera_index):
            print(f"{device.index}: {device.name}")
        return 0

    return run(config)


def run(config: AppConfig) -> int:
    camera = OpenCVCamera(config.runtime.camera_index)
    tracker = MediaPipeHandTracker(
        min_detection_confidence=config.runtime.tracker_detection_confidence,
        min_tracking_confidence=config.runtime.tracker_tracking_confidence,
    )
    config.cursor.screen_width, config.cursor.screen_height = pyautogui.size()
    engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
    mouse = PyAutoGuiMouseController(
        emergency_corner_failsafe=config.runtime.emergency_corner_failsafe,
    )
    save_config(config)

    try:
        for camera_frame in camera.frames():
            frame = tracker.track(camera_frame.image, camera_frame.timestamp_ms)
            events = engine.process(frame)
            if config.runtime.enable_real_mouse:
                apply_mouse_events(mouse, events)

            image = camera_frame.image
            if config.runtime.draw_landmarks:
                tracker.draw(image, frame.hand)
            _draw_status(image, events.status, engine.paused, config.runtime.enable_real_mouse)
            cv2.imshow("AirPilot", image)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("p"):
                engine.paused = not engine.paused
            if mouse.emergency_stop_requested():
                break
    except pyautogui.FailSafeException:
        print("AirPilot stopped by PyAutoGUI failsafe corner.", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"AirPilot runtime error: {exc}", file=sys.stderr)
        return 1
    finally:
        camera.close()
        tracker.close()
        cv2.destroyAllWindows()
    return 0


def _draw_status(image: MatLike, status: str, paused: bool, mouse_enabled: bool) -> None:
    text = (
        f"{'PAUSED' if paused else status} | "
        f"mouse={'on' if mouse_enabled else 'off'} | q/esc stop | p pause"
    )
    cv2.putText(
        image,
        text,
        (12, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (0, 0, 255) if paused else (0, 180, 0),
        2,
        cv2.LINE_AA,
    )


if __name__ == "__main__":
    raise SystemExit(main())
