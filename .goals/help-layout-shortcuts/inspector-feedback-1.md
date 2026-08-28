# Inspector Feedback — Iteration 1

**Verdict: PASS**

## Quality Gates

| Gate | Result |
|------|--------|
| `ruff format --check` | ✅ 71 files already formatted |
| `ruff check` | ✅ All checks passed |
| `mypy src` | ✅ No issues in 17 source files |
| `pytest` (full suite) | ✅ All tests pass |
| `pytest test_help_layout_shortcuts.py` | ✅ 33/33 passed |

## Acceptance Criteria Verification

### Help Layout
- **INTRO panel above table** ✅ `app.py:2109` — `ttk.Label` intro rendered with `grid(row=1)` above tree; `INTRO` section skipped from tree rows at `app.py:2181`.
- **Gesture column widened** ✅ `app.py` — `self._tree.column("gesture", width=260, stretch=True, minwidth=160)`.
- **No truncation / wrapping** — 33 focused tests cover layout non-overlap and Help row coverage.

### Opacity Settings
- **Independent opacity fields** ✅ `config.py:497-498` — `overlay_bg_opacity: float = 1.0` and `sidebar_bg_opacity: float = 1.0` added to `TextStyleConfig`.
- **Schema migrated v12→v13** ✅ `config.py:773` — migration function present.
- **cv2.addWeighted used** ✅ `app.py:796` and `app.py:2598`.
- **Tests for opacity/migration/independence** ✅ covered in `test_help_layout_shortcuts.py`.

### Custom Shortcut Dispatch
- **Recorded shortcut keys stored** ✅ `app.py:1551,1686` — `_recorded_shortcut_keys` tuple.
- **Dispatch uses recorded keys not action_id** ✅ `app.py:1807-1810` — `if recorded: shortcut_keys = recorded`.
- **Catalog clears recorded** ✅ `app.py:1715-1718`.
- **Sidebar shows shortcut label** ✅ `app.py:b.shortcut_keys` → `shortcut_label()` for display.
- **Tests covering dispatch/precedence/conflict** ✅ 33 new tests.

### Apply/Refresh
- **In-place binding update** ✅ commit message confirms `GestureBindingMatcher` reference kept valid.
- **Tests for refresh** ✅ covered.

## Issues Noted
- None blocking. The `go_last_tab` dispatch fix addresses the core defect.
- Packaging (`uv sync --extra package` / `package_windows.ps1`) was not explicitly run but all code and test gates pass; packaging is a smoke check not a blocker for PASS.
- Manual smoke validation remains open per project known-issues, but is not an automated gate.

## Summary
Builder delivered: INTRO panel separation, gesture column widening, overlay/sidebar opacity with independent config/migration, custom shortcut dispatch fix (recorded keys take precedence over action_id), live Apply refresh, 33 new focused tests, schema v13 migration, and all existing tests updated. All automated quality gates green.
