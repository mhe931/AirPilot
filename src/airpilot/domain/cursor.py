from __future__ import annotations

from dataclasses import dataclass

from airpilot.config import CursorConfig
from airpilot.domain.types import CursorPosition, Landmark


@dataclass(slots=True)
class CursorMapper:
    config: CursorConfig
    _last: CursorPosition | None = None
    _rebase_offset_x: int = 0
    _rebase_offset_y: int = 0

    @property
    def current(self) -> CursorPosition | None:
        return self._last

    def reset(self) -> None:
        self._last = None
        self._rebase_offset_x = 0
        self._rebase_offset_y = 0

    def set_current(self, position: CursorPosition | None) -> None:
        self._last = position

    def rebase(self, point: Landmark, target: CursorPosition) -> None:
        """Map the current hand anchor to the current cursor target.

        Clutching freezes the visible cursor while the hand may keep moving.  On
        release, continuing with absolute camera coordinates would make the next
        mapped frame jump toward the hand's new location.  A rebase preserves the
        calibrated motion scale/direction but treats this hand anchor as the new
        origin for the frozen target.
        """
        projected = self._project_without_rebase(point)
        self._rebase_offset_x = target.x - projected.x
        self._rebase_offset_y = target.y - projected.y
        self._last = target

    def map(self, point: Landmark) -> CursorPosition:
        mapped = self.project(point)

        if self._last is None:
            self._last = mapped
            return mapped

        dx = mapped.x - self._last.x
        dy = mapped.y - self._last.y
        if abs(dx) <= self.config.dead_zone_px and abs(dy) <= self.config.dead_zone_px:
            return self._last

        alpha = self._clamp(self.config.smoothing_alpha, 0.0, 1.0)
        smoothed = CursorPosition(
            x=int(round(self._last.x + dx * alpha * self.config.sensitivity)),
            y=int(round(self._last.y + dy * alpha * self.config.sensitivity)),
        )
        self._last = self._clamp_position(smoothed)
        return self._last

    def project(self, point: Landmark) -> CursorPosition:
        projected = self._project_without_rebase(point)
        return self._clamp_position(
            CursorPosition(
                x=projected.x + self._rebase_offset_x,
                y=projected.y + self._rebase_offset_y,
            )
        )

    def _project_without_rebase(self, point: Landmark) -> CursorPosition:
        normalized_x = self._normalize(
            point.x,
            self.config.camera_min_x,
            self.config.camera_max_x,
        )
        normalized_y = self._normalize(
            point.y,
            self.config.camera_min_y,
            self.config.camera_max_y,
        )
        if self.config.mirror_x:
            normalized_x = 1.0 - normalized_x

        x = int(round(self.config.screen_left + normalized_x * (self.config.screen_width - 1)))
        y = int(round(self.config.screen_top + normalized_y * (self.config.screen_height - 1)))
        return CursorPosition(x=x, y=y)

    def _clamp_position(self, position: CursorPosition) -> CursorPosition:
        return CursorPosition(
            x=int(
                self._clamp(
                    position.x,
                    self.config.screen_left,
                    self.config.screen_left + self.config.screen_width - 1,
                )
            ),
            y=int(
                self._clamp(
                    position.y,
                    self.config.screen_top,
                    self.config.screen_top + self.config.screen_height - 1,
                )
            ),
        )

    @staticmethod
    def _normalize(value: float, low: float, high: float) -> float:
        if high <= low:
            return 0.5
        return CursorMapper._clamp((value - low) / (high - low), 0.0, 1.0)

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
