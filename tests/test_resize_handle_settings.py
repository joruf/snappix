"""
Unit tests for configurable selection resize-handle settings.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.config import (
        DEFAULT_RESIZE_HANDLE_POSITION,
        DEFAULT_RESIZE_HANDLE_SIZE,
        normalize_resize_handle_position,
        normalize_resize_handle_size,
    )
    from src.editor_canvas import EditorCanvas
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from src.video_canvas import VideoCanvas, build_annotation_item
    from src.video_editor_window import VideoEditorWindow
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int) -> QPixmap:
    """
    Creates one opaque white pixmap for canvas tests.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Created pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 255, 255, 255))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for resize handle tests")
class TestResizeHandleConfigNormalization(unittest.TestCase):
    """
    Verifies resize-handle config values are normalized safely.
    """

    def test_normalize_resize_handle_size_clamps_to_supported_range(self) -> None:
        """
        Ensures handle size values stay within 6-24 pixels.
        """

        self.assertEqual(normalize_resize_handle_size(10), 10)
        self.assertEqual(normalize_resize_handle_size(3), 6)
        self.assertEqual(normalize_resize_handle_size(40), 24)
        self.assertEqual(normalize_resize_handle_size("bad"), DEFAULT_RESIZE_HANDLE_SIZE)

    def test_normalize_resize_handle_position_falls_back_to_default(self) -> None:
        """
        Ensures unknown placement keys fall back to the default position.
        """

        self.assertEqual(normalize_resize_handle_position("inside"), "inside")
        self.assertEqual(normalize_resize_handle_position("outside"), "outside")
        self.assertEqual(normalize_resize_handle_position("center"), "center")
        self.assertEqual(
            normalize_resize_handle_position("unknown"),
            DEFAULT_RESIZE_HANDLE_POSITION,
        )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for resize handle tests")
class TestEditorCanvasResizeHandleSettings(unittest.TestCase):
    """
    Verifies image-editor canvas overlays honor configured handle settings.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for graphics tests.
        """

        ensure_qapp()

    def _canvas_with_rect(self) -> tuple[EditorCanvas, object]:
        """
        Creates one canvas with a single selected rectangle annotation.

        Returns:
            tuple[EditorCanvas, object]: Canvas and selected scene item.
        """

        annotation = AnnotationModel(
            annotation_type="rect",
            x=20.0,
            y=20.0,
            width=40.0,
            height=30.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        canvas = EditorCanvas()
        canvas.set_screenshot(_solid_pixmap(300, 200))
        canvas.load_annotations([annotation])
        item = next(
            candidate
            for candidate in canvas.scene().items()
            if str(candidate.data(1001) or "")
        )
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access
        return canvas, item

    def test_selection_overlay_uses_default_handle_settings(self) -> None:
        """
        Ensures a new resize overlay starts with configured default handle style.
        """

        canvas, _item = self._canvas_with_rect()
        overlay = canvas._resize_overlay_item  # pylint: disable=protected-access
        self.assertIsNotNone(overlay)
        assert overlay is not None
        self.assertEqual(overlay._handle_size, float(DEFAULT_RESIZE_HANDLE_SIZE))  # pylint: disable=protected-access
        self.assertEqual(
            overlay._handle_position,  # pylint: disable=protected-access
            DEFAULT_RESIZE_HANDLE_POSITION,
        )

    def test_set_resize_handle_style_updates_existing_overlay(self) -> None:
        """
        Ensures live handle-style changes apply to the active selection overlay.
        """

        canvas, _item = self._canvas_with_rect()
        canvas.set_resize_handle_style(size=8, position="outside")
        overlay = canvas._resize_overlay_item  # pylint: disable=protected-access
        self.assertIsNotNone(overlay)
        assert overlay is not None
        self.assertEqual(overlay._handle_size, 8.0)  # pylint: disable=protected-access
        self.assertEqual(overlay._handle_position, "outside")  # pylint: disable=protected-access
        top_handle = overlay._handle_rects()["top"]  # pylint: disable=protected-access
        self.assertAlmostEqual(top_handle.y(), -8.0)

    def test_set_resize_handle_style_before_selection_applies_on_overlay_create(self) -> None:
        """
        Ensures handle settings configured before selection are used by the overlay.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_solid_pixmap(300, 200))
        canvas.set_resize_handle_style(size=12, position="inside")
        annotation = AnnotationModel(
            annotation_type="rect",
            x=10.0,
            y=10.0,
            width=30.0,
            height=20.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        canvas.load_annotations([annotation])
        item = next(
            candidate
            for candidate in canvas.scene().items()
            if str(candidate.data(1001) or "")
        )
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access
        overlay = canvas._resize_overlay_item  # pylint: disable=protected-access
        self.assertIsNotNone(overlay)
        assert overlay is not None
        self.assertEqual(overlay._handle_size, 12.0)  # pylint: disable=protected-access
        self.assertEqual(overlay._handle_position, "inside")  # pylint: disable=protected-access


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for resize handle tests")
class TestVideoCanvasResizeHandleSettings(unittest.TestCase):
    """
    Verifies video-editor canvas overlays honor configured handle settings.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for graphics tests.
        """

        ensure_qapp()

    def _canvas_with_rect(self) -> VideoCanvas:
        """
        Creates one video canvas with a visible selected rectangle annotation.

        Returns:
            VideoCanvas: Configured canvas with active overlay.
        """

        annotation = VideoAnnotationModel(
            annotation_type="rect",
            start_ms=0,
            end_ms=5000,
            x=40.0,
            y=30.0,
            width=120.0,
            height=80.0,
            stroke_rgba=[231, 76, 60, 255],
            fill_rgba=[231, 76, 60, 70],
            stroke_width=3.0,
        )
        canvas = VideoCanvas()
        canvas.set_video_size(320, 240)
        canvas.set_annotations([annotation])
        item = build_annotation_item(annotation)
        assert item is not None
        canvas.scene().addItem(item)
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access
        return canvas

    def test_video_overlay_applies_handle_style(self) -> None:
        """
        Ensures the video canvas resize overlay uses updated handle settings.
        """

        canvas = self._canvas_with_rect()
        canvas.set_resize_handle_style(size=9, position="center")
        overlay = canvas._resize_overlay_item  # pylint: disable=protected-access
        self.assertIsNotNone(overlay)
        assert overlay is not None
        self.assertEqual(overlay._handle_size, 9.0)  # pylint: disable=protected-access
        self.assertEqual(overlay._handle_position, "center")  # pylint: disable=protected-access
        top_handle = overlay._handle_rects()["top"]  # pylint: disable=protected-access
        self.assertAlmostEqual(top_handle.y(), -4.5)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for resize handle tests")
class TestEditorWindowResizeHandleSettings(unittest.TestCase):
    """
    Verifies editor shells delegate handle settings to their canvases.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for editor window tests.
        """

        ensure_qapp()

    def test_image_editor_window_forwards_handle_style(self) -> None:
        """
        Ensures the image editor applies handle settings through its canvas.
        """

        editor = EditorWindow(_solid_pixmap(200, 150))
        editor.set_resize_handle_style(size=11, position="outside")
        self.assertEqual(editor.canvas._resize_handle_size, 11.0)  # pylint: disable=protected-access
        self.assertEqual(
            editor.canvas._resize_handle_position,  # pylint: disable=protected-access
            "outside",
        )

    def test_video_editor_window_forwards_handle_style(self) -> None:
        """
        Ensures the video editor applies handle settings through its canvas.
        """

        editor = VideoEditorWindow("missing.mp4", 320, 240)
        editor.set_resize_handle_style(size=7, position="inside")
        self.assertEqual(editor.canvas._resize_handle_size, 7.0)  # pylint: disable=protected-access
        self.assertEqual(
            editor.canvas._resize_handle_position,  # pylint: disable=protected-access
            "inside",
        )


if __name__ == "__main__":
    unittest.main()
