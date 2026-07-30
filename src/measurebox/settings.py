"""Persisted MeasureBox settings for Snappix Capture."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class MeasureBoxSettings:
    """MeasureBox appearance and interaction options."""

    line_rgba: tuple[int, int, int, int] = (0, 255, 0, 179)
    fill_rgba: tuple[int, int, int, int] = (0, 255, 0, 51)
    ruler_enabled: bool = False
    ruler_outside: bool = False
    crosshair_enabled: bool = True


class MeasureBoxSettingsManager:
    """Read and write MeasureBox settings under the Snappix config directory."""

    def __init__(self, config_path: Path) -> None:
        """
        Initialize the manager with a target config path.

        Args:
            config_path: Path to JSON settings file.
        """

        self.config_path = config_path

    def load(self) -> MeasureBoxSettings:
        """
        Load MeasureBox settings from disk.

        Returns:
            Loaded settings or defaults when the file is missing or invalid.
        """

        if not self.config_path.exists():
            return MeasureBoxSettings()

        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return MeasureBoxSettings()

        return MeasureBoxSettings(
            line_rgba=self._as_rgba(payload.get("line_rgba"), (0, 255, 0, 179)),
            fill_rgba=self._as_rgba(payload.get("fill_rgba"), (0, 255, 0, 51)),
            ruler_enabled=bool(payload.get("ruler_enabled", False)),
            ruler_outside=bool(payload.get("ruler_outside", False)),
            crosshair_enabled=bool(payload.get("crosshair_enabled", True)),
        )

    def save(self, settings: MeasureBoxSettings) -> None:
        """
        Persist MeasureBox settings as JSON.

        Args:
            settings: Settings model to store.

        Returns:
            None
        """

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "line_rgba": list(settings.line_rgba),
            "fill_rgba": list(settings.fill_rgba),
            "ruler_enabled": settings.ruler_enabled,
            "ruler_outside": settings.ruler_outside,
            "crosshair_enabled": settings.crosshair_enabled,
        }
        self.config_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @staticmethod
    def _as_rgba(value: object, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """
        Validate and normalize an RGBA value from JSON.

        Args:
            value: Unknown JSON value.
            fallback: Fallback RGBA tuple.

        Returns:
            Valid RGBA tuple.
        """

        if not isinstance(value, list) or len(value) != 4:
            return fallback
        try:
            r, g, b, a = (int(channel) for channel in value)
        except (TypeError, ValueError):
            return fallback
        channels = (r, g, b, a)
        if any(channel < 0 or channel > 255 for channel in channels):
            return fallback
        return channels
