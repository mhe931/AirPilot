# Architecture

AirPilot separates perception, domain interpretation, safety policy, and OS
input so the gesture model can be reused across platforms.

## Components

- `camera`: captures local webcam frames with OpenCV.
- `tracking`: converts frames into normalized hand landmarks with MediaPipe.
- `domain`: maps landmarks to cursor positions and gesture events.
- `input`: applies gesture events to the Windows mouse through PyAutoGUI.
- `app`: coordinates runtime, preview UI, status, config, and shutdown.

## Event Flow

```text
OpenCVCamera -> MediaPipeHandTracker -> GestureEngine -> MouseController
                                      -> OpenCV status preview
```

The domain layer uses only plain dataclasses and normalized landmarks. It does
not import OpenCV, MediaPipe, or PyAutoGUI.

## Gesture Safety

Gestures are explicit states rather than one-frame classifications:

- Clicks require hold and release.
- Dragging requires a longer hold and consumes the click.
- Pinch thresholds use release hysteresis.
- Clicks have cooldowns.
- Tracking loss resets pending gestures and releases active drag.
- Paused mode suppresses movement and actions.

## Runtime Defaults

Default gestures:

- Thumb-index: left click on short release, drag on hold.
- Thumb-middle: right click.
- Thumb-ring: scroll mode.
- Thumb-pinky: pause/resume hold.

Default cursor behavior:

- Horizontal mirror enabled to match user expectation in webcam preview.
- Camera bounds crop the active control region.
- Smoothing and dead zone reduce jitter.

## Failure Handling

- Camera open/read failures produce a clear runtime error and clean shutdown.
- Missing or invalid landmarks do not emit clicks.
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
