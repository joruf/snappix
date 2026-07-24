"""
Tests for new vector shape annotations and speech-bubble geometry.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import QGraphicsScene

    from src.annotation_items import (
        DoubleArrowItem,
        add_annotation_to_scene,
        annotation_from_item,
        configure_graphics_item,
    )
    from src.annotation_shapes import TEXT_STYLE_BUBBLE, StyledTextItem
    from src.models import AnnotationModel
    from src.shape_items import (
        PathShapeItem,
        PolyPathItem,
        SpotlightItem,
        build_triangle_path,
        points_to_payload,
    )
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for shape annotation tests")
class TestShapeAnnotations(unittest.TestCase):
    """
    Verifies new drawing shapes serialize, restore, and render correctly.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_triangle_path_has_three_corners(self) -> None:
        """
        Ensures triangle geometry exposes three distinct vertices.
        """

        path = build_triangle_path(QRectF(0.0, 0.0, 100.0, 80.0))
        self.assertFalse(path.isEmpty())
        self.assertGreaterEqual(path.elementCount(), 3)

    def test_path_shape_roundtrips(self) -> None:
        """
        Ensures rect-like path shapes survive serialize/restore.
        """

        scene = QGraphicsScene()
        for kind in ("triangle", "round_rect", "star", "highlight", "cross", "checkmark"):
            with self.subTest(kind=kind):
                model = AnnotationModel(
                    annotation_type=kind,
                    x=12.0,
                    y=18.0,
                    width=60.0,
                    height=40.0,
                    stroke_rgba=[200, 40, 40, 255],
                    fill_rgba=[200, 40, 40, 90],
                    stroke_width=3.0,
                )
                item = add_annotation_to_scene(scene, model)
                self.assertIsInstance(item, PathShapeItem)
                restored = annotation_from_item(item)
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertEqual(restored.annotation_type, kind)
                self.assertAlmostEqual(restored.width, 60.0, places=1)
                self.assertAlmostEqual(restored.height, 40.0, places=1)

    def test_double_arrow_roundtrip(self) -> None:
        """
        Ensures double-headed arrows serialize and restore.
        """

        scene = QGraphicsScene()
        item = DoubleArrowItem(10.0, 10.0, 80.0, 40.0)
        configure_graphics_item(item, "double_arrow")
        scene.addItem(item)
        model = annotation_from_item(item)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.annotation_type, "double_arrow")
        restored = add_annotation_to_scene(scene, model)
        self.assertIsInstance(restored, DoubleArrowItem)

    def test_polygon_and_bent_arrow_roundtrip(self) -> None:
        """
        Ensures multi-point path annotations keep their vertices.
        """

        scene = QGraphicsScene()
        points = [QPointF(10.0, 10.0), QPointF(40.0, 15.0), QPointF(35.0, 50.0)]
        for kind in ("polyline", "polygon", "bent_arrow"):
            with self.subTest(kind=kind):
                model = AnnotationModel(
                    annotation_type=kind,
                    x=10.0,
                    y=10.0,
                    width=30.0,
                    height=40.0,
                    stroke_rgba=[20, 20, 20, 255],
                    fill_rgba=[20, 20, 20, 40] if kind == "polygon" else [0, 0, 0, 0],
                    stroke_width=3.0,
                    payload={"points": points_to_payload(points)},
                )
                item = add_annotation_to_scene(scene, model)
                self.assertIsInstance(item, PolyPathItem)
                restored = annotation_from_item(item)
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertEqual(restored.annotation_type, kind)
                self.assertEqual(len(restored.payload.get("points", [])), 3)

    def test_spotlight_roundtrip_without_recursion(self) -> None:
        """
        Ensures spotlight restores and reports a finite bounding rect.
        """

        scene = QGraphicsScene()
        scene.setSceneRect(0.0, 0.0, 400.0, 300.0)
        model = AnnotationModel(
            annotation_type="spotlight",
            x=40.0,
            y=50.0,
            width=80.0,
            height=60.0,
            stroke_rgba=[241, 196, 15, 255],
            fill_rgba=[0, 0, 0, 150],
            stroke_width=2.0,
            payload={"focus_mode": "ellipse", "dim_alpha": 150},
        )
        item = add_annotation_to_scene(scene, model)
        self.assertIsInstance(item, SpotlightItem)
        bounds = item.boundingRect()
        self.assertGreater(bounds.width(), 0.0)
        self.assertGreater(bounds.height(), 0.0)
        restored = annotation_from_item(item)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.annotation_type, "spotlight")
        self.assertEqual(restored.payload.get("focus_mode"), "ellipse")

    def test_speech_bubble_tail_is_below_text(self) -> None:
        """
        Ensures speech-bubble geometry keeps text above a distinct tail.
        """

        font = QFont()
        font.setPointSize(16)
        item = StyledTextItem(
            text="Hello",
            text_style=TEXT_STYLE_BUBBLE,
            font=font,
            text_color=QColor(20, 20, 20, 255),
            fill_color=QColor(255, 255, 255, 255),
            stroke_color=QColor(40, 40, 40, 255),
            stroke_width=2.0,
        )
        bounds = item.boundingRect()
        text_bottom = item._text_rect.bottom()  # pylint: disable=protected-access
        self.assertGreater(bounds.bottom(), text_bottom + 8.0)
        path = item._container_path()  # pylint: disable=protected-access
        self.assertFalse(path.isEmpty())
        # Path bounds must extend below the text box for the tail.
        self.assertGreater(path.boundingRect().bottom(), text_bottom + 5.0)
        # Body must still cover the text area (not shrunk into it).
        self.assertLessEqual(path.boundingRect().top(), item._text_rect.top())  # pylint: disable=protected-access
