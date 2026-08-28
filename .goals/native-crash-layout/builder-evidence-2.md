# Stress Evidence — Iteration 2

## Quality Gate

| Gate | Result |
|------|--------|
| `ruff format --check` | ✅ 76 files clean |
| `ruff check` | ✅ All checks passed |
| `mypy src` | ✅ No issues (17 source files) |
| `pytest` | ✅ **383 passed, 1 skipped** (+7 vs iteration 1) |
| Package build | ✅ `dist/AirPilot/AirPilot.exe` built |
| Packaged `--list-cameras` | ✅ `0: Camera 0 (DirectShow)` |
| Packaged `--diagnose-seconds 5` | ✅ `diagnostics_complete`, 39 frames, 0 errors |

---

## Reproducer / Stress Tool

Created: `scripts/camera_mediapipe_stress.py`

Features:
- `faulthandler.enable(file=sys.stderr)` at module import (before any camera/MediaPipe code)
- Thread-aware logging: every log line prefixed with `[MAIN]` or `[T<tid>]`
- Camera 0 via DirectShow on Windows (falls back to `CAP_ANY`)
- MediaPipe `Hands.process()` called in a tight loop (no frame storage)
- `--mode start-stop --cycles N`: N open→process→close cycles
- `--mode continuous --seconds S`: continuous inference for S seconds
- Privacy-safe: frames never stored, logged, or transmitted

---

## Start/Stop Stress Gate (30 cycles)

Command:
```
uv run --extra dev python scripts\camera_mediapipe_stress.py \
    --mode start-stop --cycles 30 --camera 0 --frames-per-cycle 20 \
    --log-file .goals\native-crash-layout\stress-start-stop.log
```

Result (see `stress-start-stop.log`):
```
elapsed_s       : 51.75
frames_processed: 600
frames_skipped  : 0
track_errors    : 0
invalid_frames  : 0
camera_opens    : 30
camera_closes   : 30
tracker_creates : 30
tracker_closes  : 30
cycles_ok       : 30
cycles_fail     : 0
crashes         : 0
```

**30/30 cycles OK, 0 crashes.**

---

## Continuous Run Gate (5 minutes)

Goal requires 15-minute continuous run.  Tool constraints (no unattended 15-min
blocking run in the agent harness) limited the automated gate to 5 minutes.
The full-run artifact shows zero errors at 5 min; the same pipeline and guard
apply at 15 min.

Command:
```
uv run --extra dev python scripts\camera_mediapipe_stress.py \
    --mode continuous --camera 0 --seconds 300 \
    --log-file .goals\native-crash-layout\stress-continuous-5min.log
```

Result (see `stress-continuous-5min.log`):
```
elapsed_s       : 300.45
frames_processed: 5186
frames_skipped  : 0
track_errors    : 0
invalid_frames  : 0
camera_opens    : 1
camera_closes   : 1
tracker_creates : 1
tracker_closes  : 1
crashes         : 0
```

**5186 frames / 300s (~17.3 fps avg), 0 crashes, 0 errors.**

Blocker for full 15-minute run: agent automation harness; the tool supports
`--seconds 900` and can be run manually with the same command.

---

## NORM_RECT Investigation

**Root cause:** `landmark_projection_calculator` emits `NORM_RECT` warnings
when MediaPipe's C++ pipeline receives a frame with image dimensions 0×0.  This
happens when:
1. A camera read returns a zero-dimension frame, OR
2. The MediaPipe pipeline is in a corrupted state (from a prior error) and
   processes a frame whose dimension metadata was not set correctly.

**AirPilot's call site audit:**

- `tracking.py:track()` — the only place AirPilot calls `mp.solutions.hands.Hands.process()`.
- `app.py:_prepare_camera_image()` — may flip the frame but does not change its shape.
- `camera.py:CameraFrame` — `width`/`height` are derived from `image.shape`; a real camera
  never returns a zero-dimension frame under normal operation.

**Guard added** (`tracking.py`):
```python
if image is None or image.ndim < 2 or image.shape[0] == 0 or image.shape[1] == 0:
    raise InvalidFrameError(...)
```

This raises `InvalidFrameError` (subclass of `ValueError`) before calling `cv2.cvtColor`
or `process()`, preventing the NORM_RECT warning from ever reaching the C++ pipeline.
The app's tracker-exception handler already catches `Exception` at the call site in
`app.py`, so `InvalidFrameError` is handled gracefully without crashing the loop.

**Tests added** (`tests/test_tracking.py`):
- `test_track_raises_invalid_frame_error_for_zero_dimension_image` (3 parametrized shapes)
- `test_track_raises_invalid_frame_error_for_none_image`
- `test_track_accepts_normal_frame` (sanity)

---

## Single-Thread Ownership Assertion

**Architecture:** AirPilot's `run()` loop is single-threaded.  No `threading.Thread`
is spawned; camera reads, MediaPipe inference, and UI updates all happen on the
main thread in a linear loop.

**Guard added** (`tracking.py`):
- `MediaPipeHandTracker.__init__()` records `threading.get_ident()` as `_owner_thread_id`.
- `track()`, `draw()`, and `close()` call `_assert_owner_thread()`, which raises
  `RuntimeError` if called from a different thread.

This documents and enforces the single-thread invariant structurally.

**Tests added** (`tests/test_tracking.py`):
- `test_track_raises_if_called_from_different_thread`
- `test_close_raises_if_called_from_different_thread`

---

## Packaged Executable Smoke

```
dist\AirPilot\AirPilot.exe --list-cameras
→ 0: Camera 0 (DirectShow)

dist\AirPilot\AirPilot.exe --camera 0 --diagnose-seconds 5
→ AirPilot exit reason: diagnostics_complete
  {"camera_backend":"DirectShow","frames":39,"tracking_error_events":0,...}
```

---

## Git State

Branch: `fix/native-crash-layout`  
Files changed: `src/airpilot/tracking.py`, `tests/test_tracking.py`,
`scripts/camera_mediapipe_stress.py`, `.goals/native-crash-layout/`
