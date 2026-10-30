"""
Tests for the ways of zooming the editors.

Zooming goes with the + and - keys and with the mouse wheel. A touchpad's
two-finger scroll still has to scroll, and Alt+wheel scrolls with a mouse, or
the picture could never be moved once the wheel zooms.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QColor, QPixmap, QWheelEvent
    from PySide6.QtTest import QTest

    from src.editor_window import EditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class ZoomCase(unittest.TestCase):
    """
    Shared setup: an editor showing a picture larger than its viewport.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Opens an editor on a large picture.
        """

        pixmap = QPixmap(1600, 1000)
        pixmap.fill(QColor(255, 255, 255))
        self.editor = EditorWindow(pixmap)
        self.addCleanup(self._dispose, self.editor)
        self.editor.resize(1100, 800)
        self.editor.show()
        # Window shortcuts only fire in the active window; another test's window
        # can hold the activation when the whole suite runs.
        self.editor.activateWindow()
        QTest.qWaitForWindowActive(self.editor)
        self._app.processEvents()
        self.canvas = self.editor.canvas

    def _dispose(self, widget) -> None:
        """
        Closes a window and frees it, so later tests are not slowed down.

        Args:
            widget: Window to dispose.
        """

        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _wheel(self, canvas, delta: int, modifiers=Qt.KeyboardModifier.NoModifier, *, pixels=0):
        """
        Delivers one wheel event to a canvas.

        Args:
            canvas: Canvas to send to.
            delta: Vertical angle delta; 120 is one notch up.
            modifiers: Held keyboard modifiers.
            pixels: Vertical pixel delta; non-zero for a touchpad.
        """

        event = QWheelEvent(
            QPointF(200.0, 150.0),
            QPointF(200.0, 150.0),
            QPoint(0, pixels),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.ScrollUpdate if pixels else Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        self._app.sendEvent(canvas.viewport(), event)

    def _key(self, key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        """
        Presses a key on the canvas.

        Args:
            key: Qt key.
            modifiers: Held keyboard modifiers.
        """

        self.canvas.setFocus()
        QTest.keyClick(self.canvas, key, modifiers)
        self._app.processEvents()


class TestWheelZoom(ZoomCase):
    """
    Verifies the mouse wheel.
    """

    def test_a_plain_wheel_notch_zooms_in(self) -> None:
        """
        Ensures the wheel zooms without any modifier held.
        """

        before = self.canvas._zoom_factor
        self._wheel(self.canvas, 120)
        self.assertGreater(self.canvas._zoom_factor, before)

    def test_a_plain_wheel_notch_back_zooms_out(self) -> None:
        """
        Ensures the wheel works in both directions.
        """

        before = self.canvas._zoom_factor
        self._wheel(self.canvas, -120)
        self.assertLess(self.canvas._zoom_factor, before)

    def test_shift_and_ctrl_still_zoom(self) -> None:
        """
        Ensures the older Shift and Ctrl mappings keep working.
        """

        for modifier in (Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.ControlModifier):
            before = self.canvas._zoom_factor
            self._wheel(self.canvas, 120, modifier)
            self.assertGreater(self.canvas._zoom_factor, before)

    def test_a_touchpad_pinch_reported_as_ctrl_and_wheel_zooms(self) -> None:
        """
        Ensures Ctrl keeps its meaning even when the event carries pixel deltas.
        """

        before = self.canvas._zoom_factor
        self._wheel(self.canvas, 120, Qt.KeyboardModifier.ControlModifier, pixels=30)
        self.assertGreater(self.canvas._zoom_factor, before)

    def test_touchpad_scrolling_scrolls_instead_of_zooming(self) -> None:
        """
        Ensures two-finger scrolling still moves the picture.
        """

        before = self.canvas._zoom_factor
        scroll_before = self.canvas.verticalScrollBar().value()
        self._wheel(self.canvas, -120, pixels=-40)
        self.assertEqual(self.canvas._zoom_factor, before)
        self.assertNotEqual(self.canvas.verticalScrollBar().value(), scroll_before)

    def test_alt_wheel_scrolls_with_a_mouse(self) -> None:
        """
        Ensures a mouse can still scroll the picture.
        """

        before = self.canvas._zoom_factor
        scroll_before = self.canvas.verticalScrollBar().value()
        self._wheel(self.canvas, -120, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.canvas._zoom_factor, before)
        self.assertNotEqual(self.canvas.verticalScrollBar().value(), scroll_before)

    def test_the_wheel_zoom_is_bounded(self) -> None:
        """
        Ensures a long spin cannot leave the supported range.
        """

        for _ in range(200):
            self._wheel(self.canvas, 120)
        self.assertLessEqual(self.canvas._zoom_factor, self.canvas.ZOOM_MAX)
        for _ in range(400):
            self._wheel(self.canvas, -120)
        self.assertGreaterEqual(self.canvas._zoom_factor, self.canvas.ZOOM_MIN)

    def test_the_video_canvas_zooms_with_the_wheel_too(self) -> None:
        """
        Ensures both editors got the same behavior.
        """

        from src.video_canvas import VideoCanvas

        canvas = VideoCanvas()
        self.addCleanup(self._dispose, canvas)
        canvas.resize(400, 300)
        canvas.show()
        self._app.processEvents()

        before = canvas._zoom_factor
        self._wheel(canvas, 120)
        self.assertGreater(canvas._zoom_factor, before)


class TestKeyZoom(ZoomCase):
    """
    Verifies the + and - keys.
    """

    def test_plus_zooms_in(self) -> None:
        """
        Ensures the bare + key zooms in.
        """

        before = self.canvas._zoom_factor
        self._key(Qt.Key.Key_Plus)
        self.assertGreater(self.canvas._zoom_factor, before)

    def test_minus_zooms_out(self) -> None:
        """
        Ensures the bare - key zooms out.
        """

        before = self.canvas._zoom_factor
        self._key(Qt.Key.Key_Minus)
        self.assertLess(self.canvas._zoom_factor, before)

    def test_equals_zooms_in_for_layouts_where_plus_needs_shift(self) -> None:
        """
        Ensures + is reachable on a layout that types it with Shift.
        """

        before = self.canvas._zoom_factor
        self._key(Qt.Key.Key_Equal)
        self.assertGreater(self.canvas._zoom_factor, before)

    def test_the_numeric_keypad_zooms_too(self) -> None:
        """
        Ensures the keypad's + and - work like the main keys.
        """

        before = self.canvas._zoom_factor
        self._key(Qt.Key.Key_Plus, Qt.KeyboardModifier.KeypadModifier)
        self.assertGreater(self.canvas._zoom_factor, before)
        middle = self.canvas._zoom_factor
        self._key(Qt.Key.Key_Minus, Qt.KeyboardModifier.KeypadModifier)
        self.assertLess(self.canvas._zoom_factor, middle)

    def test_the_ctrl_shortcuts_keep_working(self) -> None:
        """
        Ensures Ctrl++ and Ctrl+- are still bound.
        """

        before = self.canvas._zoom_factor
        self._key(Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
        self.assertGreater(self.canvas._zoom_factor, before)
        middle = self.canvas._zoom_factor
        self._key(Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
        self.assertLess(self.canvas._zoom_factor, middle)

    def test_the_default_bindings_name_the_plain_keys(self) -> None:
        """
        Ensures the shortcut table, which the settings dialog shows, says so.
        """

        from src.shortcuts import default_editor_shortcuts

        defaults = default_editor_shortcuts()
        self.assertIn("+", defaults["zoom_in"].split("; "))
        self.assertIn("-", defaults["zoom_out"].split("; "))


if __name__ == "__main__":
    unittest.main()
