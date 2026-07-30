"""
Unit tests for external media import helpers.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.constants import MAX_VIDEO_DURATION_MS
    from src.media_import import (
        VideoFileProbe,
        build_import_canvas_background,
        load_image_pixmap,
        probe_video_file,
        validate_video_duration,
        video_too_long_message,
    )
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for media import tests")
class TestMediaImportHelpers(unittest.TestCase):
    """
    Verifies image background selection and video import validation helpers.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for pixmap/image helpers.
        """

        ensure_qapp()

    def test_build_import_canvas_background_uses_white_for_opaque_image(self) -> None:
        """
        Ensures opaque imported images get a white document background.
        """

        pixmap = QPixmap(40, 30)
        pixmap.fill(QColor(120, 80, 40, 255))
        background = build_import_canvas_background(pixmap)
        self.assertEqual(background.size(), pixmap.size())
        self.assertEqual(background.toImage().pixelColor(0, 0), QColor(255, 255, 255, 255))

    def test_build_import_canvas_background_uses_transparency_for_alpha_image(self) -> None:
        """
        Ensures images with alpha use a transparent document background.
        """

        image = QImage(20, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        image.setPixelColor(5, 5, QColor(255, 0, 0, 128))
        pixmap = QPixmap.fromImage(image)
        background = build_import_canvas_background(pixmap)
        self.assertLess(background.toImage().pixelColor(0, 0).alpha(), 255)

    def test_load_image_pixmap_reads_png_file(self) -> None:
        """
        Ensures supported image files load into pixmaps.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.png"
            image = QImage(12, 10, QImage.Format.Format_RGB32)
            image.fill(QColor(10, 20, 30))
            self.assertTrue(image.save(str(path), "PNG"))
            loaded = load_image_pixmap(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertFalse(loaded.isNull())
            self.assertEqual(loaded.width(), 12)

    def test_validate_video_duration_enforces_editor_limit(self) -> None:
        """
        Ensures only positive durations up to the editor limit are accepted.
        """

        self.assertTrue(validate_video_duration(1))
        self.assertTrue(validate_video_duration(MAX_VIDEO_DURATION_MS))
        self.assertFalse(validate_video_duration(0))
        self.assertFalse(validate_video_duration(MAX_VIDEO_DURATION_MS + 1))

    def test_max_video_duration_is_thirty_minutes(self) -> None:
        """
        Pins the program-wide maximum video length to 30 minutes.
        """

        self.assertEqual(MAX_VIDEO_DURATION_MS, 30 * 60 * 1000)

    def test_video_too_long_message_names_limit_and_actual_length(self) -> None:
        """
        Ensures the shared warning states the limit and the rejected length.
        """

        message = video_too_long_message(31 * 60 * 1000)
        self.assertIn("30 minutes", message)
        self.assertIn("31.0 minutes", message)

    def test_video_too_long_message_omits_length_when_unknown(self) -> None:
        """
        Ensures the warning stays clean when no duration is available.
        """

        message = video_too_long_message()
        self.assertIn("30 minutes", message)
        self.assertNotIn("This video is", message)

    @patch("src.media_import.has_ffmpeg", return_value=True)
    @patch("src.media_import.subprocess.run")
    def test_probe_video_file_parses_ffprobe_json(
        self,
        mock_run,
        _mock_has_ffmpeg,
    ) -> None:
        """
        Ensures ffprobe JSON output is converted into width/height/duration.
        """

        mock_run.return_value.stdout = json.dumps(
            {
                "streams": [{"width": 1280, "height": 720}],
                "format": {"duration": "12.5"},
            }
        )
        mock_run.return_value.returncode = 0

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_file:
            probe = probe_video_file(tmp_file.name)

        self.assertEqual(
            probe,
            VideoFileProbe(width=1280, height=720, duration_ms=12500),
        )


if __name__ == "__main__":
    unittest.main()
