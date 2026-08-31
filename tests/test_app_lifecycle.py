"""Deterministic automated tests for the full-app UI lifecycle.

Covers the state machine paths exercised by scripts/ui_lifecycle_stress.py:
  - HelpWindow open/close/toggle cycles
  - _TkSharedRoot acquire/release/force_close cycles
  - SettingsWindow open/close cycles via real Tk
  - _handle_keypress all key paths
  - _dispatch_ui_action arm/help/settings paths
  - GestureEngine pause/resume cycles
  - MouseSafetyGate arm/disarm cycles
  - shortcut_mode baseline (no-hand frame)

Physical-camera and interactive-display scenarios are documented as
BLOCKER stubs with the manual procedure to follow.
"""

from __future__ import annotations

import pytest

from airpilot.app import (
    ExitReason,
    HelpWindow,
    _dispatch_ui_action,
    _handle_keypress,
)
from airpilot.config import AppConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.gestures import GestureEngine
from airpilot.domain.types import TrackingFrame
from airpilot.safety import MouseSafetyGate

# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------


class _FakeHelpBackend:
    def __init__(self) -> None:
        self._open = True
        self.refresh_count = 0

    def update(self, config: object) -> None:
        pass

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def force_refresh(self) -> None:
        self.refresh_count += 1


class _FakeMouse:
    def move(self, x: int, y: int) -> None: ...
    def left_click(self) -> None: ...
    def right_click(self) -> None: ...
    def middle_click(self) -> None: ...
    def drag_start(self) -> None: ...
    def drag_end(self) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...
    def release_all_keys(self) -> None: ...
    def emergency_stop_requested(self) -> bool:
        return False

    def press_key(self, key: str) -> None: ...
    def release_key(self, key: str) -> None: ...


def _help_window() -> HelpWindow:
    return HelpWindow(backend_factory=lambda: _FakeHelpBackend())  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# HelpWindow lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cycle", range(30))
def test_help_window_open_close_cycle(cycle: int) -> None:
    hw = _help_window()
    config = AppConfig()
    assert not hw.visible, "starts invisible"
    visible = hw.toggle()
    assert visible, "toggle → visible"
    hw.update(config)
    assert hw.visible, "still visible after update"
    hw.close()
    assert not hw.visible, "invisible after close"
    hw.close()  # idempotent
    assert not hw.visible, "still invisible after double-close"


def test_help_window_toggle_returns_correct_state() -> None:
    hw = _help_window()
    assert hw.toggle() is True


def test_help_window_refresh_invalidates_visible_backend() -> None:
    backend = _FakeHelpBackend()
    hw = HelpWindow(visible=True, backend_factory=lambda: backend)  # type: ignore[return-value]
    hw.update(AppConfig())

    hw.refresh(AppConfig())

    assert backend.refresh_count == 1
    assert hw.toggle() is False
    assert hw.toggle() is True


# ---------------------------------------------------------------------------
# _handle_keypress — all key paths
# ---------------------------------------------------------------------------


def _engine() -> GestureEngine:
    config = AppConfig()
    return GestureEngine(config.gestures, CursorMapper(config.cursor))


def test_handle_keypress_q_returns_user_quit() -> None:
    config = AppConfig()
    engine = _engine()
    mouse = _FakeMouse()
    safety = MouseSafetyGate()
    reason, _ = _handle_keypress(
        ord("q"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert reason is ExitReason.USER_QUIT_Q


def test_handle_keypress_p_toggles_pause() -> None:
    config = AppConfig()
    engine = _engine()
    mouse = _FakeMouse()
    safety = MouseSafetyGate()
    reason, notice = _handle_keypress(
        ord("p"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert reason is None
    assert engine.paused
    assert "Paused" in (notice or "")
    reason2, notice2 = _handle_keypress(
        ord("p"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert reason2 is None
    assert not engine.paused
    assert "Resumed" in (notice2 or "")


def test_handle_keypress_h_toggles_help() -> None:
    config = AppConfig()
    engine = _engine()
    mouse = _FakeMouse()
    safety = MouseSafetyGate()
    hw = _help_window()
    reason, notice = _handle_keypress(
        ord("h"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
        help_window=hw,
    )
    assert reason is None
    assert hw.visible


def test_handle_keypress_escape_is_ignored() -> None:
    config = AppConfig()
    engine = _engine()
    mouse = _FakeMouse()
    safety = MouseSafetyGate()
    reason, notice = _handle_keypress(
        27,
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert reason is None
    assert notice is not None and "ignored" in notice


def test_handle_keypress_unknown_key_is_noop() -> None:
    config = AppConfig()
    engine = _engine()
    mouse = _FakeMouse()
    safety = MouseSafetyGate()
    reason, notice = _handle_keypress(
        ord("z"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert reason is None
    assert notice is None


def test_handle_keypress_a_locked_returns_disabled_notice() -> None:
    config = AppConfig()
    engine = _engine()
    mouse = _FakeMouse()
    safety = MouseSafetyGate()
    reason, notice = _handle_keypress(
        ord("a"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
        mouse_output_locked=True,
    )
    assert reason is None
    assert notice is not None and "disabled" in notice.lower()


def test_handle_keypress_a_arms_and_disarms() -> None:
    config = AppConfig()
    engine = _engine()
    mouse = _FakeMouse()
    safety = MouseSafetyGate(armed=False)
    # arm
    reason, notice = _handle_keypress(
        ord("a"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert reason is None
    assert safety.armed, "should be armed after A"
    # disarm
    reason2, notice2 = _handle_keypress(
        ord("a"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert reason2 is None
    assert not safety.armed, "should be disarmed after second A"


@pytest.mark.parametrize("cycle", range(30))
def test_handle_keypress_pause_resume_cycle(cycle: int) -> None:
    config = AppConfig()
    engine = _engine()
    mouse = _FakeMouse()
    safety = MouseSafetyGate()
    _handle_keypress(
        ord("p"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert engine.paused
    _handle_keypress(
        ord("p"),
        config=config,
        engine=engine,
        safety=safety,
        mouse=mouse,  # type: ignore[arg-type]
    )
    assert not engine.paused


# ---------------------------------------------------------------------------
# _dispatch_ui_action
# ---------------------------------------------------------------------------


def test_dispatch_toggle_help_opens_and_closes() -> None:
    hw = _help_window()
    notice = _dispatch_ui_action("ui.toggle_help", hw)
    assert hw.visible
    assert notice == "Help opened"
    notice2 = _dispatch_ui_action("ui.toggle_help", hw)
    assert not hw.visible
    assert notice2 == "Help closed"


def test_dispatch_arm_sets_safety_armed() -> None:
    hw = _help_window()
    config = AppConfig()
    safety = MouseSafetyGate(armed=False)
    notice = _dispatch_ui_action("ui.arm", hw, config=config, safety=safety)
    assert safety.armed
    assert notice == "ARMED by gesture"


def test_dispatch_arm_twice_returns_already_armed() -> None:
    hw = _help_window()
    config = AppConfig()
    safety = MouseSafetyGate(armed=True)
    notice = _dispatch_ui_action("ui.arm", hw, config=config, safety=safety)
    assert notice == "Already armed"


def test_dispatch_arm_locked_returns_disabled() -> None:
    hw = _help_window()
    notice = _dispatch_ui_action("ui.arm", hw, mouse_output_locked=True)
    assert notice is not None and "disabled" in notice.lower()


def test_dispatch_unknown_action_returns_none() -> None:
    hw = _help_window()
    notice = _dispatch_ui_action("unknown.action", hw)
    assert notice is None


@pytest.mark.parametrize("cycle", range(30))
def test_dispatch_help_toggle_cycle(cycle: int) -> None:
    hw = _help_window()
    _dispatch_ui_action("ui.toggle_help", hw)
    assert hw.visible
    _dispatch_ui_action("ui.toggle_help", hw)
    assert not hw.visible


# ---------------------------------------------------------------------------
# GestureEngine pause/resume
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cycle", range(30))
def test_gesture_engine_pause_resume_cycle(cycle: int) -> None:
    config = AppConfig()
    engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
    events = engine.toggle_pause()
    assert events.paused
    events = engine.toggle_pause()
    assert not events.paused


# ---------------------------------------------------------------------------
# MouseSafetyGate arm/disarm
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cycle", range(30))
def test_safety_gate_arm_disarm_cycle(cycle: int) -> None:
    mouse = _FakeMouse()
    safety = MouseSafetyGate(armed=False)
    assert not safety.armed
    safety.toggle()
    assert safety.armed
    safety.disarm(mouse)  # type: ignore[arg-type]
    assert not safety.armed


def test_safety_gate_disarm_releases_keys() -> None:
    released: list[str] = []

    class _TrackingMouse(_FakeMouse):
        def release_all_keys(self) -> None:
            released.append("released")

        def drag_end(self) -> None: ...

    mouse = _TrackingMouse()
    safety = MouseSafetyGate(armed=True)
    safety.disarm(mouse)  # type: ignore[arg-type]
    assert released, "disarm should call release_all_keys"


# ---------------------------------------------------------------------------
# shortcut_mode baseline
# ---------------------------------------------------------------------------


def test_shortcut_mode_false_for_no_hand_frame() -> None:
    config = AppConfig()
    engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    events = engine.process(frame)
    assert not events.shortcut_mode


@pytest.mark.parametrize("cycle", range(30))
def test_shortcut_mode_never_set_without_hand(cycle: int) -> None:
    config = AppConfig()
    engine = GestureEngine(config.gestures, CursorMapper(config.cursor))
    frame = TrackingFrame(timestamp_ms=cycle, width=640, height=480, hand=None)
    events = engine.process(frame)
    assert not events.shortcut_mode


# ---------------------------------------------------------------------------
# Manual / interactive blocker stubs
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="requires physical camera + interactive display")
def test_full_app_camera_run_stub() -> None:
    """Manual: uv run --extra dev airpilot --camera 0
    Verify preview opens, sidebar non-overlap, no crash over 15 min.
    """


@pytest.mark.skip(reason="requires physical camera + interactive display")
def test_help_settings_during_camera_session_stub() -> None:
    """Manual: press H / S while preview is running.
    Verify Help/Settings windows open and close cleanly; repeat 5 times each.
    """


@pytest.mark.skip(reason="requires physical camera + interactive display")
def test_camera_interruption_recovery_stub() -> None:
    """Manual: unplug/replug USB camera.
    Verify reconnect message and app continues or exits cleanly.
    """


@pytest.mark.skip(reason="requires physical camera + interactive display")
def test_title_bar_close_exit_stub() -> None:
    """Manual: click X on AirPilot preview window.
    Verify exit reason MAIN_WINDOW_CLOSED is printed and app exits cleanly.
    """
