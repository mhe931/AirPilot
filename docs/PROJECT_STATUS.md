# Project Status

## Phase

Phase 1 Windows vertical slice is implemented. Follow-up Windows hardening and
hardware-tuning work should use short-lived focused feature branches off `main`.

## Repo State

- Remote: `git@github.com:mhe931/AirPilot.git`
- Default branch: `main`
- Main branch was unprotected when inspected on 2026-08-26.
- PR #1 and PR #2 were merged when inspected on 2026-08-26.
- No open issues were present when inspected.
- PR #3 merged camera reconnect hardening into `main`.
- PR #4 merged the MediaPipe preview-drawing compatibility fix into `main`.
- Draft PR #5 contains orientation, activation UX, cursor feedback, and two-hand
  tracking work.

## Completed

- Python 3.11 project using `uv`.
- OpenCV webcam capture and camera listing.
- MediaPipe hand tracking adapter.
- Gesture state machine with hold thresholds, hysteresis, cooldowns, drag
  lifecycle, scroll mode, pause/resume, and tracking-loss handling.
- Cursor mapper with calibration bounds, mirroring, smoothing, sensitivity, and
  dead-zone logic.
- PyAutoGUI mouse adapter plus fake controller for tests.
- Safe/armed mouse-output gate; real mouse mode starts safe by default.
- Headless diagnostics mode for camera/tracker startup without pointer movement.
- Camera backend fallback, transient read-failure retry, and bounded same-index
  camera reopen attempts after repeated read failures.
- MediaPipe preview landmark drawing compatibility fix for the pinned package.
- Preview landmark rendering now disables only the landmark overlay if drawing
  fails, instead of crashing the runtime loop.
- Default preview orientation is corrected away from selfie mirroring, cursor
  mapping matches that orientation, config schema v3 migrates legacy behavior,
  and the overlay now shows prominent active/disarmed/paused/preview-only state.
- Up to two MediaPipe hands are tracked; the right hand is preferred as the
  control hand and a secondary hand is retained for future interactions.
- `A` enables/disables mouse output unless the run is explicitly locked by
  `--no-mouse` or diagnostics, avoiding ambiguous preview-only runtime state.
- Transient cursor feedback is behind a Windows-specific adapter and restored
  during cleanup.
- Config persistence under `%APPDATA%\AirPilot\config.json`.
- Synthetic tests for gestures, mapping, tracking loss/recovery, config, and
  fake mouse event application.
- CI workflow, issue templates, PR template, package script, README, AGENTS
  handoff, roadmap, architecture, Android feasibility, and ADRs.
- PyInstaller one-dir package build under `dist\AirPilot`.

## Architecture

- `src/airpilot/domain`: reusable gesture and cursor domain logic.
- `src/airpilot/camera.py`: OpenCV camera adapter.
- `src/airpilot/tracking.py`: MediaPipe adapter.
- `src/airpilot/input.py`: Windows mouse adapter and fake implementation.
- `src/airpilot/safety.py`: safe/armed output gate.
- `src/airpilot/app.py`: runtime loop and OpenCV preview/status UI.

## Commands

```powershell
uv sync --extra dev
uv run --extra dev airpilot --list-cameras
uv run --extra dev airpilot --camera 0 --diagnose-seconds 5
uv run --extra dev airpilot --camera 0 --no-mouse
uv run --extra dev airpilot --camera 0
uv run --extra dev airpilot --camera 0 --armed
uv run --extra dev ruff format --check .
uv run --extra dev ruff check .
uv run --extra dev mypy src
uv run --extra dev python -m pytest
uv sync --extra package
powershell -ExecutionPolicy Bypass -File scripts/package_windows.ps1
```

## Validation

Last local automated validation:

- `uv run --extra dev ruff format --check .`
- `uv run --extra dev ruff check .`
- `uv run --extra dev mypy src`
- `uv run --extra dev python -m pytest`: 56 passed after two-hand tracking,
  activation hardening, cursor feedback, and config migration fixes.
- `uv run python -c "... MediaPipeHandTracker().draw(...)"` completed with
  `draw-ok` against the installed MediaPipe package.
- `uv run --extra dev airpilot --camera 0` started without the prior preview
  crash and reached live preview startup; the process was then stopped after a
  brief startup check.
- `powershell -ExecutionPolicy Bypass -File scripts\package_windows.ps1`
- `dist\AirPilot\AirPilot.exe --help`
- `dist\AirPilot\AirPilot.exe --list-cameras` detected
  `0: Camera 0 (DirectShow)`.
- `dist\AirPilot\AirPilot.exe --config %TEMP%\airpilot-packaged-validation-config.json
  --camera 0 --diagnose-seconds 5` opened Camera 0 through DirectShow and
  processed 42 frames at 640x480 with `camera_reconnects: 0`.
- `dist\AirPilot\AirPilot.exe --camera 0` stayed running during a brief packaged
  live-startup smoke test and was then stopped.
- Secret scan found only documentation/policy references to secrets/passwords,
  not credentials.
- `uv run --extra dev airpilot --list-cameras` detected
  `0: Camera 0 (DirectShow)`.
- `uv run --extra dev airpilot --config %TEMP%\airpilot-validation-config.json
  --camera 0 --diagnose-seconds 5` opened Camera 0 through DirectShow and
  processed 42 frames at 640x480, about 8.4 fps, with no hand observed and
  `camera_reconnects: 0`.

Manual live hand acquisition and real pointer gestures still must be run with a
hand physically presented to the webcam.

## Known Issues

- The package is unsigned.
- Camera unplug/replug recovery now retries reopening the same camera index, but
  manual validation is still required to confirm recovery on this hardware.
- Safe cursor feedback uses transient Windows cursor APIs rather than permanent
  system cursor replacement; behavior over other applications needs manual
  validation.
- Two-hand tracking is implemented but not yet manually validated with two
  physical hands.
- MediaPipe emits a `NORM_RECT without IMAGE_DIMENSIONS` warning during live
  hand tracking; it did not reproduce as a crash and is not yet proven to cause
  incorrect gesture behavior in this milestone.
- Multi-monitor DPI and UAC/elevated-window behavior need manual validation.
- Current emergency controls are preview-window `q`/`Esc`/`p` plus PyAutoGUI
  corner failsafe; no global hotkey or tray app yet.

## Next

Run the compact live validation with a hand in front of the laptop webcam to
confirm overlay readability, activation, movement, cursor feedback, one-hand and
two-hand detection, and orientation; then tune gesture defaults from the
resulting observations.

## Decisions Not To Reverse Silently

- Keep domain logic platform-independent for future Android reuse.
- Keep Windows input isolated behind `MouseController`.
- Keep local-only frame processing as the default privacy posture.
- Keep Android future work AccessibilityService-based; do not attempt hidden
  input injection APIs.
