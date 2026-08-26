# Project Goals

AirPilot is a production-quality, privacy-first, camera-based gesture control
system.

## Phase 1

Build a Windows app that performs:

- Webcam capture and camera selection.
- Local hand-landmark tracking.
- Gesture recognition for left click, right click, drag/drop, scrolling, and
  pause/resume.
- Smooth cursor mapping with calibration, sensitivity, smoothing, and dead-zone
  tuning.
- Real Windows mouse control behind a testable adapter.
- Visible camera/tracking/status feedback.
- Emergency stop/failsafe behavior.
- Configuration persistence.
- Synthetic tests that do not require camera hardware or desktop automation.

## Future

Explore Android device control, initially for Samsung Galaxy S24 Ultra, by
reusing AirPilot's domain gesture concepts while respecting Android platform,
security, and Play policy limits.

## Privacy

AirPilot must process frames locally by default, avoid recording/uploading
frames, and clearly document any future telemetry or data movement before it is
implemented.
