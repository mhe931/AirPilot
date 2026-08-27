# Roadmap

## Milestone 1: Windows Vertical Slice

- Webcam capture.
- Hand tracking.
- Real mouse movement and gestures.
- Synthetic tests.
- Config persistence.
- Basic docs and CI.

Status: implemented; terminal webcam diagnostics and packaged smoke tests
passed; awaiting final manual gesture usability validation for the active
Windows UX hardening PR.

## Milestone 2: Windows Hardening

- Camera reconnect/recovery.
- Global hotkey and tray pause/quit.
- Calibration UI.
- Multi-monitor and DPI validation.
- Safer startup wizard with mouse disabled by default until user arms control.
- Better gesture visualization and confidence feedback.
- Virtual keyboard and richer two-hand gestures using the current two-hand
  tracking model.

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
