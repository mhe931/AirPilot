# Goal: Help layout, transparency, and custom shortcuts

## User Request

Finish AirPilot's Help/layout/transparency work and fix custom gesture shortcuts
that display but do not execute. Continue existing valid work, preserve prior
requirements, deploy the verified result, and complete the approved Git cleanup.

Visible defects:
- Help text is truncated; Intro consumes table space; Gesture content does not fit.
- Sidebar covers important overlay/status text.
- Custom binding `go_last_tab` displays its ID/name or catalog action instead of
  executing recorded shortcut `Ctrl+9`.
- Overlay/sidebar background transparency is not independently configurable.

## Refined Goal

Make the native AirPilot desktop UI correctly lay out Help content, overlay
status, sidebar dashboard, and camera preview without truncation or overlap.
Add independently configurable overlay/status and sidebar/dashboard background
opacity settings that affect only backgrounds and are persisted/migrated. Fix the
custom gesture shortcut pipeline so saved/reloaded custom shortcuts execute the
recorded keyboard chord, not the internal binding ID, while keeping catalog
actions explicit and preserving conflict detection, debounce, refresh, and safe
key-release behavior. Verify the result with automated tests, quality gates,
packaging, smoke checks, and final Git cleanup into `main`.

## Acceptance Criteria

- [ ] Help Intro/safety/quick explanation is in a separate wrapped panel above
  the table, outside table rows.
- [ ] Help table below the Intro has columns for emoji, action, gesture,
  keys/shortcut, and state.
- [ ] Gesture column has substantially more default width than before.
- [ ] Help window and table are resizable, including user-resizable column
  dividers with sensible minimum widths; column widths may be persisted.
- [ ] Long Help cell text wraps with dynamic row height; there are no hidden
  suffixes or truncation at default window size.
- [ ] Help provides vertical scrolling and avoids horizontal scrolling at normal
  default window size.
- [ ] Help filtering/navigation continue to work and every registered
  gesture/action is included.
- [ ] Physical gestures are never replaced by action IDs or keyboard keys in
  Help/dashboard display.
- [ ] Main preview uses explicit, non-overlapping layout regions for top
  status/overlay, left contextual gesture dashboard, and camera preview.
- [ ] Sidebar never covers status, FPS, score, instructions, or other important
  overlay text across configured font sizes, sidebar widths, long mappings, DPI
  scaling, and normal resizing.
- [ ] Disabled maximize behavior is preserved.
- [ ] Settings exposes separate bounded percentage/slider controls for
  overlay/status background opacity and sidebar/dashboard background opacity.
- [ ] Opacity controls show numeric values, live preview, defaults, reset,
  validation, persistence, migration, and dynamic contrast with accessible
  defaults.
- [ ] Transparency affects only region backgrounds; text/icons remain fully
  opaque and readable.
- [ ] A saved and reloaded custom binding for `Ctrl+9` emits the exact
  normalized `Ctrl+9` chord when its gesture activates and never dispatches
  `go_last_tab`.
- [ ] Recorded custom shortcuts take precedence when present; catalog actions
  run only when explicitly selected; ambiguous custom/catalog configuration is
  prevented or made explicit.
- [ ] Settings, Help, and dashboard show a useful action label plus the actual
  shortcut, not only the internal ID.
- [ ] Supported shortcuts include combinations such as `Ctrl+9`, `Alt+W`,
  modifiers, function keys, and supported special keys.
- [ ] Dispatch emits once per recognized trigger using debounce/cooldown and
  releases all pressed keys on success, failure, pause, disarm, camera loss, and
  shutdown.
- [ ] VS Code-style conflict detection identifies the occupied gesture/context
  and current shortcut/action; confirmation atomically replaces; cancellation
  changes nothing.
- [ ] Registry, runtime matcher, Help, and dashboard refresh immediately after
  Apply without restarting the app.
- [ ] Dispatch failures surface through concise logs/UI feedback instead of
  silently showing the binding name.
- [ ] Prior behavior is preserved: contextual dashboard replacement, complete
  gesture coverage, Help/Settings/Quit gestures, natural scrolling, mouse
  settings, typography, defaults, safe arming, conflict handling, and native
  crash lifecycle fix.
- [ ] Focused tests cover custom shortcut execution, custom-vs-catalog
  precedence, invalid shortcuts, conflict confirm/cancel, immediate Apply
  refresh, debounce, forced key release, Help layout requirements, layout
  non-overlap, opacity defaults/bounds/persistence/migration/independence, and
  opaque readable text.
- [ ] Full validation runs formatter, lint, mypy, pytest, diagnostics or
  equivalent non-moving smoke checks, packaging, deployment smoke test, and final
  diff review.
- [ ] Valid work is integrated into `main`, pushed, and stale local/remote
  branches or worktrees are removed only if proven merged or superseded.

## Scope Boundaries

**In scope:**
- Windows Phase 1 desktop UI, settings, config migration, registry, action
  dispatch, shortcut recording/binding, tests, documentation directly tied to
  changed behavior, packaging and smoke verification, and Git cleanup.

**Out of scope:**
- Android implementation.
- Storing, uploading, or logging camera frames by default.
- Changing the underlying computer-vision model or MediaPipe architecture unless
  strictly necessary for this goal.
- Broad unrelated refactors, new package managers, new linters, or unrelated UI
  redesign beyond the requested Help/layout/transparency/shortcut fixes.

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
- Repository history also uses short-lived branches and merge commits; do not
  push directly to `main`.

**Guidelines:**
- No `CONSTITUTION.md`, `.agents/guidelines/`, or `.github/guidelines/` were
  present during discovery.

**Rules:**
- Preserve unrelated user work.
- Never push directly to `main`.
- Do not leave local or remote feature branches behind after completed work.
- Do not implement Android in Phase 1.
- Keep gesture/domain logic reusable and platform-independent.
- Do not store, upload, or log camera frames by default.
- Do not emit mouse clicks on startup, tracking loss, calibration, or a single
  noisy frame.
- Real mouse output starts disarmed unless `--armed` is passed explicitly.
- Verify subagent work before trusting it.
