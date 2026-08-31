from airpilot.config import CursorConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.types import Landmark


def test_cursor_mapping_uses_operator_direction_by_default() -> None:
    mapper = CursorMapper(
        CursorConfig(
            screen_width=100,
            screen_height=50,
            camera_min_x=0.2,
            camera_max_x=0.8,
            camera_min_y=0.2,
            camera_max_y=0.8,
            smoothing_alpha=1.0,
            dead_zone_px=0,
            mirror_x=True,
        )
    )

    physical_right = mapper.map(Landmark(x=0.2, y=0.2))
    assert physical_right.x == 99
    assert physical_right.y == 0

    physical_left = mapper.map(Landmark(x=0.8, y=0.8))
    assert physical_left.x == 0
    assert physical_left.y == 49


def test_cursor_mapping_can_still_mirror_when_requested() -> None:
    mapper = CursorMapper(
        CursorConfig(
            screen_width=100,
            screen_height=50,
            camera_min_x=0.2,
            camera_max_x=0.8,
            camera_min_y=0.2,
            camera_max_y=0.8,
            smoothing_alpha=1.0,
            dead_zone_px=0,
            mirror_x=False,
        )
    )

    assert mapper.map(Landmark(x=0.8, y=0.2)).x == 99


def test_cursor_mapping_spans_virtual_desktop_with_negative_origin() -> None:
    mapper = CursorMapper(
        CursorConfig(
            screen_left=-1280,
            screen_top=-200,
            screen_width=3200,
            screen_height=1280,
            camera_min_x=0.0,
            camera_max_x=1.0,
            camera_min_y=0.0,
            camera_max_y=1.0,
            smoothing_alpha=1.0,
            dead_zone_px=0,
            mirror_x=True,
        )
    )

    assert mapper.map(Landmark(x=1.0, y=0.0)).x == -1280
    bottom_right = mapper.map(Landmark(x=0.0, y=1.0))
    assert bottom_right.x == 1919
    assert bottom_right.y == 1079


def test_cursor_smoothing_and_dead_zone() -> None:
    mapper = CursorMapper(
        CursorConfig(
            screen_width=101,
            screen_height=101,
            camera_min_x=0.0,
            camera_max_x=1.0,
            camera_min_y=0.0,
            camera_max_y=1.0,
            smoothing_alpha=0.5,
            sensitivity=1.0,
            dead_zone_px=2,
            mirror_x=False,
        )
    )

    assert mapper.map(Landmark(x=0.0, y=0.0)).x == 0
    first_move = mapper.map(Landmark(x=1.0, y=1.0))
    assert first_move.x == 50
    assert first_move.y == 50

    dead_zone_move = mapper.map(Landmark(x=0.51, y=0.51))
    assert dead_zone_move == first_move


def test_higher_sensitivity_produces_larger_followup_movement() -> None:
    slow = CursorMapper(
        CursorConfig(
            screen_width=101,
            screen_height=101,
            camera_min_x=0.0,
            camera_max_x=1.0,
            camera_min_y=0.0,
            camera_max_y=1.0,
            smoothing_alpha=0.5,
            sensitivity=1.0,
            dead_zone_px=0,
            mirror_x=False,
        )
    )
    fast = CursorMapper(
        CursorConfig(
            screen_width=101,
            screen_height=101,
            camera_min_x=0.0,
            camera_max_x=1.0,
            camera_min_y=0.0,
            camera_max_y=1.0,
            smoothing_alpha=0.5,
            sensitivity=1.5,
            dead_zone_px=0,
            mirror_x=False,
        )
    )

    assert slow.map(Landmark(x=0.0, y=0.0)).x == 0
    assert fast.map(Landmark(x=0.0, y=0.0)).x == 0

    assert slow.map(Landmark(x=1.0, y=0.0)).x == 50
    assert fast.map(Landmark(x=1.0, y=0.0)).x == 75


def test_default_central_hand_region_reaches_screen_edges() -> None:
    mapper = CursorMapper(CursorConfig(smoothing_alpha=1.0, sensitivity=1.0, dead_zone_px=0))

    top_right = mapper.map(Landmark(x=0.31, y=0.27))
    bottom_left = mapper.map(Landmark(x=0.69, y=0.73))

    assert top_right.x == 1919
    assert top_right.y == 0
    assert bottom_left.x == 0
    assert bottom_left.y == 1079


def test_default_control_region_scales_across_resolutions() -> None:
    laptop = CursorMapper(
        CursorConfig(screen_width=1366, screen_height=768, smoothing_alpha=1.0, sensitivity=1.0)
    )
    desktop = CursorMapper(
        CursorConfig(screen_width=3840, screen_height=2160, smoothing_alpha=1.0, sensitivity=1.0)
    )

    assert laptop.map(Landmark(x=0.31, y=0.27)).x == 1365
    assert laptop.map(Landmark(x=0.69, y=0.73)).y == 767
    assert desktop.map(Landmark(x=0.31, y=0.27)).x == 3839
    assert desktop.map(Landmark(x=0.69, y=0.73)).y == 2159


def test_sensitivity_gain_stays_clamped_to_screen_edges() -> None:
    mapper = CursorMapper(
        CursorConfig(
            screen_width=101,
            screen_height=101,
            camera_min_x=0.31,
            camera_max_x=0.69,
            camera_min_y=0.27,
            camera_max_y=0.73,
            smoothing_alpha=1.0,
            sensitivity=10.0,
            dead_zone_px=0,
            mirror_x=False,
        )
    )

    mapper.map(Landmark(x=0.50, y=0.50))
    assert mapper.map(Landmark(x=0.69, y=0.73)).x == 100
    assert mapper.map(Landmark(x=0.69, y=0.73)).y == 100


def test_invalid_calibration_uses_center() -> None:
    mapper = CursorMapper(
        CursorConfig(
            screen_width=11,
            screen_height=11,
            camera_min_x=0.8,
            camera_max_x=0.2,
            camera_min_y=0.8,
            camera_max_y=0.2,
            smoothing_alpha=1.0,
            mirror_x=True,
        )
    )

    assert mapper.map(Landmark(x=0.3, y=0.3)).x == 5
    assert mapper.map(Landmark(x=0.3, y=0.3)).y == 5
