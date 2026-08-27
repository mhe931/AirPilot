# Inspector Feedback 1

Verdict: FAIL

## Issue: Clutch release can still jump after hand moves while frozen

**File:** `src/airpilot/domain/gestures.py`

**Severity:** Medium

**Problem:** `_release_clutch()` restores `CursorMapper.current` to the original
frozen clutch anchor. If the user moves their hand while thumb-clutched, the
release frame stays frozen, but the next thumb-open frame maps toward the hand's
new absolute position, causing a large cursor jump instead of a smooth resume.

**Evidence:** A direct probe with default cursor config produced
`resume_jump_px 480.0` after moving the hand by `offset=(0.30, 0.0)` while
clutched. Format, lint, mypy, and full pytest passed, so this is an uncovered
acceptance failure rather than a test failure.

**Suggested fix:** Rebase/recalibrate the post-clutch pointer reference so the
current hand anchor resumes from the frozen cursor target, or otherwise ramp
movement after clutch release to prevent a large first-frame jump.
