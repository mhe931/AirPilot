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
- Overlay shows a compact preview-only/disarmed/active/paused state banner,
  tracking details, controls, and the control region rectangle.
- Hand landmarks draw over the hand within 3 seconds when a hand is presented.
- If preview landmark rendering fails, the app should stay running and show
  `preview landmarks disabled` rather than crashing.
- No frames are saved to the repo, config directory, or temp directory.
- `q` and `Esc` stop the app.
- `p` toggles pause/resume.

## Real Mouse

```powershell
uv run --extra dev airpilot --camera 0
```

Pass:

- App starts with `AIRPILOT - DISARMED`; moving your hand does not move the
  pointer.
- Preview orientation matches the actual camera view, not selfie mirroring.
- Press `a`; overlay changes to `AIRPILOT - ACTIVE`.
- Press `h`; a separate gesture/action help window opens or closes without
  blocking camera processing or clipping text.
- Hold thumb-index on the second hand; the same help window toggles only after a
  deliberate hold.
- Move your hand right; the Windows pointer moves right. Move left/up/down; the
  pointer follows the same physical direction.
- Cursor reaches all four quadrants without leaving the control region.
- Pointer response feels usable with the faster defaults and is not obviously
  slow or jumpy.
- While active and tracking a usable hand, Windows cursor feedback changes to a
  hand/pointer-style cursor where supported; it restores on hand loss, disarm,
  pause, quit, or runtime failure.
- With five thumb-index pinch/releases, exactly five left clicks occur.
- Holding thumb-index starts drag; pressing `p` or removing the hand releases it.
- With five thumb-middle pinch/releases, exactly five right clicks occur.
- With five deliberate thumb-middle hold/releases, exactly five middle clicks
  occur.
- Thumb-ring vertical movement scrolls only while the overlay says `scrolling`.
- Thumb-pinky hold does not pause by default. Pressing `p` pauses/resumes without
  firing clicks. If gesture pause is explicitly enabled in config, thumb-pinky
  hold pauses and resumes without firing clicks.
- Ambiguous multi-pinch shapes show conflict/cancel behavior, not combined
  clicks.
- Moving the pointer to a screen corner stops through PyAutoGUI failsafe.
- Press `a` again; overlay returns prominently to `AIRPILOT - DISARMED`.

## Two-Hand Tracking

```powershell
uv run --extra dev airpilot --camera 0 --no-mouse
```

Pass:

- One visible hand shows `hands 1`.
- Two visible hands show `hands 2`.
- The control hand remains stable when hand ordering changes; current policy
  prefers a reliably classified right hand.
- Holding thumb-pinky on the second hand enters shortcut mode and suppresses
  normal mouse click/scroll output.

## Shortcut Actions

Do not start with risky shortcuts such as lock workstation or close window.
First validate safe actions:

- In a text field, select text manually, enter shortcut mode, perform the default
  copy gesture, and verify copy works.
- Enter shortcut mode and perform the default paste gesture; verify paste works.
- Enter shortcut mode and perform switch-app only when changing windows is safe.
- In a presentation or compatible viewer, enter shortcut mode and verify next
  slide and previous slide.
- Verify the overlay briefly shows `ACTION: ...` when an action fires.

## Compact Feedback

After the real-mouse and help-window pass, report:

```text
pause_accidental=<yes|no> pause_intentional=<ok|fail> speed=<slow|good|too_fast> help_key=<ok|fail> help_gesture=<ok|fail> help_window=<ok|fail> preview=<ok|fail> feel=<short note>
```

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
- Pointer can cross monitor boundaries. If a monitor is left or above the primary
  monitor, validate that movement reaches that negative-coordinate display.
- Display scaling above 100%.
- Elevated/UAC windows.

Record observations in `docs/PROJECT_STATUS.md`.
