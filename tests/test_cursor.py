from airpilot.config import CursorConfig
from airpilot.domain.cursor import CursorMapper
from airpilot.domain.types import Landmark


def test_cursor_mapping_clamps_without_mirroring_by_default() -> None:
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

    top_right_camera = mapper.map(Landmark(x=0.8, y=0.2))
    assert top_right_camera.x == 99
    assert top_right_camera.y == 0

    bottom_left_camera = mapper.map(Landmark(x=0.2, y=0.8))
    assert bottom_left_camera.x == 0
    assert bottom_left_camera.y == 49


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
            mirror_x=True,
        )
    )

    assert mapper.map(Landmark(x=0.8, y=0.2)).x == 0


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
            mirror_x=False,
        )
    )

    assert mapper.map(Landmark(x=0.3, y=0.3)).x == 5
    assert mapper.map(Landmark(x=0.3, y=0.3)).y == 5
