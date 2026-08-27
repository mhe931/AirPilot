# Goal: Configurable UI Completion

## User Request

Complete AirPilot's configurable gesture/UI system and fix the remaining
interaction issues. Own discovery, implementation, integration, validation, and
delivery end to end.

## Refined Goal

Continue from the current valid `feat/angle-scroll-settings-refine` branch and
PR #11 without duplicating already-completed thumb-angle, scroll, Settings,
Help, and data-driven binding work. Complete the remaining configurable
gesture/UI system by polishing and extending gesture bindings, adding live
contextual gesture/action sidebar guidance, making visible text styling
configurable by UI region, preserving readable high-contrast defaults, and
verifying the Windows source and packaged application. Leave the PR open and
unmerged pending physical hand validation.

## Acceptance Criteria

- [ ] Existing valid PR #11 work remains intact: mouse activation uses a
  configurable thumb-index angle with default target `90` degrees and tolerance
  `10` degrees; natural touch-style scrolling remains smooth/configurable;
  Settings/Help windows remain native/responsive; data-driven gesture bindings
  and the disabled PowerPoint next-slide example remain available.
- [ ] Mouse settings are comprehensive and user-editable: pointer sensitivity,
  smoothing, active-region bounds, dead zone, thumb target angle, angle
  tolerance, activation hysteresis/debounce, scroll direction/speed,
  scroll dead zone/smoothing, failsafe, and other existing mouse/runtime
  parameters are surfaced with safe validation, Apply/Cancel/Reset,
  persistence, and backward-compatible migration.
- [ ] Gesture bindings are fully configurable and data-driven without scattered
  hardcoded combinations: per finger for both hands (extended/folded/ignored),
  hand selector (`left`, `right`, `control`, `secondary`, `either`), movement
  direction/threshold combinations, trigger (`enter`, `hold/repeat`, `release`),
  hold/cooldown/sensitivity, enabled state, and assignable action from the
  action catalog including click, drag, scroll, copy, paste, presentation
  next/previous, shortcuts, open Help, and open Settings.
- [ ] Configurable gestures exist for opening/closing Help and opening/closing
  Settings. They must not fire repeatedly while held or accidentally toggle
  windows multiple times.
- [ ] Conflicts and unsafe/ambiguous mappings are detected and surfaced clearly
  in Settings and configuration validation; risky OS actions remain disabled by
  default and malformed settings cannot crash startup.
- [ ] The configurable example `thumb folded + index folded + hand moves right
  -> presentation next slide` remains shipped disabled by default and can be
  enabled/configured by the user.
- [ ] A left-side contextual gesture/action panel appears in the preview. It
  lists available gestures and assigned actions clearly, updates live based on
  active mode, detected hand(s), current mappings, shortcut mode, and settings,
  and immediately expands shortcut-mode options when a second hand activates
  shortcut mode.
- [ ] The sidebar uses intuitive and consistent emojis/icons for fingers, hands,
  movement directions, and actions. The same gesture emojis are used in Help and
  sidebar rows.
- [ ] Help preserves its current responsive/native quality but renders
  gesture/action instructions as a clean table with columns `Emoji`, `Gesture`,
  `Action`, and `Notes/Status`; long cells wrap, rows align, filtering and
  vertical scrolling remain, and no horizontal scrolling is needed at supported
  sizes.
- [ ] Visible text styling is configurable by UI region: status/header text,
  overlay labels, sidebar, Help, Settings, instructions, gesture feedback, and
  other meaningful text areas support font family, size, weight/style,
  foreground color, and background/contrast where applicable.
- [ ] Text style settings have sensible accessible defaults, safe validation,
  preview/reset controls, persistence, and backward-compatible migration.
  The unreadable green top text is fixed by default with a clean high-contrast
  style while preserving user customization.
- [ ] Preview remains compact, readable, responsive, and low-clutter at 640x480
  and DPI-scaled Windows displays. It avoids flicker, clipped diagnostic walls,
  accidental input, and excessive CPU usage.
- [ ] Safety and behavior are preserved: safe-by-default arming, pause/disarm
  drag release, conflict cancellation, corner failsafe, camera fallback,
  diagnostics, privacy/no frame persistence, normal Windows cursor behavior,
  and current click/drag/scroll behavior.
- [ ] Tests cover angle tolerance, gesture recognition, conflicts, movement
  actions, Settings persistence/migration, natural scrolling, live sidebar
  updates, emoji consistency, Help table wrapping/filtering, typography controls,
  preview/reset, resizing/readable defaults, and Help/Settings gesture triggers
  without repeated accidental toggles.
- [ ] Validation passes: focused tests, `uv sync --extra dev`,
  `uv run --extra dev ruff format --check .`, `uv run --extra dev ruff check .`,
  `uv run --extra dev mypy src`, `uv run --extra dev python -m pytest`, source
  camera/headless diagnostics where supported, `uv sync --extra package`,
  Windows package build, packaged camera list, and packaged diagnostics.
- [ ] Final diff is inspected. PR #11 is updated, CI passes, and the PR remains
  unmerged until physical validation confirms thumb angle activation,
  clutch/resume, pointer, touch-style scroll, custom binding, Help tables,
  readable header/sidebar, Settings text controls, and click/drag/failsafe
  regression.

## Scope Boundaries

**In scope:**
- Extending current branch `feat/angle-scroll-settings-refine` and PR #11.
- Windows 11 desktop runtime with existing Python, MediaPipe, OpenCV, PyAutoGUI,
  Tkinter/stdlib UI, config system, action catalog, tests, docs, package build,
  and PR update.
- Reusing and extending existing data-driven binding/settings code from PR #11.

**Out of scope:**
- Merging before physical validation.
- Android implementation.
- New non-stdlib UI/runtime dependencies unless unavoidable.
- Enabling risky OS actions by default.
- Camera frame recording/uploads/log persistence.
- System shutdown/hibernate.
- Global Windows cursor icon/scheme modifications.

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
- No `CONSTITUTION.md`, `.agents/guidelines`, `.github/guidelines`,
  `justfile`, `Makefile`, or `package.json` were found.

**Rules:**
- Default branch is `main`; never push directly to `main`.
- Only persistent branch should be `main`; focused short-lived branches are
  allowed and should be merged/deleted after handoff when appropriate.
- Phase 1 is Windows-only; Android remains documentation-only.
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
  `feat/angle-scroll-settings-refine` is clean and tracks origin; PR #11 is
  open, clean, and CI-passing; latest commit is
  `d385b49bc28e4e910954fb276b5f33bffe8c2adb`.
