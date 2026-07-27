"""
Unit tests for the capture-image persistence service.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from src.post_capture_service import build_capture_filename, save_capture_pixmap_to_directory

try:
    from PySide6.QtGui import QColor, QPixmap
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


class TestBuildCaptureFilename(unittest.TestCase):
    """
    Verifies the timestamped capture filename format.
    """

    def test_matches_expected_pattern(self) -> None:
        """
        Ensures the filename follows the documented snappix_<timestamp>.png shape.
        """

        name = build_capture_filename(datetime(2026, 3, 5, 14, 7, 9))
        self.assertEqual(name, "snappix_2026-03-05_14-07-09.png")

    def test_defaults_to_current_time(self) -> None:
        """
        Ensures omitting the timestamp still produces a valid filename.
        """

        name = build_capture_filename()
        self.assertRegex(name, r"^snappix_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.png$")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for pixmap save tests")
class TestSaveCapturePixmapToDirectory(unittest.TestCase):
    """
    Verifies saving a capture pixmap to an existing directory.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for QPixmap operations.
        """

        cls._app = ensure_qapp()

    def test_saves_pixmap_and_returns_path(self) -> None:
        """
        Ensures a valid pixmap is written as a timestamped PNG in the directory.
        """

        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor(255, 0, 0))
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            saved_path = save_capture_pixmap_to_directory(pixmap, directory)

            self.assertIsNotNone(saved_path)
            assert saved_path is not None
            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.parent, directory)
            self.assertRegex(saved_path.name, r"^snappix_.*\.png$")

    def test_returns_none_when_save_fails(self) -> None:
        """
        Ensures a failed pixmap save is reported as None rather than raising.
        """

        failing_pixmap = MagicMock()
        failing_pixmap.save.return_value = False
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = save_capture_pixmap_to_directory(failing_pixmap, Path(tmp_dir))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
