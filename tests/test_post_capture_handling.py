"""
Unit tests for AppController's post-capture action handling.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.config import POST_CAPTURE_CLIPBOARD, POST_CAPTURE_SAVE
from src.post_capture_service import DEFAULT_FILENAME_TEMPLATE

try:
    from PySide6.QtGui import QColor, QPixmap
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _make_controller(*, post_capture_action: str, save_directory: Path | None = None):
    """
    Builds a bare AppController instance with only the attributes
    ``_handle_capture_result`` touches, bypassing the heavy real ``__init__``
    (tray icon, singleton lock, config bootstrap) per the project's existing
    ``object.__new__(AppController)`` test pattern.

    Args:
        post_capture_action: Configured post-capture action to simulate.
        save_directory: Directory returned by ``_capture_save_directory``.

    Returns:
        AppController: Bare controller instance ready for _handle_capture_result.
    """

    from run import AppController

    controller = object.__new__(AppController)
    controller.config = SimpleNamespace(
        post_capture_action=post_capture_action,
        capture_filename_template=DEFAULT_FILENAME_TEMPLATE,
    )
    controller.capture_panel = MagicMock()
    controller._QMessageBox = MagicMock()
    controller._tray_available = True
    controller.tray_icon = MagicMock()
    controller.tray_icon.isVisible.return_value = True
    controller.editor_tabs = MagicMock()
    controller.editor_tabs.count.return_value = 0
    controller._create_editor_tab = MagicMock()
    if save_directory is not None:
        controller._capture_save_directory = MagicMock(return_value=save_directory)
    return controller


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for post-capture handling tests")
class TestHandleCaptureResult(unittest.TestCase):
    """
    Verifies AppController._handle_capture_result branches on a null pixmap,
    clipboard, save, and default-to-editor post-capture actions.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for QPixmap/clipboard operations.
        """

        cls._app = ensure_qapp()

    def test_null_pixmap_warns_and_shows_panel(self) -> None:
        """
        Ensures an empty capture warns the user and reopens the capture panel.
        """

        controller = _make_controller(post_capture_action=POST_CAPTURE_CLIPBOARD)
        controller._handle_capture_result(QPixmap())

        controller._QMessageBox.warning.assert_called_once()
        controller.capture_panel.show.assert_called_once()
        controller.tray_icon.showMessage.assert_not_called()

    def test_clipboard_action_copies_and_notifies(self) -> None:
        """
        Ensures the clipboard action copies the pixmap and shows a tray notification.
        """

        controller = _make_controller(post_capture_action=POST_CAPTURE_CLIPBOARD)
        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor(0, 255, 0))

        controller._handle_capture_result(pixmap)

        controller.capture_panel.show.assert_called_once()
        controller.tray_icon.showMessage.assert_called_once()
        controller._create_editor_tab.assert_not_called()

    def test_save_action_success_writes_file_and_notifies(self) -> None:
        """
        Ensures the save action writes a PNG to the configured directory.
        """

        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor(0, 0, 255))
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            controller = _make_controller(
                post_capture_action=POST_CAPTURE_SAVE,
                save_directory=directory,
            )

            controller._handle_capture_result(pixmap)

            saved_files = list(directory.glob("snappix_*.png"))
            self.assertEqual(len(saved_files), 1)
        controller.capture_panel.show.assert_called_once()
        controller.tray_icon.showMessage.assert_called_once()
        controller._QMessageBox.warning.assert_not_called()

    def test_save_action_failure_warns(self) -> None:
        """
        Ensures a failed save shows a warning instead of a tray notification.
        """

        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor(0, 0, 0))
        # A directory that does not exist makes the pixmap.save() call fail.
        missing_directory = Path(tempfile.mkdtemp()) / "does-not-exist"
        controller = _make_controller(
            post_capture_action=POST_CAPTURE_SAVE,
            save_directory=missing_directory,
        )

        controller._handle_capture_result(pixmap)

        controller._QMessageBox.warning.assert_called_once()
        controller.tray_icon.showMessage.assert_not_called()

    def test_default_action_opens_editor_tab(self) -> None:
        """
        Ensures any other configured action falls back to opening an editor tab.
        """

        controller = _make_controller(post_capture_action="open_editor")
        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor(255, 255, 0))

        controller._handle_capture_result(pixmap)

        controller._create_editor_tab.assert_called_once()
        controller.capture_panel.show.assert_called_once()


if __name__ == "__main__":
    unittest.main()
