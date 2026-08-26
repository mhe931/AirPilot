# Architecture

AirPilot separates perception, domain interpretation, safety policy, and OS
input so the gesture model can be reused across platforms.

## Components

- `camera`: captures local webcam frames with OpenCV.
- `tracking`: converts frames into normalized hand landmarks with MediaPipe.
- `domain`: maps landmarks to cursor positions and gesture events.
- `input`: applies gesture events to the Windows mouse through PyAutoGUI.
- `cursor_feedback`: provides transient Windows cursor-shape feedback while the
  control hand is active, without permanently replacing system cursors.
- `app`: coordinates runtime, preview UI, status, config, and shutdown.

## Event Flow

```text
OpenCVCamera -> MediaPipeHandTracker -> GestureEngine -> MouseSafetyGate -> MouseController
                                      -> CursorFeedbackController
                                      -> OpenCV status preview
```

The domain layer uses only plain dataclasses and normalized landmarks. It does
not import OpenCV, MediaPipe, or PyAutoGUI.

## Two-Hand Model

`TrackingFrame` carries all detected hands plus a `control_hand` alias used by
the existing gesture engine. MediaPipe is configured for up to two hands. The
control-hand policy is deterministic: prefer a detected right hand, otherwise a
left hand, otherwise the first unknown hand. The secondary hand is exposed for
future keyboard, zoom, modifier, or two-hand chord features but is not yet used
to emit actions.

## Gesture Safety

Gestures are explicit states rather than one-frame classifications:

- Clicks require hold and release.
- Dragging requires a longer hold and consumes the click.
- Pinch thresholds use release hysteresis.
- Clicks have cooldowns.
- Tracking loss resets pending gestures and releases active drag.
- Paused mode suppresses movement and actions.
- Real mouse output is gated by an explicit safe/active state.
- `--no-mouse` and diagnostics lock output off for that run; otherwise `A`
  enables/disables output even if a loaded config had mouse output disabled.
- Conflicting new pinches are canceled rather than emitted as combined actions.

## Runtime Defaults

Default gestures:

- Thumb-index: left click on short release, drag on hold.
- Thumb-middle: right click.
- Thumb-ring: scroll mode.
- Thumb-pinky: pause/resume hold.

Default cursor behavior:

- Actual-orientation preview by default; no selfie mirror is applied by default.
- Pointer mapping follows the displayed camera orientation.
- Camera bounds crop the active control region.
- Smoothing and dead zone reduce jitter.

## Failure Handling

- Camera open/read failures produce a clear runtime error and clean shutdown.
- Transient camera read failures are retried before surfacing an error.
- Sustained read failures trigger bounded reopen attempts on the same camera
  index before AirPilot exits.
- Missing or invalid landmarks do not emit clicks.
- Preview landmark rendering failures disable only the landmark overlay and keep
  the gesture loop running.
- Cursor feedback restoration runs during cleanup so transient cursor state does
  not intentionally persist after quit, errors, or camera failure.
- Tracking loss reports status and resets cursor smoothing.
- PyAutoGUI corner failsafe is enabled by default.

## Future Android Reuse

Android should reuse:

- Landmark and gesture concepts.
- Debounce/hysteresis/cooldown rules.
- Mapping from gesture events to high-level input intents.

Android must replace:

- Camera adapter with CameraX.
- Input adapter with AccessibilityService/IME/overlay mechanisms.
- UI/runtime shell with native Android components.
