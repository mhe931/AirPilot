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

    assert "tracking" in lines[0]
    assert "hand" in lines[0]
    assert "hand score 0.82" in lines[0]
    assert "left_pinch" in lines[1]
    assert "mouse safe" in lines[1]


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
    )

    assert "searching" in lines[0]
    assert "mouse off" in lines[1]


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

    assert "paused" in lines[0]
    assert "dragging" in lines[1]
    assert "mouse armed" in lines[1]


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
