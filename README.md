# AirPilot

AirPilot is a privacy-first, camera-based gesture controller. Phase 1 is a
Windows desktop app that turns webcam hand landmarks into mouse movement,
clicks, dragging, scrolling, pause/resume, and deliberate shortcut commands.

Frames are processed locally. AirPilot does not record or upload camera frames.

## Current Status

Implemented:

- OpenCV webcam capture with camera selection.
- MediaPipe hand tracking.
- Platform-independent gesture state machine with debounce, hysteresis,
  cooldowns, drag lifecycle, scrolling, optional gesture pause/resume, and
  tracking-loss safety.
- Safe-by-default arming gate so real mouse control does not start until the
  user presses `a` or passes `--armed`.
- Smooth cursor mapping with calibration bounds, sensitivity, smoothing, and
  dead zone across the Windows virtual desktop.
- Default actual-orientation preview with operator-facing pointer mapping:
  moving your hand right moves the Windows pointer right.
- Two-hand tracking model with a right-hand-preferred control hand and secondary
  hand reserved for future interactions.
- Compact preview banner for DISARMED, ACTIVE, PAUSED, and preview-only modes.
- Bounded camera reopen attempts after sustained frame-read failures.
- Transient Windows cursor feedback while active control-hand tracking is
  available, restored on shutdown.
- Windows mouse adapter through PyAutoGUI, isolated behind a testable interface.
- Win32 virtual-desktop geometry and pointer movement so multi-monitor layouts,
  including monitors left or above the primary display, can be addressed.
- Configurable shortcut action catalog with safe default two-hand shortcut mode.
- Separate gesture/action help window, opened by `h` or a deliberate two-hand
  help gesture.
- Config persistence under `%APPDATA%\AirPilot\config.json`.
- Synthetic landmark tests that do not require a webcam or desktop automation.
- Preview landmark drawing is compatible with the pinned MediaPipe package and
  falls back to status-only preview if landmark rendering fails.

See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) for the live handoff.

## Requirements

- Windows 10 or newer.
- Python 3.11.
- A webcam.
- `uv` for reproducible local setup.

## Setup

```powershell
git clone git@github.com:mhe931/AirPilot.git
cd AirPilot
uv sync --extra dev
```

## Run

List cameras:

```powershell
uv run --extra dev airpilot --list-cameras
```

Run with real mouse control:

```powershell
uv run --extra dev airpilot --camera 0
```

Real mouse mode starts in safe mode. Press `a` in the preview window to enable
or disable pointer control. The preview shows an `AIRPILOT - DISARMED` or
`AIRPILOT - ACTIVE` banner so the current state is obvious without covering the
camera view. Use `--armed` only when you intentionally want immediate control.

Run safely without moving the mouse:

```powershell
uv run --extra dev airpilot --camera 0 --no-mouse
```

Run headless webcam/tracker diagnostics without moving the mouse:

```powershell
uv run --extra dev airpilot --camera 0 --diagnose-seconds 5
```

Diagnostics JSON includes `camera_reconnects` so unplug/replug recovery can be
verified without moving the pointer.

Controls:

- `q` or `Esc`: stop AirPilot while the preview window is focused.
- `p`: pause/resume while the preview window is focused.
- `a`: arm/disarm real mouse output while the preview window is focused.
- `h`: show/hide the separate gesture and action help window.
- Move the real pointer to a screen corner to trigger PyAutoGUI's failsafe.

If your webcam feed is already non-mirrored at the driver level, you can change
`runtime.flip_camera_x` in `%APPDATA%\AirPilot\config.json`.

Default gestures:

- Thumb + index pinch, then release: left click.
- Thumb + index pinch and hold: drag; release to drop.
- Thumb + middle pinch, then release: right click.
- Thumb + middle pinch and hold, then release: middle click.
- Thumb + ring pinch while moving vertically: scroll.
- Pause gesture is disabled by default to prevent accidental `PAUSED` state;
  keyboard `p` remains available. If enabled in config, thumb + pinky hold
  pauses/resumes.
- Help window: hold thumb + index on the second hand.
- Shortcut mode: hold thumb + pinky on the second hand, then use configured
  control-hand shortcut gestures. Defaults include copy, paste, switch app, next
  slide, and previous slide. Risky actions such as lock workstation and close
  window are disabled by default.

Pointer defaults intentionally favor responsiveness: a smaller active camera
region, higher sensitivity, lighter smoothing, and a small dead zone. Tune
`cursor.camera_min_*`, `cursor.camera_max_*`, `cursor.sensitivity`,
`cursor.smoothing_alpha`, and `cursor.dead_zone_px` in
`%APPDATA%\AirPilot\config.json` if your setup feels too slow or too fast.

## Validate

```powershell
uv run --extra dev ruff format --check .
uv run --extra dev ruff check .
uv run --extra dev mypy src
uv run --extra dev python -m pytest
```

## Package

```powershell
uv sync --extra package
powershell -ExecutionPolicy Bypass -File scripts/package_windows.ps1
```

The unsigned executable is written under `dist\AirPilot`. Code signing and
installer polish are not complete yet. If the webcam briefly disconnects,
AirPilot now retries reopening the same camera index before failing.
