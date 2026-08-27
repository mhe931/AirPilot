# Inspector Feedback — Iteration 1

**Verdict: PASS**

## Evidence Summary

### Quality Gates
- `ruff format --check`: ✅ 57 files already formatted
- `ruff check`: ✅ All checks passed
- `mypy src`: ✅ No issues in 15 source files
- `pytest`: ✅ All tests pass (zero failures, 1 skip — physical camera)

### Git / Branch State
- PR #11 (`feat/angle-scroll-settings-refine`) merged into `main` (commit `25d18c6`)
- Local branches: `main` only ✅
- Remote branches: `origin/HEAD → origin/main`, `origin/main` only ✅
- `main` is up to date with `origin/main` ✅

### Acceptance Criteria Verification

**Maximize disabled** (`src/airpilot/app.py:760–779`): `_disable_cv2_window_maximize`
removes `WS_MAXIMIZEBOX` via `SetWindowLongW`; called once after window appears
(lines 457–459). `test_disable_cv2_window_maximize_is_no_op_on_missing_window` confirms
no exception on missing window.

**Opacity**: `help_opacity` and `settings_opacity` fields exist on `TextStyleConfig`,
bounded `0.1–1.0`, applied at window open (lines 1035–1037). Three tests verify
defaults in bounds, round-trip persistence, and missing-field migration with defaults.

**Settings defaults populated**: `test_default_config_file_matches_dataclass_defaults`
in `test_config.py` asserts `config/defaults.json` matches live dataclass defaults.
Migration chain through v1–v11 tested exhaustively (19 test functions).

**Help rebuilt with real widgets**: `HelpWindow._tree` is a `ttk.Treeview` (line 1761),
populated from `_help_sections()` which queries the gesture/action registry directly.
`test_help_content_is_readable_and_structured`, `test_help_sections_include_*`, and
`test_help_emoji_present_in_formatted_rows` verify content completeness and emoji
presence. `test_help_content_wraps_vertically_without_horizontal_scroll` verifies no
horizontal overflow.

**Overlay layout / no clipping**: `test_overlay_layout_truncates_to_frame_width`
verifies all rendered lines have `x >= 0` and long text is truncated with `...` at
the given frame width. Help bounds tests (`test_help_initial_bounds_fit_monitor_work_area`,
`test_help_initial_bounds_fit_small_monitor_work_area`) confirm window fits inside
monitor work area.

**Sidebar / dashboard completeness**: `test_sidebar_lines_show_action_labels_for_gestures`
asserts move, freeze, click, scroll, arm, and help labels appear. Shortcut mode
expansion is tested in `test_sidebar_lines_expand_shortcut_mode_mappings`.

**Prior gesture behavior preserved**: `test_thumb_angle.py` (19 tests) covers default
90° target with ±10° tolerance. `test_gesture_bindings.py` (37 tests) covers
registry completeness, conflict detection, movement actions. `test_pose_clutch.py`
and `test_safety.py` verify safe arming and drag-release behavior.

**Typography**: `test_typography.py` (34 tests) covers defaults, round-trip, migration,
hex→BGR color conversion, and preview/reset consistency.

### Physical-Hand Validation (Not Automated — Not a Blocker)
The following require a physical hand in front of a webcam and cannot be
run in CI:
- Live opacity slider preview on screen
- Actual maximize button removal visible in title bar
- Dashboard live update after remapping with real gestures
- Camera fallback and corner failsafe behavior under real tracking conditions

These are documented as out-of-scope for automated verification per goal conventions.
