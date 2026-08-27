from __future__ import annotations

from dataclasses import dataclass

from airpilot.config import CursorConfig
from airpilot.domain.types import CursorPosition, Landmark


@dataclass(slots=True)
class CursorMapper:
    config: CursorConfig
    _last: CursorPosition | None = None

    def reset(self) -> None:
        self._last = None

    def map(self, point: Landmark) -> CursorPosition:
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
        mapped = CursorPosition(x=x, y=y)

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
