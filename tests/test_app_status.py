from airpilot.app import TrackingStats, status_lines
from airpilot.config import AppConfig
from airpilot.domain.types import GestureEvents, HandLandmarks, Landmark, TrackingFrame


def test_status_lines_show_tracking_gesture_and_safe_mouse() -> None:
    frame = TrackingFrame(
        timestamp_ms=0,
        width=640,
        height=480,
        hand=HandLandmarks(tuple(Landmark(0.5, 0.5) for _ in range(21)), confidence=0.82),
    )
    lines = status_lines(
        frame,
        GestureEvents(active_gesture="left_pinch", status="tracking"),
        AppConfig(),
        armed=False,
        fps=29.6,
    )

    assert lines[0] == "AIRPILOT - DISARMED"
    assert "A = Enable Mouse" in lines[1]
    assert "tracking hand" in lines[2]
    assert "left_pinch" in lines[2]
    assert "control" in lines[2]
    assert "A arm" in lines[3]
    assert any(line.startswith("Gestures:") for line in lines)


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
