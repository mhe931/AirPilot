# Manual Webcam Validation

Run this checklist on Windows with a webcam.

## Safe Preview

```powershell
uv run --extra dev airpilot --list-cameras
uv run --extra dev airpilot --camera 0 --no-mouse
```

Verify:

- Preview window opens.
- Camera-active state is visible.
- Hand landmarks draw over the hand.
- No frames are saved to the repo, config directory, or temp directory.
- `q` and `Esc` stop the app.
- `p` toggles pause/resume.

## Real Mouse

```powershell
uv run --extra dev airpilot --camera 0
```

Verify:

- Cursor movement is smooth enough for target selection.
- Cursor does not jump wildly on startup.
- Thumb-index short pinch/release emits one left click.
- Holding thumb-index starts drag; release drops.
- Thumb-middle short pinch/release emits one right click.
- Thumb-ring vertical movement scrolls in the expected direction.
- Thumb-pinky hold pauses and resumes.
- Removing the hand stops actions and releases drag.
- Moving the pointer to a screen corner stops through PyAutoGUI failsafe.

## Edge Cases

Verify and record:

- Bad lighting.
- Occlusion.
- Camera unplug/replug.
- Camera already in use by another app.
- Sleep/wake.
- Multi-monitor layout.
- Display scaling above 100%.
- Elevated/UAC windows.

Record observations in `docs/PROJECT_STATUS.md`.
