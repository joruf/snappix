"""
Tests for arrow hit-testing and head direction.
"""

from __future__ import annotations

import math
import unittest

try:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPen, QPixmap

    from src.annotation_items import ArrowItem, configure_graphics_item
    from src.editor_canvas import EditorCanvas, Tool
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int) -> QPixmap:
    """
    Creates a solid white pixmap for canvas tests.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Solid pixmap.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(255, 255, 255, 255))
    return pixmap


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for arrow selection tests")
class TestArrowSelection(unittest.TestCase):
    """
    Verifies arrow head orientation and selectable hit areas.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_arrow_head_follows_line_direction(self) -> None:
        """
        Ensures the arrow tip points along p1→p2 for cardinal directions.
        """

        cases = {
            "right": ((10.0, 50.0), (110.0, 50.0), (1.0, 0.0)),
            "left": ((110.0, 50.0), (10.0, 50.0), (-1.0, 0.0)),
            "down": ((50.0, 10.0), (50.0, 110.0), (0.0, 1.0)),
            "up": ((50.0, 110.0), (50.0, 10.0), (0.0, -1.0)),
        }
        for name, (p1, p2, expected) in cases.items():
            with self.subTest(direction=name):
                item = ArrowItem(p1[0], p1[1], p2[0], p2[1])
                item.setPen(QPen(QColor(255, 0, 0, 255), 3.0))
                head = item._arrow_head_path()  # pylint: disable=protected-access
                self.assertFalse(head.isEmpty())
                tip = QPointF(p2[0], p2[1])
                # Centroid of triangle lies behind the tip; tip→centroid is opposite to direction.
                # Use bounding center of the head path relative to tip.
                center = head.boundingRect().center()
                tip_to_center = QPointF(center.x() - tip.x(), center.y() - tip.y())
                length = math.hypot(tip_to_center.x(), tip_to_center.y())
                self.assertGreater(length, 0.1)
                direction = QPointF(tip_to_center.x() / length, tip_to_center.y() / length)
                # Head mass is behind the tip, so tip→center should oppose the shaft direction.
                self.assertLess(
                    direction.x() * expected[0] + direction.y() * expected[1],
                    -0.5,
                    msg=f"{name}: head center not behind tip",
                )

    def test_arrow_shape_hits_near_shaft(self) -> None:
        """
        Ensures clicks slightly off the geometric line still select the arrow.
        """

        item = ArrowItem(20.0, 40.0, 180.0, 40.0)
        item.setPen(QPen(QColor(255, 0, 0, 255), 2.0))
        configure_graphics_item(item, "arrow")
        self.assertTrue(item.contains(QPointF(100.0, 40.0)))
        self.assertTrue(item.contains(QPointF(100.0, 46.0)))
        self.assertTrue(item.contains(QPointF(100.0, 34.0)))

    def test_selected_arrow_shaft_remains_clickable_under_overlay(self) -> None:
        """
        Ensures the resize overlay does not steal shaft clicks on arrows.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_solid_pixmap(240, 160))
        canvas.set_tool(Tool.SELECT)
        model = AnnotationModel(
            annotation_type="arrow",
            x=30.0,
            y=120.0,
            width=160.0,
            height=-80.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=3.0,
        )
        canvas.load_annotations([model])
        items = [
            item
            for item in canvas._annotation_items()  # pylint: disable=protected-access
            if str(item.data(1001) or "") == "arrow"
        ]
        self.assertEqual(len(items), 1)
        arrow = items[0]
        self.assertAlmostEqual(arrow.line().angle(), 26.565, places=2)

        arrow.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access
        overlay = canvas._resize_overlay_item  # pylint: disable=protected-access
        self.assertIsNotNone(overlay)
        assert overlay is not None
        self.assertFalse(overlay._interior_interactive)  # pylint: disable=protected-access

        mid = QPointF(
            (arrow.line().p1().x() + arrow.line().p2().x()) / 2.0,
            (arrow.line().p1().y() + arrow.line().p2().y()) / 2.0,
        )
        hit_items = canvas._scene.items(mid)  # pylint: disable=protected-access
        self.assertTrue(any(item is arrow for item in hit_items))
        # Overlay may still be listed, but shaft clicks must resolve to the arrow.
        top_annotation = next(
            (
                item
                for item in hit_items
                if str(item.data(1001) or "")
            ),
            None,
        )
        self.assertIs(top_annotation, arrow)
