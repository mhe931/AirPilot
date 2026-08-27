# Goal Summary: Crash UI Registry Fix

## What was achieved

- Added `src/airpilot/registry.py` as the structured gesture/action registry
  baseline with physical gesture text, emoji/text labels, modes, actions,
  emitted keys, and enabled/safety state.
- Fixed the Help truncation defect that displayed physical gestures as truncated
  keyboard-like fragments such as `Shortcut Mode + h`.
- Improved dashboard mode replacement so default and shortcut-mode opportunities
  do not stale-append across context changes.
- Added Help/Settings/Quit-related registry coverage and tests for physical
  gesture vs emitted-key separation.
- Fixed the native shutdown crash path by using one shared Tk root for Help and
  Settings and changing cleanup ordering so OpenCV windows are destroyed before
  Tk teardown.
- Integrated the work into `main`, pushed it, merged/closed PR #12, and removed
  short-lived local/remote branches so only `main` remains.

## Acceptance criteria mapping

- Gesture-vs-key separation: covered by registry tests and Help row regression
  tests; emitted shortcuts stay in the Keys/Shortcut field.
- Help truncation/completeness: formatter truncation was removed and Treeview
  Help consumes non-truncated rows.
- Dashboard context replacement: tested for default vs shortcut mode and any-mode
  entries.
- Crash lifecycle: shared Tk root, idempotent cleanup, and OpenCV-before-Tk
  teardown were implemented and independently inspected.
- MediaPipe/TFLite warnings: determined benign informational/native logging, not
  the crash cause.
- Git cleanup: verified local branches `main` only and remote branches
  `origin/main` plus `origin/HEAD` only.

## Iteration history

1. **Iteration 1 — PASS.** Builder implemented registry, Help/dashboard fixes,
   lifecycle crash fix, validation, packaging smoke, merge to `main`, and branch
   cleanup. Inspector verified code, tests, PR #12 merge, and main-only branch
   state.

## Validation evidence

- Builder reported:
  - `ruff format --check`
  - `ruff check`
  - `mypy src`
  - `pytest` (`264 passed, 1 skipped`)
  - source camera list and diagnostics
  - packaged camera list and diagnostics (`21.4 fps`, `hand_observed: true`)
- Inspector reported:
  - `pytest tests/` (`285 passed, 1 skipped`)
  - registry/Help/dashboard/lifecycle tests passing
  - PR #12 merged
  - local/remote branches cleaned to `main` only

## Residual physical checks

- Extended live camera session with Help and Settings open/close repeatedly to
  confirm no native crash on the user's display/camera.
- Physical shortcut-mode transitions to confirm dashboard rows replace cleanly
  with real hand input.
- Physical validation of Help/Settings/Quit configured gestures, including
  Quit's deliberate activation and orderly cleanup.

## Suggested squash command

The work is already integrated to `main` per the user's request. If a future
cleanup squash were desired, use the recorded initial SHA:

```bash
git reset --soft ff492e85d771c47f7edfc45c6877f5c1b29d4fe1
git commit -m 'fix(ui): align gesture registry and stabilize shutdown

AirPilot now separates physical gestures from emitted shortcuts in Help and the
dashboard, uses a structured registry baseline, and shuts down shared UI/native
resources safely after repeated Help/Settings use.

Assisted-by: Claude:Sonnet-4.6'
```
