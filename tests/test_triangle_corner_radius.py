"""
Tests for rounded triangle corners and the shared rounded-polygon helper.
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPixmap

from src.shape_items import (
    PathShapeItem,
    build_rect_path,
    build_rounded_polygon_path,
    build_triangle_path,
    path_for_shape_kind,
)
from tests.qt_test_utils import ensure_qapp


def polygon_area(path) -> float:
    """
    Computes the enclosed area of a painter path via its fill polygon.

    Args:
        path: Painter path to measure.

    Returns:
        float: Absolute enclosed area.
    """

    polygon = path.toFillPolygon()
    total = 0.0
    count = polygon.count()
    for index in range(count):
        current = polygon.at(index)
        following = polygon.at((index + 1) % count)
        total += current.x() * following.y() - following.x() * current.y()
    return abs(total) / 2.0


class TriangleCornerRadiusTests(unittest.TestCase):
    """
    Class TriangleCornerRadiusTests

    Covers rounding geometry, clamping, and the sharp-corner fallback.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        self.rect = QRectF(0.0, 0.0, 200.0, 150.0)

    def test_zero_radius_keeps_three_straight_edges(self) -> None:
        """
        Returns:
            None
        """

        path = build_triangle_path(self.rect, corner_radius=0.0)
        self.assertEqual(path.elementCount(), 4)

    def test_default_call_is_still_sharp(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(build_triangle_path(self.rect).elementCount(), 4)

    def test_rounding_adds_arc_elements(self) -> None:
        """
        Returns:
            None
        """

        self.assertGreater(
            build_triangle_path(self.rect, corner_radius=15.0).elementCount(),
            build_triangle_path(self.rect, corner_radius=0.0).elementCount(),
        )

    def test_rounding_shrinks_area_monotonically(self) -> None:
        """
        Returns:
            None
        """

        areas = [
            polygon_area(build_triangle_path(self.rect, corner_radius=float(radius)))
            for radius in (0, 10, 25, 50)
        ]
        self.assertEqual(areas, sorted(areas, reverse=True))

    def test_rounded_triangle_stays_inside_its_bounding_rect(self) -> None:
        """
        Returns:
            None
        """

        bounds = build_triangle_path(self.rect, corner_radius=40.0).boundingRect()
        self.assertGreaterEqual(bounds.left(), self.rect.left() - 0.5)
        self.assertGreaterEqual(bounds.top(), self.rect.top() - 0.5)
        self.assertLessEqual(bounds.right(), self.rect.right() + 0.5)
        self.assertLessEqual(bounds.bottom(), self.rect.bottom() + 0.5)

    def test_excessive_radius_saturates_instead_of_collapsing(self) -> None:
        """
        Returns:
            None
        """

        saturated = polygon_area(build_triangle_path(self.rect, corner_radius=100.0))
        absurd = polygon_area(build_triangle_path(self.rect, corner_radius=9999.0))
        self.assertAlmostEqual(saturated, absurd, delta=1.0)
        self.assertGreater(absurd, 0.0)

    def test_degenerate_rect_yields_empty_path(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(
            build_triangle_path(QRectF(0.0, 0.0, 0.2, 0.2), corner_radius=5.0).elementCount(),
            0,
        )

    def test_shape_kind_dispatch_passes_radius_to_triangle(self) -> None:
        """
        Returns:
            None
        """

        sharp = path_for_shape_kind("triangle", self.rect, corner_radius=0.0)
        rounded = path_for_shape_kind("triangle", self.rect, corner_radius=20.0)
        self.assertNotEqual(sharp.elementCount(), rounded.elementCount())

    def test_helper_matches_qt_rounded_rect_for_a_square(self) -> None:
        """
        The helper must produce the same arcs as addRoundedRect, otherwise a
        rectangle and a triangle would look different at the same radius.

        Returns:
            None
        """

        square = [
            QPointF(0.0, 0.0),
            QPointF(100.0, 0.0),
            QPointF(100.0, 100.0),
            QPointF(0.0, 100.0),
        ]
        mine = polygon_area(build_rounded_polygon_path(square, 20.0))
        qt_native = polygon_area(build_rect_path(QRectF(0.0, 0.0, 100.0, 100.0), corner_radius=20.0))
        self.assertAlmostEqual(mine, qt_native, delta=1.0)

    def test_helper_rejects_degenerate_point_counts(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(build_rounded_polygon_path([], 10.0).elementCount(), 0)
        self.assertEqual(
            build_rounded_polygon_path([QPointF(0.0, 0.0), QPointF(10.0, 0.0)], 10.0).elementCount(),
            0,
        )

    def test_helper_with_zero_radius_keeps_vertex_count(self) -> None:
        """
        Returns:
            None
        """

        square = [
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(10.0, 10.0),
            QPointF(0.0, 10.0),
        ]
        self.assertEqual(build_rounded_polygon_path(square, 0.0).elementCount(), 5)

    def test_sharper_corner_pulls_its_arc_further_from_the_vertex(self) -> None:
        """
        An arc of a given radius sits further from a sharp vertex than from a
        blunt one, because the run-up is ``r / tan(angle/2)``. A tall thin
        triangle therefore loses much more of its tip at the same radius --
        the same behaviour vector editors show, not a clamping bug.

        Returns:
            None
        """

        wide = build_triangle_path(QRectF(0.0, 0.0, 300.0, 100.0), corner_radius=20.0)
        narrow = build_triangle_path(QRectF(0.0, 0.0, 60.0, 300.0), corner_radius=20.0)
        self.assertGreater(wide.elementCount(), 0)
        self.assertGreater(narrow.elementCount(), 0)
        self.assertGreater(narrow.boundingRect().top(), wide.boundingRect().top())

    def test_blunt_neighbour_lends_edge_room_to_a_sharp_corner(self) -> None:
        """
        Two corners share an edge, so the constraint is that their combined
        run-ups fit inside it -- not that each stays under half of it. Capping
        at half would clamp a sharp apex even when its blunt neighbours leave
        plenty of the edge unused.

        Returns:
            None
        """

        rect = QRectF(0.0, 0.0, 60.0, 300.0)
        # The apex needs a run-up well past half the slant edge; a half-edge cap
        # would stop it short and leave the tip visibly less rounded.
        generous = build_triangle_path(rect, corner_radius=20.0)
        self.assertGreater(generous.boundingRect().top(), 150.0)


class TriangleRadiusApplyTests(unittest.TestCase):
    """
    Class TriangleRadiusApplyTests

    Covers the whole chain from the Edit panel slider down to the shape, which
    is where a rounded-triangle path that builds correctly can still look like
    "the slider does nothing".
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        from src.editor_window import EditorWindow

        pixmap = QPixmap(600, 400)
        pixmap.fill(QColor("#FFFFFF"))
        self.window = EditorWindow(pixmap)

    def tearDown(self) -> None:
        """
        Returns:
            None
        """

        self.window.close()

    def _selected_shape(self, kind: str) -> PathShapeItem:
        """
        Adds one registered, selected shape of the given kind to the canvas.

        Args:
            kind: Annotation type to create.

        Returns:
            PathShapeItem: The selected item.
        """

        from src.annotation_items import configure_graphics_item

        item = PathShapeItem(kind, QRectF(0.0, 0.0, 200.0, 150.0))
        self.window.canvas._scene.addItem(item)  # pylint: disable=protected-access
        configure_graphics_item(item, kind)
        item.setSelected(True)
        return item

    def test_slider_change_reaches_a_selected_triangle(self) -> None:
        """
        Returns:
            None
        """

        item = self._selected_shape("triangle")
        before = item.path().elementCount()
        self.window.canvas.set_rect_corner_radius(
            20.0, apply_to_selection=True, update_default=False, emit_history=False
        )
        self.assertEqual(item.corner_radius(), 20.0)
        self.assertGreater(item.path().elementCount(), before)

    def test_slider_change_still_reaches_a_selected_rectangle(self) -> None:
        """
        Returns:
            None
        """

        item = self._selected_shape("rect")
        before = item.path().elementCount()
        self.window.canvas.set_rect_corner_radius(
            20.0, apply_to_selection=True, update_default=False, emit_history=False
        )
        self.assertEqual(item.corner_radius(), 20.0)
        self.assertGreater(item.path().elementCount(), before)

    def test_triangle_radius_survives_a_save_load_roundtrip(self) -> None:
        """
        Returns:
            None
        """

        from src.annotation_items import add_annotation_to_scene, annotation_from_item
        from src.editor_canvas import ITEM_ROLE_TYPE

        item = self._selected_shape("triangle")
        item.set_corner_radius(25.0)
        model = annotation_from_item(item)
        self.assertEqual(model.payload.get("corner_radius"), 25.0)

        restored = add_annotation_to_scene(
            self.window.canvas._scene, model  # pylint: disable=protected-access
        )
        self.assertEqual(restored.corner_radius(), 25.0)
        self.assertEqual(str(restored.data(ITEM_ROLE_TYPE)), "triangle")


class TriangleRadiusToolbarTests(unittest.TestCase):
    """
    Class TriangleRadiusToolbarTests

    Covers the Edit panel exposing the radius control for triangles.
    """

    def test_both_editors_offer_radius_for_triangle(self) -> None:
        """
        Returns:
            None
        """

        from src.editor_window import _SHAPE_RADIUS_SELECTION_TYPES as image_types
        from src.video_vector_toolbar import _SHAPE_RADIUS_SELECTION_TYPES as video_types

        self.assertIn("triangle", image_types)
        self.assertIn("triangle", video_types)
        self.assertEqual(image_types, video_types)


if __name__ == "__main__":
    unittest.main()
