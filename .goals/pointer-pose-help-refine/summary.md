# Goal Summary: Pointer Pose Help Refine

## Result

PASS. AirPilot's Windows gesture-control UX was refined to use a stable pointer
anchor, natural thumb clutch semantics, pose-based click/drag gestures, and an
action-first Help dictionary while preserving safety and diagnostics behavior.

## Acceptance criteria mapping

- Pointer stability: implemented a weighted palm/knuckle pointer reference with
  legacy fallback so finger bends no longer drive the cursor reference.
- Thumb clutch: thumb-open moves; thumb-closed freezes; clutch release rebases
  the cursor mapper so the first resumed frame does not jump.
- Left click and drag: clutched index bend/release clicks once at the frozen
  target; clutched index hold plus deliberate hand movement starts drag; safety
  releases remain covered.
- Right and middle click: clutched middle bend/release handles right click, and
  middle long hold handles middle click without action collision.
- Cursor icon safety: cursor feedback remains no-op and does not globally
  override Windows cursor icons.
- Help redesign: Help is now organized as `What it does | Gesture |
  Shortcut/Keys | State`, grouped by user action categories with common actions
  first.
- Existing features: Shortcut Mode, Clipboard History, Task View, scroll,
  multi-monitor mapping, Q-only quit, diagnostics, privacy, and failsafe latch
  behavior were preserved in code and regression tests.
- Tests and docs: synthetic tests and documentation were updated for pointer
  stability, clutch resume, action lifecycles, Help content, cursor feedback, and
  manual validation.

## Iteration history

1. FAIL: Inspector found that releasing clutch after moving the hand could still
   cause a large resume jump (`480.0` px in the probe).
2. PASS: Builder added cursor rebase support and regression coverage. Inspector
   verified release remained frozen, stationary resume distance was `0.0`, and a
   subsequent nudge moved smoothly by `32.0` px.

## Validation evidence

- Targeted tests passed in Inspector verification.
- Dev gates passed: `ruff format --check`, `ruff check`, `mypy src`, and full
  pytest (`136 passed`) in Builder/Inspector verification.
- Package build passed in Builder/Inspector verification.
- Source and packaged diagnostics smoke passed in Builder/Inspector
  verification.

## Recommendations

- Run the compact manual validation checklist with a hand in front of the laptop
  webcam and record only the requested fields.
- Tune gesture thresholds from observed physical behavior if any action feels
  unreliable.
- Keep packaged executable signing and multi-monitor DPI validation as future
  release-hardening tasks.
