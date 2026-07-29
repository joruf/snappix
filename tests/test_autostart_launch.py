"""
Unit tests for the boot/login autostart launch mode.

On a normal manual start, Snappix shows the Capture panel as usual. When
launched from the OS autostart entry (``--autostart``), it must stay tray-only:
no Capture window, no Editor, no project/recovery restoration.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _make_controller(*, autostart_launch: bool):
    """
    Builds a bare AppController instance with only the attributes ``show()``
    touches, bypassing the heavy real ``__init__`` per the project's existing
    ``object.__new__(AppController)`` test pattern.

    Args:
        autostart_launch: Value to set for ``_autostart_launch``.

    Returns:
        AppController: Bare controller instance ready for show().
    """

    from run import AppController

    controller = object.__new__(AppController)
    controller._autostart_launch = autostart_launch
    controller._startup_project_path = ""
    controller._apply_capture_taskbar_identity = MagicMock()
    controller.capture_panel = MagicMock()
    controller._open_project_in_editor = MagicMock()
    controller._maybe_restore_recovery_snapshot = MagicMock()
    return controller


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for autostart launch tests")
class TestAutostartLaunchShow(unittest.TestCase):
    """
    Verifies AppController.show() stays tray-only under ``--autostart``.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_autostart_launch_keeps_capture_panel_and_editor_closed(self) -> None:
        """
        Ensures an autostart launch shows neither the Capture panel nor an
        editor/recovery snapshot, but still applies the taskbar identity so
        the tray icon reflects the current theme/icon.
        """

        controller = _make_controller(autostart_launch=True)
        controller.show()

        controller._apply_capture_taskbar_identity.assert_called_once()
        controller.capture_panel.show.assert_not_called()
        controller._open_project_in_editor.assert_not_called()
        controller._maybe_restore_recovery_snapshot.assert_not_called()

    def test_normal_launch_shows_capture_panel_and_restores_recovery(self) -> None:
        """
        Ensures a normal (non-autostart) launch keeps its existing behavior:
        the Capture panel is shown and the recovery snapshot is restored.
        """

        controller = _make_controller(autostart_launch=False)
        controller.show()

        controller.capture_panel.show.assert_called_once()
        controller._open_project_in_editor.assert_not_called()
        controller._maybe_restore_recovery_snapshot.assert_called_once()

    def test_normal_launch_with_startup_project_opens_it_instead_of_recovery(self) -> None:
        """
        Ensures a normal launch with a CLI-provided project path opens that
        project and skips recovery-snapshot restoration, unaffected by the
        new autostart branch.
        """

        controller = _make_controller(autostart_launch=False)
        controller._startup_project_path = "/tmp/example.snappix"
        controller.show()

        controller._open_project_in_editor.assert_called_once_with("/tmp/example.snappix")
        controller._maybe_restore_recovery_snapshot.assert_not_called()


class TestAutostartLoginExecCommand(unittest.TestCase):
    """
    Verifies the boot/login autostart entry launches with ``--autostart``.
    """

    def test_login_exec_command_appends_autostart_flag(self) -> None:
        """
        Ensures the login autostart command is the normal launch command with
        ``--autostart`` appended, so the app can detect the boot-time launch.
        """

        import run

        with patch.object(run, "_autostart_exec_command", return_value='python3 "run.py"'):
            self.assertEqual(
                run._autostart_login_exec_command(),
                'python3 "run.py" --autostart',
            )


if __name__ == "__main__":
    unittest.main()
