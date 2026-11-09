"""
Tests for opening images with Snappix: from a file manager, from the command
line, and from a second launch while Snappix is already running.

A viewer has one duty above all others: it must never harm the file it was
asked to show. These tests open real files in a real controller and check, among
other things, that closing the tab leaves the picture where it was.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QMessageBox

    from tests.qt_test_utils import ensure_qapp
    from tests.test_capture_tabs import CaptureTabCase

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False
    CaptureTabCase = unittest.TestCase  # type: ignore[assignment,misc]

TEST_SERVER_NAME = "snappix-instance-test-viewer"


def _write_image(directory: Path, name: str, width: int = 500, height: int = 300) -> Path:
    """
    Writes a small image file.

    Args:
        directory: Folder to write into.
        name: File name; the suffix decides the format.
        width: Width in pixels.
        height: Height in pixels.

    Returns:
        Path: The written file.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(20, 120, 60))
    path = directory / name
    assert pixmap.save(str(path)), f"could not write {path}"
    return path


class TestParsingMessages(unittest.TestCase):
    """
    Verifies what the running instance makes of another launch's message.
    """

    def test_show_means_no_files(self) -> None:
        """
        Ensures the old plain request still just raises the window.
        """

        import run

        self.assertEqual(run._parse_instance_message(b"show"), [])

    def test_open_lists_one_file_per_line(self) -> None:
        """
        Ensures paths with spaces survive.
        """

        import run

        data = "open\n/tmp/a b.png\n/tmp/c.jpg".encode()

        self.assertEqual(run._parse_instance_message(data), ["/tmp/a b.png", "/tmp/c.jpg"])

    def test_blank_lines_and_garbage_are_ignored(self) -> None:
        """
        Ensures a damaged message cannot open anything odd.
        """

        import run

        self.assertEqual(run._parse_instance_message(b""), [])
        self.assertEqual(run._parse_instance_message(b"\xff\xfe"), [])
        self.assertEqual(run._parse_instance_message(b"open\n\n  \n/a.png\n"), ["/a.png"])
        self.assertEqual(run._parse_instance_message(b"delete\n/a.png"), [])


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestSecondLaunchWithFiles(CaptureTabCase):
    """
    Verifies that a file opened while Snappix is running goes to that Snappix.
    """

    def setUp(self) -> None:
        """
        Gives the instance channel a name of this test's own.
        """

        super().setUp()
        import run

        self._run = run
        patcher = patch.object(run, "_instance_server_name", return_value=TEST_SERVER_NAME)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(QLocalServer.removeServer, TEST_SERVER_NAME)

    def _wait_until(self, condition) -> None:
        """
        Lets the event loop run until a condition holds.

        Args:
            condition: Function returning True when done.
        """

        for _ in range(200):
            self._app.processEvents()
            if condition():
                return

    def test_the_file_reaches_the_running_instance(self) -> None:
        """
        Ensures the second launch hands its file over instead of dropping it.
        """

        controller = self._controller()
        server = self._run._start_instance_server(controller)
        self.assertIsNotNone(server)
        self.addCleanup(server.close)

        with TemporaryDirectory() as directory:
            image = _write_image(Path(directory), "shot.png")
            self.assertTrue(self._run._signal_running_instance([str(image)]))
            self._wait_until(lambda: controller.editor_tabs.count() > 0)

            self.assertEqual(controller.editor_tabs.count(), 1)
            self.assertEqual(controller.editor_tabs.tabText(0), "shot.png")

    def test_a_plain_second_launch_still_raises_the_window(self) -> None:
        """
        Ensures the file path did not break the original behaviour.
        """

        controller = MagicMock()
        server = self._run._start_instance_server(controller)
        self.addCleanup(server.close)

        self.assertTrue(self._run._signal_running_instance())
        self._wait_until(lambda: controller._show_from_tray.called)

        controller._show_from_tray.assert_called_once()
        controller.open_files.assert_not_called()

    def test_several_files_arrive_together(self) -> None:
        """
        Ensures a multi-file selection opens every file.
        """

        controller = self._controller()
        server = self._run._start_instance_server(controller)
        self.addCleanup(server.close)

        with TemporaryDirectory() as directory:
            names = ["a.png", "b.jpg", "c.bmp"]
            files = [str(_write_image(Path(directory), name)) for name in names]
            self._run._signal_running_instance(files)
            self._wait_until(lambda: controller.editor_tabs.count() >= 3)

            self.assertEqual(
                [controller.editor_tabs.tabText(i) for i in range(controller.editor_tabs.count())],
                names,
            )

    def test_a_blocked_launch_hands_over_its_files(self) -> None:
        """
        Ensures the launch path passes the files on, not only the helper.
        """

        with patch.object(self._run, "_acquire_single_instance_lock", return_value=False), patch.object(
            self._run, "_signal_running_instance", return_value=True
        ) as signal:
            code = self._run._launch_gui(startup_files=["/tmp/a.png"])

        self.assertEqual(code, 0)
        signal.assert_called_once_with(["/tmp/a.png"])


class TestCommandLine(unittest.TestCase):
    """
    Verifies that main() turns arguments into files to open.
    """

    def _main(self, arguments: list[str]):
        """
        Runs main() with arguments and a stubbed launcher.

        Args:
            arguments: Arguments after the program name.

        Returns:
            MagicMock: The stand-in for ``_launch_gui``.
        """

        import run

        with patch.object(run, "_ensure_qt_runtime", return_value=0), patch(
            "src.crash_log.install"
        ), patch.object(run, "_launch_gui", return_value=0) as launch, patch.object(
            sys, "argv", ["snappix", *arguments]
        ):
            run.main()
        return launch

    def test_image_arguments_become_startup_files(self) -> None:
        """
        Ensures double-clicking an image reaches the controller.
        """

        with TemporaryDirectory() as directory:
            image = Path(directory) / "a.png"
            image.write_bytes(b"x")

            launch = self._main([str(image)])

        self.assertEqual([Path(f).name for f in launch.call_args.kwargs["startup_files"]], ["a.png"])

    def test_no_arguments_means_no_files(self) -> None:
        """
        Ensures an ordinary start is unchanged.
        """

        launch = self._main([])

        self.assertEqual(launch.call_args.kwargs["startup_files"], [])

    def test_the_autostart_flag_is_not_mistaken_for_a_file(self) -> None:
        """
        Ensures the login launch still stays in the tray.
        """

        launch = self._main(["--autostart"])

        self.assertTrue(launch.call_args.kwargs["autostart_launch"])
        self.assertEqual(launch.call_args.kwargs["startup_files"], [])


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestOpeningFiles(CaptureTabCase):
    """
    Verifies what the controller does with the files it is given.
    """

    def test_an_image_opens_in_a_tab_at_its_original_size(self) -> None:
        """
        Ensures the picture appears as itself, not scaled to the window.
        """

        controller = self._controller()
        with TemporaryDirectory() as directory:
            image = _write_image(Path(directory), "photo.png", 1800, 1200)

            controller.open_files([str(image)])
            self._app.processEvents()
            self._app.processEvents()

            editor = controller.editors[-1]
            self.assertEqual(controller.editor_tabs.tabText(0), "photo.png")
            self.assertEqual(
                (editor.canvas.screenshot().width(), editor.canvas.screenshot().height()), (1800, 1200)
            )
            self.assertAlmostEqual(editor.canvas.transform().m11(), 1.0)

    def test_the_editor_window_is_shown(self) -> None:
        """
        Ensures opening a file brings the editor up.
        """

        controller = self._controller()
        with TemporaryDirectory() as directory:
            controller.open_files([str(_write_image(Path(directory), "a.png"))])

        self.assertTrue(controller.editor_host.isVisible())

    def test_the_file_is_never_touched_or_deleted(self) -> None:
        """
        Ensures a viewer does no harm: closing the tab leaves the picture alone.
        """

        controller = self._controller()
        with TemporaryDirectory() as directory:
            image = _write_image(Path(directory), "keep.png")
            before = image.read_bytes()
            controller.open_files([str(image)])
            self._app.processEvents()

            self.assertEqual(controller.editors[-1].capture_file(), "")
            controller._close_editor_tab_by_index(0, delete_capture=True)

            self.assertTrue(image.is_file())
            self.assertEqual(image.read_bytes(), before)

    def test_an_opened_tab_has_the_single_default_close_button(self) -> None:
        """
        Ensures there is no "delete the image" button on somebody's own file.
        """

        from src.tab_close_buttons import TabClosePair

        controller = self._controller()
        with TemporaryDirectory() as directory:
            controller.open_files([str(_write_image(Path(directory), "a.png"))])
            tab_bar = controller.editor_tabs.tabBar()

            for position in (tab_bar.ButtonPosition.LeftSide, tab_bar.ButtonPosition.RightSide):
                self.assertNotIsInstance(tab_bar.tabButton(0, position), TabClosePair)

    def test_the_same_file_twice_shows_one_tab(self) -> None:
        """
        Ensures a repeated open brings the tab forward instead of duplicating it.
        """

        controller = self._controller()
        with TemporaryDirectory() as directory:
            first = _write_image(Path(directory), "a.png")
            second = _write_image(Path(directory), "b.png")
            controller.open_files([str(first), str(second)])
            controller.editor_tabs.setCurrentIndex(1)

            controller.open_files([str(first)])

            self.assertEqual(controller.editor_tabs.count(), 2)
            self.assertEqual(controller.editor_tabs.currentIndex(), 0)

    def test_several_files_open_in_order(self) -> None:
        """
        Ensures every file gets its tab.
        """

        controller = self._controller()
        with TemporaryDirectory() as directory:
            files = [str(_write_image(Path(directory), name)) for name in ("1.png", "2.jpg", "3.webp")]

            controller.open_files(files)

            self.assertEqual(
                [controller.editor_tabs.tabText(i) for i in range(3)], ["1.png", "2.jpg", "3.webp"]
            )

    def test_a_broken_image_says_so_and_opens_nothing(self) -> None:
        """
        Ensures a corrupt file is reported instead of leaving an empty tab.
        """

        controller = self._controller()
        controller._QMessageBox = MagicMock()
        with TemporaryDirectory() as directory:
            broken = Path(directory) / "broken.png"
            broken.write_bytes(b"this is not a png")

            controller.open_files([str(broken)])

        controller._QMessageBox.warning.assert_called_once()
        self.assertEqual(controller.editor_tabs.count(), 0)

    def test_a_project_file_goes_to_the_project_opener(self) -> None:
        """
        Ensures ``.sfp`` files are projects, not pictures.
        """

        controller = self._controller()
        controller._QMessageBox = MagicMock()
        with patch.object(controller, "_open_project_in_editor") as open_project:
            controller.open_files(["/tmp/work.sfp"])

        open_project.assert_called_once_with("/tmp/work.sfp")

    def test_an_edited_viewer_tab_can_still_be_exported(self) -> None:
        """
        Ensures the opened image is a normal, editable document.
        """

        controller = self._controller()
        with TemporaryDirectory() as directory:
            controller.open_files([str(_write_image(Path(directory), "a.png"))])
            editor = controller.editors[-1]
            self._draw(editor)

            self.assertTrue(editor.has_drawn_annotations())
            self.assertFalse(editor._export_output_pixmap(for_jpeg=False).isNull())


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestStartingAsViewer(CaptureTabCase):
    """
    Verifies the first start when it was asked to open a file.
    """

    def _start(self, files: list[str]):
        """
        Builds a controller the way a launch with files does, and shows it.

        Args:
            files: Startup files.

        Returns:
            AppController: The shown controller.
        """

        import run

        controller = run.AppController(
            self._app, startup_project_path="", autostart_launch=False, startup_files=files
        )
        self.addCleanup(self._dispose, controller)
        controller.show()
        self._app.processEvents()
        return controller

    def test_the_picture_appears_and_the_capture_panel_does_not(self) -> None:
        """
        Ensures double-clicking an image opens the image, not Snappix's capture window.
        """

        with TemporaryDirectory() as directory:
            controller = self._start([str(_write_image(Path(directory), "a.png"))])

            self.assertEqual(controller.editor_tabs.count(), 1)
            self.assertTrue(controller.editor_host.isVisible())
            self.assertFalse(controller.capture_panel.isVisible())

    def test_an_ordinary_start_still_shows_the_capture_panel(self) -> None:
        """
        Ensures nothing changed for a start without files.
        """

        controller = self._start([])

        self.assertTrue(controller.capture_panel.isVisible())
        self.assertEqual(controller.editor_tabs.count(), 0)

    def test_restored_tabs_and_the_opened_file_both_appear(self) -> None:
        """
        Ensures opening a file does not throw away the previous session.
        """

        first = self._controller()
        self._capture(first)
        first._save_editor_session()

        with TemporaryDirectory() as directory:
            controller = self._start([str(_write_image(Path(directory), "extra.png"))])

            titles = [controller.editor_tabs.tabText(i) for i in range(controller.editor_tabs.count())]
            self.assertEqual(len(titles), 2)
            self.assertIn("extra.png", titles)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestSettingsRow(unittest.TestCase):
    """
    Verifies the "default image viewer" row in the settings.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _dialog(self, service):
        """
        Builds a settings dialog around a viewer service.

        Args:
            service: Service or None.

        Returns:
            SettingsDialog: The dialog, closed again after the test.
        """

        from PySide6.QtCore import QCoreApplication, QEvent

        from src.config import AppConfig
        from src.settings_dialog import SettingsDialog

        dialog = SettingsDialog(AppConfig(), default_viewer=service)

        def dispose() -> None:
            for box in dialog.findChildren(QMessageBox):
                box.close()
            dialog.close()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        self.addCleanup(dispose)
        return dialog

    @staticmethod
    def _service(*, supported: bool = True, ok: bool = True) -> MagicMock:
        """
        Builds a stand-in for the viewer service.

        Args:
            supported: What ``is_supported`` answers.
            ok: Whether ``make_default`` succeeds.

        Returns:
            MagicMock: The service.
        """

        from src.file_association import AssociationResult

        service = MagicMock()
        service.is_supported.return_value = supported
        service.status.return_value = "Another program opens images by default."
        service.make_default.return_value = AssociationResult(ok, "Snappix now opens images by default.")
        return service

    def test_the_row_is_there_with_the_current_state(self) -> None:
        """
        Ensures the person sees who opens images now.
        """

        dialog = self._dialog(self._service())

        self.assertEqual(
            dialog.default_viewer_status.text(), "Another program opens images by default."
        )

    def test_the_button_asks_the_system_and_shows_the_answer(self) -> None:
        """
        Ensures a click does the thing and says what came of it.
        """

        service = self._service()
        dialog = self._dialog(service)

        dialog.default_viewer_button.click()

        service.make_default.assert_called_once()
        self.assertEqual(dialog.default_viewer_status.text(), "Snappix now opens images by default.")

    def test_the_system_is_not_asked_just_by_opening_the_settings(self) -> None:
        """
        Ensures the default only changes when the button is pressed.
        """

        service = self._service()
        self._dialog(service)

        service.make_default.assert_not_called()

    def test_without_a_service_there_is_no_row(self) -> None:
        """
        Ensures the settings work where no service is given.
        """

        self.assertFalse(hasattr(self._dialog(None), "default_viewer_button"))

    def test_on_an_unsupported_system_there_is_no_row(self) -> None:
        """
        Ensures a button that cannot work is not shown.
        """

        self.assertFalse(hasattr(self._dialog(self._service(supported=False)), "default_viewer_button"))

    def test_the_controller_gives_the_dialog_a_service(self) -> None:
        """
        Ensures the real Settings window has the row, not just this test's dialog.
        """

        import run

        controller = object.__new__(run.AppController)

        service = controller._default_viewer_service()

        self.assertEqual(service.is_supported(), sys.platform.startswith(("linux", "win")))


if __name__ == "__main__":
    unittest.main()
