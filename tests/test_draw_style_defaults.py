"""
Tests for shared draw-style defaults used by image and video editors.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QColor, QPixmap

    from src.draw_style_defaults import (
        MARK_CHECKMARK_COLOR,
        MARK_CROSS_COLOR,
        apply_tool_default_colors,
        create_default_style_state,
        tool_default_stroke_color,
    )
    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.video_editor_window import VideoEditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for draw-style default tests")
class TestDrawStyleDefaults(unittest.TestCase):
    """
    Verifies shared editor draw defaults and tool-specific mark colors.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_create_default_style_state_matches_image_editor(self) -> None:
        """
        Ensures the shared default style uses the image editor baseline values.
        """

        style = create_default_style_state()
        self.assertEqual(style.stroke_width, 6.0)
        self.assertEqual(style.font_family, "Sans Serif")
        self.assertEqual(style.fill_color.alpha(), 80)

    def test_checkmark_default_color_is_green(self) -> None:
        """
        Ensures the checkmark tool resolves to the green palette color.
        """

        self.assertEqual(tool_default_stroke_color(Tool.CHECKMARK).name(), MARK_CHECKMARK_COLOR.name())
        self.assertEqual(MARK_CHECKMARK_COLOR.name(), "#2ecc71")

    def test_cross_default_color_is_red(self) -> None:
        """
        Ensures the cross tool resolves to the red palette color.
        """

        self.assertEqual(tool_default_stroke_color(Tool.CROSS).name(), MARK_CROSS_COLOR.name())

    def test_image_editor_applies_checkmark_green_on_tool_switch(self) -> None:
        """
        Ensures selecting Checkmark switches the active draw color to green.
        """

        pixmap = QPixmap(200, 150)
        pixmap.fill(QColor(240, 240, 240))
        window = EditorWindow(pixmap)
        window._set_tool(Tool.CHECKMARK)  # pylint: disable=protected-access
        style = window.canvas.style_state()
        self.assertEqual(style.stroke_color.name(), "#2ecc71")
        self.assertEqual(style.fill_color.name(), "#2ecc71")
        window.close()

    def test_video_editor_applies_checkmark_green_on_tool_switch(self) -> None:
        """
        Ensures the video editor uses the same green default for Checkmark.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
            editor._vector_toolbar._set_tool(Tool.CHECKMARK)  # pylint: disable=protected-access
            style = editor.style_state()
            self.assertEqual(style.stroke_color.name(), "#2ecc71")
            self.assertEqual(style.fill_color.name(), "#2ecc71")
            editor.close()

    def test_apply_tool_default_colors_updates_both_targets(self) -> None:
        """
        Ensures mark defaults update stroke and fill together.
        """

        style = create_default_style_state()
        self.assertTrue(apply_tool_default_colors(Tool.CHECKMARK, style))
        self.assertEqual(style.stroke_color.name(), "#2ecc71")
        self.assertEqual(style.fill_color.name(), "#2ecc71")


if __name__ == "__main__":
    unittest.main()
