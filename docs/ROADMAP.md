# Roadmap

## Milestone 1: Windows Vertical Slice

- Webcam capture.
- Hand tracking.
- Real mouse movement and gestures.
- Synthetic tests.
- Config persistence.
- Basic docs and CI.

Status: implemented; awaiting manual live tracking validation and CI result.

## Milestone 2: Windows Hardening

- Camera reconnect/recovery.
- Global hotkey and tray pause/quit.
- Calibration UI.
- Multi-monitor and DPI validation.
- Safer startup wizard with mouse disabled by default until user arms control.
- Better gesture visualization and confidence feedback.

## Milestone 3: Distribution

- Reliable PyInstaller packaging.
- Installer.
- Code signing.
- Clean uninstall.
- Windows VM install smoke test.

## Milestone 4: Android Prototype

- CameraX foreground app.
- AccessibilityService action adapter.
- Optional overlay pointer.
- Deterministic, user-command-driven gesture mapping.
- Play policy review before distribution.
