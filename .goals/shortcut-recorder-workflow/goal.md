# Goal: Shortcut Recorder Assignment Workflow

## User Request

Improve AirPilot's custom gesture assignment workflow. Continue the current
verified implementation and preserve all prior requirements.

Requirements:
- Replace the free-text `Action ID` field with a keyboard-shortcut recorder.
- When focused, show a state such as `Waiting for shortcut...` and capture the
  user's complete key combination, e.g. `Ctrl+9`, `Alt+W`, `Ctrl+Shift+P`, or
  supported special/function keys.
- Normalize and display shortcuts consistently while preserving the intended
  keys.
- Validate unsupported, modifier-only, reserved, or unsafe combinations.
- When the configured gesture occurs, emit its recorded shortcut exactly once
  using the existing safe input mechanism. Respect debounce/cooldown and release
  all pressed keys even after errors, pause, disarm, or shutdown.
- Permit users to select a gesture already assigned elsewhere, but detect the
  conflict immediately.
- Show a VS Code-style warning identifying the conflicting gesture, its current
  action/shortcut and context, and what the new assignment will replace.
- Require explicit confirmation before overriding. On confirmation, replace the
  previous mapping atomically; on cancellation, preserve it.
- Clearly expose repeated/conflicting gestures in Settings with warning
  indicators and searchable/filterable details.
- Account for gesture context/mode: treat mappings as conflicts only when their
  activation contexts can overlap.
- After replacement, refresh Settings, Help, and the left dashboard immediately
  from the authoritative gesture registry so no stale assignment remains.
- Persist shortcuts and overrides safely with backward-compatible settings
  migration.
- Add tests for shortcut capture/normalization, modifier and special keys,
  invalid combinations, exact key emission, debounce, forced key release,
  overlapping versus separate contexts, warning text, cancel/confirm override,
  atomic persistence, and live Help/dashboard refresh. Run full relevant
  validation and inspect the actual UI.
- Deliver only: `status | changes | validation | git/PR | blockers | next`.
- After all old and new tasks are finished, hibernate the system.

## Refined Goal

Implement a safe, data-driven keyboard-shortcut assignment workflow for
AirPilot's configurable gesture settings. Users should record a keyboard
shortcut instead of typing an action id, receive clear conflict warnings before
overrides, and see Settings, Help, and the left dashboard refresh immediately
from the authoritative gesture/action registry. Gesture-triggered shortcut
emission must be exact, one-shot/cooldown-safe, and must release any pressed keys
on errors, pause, disarm, or shutdown. The system must remain backward
compatible, validated by tests and existing quality gates, and end with a clean
Git/PR state; hibernation is allowed only after the final report is delivered and
all work is complete.

## Acceptance Criteria

- [ ] Settings replaces any free-text custom `Action ID` entry with a focused
  keyboard-shortcut recorder that displays `Waiting for shortcut...`, captures
  complete key combinations, handles supported special/function keys, and
  normalizes display such as `Ctrl+9`, `Alt+W`, and `Ctrl+Shift+P`.
- [ ] Shortcut validation rejects unsupported keys, modifier-only shortcuts,
  reserved app/system controls, and unsafe combinations with visible actionable
  errors and no malformed persisted state.
- [ ] Configured gesture shortcuts emit exactly once through the existing safe
  input path, honor debounce/cooldown, and release all pressed keys on normal
  completion, errors, pause, disarm, tracking loss, and shutdown.
- [ ] Gesture conflicts are detected immediately using context/mode overlap
  rules. Non-overlapping contexts are allowed; overlapping duplicate gestures
  show a VS Code-style warning containing the conflicting gesture, existing
  action/shortcut, existing context, and replacement target.
- [ ] Conflict override requires explicit confirmation. Confirm replaces the
  previous mapping atomically and refreshes all derived UI; cancel preserves the
  existing mapping and persistence unchanged.
- [ ] Settings clearly exposes repeated/conflicting gestures with warning
  indicators plus searchable/filterable details.
- [ ] Help and the left dashboard refresh immediately from the authoritative
  registry/settings after replacement, with no stale assignment, gesture/key
  confusion, or duplicated rows.
- [ ] Shortcut settings and overrides persist safely with backward-compatible
  migration for older configs and defaults.
- [ ] Automated tests cover shortcut capture/normalization, modifier/special
  keys, invalid combinations, exact emission, debounce, forced key release,
  context overlap conflicts, warning text, cancel/confirm override behavior,
  atomic persistence, migration, and live Help/dashboard refresh.
- [ ] Existing quality gates pass: formatting, linting, mypy, full tests,
  source diagnostics where practical, Windows packaging, packaged smoke tests,
  and final diff/UI inspection.
- [ ] Git workflow is safe: inspect branch/worktree/PR state, use focused work,
  do not discard user work, integrate valid work to `main`, push/PR as
  appropriate, and finish with clean synchronized `main` as the only persistent
  branch where permissions allow.
- [ ] The final hibernation request is not performed until after all tasks,
  validation, final report, and cleanup are complete.

## Scope Boundaries

**In scope:**
- Shortcut recorder UI and validation in Settings.
- Data model/migration for custom recorded shortcuts.
- Conflict detection/override UX for gesture mappings.
- Safe shortcut emission through existing input abstractions.
- Immediate Settings, Help, and dashboard refresh from authoritative registry
  and current persisted settings.
- Regression/unit/UI tests and existing AirPilot validation/package workflow.
- Git/PR management and final clean branch/worktree state.

**Out of scope:**
- Android implementation.
- Changing AirPilot's safety-by-default arming model.
- Adding unrelated dependencies or unrelated UI redesigns.
- Modifying system-wide cursor schemes or storing/uploading camera frames.
- Merging or deleting unmerged work without proof it is integrated or
  superseded.

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
- No repository-specific message format found; use conventional commits.
- Builder commits must use `type(scope): [B] description` and include
  `Assisted-by: Claude:Sonnet-4.6`.
- Inspector commits must use `chore(scope): [I] description` and include
  `Assisted-by: Claude:Haiku-4.5`.

**Guidelines:**
- `AGENTS.md`
- `CONTRIBUTING.md`
- `.github\workflows\ci.yml`
- No `CONSTITUTION.md`, `.agents\guidelines\`, or `.github\guidelines\` found.

**Rules:**
- Phase 1 remains Windows-only; Android stays documentation-only unless
  explicitly requested.
- Keep platform-independent gesture/cursor logic in `src\airpilot\domain`.
- Keep real OS input behind injectable adapters so tests use fakes.
- Real mouse output starts disarmed unless `--armed` is explicitly passed.
- Do not store, upload, or log camera frames by default.
- Do not emit clicks on startup, tracking loss, calibration, or a single noisy
  frame.
- Preserve safe arming, conflict cancellation, drag release, pause/disarm
  behavior, corner failsafe, camera fallback, diagnostics, and normal Windows
  cursor behavior.
- Default and only persistent branch is `main`; short-lived focused branches are
  allowed but must be merged/deleted before handoff.
- Never push directly to `main` unless explicitly required by the established
  cleanup/finalization process; preserve unrelated user work.
