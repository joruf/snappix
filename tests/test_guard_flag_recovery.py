"""
Tests that re-entrancy guard flags survive a failure.

Several UI syncs set a flag, update widgets, then clear it. Written without
``try/finally``, a failure in between leaves the flag set for the rest of the
session -- and because every one of these flags means "ignore the next signal,
it is only an echo of this update", the feature it protects then goes quiet:
resize handles stop following the annotation, layer controls stop applying, and
history entries stop restoring. Nothing crashes, nothing is logged, the editor
just stops reacting, which is why this class of bug is reported as "it sometimes
goes weird" rather than as a bug with steps.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.editor_canvas import EditorCanvas
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _screenshot(width: int = 400, height: int = 300) -> QPixmap:
    """
    Builds a plain screenshot pixmap.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Filled pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 255, 255))
    return QPixmap.fromImage(image)


def _rect_annotation() -> AnnotationModel:
    """
    Builds one rectangle annotation.

    Returns:
        AnnotationModel: Rectangle model.
    """

    return AnnotationModel(
        annotation_type="rect",
        x=60.0,
        y=60.0,
        width=120.0,
        height=90.0,
        stroke_rgba=[200, 0, 0, 255],
        fill_rgba=[200, 0, 0, 60],
        stroke_width=2.0,
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for guard flag tests")
class TestResizeOverlayGuardFlag(unittest.TestCase):
    """
    Verifies the resize overlay keeps working after a failed sync.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for canvas tests.
        """

        cls._app = ensure_qapp()

    def _canvas_with_selection(self):
        """
        Builds a canvas with one selected rectangle and an active overlay.

        Returns:
            tuple[EditorCanvas, object]: Canvas and annotation item.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_screenshot())
        canvas.load_annotations([_rect_annotation()])
        item = next(i for i in canvas.scene().items() if str(i.data(1001) or ""))
        item.setSelected(True)
        canvas._sync_resize_overlay_with_target(item)
        return canvas, item

    def test_failed_sync_clears_the_flag(self) -> None:
        """
        Ensures the guard is released even when the update raises.
        """

        canvas, item = self._canvas_with_selection()
        overlay = canvas._resize_overlay_item
        self.assertIsNotNone(overlay)

        def boom(*_args, **_kwargs):
            raise RuntimeError("overlay update failed")

        with patch.object(overlay, "set_frame_mode", boom):
            with self.assertRaises(RuntimeError):
                canvas._sync_resize_overlay_with_target(item)

        self.assertFalse(canvas._updating_resize_overlay)

    def test_handles_still_follow_the_annotation_after_a_failure(self) -> None:
        """
        Ensures the user-visible consequence is gone: the resize handles keep
        tracking the annotation instead of freezing at their last position.
        """

        canvas, item = self._canvas_with_selection()
        overlay = canvas._resize_overlay_item

        def boom(*_args, **_kwargs):
            raise RuntimeError("overlay update failed")

        with patch.object(overlay, "set_frame_mode", boom):
            with self.assertRaises(RuntimeError):
                canvas._sync_resize_overlay_with_target(item)

        before = canvas._resize_overlay_item.scene_rect().width()
        item.setRect(item.rect().adjusted(0.0, 0.0, 60.0, 60.0))
        canvas._sync_resize_overlay_with_target(item)
        after = canvas._resize_overlay_item.scene_rect().width()

        self.assertGreater(after, before)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for guard flag tests")
class TestEditorWindowGuardFlags(unittest.TestCase):
    """
    Verifies the layer and history syncs release their guards on failure.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def _window(self):
        """
        Builds an editor window holding one annotation.

        Returns:
            EditorWindow: Window under test.
        """

        window = EditorWindow(_screenshot())
        self.addCleanup(window.close)
        window.canvas.load_annotations([_rect_annotation()])
        return window

    def test_layer_panel_guard_is_released_on_failure(self) -> None:
        """
        Ensures a failed layer refresh cannot mute the layer controls.
        """

        window = self._window()

        def boom(*_args, **_kwargs):
            raise RuntimeError("combo refresh failed")

        with patch.object(window.layer_combo, "addItem", boom):
            with self.assertRaises(RuntimeError):
                window._refresh_layer_panel()

        self.assertFalse(window._syncing_layer_panel)

    def test_history_list_guard_is_released_on_failure(self) -> None:
        """
        Ensures a failed history refresh cannot mute the undo list.
        """

        window = self._window()

        def boom(*_args, **_kwargs):
            raise RuntimeError("history refresh failed")

        with patch.object(window.history_list_combo, "addItem", boom):
            with self.assertRaises(RuntimeError):
                window._refresh_history_list()

        self.assertFalse(window._syncing_history_list)


if __name__ == "__main__":
    unittest.main()
