# Goal: Final UI Polish Main

## User Request

Finish and polish AirPilot's configurable gesture/UI system, resolve the visible
layout/help defects, and leave Git with `main` as the only branch. Own discovery
through verified delivery.

## Refined Goal

Continue the current valid AirPilot implementation on PR #11 without rebuilding
completed thumb-angle, scroll, Settings, Help, sidebar, typography, and binding
work. Fix the visible main-window overlap/clipping defects, disable main-window
maximize, add validated opacity settings, ensure Settings defaults are always
visible, rebuild Help with real layout widgets/table columns from the
authoritative gesture/action registry, complete the live in-app gesture
dashboard, validate the source and packaged Windows app, then safely integrate
the work into `main`. Finish with clean synchronized `main` as the only local
and remote non-HEAD branch, deleting only branches proven merged/superseded and
reporting any permission blocker exactly.

## Acceptance Criteria

- [ ] Main preview/window layout has no overlapping/clipped sidebar, header,
  camera, boxes, or text at supported sizes. It uses reserved regions, padding,
  minimum dimensions, wrapping, and responsive sizing for the left gesture
  dashboard, top status area, and camera preview.
- [ ] Layout is tested for small and large windows, long labels, custom
  fonts/sizes, and supported display scaling.
- [ ] The main preview window cannot be maximized and its maximize title-bar
  button is removed/disabled where supported, while normal move, minimize, and
  close behavior remains.
- [ ] Configurable opacity exists where cleanly supported for the main window,
  sidebar/dashboard, overlays/status panels, Help, and Settings. Values are
  bounded, validated, persisted, resettable, have readable defaults, and support
  live preview where practical.
- [ ] Settings loads and visibly displays defaults for every field on first run,
  after reset, and when migrating missing/old configuration. No unexplained blank
  controls appear and malformed settings cannot crash startup.
- [ ] Configurable typography per UI region is retained and completed: font
  family, size, weight/style, foreground/background color, contrast/defaults,
  preview/reset, validation, persistence, and backward-compatible migration.
- [ ] The unreadable green top text is fixed by default with clean high-contrast
  styling while preserving customization.
- [ ] Help is rebuilt as a polished, aligned, scrollable UI using real layout
  widgets/table columns, not space-padded text. It has no clipping, overlap,
  broken separators, or horizontal overflow; headings, spacing, typography,
  column widths, wrapping, navigation, filter, and resizing are consistent.
- [ ] Help is generated from the authoritative gesture/action registry/settings
  so it cannot drift from implementation.
- [ ] Help includes every supported gesture, mode, movement, keyboard control,
  mouse action, shortcut, presentation/browser/media/window action,
  risky/disabled action, and status, including Help, Settings, pause/resume,
  arm/disarm, quit, shortcut-mode, and dashboard behavior.
- [ ] Help and dashboard use consistent emojis plus text labels. Emoji must not
  be the only meaning. Required examples include clear finger/hand gestures such
  as `👌`, `🙌`, `☝🏻`, `👆🏻`, `🤏🏻`, `🤘🏻`, `🖐🏻`, `✋🏻`, `👌🏻`, `👐🏻`,
  `🤟🏻`, `✊🏻`, and suitable movement/action emojis.
- [ ] The left-side in-app gesture dashboard is complete: it shows gesture emoji,
  name, mapped action, state/availability, and relevant mode; includes Help,
  Settings, arm/disarm, pause, quit, mouse, and shortcut gestures; expands
  shortcut-mode mappings immediately when the second hand activates shortcut
  mode; updates live after remapping; and is generated from the same registry
  and settings as Help.
- [ ] Prior behavior is preserved: configurable thumb/index activation target
  with default `90` degrees and `±10` tolerance, natural touchpad-style
  scrolling, configurable mouse behavior, per-hand/per-finger/movement gesture
  assignments, configurable Help/Settings gestures, high-contrast status text,
  safe arming, conflict detection, drag release on pause/disarm/loss, corner
  failsafe, camera fallback, diagnostics, privacy, and normal Windows cursor
  behavior.
- [ ] Defaults remain accessible, uncluttered, and backward compatible.
- [ ] Tests cover defaults/reset/migration, opacity bounds/persistence,
  gesture/action registry completeness, angle tolerance, conflicts, movement
  actions, Help/Settings mappings, scrolling, mouse settings, no overlap/clipping,
  sidebar/header/camera geometry, maximize unavailable, defaults populated,
  opacity/font previews, Help alignment/filtering/scrolling/emojis/wrapping,
  complete registry coverage, long text, custom font sizes, and supported DPI
  scaling.
- [ ] Validation passes: formatter, lint, mypy, complete relevant tests, source
  camera/headless diagnostics where supported, Windows packaging/build checks,
  packaged camera list, and packaged diagnostics.
- [ ] Final diff is inspected. Actual UI/artifacts are verified where feasible;
  any remaining physical-hand validation is clearly separated from automated and
  simulated verification.
- [ ] Git is safely integrated: local/remote branches, worktrees, open PRs,
  uncommitted changes, and divergence are inspected before history changes;
  valid work is integrated into `main`, committed and pushed; related PRs are
  closed/updated as appropriate; attached worktrees are removed before branch
  deletion; no unmerged branch or changes are deleted; branch protection or
  permission blockers are reported exactly.
- [ ] Final state is clean synchronized `main`, no stale worktrees, and `main`
  is the only local and remote branch except `origin/HEAD`.

## Scope Boundaries

**In scope:**
- Current AirPilot Windows desktop app, existing Python/MediaPipe/OpenCV/
  PyAutoGUI/Tkinter stack, config/schema migration, action/gesture registry,
  Help/Settings/preview UI, tests, docs if directly needed, package build,
  PR #11 integration, local/remote branch cleanup.

**Out of scope:**
- Android implementation.
- New non-stdlib dependencies unless unavoidable.
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
- Default/persistent branch is `main`; never push directly to `main` unless the
  user explicitly requests integration after validation. This goal explicitly
  requests final integration and pushed `main`.
- Focused branches are allowed but should be merged/deleted before handoff.
- Phase 1 is Windows-only; Android remains documentation-only.
- Preserve unrelated user work and never delete unmerged branches/changes.
- Real mouse output starts disarmed unless `--armed` is passed.
- Do not emit clicks on startup, tracking loss, calibration, or a single noisy
  frame.
- Keep gesture/domain logic reusable and platform-independent.
- Do not store, upload, or log camera frames by default.
- Keep mouse injection behind `MouseController` so tests use fakes.
- Do not intentionally change Windows cursor icons or cursor schemes.
- Verify subagent work before trusting it.
- Goal creation context: branch `feat/angle-scroll-settings-refine` is clean and
  tracks origin; PR #11 is open, clean, and CI-passing; local branches are
  `main`, `bugfix/thumb-help-cursor-physical-validation`, and
  `feat/angle-scroll-settings-refine`; remote branches are `origin/main`,
  `origin/bugfix/thumb-help-cursor-physical-validation`, and
  `origin/feat/angle-scroll-settings-refine`; only one worktree is present.
