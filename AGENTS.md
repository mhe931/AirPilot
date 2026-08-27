# AirPilot Agent Entrypoint

This file is the authoritative starting point for future Codex agents.

## Phase

Phase 1 Windows vertical slice is implemented locally: webcam capture to hand
tracking to gesture recognition to real Windows mouse control.

Android must remain documentation-only until explicitly requested.

## Repo State

- Remote: `git@github.com:mhe931/AirPilot.git`
- Default branch: `main`
- Persistent branch policy: `main` only. Future agents may create short-lived
  focused branches, but merge and delete them before handoff.
- Main is not branch-protected as of 2026-08-26.
- PR #3 merged camera reconnect hardening into `main`.
- PR #4 merged the MediaPipe preview-drawing compatibility fix into `main`.
- PR #5 merged orientation/arming UX into `main`.
- PR #6 merged Windows live interaction UX into `main`.
- PR #7 merged Windows actions, monitor mapping, stability instrumentation, and
  cleanup into `main`.

## Architecture Paths

- `src/airpilot/domain/`: platform-independent cursor and gesture logic.
- `src/airpilot/camera.py`: OpenCV camera adapter.
- `src/airpilot/tracking.py`: MediaPipe hand-tracking adapter.
- `src/airpilot/input.py`: Windows mouse adapter and fake controller.
- `src/airpilot/display.py`: Windows virtual-desktop geometry adapter.
- `src/airpilot/actions.py`: configurable shortcut/action routing.
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
- Do not leave local or remote feature branches behind after completed work.
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
  thresholds, click-target lock, deliberate drag state, scroll state, optional
  gesture pause state, and tracking-loss handling.
- Cursor mapper with calibration, mirroring, smoothing, sensitivity, and
  dead-zone behavior over Windows virtual-desktop coordinates.
- Config persistence with schema versioning.
- Tests for gestures, mapping, tracking loss/recovery, config, and fake input.
- Safe/armed gate, richer status overlay, headless diagnostics, camera backend
  fallback, transient read-failure retry, and bounded camera reopen attempts
  after sustained read failures.
- Preview landmark drawing is compatible with the pinned MediaPipe package and
  disables only landmark rendering if preview drawing fails, rather than
  crashing the core loop.
- The preview now defaults to an actual-orientation image, real mouse control
  starts with a prominent disarmed banner, and legacy configs migrate to the
  new camera-orientation behavior.
- Tracking carries up to two hands, with a deterministic right-hand-preferred
  control hand and a secondary hand reserved for future gestures.
- Mouse activation is explicit in the preview: `A` enables/disables mouse output
  unless the run was intentionally started with `--no-mouse` or diagnostics.
- Mouse activation can also be armed with a deliberate second-hand thumb-middle
  hold from the disarmed startup state.
- Windows cursor feedback is encapsulated behind an adapter and restored during
  shutdown; it uses transient OS cursor calls rather than permanent system
  cursor replacement.
- CI workflow for formatting, linting, typing, and tests.
- Android feasibility document.
- PyInstaller one-dir package builds and packaged CLI camera listing detects
  `Camera 0` on the development machine.
- Headless webcam diagnostics open Camera 0 through DirectShow and process
  aggregate tracker stats without moving the pointer or saving frames, including
  camera reconnect counts.
- Physical rightward pointer direction is corrected by keeping actual-orientation
  preview while mirroring normalized X for operator-facing pointer motion.
- Initial shortcut/action catalog and two-hand shortcut mode are implemented with
  risky shortcuts disabled by default.
- Clipboard History (`clipboard.history` / `Win+V`) is enabled by default through
  shortcut-mode thumb-middle hold.
- Middle click is available via a deliberate thumb-middle hold/release.
- The preview stays compact; full gesture/action help opens in a separate window
  with `H` or a deliberate second-hand thumb-index hold, and contains a
  glanceable quick-start dashboard, mappings, action catalog, Task View guidance,
  and safety notes.
- Scroll uses thumb-ring pinch plus accumulated vertical wrist movement with
  configurable sensitivity/cooldown while suppressing pointer movement.
- Gesture pause is disabled by default to prevent accidental `PAUSED`; keyboard
  `P` still pauses/resumes, and config can explicitly re-enable the gesture.
- Pointer defaults now favor responsiveness with tighter camera bounds, higher
  sensitivity, lighter smoothing, and a small dead zone.
- Click candidates freeze the pointer target; drag starts only after a hold plus
  deliberate movement.
- Default app switching uses Task View: Shortcut Mode plus thumb-index hold opens
  `Win+Tab`, hand movement sends left/right, and release confirms with Enter.
- Runtime exits print `AirPilot exit reason: ...`. Canonical quit is preview
  key `Q`; `Esc` is ignored by AirPilot so synthetic/system Esc from Task View
  cannot close the preview loop.
- Transient tracker exceptions are counted in diagnostics and treated as
  tracking loss for that frame. PyAutoGUI failsafe disarms mouse output and
  continues when recovery is possible.

## Known Issues

- Manual validation is still required for arm gesture, click accuracy, drag,
  Help glanceability, Task View, scroll up/down/control, Clipboard History,
  long-run stability, and feel.
- Packaged executable is unsigned.
- Camera unplug/replug recovery now retries reopening the same camera index, but
  recovery still depends on Windows presenting the device again on that index.
- Multi-monitor DPI behavior has not been manually validated.
- Global hotkey/tray emergency stop is not implemented; current stop controls
  are preview-window `Q` and PyAutoGUI corner failsafe.

## Milestone Acceptance

- Fresh `uv sync --extra dev` succeeds.
- Format, lint, mypy, and tests pass.
- PyInstaller package builds and packaged executable starts.
- `airpilot --list-cameras` works on Windows.
- `airpilot --camera 0 --diagnose-seconds 5` starts camera/tracker without
  moving the mouse.
- `airpilot --camera 0 --no-mouse` shows tracking without mouse movement.
- Real mouse mode supports move, left/right/middle click, drag/drop, scroll,
  pause/resume, shortcut actions, and failsafe stop.
- Docs match the implementation.

## Next Task

Run the compact live validation checklist and collect:
`run_duration=<minutes before manual quit or unexpected close>
exit=<manual_q|closed_itself> exit_reason=<exact printed reason>
mouse=<ok|fail> click=<ok|fail> feel=<short note>`.

## Decisions Not To Silently Reverse

- Use Python 3.11, `uv`, OpenCV, MediaPipe `<0.10.30`, and PyAutoGUI for Phase
  1 until the tracker migrates to MediaPipe Tasks with a packaged model asset.
- Keep Android as a future AccessibilityService-based path, not hidden input
  injection.
- Keep mouse injection behind `MouseController` so tests use fakes.
- Keep AirPilot privacy-first with local processing and no recording/uploads by
  default.
