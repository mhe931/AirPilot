from airpilot.app import (
    ExitReason,
    HelpBackend,
    HelpBounds,
    HelpWindow,
    TrackingStats,
    _dispatch_ui_action,
    _filter_help_sections,
    _handle_keypress,
    _help_initial_bounds,
    _help_lines,
    _help_sections,
    _help_text_wrap_mode,
    _preview_window_closed,
    _text_width,
    _wrap_help_lines,
    status_lines,
)
from airpilot.config import AppConfig
from airpilot.domain.types import GestureEvents, HandLandmarks, Landmark, TrackingFrame
from airpilot.input import RecordingMouseController
from airpilot.safety import MouseSafetyGate


def test_status_lines_show_tracking_gesture_and_safe_mouse() -> None:
    frame = TrackingFrame(
        timestamp_ms=0,
        width=640,
        height=480,
        hand=HandLandmarks(tuple(Landmark(0.5, 0.5) for _ in range(21)), confidence=0.82),
    )
    lines = status_lines(
        frame,
        GestureEvents(active_gesture="click_candidate", status="tracking"),
        AppConfig(),
        armed=False,
        fps=29.6,
    )

    assert lines[0] == "AIRPILOT - DISARMED"
    assert "thumb+middle to arm" in lines[1]
    assert "hand" in lines[2]
    assert "click_candidate" in lines[2]
    assert "score" in lines[2]
    assert "A arm" in lines[3]
    assert not any("Thumb + index" in line for line in lines)


def test_status_lines_show_task_view_guidance() -> None:
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)

    lines = status_lines(
        frame,
        GestureEvents(active_gesture="task_view", status="task_view"),
        AppConfig(),
        armed=True,
        fps=24.0,
    )

    assert lines[0] == "AIRPILOT - ACTIVE"
    assert "move left/right" in lines[1]


def test_status_lines_show_arm_gesture_progress() -> None:
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)

    lines = status_lines(
        frame,
        GestureEvents(active_gesture="arm_pending", status="arm_pending"),
        AppConfig(),
        armed=False,
        fps=24.0,
    )

    assert lines[0] == "AIRPILOT - DISARMED"
    assert "ARMING" in lines[1]


def test_status_lines_show_mouse_off_for_no_mouse_mode() -> None:
    config = AppConfig()
    config.runtime.enable_real_mouse = False
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)

    lines = status_lines(
        frame,
        GestureEvents(active_gesture="none", status="searching"),
        config,
        armed=False,
        fps=0.0,
        mouse_output_locked=True,
    )

    assert lines[0] == "AIRPILOT - PREVIEW ONLY"
    assert "Mouse output disabled" in lines[1]
    assert "searching" in lines[2]
    assert "Q quit" in lines[3]


def test_status_lines_show_paused_armed_and_active_gestures() -> None:
    config = AppConfig()
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)

    lines = status_lines(
        frame,
        GestureEvents(active_gesture="dragging", paused=True, status="paused"),
        config,
        armed=True,
        fps=31.0,
    )

    assert lines[0] == "AIRPILOT - PAUSED"
    assert "Press P to resume" in lines[1]
    assert "dragging" in lines[2]


def test_status_lines_show_thumb_folded_clutch_guidance() -> None:
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)

    lines = status_lines(
        frame,
        GestureEvents(active_gesture="clutch", status="clutch"),
        AppConfig(),
        armed=True,
        fps=31.0,
    )

    assert lines[1] == "Thumb folded: pointer frozen. Open thumb to resume."


def test_status_lines_surface_preview_drawing_warning() -> None:
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)

    lines = status_lines(
        frame,
        GestureEvents(active_gesture="none", status="tracking"),
        AppConfig(),
        armed=False,
        fps=24.0,
        drawing_error="landmarks disabled",
    )

    assert lines[-1] == "preview landmarks disabled"


def test_status_lines_show_armed_notice() -> None:
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)

    lines = status_lines(
        frame,
        GestureEvents(active_gesture="none", status="tracking"),
        AppConfig(),
        armed=True,
        fps=24.0,
        operator_notice="Mouse control enabled",
    )

    assert lines[0] == "AIRPILOT - ACTIVE"
    assert lines[1] == "Mouse control enabled"


def test_overlay_layout_truncates_to_frame_width() -> None:
    longest = "Controls: A = Arm/Disarm | P = Pause/Resume | Q = Quit"
    layout = __import__("airpilot.app", fromlist=["_layout_overlay"])._layout_overlay(
        ["AIRPILOT - DISARMED", longest],
        160,
    )

    assert all(line.x >= 0 for line in layout)
    assert all(len(line.text) <= len(longest) for line in layout)
    assert layout[1].text.endswith("...")


def test_h_key_toggles_help_window() -> None:
    help_window = HelpWindow()

    should_exit, notice = _handle_keypress(
        ord("h"),
        config=AppConfig(),
        engine=_StubEngine(),
        safety=MouseSafetyGate(),
        mouse=RecordingMouseController(),
        help_window=help_window,
    )

    assert not should_exit
    assert notice == "Help opened"
    assert help_window.visible is True

    should_exit, notice = _handle_keypress(
        ord("H"),
        config=AppConfig(),
        engine=_StubEngine(),
        safety=MouseSafetyGate(),
        mouse=RecordingMouseController(),
        help_window=help_window,
    )

    assert not should_exit
    assert notice == "Help closed"
    assert help_window.visible is False


def test_q_key_reports_explicit_quit_reason() -> None:
    exit_reason, notice = _handle_keypress(
        ord("q"),
        config=AppConfig(),
        engine=_StubEngine(),
        safety=MouseSafetyGate(),
        mouse=RecordingMouseController(),
    )

    assert exit_reason is ExitReason.USER_QUIT_Q
    assert notice == "Quit requested"


def test_escape_key_does_not_quit() -> None:
    exit_reason, notice = _handle_keypress(
        27,
        config=AppConfig(),
        engine=_StubEngine(),
        safety=MouseSafetyGate(),
        mouse=RecordingMouseController(),
    )

    assert exit_reason is None
    assert notice == "Esc ignored; press Q to quit"


def test_preview_close_detection_only_reports_actual_hidden_window(monkeypatch: object) -> None:
    monkeypatch.setattr("airpilot.app.cv2.getWindowProperty", lambda *_args: 1.0)
    assert not _preview_window_closed("AirPilot", preview_created=True)

    monkeypatch.setattr("airpilot.app.cv2.getWindowProperty", lambda *_args: -1.0)
    assert not _preview_window_closed("AirPilot", preview_created=True)

    monkeypatch.setattr("airpilot.app.cv2.getWindowProperty", lambda *_args: 0.0)
    assert _preview_window_closed("AirPilot", preview_created=True)


def test_preview_close_detection_ignores_transient_opencv_errors(monkeypatch: object) -> None:
    import cv2

    def raise_cv2_error(*_args: object) -> float:
        raise cv2.error("transient")

    monkeypatch.setattr("airpilot.app.cv2.getWindowProperty", raise_cv2_error)

    assert not _preview_window_closed("AirPilot", preview_created=True)


def test_gesture_arm_enables_mouse_output_when_config_was_disabled() -> None:
    config = AppConfig()
    config.runtime.enable_real_mouse = False
    safety = MouseSafetyGate()

    notice = _dispatch_ui_action("ui.arm", None, config=config, safety=safety)

    assert notice == "ARMED by gesture"
    assert config.runtime.enable_real_mouse is True
    assert safety.armed is True


def test_gesture_arm_respects_mouse_output_lock() -> None:
    config = AppConfig()
    config.runtime.enable_real_mouse = False
    safety = MouseSafetyGate()

    notice = _dispatch_ui_action(
        "ui.arm",
        None,
        config=config,
        safety=safety,
        mouse_output_locked=True,
    )

    assert notice == "Mouse output disabled for diagnostics/--no-mouse"
    assert config.runtime.enable_real_mouse is False
    assert safety.armed is False


def test_help_window_update_reuses_single_window(monkeypatch: object) -> None:
    del monkeypatch
    backend = _FakeHelpBackend()
    help_window = HelpWindow(visible=True, backend_factory=lambda: backend)

    help_window.update(AppConfig())
    help_window.update(AppConfig())

    assert backend.update_count == 2
    assert help_window.visible is True


def test_help_window_stays_closed_after_manual_close(monkeypatch: object) -> None:
    del monkeypatch
    backend = _FakeHelpBackend(open_after_update=False)
    help_window = HelpWindow(visible=True, backend_factory=lambda: backend)

    help_window.update(AppConfig())
    help_window.update(AppConfig())

    assert backend.update_count == 1
    assert help_window.visible is False


def test_help_content_is_readable_and_structured() -> None:
    lines = _help_lines(AppConfig())
    sections = _help_sections(AppConfig())
    section_titles = {section.title for section in sections}

    assert "AirPilot Help" in lines
    assert "QUICK START" in lines
    assert "MOUSE" in lines
    assert "CONTROL" in lines
    assert "SHORTCUT MODE" in lines
    assert "WINDOWS/APPS" in lines
    assert "BROWSER" in lines
    assert "PRESENTATION" in lines
    assert "MEDIA" in lines
    assert any("Task View" in line for line in lines)
    assert any("Move pointer | Thumb open; move palm/knuckle" in line for line in lines)
    assert any("Left click | While clutched, bend/release index" in line for line in lines)
    assert any(
        "Clipboard history | Shortcut mode + hold thumb/middle | Win+V" in line for line in lines
    )
    assert any("Quit AirPilot | Press Q" in line for line in lines)
    assert {"INTRO", "QUICK START", "MOUSE", "CONTROL", "SHORTCUT MODE"} <= section_titles
    wrapped = _wrap_help_lines(lines, 460)
    assert not any(line.endswith("...") for line in wrapped)
    assert any("Win+V" in line for line in wrapped)
    assert all(_text_width(line, 0.55) <= 460 for line in wrapped[2:])


def test_help_initial_bounds_fit_monitor_work_area() -> None:
    work_area = HelpBounds(left=100, top=50, width=800, height=600)

    bounds = _help_initial_bounds(work_area)

    assert bounds.left >= work_area.left
    assert bounds.top >= work_area.top
    assert bounds.left + bounds.width <= work_area.left + work_area.width
    assert bounds.top + bounds.height <= work_area.top + work_area.height
    assert bounds.width >= 640
    assert bounds.height >= 420


def test_help_initial_bounds_fit_small_monitor_work_area() -> None:
    work_area = HelpBounds(left=0, top=0, width=500, height=360)

    bounds = _help_initial_bounds(work_area)

    assert bounds.left + bounds.width <= 500
    assert bounds.top + bounds.height <= 360
    assert bounds.width >= 320
    assert bounds.height >= 280


def test_help_content_wraps_vertically_without_horizontal_scroll() -> None:
    sections = _filter_help_sections(_help_sections(AppConfig()), "clipboard")

    assert sections
    assert _help_text_wrap_mode() == "word"
    assert any("Clipboard history" in line for section in sections for line in section.lines)


def test_help_wrapping_does_not_truncate_long_pipe_fields() -> None:
    lines = [
        "Shortcut mode + hold thumb/middle | "
        "Extremely long custom clipboard history action label | Win+V | enabled",
        "A | WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW | Z",
    ]

    wrapped = _wrap_help_lines(lines, 260)

    assert not any(line.endswith("...") for line in wrapped)
    assert any("Win+V" in line for line in wrapped)
    assert any("Z" in line for line in wrapped)
    assert _text_width(wrapped[0], 0.75) <= 260
    assert all(_text_width(line, 0.55) <= 260 for line in wrapped[1:])


def test_tracking_stats_summary_is_aggregate_only() -> None:
    stats = TrackingStats()
    hand = HandLandmarks(tuple(Landmark(0.5, 0.5) for _ in range(21)), confidence=0.9)

    stats.observe(
        TrackingFrame(timestamp_ms=100, width=640, height=480, hand=None),
        GestureEvents(),
    )
    stats.observe(
        TrackingFrame(timestamp_ms=140, width=640, height=480, hand=hand),
        GestureEvents(tracking_lost=True),
    )

    summary = stats.summary(camera_backend="DirectShow")
    assert summary["camera_backend"] == "DirectShow"
    assert summary["frames"] == 2
    assert summary["frame_width"] == 640
    assert summary["frame_height"] == 480
    assert summary["hand_frames"] == 1
    assert summary["hand_observed"] is True
    assert summary["tracking_lost_events"] == 1
    assert "camera_reconnects" not in summary
    assert "image" not in summary


def test_tracking_stats_handles_zero_and_out_of_order_timestamps() -> None:
    stats = TrackingStats()
    assert stats.summary()["frames"] == 0

    stats.observe(
        TrackingFrame(timestamp_ms=200, width=640, height=480, hand=None),
        GestureEvents(),
    )
    stats.observe(
        TrackingFrame(timestamp_ms=100, width=640, height=480, hand=None),
        GestureEvents(),
    )

    assert stats.summary()["max_frame_gap_ms"] == 0


class _StubEngine:
    def toggle_pause(self) -> GestureEvents:
        return GestureEvents(paused_changed=True, paused=True)


class _FakeHelpBackend(HelpBackend):
    def __init__(self, *, open_after_update: bool = True) -> None:
        self.update_count = 0
        self.closed = False
        self._open_after_update = open_after_update

    def update(self, _config: AppConfig) -> None:
        self.update_count += 1
        self.closed = not self._open_after_update

    def close(self) -> None:
        self.closed = True

    def is_open(self) -> bool:
        return not self.closed
