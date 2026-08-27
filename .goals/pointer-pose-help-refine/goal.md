# Goal: Pointer Pose Help Refine

## User Request

Refine AirPilot after real physical testing. Make pointer movement stable and
predictable; do not require thumb/fingertip contact for gestures; use a natural
thumb-close clutch that freezes the pointer so clicks/actions can be accurate;
ensure AirPilot never changes the Windows cursor icon; redesign Help as an
action-first gesture/action dictionary; preserve safety, shortcuts, Task View,
scroll, diagnostics, failsafe latch behavior, packaging, and single-branch repo
policy.

## Refined Goal

Improve AirPilot's Windows gesture-control UX on top of merged PR #8 by making
pointer movement rely on a stable hand/palm anchor rather than finger-tip pose
changes, refining pose/clutch semantics so thumb-open moves and thumb-closed
freezes, and making clutched index/middle bends drive click/drag/right/middle
actions accurately without requiring fingertip contact. Redesign the Help window
into a scannable dictionary where each row starts with what the user wants to do
and then shows the gesture/shortcut. Preserve existing safety, multi-monitor,
Shortcut Mode, Win+V, Win+Tab Task View, scroll, no global cursor-icon override,
runtime exit diagnostics, and failsafe latch behavior.

## Acceptance Criteria

- [ ] Pointer movement uses a stable hand/palm anchor or hybrid reference so
      bending index/middle fingers alone does not significantly move the pointer
      reference; hand right/left/up/down still maps naturally across the Windows
      virtual desktop.
- [ ] Thumb-open state moves the pointer; thumb-closed/bent state immediately
      freezes at the exact current target and resumes smoothly without a large
      jump.
- [ ] Clutched index bend/release produces one left click at the frozen target;
      clutched index hold plus deliberate hand movement starts drag; tracking
      loss/disarm releases drag safely.
- [ ] Clutched middle bend/release produces right click; clutched middle long
      hold produces middle click; right and middle click do not collide.
- [ ] No AirPilot code globally overrides or substitutes Windows cursor icons;
      cursor feedback remains a no-op/normal OS cursor behavior.
- [ ] Help is redesigned as an action-first dictionary (`What it does | Gesture`)
      grouped by useful categories, with common actions first, enabled/available
      state, shortcut keys where useful, and no critical clipping/truncation.
- [ ] Existing features are preserved: camera/tracking stability, actual
      orientation, multi-monitor mapping, two-hand arm/help/Shortcut Mode,
      Clipboard History, Task View, scroll, privacy, Q-only quit, diagnostics,
      runtime exit reasons, and failsafe latch behavior.
- [ ] Synthetic tests cover pose states, pointer anchor stability, clutch freeze
      and resume, click/drag/middle/right click lifecycle, Help dictionary
      content/rendering, cursor icon no-op behavior, and failsafe latch
      regressions.
- [ ] Required validation passes: `uv sync --extra dev`, format, lint, mypy,
      full pytest, source diagnostics/startup smoke, package rebuild, packaged
      diagnostics/startup smoke, CI green, independent review clean, docs
      synchronized, clean synchronized `main` at completion.

## Scope Boundaries

**In scope:**
- Windows desktop AirPilot gesture, cursor, pose, Help, config, tests, docs,
  packaging, PR/merge cleanup.
- One temporary branch from `main`, merged and deleted before final handoff.
- Small focused config/schema updates if needed for pose/pointer tuning.

**Out of scope:**
- Android implementation.
- Full keyboard/virtual keyboard.
- Requiring fingertip contact for core mouse gestures.
- Global Windows cursor-icon changes.
- Many arbitrary new gestures unrelated to the requested core model.
- Weakening safety, privacy, diagnostics, failsafe behavior, or test isolation.

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
- No project-specific format found; use conventional commits where useful.
- Goal subagent commits must include `[B]` or `[I]` markers and an
  `Assisted-by:` trailer.

**Guidelines:**
- `AGENTS.md` is authoritative.
- No `CONSTITUTION.md`, `.agents/guidelines`, or `.github/guidelines` found.
- Relevant workflow files: `.github/workflows/ci.yml`,
  `.github/pull_request_template.md`, `CONTRIBUTING.md`, `pyproject.toml`.

**Rules:**
- Persistent branch policy is `main` only; use a short-lived focused branch and
  delete it before handoff.
- Never push directly to `main`.
- Do not implement Android in Phase 1.
- Keep gesture/domain logic platform-independent.
- Do not store, upload, or log camera frames by default.
- Do not emit clicks on startup, tracking loss, calibration, or a single noisy
  frame.
- Real mouse output starts disarmed unless `--armed` is explicitly passed.
- `--no-mouse` and diagnostics lock output off.
- Tests must use fakes/recording adapters and never move the real pointer or
  send real keyboard shortcuts.
- Risky shortcuts remain disabled by default.
- Verify subagent work before trusting it.
