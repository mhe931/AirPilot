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
  cooldowns, click-location lock, deliberate drag lifecycle, scrolling, optional
  gesture pause/resume, and tracking-loss safety.
- Safe-by-default arming gate so real mouse control does not start until the
  user presses `a`, performs the deliberate arm gesture, or passes `--armed`.
- Smooth cursor mapping with calibration bounds, sensitivity, smoothing, and
  dead zone across the Windows virtual desktop.
- Default actual-orientation preview with operator-facing pointer mapping:
  moving your hand right moves the Windows pointer right.
- Two-hand tracking model with a right-hand-preferred control hand and secondary
  hand reserved for future interactions.
- Compact preview banner for DISARMED, ACTIVE, PAUSED, and preview-only modes.
- Bounded camera reopen attempts after sustained frame-read failures.
- Runtime shutdown always prints an `AirPilot exit reason: ...` line so
  unexpected closes leave terminal evidence.
- Transient tracker frame failures and PyAutoGUI failsafe events disarm/recover
  where possible instead of disappearing without context.
- No global Windows cursor icon override; operator feedback stays in the
  preview/help UI.
- Windows mouse adapter through PyAutoGUI, isolated behind a testable interface.
- Win32 virtual-desktop geometry and pointer movement so multi-monitor layouts,
  including monitors left or above the primary display, can be addressed.
- Configurable shortcut action catalog with safe default two-hand shortcut mode.
- Separate action-first help dictionary, opened by `h` or a deliberate two-hand
  help gesture, with quick-start rows, mouse/control gestures, shortcut mappings,
  grouped action shortcuts, and safety reference content.
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

Real mouse mode starts in safe mode. Hold second-hand thumb + middle to arm, or
press `a` in the preview window to enable or disable pointer control. The
preview shows an `AIRPILOT - DISARMED` or
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

Diagnostics JSON includes `camera_reconnects` and `tracking_error_events` so
unplug/replug recovery and transient tracker faults can be verified without
moving the pointer.

Controls:

- `q`: stop AirPilot while the preview window is focused.
- `Esc`: ignored by AirPilot; this avoids Task View/system Esc actions leaking
  back into the preview and closing the app.
- `p`: pause/resume while the preview window is focused.
- `a`: arm/disarm real mouse output while the preview window is focused.
- `h`: show/hide the native, resizable gesture and action Help window.
- Move the real pointer to a screen corner to trigger PyAutoGUI's failsafe.

If your webcam feed is already non-mirrored at the driver level, you can change
`runtime.flip_camera_x` in `%APPDATA%\AirPilot\config.json`.

Default gestures:

- Second-hand thumb + middle hold: arm AirPilot from the disarmed startup state.
- Thumb open/extended away from the palm: pointer follows a stable control-hand
  palm/knuckle anchor, even if the index or middle finger is bent.
- Thumb closed/bent toward the palm: clutch/freeze the pointer immediately.
  Opening the thumb resumes from the frozen target without jumping.
- While clutched, bend and release index: left click at the frozen target.
- While clutched, hold bent index and move deliberately: drag; release to drop.
- While clutched, bend and release middle: right click.
- While clutched, hold middle long enough and release: middle click.
- Thumb + ring pinch while moving the hand vertically: scroll wheel. AirPilot
  uses accumulated wrist movement while the pinch is held, so small movement can
  build into smooth repeated scrolling without moving the pointer.
- Pause gesture is disabled by default to prevent accidental `PAUSED` state;
  keyboard `p` remains available. If enabled in config, thumb + pinky hold
  pauses/resumes.
- Help window: hold thumb + index on the second hand.
- Shortcut mode: hold thumb + pinky on the second hand, then use configured
  control-hand shortcut gestures. Defaults include copy, paste, clipboard
  history (`Win+V` via thumb-middle hold), Task View (`Win+Tab` via
  thumb-index hold), next slide, and previous slide. While Task View is open,
  move the held hand left/right to select and release to open. The old Alt+Tab
  action remains available in the catalog but is no longer a default gesture.
  Risky actions such as lock workstation and close window are disabled by
  default.

Pointer defaults intentionally favor responsiveness: a smaller active camera
region, higher sensitivity, lighter smoothing, and a small dead zone. Tune
`cursor.camera_min_*`, `cursor.camera_max_*`, `cursor.sensitivity`,
`cursor.smoothing_alpha`, and `cursor.dead_zone_px` in
`%APPDATA%\AirPilot\config.json` if your setup feels too slow or too fast.
For scroll feel, tune `gestures.scroll_sensitivity`,
`gestures.scroll_activation_y_delta`, `gestures.scroll_cooldown_ms`, and
`gestures.scroll_units_per_step`. For pose feel, tune
`gestures.thumb_close_threshold`, `gestures.thumb_open_threshold`,
`gestures.finger_bend_threshold`, and `gestures.finger_extend_threshold`.

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

AirPilot does not intentionally replace, decorate, animate, or globally modify
the Windows mouse cursor. Cursor feedback is limited to the preview/status and
Help UI.

## Troubleshooting Unexpected Closes

AirPilot prints one terminal-side shutdown reason on every exit:

- `user_quit_q`
- `main_window_closed`
- `camera_unrecoverable`
- `failsafe`
- `fatal_exception`
- `diagnostics_complete`
- `explicit_shutdown`
- `unknown`

If AirPilot closes without a manual `q`, copy the exact `AirPilot exit reason:
...` line and any warning/error above it. The app never logs camera frames.

Repository policy: `main` is the only persistent branch. Temporary branches are
allowed for focused work, but they should be merged and deleted promptly.
