# Project Status

## Phase

Phase 1 Windows vertical slice is implemented. Hardware-tuning work is on branch
`feature/windows-hardware-tuning`.

## Repo State

- Remote: `git@github.com:mhe931/AirPilot.git`
- Default branch: `main`
- Main branch was unprotected when inspected on 2026-08-26.
- No issues, PRs, or workflow runs existed before this milestone.

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
- Camera backend fallback and transient read-failure retry.
- Overlay/status lines show tracking state, active gesture, hand score, fps,
  mouse state, and calibration region.
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
- `uv run --extra dev python -m pytest`: 33 passed.
- `powershell -ExecutionPolicy Bypass -File scripts\package_windows.ps1`
- `dist\AirPilot\AirPilot.exe --help`
- `dist\AirPilot\AirPilot.exe --list-cameras` detected
  `0: Camera 0 (DirectShow)`.
- `dist\AirPilot\AirPilot.exe --config %TEMP%\airpilot-packaged-validation-config.json
  --camera 0 --diagnose-seconds 3` opened Camera 0 through DirectShow and
  processed 14 frames at 640x480, about 4.6 fps, with no hand observed.
- Secret scan found only documentation/policy references to secrets/passwords,
  not credentials.
- `uv run --extra dev airpilot --list-cameras` detected
  `0: Camera 0 (DirectShow)`.
- `uv run --extra dev airpilot --config %TEMP%\airpilot-validation-config.json
  --camera 0 --diagnose-seconds 5` opened Camera 0 through DirectShow and
  processed 43 frames at 640x480, about 8.5 fps, with no hand observed.

Manual live hand acquisition and real pointer gestures still must be run with a
hand physically presented to the webcam.

## Known Issues

- The package is unsigned.
- Camera unplug/replug recovery retries transient frame-read failures but does
  not reopen a disconnected camera yet.
- Multi-monitor DPI and UAC/elevated-window behavior need manual validation.
- Current emergency controls are preview-window `q`/`Esc`/`p` plus PyAutoGUI
  corner failsafe; no global hotkey or tray app yet.

## Next

Run the short interactive checklist in `docs/MANUAL_VALIDATION.md` with a hand
in front of the laptop webcam and tune gesture defaults from observations.

## Decisions Not To Reverse Silently

- Keep domain logic platform-independent for future Android reuse.
- Keep Windows input isolated behind `MouseController`.
- Keep local-only frame processing as the default privacy posture.
- Keep Android future work AccessibilityService-based; do not attempt hidden
  input injection APIs.
