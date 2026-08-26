# AirPilot Agent Entrypoint

This file is the authoritative starting point for future Codex agents.

## Phase

Phase 1 Windows vertical slice is implemented locally: webcam capture to hand
tracking to gesture recognition to real Windows mouse control.

Android must remain documentation-only until explicitly requested.

## Repo State

- Remote: `git@github.com:mhe931/AirPilot.git`
- Default branch: `main`
- Create a focused feature branch for each milestone; verify the current branch
  before editing.
- Main is not branch-protected as of 2026-08-26.
- Draft PR #3 tracks camera reconnect hardening and has passing CI; live gesture
  validation still remains pending human observation.

## Architecture Paths

- `src/airpilot/domain/`: platform-independent cursor and gesture logic.
- `src/airpilot/camera.py`: OpenCV camera adapter.
- `src/airpilot/tracking.py`: MediaPipe hand-tracking adapter.
- `src/airpilot/input.py`: Windows mouse adapter and fake controller.
- `src/airpilot/safety.py`: safe/armed mouse-output gate.
- `src/airpilot/app.py`: desktop runtime loop and preview UI.
- `tests/`: synthetic landmark and fake-input tests.
- `config/defaults.json`: default config example.

## Canonical Commands

```powershell
uv sync --extra dev
uv run --extra dev airpilot --list-cameras
uv run --extra dev airpilot --camera 0 --diagnose-seconds 5
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
- Real mouse output starts disarmed unless `--armed` is passed explicitly.
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
- Safe/armed gate, richer status overlay, headless diagnostics, camera backend
  fallback, transient read-failure retry, and bounded camera reopen attempts
  after sustained read failures.
- CI workflow for formatting, linting, typing, and tests.
- Android feasibility document.
- PyInstaller one-dir package builds and packaged CLI camera listing detects
  `Camera 0` on the development machine.
- Headless webcam diagnostics open Camera 0 through DirectShow and process
  aggregate tracker stats without moving the pointer or saving frames, including
  camera reconnect counts.

## Known Issues

- Manual hand acquisition and real pointer gesture validation are still required
  with a hand physically presented to the laptop webcam.
- Packaged executable is unsigned.
- Camera unplug/replug recovery now retries reopening the same camera index, but
  recovery still depends on Windows presenting the device again on that index.
- Multi-monitor DPI behavior has not been manually validated.
- Global hotkey/tray emergency stop is not implemented; current stop controls
  are preview-window keys and PyAutoGUI corner failsafe.

## Milestone Acceptance

- Fresh `uv sync --extra dev` succeeds.
- Format, lint, mypy, and tests pass.
- PyInstaller package builds and packaged executable starts.
- `airpilot --list-cameras` works on Windows.
- `airpilot --camera 0 --diagnose-seconds 5` starts camera/tracker without
  moving the mouse.
- `airpilot --camera 0 --no-mouse` shows tracking without mouse movement.
- Real mouse mode supports move, left/right click, drag/drop, scroll,
  pause/resume, and failsafe stop.
- Docs match the implementation.

## Next Task

Run the short interactive validation checklist with a hand in front of the
laptop webcam, then tune gesture defaults from observed behavior.

## Decisions Not To Silently Reverse

- Use Python 3.11, `uv`, OpenCV, MediaPipe `<0.10.30`, and PyAutoGUI for Phase
  1 until the tracker migrates to MediaPipe Tasks with a packaged model asset.
- Keep Android as a future AccessibilityService-based path, not hidden input
  injection.
- Keep mouse injection behind `MouseController` so tests use fakes.
- Keep AirPilot privacy-first with local processing and no recording/uploads by
  default.
