# Project Status

## Phase

Phase 1 Windows vertical slice is implemented. Follow-up Windows hardening and
hardware-tuning work should use short-lived focused branches off `main`, then
merge and delete them.

## Repo State

- Remote: `git@github.com:mhe931/AirPilot.git`
- Default branch: `main`
- Persistent branch policy: `main` only.
- Main branch was unprotected when inspected on 2026-08-26.
- PR #1 and PR #2 were merged when inspected on 2026-08-26.
- No open issues were present when inspected.
- PR #3 merged camera reconnect hardening into `main`.
- PR #4 merged the MediaPipe preview-drawing compatibility fix into `main`.
- PR #5 merged orientation and arming UX into `main`.
- PR #6 merged Windows live interaction UX into `main`.
- PR #7 merged Windows actions, monitor mapping, stability instrumentation, and
  cleanup into `main`.

## Completed

- Python 3.11 project using `uv`.
- OpenCV webcam capture and camera listing.
- MediaPipe hand tracking adapter.
- Gesture state machine with hold thresholds, hysteresis, cooldowns, drag
  lifecycle, click-target lock, scroll mode, optional gesture pause/resume, and
  tracking-loss handling.
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
  and the overlay now shows compact active/disarmed/paused/preview-only state.
- Up to two MediaPipe hands are tracked; the right hand is preferred as the
  control hand and a secondary hand is retained for future interactions.
- `A` enables/disables mouse output unless the run is explicitly locked by
  `--no-mouse` or diagnostics, avoiding ambiguous preview-only runtime state.
- A deliberate second-hand thumb-middle hold can arm AirPilot from the disarmed
  startup state without reaching for the keyboard.
- Cursor feedback no longer overrides the global Windows cursor icon; active
  state is reported through the preview/help UI.
- Physical hand-right now maps to pointer-right while keeping the actual camera
  preview orientation.
- Win32 virtual-desktop geometry is used for cursor mapping, including negative
  origins for monitors left or above the primary display.
- Primary mouse gestures now use pose/clutch semantics: thumb open tracks from a
  stable palm/knuckle anchor, thumb closed/bent freezes the pointer, index
  bend/release clicks or drags while clutched, and middle bend/release maps to
  right or middle click.
- A separate gesture/action help window is available with `H` or a deliberate
  second-hand thumb-index hold. The Help window is now an action-first dictionary
  grouped by Quick Start, Mouse, Control, Shortcut Mode, Windows/Apps, Browser,
  Presentation, Media, and Risky.
- A configurable shortcut action catalog and two-hand shortcut mode are
  implemented; risky actions are disabled by default. Clipboard History
  (`clipboard.history` / `Win+V`) is enabled by default through shortcut-mode
  thumb-middle hold.
- Scroll uses a deliberate thumb-ring pinch plus accumulated vertical wrist
  movement, configurable sensitivity, and a short cooldown for smoother repeated
  wheel events while suppressing pointer movement.
- Cursor defaults use a tighter active camera region, higher sensitivity, lighter
  smoothing, and a small dead zone for more responsive pointer movement.
- Gesture pause is disabled by default to avoid accidental `PAUSED`; keyboard
  `P` remains available and the gesture can be re-enabled in config.
- Clutched click candidates freeze the pointer at the intended target; dragging
  requires hold plus deliberate movement so long holds do not become accidental
  drags.
- The default app-switch flow is now Windows Task View: Shortcut Mode plus
  thumb-index hold opens `Win+Tab`, hand movement sends left/right navigation,
  and release confirms with Enter. Alt+Tab remains cataloged but is no longer a
  default gesture.
- Config persistence under `%APPDATA%\AirPilot\config.json`.
- Synthetic tests for gestures, mapping, tracking loss/recovery, config, and
  fake mouse event application.
- CI workflow, issue templates, PR template, package script, README, AGENTS
  handoff, roadmap, architecture, Android feasibility, and ADRs.
- PyInstaller one-dir package build under `dist\AirPilot`.
- Runtime termination now reports explicit terminal-side reasons:
  `user_quit_q`, `main_window_closed`, `camera_unrecoverable`, `failsafe`,
  `fatal_exception`, `diagnostics_complete`, `explicit_shutdown`, or `unknown`.
- `Q` is the canonical AirPilot quit key. `Esc` is intentionally ignored by the
  preview loop so Task View/system Esc actions cannot close AirPilot through
  OpenCV key leakage.
- Transient tracker exceptions are counted as `tracking_error_events` and
  converted into one frame of tracking loss instead of terminating the loop.
- PyAutoGUI failsafe disarms mouse output and continues when it fires during
  normal mouse control; repeated corner polling is latched to one warning until
  the pointer leaves the failsafe condition or control is rearmed.

## Architecture

- `src/airpilot/domain`: reusable gesture and cursor domain logic.
- `src/airpilot/camera.py`: OpenCV camera adapter.
- `src/airpilot/tracking.py`: MediaPipe adapter.
- `src/airpilot/input.py`: Windows mouse adapter and fake implementation.
- `src/airpilot/display.py`: Windows virtual-desktop geometry adapter.
- `src/airpilot/actions.py`: gesture-to-action routing and shortcut catalog.
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

Last local automated validation for the pointer-pose/help refinement:

- `uv sync --extra dev`
- `uv run --extra dev ruff format --check .`
- `uv run --extra dev ruff check .`
- `uv run --extra dev mypy src`
- `uv run --extra dev python -m pytest`: 135 passed, including stable
  palm/knuckle pointer-anchor, clutch freeze/resume, click/drag lifecycle, Help
  dictionary, cursor-feedback no-op, and failsafe latch coverage.
- `uv run --extra dev airpilot --list-cameras` detected
  `0: Camera 0 (DirectShow)`.
- `uv run --extra dev airpilot --config %TEMP%\airpilot-validation-pointer-pose-help.json
  --camera 0 --diagnose-seconds 5` opened Camera 0 through DirectShow and
  processed 125 frames at 640x480, about 24.9 fps, with no hand observed,
  `tracking_error_events: 0`, and `camera_reconnects: 0`.
- `uv sync --extra package`
- `powershell -ExecutionPolicy Bypass -File scripts\package_windows.ps1`
- `dist\AirPilot\AirPilot.exe --help`
- `dist\AirPilot\AirPilot.exe --list-cameras` detected
  `0: Camera 0 (DirectShow)`.
- `dist\AirPilot\AirPilot.exe --config %TEMP%\airpilot-packaged-pointer-pose-help.json
  --camera 0 --diagnose-seconds 5` opened Camera 0 through DirectShow and
  processed 87 frames at 640x480, about 17.3 fps, with no hand observed,
  `tracking_error_events: 0`, and `camera_reconnects: 0`.

Manual live hand acquisition and real pointer gestures still must be run with a
hand physically presented to the webcam for this follow-up. Required checks now
focus on thumb-open tracking, thumb-closed clutch, index/middle bend clicks,
drag feel, arm gesture, Help glanceability, Task View, scroll up/down/control,
Clipboard History, failsafe latch behavior, and overall feel.

## Known Issues

- The package is unsigned.
- Camera unplug/replug recovery now retries reopening the same camera index, but
  manual validation is still required to confirm recovery on this hardware.
- Cursor icon override is intentionally disabled; any future feedback should
  remain local to AirPilot UI unless explicitly reapproved.
- Two-hand shortcut mode, two-hand help, two-hand arm, and Task View gesture
  navigation are implemented but not yet manually validated with two physical
  hands.
- MediaPipe emits a `NORM_RECT without IMAGE_DIMENSIONS` warning during live
  hand tracking; it did not reproduce as a crash and is not yet proven to cause
  incorrect gesture behavior in this milestone.
- Multi-monitor crossing, DPI, and UAC/elevated-window behavior need manual
  validation.
- Current emergency controls are preview-window `Q`, pause key `P`, and
  PyAutoGUI corner failsafe; no global hotkey or tray app yet.

## Next

Run source/package validation and CI after each focused branch, then request
compact human validation with:
`run_duration=<minutes before manual quit or unexpected close>
exit=<manual_q|closed_itself> exit_reason=<exact printed reason>
mouse=<ok|fail> click=<ok|fail> feel=<short note>`.

## Decisions Not To Reverse Silently

- Keep domain logic platform-independent for future Android reuse.
- Keep Windows input isolated behind `MouseController`.
- Keep local-only frame processing as the default privacy posture.
- Keep Android future work AccessibilityService-based; do not attempt hidden
  input injection APIs.
