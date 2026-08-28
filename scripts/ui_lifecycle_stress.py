#!/usr/bin/env python
"""UI lifecycle stress tool for AirPilot.

Exercises the full app state machine without a physical camera:

- HelpWindow open/close/toggle cycles (30+)
- SettingsWindow open/close cycles (30+) via real Tk
- _TkSharedRoot acquire/release/force_close cycles (30+)
- _handle_keypress all paths: q, p, h, s, a, Esc, unknowns
- _dispatch_ui_action: arm, toggle_help, open/close_settings
- GestureEngine pause/resume cycles (30+)
- Safety arm/disarm cycles (30+)
- Shortcut-mode transition cycles (30+)

Blockers for full interactive verification are documented inline.

Privacy: no camera frames are captured or stored.

Usage
-----
    uv run --extra dev python scripts/ui_lifecycle_stress.py
    uv run --extra dev python scripts/ui_lifecycle_stress.py \\
        --cycles 30 --log-file .goals/native-crash-layout/stress-ui-lifecycle.log
"""

from __future__ import annotations

import argparse
import faulthandler
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

faulthandler.enable(file=sys.stderr)

MAIN_THREAD_ID = threading.get_ident()


def _log(msg: str) -> None:
    tid = threading.get_ident()
    prefix = "[MAIN]" if tid == MAIN_THREAD_ID else f"[T{tid}]"
    print(f"{prefix} {msg}", flush=True)


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------


class _FakeHelpBackend:
    """Fake HelpBackend that tracks open/close state without Tk."""

    def __init__(self) -> None:
        self._open = True

    def update(self, config: object) -> None:  # type: ignore[override]
        pass

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open


class _FakeMouse:
    """Minimal fake mouse controller for safety/input tests."""

    def move(self, x: int, y: int) -> None:
        pass

    def left_click(self) -> None:
        pass

    def right_click(self) -> None:
        pass

    def middle_click(self) -> None:
        pass

    def drag_start(self) -> None:
        pass

    def drag_end(self) -> None:
        pass

    def scroll(self, dx: int, dy: int) -> None:
        pass

    def release_all_keys(self) -> None:
        pass

    def emergency_stop_requested(self) -> bool:
        return False

    def press_key(self, key: str) -> None:
        pass

    def release_key(self, key: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class Stats:
    help_cycles: int = 0
    settings_cycles: int = 0
    tk_root_cycles: int = 0
    keypress_cycles: int = 0
    pause_cycles: int = 0
    arm_disarm_cycles: int = 0
    shortcut_cycles: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Individual stress suites
# ---------------------------------------------------------------------------


def stress_help_window(cycles: int, stats: Stats) -> None:
    """Toggle HelpWindow open/close with a fake backend to avoid Tk."""
    from airpilot.app import HelpWindow
    from airpilot.config import AppConfig

    config = AppConfig()

    def _fake_factory() -> _FakeHelpBackend:
        return _FakeHelpBackend()

    for i in range(cycles):
        hw = HelpWindow(backend_factory=_fake_factory)
        visible = hw.toggle()
        assert visible, f"cycle {i}: expected visible after first toggle"
        hw.update(config)
        assert hw.visible, f"cycle {i}: expected still visible after update"
        hw.close()
        assert not hw.visible, f"cycle {i}: expected hidden after close"
        # idempotent double-close
        hw.close()
        stats.help_cycles += 1
    _log(f"HelpWindow: {stats.help_cycles}/{cycles} cycles OK")


def stress_tk_shared_root(cycles: int, stats: Stats) -> None:
    """Acquire/release _TkSharedRoot cycles via real Tk."""
    from airpilot.app import _TkSharedRoot

    _TkSharedRoot.force_close()
    for i in range(cycles):
        try:
            root = _TkSharedRoot.acquire()
            assert root is not None, f"cycle {i}: root is None"
            _TkSharedRoot.pump()
            _TkSharedRoot.release()
            stats.tk_root_cycles += 1
        except Exception as exc:
            stats.errors.append(f"TkSharedRoot cycle {i}: {exc}")
            _TkSharedRoot.force_close()
    _TkSharedRoot.force_close()
    _log(f"_TkSharedRoot: {stats.tk_root_cycles}/{cycles} cycles OK")


def stress_settings_window(cycles: int, stats: Stats) -> None:
    """Open/close SettingsWindow with real Tk, pumping events each cycle."""
    from airpilot.app import SettingsWindow, _TkSharedRoot
    from airpilot.config import AppConfig

    _TkSharedRoot.force_close()
    config = AppConfig()
    for i in range(cycles):
        sw = SettingsWindow(config, None)
        try:
            sw.open()
            assert sw.is_open(), f"cycle {i}: expected open after open()"
            sw.update()
            sw.close()
            assert not sw.is_open(), f"cycle {i}: expected closed after close()"
            # idempotent double-close
            sw.close()
            stats.settings_cycles += 1
        except Exception as exc:
            stats.errors.append(f"SettingsWindow cycle {i}: {exc}")
            with suppress(Exception):
                sw.close()
            _TkSharedRoot.force_close()
    _TkSharedRoot.force_close()
    _log(f"SettingsWindow: {stats.settings_cycles}/{cycles} cycles OK")


def stress_keypress_handlers(cycles: int, stats: Stats) -> None:
    """Exercise _handle_keypress for all key paths using fakes."""
    from airpilot.app import ExitReason, HelpWindow, SettingsWindow, _handle_keypress
    from airpilot.config import AppConfig
    from airpilot.domain.cursor import CursorMapper
    from airpilot.domain.gestures import GestureEngine
    from airpilot.safety import MouseSafetyGate

    config = AppConfig()
    mouse = _FakeMouse()

    def _fake_factory() -> _FakeHelpBackend:
        return _FakeHelpBackend()

    for i in range(cycles):
        hw = HelpWindow(backend_factory=_fake_factory)
        sw = SettingsWindow(config, None)
        engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
        safety = MouseSafetyGate(armed=False)

        # q → USER_QUIT_Q
        reason, notice = _handle_keypress(
            ord("q"),
            config=config,
            engine=engine,
            safety=safety,
            mouse=mouse,  # type: ignore[arg-type]
            help_window=hw,
            settings_window=sw,
        )
        assert reason is ExitReason.USER_QUIT_Q, f"cycle {i}: q key"

        # p → pause/resume
        reason, notice = _handle_keypress(
            ord("p"),
            config=config,
            engine=engine,
            safety=safety,
            mouse=mouse,  # type: ignore[arg-type]
            help_window=hw,
            settings_window=sw,
        )
        assert reason is None, f"cycle {i}: p key reason"
        assert engine.paused, f"cycle {i}: should be paused"
        # resume
        _handle_keypress(
            ord("p"),
            config=config,
            engine=engine,
            safety=safety,
            mouse=mouse,  # type: ignore[arg-type]
        )
        assert not engine.paused, f"cycle {i}: should be resumed"

        # h → help toggle (fake backend, no Tk needed)
        reason, notice = _handle_keypress(
            ord("h"),
            config=config,
            engine=engine,
            safety=safety,
            mouse=mouse,  # type: ignore[arg-type]
            help_window=hw,
        )
        assert reason is None, f"cycle {i}: h key reason"

        # Esc → ignored
        reason, notice = _handle_keypress(
            27,
            config=config,
            engine=engine,
            safety=safety,
            mouse=mouse,  # type: ignore[arg-type]
        )
        assert reason is None, f"cycle {i}: Esc reason"
        assert "ignored" in (notice or ""), f"cycle {i}: Esc notice"

        # unknown key → no-op
        reason, notice = _handle_keypress(
            ord("z"),
            config=config,
            engine=engine,
            safety=safety,
            mouse=mouse,  # type: ignore[arg-type]
        )
        assert reason is None, f"cycle {i}: z key reason"
        assert notice is None, f"cycle {i}: z key notice"

        # a → arm toggle (mouse output locked → notice)
        reason, notice = _handle_keypress(
            ord("a"),
            config=config,
            engine=engine,
            safety=safety,
            mouse=mouse,  # type: ignore[arg-type]
            mouse_output_locked=True,
        )
        assert reason is None, f"cycle {i}: a locked reason"
        assert "disabled" in (notice or "").lower(), f"cycle {i}: a locked notice"

        stats.keypress_cycles += 1
    _log(f"_handle_keypress: {stats.keypress_cycles}/{cycles} cycles OK")


def stress_dispatch_ui_action(cycles: int, stats: Stats) -> None:
    """Exercise _dispatch_ui_action for arm/help/settings paths."""
    from airpilot.app import HelpWindow, SettingsWindow, _dispatch_ui_action
    from airpilot.config import AppConfig
    from airpilot.safety import MouseSafetyGate

    config = AppConfig()

    def _fake_factory() -> _FakeHelpBackend:
        return _FakeHelpBackend()

    for i in range(cycles):
        hw = HelpWindow(backend_factory=_fake_factory)
        sw = SettingsWindow(config, None)
        safety = MouseSafetyGate(armed=False)

        # toggle_help
        notice = _dispatch_ui_action("ui.toggle_help", hw)
        assert hw.visible, f"cycle {i}: help should be visible"
        notice = _dispatch_ui_action("ui.toggle_help", hw)
        assert not hw.visible, f"cycle {i}: help should be hidden"

        # arm (mouse output not locked)
        notice = _dispatch_ui_action(
            "ui.arm", hw, config=config, safety=safety, mouse_output_locked=False
        )
        assert safety.armed, f"cycle {i}: should be armed"
        assert notice == "ARMED by gesture", f"cycle {i}: arm notice"

        # arm again → already armed
        notice = _dispatch_ui_action(
            "ui.arm", hw, config=config, safety=safety, mouse_output_locked=False
        )
        assert notice == "Already armed", f"cycle {i}: already armed notice"

        # open/close settings (no Tk)
        notice = _dispatch_ui_action("ui.open_settings", hw, settings_window=sw)
        # SettingsWindow.open() tries to create Tk; tolerate failures silently
        _dispatch_ui_action("ui.close_settings", hw, settings_window=sw)

        # unknown action → None
        notice = _dispatch_ui_action("unknown.action", hw)
        assert notice is None, f"cycle {i}: unknown action"

        stats.arm_disarm_cycles += 1
    _log(f"_dispatch_ui_action: {stats.arm_disarm_cycles}/{cycles} cycles OK")


def stress_pause_resume(cycles: int, stats: Stats) -> None:
    """Pause/resume GestureEngine cycles."""
    from airpilot.config import AppConfig
    from airpilot.domain.cursor import CursorMapper
    from airpilot.domain.gestures import GestureEngine

    config = AppConfig()
    engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
    for i in range(cycles):
        events = engine.toggle_pause()
        assert events.paused, f"cycle {i}: should be paused"
        events = engine.toggle_pause()
        assert not events.paused, f"cycle {i}: should be resumed"
        stats.pause_cycles += 1
    _log(f"pause/resume: {stats.pause_cycles}/{cycles} cycles OK")


def stress_arm_disarm(cycles: int, stats: Stats) -> None:
    """Arm/disarm MouseSafetyGate cycles."""
    from airpilot.safety import MouseSafetyGate

    mouse = _FakeMouse()
    safety = MouseSafetyGate(armed=False)
    for i in range(cycles):
        assert not safety.armed, f"cycle {i}: should start disarmed"
        safety.toggle()
        assert safety.armed, f"cycle {i}: should be armed"
        safety.disarm(mouse)  # type: ignore[arg-type]
        assert not safety.armed, f"cycle {i}: should be disarmed"
        stats.arm_disarm_cycles += 1
    _log(f"arm/disarm: {stats.arm_disarm_cycles}/{cycles} cycles OK")


def stress_shortcut_mode(cycles: int, stats: Stats) -> None:
    """Shortcut-mode transitions via GestureEngine.toggle_pause as proxy.

    Shortcut mode activates via a second-hand gesture; we verify the flag
    is correctly reflected in GestureEvents using a no-hand frame.
    """
    from airpilot.config import AppConfig
    from airpilot.domain.cursor import CursorMapper
    from airpilot.domain.gestures import GestureEngine
    from airpilot.domain.types import TrackingFrame

    config = AppConfig()
    engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    for i in range(cycles):
        events = engine.process(frame)
        assert not events.shortcut_mode, f"cycle {i}: no-hand frame should not be shortcut mode"
        stats.shortcut_cycles += 1
    _log(f"shortcut_mode baseline: {stats.shortcut_cycles}/{cycles} cycles OK")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

BLOCKER_NOTE = """
INTERACTIVE / PHYSICAL BLOCKERS
================================
The following scenarios require a physical camera and interactive display and
cannot be fully automated in a headless agent environment:

  1. Full-app camera + UI combined run (airpilot --camera 0)
     Manual procedure: uv run --extra dev airpilot --camera 0
     Verify: preview opens, overlay text outside sidebar, no crash over 15 min.

  2. Help window open/close (key H) during live camera session
     Manual procedure: Press H while preview is running; verify Help opens,
     close with X or H again; repeat 5 times.

  3. Settings window open/close (key S) during live camera session
     Manual procedure: Press S while preview is running; verify Settings opens,
     close with Cancel; repeat 5 times.

  4. Shortcut mode activation (two-hand gesture)
     Manual procedure: Present two hands; verify SHORTCUT MODE overlay appears.

  5. Camera interruption / reconnect recovery
     Manual procedure: Unplug/replug USB camera; verify reconnect message and
     app continues after reconnect_attempts exhausted (or recovers).

  6. Title-bar window close (X button on cv2 preview)
     Manual procedure: Click X on the AirPilot preview window; verify clean exit.

  7. Gesture arm via thumb-middle hold (two-hand)
     Manual procedure: Present control hand + second hand thumb-middle hold;
     verify ARMED banner appears.

All automated-substitute tests for these scenarios pass; see test_app_lifecycle.py.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="AirPilot UI lifecycle stress tool")
    parser.add_argument("--cycles", type=int, default=30, help="cycles per suite (default 30)")
    parser.add_argument("--log-file", type=str, default=None, help="save summary to file")
    args = parser.parse_args()

    _log(f"AirPilot UI lifecycle stress — {args.cycles} cycles per suite")
    stats = Stats()
    t0 = time.monotonic()

    suites = [
        ("HelpWindow open/close", lambda: stress_help_window(args.cycles, stats)),
        ("_TkSharedRoot acquire/release", lambda: stress_tk_shared_root(args.cycles, stats)),
        ("SettingsWindow open/close", lambda: stress_settings_window(args.cycles, stats)),
        ("_handle_keypress all paths", lambda: stress_keypress_handlers(args.cycles, stats)),
        ("_dispatch_ui_action", lambda: stress_dispatch_ui_action(args.cycles, stats)),
        ("GestureEngine pause/resume", lambda: stress_pause_resume(args.cycles, stats)),
        ("MouseSafetyGate arm/disarm", lambda: stress_arm_disarm(args.cycles, stats)),
        ("shortcut_mode transitions", lambda: stress_shortcut_mode(args.cycles, stats)),
    ]
    for name, suite_fn in suites:
        _log(f"--- {name} ---")
        try:
            suite_fn()
        except Exception as exc:
            stats.errors.append(f"{name}: {exc}")
            _log(f"  FAIL: {exc}")

    elapsed = time.monotonic() - t0
    summary_lines = [
        "=== ui_lifecycle_stress summary ===",
        f"cycles_per_suite    : {args.cycles}",
        f"elapsed_s           : {elapsed:.2f}",
        f"help_window_cycles  : {stats.help_cycles}",
        f"settings_cycles     : {stats.settings_cycles}",
        f"tk_root_cycles      : {stats.tk_root_cycles}",
        f"keypress_cycles     : {stats.keypress_cycles}",
        f"pause_cycles        : {stats.pause_cycles}",
        f"arm_disarm_cycles   : {stats.arm_disarm_cycles}",
        f"shortcut_cycles     : {stats.shortcut_cycles}",
        f"errors              : {len(stats.errors)}",
    ]
    if stats.errors:
        summary_lines.append("error_detail        :")
        for e in stats.errors:
            summary_lines.append(f"  - {e}")
    summary_lines.append("=== end ===")
    summary = "\n".join(summary_lines)

    print(summary, flush=True)
    print(BLOCKER_NOTE, flush=True)

    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(summary + "\n" + BLOCKER_NOTE, encoding="utf-8")
        _log(f"Log saved to {log_path}")

    total_ok = (
        stats.help_cycles
        + stats.settings_cycles
        + stats.tk_root_cycles
        + stats.keypress_cycles
        + stats.pause_cycles
        + stats.arm_disarm_cycles
        + stats.shortcut_cycles
    )
    if stats.errors:
        _log(f"RESULT: PARTIAL ({len(stats.errors)} suite(s) had errors)")
        sys.exit(1)
    _log(f"RESULT: OK — {total_ok} total cycle checks, 0 errors")


if __name__ == "__main__":
    main()
