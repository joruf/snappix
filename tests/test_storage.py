"""
Unit tests for project storage helpers.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.constants import APP_FILE_EXTENSION
from src.models import AnnotationModel, ProjectModel

try:
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.storage import (
        base64_png_to_pixmap,
        build_project_model,
        load_project,
        pixmap_to_base64_png,
        save_project,
    )
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int, color: QColor) -> QPixmap:
    """
    Creates a solid color pixmap for test scenarios.

    Args:
        width: Pixmap width in pixels.
        height: Pixmap height in pixels.
        color: Fill color.

    Returns:
        QPixmap: Generated pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color)
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for storage GUI tests")
class TestStorage(unittest.TestCase):
    """
    Verifies serialization and archive read/write behavior.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for pixmap operations.
        """

        cls._app = ensure_qapp()

    def test_pixmap_base64_roundtrip(self) -> None:
        """
        Ensures encoded pixmap can be decoded without size loss.
        """

        source = _solid_pixmap(20, 10, QColor(12, 34, 56, 255))
        encoded = pixmap_to_base64_png(source)
        restored = base64_png_to_pixmap(encoded)

        self.assertEqual(restored.width(), 20)
        self.assertEqual(restored.height(), 10)

    def test_build_project_model_uses_screenshot_geometry(self) -> None:
        """
        Ensures generated project model copies screenshot dimensions.
        """

        source = _solid_pixmap(77, 55, QColor(255, 0, 0, 255))
        model = build_project_model(source, [])

        self.assertEqual(model.canvas_width, 77)
        self.assertEqual(model.canvas_height, 55)
        self.assertTrue(bool(model.screenshot_png_base64))

    def test_save_and_load_project_with_image_asset_payload(self) -> None:
        """
        Ensures image payloads are externalized and restored from ZIP.
        """

        screenshot = _solid_pixmap(16, 16, QColor(0, 128, 255, 255))
        embedded_image = _solid_pixmap(6, 8, QColor(120, 20, 40, 255))
        annotation = AnnotationModel(
            annotation_type="image",
            x=1.0,
            y=2.0,
            width=6.0,
            height=8.0,
            stroke_rgba=[0, 0, 0, 0],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=0.0,
            payload={"image_png_base64": pixmap_to_base64_png(embedded_image)},
        )
        model = build_project_model(screenshot, [annotation])

        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "project_without_extension"
            save_project(target, model)
            archive_path = target.with_suffix(APP_FILE_EXTENSION)
            self.assertTrue(archive_path.exists())

            with zipfile.ZipFile(archive_path, "r") as archive:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                payload = manifest["annotations"][0]["payload"]
                self.assertEqual(payload.get("image_png_base64"), "")
                self.assertTrue(str(payload.get("image_asset_path", "")).startswith("assets/image-"))

            restored = load_project(archive_path)
            self.assertEqual(restored.canvas_width, 16)
            self.assertEqual(restored.canvas_height, 16)
            restored_payload = restored.annotations[0].payload
            self.assertTrue(bool(restored_payload.get("image_png_base64")))
            self.assertIsNone(restored_payload.get("image_asset_path"))

    def test_save_project_creates_missing_parent_directories(self) -> None:
        """
        Ensures project saves create missing parent folders automatically.
        """

        screenshot = _solid_pixmap(12, 12, QColor(255, 255, 255, 255))
        model = build_project_model(screenshot, [])

        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "nested" / "session" / "canvas.sfp"
            save_project(target, model)
            self.assertTrue(target.is_file())

    def test_load_project_supports_legacy_json(self) -> None:
        """
        Ensures JSON-based legacy projects can be loaded.
        """

        model = ProjectModel(
            format_name="snappix-project",
            format_version=2,
            canvas_width=5,
            canvas_height=7,
            screenshot_png_base64="abc",
            annotations=[],
            metadata={},
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "legacy.json"
            path.write_text(json.dumps(model.to_dict()), encoding="utf-8")
            restored = load_project(path)
            self.assertEqual(restored.canvas_width, 5)
            self.assertEqual(restored.canvas_height, 7)

