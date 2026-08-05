"""
Regression tests for the short dashed copy-feedback outline on Ctrl+C.

These must stay green so a future copy-path change cannot silently drop the
animated frame around the copied place again.
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsItem

from src.annotation_items import add_annotation_to_scene
from src.editor_window import EditorWindow
from src.models import AnnotationModel
from tests.qt_test_utils import ensure_qapp


def _editor(width: int = 320, height: int = 240) -> EditorWindow:
    """
    Builds one editor tab with a solid background.

    Args:
        width: Document width.
        height: Document height.

    Returns:
        EditorWindow: Fresh editor window.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(240, 240, 240))
    return EditorWindow(pixmap)


def _add_rect(window: EditorWindow, x: float, y: float) -> QGraphicsItem:
    """
    Adds one selectable rectangle annotation.

    Args:
        window: Target editor.
        x: Scene X.
        y: Scene Y.

    Returns:
        QGraphicsItem: Created item.
    """

    item = add_annotation_to_scene(
        window.canvas.scene(),
        AnnotationModel(
            annotation_type="rect",
            x=x,
            y=y,
            width=60.0,
            height=40.0,
            stroke_rgba=[220, 40, 40, 255],
            fill_rgba=[220, 40, 40, 60],
            stroke_width=2.0,
        ),
    )
    assert item is not None
    return item


def _assert_active_dashed_feedback(test: unittest.TestCase, window: EditorWindow) -> None:
    """
    Asserts the copy-feedback frame is visible, dashed, and animating.

    Args:
        test: Active test case.
        window: Editor under test.

    Returns:
        None
    """

    feedback = window.canvas._copy_feedback_item  # pylint: disable=protected-access
    test.assertIsNotNone(feedback)
    assert feedback is not None
    test.assertTrue(feedback.isVisible())
    test.assertTrue(window.canvas._copy_feedback_timer.isActive())  # pylint: disable=protected-access
    pen = feedback.pen()
    # setDashPattern() makes Qt report CustomDashLine rather than DashLine.
    test.assertIn(pen.style(), {Qt.PenStyle.DashLine, Qt.PenStyle.CustomDashLine})
    test.assertGreaterEqual(len(pen.dashPattern()), 2)
    test.assertGreater(pen.widthF(), 0.0)


class TestCopyFeedback(unittest.TestCase):
    """
    Verifies Ctrl+C always shows the temporary dashed copy outline.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for graphics widgets.
        """

        cls._app = ensure_qapp()

    def tearDown(self) -> None:
        """
        Closes the editor created by each test.
        """

        window = getattr(self, "_window", None)
        if window is not None:
            window.canvas.clear_copy_feedback()
            window.close()

    def test_ctrl_c_pixel_selection_shows_dashed_feedback(self) -> None:
        """
        Ensures the Ctrl+C entry point flashes around a marked region.

        This is the path that previously dropped the animation when cutout
        copy was added.
        """

        self._window = _editor()
        path = QPainterPath()
        path.addRect(QRectF(40.0, 50.0, 90.0, 70.0))
        self._window.canvas.set_pixel_selection_path(path)

        self._window.copy_current_image_to_clipboard()

        _assert_active_dashed_feedback(self, self._window)
        feedback = self._window.canvas._copy_feedback_item  # pylint: disable=protected-access
        assert feedback is not None
        self.assertTrue(feedback.rect().contains(QRectF(40.0, 50.0, 90.0, 70.0)))

    def test_ctrl_c_selected_annotation_shows_dashed_feedback(self) -> None:
        """
        Ensures copying a selected drawn object flashes around that object.
        """

        self._window = _editor()
        item = _add_rect(self._window, 30.0, 40.0)
        self._window.canvas.scene().clearSelection()
        item.setSelected(True)

        self._window.copy_current_image_to_clipboard()

        _assert_active_dashed_feedback(self, self._window)
        feedback = self._window.canvas._copy_feedback_item  # pylint: disable=protected-access
        assert feedback is not None
        self.assertTrue(feedback.rect().contains(QRectF(30.0, 40.0, 60.0, 40.0)))

    def test_ctrl_c_full_drawing_area_shows_dashed_feedback(self) -> None:
        """
        Ensures copying the whole tab without a selection still flashes.
        """

        self._window = _editor(200, 150)
        self._window.canvas.scene().clearSelection()
        self._window.canvas.clear_pixel_selection()

        self._window.copy_current_image_to_clipboard()

        _assert_active_dashed_feedback(self, self._window)
        feedback = self._window.canvas._copy_feedback_item  # pylint: disable=protected-access
        assert feedback is not None
        document = self._window.canvas.document_rect()
        self.assertTrue(feedback.rect().contains(document))

    def test_copy_drawing_area_menu_action_shows_dashed_feedback(self) -> None:
        """
        Ensures Edit → Copy Drawing Area also flashes the document frame.
        """

        self._window = _editor(180, 120)
        self._window.copy_drawing_area_to_clipboard()

        _assert_active_dashed_feedback(self, self._window)
        feedback = self._window.canvas._copy_feedback_item  # pylint: disable=protected-access
        assert feedback is not None
        self.assertTrue(feedback.rect().contains(self._window.canvas.document_rect()))

    def test_selected_annotations_preferred_over_pixel_selection(self) -> None:
        """
        Ensures Ctrl+C prefers a selected object over a leftover pixel mark,
        and still flashes around that object.
        """

        self._window = _editor()
        item = _add_rect(self._window, 20.0, 25.0)
        path = QPainterPath()
        path.addRect(QRectF(100.0, 100.0, 50.0, 40.0))
        self._window.canvas.set_pixel_selection_path(path)
        self._window.canvas.scene().clearSelection()
        item.setSelected(True)

        self._window.copy_current_image_to_clipboard()

        _assert_active_dashed_feedback(self, self._window)
        feedback = self._window.canvas._copy_feedback_item  # pylint: disable=protected-access
        assert feedback is not None
        self.assertTrue(feedback.rect().contains(QRectF(20.0, 25.0, 60.0, 40.0)))
        # Must not hug the leftover pixel selection instead.
        self.assertFalse(feedback.rect().contains(QRectF(100.0, 100.0, 50.0, 40.0)))

    def test_copy_feedback_dash_offset_advances_while_running(self) -> None:
        """
        Ensures the marching-ants timer actually animates the dashed pen.
        """

        self._window = _editor()
        self._window.canvas.flash_copy_feedback(QRectF(10.0, 10.0, 40.0, 30.0))
        feedback = self._window.canvas._copy_feedback_item  # pylint: disable=protected-access
        assert feedback is not None
        before = feedback.pen().dashOffset()

        self._window.canvas._on_copy_feedback_tick()  # pylint: disable=protected-access

        after = feedback.pen().dashOffset()
        self.assertGreater(after, before)

    def test_copy_feedback_clears_after_animation_ticks(self) -> None:
        """
        Ensures the outline removes itself after the short animation window.
        """

        self._window = _editor()
        self._window.canvas.flash_copy_feedback(QRectF(10.0, 10.0, 40.0, 30.0))
        self.assertIsNotNone(self._window.canvas._copy_feedback_item)  # pylint: disable=protected-access

        for _ in range(40):
            self._window.canvas._on_copy_feedback_tick()  # pylint: disable=protected-access

        self.assertIsNone(self._window.canvas._copy_feedback_item)  # pylint: disable=protected-access
        self.assertFalse(self._window.canvas._copy_feedback_timer.isActive())  # pylint: disable=protected-access

    def test_degenerate_rect_does_not_create_feedback(self) -> None:
        """
        Ensures empty or tiny target rectangles never leave a stuck overlay.
        """

        self._window = _editor()
        self._window.canvas.flash_copy_feedback(QRectF())
        self.assertIsNone(self._window.canvas._copy_feedback_item)  # pylint: disable=protected-access

        self._window.canvas.flash_copy_feedback(QRectF(5.0, 5.0, 0.5, 10.0))
        self.assertIsNone(self._window.canvas._copy_feedback_item)  # pylint: disable=protected-access

    def test_new_flash_replaces_previous_feedback(self) -> None:
        """
        Ensures a second copy replaces the previous outline instead of stacking.
        """

        self._window = _editor()
        self._window.canvas.flash_copy_feedback(QRectF(10.0, 10.0, 40.0, 30.0))
        first = self._window.canvas._copy_feedback_item  # pylint: disable=protected-access
        self.assertIsNotNone(first)

        self._window.canvas.flash_copy_feedback(QRectF(80.0, 60.0, 50.0, 40.0))
        second = self._window.canvas._copy_feedback_item  # pylint: disable=protected-access
        self.assertIsNotNone(second)
        self.assertIsNot(first, second)
        assert second is not None
        self.assertTrue(second.rect().contains(QRectF(80.0, 60.0, 50.0, 40.0)))
        self.assertIsNone(first.scene())


if __name__ == "__main__":
    unittest.main()
