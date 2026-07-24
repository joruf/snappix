"""
Tests for contextual Style color visibility (Border / Fill / Text).
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtGui import QColor, QPixmap

    from src.annotation_items import add_annotation_to_scene
    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for style color visibility tests")
class TestStyleColorVisibility(unittest.TestCase):
    """
    Verifies Border/Fill/Text groups appear only for matching tools or selections.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_select_tool_hides_all_color_groups(self) -> None:
        """
        Ensures Select mode without a selection hides Border, Fill, and Text.
        """

        pixmap = QPixmap(120, 80)
        pixmap.fill(QColor(230, 230, 230))
        window = EditorWindow(pixmap)
        window._set_tool(Tool.SELECT)  # pylint: disable=protected-access
        self.assertTrue(window.stroke_button.isHidden())
        self.assertTrue(window.fill_button.isHidden())
        self.assertTrue(window.text_color_button.isHidden())
        self.assertFalse(window._property_tabs.isTabVisible(window._PROPERTY_TAB_STYLE))  # pylint: disable=protected-access
        window.close()

    def test_line_tool_shows_only_border(self) -> None:
        """
        Ensures the Line tool exposes Border colors only.
        """

        pixmap = QPixmap(120, 80)
        pixmap.fill(QColor(230, 230, 230))
        window = EditorWindow(pixmap)
        window._set_tool(Tool.LINE)  # pylint: disable=protected-access
        self.assertFalse(window.stroke_button.isHidden())
        self.assertTrue(window.fill_button.isHidden())
        self.assertTrue(window.text_color_button.isHidden())
        self.assertTrue(window._property_tabs.isTabVisible(window._PROPERTY_TAB_STYLE))  # pylint: disable=protected-access
        window.close()

    def test_text_selection_shows_text_colors(self) -> None:
        """
        Ensures selecting text in Select mode shows Text (and box) color groups.
        """

        pixmap = QPixmap(160, 100)
        pixmap.fill(QColor(230, 230, 230))
        window = EditorWindow(pixmap)
        window._set_tool(Tool.SELECT)  # pylint: disable=protected-access
        item = add_annotation_to_scene(
            window.canvas.scene(),
            AnnotationModel(
                annotation_type="text",
                x=10.0,
                y=10.0,
                width=80.0,
                height=24.0,
                stroke_rgba=[0, 0, 0, 255],
                fill_rgba=[255, 255, 255, 255],
                stroke_width=1.0,
                text="Hello",
                payload={
                    "text_style": "box",
                    "text_rgba": [44, 62, 80, 255],
                },
            ),
        )
        assert item is not None
        item.setSelected(True)
        window._on_selection_style_changed(  # pylint: disable=protected-access
            window.canvas._build_selection_payload(item)  # pylint: disable=protected-access
        )
        self.assertFalse(window.text_color_button.isHidden())
        self.assertFalse(window.stroke_button.isHidden())
        self.assertFalse(window.fill_button.isHidden())
        window.close()

    def test_selected_line_shows_only_border(self) -> None:
        """
        Ensures a selected line in Select mode shows Border only.
        """

        pixmap = QPixmap(160, 100)
        pixmap.fill(QColor(230, 230, 230))
        window = EditorWindow(pixmap)
        window._set_tool(Tool.SELECT)  # pylint: disable=protected-access
        item = add_annotation_to_scene(
            window.canvas.scene(),
            AnnotationModel(
                annotation_type="line",
                x=10.0,
                y=10.0,
                width=40.0,
                height=20.0,
                stroke_rgba=[231, 76, 60, 255],
                fill_rgba=[0, 0, 0, 0],
                stroke_width=3.0,
            ),
        )
        assert item is not None
        item.setSelected(True)
        window._on_selection_style_changed(  # pylint: disable=protected-access
            window.canvas._build_selection_payload(item)  # pylint: disable=protected-access
        )
        self.assertFalse(window.stroke_button.isHidden())
        self.assertTrue(window.fill_button.isHidden())
        self.assertTrue(window.text_color_button.isHidden())
        window.close()


if __name__ == "__main__":
    unittest.main()
