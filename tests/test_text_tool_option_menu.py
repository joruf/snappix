"""
Tests for Text tool option popup menus.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSlider, QTabWidget, QToolButton

    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestTextToolOptionMenu(unittest.TestCase):
    """
    Verifies typography settings live on the Text tool popup menu.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures QApplication exists.
        """

        cls._app = ensure_qapp()

    def test_text_tool_menu_contains_typography_controls(self) -> None:
        """
        Ensures the Text tool popup exposes font, size, style, and width.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        button = window._tool_buttons[Tool.TEXT]  # pylint: disable=protected-access
        self.assertIsNotNone(button.menu())
        self.assertEqual(
            button.popupMode(),
            QToolButton.ToolButtonPopupMode.MenuButtonPopup,
        )
        self.assertTrue(bool(button.property("menuTool")))

        panel = None
        for action in button.menu().actions():
            widget = action.defaultWidget() if hasattr(action, "defaultWidget") else None
            if widget is not None:
                panel = widget
                break
        self.assertIsNotNone(panel)
        assert panel is not None
        self.assertTrue(panel.findChildren(QComboBox))
        self.assertTrue(panel.findChildren(QDoubleSpinBox))
        self.assertTrue(panel.findChildren(QSlider))
        self.assertIs(window.font_family_combo.parent(), panel)
        self.assertIs(window.font_size_combo.parent(), panel)
        self.assertIs(window.text_style_combo.parent(), panel)
        self.assertIs(window.text_width_menu_slider.parent(), panel)
        window.close()

    def test_property_tabs_no_longer_include_text_tab(self) -> None:
        """
        Ensures typography was removed from the property tab strip.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        tabs = window.findChild(QTabWidget, "editorPropertyTabs")
        self.assertIsNotNone(tabs)
        assert tabs is not None
        titles = [tabs.tabText(index) for index in range(tabs.count())]
        self.assertNotIn("Text", titles)
        # The former "Style" tab is now called "Edit".
        self.assertIn("Edit", titles)
        self.assertIn("Arrange", titles)
        self.assertIn("Export", titles)
        window.close()


if __name__ == "__main__":
    unittest.main()
