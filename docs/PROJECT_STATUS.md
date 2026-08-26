# Project Status

## Phase

Phase 1 Windows vertical slice is implemented on branch
`feature/windows-phase1-vertical-slice`.

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
- `src/airpilot/app.py`: runtime loop and OpenCV preview/status UI.

## Commands

```powershell
uv sync --extra dev
uv run --extra dev airpilot --list-cameras
uv run --extra dev airpilot --camera 0 --no-mouse
uv run --extra dev airpilot --camera 0
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
- `uv run --extra dev python -m pytest`
- `powershell -ExecutionPolicy Bypass -File scripts\package_windows.ps1`
- `dist\AirPilot\AirPilot.exe --help`
- `dist\AirPilot\AirPilot.exe --list-cameras` detected `Camera 0`
- Secret scan found only documentation/policy references to secrets/passwords,
  not credentials.

Manual live tracking and real pointer validation still must be run on physical
hardware.

## Known Issues

- The package is unsigned.
- Camera unplug/replug recovery currently exits gracefully instead of reconnecting.
- Multi-monitor DPI and UAC/elevated-window behavior need manual validation.
- Current emergency controls are preview-window `q`/`Esc`/`p` plus PyAutoGUI
  corner failsafe; no global hotkey or tray app yet.

## Next

Run `docs/MANUAL_VALIDATION.md` on a Windows machine with a webcam and tune the
gesture defaults from observations.

## Decisions Not To Reverse Silently

- Keep domain logic platform-independent for future Android reuse.
- Keep Windows input isolated behind `MouseController`.
- Keep local-only frame processing as the default privacy posture.
- Keep Android future work AccessibilityService-based; do not attempt hidden
  input injection APIs.
