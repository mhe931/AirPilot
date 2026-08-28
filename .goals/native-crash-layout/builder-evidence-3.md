# Stress Evidence — Iteration 3

## Quality Gate

| Gate | Result |
|------|--------|
| `ruff format --check` | ✅ 80 files clean |
| `ruff check` | ✅ All checks passed |
| `mypy src` | ✅ No issues (17 source files) |
| `pytest` | ✅ **578 passed, 5 skipped** (+195 vs iteration 2) |

---

## 15-Minute Continuous Run

Command:
```
uv run --extra dev python scripts\camera_mediapipe_stress.py \
    --mode continuous --camera 0 --seconds 900 \
    --log-file .goals\native-crash-layout\stress-continuous-15min.log
```

Result (see `stress-continuous-15min.log`):
```
elapsed_s       : 900.46
frames_processed: 8975
frames_skipped  : 0
track_errors    : 0
invalid_frames  : 0
camera_opens    : 1
camera_closes   : 1
tracker_creates : 1
tracker_closes  : 1
crashes         : 0
```

**8975 frames / 900s / ~10.0 fps avg, 0 crashes, 0 errors.**

---

## UI Lifecycle Stress Gate

Created: `scripts/ui_lifecycle_stress.py`

Features:
- `faulthandler.enable(file=sys.stderr)` at module import
- Thread-aware logging (`[MAIN]`/`[T<tid>]` prefix)
- 30 cycles per suite (configurable via `--cycles`)
- Suites covered:
  - HelpWindow open/close/toggle (fake backend, no Tk required)
  - `_TkSharedRoot` acquire/release via real Tk
  - `SettingsWindow` open/close via real Tk
  - `_handle_keypress` all paths (q, p, h, s, a, Esc, unknowns)
  - `_dispatch_ui_action` arm/help/settings
  - `GestureEngine` pause/resume cycles
  - `MouseSafetyGate` arm/disarm cycles
  - `shortcut_mode` baseline (no-hand frame)
- Interactive/physical blocker documentation

Command:
```
uv run --extra dev python scripts\ui_lifecycle_stress.py \
    --cycles 30 \
    --log-file .goals\native-crash-layout\stress-ui-lifecycle.log
```

Result (see `stress-ui-lifecycle.log`):
```
cycles_per_suite    : 30
elapsed_s           : 35.91
help_window_cycles  : 30
settings_cycles     : 30
tk_root_cycles      : 30
keypress_cycles     : 30
pause_cycles        : 30
arm_disarm_cycles   : 60
shortcut_cycles     : 30
errors              : 0
```

**All 8 suites × 30 cycles = 240 total cycle checks, 0 errors.**

---

## Interactive / Physical Blockers

The following scenarios require a physical camera and interactive display:

| Scenario | Automated Substitute | Manual Procedure |
|----------|----------------------|------------------|
| Full-app camera + UI | 15-min camera stress | `airpilot --camera 0` |
| Help open/close (H key) | `_handle_keypress` h-key + HelpWindow toggle cycles in stress/tests | Press H while running; repeat 5× |
| Settings open/close (S key) | SettingsWindow 30-cycle stress | Press S while running; repeat 5× |
| Shortcut mode (two-hand) | shortcut_mode baseline test (no false positives) | Present two hands |
| Camera interruption | 30-cycle start/stop + reconnect retry tested in tracking tests | Unplug/replug USB camera |
| Title-bar close (X) | `ExitReason.MAIN_WINDOW_CLOSED` path covered in app.py | Click X on preview |
| Gesture arm (thumb-middle) | `_dispatch_ui_action("ui.arm")` 30-cycle stress | Two-hand thumb-middle hold |

---

## New Tests (195 additional passing tests)

File: `tests/test_app_lifecycle.py`

Coverage:
- `test_help_window_open_close_cycle[0..29]`: 30 parametrized HelpWindow cycles
- `test_help_window_toggle_returns_correct_state`: toggle state machine
- `test_handle_keypress_*`: all key paths (q/p/h/s/a/Esc/unknown), arm/disarm, pause, locked mode
- `test_handle_keypress_pause_resume_cycle[0..29]`: 30 pause/resume cycles
- `test_dispatch_*`: toggle_help, arm, already-armed, locked, open/close_settings, unknown
- `test_dispatch_help_toggle_cycle[0..29]`: 30 help toggle cycles
- `test_gesture_engine_pause_resume_cycle[0..29]`: 30 GestureEngine pause/resume cycles
- `test_safety_gate_arm_disarm_cycle[0..29]`: 30 arm/disarm cycles
- `test_safety_gate_disarm_releases_keys`: key release on disarm
- `test_shortcut_mode_false_for_no_hand_frame`: baseline no false positives
- `test_shortcut_mode_never_set_without_hand[0..29]`: 30 cycle regression
- 4 × `@pytest.mark.skip` manual blocker stubs documenting manual procedures

---

## Git State

Branch: `fix/native-crash-layout`
Files added: `scripts/ui_lifecycle_stress.py`, `tests/test_app_lifecycle.py`,
  `.goals/native-crash-layout/stress-continuous-15min.log`,
  `.goals/native-crash-layout/stress-ui-lifecycle.log`,
  `.goals/native-crash-layout/builder-evidence-3.md`
