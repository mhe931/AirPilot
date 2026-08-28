#!/usr/bin/env python
"""Minimal camera + MediaPipe reproducer and stress tool.

Isolates AirPilot application code from dependency/native-runtime failure by
running only the camera → frame → MediaPipe pipeline without any Tkinter, Tk
shared-root, PyAutoGUI, or UI event-pump code.

Privacy: frames are never stored to disk, printed, uploaded, or transmitted.
Only aggregate statistics are logged and saved.

Usage examples
--------------
Start/stop stress (30 cycles, camera index 0)::

    uv run --extra dev python scripts/camera_mediapipe_stress.py \\
        --mode start-stop --cycles 30 --camera 0

Continuous run (300 seconds = 5 minutes, camera index 0)::

    uv run --extra dev python scripts/camera_mediapipe_stress.py \\
        --mode continuous --seconds 300 --camera 0

Save log artifact::

    uv run --extra dev python scripts/camera_mediapipe_stress.py \\
        --mode start-stop --cycles 30 --camera 0 \\
        --log-file .goals/native-crash-layout/stress-start-stop.log
"""

from __future__ import annotations

import argparse
import faulthandler
import logging
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import mediapipe as mp

# ── Enable faulthandler early so native crash stack traces appear in stderr ──
faulthandler.enable(file=sys.stderr)

MAIN_THREAD_ID = threading.get_ident()


def _log(msg: str, level: int = logging.INFO) -> None:
    tid = threading.get_ident()
    tag = "MAIN" if tid == MAIN_THREAD_ID else f"T{tid}"
    logging.log(level, "[%s] %s", tag, msg)


@dataclass
class RunStats:
    frames_processed: int = 0
    frames_skipped: int = 0
    track_errors: int = 0
    invalid_frame_errors: int = 0
    camera_opens: int = 0
    camera_closes: int = 0
    tracker_creates: int = 0
    tracker_closes: int = 0
    start_stop_cycles_ok: int = 0
    start_stop_cycles_fail: int = 0
    elapsed_s: float = 0.0
    crashes: list[str] = field(default_factory=list)


def _open_camera(index: int, stats: RunStats) -> cv2.VideoCapture:
    backends = (cv2.CAP_DSHOW, cv2.CAP_ANY) if sys.platform == "win32" else (cv2.CAP_ANY,)
    for backend in backends:
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                stats.camera_opens += 1
                _log(f"Camera {index} opened (backend {backend})")
                return cap
            cap.release()
    raise RuntimeError(f"Camera {index} could not be opened with any backend.")


def _close_camera(cap: cv2.VideoCapture, stats: RunStats) -> None:
    with suppress(Exception):
        cap.release()
    stats.camera_closes += 1
    _log("Camera released")


def _make_tracker(stats: RunStats) -> mp.solutions.hands.Hands:
    tracker = mp.solutions.hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=1,
        min_detection_confidence=0.55,
        min_tracking_confidence=0.55,
    )
    stats.tracker_creates += 1
    _log(f"MediaPipe Hands created (total creates={stats.tracker_creates})")
    return tracker


def _close_tracker(tracker: mp.solutions.hands.Hands, stats: RunStats) -> None:
    with suppress(Exception):
        tracker.close()
    stats.tracker_closes += 1
    _log(f"MediaPipe Hands closed (total closes={stats.tracker_closes})")


def _process_frame(
    cap: cv2.VideoCapture,
    tracker: mp.solutions.hands.Hands,
    stats: RunStats,
) -> bool:
    """Read one frame, validate dimensions, and run MediaPipe inference.

    Returns True on success, False on a non-fatal read failure.
    Never stores the frame.
    """
    ok, frame = cap.read()
    if not ok or frame is None:
        stats.frames_skipped += 1
        return False

    h, w = frame.shape[:2]
    if h == 0 or w == 0:
        # Guard: empty/zero-dimension frames cause landmark_projection_calculator
        # NORM_RECT warnings and corrupt pipeline state → skip, count, log.
        stats.invalid_frame_errors += 1
        _log(
            f"Invalid frame shape ({w}x{h}) – skipped to prevent NORM_RECT pipeline "
            "corruption.  This is the root cause of landmark_projection_calculator "
            "warnings; AirPilot's tracker.track() now raises InvalidFrameError here.",
            logging.WARNING,
        )
        return False

    # Run inference (no frame stored)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    try:
        _ = tracker.process(rgb)
        stats.frames_processed += 1
    except Exception as exc:
        stats.track_errors += 1
        _log(f"tracker.process() error: {type(exc).__name__}: {exc}", logging.WARNING)
    # Frame goes out of scope here – no storage.
    return True


def run_start_stop(camera_index: int, cycles: int, frames_per_cycle: int, stats: RunStats) -> None:
    """30+ repeated open→process→close cycles to stress lifecycle teardown."""
    _log(f"START-STOP mode: {cycles} cycles × ~{frames_per_cycle} frames, camera {camera_index}")
    t0 = time.perf_counter()
    for cycle in range(1, cycles + 1):
        _log(f"Cycle {cycle}/{cycles}: opening camera + tracker …")
        try:
            cap = _open_camera(camera_index, stats)
            tracker = _make_tracker(stats)

            consecutive_fails = 0
            for _ in range(frames_per_cycle):
                ok = _process_frame(cap, tracker, stats)
                if not ok:
                    consecutive_fails += 1
                    if consecutive_fails >= 5:
                        _log("5 consecutive read failures – aborting cycle early", logging.WARNING)
                        break
                else:
                    consecutive_fails = 0

            _close_tracker(tracker, stats)
            _close_camera(cap, stats)
            stats.start_stop_cycles_ok += 1
            _log(f"Cycle {cycle} OK")
        except Exception as exc:
            stats.start_stop_cycles_fail += 1
            msg = f"Cycle {cycle} FAILED: {type(exc).__name__}: {exc}"
            stats.crashes.append(msg)
            _log(msg, logging.ERROR)

    stats.elapsed_s = time.perf_counter() - t0
    _log(
        f"START-STOP complete: {stats.start_stop_cycles_ok} OK, "
        f"{stats.start_stop_cycles_fail} FAIL in {stats.elapsed_s:.1f}s"
    )


def run_continuous(camera_index: int, duration_s: float, stats: RunStats) -> None:
    """Continuous inference run for *duration_s* seconds."""
    _log(f"CONTINUOUS mode: {duration_s:.0f}s, camera {camera_index}")
    t0 = time.perf_counter()
    try:
        cap = _open_camera(camera_index, stats)
        tracker = _make_tracker(stats)

        deadline = t0 + duration_s
        consecutive_fails = 0
        while time.perf_counter() < deadline:
            ok = _process_frame(cap, tracker, stats)
            if not ok:
                consecutive_fails += 1
                if consecutive_fails >= 30:
                    _log("30 consecutive read failures – stopping continuous run", logging.WARNING)
                    break
                time.sleep(0.01)
            else:
                consecutive_fails = 0
            if stats.frames_processed % 300 == 0 and stats.frames_processed > 0:
                elapsed = time.perf_counter() - t0
                fps = stats.frames_processed / max(elapsed, 0.001)
                _log(f"  {elapsed:.0f}s elapsed, {stats.frames_processed} frames, {fps:.1f} fps")

        _close_tracker(tracker, stats)
        _close_camera(cap, stats)
    except Exception as exc:
        msg = f"CONTINUOUS failed: {type(exc).__name__}: {exc}"
        stats.crashes.append(msg)
        _log(msg, logging.ERROR)

    stats.elapsed_s = time.perf_counter() - t0
    elapsed = stats.elapsed_s
    fps = stats.frames_processed / max(elapsed, 0.001)
    _log(
        f"CONTINUOUS complete: {stats.frames_processed} frames in {elapsed:.1f}s "
        f"({fps:.1f} fps), errors={stats.track_errors}"
    )


def _summary(stats: RunStats, mode: str) -> str:
    lines = [
        "=== camera_mediapipe_stress summary ===",
        f"mode            : {mode}",
        f"elapsed_s       : {stats.elapsed_s:.2f}",
        f"frames_processed: {stats.frames_processed}",
        f"frames_skipped  : {stats.frames_skipped}",
        f"track_errors    : {stats.track_errors}",
        f"invalid_frames  : {stats.invalid_frame_errors}",
        f"camera_opens    : {stats.camera_opens}",
        f"camera_closes   : {stats.camera_closes}",
        f"tracker_creates : {stats.tracker_creates}",
        f"tracker_closes  : {stats.tracker_closes}",
    ]
    if mode == "start-stop":
        lines += [
            f"cycles_ok       : {stats.start_stop_cycles_ok}",
            f"cycles_fail     : {stats.start_stop_cycles_fail}",
        ]
    if stats.crashes:
        lines.append(f"crashes         : {len(stats.crashes)}")
        for c in stats.crashes:
            lines.append(f"  - {c}")
    else:
        lines.append("crashes         : 0")
    lines.append("=== end ===")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AirPilot camera+MediaPipe stress tool")
    parser.add_argument("--mode", choices=["start-stop", "continuous"], default="start-stop")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--cycles", type=int, default=30, help="start-stop cycles")
    parser.add_argument(
        "--frames-per-cycle", type=int, default=20, help="frames per start-stop cycle"
    )
    parser.add_argument("--seconds", type=float, default=300.0, help="continuous run duration")
    parser.add_argument("--log-file", type=Path, default=None, help="save summary to file")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    _log(f"faulthandler enabled (stderr). Python {sys.version.split()[0]}")
    _log(f"OpenCV {cv2.__version__}, MediaPipe {mp.__version__}")
    _log(f"Main thread id: {MAIN_THREAD_ID}")

    stats = RunStats()
    if args.mode == "start-stop":
        run_start_stop(args.camera, args.cycles, args.frames_per_cycle, stats)
    else:
        run_continuous(args.camera, args.seconds, stats)

    summary = _summary(stats, args.mode)
    print(summary)

    if args.log_file is not None:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        args.log_file.write_text(summary + "\n", encoding="utf-8")
        _log(f"Artifact saved to {args.log_file}")

    fail = stats.start_stop_cycles_fail > 0 if args.mode == "start-stop" else bool(stats.crashes)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
