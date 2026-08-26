# AirPilot

AirPilot is a privacy-first, camera-based gesture controller. Phase 1 is a
Windows desktop app that turns webcam hand landmarks into mouse movement,
clicks, dragging, scrolling, and pause/resume commands.

Frames are processed locally. AirPilot does not record or upload camera frames.

## Current Status

Implemented:

- OpenCV webcam capture with camera selection.
- MediaPipe hand tracking.
- Platform-independent gesture state machine with debounce, hysteresis,
  cooldowns, drag lifecycle, scrolling, pause/resume, and tracking-loss safety.
- Smooth cursor mapping with calibration bounds, sensitivity, smoothing, and
  dead zone.
- Windows mouse adapter through PyAutoGUI, isolated behind a testable interface.
- Config persistence under `%APPDATA%\AirPilot\config.json`.
- Synthetic landmark tests that do not require a webcam or desktop automation.

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

Run safely without moving the mouse:

```powershell
uv run --extra dev airpilot --camera 0 --no-mouse
```

Controls:

- `q` or `Esc`: stop AirPilot while the preview window is focused.
- `p`: pause/resume while the preview window is focused.
- Move the real pointer to a screen corner to trigger PyAutoGUI's failsafe.

Default gestures:

- Thumb + index pinch, then release: left click.
- Thumb + index pinch and hold: drag; release to drop.
- Thumb + middle pinch, then release: right click.
- Thumb + ring pinch while moving vertically: scroll.
- Thumb + pinky hold: pause/resume.

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
installer polish are not complete yet.
