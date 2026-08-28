# Goal: Native crash and main-window overlap

## User Request

Diagnose and permanently fix AirPilot's reproducible native crash and the
main-window overlap shown in the screenshot. Do not continue unrelated feature
work until these issues are resolved and stress-tested.

Evidence:
- Command: `uv run --extra dev airpilot --camera 0`
- Crash after about 69 seconds:
  `Fatal Python error: PyEval_RestoreThread: the function must be called with the GIL held`
- Current frame:
  - `src/airpilot/app.py:542` in `run`
  - `src/airpilot/app.py:394` in `main`
- It previously failed similarly at `app.py:461`, so the earlier
  lifecycle/threading fix was insufficient.
- MediaPipe logs immediately before failure include
  `landmark_projection_calculator` using `NORM_RECT` without image dimensions.
- Screenshot shows camera-preview text such as FPS, score, Help, Settings, and
  Quit instructions rendered behind the left sidebar and unreadable.

## Refined Goal

Find the root cause of the Windows/Python 3.11 native crash in the live
camera/MediaPipe/OpenCV/Tk/PyAutoGUI runtime and implement a durable lifecycle
fix. Add enough diagnostic tooling and stress tests to prove the full app can
start, run, open/close Help and Settings, pause/disarm/re-arm, handle camera
interruptions, and shut down without GIL crashes, hangs, orphan threads, held
keys/buttons, or post-shutdown callbacks. Also fix the main preview geometry so
the sidebar reserves space and all camera diagnostic/instruction text is drawn
inside the visible camera region, never behind the sidebar.

## Acceptance Criteria

- [ ] The exact current code at `src/airpilot/app.py` lines around 394 and 542
  and recent crash/lifecycle changes are inspected and documented.
- [ ] The crash is reproduced repeatedly on Windows/Python 3.11 with camera 0,
  or a credible blocker/equivalent reproducer result is documented.
- [ ] `faulthandler`, thread-aware diagnostic logging, and native crash evidence
  are enabled for crash/stress runs.
- [ ] Every MediaPipe/TFLite, OpenCV, Tk, Pillow, and PyAutoGUI call path is
  audited for cross-thread native-object use, concurrent process/read/close/
  release, callbacks after destruction, UI calls outside the main thread,
  cleanup races, and wrong-thread finalization.
- [ ] One thread exclusively owns camera and MediaPipe objects.
- [ ] Tracker inference is serialized; `process()` is never concurrent.
- [ ] Native objects are never closed, recreated, released, or finalized while
  inference is active.
- [ ] Worker results, if any, are queued to the UI thread; every Tk operation is
  performed on the UI/main thread.
- [ ] Runtime has explicit lifecycle states and idempotent ordered shutdown:
  stop signal, cancel callbacks, stop new frames, join worker, close tracker,
  release camera, release input keys/buttons, destroy UI.
- [ ] Help/Settings/dashboard callbacks, gesture actions, camera retries, and
  shutdown paths are investigated for triggering the race and fixed if needed.
- [ ] The MediaPipe `NORM_RECT` warning is investigated and corrected if caused
  by AirPilot; warnings are not merely suppressed.
- [ ] Compatible pinned versions of Python, MediaPipe, protobuf, OpenCV, and
  Pillow are checked against official compatibility evidence; dependency changes
  are made only when justified and locked reproducibly.
- [ ] A minimal camera+MediaPipe reproducer exists and can isolate application
  code from dependency/native-runtime failure.
- [ ] Main preview layout uses explicit non-overlapping top status banner, left
  gesture dashboard/sidebar, and camera preview/text regions.
- [ ] Sidebar reserves its own width. FPS, score, Help, Settings, Quit, gesture
  state, and other important text are positioned relative to the visible preview
  region after the sidebar and remain fully visible.
- [ ] Overlay text wraps or repositions within the camera region if it would
  collide, including long mappings, customized fonts, sidebar width changes,
  window resizing, and supported DPI scaling.
- [ ] Separate sidebar/overlay background-opacity settings are preserved and
  text remains fully opaque/readable.
- [ ] A deterministic regression test or geometry assertion proves sidebar and
  overlay text bounds never intersect.
- [ ] Stress verification includes at least 30 repeated start/stop cycles,
  15-minute continuous camera/inference run, repeated Help/Settings open-close,
  shortcut-mode transitions, pause/disarm/re-arm, camera interruption/recovery,
  keyboard/gesture/title-bar exits, and packaged executable smoke/stress tests.
- [ ] Formatter, lint, type checks, full tests, diagnostics, and packaged smoke
  tests pass.
- [ ] The verified fix is committed and pushed to `main` through repository
  governance; remaining branches are not deleted and no release is deployed
  until crash stress and layout verification pass.

## Scope Boundaries

**In scope:**
- Windows Phase 1 live runtime crash diagnosis/fix, diagnostic/stress tooling,
  camera/MediaPipe/OpenCV/Tk/PyAutoGUI lifecycle, shutdown ordering, input
  release safety, main preview layout geometry, tests, packaging smoke, PR/merge
  to `main`, and directly relevant dependency evidence.

**Out of scope:**
- Android implementation.
- Unrelated feature work or UI redesign not required for the crash/layout fix.
- Storing, uploading, or logging camera frames by default.
- Deleting unrelated branches or deploying a release before stress gates pass.
- Changing dependencies without compatibility evidence and a reproducible lock.

## Applicable Project Conventions

**Quality gate command:**
- `uv sync --extra dev`
- `uv run --extra dev ruff format --check .`
- `uv run --extra dev ruff check .`
- `uv run --extra dev mypy src`
- `uv run --extra dev python -m pytest`
- `uv sync --extra package`
- `powershell -ExecutionPolicy Bypass -File scripts/package_windows.ps1`

**Commit convention:**
- Use conventional commits with role markers during goal iterations:
  `type(scope): [B] description` for Builder and
  `chore(scope): [I] description` for Inspector, title <= 72 characters.
- Include `Assisted-by: Claude:Sonnet-4.6` in Builder commits and
  `Assisted-by: Claude:Haiku-4.5` in Inspector commits.
- Use short-lived feature branches and PRs. Never push directly to `main`.

**Guidelines:**
- No `CONSTITUTION.md`, `.agents/guidelines/`, or `.github/guidelines/` were
  present during discovery.

**Rules:**
- Preserve unrelated user work.
- Never push directly to `main`.
- Do not leave completed feature branches behind unless cleanup is explicitly
  blocked.
- Do not implement Android in Phase 1.
- Keep gesture/domain logic reusable and platform-independent.
- Do not store, upload, or log camera frames by default.
- Do not emit mouse clicks on startup, tracking loss, calibration, or a single
  noisy frame.
- Real mouse output starts disarmed unless `--armed` is passed explicitly.
- Verify subagent work before trusting it.
