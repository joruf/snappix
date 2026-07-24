"""
Tests that editor toolbars wrap buttons with the shared flow layout.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QGroupBox, QToolButton

    from src.editor_window import EditorWindow
    from src.flow_layout import FlowLayoutWidget
    from src.video_editor_window import VideoEditorWindow
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for toolbar flow tests")
class TestEditorToolbarFlow(unittest.TestCase):
    """
    Verifies image and video toolbars use float-style wrapping.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_image_editor_tool_strip_uses_flow_layout(self) -> None:
        """
        Ensures the image editor tool strip is a FlowLayoutWidget with tools.
        """

        pixmap = QPixmap(120, 80)
        pixmap.fill(QColor(255, 255, 255))
        window = EditorWindow(pixmap)
        strip = window._toolbar_widget.findChild(FlowLayoutWidget, "editorToolStrip")
        self.assertIsNotNone(strip)
        assert strip is not None
        tool_buttons = [child for child in strip.findChildren(QToolButton) if child.isCheckable()]
        self.assertGreaterEqual(len(tool_buttons), 20)
        category_boxes = strip.findChildren(QGroupBox, "toolCategoryBox")
        self.assertGreaterEqual(len(category_boxes), 5)
        titles = {box.title() for box in category_boxes}
        self.assertIn("Shapes", titles)
        self.assertIn("Lines", titles)
        self.assertIn("Marks", titles)
        for box in category_boxes:
            nested_flows = box.findChildren(FlowLayoutWidget)
            self.assertEqual(
                nested_flows,
                [],
                f"Category '{box.title()}' should not wrap tools internally",
            )
        narrow = strip.heightForWidth(220)
        wide = strip.heightForWidth(1400)
        self.assertGreater(narrow, wide)
        window.close()

    def test_editor_window_can_shrink_below_unwrapped_toolbar_width(self) -> None:
        """
        Ensures category/property flow layouts do not lock a huge window minimum width.
        """

        pixmap = QPixmap(120, 80)
        pixmap.fill(QColor(255, 255, 255))
        window = EditorWindow(pixmap)
        window.show()
        self._app.processEvents()
        self.assertLess(
            window.minimumSizeHint().width(),
            900,
            "Editor minimum width should stay shrinkable via wrapping toolbars",
        )
        window.resize(700, 520)
        self._app.processEvents()
        self.assertLessEqual(window.width(), 720)
        window.close()

    def test_video_editor_toolbar_uses_flow_layout(self) -> None:
        """
        Ensures the video editor toolbar host wraps controls with FlowLayoutWidget.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
            self.assertIsInstance(editor._toolbar_host, FlowLayoutWidget)
            category_boxes = editor._toolbar_host.findChildren(QGroupBox, "toolCategoryBox")
            self.assertGreaterEqual(len(category_boxes), 4)
            titles = {box.title() for box in category_boxes}
            self.assertIn("Shapes", titles)
            self.assertIn("Playback", titles)
            for box in category_boxes:
                nested_flows = box.findChildren(FlowLayoutWidget)
                self.assertEqual(
                    nested_flows,
                    [],
                    f"Category '{box.title()}' should not wrap tools internally",
                )
            narrow = editor._toolbar_host.heightForWidth(200)
            wide = editor._toolbar_host.heightForWidth(1600)
            self.assertGreater(narrow, wide)
