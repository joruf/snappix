"""
Unit tests for editor toolbar drawing-tool tooltips.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtGui import QColor, QPixmap

    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for toolbar tooltip tests")
class TestEditorToolTooltips(unittest.TestCase):
    """
    Verifies every drawing tool button has a descriptive English tooltip.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for editor widgets.
        """

        cls._app = ensure_qapp()

    def test_every_tool_button_has_descriptive_english_tooltip(self) -> None:
        """
        Ensures no tool falls back to a short label-only tooltip.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)

        short_labels = {
            "Select",
            "Sel Rect",
            "Sel Ellipse",
            "Lasso",
            "Wand",
            "Magic Wand",
            "Brush",
            "Bucket",
            "Fill",
            "Rectangle",
            "Circle",
            "Line",
            "Arrow",
            "Text",
            "Bg Fill",
            "Blur",
            "Step",
            "OCR",
            "Crop",
            "Use this tool.",
            "Drawing tool",
        }
        expected_tools = [
            Tool.SELECT,
            Tool.SELECT_RECT,
            Tool.SELECT_ELLIPSE,
            Tool.SELECT_PATH,
            Tool.MAGIC_WAND,
            Tool.BRUSH,
            Tool.BUCKET,
            Tool.RECT,
            Tool.ELLIPSE,
            Tool.LINE,
            Tool.ARROW,
            Tool.TEXT,
            Tool.FILL_BG,
            Tool.BLUR,
            Tool.STEP,
            Tool.OCR,
            Tool.CROP,
        ]

        for tool_key in expected_tools:
            self.assertIn(tool_key, window._tool_buttons)  # pylint: disable=protected-access
            tip = window._tool_buttons[tool_key].toolTip().strip()  # pylint: disable=protected-access
            self.assertTrue(tip, f"Missing tooltip for tool {tool_key}")
            self.assertNotIn(tip, short_labels, f"Tooltip for {tool_key} is only a short label: {tip!r}")
            self.assertIn("—", tip, f"Tooltip for {tool_key} should name the tool: {tip!r}")
            self.assertLessEqual(len(tip), 90, f"Tooltip for {tool_key} is too long: {tip!r}")

        window.close()

    def test_lock_visuals_keep_descriptive_tooltip(self) -> None:
        """
        Ensures locking a tool does not replace the tooltip with the short label.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        window._toggle_tool_lock(Tool.RECT)  # pylint: disable=protected-access
        tip = window._tool_buttons[Tool.RECT].toolTip()  # pylint: disable=protected-access
        self.assertIn("Rectangle", tip)
        self.assertIn("locked", tip.lower())
        self.assertNotEqual(tip.strip(), "Rectangle")
        window.close()

    def test_fill_tool_tooltip_explains_selection_fill(self) -> None:
        """
        Ensures the Fill tool tooltip states name and purpose clearly.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        tip = window._tool_buttons[Tool.BUCKET].toolTip()  # pylint: disable=protected-access
        self.assertTrue(tip.startswith("Fill"))
        self.assertIn("selection", tip.lower())
        self.assertIn("fill color", tip.lower())
        self.assertIn("opacity", tip.lower())
        window.close()


if __name__ == "__main__":
    unittest.main()
