# Manual Webcam Validation

Run this checklist on Windows with a webcam.

## Terminal Startup

```powershell
uv run --extra dev airpilot --list-cameras
uv run --extra dev airpilot --camera 0 --diagnose-seconds 5
```

Pass:

- Camera 0 is listed.
- Diagnostics prints JSON with `frames > 0`, `frame_width > 0`, and
  `frame_height > 0`.
- Diagnostics includes `camera_reconnects`.
- If your hand is visible to the camera during the diagnostic, `hand_observed`
  should be `true`.

## Safe Preview

```powershell
uv run --extra dev airpilot --camera 0 --no-mouse
```

Pass:

- Preview window opens.
- Overlay shows searching/tracking, active gesture, hand score, fps, mouse off,
  and the control region rectangle.
- Hand landmarks draw over the hand within 3 seconds when a hand is presented.
- No frames are saved to the repo, config directory, or temp directory.
- `q` and `Esc` stop the app.
- `p` toggles pause/resume.

## Real Mouse

```powershell
uv run --extra dev airpilot --camera 0
```

Pass:

- App starts with `mouse safe`; moving your hand does not move the pointer.
- Press `a`; overlay changes to `mouse armed`.
- Cursor reaches all four quadrants without leaving the control region.
- With five thumb-index pinch/releases, exactly five left clicks occur.
- Holding thumb-index starts drag; pressing `p` or removing the hand releases it.
- With five thumb-middle pinch/releases, exactly five right clicks occur.
- Thumb-ring vertical movement scrolls only while the overlay says `scrolling`.
- Thumb-pinky hold pauses and resumes without firing clicks.
- Ambiguous multi-pinch shapes show conflict/cancel behavior, not combined
  clicks.
- Moving the pointer to a screen corner stops through PyAutoGUI failsafe.
- Press `a` again; overlay returns to `mouse safe`.

## Edge Cases

Verify and record:

- Bad lighting.
- Occlusion.
- Camera unplug/replug. If Windows restores the device on the same index within
  the retry window, AirPilot should recover without a manual restart; otherwise
  it should exit with a clear runtime error instead of hanging.
- Camera already in use by another app.
- Sleep/wake.
- Multi-monitor layout.
- Display scaling above 100%.
- Elevated/UAC windows.

Record observations in `docs/PROJECT_STATUS.md`.
