"""
Unit tests for Snappix MeasureBox settings and session helpers.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtWidgets import QMenu

    from src.measurebox.session import MeasureBoxSession
    from src.measurebox.settings import MeasureBoxSettings, MeasureBoxSettingsManager
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for MeasureBox tests")
class TestMeasureBoxSettings(unittest.TestCase):
    """Verifies MeasureBox settings persistence."""

    def test_load_returns_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = MeasureBoxSettingsManager(Path(tmp_dir) / "measurebox.json")
            settings = manager.load()
            self.assertEqual(settings.line_rgba, (0, 255, 0, 179))
            self.assertFalse(settings.ruler_enabled)
            self.assertTrue(settings.crosshair_enabled)

    def test_round_trip_persists_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "measurebox.json"
            manager = MeasureBoxSettingsManager(path)
            settings = MeasureBoxSettings(
                line_rgba=(10, 20, 30, 40),
                fill_rgba=(50, 60, 70, 80),
                ruler_enabled=True,
                ruler_outside=True,
                crosshair_enabled=False,
            )
            manager.save(settings)
            loaded = manager.load()
            self.assertEqual(loaded.line_rgba, (10, 20, 30, 40))
            self.assertEqual(loaded.fill_rgba, (50, 60, 70, 80))
            self.assertTrue(loaded.ruler_enabled)
            self.assertTrue(loaded.ruler_outside)
            self.assertFalse(loaded.crosshair_enabled)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for MeasureBox tests")
class TestMeasureBoxSession(unittest.TestCase):
    """Verifies session helpers without starting the live overlay."""

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_settings_menu_contains_expected_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            session = MeasureBoxSession(settings_path=Path(tmp_dir) / "measurebox.json")
            menu = session.build_settings_menu()
            self.assertIsInstance(menu, QMenu)
            labels = [action.text() for action in menu.actions() if action.text()]
            self.assertIn("Line Color...", labels)
            self.assertIn("Fill Color...", labels)
            self.assertIn("Show Pixel Ruler (px)", labels)
            self.assertIn("Ruler Outside Rectangle", labels)
            self.assertIn("Show Left Shift Crosshair", labels)

    def test_apply_settings_updates_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "measurebox.json"
            session = MeasureBoxSession(settings_path=path)
            session.apply_settings(
                MeasureBoxSettings(
                    line_rgba=(1, 2, 3, 4),
                    fill_rgba=(5, 6, 7, 8),
                    ruler_enabled=True,
                    ruler_outside=False,
                    crosshair_enabled=False,
                )
            )
            settings = session.settings
            self.assertEqual(settings.line_rgba, (1, 2, 3, 4))
            self.assertTrue(settings.ruler_enabled)
            self.assertFalse(settings.crosshair_enabled)
            self.assertTrue(path.exists())

    @patch("src.measurebox.session.EscapeListener")
    @patch("src.measurebox.session.GlobalCtrlClickListener")
    @patch("src.measurebox.session.OverlayView")
    def test_start_then_stop_tears_down_overlay(
        self,
        overlay_cls: MagicMock,
        ctrl_cls: MagicMock,
        escape_cls: MagicMock,
    ) -> None:
        overlay = MagicMock()
        overlay_cls.return_value = overlay
        ctrl = MagicMock()
        ctrl_cls.return_value = ctrl
        escape = MagicMock()
        escape_cls.return_value = escape

        finished = MagicMock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            session = MeasureBoxSession(
                settings_path=Path(tmp_dir) / "measurebox.json",
                on_finished=finished,
            )
            session.start()
            self.assertTrue(session.is_active())
            session.stop()
            self.assertFalse(session.is_active())
            overlay.clear_all.assert_called()
            overlay.deleteLater.assert_called()
            ctrl.stop.assert_called()
            escape.stop.assert_called()
            finished.assert_called_once()


if __name__ == "__main__":
    unittest.main()
