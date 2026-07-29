"""
Unit tests for unlocking a locked draw tool with the Escape key, in both the
Image and Video editors.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.video_editor_window import VideoEditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int) -> "QPixmap":
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


def _make_silent_video(path: Path) -> None:
    """
    Renders a tiny silent test clip with ffmpeg for video editor tests.

    Args:
        path: Destination file path for the generated video.

    Returns:
        None
    """

    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48:d=1",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for tool-lock escape tests")
class TestImageEditorToolLockEscape(unittest.TestCase):
    """
    Verifies Escape clears a locked tool on the Image editor canvas.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = ensure_qapp()

    def test_escape_unlocks_locked_tool_and_returns_to_select(self) -> None:
        """
        Ensures pressing Escape on the canvas while a tool is locked clears
        the lock and switches back to the Select tool.
        """

        window = EditorWindow(_solid_pixmap(200, 120))
        window._toggle_tool_lock(Tool.RECT)  # pylint: disable=protected-access
        self.assertEqual(window._locked_tool, Tool.RECT)  # pylint: disable=protected-access

        window.canvas.tool_lock_escape_requested.emit()

        self.assertIsNone(window._locked_tool)  # pylint: disable=protected-access
        self.assertEqual(window.canvas._tool, Tool.SELECT)  # pylint: disable=protected-access
        window.close()

    def test_escape_without_a_locked_tool_is_a_no_op(self) -> None:
        """
        Ensures Escape does nothing when no tool is currently locked.
        """

        window = EditorWindow(_solid_pixmap(200, 120))
        window.canvas.set_tool(Tool.RECT)

        window.canvas.tool_lock_escape_requested.emit()

        self.assertIsNone(window._locked_tool)  # pylint: disable=protected-access
        self.assertEqual(window.canvas._tool, Tool.RECT)  # pylint: disable=protected-access
        window.close()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for tool-lock escape tests")
class TestVideoEditorToolLockEscape(unittest.TestCase):
    """
    Verifies Escape clears a locked tool on the Video editor canvas.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_escape_unlocks_locked_tool_and_returns_to_select(self) -> None:
        """
        Ensures pressing Escape on the video canvas while a tool is locked
        clears the lock and switches back to the Select tool.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_video = Path(tmp_dir) / "source.mp4"
            _make_silent_video(source_video)
            editor = VideoEditorWindow(str(source_video), 320, 240)
            toolbar = editor._vector_toolbar  # pylint: disable=protected-access
            toolbar._toggle_tool_lock(Tool.RECT)  # pylint: disable=protected-access
            self.assertEqual(toolbar._locked_tool, Tool.RECT)  # pylint: disable=protected-access

            editor.canvas.tool_lock_escape_requested.emit()

            self.assertIsNone(toolbar._locked_tool)  # pylint: disable=protected-access
            self.assertEqual(editor.canvas._tool, Tool.SELECT)  # pylint: disable=protected-access
            editor.close()


if __name__ == "__main__":
    unittest.main()
