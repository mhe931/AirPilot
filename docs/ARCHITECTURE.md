# Architecture

AirPilot separates perception, domain interpretation, safety policy, and OS
input so the gesture model can be reused across platforms.

## Components

- `camera`: captures local webcam frames with OpenCV.
- `tracking`: converts frames into normalized hand landmarks with MediaPipe.
- `domain`: maps landmarks to cursor positions and gesture events.
- `input`: applies gesture events to Windows mouse/keyboard adapters.
- `display`: reads Windows virtual-desktop geometry for multi-monitor mapping.
- `actions`: routes deliberate shortcut-mode gestures to semantic action IDs and
  fakeable keyboard shortcut dispatch.
- `cursor_feedback`: provides transient Windows cursor-shape feedback while the
  control hand is active, without permanently replacing system cursors.
- `app`: coordinates runtime, preview UI, status, config, and shutdown.

## Event Flow

```text
OpenCVCamera -> MediaPipeHandTracker -> GestureEngine -> ActionRouter -> MouseSafetyGate
                                                    -> MouseController / shortcut dispatch
                                                    -> CursorFeedbackController
                                                    -> OpenCV status preview
```

The domain layer uses only plain dataclasses and normalized landmarks. It does
not import OpenCV, MediaPipe, or PyAutoGUI.

## Two-Hand Model

`TrackingFrame` carries all detected hands plus a `control_hand` alias used by
the existing gesture engine. MediaPipe is configured for up to two hands. The
control-hand policy is deterministic: prefer a detected right hand, otherwise a
left hand, otherwise the first unknown hand. The secondary hand gates shortcut
mode by requiring an intentional second-hand thumb-pinky hold before shortcut
gestures can emit keyboard actions. Separate second-hand holds arm AirPilot
(thumb-middle) and toggle the help dashboard (thumb-index) without entering
shortcut mode.

## Gesture Safety

Gestures are explicit states rather than one-frame classifications:

- Clicks require hold and release. A click candidate locks the cursor position so
  pinch jitter does not move the click target.
- Dragging requires a longer hold plus deliberate movement and consumes the
  click.
- Pinch thresholds use release hysteresis.
- Clicks have cooldowns.
- Scroll uses an explicit held state with pinch hysteresis, accumulated vertical
  wrist movement, configurable sensitivity, and a short emit cooldown.
- Tracking loss resets pending gestures and releases active drag.
- Paused mode suppresses movement and actions; the keyboard pause control is
  always available, while gesture pause is opt-in to reduce accidental pauses.
- Real mouse output is gated by an explicit safe/active state and can be armed
  with the preview key or the deliberate second-hand arm gesture.
- `--no-mouse` and diagnostics lock output off for that run; otherwise `A`
  enables/disables output even if a loaded config had mouse output disabled.
- Conflicting new pinches are canceled rather than emitted as combined actions.
- Shortcut actions run only through configured semantic action IDs, use cooldowns,
  require shortcut mode, and skip risky actions unless explicitly enabled.

## Runtime Defaults

Default gestures:

- Thumb-index: left click on release, with target lock while held; drag starts
  only after hold plus deliberate movement.
- Thumb-middle: right click.
- Thumb-middle hold: middle click.
- Thumb-ring: scroll mode; while held, accumulated vertical wrist movement emits
  repeated wheel events and suppresses pointer movement.
- Thumb-pinky: optional pause/resume hold when enabled in config.
- Second-hand thumb-middle hold: arm from the disarmed startup state.
- Second-hand thumb-index hold: toggle the separate help dashboard.
- Second-hand thumb-pinky hold: shortcut mode; configured shortcut gestures emit
  enabled catalog actions such as copy, paste, clipboard history, Task View, and
  slide navigation. Default Clipboard History is `Win+V` through shortcut-mode
  thumb-middle hold. Default Task View opens with `Win+Tab` through
  shortcut-mode thumb-index hold, navigates with left/right arrow keys from hand
  movement, and confirms with Enter on release.

Default cursor behavior:

- Actual-orientation preview by default; no selfie mirror is applied by default.
- Pointer mapping uses an operator-facing convention: moving the physical hand
  right maps to increasing Windows desktop X, and moving down maps to increasing
  Y. Because an actual-orientation preview is camera-facing, the mapper mirrors X
  by default for intuitive pointer motion while leaving the preview unflipped.
- Runtime display geometry comes from Win32 virtual-screen metrics, so the mapper
  targets absolute virtual-desktop coordinates including negative origins.
- Camera bounds crop the active control region. Defaults intentionally use a
  tighter active region for faster pointer travel.
- Smoothing, sensitivity, and dead zone balance responsiveness against jitter.

## Action Catalog

`ActionConfig.catalog` stores semantic IDs, labels, profiles, key chords,
enabled state, and risky-action flags. The initial catalog covers high-value
Windows, editing, browser, presentation, and media shortcuts. Safe actions such
as copy, paste, Clipboard History (`clipboard.history` / `Win+V`), Task View
(`system.task_view` / `Win+Tab`), and slide navigation are enabled by default.
The old Alt+Tab switch action remains available but is not a default gesture.
Higher impact actions such as lock workstation, close window, desktop switching,
and tab close are present but disabled and/or risky by default.

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
- Automated tests use recording adapters and never move the real pointer, change
  the real cursor, send hotkeys, lock Windows, close windows, or switch desktops.

## Future Android Reuse

Android should reuse:

- Landmark and gesture concepts.
- Debounce/hysteresis/cooldown rules.
- Mapping from gesture events to high-level input intents.

Android must replace:

- Camera adapter with CameraX.
- Input adapter with AccessibilityService/IME/overlay mechanisms.
- UI/runtime shell with native Android components.
