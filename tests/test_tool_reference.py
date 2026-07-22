"""
Unit tests for the tools reference catalog and dialog.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QLabel

    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.tool_reference import (
        TOOL_HELP_ENTRIES,
        format_tool_explanation,
        format_tool_tooltip,
        tool_help_entry,
    )
    from src.tool_reference_dialog import ToolReferenceDialog
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for tools reference tests")
class TestToolReference(unittest.TestCase):
    """
    Verifies tool help catalog content and the reference dialog list.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def test_catalog_covers_every_toolbar_tool(self) -> None:
        """
        Ensures every toolbar tool has a catalog entry with name and description.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        toolbar_tools = set(window._tool_buttons.keys())  # pylint: disable=protected-access
        catalog_tools = {entry.tool for entry in TOOL_HELP_ENTRIES}
        self.assertEqual(toolbar_tools, catalog_tools)
        for entry in TOOL_HELP_ENTRIES:
            self.assertTrue(entry.name.strip())
            self.assertTrue(entry.description.strip())
            self.assertTrue(entry.tooltip_blurb.strip())
            tip = format_tool_tooltip(entry.tool)
            self.assertTrue(tip.startswith(entry.name))
            self.assertIn("—", tip)
            explanation = format_tool_explanation(entry)
            self.assertTrue(explanation.startswith(entry.name))
            self.assertIn(entry.description, explanation)
        window.close()

    def test_fill_entry_explains_selection_and_opacity(self) -> None:
        """
        Ensures Fill help text mentions selection and opacity.
        """

        entry = tool_help_entry(Tool.BUCKET)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.name, "Fill")
        self.assertIn("selection", entry.description.lower())
        self.assertIn("opacity", entry.description.lower())

    def test_tools_reference_dialog_lists_symbol_and_explanation(self) -> None:
        """
        Ensures the dialog lists an icon row and explanation for every tool.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        dialog = ToolReferenceDialog(window, window._build_tool_icon)  # pylint: disable=protected-access
        self.assertEqual(dialog.tool_row_count(), len(TOOL_HELP_ENTRIES))
        self.assertEqual(
            dialog.scroll_area.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        row_texts = dialog.tool_row_texts()
        self.assertEqual(len(row_texts), len(TOOL_HELP_ENTRIES))
        for index, entry in enumerate(TOOL_HELP_ENTRIES):
            name, description = row_texts[index]
            self.assertEqual(name, entry.name)
            self.assertEqual(description, entry.description)
            icon_badge = dialog.rows[index].findChild(QLabel, "toolReferenceIconBadge")
            self.assertIsNotNone(icon_badge)
            assert icon_badge is not None
            self.assertFalse(icon_badge.pixmap().isNull())
        dialog.close()
        window.close()

    def test_editor_opens_tools_reference_from_helper(self) -> None:
        """
        Ensures the editor exposes show_tools_reference for Help and toolbar.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        self.assertTrue(hasattr(window, "show_tools_reference"))
        self.assertTrue(hasattr(window, "tools_help_button"))
        self.assertEqual(window.tools_help_button.text(), "?")
        window.close()


if __name__ == "__main__":
    unittest.main()
