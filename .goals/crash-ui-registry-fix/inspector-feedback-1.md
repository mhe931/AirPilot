# Inspector Feedback — Iteration 1

**Verdict: PASS**

---

## Evidence Reviewed

| Area | Artefact | Result |
|------|----------|--------|
| Registry completeness | `src/airpilot/registry.py` | ✅ 5 sections, 26 entries, all required ids present |
| Duplicate IDs | `test_registry_has_no_duplicate_ids` | ✅ |
| Gesture-vs-key separation | `test_gesture_text_never_contains_emitted_shortcut_notation` | ✅ |
| `Shortcut Mode + h` truncation regression | `test_action_help_lines_switch_apps_not_truncated`, `test_format_help_row_no_truncation` | ✅ Fixed; `_format_help_row` comment explicitly names the bug |
| Help/Settings/Quit in registry | `test_registry_control_includes_help_settings_quit` | ✅ |
| Physical gesture entries for Help/Arm | `test_registry_control_includes_physical_gestures_for_help` | ✅ |
| Dashboard mode replacement | `test_default_mode_entries_exclude_shortcut_only_entries`, `test_shortcut_mode_entries_do_not_include_default_only_entries` | ✅ |
| Any-mode entries appear in both modes | `test_any_mode_entries_appear_in_both_modes` | ✅ |
| `keys_label` formatting | `test_registry_entry_keys_label_formatting` | ✅ Win+Tab produces correct label |
| Crash fix / lifecycle | `_TkSharedRoot` singleton, `run()` finally block ordering | ✅ (see below) |
| Cleanup ordering | `cv2.destroyAllWindows()` before camera/tracker close, Tk windows, `force_close()` | ✅ Correct order |
| All tests | `pytest tests/` | ✅ 285 passed, 1 skipped |
| Branch state | `git branch -a` | ✅ Only `main` local and remote |
| PR #12 | Merge commit `bd5c385` on `main` | ✅ Merged |

---

## Crash Root Cause Fix

The native crash was caused by multiple `tk.Tk()` instances and OpenCV's
`cv2.waitKey()` Windows message pump interleaving with Tk event handling.

**Fix verified:**
- `_TkSharedRoot` ref-counted singleton: one `tk.Tk()` per process, both
  `HelpWindow` and `SettingsWindow` share it via `acquire()`/`release()`.
- `force_close()` teardown in `run()` finally block comes **after**
  `cv2.destroyAllWindows()` — OpenCV message pump stopped before any Tk cleanup.
- `suppress(Exception)` wraps every cleanup step for idempotent teardown.

---

## MediaPipe Warning Handling

Tracking exceptions are caught per-frame; warnings are printed only for
the first 3 events then every 30th — prevents log flooding without masking
causality.

---

## Registry → Rendering Integration Note

`action_help_lines()` (actions.py) and `_sidebar_lines()` (app.py) each
maintain their own string literals rather than being **derived** from
`GESTURE_REGISTRY`. The registry is the authoritative **data catalog and
test baseline**, not a runtime generator. This is an acceptable trade-off
given the 20 registry-specific tests that cross-check correctness at key
integration points. Future additions to the registry **will not
automatically appear in Help or the sidebar** without corresponding
updates to those functions — the tests cover the existing entries but do
not exhaustively enforce full parity. This is a known limitation, not a
blocking defect for this iteration.

---

## Physical-Hand Validation

Gesture recognition, MediaPipe lifecycle, and mouse control require a
physical camera and hand. These paths cannot be validated in this
environment and are noted separately as unverified.

---

## Summary

All critical goals are met:
- Authoritative registry created with tests enforcing completeness and
  gesture-vs-key separation.
- `Shortcut Mode + h` truncation regression is fixed and regression-tested.
- Crash caused by multiple Tk roots eliminated; cleanup ordering is correct.
- Dashboard replaces entries cleanly by mode with no stale mixing.
- Help/Settings/Quit keyboard and gesture entries are present and correct.
- 285/286 tests pass; sole skip is pre-existing and unrelated.
- Only `main` exists locally and remotely; PR #12 merged.
