"""
Tests for per-tool and per-element stroke width preferences.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import (
    AppConfig,
    ConfigManager,
    DEFAULT_TOOL_STROKE_WIDTHS,
    normalize_stroke_width,
    normalize_tool_stroke_widths,
)

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QSlider, QToolButton

    from src.annotation_items import create_stroke_pen, pen_stroke_width
    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


class TestToolStrokeWidthConfig(unittest.TestCase):
    """
    Verifies per-tool width normalization and persistence.
    """

    def test_normalize_allows_zero_for_shapes(self) -> None:
        """
        Ensures shape tools may use width 0 while brush tools stay at least 1.
        """

        self.assertEqual(normalize_stroke_width(0), 0)
        self.assertEqual(normalize_stroke_width(0, minimum=1), 1)
        widths = normalize_tool_stroke_widths({"rect": 0, "brush": 0})
        self.assertEqual(widths["rect"], 0)
        self.assertEqual(widths["brush"], 1)

    def test_normalize_merges_defaults(self) -> None:
        """
        Ensures unknown tools are ignored and defaults fill missing keys.
        """

        widths = normalize_tool_stroke_widths({"brush": 22, "mystery": 9})
        self.assertEqual(widths["brush"], 22)
        self.assertEqual(widths["eraser"], DEFAULT_TOOL_STROKE_WIDTHS["eraser"])
        self.assertNotIn("mystery", widths)

    def test_config_roundtrip_persists_tool_widths(self) -> None:
        """
        Ensures tool stroke widths survive config save/load.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            manager = ConfigManager(path)
            config = AppConfig(tool_stroke_widths={"brush": 18, "line": 5, "rect": 0})
            manager.save(config)
            restored = manager.load()
            self.assertEqual(restored.tool_stroke_widths["brush"], 18)
            self.assertEqual(restored.tool_stroke_widths["line"], 5)
            self.assertEqual(restored.tool_stroke_widths["rect"], 0)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for editor width tests")
class TestStrokeWidthZero(unittest.TestCase):
    """
    Verifies width 0 disables borders without Qt hairline pens.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def test_create_stroke_pen_zero_uses_no_pen(self) -> None:
        """
        Ensures width 0 builds a disabled pen instead of a hairline.
        """

        pen = create_stroke_pen(QColor(255, 0, 0), 0)
        self.assertEqual(pen.style(), Qt.PenStyle.NoPen)
        self.assertEqual(pen_stroke_width(pen), 0.0)

    def test_rectangle_with_zero_width_has_no_border(self) -> None:
        """
        Ensures loaded rectangles with stroke_width 0 use NoPen.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=10.0,
                    y=10.0,
                    width=30.0,
                    height=20.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 80],
                    stroke_width=0.0,
                )
            ]
        )
        item = next(iter(window.canvas._annotation_items()))  # pylint: disable=protected-access
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(pen_stroke_width(item.pen()), 0.0)
        window.close()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for editor width tests")
class TestToolStrokeWidthEditor(unittest.TestCase):
    """
    Verifies editor tool switching restores per-tool widths and menus.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def test_switching_tools_restores_saved_widths(self) -> None:
        """
        Ensures Brush and Line keep independent width preferences.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        window.apply_tool_stroke_widths(
            {"brush": 14, "line": 3, "rect": 4},
            emit_signal=False,
        )
        window._set_tool(Tool.BRUSH)  # pylint: disable=protected-access
        self.assertEqual(int(window.canvas._style.stroke_width), 14)  # pylint: disable=protected-access
        window._apply_tool_stroke_width(20, tool=Tool.BRUSH, persist=False)  # pylint: disable=protected-access
        window._set_tool(Tool.LINE)  # pylint: disable=protected-access
        self.assertEqual(int(window.canvas._style.stroke_width), 3)  # pylint: disable=protected-access
        window._set_tool(Tool.BRUSH)  # pylint: disable=protected-access
        self.assertEqual(int(window.canvas._style.stroke_width), 20)  # pylint: disable=protected-access
        window.close()

    def test_element_width_independent_of_tool_default(self) -> None:
        """
        Ensures the Line tool's default-thickness popup and the Style panel's
        per-element thickness control are fully independent: the popup only
        ever changes the tool default (never a selected element), and the
        Style panel only ever changes the selected element (never the
        tool default).
        """

        pixmap = QPixmap(120, 90)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        window.apply_tool_stroke_widths(
            {"line": 8, "rect": 4},
            emit_signal=False,
        )
        window._set_tool(Tool.LINE)  # pylint: disable=protected-access
        self.assertEqual(
            window._tool_stroke_widths["line"],  # pylint: disable=protected-access
            8,
        )
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="line",
                    x=10.0,
                    y=10.0,
                    width=40.0,
                    height=0.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[0, 0, 0, 0],
                    stroke_width=2.0,
                ),
                AnnotationModel(
                    annotation_type="line",
                    x=10.0,
                    y=30.0,
                    width=40.0,
                    height=0.0,
                    stroke_rgba=[0, 0, 255, 255],
                    fill_rgba=[0, 0, 0, 0],
                    stroke_width=12.0,
                ),
            ]
        )
        thin = next(
            item
            for item in window.canvas._annotation_items()  # pylint: disable=protected-access
            if abs(float(item.pen().widthF()) - 2.0) < 0.1
        )
        thick = next(
            item
            for item in window.canvas._annotation_items()  # pylint: disable=protected-access
            if abs(float(item.pen().widthF()) - 12.0) < 0.1
        )
        thin.setSelected(True)

        # The Line tool popup only ever edits the tool default now.
        window._apply_tool_stroke_width(20, tool=Tool.LINE, persist=False)  # pylint: disable=protected-access
        self.assertEqual(int(thin.pen().widthF()), 2)
        self.assertEqual(int(thick.pen().widthF()), 12)
        self.assertEqual(
            window._tool_stroke_widths["line"],  # pylint: disable=protected-access
            20,
        )

        # The Style panel's thickness slider only ever edits the selection.
        window._style_thickness_changed(30)  # pylint: disable=protected-access
        self.assertEqual(int(thin.pen().widthF()), 30)
        self.assertEqual(int(thick.pen().widthF()), 12)
        self.assertEqual(
            window._tool_stroke_widths["line"],  # pylint: disable=protected-access
            20,
        )
        window.close()

    def test_style_palette_has_no_general_width_slider(self) -> None:
        """
        Ensures the shared Width slider was removed from the style palette.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        self.assertFalse(hasattr(window, "stroke_size_slider"))
        window.close()

    def test_stroke_aware_tools_expose_width_menu(self) -> None:
        """
        Ensures drawing tools that use width expose a Width slider popup.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        for tool in (
            Tool.BRUSH,
            Tool.ERASER,
            Tool.RECT,
            Tool.ELLIPSE,
            Tool.LINE,
            Tool.ARROW,
            Tool.TEXT,
        ):
            button = window._tool_buttons[tool]  # pylint: disable=protected-access
            self.assertIsNotNone(button.menu())
            self.assertEqual(
                button.popupMode(),
                QToolButton.ToolButtonPopupMode.MenuButtonPopup,
            )
            self.assertTrue(bool(button.property("menuTool")))
            titles = [action.text() for action in button.menu().actions() if action.text()]
            self.assertFalse(any(text.endswith(" px") for text in titles))
            has_slider = False
            for action in button.menu().actions():
                widget = action.defaultWidget() if hasattr(action, "defaultWidget") else None
                if widget is None:
                    continue
                if widget.findChildren(QSlider):
                    has_slider = True
                    break
            self.assertTrue(has_slider)
        window.close()

    def test_tool_menu_width_slider_updates_default(self) -> None:
        """
        Ensures the tool popup Width slider updates the tool default.
        """

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)
        canvas = window.canvas
        window._set_tool(Tool.BRUSH)  # pylint: disable=protected-access
        window._apply_tool_stroke_width(8, tool=Tool.BRUSH, persist=False)  # pylint: disable=protected-access
        self.assertEqual(int(canvas._style.stroke_width), 8)  # pylint: disable=protected-access
        window.close()


if __name__ == "__main__":
    unittest.main()
