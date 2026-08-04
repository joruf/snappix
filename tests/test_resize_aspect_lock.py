"""
Tests for the aspect-ratio lock while dragging a resize handle.

The behaviour these pin: holding the modifier *before* grabbing a corner must
lock the ratio. Reading the modifier live from each move event is what makes
that work -- latching it at press time would only honour a key already down, and
latching it never would only honour one pressed mid-drag.
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent

from src.crop_item import CropSelectionItem, aspect_lock_requested
from tests.qt_test_utils import ensure_qapp

_START = QRectF(0.0, 0.0, 200.0, 100.0)
_START_RATIO = 2.0
_DRAG_TO = QPointF(400.0, 120.0)


class AspectLockModifierTests(unittest.TestCase):
    """
    Class AspectLockModifierTests

    Covers which keys request a proportional resize.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()

    def test_control_requests_the_lock(self) -> None:
        """
        Returns:
            None
        """

        self.assertTrue(aspect_lock_requested(Qt.KeyboardModifier.ControlModifier))

    def test_shift_still_requests_the_lock(self) -> None:
        """
        Shift was the original binding; removing it would break existing habits.

        Returns:
            None
        """

        self.assertTrue(aspect_lock_requested(Qt.KeyboardModifier.ShiftModifier))

    def test_both_together_request_the_lock(self) -> None:
        """
        Returns:
            None
        """

        self.assertTrue(
            aspect_lock_requested(
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            )
        )

    def test_unrelated_modifiers_do_not(self) -> None:
        """
        Returns:
            None
        """

        self.assertFalse(aspect_lock_requested(Qt.KeyboardModifier.AltModifier))
        self.assertFalse(aspect_lock_requested(Qt.KeyboardModifier.NoModifier))


class AspectLockDragTests(unittest.TestCase):
    """
    Class AspectLockDragTests

    Covers the ratio actually being held during a handle drag.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()

    def _drag(self, modifiers) -> QRectF:
        """
        Drags the bottom-right handle with the given modifiers held throughout.

        Args:
            modifiers: Keyboard modifiers present on the move event.

        Returns:
            QRectF: Resulting scene rectangle.
        """

        scene = QGraphicsScene()
        item = CropSelectionItem(QRectF(_START))
        scene.addItem(item)
        item.set_aspect_ratio_lock_enabled(True)

        # Grab the corner, exactly as the press handler does.
        item._active_handle = "bottom_right"  # pylint: disable=protected-access
        item._resizing = True  # pylint: disable=protected-access
        rect = item.scene_rect()
        item._resize_aspect_ratio = rect.width() / rect.height()  # pylint: disable=protected-access

        event = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.Type.GraphicsSceneMouseMove)
        event.setScenePos(_DRAG_TO)
        event.setModifiers(modifiers)
        item.mouseMoveEvent(event)
        return item.scene_rect()

    def test_drag_without_a_modifier_is_free(self) -> None:
        """
        Returns:
            None
        """

        rect = self._drag(Qt.KeyboardModifier.NoModifier)
        self.assertNotAlmostEqual(rect.width() / rect.height(), _START_RATIO, places=2)

    def test_control_held_from_the_start_locks_the_ratio(self) -> None:
        """
        The reported defect: the key had to be pressed after the drag began.
        Holding it before grabbing the corner must work.

        Returns:
            None
        """

        rect = self._drag(Qt.KeyboardModifier.ControlModifier)
        self.assertAlmostEqual(rect.width() / rect.height(), _START_RATIO, places=2)

    def test_shift_held_from_the_start_locks_the_ratio(self) -> None:
        """
        Returns:
            None
        """

        rect = self._drag(Qt.KeyboardModifier.ShiftModifier)
        self.assertAlmostEqual(rect.width() / rect.height(), _START_RATIO, places=2)

    def test_locked_drag_still_grows_the_shape(self) -> None:
        """
        Preserving the ratio must not mean ignoring the drag.

        Returns:
            None
        """

        rect = self._drag(Qt.KeyboardModifier.ControlModifier)
        self.assertGreater(rect.width(), _START.width())
        self.assertGreater(rect.height(), _START.height())

    def test_lock_can_be_disabled_on_the_item(self) -> None:
        """
        Returns:
            None
        """

        scene = QGraphicsScene()
        item = CropSelectionItem(QRectF(_START))
        scene.addItem(item)
        item.set_aspect_ratio_lock_enabled(False)
        item._active_handle = "bottom_right"  # pylint: disable=protected-access
        item._resizing = True  # pylint: disable=protected-access
        item._resize_aspect_ratio = _START_RATIO  # pylint: disable=protected-access

        event = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.Type.GraphicsSceneMouseMove)
        event.setScenePos(_DRAG_TO)
        event.setModifiers(Qt.KeyboardModifier.ControlModifier)
        item.mouseMoveEvent(event)

        rect = item.scene_rect()
        self.assertNotAlmostEqual(rect.width() / rect.height(), _START_RATIO, places=2)


if __name__ == "__main__":
    unittest.main()
