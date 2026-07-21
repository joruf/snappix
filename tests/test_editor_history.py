"""
Unit tests for editor history labels and list behavior.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int) -> QPixmap:
    """
    Creates a plain screenshot image for editor tests.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Generated pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 255, 255, 255))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for editor history tests")
class TestEditorHistory(unittest.TestCase):
    """
    Verifies history labels and toolbar history list synchronization.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures QApplication exists for editor widgets.
        """

        cls._app = ensure_qapp()

    def test_canvas_action_label_is_recorded(self) -> None:
        """
        Ensures canvas action label appears as history entry.
        """

        window = EditorWindow(_solid_pixmap(200, 120))
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
        window.canvas.load_annotations([annotation])
        window.canvas._emit_content_changed("Draw rectangle")  # pylint: disable=protected-access

        self.assertEqual(window._history_labels[-1], "Draw rectangle")  # pylint: disable=protected-access
        self.assertIn("Draw rectangle", window.history_list_combo.currentText())
        window.close()

    def test_pending_label_overrides_canvas_label(self) -> None:
        """
        Ensures explicit pending label is used for next history state.
        """

        window = EditorWindow(_solid_pixmap(200, 120))
        annotation = AnnotationModel(
            annotation_type="text",
            x=12.0,
            y=14.0,
            width=40.0,
            height=20.0,
            stroke_rgba=[0, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=1.0,
            text="A",
            font_size=16,
            font_family="Sans Serif",
        )
        window._set_next_history_label("Change text color")  # pylint: disable=protected-access
        window.canvas.load_annotations([annotation])
        window._push_history_state()  # pylint: disable=protected-access

        self.assertEqual(window._history_labels[-1], "Change text color")  # pylint: disable=protected-access
        self.assertIn("Change text color", window.history_list_combo.currentText())
        window.close()

    def test_one_shot_tool_switches_back_to_select(self) -> None:
        """
        Ensures single-click draw mode returns to Select after one draw action.
        """

        window = EditorWindow(_solid_pixmap(200, 120))
        window._on_tool_button_clicked(Tool.RECT)  # pylint: disable=protected-access
        self.assertEqual(window._one_shot_tool, Tool.RECT)  # pylint: disable=protected-access

        window._apply_one_shot_tool_completion("Draw rectangle")  # pylint: disable=protected-access
        self.assertEqual(window._active_tool, Tool.SELECT)  # pylint: disable=protected-access
        self.assertIsNone(window._one_shot_tool)  # pylint: disable=protected-access
        window.close()

    def test_double_click_lock_sets_and_clears_lock_visual(self) -> None:
        """
        Ensures locked drawing tool displays lock marker and toggles off.
        """

        window = EditorWindow(_solid_pixmap(200, 120))
        window._toggle_tool_lock(Tool.RECT)  # pylint: disable=protected-access
        self.assertEqual(window._locked_tool, Tool.RECT)  # pylint: disable=protected-access
        self.assertIn("🔒", window._tool_buttons[Tool.RECT].text())  # pylint: disable=protected-access

        window._on_tool_button_clicked(Tool.RECT)  # pylint: disable=protected-access
        self.assertIsNone(window._locked_tool)  # pylint: disable=protected-access
        self.assertEqual(window._active_tool, Tool.SELECT)  # pylint: disable=protected-access
        self.assertNotIn("🔒", window._tool_buttons[Tool.RECT].text())  # pylint: disable=protected-access
        window.close()

