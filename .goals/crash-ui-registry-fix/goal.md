# Goal: Crash UI Registry Fix

## User Request

Fix AirPilot's gesture documentation/dashboard correctness and sudden native
crash, complete the remaining UI work, deploy the verified build, then leave
`main` as the only local/remote branch. Own the task end to end.

## Refined Goal

Continue the current clean `main` implementation without rebuilding completed
work. Fix Help/dashboard drift by introducing one authoritative structured
gesture/action registry that generates recognition mappings, Help data, and
dashboard rows with strict separation between physical gestures and emitted
keyboard shortcuts. Diagnose and fix the native Windows/Python 3.11 shutdown
crash around OpenCV/Tk/MediaPipe lifecycle, complete Help/dashboard polish,
add conflict-free Help/Settings/Quit physical gestures, validate source and
packaged builds, integrate to `main`, deploy/package smoke-test the artifact,
and finish with clean synchronized `main` as the only local/remote branch.

## Acceptance Criteria

- [ ] Repository instructions, Git/worktrees/PRs, screenshots/report context,
  `src/airpilot/app.py` around lines 313/461, gesture registry, UI threading,
  tests, and config schema are inspected before implementation.
- [ ] One authoritative structured gesture/action registry exists with gesture
  components, human-readable labels, emoji labels, mode/context, action,
  optional keyboard shortcut/output, enabled/safety state, and section/status.
- [ ] Recognition mappings, Help, and dashboard data are generated from that
  registry so they cannot drift.
- [ ] Physical gesture text is never confused with emitted keyboard keys:
  Help's Gesture column shows e.g. `Shortcut Mode + index`, while
  Keys/Shortcut shows outputs such as `Win+Tab`.
- [ ] The `Switch apps | Shortcut Mode + h` truncation/incorrect display is
  eliminated and covered by regression tests.
- [ ] Help content is exhaustive and complete: every implemented gesture,
  action, mode, movement, keyboard control, mouse action, shortcut,
  presentation/browser/media/window/media action, risky/disabled action,
  Help, Settings, pause/resume, arm/disarm, quit, shortcut-mode/dashboard
  behavior, both hands/fingers, and movements appears exactly once in the
  appropriate Help/dashboard sections.
- [ ] Help uses real layout widgets/table columns with polished alignment,
  column sizing, wrapping/scrolling/filtering, emojis plus text labels, no
  clipping, no broken separators, and no horizontal dependence at normal size.
- [ ] The left dashboard shows only currently possible next gestures. It
  replaces, not appends, rows whenever context/mode changes; default mode shows
  default opportunities only; shortcut mode clears old entries and shows only
  shortcut-mode mappings; mode exit restores the correct list; remapping updates
  immediately without stale/flickering rows.
- [ ] Help and dashboard use the same accurate gesture emojis and text labels,
  retaining requested visual style/emojis. Emoji is never the only meaning.
- [ ] Configurable conflict-free physical gestures exist for Help, Settings, and
  Quit. They appear in Help/dashboard, keep keyboard alternatives in
  Keys/Shortcut only, do not fire repeatedly while held, and Quit is resistant
  to accidental activation and performs orderly cleanup.
- [ ] Existing behavior is preserved: non-overlapping UI, non-maximizable main
  window, default-populated Settings, opacity/typography controls, readable
  status text, configurable mouse/gesture settings, thumb/index activation
  target 90 degrees with ±10 default tolerance, natural two-finger scrolling,
  safe arming/conflict handling, drag release, pause/disarm behavior, corner
  failsafe, camera fallback, diagnostics, privacy, and normal Windows cursor.
- [ ] Crash diagnosis is evidence-based. Instrument/reproduce the shutdown path
  before guessing and document whether MediaPipe/TFLite warnings are causal or
  benign.
- [ ] Thread/lifecycle fix ensures Tk/UI work only occurs on the UI thread; no
  native callbacks or UI updates occur after teardown; stop is signaled,
  scheduled callbacks are canceled, workers stopped/joined if any, camera and
  tracker/native objects released, held mouse buttons released, windows
  destroyed, and exit happens idempotently for Quit gesture, keyboard quit,
  title-bar close, errors, and camera loss.
- [ ] Useful crash logging is added without exposing sensitive data.
- [ ] Tests cover registry completeness/uniqueness, gesture-vs-key semantic
  separation, Help/Settings/Quit mappings, conflicts, dashboard replacement per
  mode, mode exit, live remapping, Help/dashboard coverage with no unknown/stale
  items, alignment/wrapping/scrolling/filtering/emojis, no overlap, defaults,
  opacity, disabled maximize, scrolling, mouse settings, crash/lifecycle
  idempotency, and repeated Help/Settings open-close/startup-shutdown paths.
- [ ] Stress/diagnostic validation includes repeated Help/Settings open-close,
  shortcut-mode transitions, camera loss/reconnect where feasible, Quit gesture,
  keyboard quit, title-bar close, pause/disarm, repeated startup/shutdown, and
  an extended live camera session or deterministic simulated equivalent with
  any remaining physical-hand check clearly identified.
- [ ] Formatter, lint, mypy, full relevant tests, source diagnostics, packaging,
  deployed/packaged smoke tests, final diff inspection, and final Git/branch
  verification all pass.
- [ ] Valid work is integrated into `main`, committed and pushed; build artifact
  is deployed/prepared per repository packaging process and smoke-tested; all
  obsolete local/remote branches are deleted only after proven merged/
  superseded/integrated; final state is clean synchronized `main` with local
  branches `main` only and remote branches `origin/main` plus `origin/HEAD`.

## Scope Boundaries

**In scope:**
- Current AirPilot Windows desktop app, existing Python/OpenCV/MediaPipe/
  PyAutoGUI/Tkinter stack, config/schema migration, action/gesture registry,
  Help/Settings/preview/dashboard UI, lifecycle/shutdown code, tests, docs if
  directly relevant, package build, smoke tests, Git/PR/branch cleanup.

**Out of scope:**
- Android implementation.
- New non-stdlib dependencies unless strictly unavoidable.
- Enabling risky OS actions by default.
- Deleting unmerged or unverified branches.
- Discarding user changes.
- Camera frame recording/uploads/log persistence.
- System shutdown/hibernate.
- Global Windows cursor icon/scheme changes.

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

**Guidelines:**
- `AGENTS.md`
- `CONTRIBUTING.md`
- `.github/workflows/ci.yml`
- `.github/pull_request_template.md`
- No `CONSTITUTION.md`, `.agents/guidelines`, `.github/guidelines`,
  `justfile`, `Makefile`, or `package.json` were found.

**Rules:**
- Persistent branch is `main`; short-lived focused branches are allowed but must
  be merged/deleted before handoff.
- Never delete unmerged work or discard user changes.
- Phase 1 is Windows-only; Android remains documentation-only.
- Real mouse output starts disarmed unless `--armed` is passed.
- Do not emit clicks on startup, tracking loss, calibration, or a single noisy
  frame.
- Keep gesture/domain logic reusable and platform-independent.
- Do not store, upload, or log camera frames by default.
- Keep mouse injection behind `MouseController` so tests use fakes.
- Do not intentionally change Windows cursor icons or cursor schemes.
- Verify subagent work before trusting it.
- Goal creation context: current branch is clean synchronized `main` at
  `ff492e85d771c47f7edfc45c6877f5c1b29d4fe1`; no open PRs; local branches
  `main` only; remote branches `origin/main` and `origin/HEAD` only; one
  worktree is present.
