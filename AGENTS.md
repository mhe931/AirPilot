# AirPilot Agent Entrypoint

This file is the authoritative starting point for future Codex agents.

## Phase

Phase 1 Windows vertical slice is implemented locally: webcam capture to hand
tracking to gesture recognition to real Windows mouse control.

Android must remain documentation-only until explicitly requested.

## Repo State

- Remote: `git@github.com:mhe931/AirPilot.git`
- Default branch: `main`
- Active feature branch for this milestone: `feature/windows-phase1-vertical-slice`
- Main is not branch-protected as of 2026-08-26.

## Architecture Paths

- `src/airpilot/domain/`: platform-independent cursor and gesture logic.
- `src/airpilot/camera.py`: OpenCV camera adapter.
- `src/airpilot/tracking.py`: MediaPipe hand-tracking adapter.
- `src/airpilot/input.py`: Windows mouse adapter and fake controller.
- `src/airpilot/app.py`: desktop runtime loop and preview UI.
- `tests/`: synthetic landmark and fake-input tests.
- `config/defaults.json`: default config example.

## Canonical Commands

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

## Rules

- Preserve unrelated user work.
- Never push directly to `main`.
- Do not implement Android in Phase 1.
- Keep gesture/domain logic reusable and platform-independent.
- Do not store, upload, or log camera frames by default.
- Do not emit mouse clicks on startup, tracking loss, calibration, or a single
  noisy frame.
- Verify subagent work before trusting it.

## Completed

- Python project metadata and locked dependencies.
- MediaPipe/OpenCV/PyAutoGUI Windows runtime.
- Explicit gesture state machine with cooldowns, hysteresis, click hold
  thresholds, drag state, scroll state, pause state, and tracking-loss handling.
- Cursor mapper with calibration, mirroring, smoothing, sensitivity, and
  dead-zone behavior.
- Config persistence with schema versioning.
- Tests for gestures, mapping, tracking loss/recovery, config, and fake input.
- CI workflow for formatting, linting, typing, and tests.
- Android feasibility document.
- PyInstaller one-dir package builds and packaged CLI camera listing detects
  `Camera 0` on the development machine.

## Known Issues

- Manual live tracking and real pointer validation are still required on
  physical hardware.
- Packaged executable is unsigned.
- Camera unplug/replug recovery exits gracefully but does not reconnect yet.
- Multi-monitor DPI behavior has not been manually validated.
- Global hotkey/tray emergency stop is not implemented; current stop controls
  are preview-window keys and PyAutoGUI corner failsafe.

## Milestone Acceptance

- Fresh `uv sync --extra dev` succeeds.
- Format, lint, mypy, and tests pass.
- PyInstaller package builds and packaged executable starts.
- `airpilot --list-cameras` works on Windows.
- `airpilot --camera 0 --no-mouse` shows tracking without mouse movement.
- Real mouse mode supports move, left/right click, drag/drop, scroll,
  pause/resume, and failsafe stop.
- Docs match the implementation.

## Next Task

Run the manual webcam validation checklist on a Windows machine with a camera,
then tune defaults from observed behavior.

## Decisions Not To Silently Reverse

- Use Python 3.11, `uv`, OpenCV, MediaPipe, and PyAutoGUI for Phase 1.
- Keep Android as a future AccessibilityService-based path, not hidden input
  injection.
- Keep mouse injection behind `MouseController` so tests use fakes.
- Keep AirPilot privacy-first with local processing and no recording/uploads by
  default.
