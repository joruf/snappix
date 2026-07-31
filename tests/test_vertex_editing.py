"""
Tests for dragging individual vertices of multi-point annotations.

Polyline, polygon, and bent arrow all share PolyPathItem, so editing behaves
identically in the image and the video editor.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPointF

    from src.shape_items import (
        VERTEX_GRAB_PADDING_PX,
        VERTEX_HANDLE_PX,
        PolyPathItem,
    )
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


POLY_KINDS = ("polyline", "polygon", "bent_arrow")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for vertex editing tests")
class TestVertexHitTesting(unittest.TestCase):
    """
    Verifies vertex handles can be picked without hitting the wrong one.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _item(self, kind: str = "polyline") -> PolyPathItem:
        return PolyPathItem(
            kind,
            [QPointF(0.0, 0.0), QPointF(50.0, 20.0), QPointF(100.0, 0.0)],
        )

    def test_exact_vertex_position_is_hit(self) -> None:
        """
        Ensures each vertex reports its own index.
        """

        item = self._item()

        self.assertEqual(item.vertex_at(QPointF(0.0, 0.0)), 0)
        self.assertEqual(item.vertex_at(QPointF(50.0, 20.0)), 1)
        self.assertEqual(item.vertex_at(QPointF(100.0, 0.0)), 2)

    def test_near_miss_within_grab_padding_still_hits(self) -> None:
        """
        Ensures the handle is practical to grab, not pixel-exact.
        """

        item = self._item()
        offset = VERTEX_HANDLE_PX + VERTEX_GRAB_PADDING_PX - 1.0

        self.assertEqual(item.vertex_at(QPointF(50.0 + offset, 20.0)), 1)

    def test_far_position_hits_nothing(self) -> None:
        """
        Ensures body clicks are not mistaken for vertex grabs.
        """

        item = self._item()

        self.assertIsNone(item.vertex_at(QPointF(25.0, 200.0)))

    def test_bounding_rect_leaves_room_for_handles(self) -> None:
        """
        Ensures handles are not clipped at the shape's edge.
        """

        item = self._item()
        path_bounds = item.path().boundingRect()

        self.assertLess(item.boundingRect().left(), path_bounds.left())
        self.assertGreater(item.boundingRect().right(), path_bounds.right())


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for vertex editing tests")
class TestVertexMoving(unittest.TestCase):
    """
    Verifies moving one vertex leaves the others untouched.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_moving_a_vertex_changes_only_that_vertex(self) -> None:
        """
        Ensures editing is per-vertex, not a whole-shape transform.
        """

        for kind in POLY_KINDS:
            with self.subTest(kind=kind):
                item = PolyPathItem(
                    kind, [QPointF(0.0, 0.0), QPointF(50.0, 20.0), QPointF(100.0, 0.0)]
                )

                self.assertTrue(item.move_vertex(1, QPointF(60.0, 90.0)))

                points = item.points()
                self.assertEqual((points[0].x(), points[0].y()), (0.0, 0.0))
                self.assertEqual((points[1].x(), points[1].y()), (60.0, 90.0))
                self.assertEqual((points[2].x(), points[2].y()), (100.0, 0.0))

    def test_moving_rebuilds_the_drawn_path(self) -> None:
        """
        Ensures the shape actually redraws, not just its stored points.
        """

        item = PolyPathItem("polyline", [QPointF(0.0, 0.0), QPointF(10.0, 0.0)])
        before = item.path().boundingRect()

        item.move_vertex(1, QPointF(10.0, 120.0))

        self.assertGreater(item.path().boundingRect().height(), before.height())

    def test_out_of_range_index_is_rejected(self) -> None:
        """
        Ensures a stale index cannot corrupt the vertex list.
        """

        item = PolyPathItem("polyline", [QPointF(0.0, 0.0), QPointF(10.0, 0.0)])

        self.assertFalse(item.move_vertex(9, QPointF(5.0, 5.0)))
        self.assertFalse(item.move_vertex(-1, QPointF(5.0, 5.0)))
        self.assertEqual(len(item.points()), 2)

    def test_moving_to_the_same_spot_reports_no_change(self) -> None:
        """
        Ensures redundant drags do not spam history.
        """

        item = PolyPathItem("polyline", [QPointF(0.0, 0.0), QPointF(10.0, 0.0)])

        self.assertFalse(item.move_vertex(1, QPointF(10.0, 0.0)))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for vertex editing tests")
class TestVertexAxisLock(unittest.TestCase):
    """
    Verifies the Shift axis lock during a vertex drag.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_dominant_horizontal_travel_locks_the_y_axis(self) -> None:
        """
        Ensures a mostly sideways drag keeps the original height.
        """

        item = PolyPathItem("polyline", [QPointF(0.0, 0.0)])
        origin = QPointF(10.0, 10.0)

        locked = item.lock_vertex_target(origin, QPointF(90.0, 18.0))

        self.assertEqual((locked.x(), locked.y()), (90.0, 10.0))

    def test_dominant_vertical_travel_locks_the_x_axis(self) -> None:
        """
        Ensures a mostly vertical drag keeps the original x.
        """

        item = PolyPathItem("polyline", [QPointF(0.0, 0.0)])
        origin = QPointF(10.0, 10.0)

        locked = item.lock_vertex_target(origin, QPointF(16.0, 90.0))

        self.assertEqual((locked.x(), locked.y()), (10.0, 90.0))

    def test_lock_never_moves_both_axes(self) -> None:
        """
        Ensures exactly one axis survives the constraint.
        """

        item = PolyPathItem("polyline", [QPointF(0.0, 0.0)])
        origin = QPointF(10.0, 10.0)

        locked = item.lock_vertex_target(origin, QPointF(40.0, 40.0))

        moved_axes = int(locked.x() != origin.x()) + int(locked.y() != origin.y())
        self.assertEqual(moved_axes, 1)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for vertex editing tests")
class TestWholeShapeStillMovable(unittest.TestCase):
    """
    Verifies vertex editing did not take away moving the shape as a whole.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_body_press_does_not_start_a_vertex_drag(self) -> None:
        """
        Ensures pressing away from a handle leaves the vertex drag inactive.
        """

        item = PolyPathItem(
            "polyline", [QPointF(0.0, 0.0), QPointF(100.0, 0.0)]
        )
        item.setSelected(True)

        self.assertIsNone(item.vertex_at(QPointF(50.0, 0.0)))
        self.assertIsNone(item._active_vertex)  # pylint: disable=protected-access

    def test_item_keeps_the_movable_flag(self) -> None:
        """
        Ensures the shape can still be dragged in one piece.
        """

        from PySide6.QtWidgets import QGraphicsItem

        from src.annotation_items import configure_graphics_item

        item = PolyPathItem("polygon", [QPointF(0.0, 0.0), QPointF(10.0, 10.0)])
        configure_graphics_item(item, "polygon")

        self.assertTrue(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


if __name__ == "__main__":
    unittest.main()
