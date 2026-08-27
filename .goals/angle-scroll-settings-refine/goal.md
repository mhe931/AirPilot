# Goal: Angle Scroll Settings Refine

## User Request

Own the next AirPilot refinement end to end. Fix thumb activation, scrolling,
Help tables, preview readability, and build configurable gesture/mouse settings.
Use the preceding screenshots and discussion as acceptance evidence. Continue
valid existing work; do not recreate completed fixes.

## Refined Goal

AirPilot must keep the already-merged clutch, Help-window, and normal-cursor
fixes, then refine the Windows desktop app so real pointer movement activates
only when a robust thumb-index angle is near the configured target. Scrolling
must feel like continuous two-finger touchpad/touchscreen scrolling, Help must
show real readable action tables, the preview header must become compact and
readable, and users must be able to configure mouse/gesture settings through a
normal Windows-style Settings window. The result must be implemented safely,
tested, packaged, pushed to a focused PR, and left unmerged pending physical
validation.

## Acceptance Criteria

- [ ] Thumb activation uses a robust thumb-index angle derived from appropriate
  landmarks, normalized for hand scale, in-plane rotation, and left/right hands.
  Defaults are target angle `90` degrees and tolerance `10` degrees, accepting
  `80` through `100` degrees and rejecting `79` and `101`.
- [ ] Mouse pointer movement is enabled only when the thumb-index activation
  angle is within the configured range after hysteresis/debounce; thumb folded
  clutches/freezes immediately; reopening/resuming never jumps the cursor.
- [ ] Index and middle bending do not independently freeze pointer movement
  unless a configured gesture binding explicitly requires them.
- [ ] Diagnostics/status/settings expose the measured thumb angle and activation
  state where useful without creating dense unreadable preview text.
- [ ] Scrolling is continuous while the configured scroll gesture is held:
  captures an initial hand anchor, converts proportional vertical displacement
  to smooth scroll deltas, has no initial jump, resets cleanly on release, and
  freezes pointer movement while active.
- [ ] Scroll behavior is configurable for sensitivity, dead zone, smoothing,
  natural direction toggle, rate/repeat limit, and axis if supported by the
  existing mouse abstraction.
- [ ] Tracking loss, pause, disarm, conflicts, and shutdown cancel scrolling and
  click/drag states safely without stuck drags or accumulated scroll motion.
- [ ] A normal Windows-style Settings window is accessible from the app/keyboard,
  supports Apply/Cancel/Reset to defaults, constrains invalid values, persists
  through the existing config system, migrates backward compatibly, and cannot
  crash startup on malformed settings.
- [ ] Gesture bindings are data-driven and persisted: hand selection supports
  left, right, control, secondary, or either; each finger supports folded,
  extended, or any; movement supports none, left, right, up, and down; trigger
  supports enter, hold/repeat, and release where appropriate; each binding
  supports movement threshold, hold time, cooldown, sensitivity where relevant,
  action assignment from the existing catalog, and enabled/disabled state.
- [ ] Independent left- and right-hand bindings are supported, conflicts and
  duplicate firing are detected, and validation errors are shown clearly.
- [ ] Include the configurable example `thumb folded + index folded + hand moves
  right -> PowerPoint next slide` without forcing it as an unsafe universal
  default.
- [ ] Mouse settings include thumb target angle, thumb tolerance,
  activation hysteresis/debounce, pointer sensitivity/speed, smoothing, existing
  active-region bounds/dead zone, scroll sensitivity, scroll direction, scroll
  dead zone, and scroll smoothing with brief explanations and safe ranges.
- [ ] The existing responsive Help window remains, but action information renders
  as readable aligned tables with columns `Action | Gesture | Shortcut/Keys |
  State`; long cells wrap, rows stay aligned, vertical scrolling/filtering remain,
  no horizontal scrolling is needed at normal supported sizes, and displayed
  gestures/settings reflect the current configuration instead of stale hardcoded
  text.
- [ ] Preview status replaces the oversized/dense green header with a compact,
  readable, high-contrast status panel that fits 640x480 and DPI-scaled Windows
  displays. It prioritizes app state, armed/disarmed, pointer/clutch/gesture
  state, control hand, confidence, and essential shortcuts; detailed diagnostics
  move out of the primary header.
- [ ] Regression tests cover angle geometry at 79, 80, 90, 100, and 101 degrees;
  tolerance changes; hysteresis; left/right hands; rotation; malformed/missing
  landmarks; continuous scroll direction/proportional displacement/dead zone/
  smoothing/release/tracking-loss/pause/disarm/no-initial-jump; gesture
  serialization/migration/matching/movement/conflicts/cooldown/one-shot/repeat/
  PowerPoint example; Settings validation/persistence/reset; Help table bounds
  and wrapping; and status rendering at small sizes/DPI-scaled geometry.
- [ ] Validation passes: focused tests, `uv sync --extra dev`,
  `uv run --extra dev ruff format --check .`, `uv run --extra dev ruff check .`,
  `uv run --extra dev mypy src`, `uv run --extra dev python -m pytest`, source
  camera diagnostics, `uv sync --extra package`, Windows package build, packaged
  camera list, and packaged diagnostics.
- [ ] A focused branch and PR are pushed; CI passes; the PR is not merged until
  physical validation confirms thumb angle activation, clutch/resume, pointer,
  touch-style scroll, custom binding, Help tables, readable header, and
  click/drag/failsafe regression.

## Scope Boundaries

**In scope:**
- Windows 11 desktop runtime implemented in Python with MediaPipe/OpenCV,
  PyAutoGUI, Tkinter/stdlib UI where appropriate, existing config system,
  existing action catalog, tests, docs, packaging, branch/PR management.
- Preserving and building on PR #10's already-merged fixes for no-jump clutch
  resume, native Help window, and normal Windows cursor behavior.

**Out of scope:**
- Merging before physical validation.
- Android implementation.
- New non-stdlib GUI/runtime dependencies unless strictly unavoidable.
- Risky OS actions enabled by default.
- Camera frame recording, uploads, or persisted frame logs.
- System shutdown, hibernate, or global cursor scheme/icon changes.

## Applicable Project Conventions

**Quality gate command:**
- `uv sync --extra dev`
- `uv run --extra dev ruff format --check .`
- `uv run --extra dev ruff check .`
- `uv run --extra dev mypy src`
- `uv run --extra dev python -m pytest`
- `uv run --extra dev airpilot --list-cameras`
- `uv run --extra dev airpilot --camera 0 --diagnose-seconds 5`
- `uv sync --extra package`
- `powershell -ExecutionPolicy Bypass -File scripts\package_windows.ps1`
- `.\dist\AirPilot\AirPilot.exe --list-cameras`
- `.\dist\AirPilot\AirPilot.exe --camera 0 --diagnose-seconds 5`

**Commit convention:**
- Conventional commits.
- Goal Builder commits must use `type(scope): [B] description` and trailer
  `Assisted-by: Claude:Sonnet-4.6`.
- Goal Inspector commits must use `chore(scope): [I] description` and trailer
  `Assisted-by: Claude:Haiku-4.5`.
- Repository policy also requires the normal Copilot co-author trailer when
  this chat creates commits; subagents should include the goal skill trailer.

**Guidelines:**
- `AGENTS.md`
- `CONTRIBUTING.md`
- `.github/workflows/ci.yml`
- No `CONSTITUTION.md`, `.agents/guidelines`, `.github/guidelines`,
  `justfile`, `Makefile`, or `package.json` were found.

**Rules:**
- Default branch is `main`; never push directly to `main`.
- Only persistent branch should be `main`; focused short-lived branches are
  allowed but should be merged/deleted after handoff when appropriate.
- Phase 1 is Windows-only; Android stays documentation-only.
- Preserve unrelated user work.
- Real mouse output starts disarmed unless `--armed` is passed.
- Do not emit clicks on startup, tracking loss, calibration, or a single noisy
  frame.
- Keep gesture/domain logic reusable and platform-independent.
- Do not store, upload, or log camera frames by default.
- Keep mouse injection behind `MouseController` so tests use fakes.
- Do not intentionally change Windows cursor icons or cursor schemes.
- Verify subagent work before trusting it.
- Current context at goal creation: current branch
  `bugfix/thumb-help-cursor-physical-validation` is clean and tracks origin;
  PR #10 is already merged; latest relevant commit is
  `dd140e42584071f0eff5f9ddab1c619a160793f6`. Builder should synchronize with
  latest `origin/main` and create one new focused branch for this refinement.
