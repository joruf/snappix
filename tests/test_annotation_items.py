"""
Unit tests for annotation conversion helpers.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPixmap
    from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene

    from src.annotation_items import (
        ITEM_ROLE_TYPE,
        StyleState,
        add_annotation_to_scene,
        annotation_from_item,
        color_to_list,
        configure_graphics_item,
        create_pen,
        list_to_color,
        normalize_stroke_style,
        stroke_style_to_qt,
        STROKE_STYLE_DASH,
        STROKE_STYLE_DOT,
        STROKE_STYLE_SOLID,
    )
    from src.models import AnnotationModel
    from src.storage import pixmap_to_base64_png
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _make_pixmap_base64() -> str:
    """
    Creates a tiny PNG payload for image annotation tests.

    Returns:
        str: Base64 PNG bytes.
    """

    image = QImage(3, 4, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 0, 0, 255))
    return pixmap_to_base64_png(QPixmap.fromImage(image))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for annotation GUI tests")
class TestAnnotationItems(unittest.TestCase):
    """
    Verifies annotation utility and reconstruction behavior.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for graphics types.
        """

        cls._app = ensure_qapp()

    def test_color_list_roundtrip(self) -> None:
        """
        Ensures color conversion preserves RGBA channels.
        """

        color = QColor(11, 22, 33, 44)
        self.assertEqual(color_to_list(color), [11, 22, 33, 44])
        restored = list_to_color([11, 22, 33, 44])
        self.assertEqual(restored.red(), 11)
        self.assertEqual(restored.green(), 22)
        self.assertEqual(restored.blue(), 33)
        self.assertEqual(restored.alpha(), 44)

    def test_list_to_color_invalid_values_returns_default_red(self) -> None:
        """
        Ensures invalid color payload falls back to opaque red.
        """

        fallback = list_to_color([1, 2, 3])
        self.assertEqual((fallback.red(), fallback.green(), fallback.blue(), fallback.alpha()), (255, 0, 0, 255))

    def test_create_pen_uses_style_values(self) -> None:
        """
        Ensures pen creation uses configured stroke attributes.
        """

        style = StyleState(
            stroke_color=QColor(40, 50, 60, 255),
            fill_color=QColor(1, 2, 3, 4),
            text_color=QColor(4, 3, 2, 255),
            stroke_width=5.0,
            font_size=16,
            font_family="Sans Serif",
            font_bold=False,
            font_italic=False,
            font_underline=False,
        )
        pen = create_pen(style)
        self.assertEqual(pen.widthF(), 5.0)
        self.assertEqual(pen.color().red(), 40)
        self.assertFalse(pen.isCosmetic())

    def test_configure_graphics_item_sets_flags_and_type(self) -> None:
        """
        Ensures generic item flags and metadata are configured.
        """

        item = QGraphicsRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
        configure_graphics_item(item, "rect")
        self.assertTrue(item.flags() & item.GraphicsItemFlag.ItemIsSelectable)
        self.assertTrue(item.flags() & item.GraphicsItemFlag.ItemIsMovable)
        self.assertEqual(item.data(ITEM_ROLE_TYPE), "rect")

    def test_annotation_from_text_item_includes_font_family(self) -> None:
        """
        Ensures text annotation serialization carries font fields.
        """

        scene = QGraphicsScene()
        text_item = scene.addText("hello")
        font = QFont(text_item.font())
        font.setPointSize(21)
        font.setFamily("DejaVu Sans")
        font.setBold(True)
        font.setItalic(True)
        font.setUnderline(True)
        text_item.setFont(font)
        text_item.setDefaultTextColor(QColor(7, 8, 9, 255))
        text_item.setPos(4.0, 6.0)
        configure_graphics_item(text_item, "text")

        annotation = annotation_from_item(text_item)
        self.assertIsNotNone(annotation)
        assert annotation is not None
        self.assertEqual(annotation.annotation_type, "text")
        self.assertEqual(annotation.text, "hello")
        self.assertEqual(annotation.font_size, 21)
        self.assertEqual(annotation.font_family, "DejaVu Sans")
        self.assertTrue(annotation.font_bold)
        self.assertTrue(annotation.font_italic)
        self.assertTrue(annotation.font_underline)
        self.assertEqual(annotation.stroke_rgba, [7, 8, 9, 255])

    def test_add_annotation_to_scene_creates_text_with_font_family(self) -> None:
        """
        Ensures scene reconstruction applies text style fields.
        """

        scene = QGraphicsScene()
        annotation = AnnotationModel(
            annotation_type="text",
            x=1.0,
            y=2.0,
            width=0.0,
            height=0.0,
            stroke_rgba=[1, 2, 3, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=1.0,
            text="unit",
            font_size=19,
            font_family="DejaVu Sans Mono",
        )
        item = add_annotation_to_scene(scene, annotation)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.data(ITEM_ROLE_TYPE), "text")
        self.assertEqual(item.font().pointSize(), 19)
        self.assertEqual(item.font().family(), "DejaVu Sans Mono")

    def test_add_annotation_to_scene_creates_image_item(self) -> None:
        """
        Ensures image annotation payload is decoded into scene item.
        """

        scene = QGraphicsScene()
        encoded = _make_pixmap_base64()
        annotation = AnnotationModel(
            annotation_type="image",
            x=10.0,
            y=12.0,
            width=6.0,
            height=8.0,
            stroke_rgba=[0, 0, 0, 0],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=0.0,
            payload={"image_png_base64": encoded},
        )
        item = add_annotation_to_scene(scene, annotation)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.data(ITEM_ROLE_TYPE), "image")
        self.assertEqual(str(item.data(2001)), encoded)

    def test_normalize_stroke_style_falls_back_to_solid(self) -> None:
        """
        Ensures unknown stroke styles default to solid.
        """

        self.assertEqual(normalize_stroke_style("invalid"), STROKE_STYLE_SOLID)
        self.assertEqual(normalize_stroke_style(STROKE_STYLE_DASH), STROKE_STYLE_DASH)

    def test_stroke_style_to_qt_maps_dash_and_dot(self) -> None:
        """
        Ensures stroke style identifiers map to Qt pen styles.
        """

        self.assertEqual(stroke_style_to_qt(STROKE_STYLE_DASH), Qt.PenStyle.DashLine)
        self.assertEqual(stroke_style_to_qt(STROKE_STYLE_DOT), Qt.PenStyle.DotLine)
        self.assertEqual(stroke_style_to_qt(STROKE_STYLE_SOLID), Qt.PenStyle.SolidLine)

    def test_line_annotation_roundtrip_preserves_stroke_style(self) -> None:
        """
        Ensures dashed line annotations serialize stroke style in payload.
        """

        scene = QGraphicsScene()
        annotation = AnnotationModel(
            annotation_type="line",
            x=10.0,
            y=20.0,
            width=80.0,
            height=0.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=2.0,
            payload={"stroke_style": STROKE_STYLE_DASH},
        )
        item = add_annotation_to_scene(scene, annotation)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.pen().style(), Qt.PenStyle.DashLine)

        restored = annotation_from_item(item)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.payload.get("stroke_style"), STROKE_STYLE_DASH)

