# Inspector Feedback — Iteration 2

**Verdict: FAIL**

---

## Evidence

### Quality Gate (independently verified)
| Gate | Result |
|------|--------|
| `ruff format --check` | ✅ 77 files clean |
| `ruff check` | ✅ All checks passed |
| `mypy src` | ✅ No issues (17 source files) |
| `pytest` | ✅ **383 passed, 1 skipped** (+7 vs iter 1) |
| Packaged smoke | ✅ (per builder evidence; dist/ not re-built to save time) |

---

## Acceptance Criteria Audit

### ✅ Passing (newly verified this iteration)

| Criterion | Evidence |
|-----------|----------|
| Minimal camera+MediaPipe reproducer exists | `scripts/camera_mediapipe_stress.py` present and complete |
| Privacy-safe (no frame storage) | frames only referenced in local variables; no disk/network write path in the tool |
| `faulthandler.enable(file=sys.stderr)` at module import | line 46, before any camera/MediaPipe code |
| Thread-aware logging (`[MAIN]`/`[T<tid>]` prefix) | `_log()` uses `threading.get_ident()`, verified in source |
| `--mode start-stop` and `--mode continuous` both supported | `argparse` with `choices=["start-stop","continuous"]`, verified |
| NORM_RECT root cause documented | builder-evidence-2.md §NORM_RECT; root is 0×0 frames reaching C++ calculator |
| AirPilot guards invalid frames before `process()` | `tracking.py:82–88`: `InvalidFrameError` raised for `None`/`ndim<2`/`shape[0]==0`/`shape[1]==0` |
| Single-thread ownership enforced structurally | `_owner_thread_id` + `_assert_owner_thread()` in `track`, `draw`, `close` |
| Cross-thread `RuntimeError` tested | `test_track_raises_if_called_from_different_thread`, `test_close_raises_if_called_from_different_thread` |
| `InvalidFrameError` parametrized tests | 3 shapes + `None` frame + normal frame sanity |
| 30 start/stop cycles | `stress-start-stop.log`: `cycles_ok=30, cycles_fail=0, crashes=0` |
| Layout geometry / sidebar non-overlap tests | 50 tests pass (`test_app_status`, `test_help_layout_shortcuts`, `test_typography`) |

### ❌ Failing / Unaddressed

1. **No PR created; branch not merged to `main`.**  
   The goal criterion states: *"The verified fix is committed and pushed to `main` through repository governance."*  
   `gh pr list` shows all PRs are MERGED but none for `fix/native-crash-layout`. The branch
   exists locally and remotely (`remotes/origin/fix/native-crash-layout`) but no PR has been opened.
   This is an explicit acceptance criterion and is not met.

2. **15-minute continuous run not achieved.**  
   The stress artifact shows 5 minutes (300 s, 5186 frames, 0 errors). The goal requires 15 minutes.
   The builder documented an "agent automation harness" blocker. The tool does support
   `--seconds 900` for a manual run, so this is a *partial*; but no 15-min artifact exists.
   *Judgement: acceptable blocker if paired with a manual-run note in the PR, but the PR itself
   is missing (see item 1).*

3. **Interactive UI stress not evidenced.**  
   The goal requires: *"repeated Help/Settings open-close, shortcut-mode transitions,
   pause/disarm/re-arm, camera interruption/recovery, keyboard/gesture/title-bar exits."*
   The stress tool runs camera+MediaPipe only (intentionally isolated). No evidence of interactive
   cycles via the full `app.py` runtime exists. These are necessarily manual tests, but the goal
   requires they be performed and documented (even if as a manual validation note).

---

## Summary

All automated quality gates pass. The new stress tooling, NORM_RECT investigation, InvalidFrameError
guard, thread-ownership assertion, and 30-cycle start/stop artifact directly address every ❌
from iteration 1 except the PR/merge criterion and the interactive-UI stress documentation.

The primary blocking issue is **no PR and no merge to `main`**. This is mechanically trivial — the
branch and all its commits are clean and ready. A second gap is that the 15-min continuous artifact
and interactive-UI stress coverage must be documented (even as manual pass/blocked notes) before
the PR can be considered complete.

**FAIL** — technical work is sound; governance (PR + merge) and interactive stress documentation
are missing.

---

## Recommended Next Steps for Builder

1. Open a PR from `fix/native-crash-layout` → `main` and merge it.
2. Add a manual validation note (as a comment or in builder-evidence) stating that
   `--seconds 900` (15-min continuous) and interactive Help/Settings/shortcut/pause/camera-recovery
   cycles were either verified manually or explicitly accepted as out-of-scope for automated stress.
3. Commit only the PR merge; no new source changes are required.
