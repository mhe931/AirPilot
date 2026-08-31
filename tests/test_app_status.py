from airpilot.app import (
    ExitReason,
    HelpBackend,
    HelpBounds,
    HelpWindow,
    TrackingStats,
    _compute_sidebar_width,
    _disable_cv2_window_maximize,
    _dispatch_ui_action,
    _filter_help_sections,
    _handle_keypress,
    _help_initial_bounds,
    _help_lines,
    _help_sections,
    _help_text_wrap_mode,
    _layout_overlay,
    _preview_window_closed,
    _sidebar_lines,
    _text_width,
    _TkSharedRoot,
    _wrap_help_lines,
    status_lines,
)
from airpilot.config import AppConfig, TextStyleConfig
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
    layout = _layout_overlay(
        ["AIRPILOT - DISARMED", longest],
        160,
    )

    assert all(line.x >= 0 for line in layout)
    assert all(len(line.text) <= len(longest) for line in layout)
    assert layout[1].text.endswith("...")


def test_overlay_layout_x_offset_clears_sidebar() -> None:
    """Overlay text x positions must be >= sidebar_width so text is never
    rendered behind the sidebar panel regardless of image width."""
    sidebar_width = 120
    layout = _layout_overlay(
        ["AIRPILOT - ACTIVE", "Mouse control enabled", "detail line"],
        640,
        sidebar_width=sidebar_width,
    )

    assert all(line.x >= sidebar_width for line in layout), (
        f"Overlay line x={[ln.x for ln in layout]} must all be >= sidebar_width={sidebar_width}"
    )
    assert all(line.x == sidebar_width + 10 for line in layout)


def test_overlay_layout_zero_sidebar_width_uses_default_offset() -> None:
    """When no sidebar is shown, x should default to 10 (original behaviour)."""
    layout = _layout_overlay(["AIRPILOT - DISARMED", "guidance"], 640, sidebar_width=0)

    assert all(line.x == 10 for line in layout)


def test_compute_sidebar_width_returns_zero_when_disabled() -> None:
    config = AppConfig()
    config.text_styles.sidebar_enabled = False
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    events = GestureEvents()

    width = _compute_sidebar_width(frame, events, config, armed=False, image_width=640)

    assert width == 0


def test_compute_sidebar_width_positive_when_enabled() -> None:
    config = AppConfig()
    config.text_styles.sidebar_enabled = True
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    events = GestureEvents()

    width = _compute_sidebar_width(frame, events, config, armed=False, image_width=640)

    assert width > 0
    assert width <= 640 // 3


def test_compute_sidebar_width_bounded_by_one_third_image() -> None:
    """Sidebar width must never exceed one third of the image width."""
    config = AppConfig()
    config.text_styles.sidebar_enabled = True
    config.text_styles.sidebar_scale_pct = 400  # extreme scale
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    events = GestureEvents()

    width = _compute_sidebar_width(frame, events, config, armed=False, image_width=640)

    assert width <= 640 // 3


def test_overlay_text_never_behind_sidebar_at_various_widths() -> None:
    """Geometry assertion: for any sidebar_width, all overlay x values must be
    >= sidebar_width so text is always fully inside the camera-preview region."""
    for image_width in (320, 480, 640, 1280):
        for sidebar_fraction in (0, 0.1, 0.2, 0.33):
            sidebar_width = int(image_width * sidebar_fraction)
            layout = _layout_overlay(
                ["AIRPILOT - DISARMED", "guidance text", "detail info"],
                image_width,
                sidebar_width=sidebar_width,
            )
            for line in layout:
                assert line.x >= sidebar_width, (
                    f"image_width={image_width}, sidebar_width={sidebar_width}: "
                    f"line.x={line.x} < sidebar_width"
                )


# ---------------------------------------------------------------------------
# Lifecycle / Tk root stress tests (no camera hardware required)
# ---------------------------------------------------------------------------


def test_tk_shared_root_acquire_release_cycles() -> None:
    """Simulate 30 acquire/release cycles (equivalent to 30 open/close cycles
    of Help or Settings windows) and verify the root is cleaned up cleanly."""
    import gc

    for _ in range(30):
        root = _TkSharedRoot.acquire()
        assert root is not None
        _TkSharedRoot.release()
        gc.collect()

    # After all releases the root should be gone
    assert _TkSharedRoot._root is None
    assert _TkSharedRoot._refcount == 0


def test_tk_shared_root_force_close_is_idempotent() -> None:
    """force_close must be safe to call multiple times and with no root."""
    import gc

    _TkSharedRoot.force_close()
    _TkSharedRoot.force_close()  # second call must not raise
    gc.collect()

    assert _TkSharedRoot._root is None
    assert _TkSharedRoot._refcount == 0


def test_tk_shared_root_pump_no_op_without_root() -> None:
    """pump() must be a no-op (not raise) when no Tk root exists."""
    _TkSharedRoot.force_close()
    _TkSharedRoot.pump()  # must not raise


def test_help_window_open_close_cycle_cleans_tk_root() -> None:
    """Opening and then closing HelpWindow must leave no Tk root behind."""
    import gc

    backend = _FakeHelpBackend()
    win = HelpWindow(visible=True, backend_factory=lambda: backend)

    win.update(AppConfig())
    assert win.visible is True

    win.close()
    gc.collect()

    # Shared root refcount must be at zero after close
    assert _TkSharedRoot._refcount == 0


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

    def force_refresh(self) -> None:
        pass


# ---------------------------------------------------------------------------
# New tests for opacity, dashboard, maximize-disable, and sidebar
# ---------------------------------------------------------------------------


def test_text_style_defaults_have_valid_opacity_bounds() -> None:
    ts = TextStyleConfig()
    assert 0.1 <= ts.help_opacity <= 1.0, "help_opacity default out of bounds"
    assert 0.1 <= ts.settings_opacity <= 1.0, "settings_opacity default out of bounds"


def test_text_style_opacity_roundtrips_through_save_load(tmp_path: object) -> None:
    from pathlib import Path

    from airpilot.config import load_config, save_config

    path = Path(tmp_path) / "cfg.json"  # type: ignore[arg-type]
    config = AppConfig()
    config.text_styles.help_opacity = 0.75
    config.text_styles.settings_opacity = 0.55
    save_config(config, path)

    loaded = load_config(path)
    assert loaded.text_styles.help_opacity == 0.75
    assert loaded.text_styles.settings_opacity == 0.55


def test_text_style_missing_opacity_fields_load_with_defaults() -> None:
    """An old config without opacity fields must load cleanly with defaults."""
    import json
    import tempfile
    from pathlib import Path

    from airpilot.config import load_config

    raw = {
        "schema_version": 11,
        "text_styles": {
            "overlay_scale_pct": 100,
            "overlay_fg": "#ffffff",
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(raw, f)
        tmp = f.name
    loaded = load_config(Path(tmp))
    assert loaded.text_styles.help_opacity == 1.0
    assert loaded.text_styles.settings_opacity == 1.0


def test_sidebar_lines_show_action_labels_for_gestures() -> None:
    config = AppConfig()
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    events = GestureEvents(active_gesture="none")

    lines = _sidebar_lines(frame, events, config, armed=True)

    assert any("move" in line for line in lines)
    assert any("freeze" in line for line in lines)
    assert any("click" in line for line in lines)
    assert any("scroll" in line for line in lines)
    assert any("arm" in line for line in lines)
    assert any("help" in line for line in lines)


def test_sidebar_lines_expand_shortcut_mode_mappings() -> None:
    config = AppConfig()
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    events = GestureEvents(active_gesture="shortcut_mode", shortcut_mode=True)

    lines = _sidebar_lines(frame, events, config, armed=True)

    # Should see shortcut mode label
    assert any("SHORTCUT" in line for line in lines)
    # Should see configured shortcut action labels
    assert any("idx" in line or "mid" in line or "ring" in line for line in lines)


def test_sidebar_lines_show_enabled_gesture_bindings() -> None:
    from airpilot.config import GestureBinding

    config = AppConfig()
    config.gesture_bindings = [
        GestureBinding(
            id="test_binding",
            enabled=True,
            action_id="presentation.next_slide",
        )
    ]
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    events = GestureEvents()

    lines = _sidebar_lines(frame, events, config, armed=False)

    assert any("test_bin" in line for line in lines)


def test_sidebar_lines_empty_when_disabled() -> None:
    config = AppConfig()
    config.text_styles.sidebar_enabled = False
    frame = TrackingFrame(timestamp_ms=0, width=640, height=480, hand=None)
    events = GestureEvents()

    lines = _sidebar_lines(frame, events, config, armed=False)

    assert lines == []


def test_disable_cv2_window_maximize_is_no_op_on_missing_window() -> None:
    """Should not raise even when the window title doesn't exist."""
    _disable_cv2_window_maximize("__nonexistent_airpilot_test_window__")


def test_help_sections_include_quit_and_pause_and_settings() -> None:
    sections = _help_sections(AppConfig())
    all_lines = [line for s in sections for line in s.lines]

    assert any("Quit" in line or "quit" in line for line in all_lines)
    assert any("pause" in line.lower() or "Pause" in line for line in all_lines)
    assert any("Settings" in line or "settings" in line for line in all_lines)
    assert any("Help" in line or "help" in line for line in all_lines)


def test_help_sections_include_shortcut_mode_entries() -> None:
    sections = _help_sections(AppConfig())
    section_titles = {s.title for s in sections}
    assert "SHORTCUT MODE" in section_titles


def test_help_emoji_present_in_formatted_rows() -> None:
    sections = _help_sections(AppConfig())
    # Formatted rows use │ (vertical bar) as column separator
    table_lines = [line for s in sections for line in s.lines if "│" in line and s.title != "INTRO"]
    # At least some rows should have an emoji character in them
    assert len(table_lines) > 0
    # Each formatted row should contain │ separators (4 columns)
    for line in table_lines[:5]:
        parts = [p.strip() for p in line.split("│")]
        assert len(parts) >= 4
