"""
Tests for tool context-menu property sync with selection vs defaults.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtGui import QColor, QPixmap

    from src.annotation_items import STROKE_STYLE_DASH, STROKE_STYLE_SOLID
    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for tool menu sync tests")
class TestToolMenuSelectionSync(unittest.TestCase):
    """
    Verifies tool popup widgets mirror selection or tool defaults.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_selected_line_shows_object_width_in_tool_menu(self) -> None:
        """
        Ensures selecting a line shows that line's width in the Line menu.
        """

        pixmap = QPixmap(140, 100)
        pixmap.fill(QColor(230, 230, 230))
        window = EditorWindow(pixmap)
        window.apply_tool_stroke_widths({"line": 4}, emit_signal=False)
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="line",
                    x=10.0,
                    y=20.0,
                    width=60.0,
                    height=0.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[0, 0, 0, 0],
                    stroke_width=14.0,
                    payload={"stroke_style": STROKE_STYLE_DASH},
                )
            ]
        )
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        slider = window._tool_width_sliders[Tool.LINE]  # pylint: disable=protected-access
        combo = window._tool_style_combos[Tool.LINE]  # pylint: disable=protected-access
        self.assertEqual(slider.value(), 14)
        self.assertEqual(combo.currentData(), STROKE_STYLE_DASH)
        self.assertEqual(
            window._tool_stroke_widths["line"],  # pylint: disable=protected-access
            4,
        )
        window.close()

    def test_deselect_restores_tool_menu_defaults(self) -> None:
        """
        Ensures deselecting restores Width/Style menus to tool defaults.
        """

        pixmap = QPixmap(140, 100)
        pixmap.fill(QColor(230, 230, 230))
        window = EditorWindow(pixmap)
        window.apply_tool_stroke_widths({"line": 7}, emit_signal=False)
        window.apply_tool_stroke_styles(
            {"line": STROKE_STYLE_SOLID},
            emit_signal=False,
        )
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="line",
                    x=10.0,
                    y=20.0,
                    width=40.0,
                    height=10.0,
                    stroke_rgba=[0, 0, 255, 255],
                    fill_rgba=[0, 0, 0, 0],
                    stroke_width=18.0,
                    payload={"stroke_style": STROKE_STYLE_DASH},
                )
            ]
        )
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access
        item.setSelected(False)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        slider = window._tool_width_sliders[Tool.LINE]  # pylint: disable=protected-access
        combo = window._tool_style_combos[Tool.LINE]  # pylint: disable=protected-access
        self.assertEqual(slider.value(), 7)
        self.assertEqual(combo.currentData(), STROKE_STYLE_SOLID)
        window.close()

    def test_width_without_selection_updates_default(self) -> None:
        """
        Ensures Width changes without selection persist as tool defaults.
        """

        pixmap = QPixmap(100, 80)
        pixmap.fill(QColor(230, 230, 230))
        window = EditorWindow(pixmap)
        window._apply_tool_stroke_width(11, tool=Tool.RECT, persist=False)  # pylint: disable=protected-access
        self.assertEqual(
            window._tool_stroke_widths["rect"],  # pylint: disable=protected-access
            11,
        )
        self.assertEqual(
            window._tool_width_sliders[Tool.RECT].value(),  # pylint: disable=protected-access
            11,
        )
        window.close()

    def test_brush_menu_keeps_default_while_shape_selected(self) -> None:
        """
        Ensures Brush Width edits defaults even when a shape is selected.
        """

        pixmap = QPixmap(120, 90)
        pixmap.fill(QColor(230, 230, 230))
        window = EditorWindow(pixmap)
        window.apply_tool_stroke_widths({"brush": 9, "rect": 3}, emit_signal=False)
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=8.0,
                    y=8.0,
                    width=30.0,
                    height=20.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 40],
                    stroke_width=5.0,
                )
            ]
        )
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window._apply_tool_stroke_width(22, tool=Tool.BRUSH, persist=False)  # pylint: disable=protected-access
        self.assertEqual(int(item.pen().widthF()), 5)
        self.assertEqual(
            window._tool_stroke_widths["brush"],  # pylint: disable=protected-access
            22,
        )
        window.close()
