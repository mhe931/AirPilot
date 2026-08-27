# Goal Summary: Angle Scroll Settings Refine

## What was achieved

- Thumb activation now uses configurable angle activation with default
  `90` degrees target and `10` degrees tolerance.
- Pointer clutch/resume behavior from PR #10 was preserved while adding
  angle-based activation and status visibility.
- Scroll behavior was refined with continuous displacement controls,
  configurable sensitivity/dead zone/smoothing/direction, and clean release.
- Mouse and gesture settings were added to a Windows-style Settings window.
- A data-driven gesture-binding model was added with persisted defaults,
  matching, cooldowns, conflict checks, and a disabled PowerPoint next-slide
  example for `thumb folded + index folded + move hand right`.
- Help keeps the native responsive window and displays action data in readable
  table-style rows.
- Preview status was made compact and high-contrast with details moved below the
  main banner.
- Packaging and packaged smoke checks were reported complete by Builder, and
  Inspector verified quality gates and PR CI.

## Acceptance criteria mapping

- Thumb angle boundaries, tolerance changes, hysteresis, left/right hands,
  rotation, and malformed landmarks: implemented and tested.
- Thumb folded clutch and no-jump resume: preserved from PR #10 and covered by
  existing tests.
- Continuous scroll configuration and release behavior: implemented and tested.
- Settings persistence/reset/validation: implemented and tested.
- Data-driven bindings, conflict detection, cooldowns, one-shot/repeat behavior,
  and disabled PowerPoint example: implemented and tested.
- Help table readability and preview compactness: implemented and inspected by
  the Inspector.
- PR opened, CI passed, and merge is blocked pending physical validation.

## Iteration history

1. **Iteration 1 — FAIL.** Angle activation, scroll tuning, early Settings UI,
   Help table header, and tests passed, but data-driven gesture bindings,
   binding Settings UI, binding tests, and the full preview-panel redesign were
   missing.
2. **Iteration 2 — PASS.** Builder added gesture binding schema/matcher,
   Settings binding tab, persistence/migration tests, compact preview panel, and
   disabled PowerPoint example. Inspector verified 217 passing tests, 1 skipped
   physical/synthetic PowerPoint fixture, clean lint/type checks, and successful
   CI.

## Inspector notes and residual risks

- Inspector found no blocking issues in iteration 2.
- Physical validation is still required before merge because camera/hand feel,
  touch-style scroll feel, Settings usability, and the real PowerPoint-style
  binding cannot be fully proven by synthetic tests.

## Recommendations

- Physically validate PR #11 with the exact checklist before merging.
- If the custom binding feels unreliable with real landmarks, collect only
  aggregate angle/binding status observations; do not save camera frames.
- After physical confirmation, merge PR #11, sync clean `main`, delete the
  feature branch, and update project status docs with the validation result.

## Suggested squash command

```bash
git reset --soft dd140e42584071f0eff5f9ddab1c619a160793f6
git commit -m 'feat(gestures): refine activation scroll and settings

AirPilot now activates pointer movement through configurable thumb-angle
control, provides touch-style scrolling, exposes mouse and gesture settings, and
shows clearer Help and preview UI for physical Windows testing.

Assisted-by: Claude:Sonnet-4.6'
```
