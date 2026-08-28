# Inspector Feedback — Iteration 1

**Verdict: FAIL**

---

## Evidence

### Quality Gate
- `376 passed, 1 skipped` — all existing tests pass plus 9 new tests
- `ruff format --check`, `ruff check`, `mypy src` — all clean
- Branch: `fix/native-crash-layout` (not yet merged to `main`)

---

## Acceptance Criteria Audit

### ✅ Passing

| Criterion | Evidence |
|-----------|----------|
| Lines ~394/542 inspected and documented | `app.py` commit message documents both call sites; `faulthandler.enable()` added at `main()` entry |
| `faulthandler` enabled | `faulthandler.enable(file=sys.stderr)` at line 342 |
| Tk events drained before `cv2.waitKey` | `help_window.update(config)` + `settings_window.update()` called at lines 585–586, before `cv2.imshow`/`cv2.waitKey` at lines 587/593 |
| Explicit shutdown order | `finally` block at line 660: `cv2.destroyAllWindows` → `camera.close` → `tracker.close` → `safety.disarm` → `help_window.close` → `settings_window.close` → `_TkSharedRoot.force_close` |
| Shutdown is idempotent | All steps wrapped in `with suppress(Exception)` |
| `_TkSharedRoot` singleton manages shared root | Ref-counted acquire/release/force_close present |
| MediaPipe pipeline reset on 5 consecutive exceptions | `_tracker_error_streak` counter + reset at lines 486–500 |
| NORM_RECT warning investigated (not suppressed) | Comment at line 426 identifies it as a pipeline-corruption signal; tracker recreation is the structural response |
| Layout fix: sidebar reserves space | `_compute_sidebar_width` mirrors `_draw_sidebar` geometry; `_layout_overlay` uses `x_offset = sidebar_width + 10` |
| Geometry regression tests present | `test_overlay_text_never_behind_sidebar_at_various_widths` parametrically checks 16 combinations; `test_overlay_layout_x_offset_clears_sidebar` asserts `x >= sidebar_width` |
| `_TkSharedRoot` lifecycle stress test | `test_tk_shared_root_acquire_release_cycles` runs 30 cycles |
| Format / lint / types / full tests pass | Verified independently above |

### ❌ Failing / Unaddressed

1. **Crash reproduction / 15-minute continuous-run stress gate not performed.**
   The goal explicitly requires: "30 repeated start/stop cycles, 15-minute continuous camera/inference run, repeated Help/Settings open-close, shortcut-mode transitions, pause/disarm/re-arm, camera interruption/recovery, keyboard/gesture/title-bar exits, and packaged executable smoke/stress tests."  
   No stress artifact, log, or documented equivalent substitution exists.  
   The 30-cycle `test_tk_shared_root_acquire_release_cycles` tests the *Tk root* only — it does not start the camera, run MediaPipe, or cover GIL interaction under load.

2. **No minimal camera+MediaPipe reproducer.**  
   The goal requires "A minimal camera+MediaPipe reproducer exists and can isolate application code from dependency/native-runtime failure." No such script/test was added.

3. **Thread/inference audit is asserted but not demonstrated.**  
   The criteria state "One thread exclusively owns camera and MediaPipe objects" and "Tracker inference is serialized; `process()` is never concurrent." The current architecture is single-threaded (no worker thread, no `threading.Thread`), so these hold structurally — but the audit is not documented or asserted in test form.

4. **NORM_RECT root cause investigation is shallow.**  
   The fix treats the NORM_RECT warnings as a symptom of pipeline corruption and resets the tracker. This may be sufficient, but the goal says "investigated and corrected if caused by AirPilot" — no evidence was provided that the *cause* (e.g., passing empty/zero-dimension images to MediaPipe) was checked against the `tracker.track()` call sites.

5. **Packaged smoke test not performed.**  
   `scripts/package_windows.ps1` execution and packaged-executable smoke-run under the crash scenario is required by the goal but not documented.

6. **No PR / governance evidence yet.**  
   The branch `fix/native-crash-layout` exists but has not been merged to `main`. This is expected for an in-progress iteration, but the goal requires merge before completion.

---

## Summary

The GIL-crash fix (Tk pre-pump before `waitKey`) is architecturally sound and correctly identified. The shutdown-ordering, faulthandler, tracker reset, and layout geometry fixes are all present and tested. The quality gate is clean.

However, the required **stress verification gates** (15-min run, 30 start/stop cycles with camera hardware, Help/Settings cycles, packaged smoke test) have not been performed and no credible documented substitute exists. These are explicit acceptance criteria and cannot be waived.

**FAIL** — structural fixes are correct; stress gates and reproducer are missing.
