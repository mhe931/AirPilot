# Inspector Feedback — Iteration 1

**Verdict: FAIL**

## What Was Verified

| Check | Result |
|---|---|
| `uv run --extra dev ruff format --check .` | ✅ pass |
| `uv run --extra dev ruff check .` | ✅ pass |
| `uv run --extra dev mypy src` | ✅ pass (15 source files, no issues) |
| `uv run --extra dev python -m pytest` | ✅ 181 passed |
| CI (PR #11) | ✅ pass |
| PR open and unmerged | ✅ yes |

## What Was Implemented Correctly

- **Angle-based thumb activation** (`thumb_index_angle_deg` in `pose.py`):
  uses WRIST→MIDDLE_MCP as stable reference and THUMB_MCP→THUMB_TIP as thumb
  axis; scale-invariant and mirrored-hand invariant. Default target 90°,
  tolerance 10°.
- **Hysteresis in `_thumb_angle_in_range`**: widens the band when already active
  to prevent jitter; narrower for entry. ✅
- **Scroll dead zone** (`scroll_dead_zone=0.004`) and **natural direction toggle**
  (`scroll_natural_direction`): both wired in `gestures.py` with correct logic. ✅
- **Config migration v9→v10**: new fields have safe defaults; `_migrate_v9_config`
  is present and all 16 config tests pass. ✅
- **SettingsWindow** class (Tkinter): Mouse tab (angle target, tolerance,
  hysteresis, use-angle checkbox) and Scroll tab (sensitivity, dead zone, units,
  natural direction); Apply mutates live config; Reset restores dataclass
  defaults; Cancel/close discards. ✅
- **Help table header**: `_format_help_header` adds `Action│Gesture│Keys│State`
  column separators; compact scales applied. ✅
- **Compact angle field in status**: `θ<angle>° | <fps>fps` appended when
  angle-activation is enabled. ✅
- **Regression tests** (`test_thumb_angle.py`): 34 new tests covering 79/80/90/
  100/101° boundary, tolerance, hysteresis, left/right mirrors, rotation
  invariance, malformed landmarks, scroll dead zone, tracking-loss cancel,
  and GestureEngine angle-activation integration. ✅

## Unmet Acceptance Criteria

### 1. Data-driven configurable gesture bindings (criteria 9–11) — NOT IMPLEMENTED

The goal requires:
- A binding schema: hand selection (left/right/either), per-finger state
  (folded/extended/any), movement direction (none/left/right/up/down), trigger
  type (enter/hold-repeat/release), threshold, hold time, cooldown, sensitivity,
  action assignment, enabled/disabled.
- Independent left- and right-hand binding support with conflict detection and
  clear validation errors.
- A configurable example `thumb folded + index folded + hand moves right →
  PowerPoint next slide` shipped disabled by default.

None of these exist in `src/` or `config/defaults.json`. There is no
`GestureBinding` type, no gesture binding tab in SettingsWindow, no conflict
detection, and no PowerPoint example entry.

### 2. Missing regression test coverage (criterion 15 partial)

The goal requires tests for:
- gesture serialization / migration / matching / movement / conflicts / cooldown
  / one-shot / repeat / PowerPoint example

None of the 181 tests cover any of these topics.

### 3. Settings window — no gesture bindings tab or persistence validation tests

SettingsWindow covers mouse and scroll but not gesture bindings. The goal
requires gesture bindings to be configurable through the Settings window with
all the fields above.

### 4. Preview status compact panel (criterion 14) — partial

A compact angle indicator was added to the status text. However, the goal
requires replacing the "oversized/dense green header with a compact, readable,
high-contrast status panel that fits 640x480 and DPI-scaled Windows displays".
The `app.py` diff shows only minor text additions, not a redesigned overlay
panel. This item is partially addressed but not fully met.

## Issues Found in Implemented Code

**No blocking bugs found** in the implemented subset. The angle geometry,
hysteresis, scroll dead zone, config migration, and Settings UI are all
correctly implemented and tested.

## Required for PASS

1. Implement data-driven gesture binding schema and persistence
   (criteria 9–11): `GestureBinding` dataclass, config serialization/migration,
   matcher in GestureEngine, conflict detection, disabled PowerPoint example.
2. Add regression tests for gesture bindings (criterion 15).
3. Add gesture bindings tab to SettingsWindow.
4. Compact preview status panel (criterion 14) — fully redesign the OpenCV
   overlay header to be small/readable at 640×480 and high DPI.
