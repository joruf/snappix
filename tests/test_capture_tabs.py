"""
Tests for captures that live as files from the moment they are taken.

Every screenshot and recording opens as a tab *and* sits in the capture folder.
The tab's X deletes both, File > Close style closing keeps the file, and a tab
that got lost is rebuilt from the folder on the next start. These tests drive a
real controller against an isolated home, because the wiring between capture,
tab, session and folder is where this can break.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtCore import QCoreApplication, QEvent, QPointF
    from PySide6.QtGui import QColor, QPixmap

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

CONFIRM = "src.close_tab_dialog.confirm_close_tab"


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class CaptureTabCase(unittest.TestCase):
    """
    Shared setup: an isolated home and a way to start a controller in it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Points every per-user location at a temporary home.
        """

        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = temporary.name
        environment = patch.dict(
            os.environ,
            {
                "HOME": self.home,
                "USERPROFILE": self.home,
                "LOCALAPPDATA": self.home,
                "XDG_CONFIG_HOME": f"{self.home}/.config",
                "XDG_DATA_HOME": f"{self.home}/.local/share",
                "XDG_CACHE_HOME": f"{self.home}/.cache",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

        # A dialog that appears when it should not must fail a test, not hang it.
        modal = patch("PySide6.QtWidgets.QMessageBox.exec", return_value=0)
        modal.start()
        self.addCleanup(modal.stop)

        # A real manager would grab global hotkeys on whatever desktop runs the
        # tests, and its listener threads sometimes block on the X server.
        hotkeys = patch("src.global_hotkeys.GlobalHotkeyManager", MagicMock())
        hotkeys.start()
        self.addCleanup(hotkeys.stop)

        from src.theme import current_theme_name, set_current_theme

        self.addCleanup(set_current_theme, current_theme_name())

        from src.session_recovery import reset_workspace_root

        reset_workspace_root()
        self.addCleanup(reset_workspace_root)
        self.folder = Path(self.home) / "Downloads" / "snappix"

    def _controller(self):
        """
        Starts a controller the way the application does.

        Returns:
            AppController: Controller living in the temporary home.
        """

        import run

        controller = run.AppController(self._app, startup_project_path="", autostart_launch=False)
        self.addCleanup(self._dispose, controller)
        return controller

    def _dispose(self, controller) -> None:
        """
        Releases what a controller created, without touching any file.

        Args:
            controller: Controller to release.
        """

        controller._is_quitting = True
        while controller.editor_tabs.count() > 0:
            controller._close_editor_tab_by_index(0)
        controller.tray_icon.hide()
        for widget in (controller.editor_host, controller.capture_panel, controller.tray_icon):
            widget.deleteLater()
        self._app.processEvents()
        # deleteLater() only runs inside an event loop; without this every test
        # leaves its windows alive and each stylesheet change gets slower.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        # The controller styles the whole application; left in place, that
        # stylesheet slows every widget any later test creates.
        self._app.setStyleSheet("")

    def _capture(self, controller) -> object:
        """
        Delivers one screenshot as the capture flow does.

        Args:
            controller: Controller under test.

        Returns:
            EditorWindow: The tab that opened.
        """

        pixmap = QPixmap(120, 80)
        pixmap.fill(QColor(200, 40, 40))
        before = len(controller.editors)
        controller._handle_capture_result(pixmap)
        self._app.processEvents()
        self.assertEqual(len(controller.editors), before + 1)
        return controller.editors[-1]

    def _draw(self, editor) -> None:
        """
        Adds one stroke, which is a change the capture file does not hold.

        Args:
            editor: Editor to draw on.
        """

        from src.editor_canvas import Tool

        canvas = editor.canvas
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(10.0, 10.0))
        for index in range(1, 12):
            canvas._extend_freehand_stroke(QPointF(10.0 + index * 6.0, 20.0 + index))
        canvas._finalize_poly_draw()
        self._app.processEvents()

    def _files(self) -> list[str]:
        """
        Lists the capture files, leaving the hidden index out.

        Returns:
            list[str]: File names in the capture folder.
        """

        if not self.folder.is_dir():
            return []
        return sorted(name for name in os.listdir(self.folder) if not name.startswith("."))


class TestCaptureBecomesAFile(CaptureTabCase):
    """
    Verifies that a screenshot is a file before anyone touches the tab.
    """

    def test_a_capture_is_written_to_the_folder_at_once(self) -> None:
        """
        Ensures the file exists the moment the tab opens.
        """

        controller = self._controller()
        editor = self._capture(controller)

        files = self._files()
        self.assertEqual(len(files), 1)
        self.assertEqual(Path(editor.capture_file()), self.folder / files[0])
        self.assertFalse(QPixmap(editor.capture_file()).isNull())

    def test_the_file_is_indexed_as_a_snappix_capture(self) -> None:
        """
        Ensures the file counts as ours, so it may be restored and deleted.
        """

        from src.capture_files import is_registered

        controller = self._controller()
        editor = self._capture(controller)
        self.assertTrue(is_registered(editor.capture_file()))

    def test_a_failing_write_still_opens_the_tab(self) -> None:
        """
        Ensures a full disk costs the file, never the screenshot.
        """

        controller = self._controller()
        with patch.object(controller, "_save_capture_pixmap", side_effect=OSError("full")):
            editor = self._capture(controller)

        self.assertEqual(editor.capture_file(), "")
        self.assertEqual(self._files(), [])

    def test_two_captures_do_not_overwrite_each_other(self) -> None:
        """
        Ensures captures within one second keep separate files.
        """

        controller = self._controller()
        first = self._capture(controller)
        second = self._capture(controller)

        self.assertNotEqual(first.capture_file(), second.capture_file())
        self.assertEqual(len(self._files()), 2)


class TestTabCrossDeletes(CaptureTabCase):
    """
    Verifies the X on a tab.
    """

    def test_an_untouched_capture_is_deleted_without_asking(self) -> None:
        """
        Ensures X removes tab and file, silently, when nothing was changed.
        """

        controller = self._controller()
        self._capture(controller)

        with patch(CONFIRM, side_effect=AssertionError("asked")) as ask:
            controller._close_editor_tab_with_capture(0)

        ask.assert_not_called()
        self.assertEqual(controller.editor_tabs.count(), 0)
        self.assertEqual(self._files(), [])

    def test_a_changed_capture_asks_before_deleting(self) -> None:
        """
        Ensures work is never thrown away unannounced.
        """

        controller = self._controller()
        editor = self._capture(controller)
        self._draw(editor)
        self.assertTrue(editor.has_changes_since_capture())

        with patch(CONFIRM, return_value=False) as ask:
            controller._close_editor_tab_with_capture(0)

        ask.assert_called_once()
        self.assertIn("deletes", ask.call_args[0][1])
        self.assertEqual(controller.editor_tabs.count(), 1)
        self.assertEqual(len(self._files()), 1)

    def test_confirming_deletes_the_changed_capture(self) -> None:
        """
        Ensures confirming removes the file along with the tab.
        """

        controller = self._controller()
        editor = self._capture(controller)
        self._draw(editor)

        with patch(CONFIRM, return_value=True) as ask:
            controller._close_editor_tab_with_capture(0)

        ask.assert_called_once()
        self.assertEqual(controller.editor_tabs.count(), 0)
        self.assertEqual(self._files(), [])

    def test_the_x_button_is_wired_to_the_deleting_close(self) -> None:
        """
        Ensures the real tab X reaches the deleting path, not only the method.
        """

        controller = self._controller()
        self._capture(controller)

        with patch(CONFIRM, side_effect=AssertionError("asked")):
            controller.editor_tabs.tabCloseRequested.emit(0)

        self.assertEqual(controller.editor_tabs.count(), 0)
        self.assertEqual(self._files(), [])

    def test_a_tab_without_a_capture_file_closes_as_before(self) -> None:
        """
        Ensures an imported or new tab keeps its old prompt and loses nothing.
        """

        controller = self._controller()
        pixmap = QPixmap(60, 40)
        pixmap.fill(QColor(10, 10, 10))
        editor = controller._create_editor_tab(pixmap, "Imported")
        self._draw(editor)

        with patch(CONFIRM, return_value=False) as ask:
            controller._close_editor_tab_with_capture(0)

        ask.assert_called_once()
        self.assertNotIn("deletes", ask.call_args[0][1])
        self.assertEqual(controller.editor_tabs.count(), 1)

    def test_somebody_elses_file_is_not_deleted(self) -> None:
        """
        Ensures a tab pointing at an unindexed file cannot delete it.
        """

        controller = self._controller()
        pixmap = QPixmap(60, 40)
        pixmap.fill(QColor(10, 10, 10))
        self.folder.mkdir(parents=True)
        theirs = self.folder / "holiday.png"
        pixmap.save(str(theirs))
        editor = controller._create_editor_tab(pixmap, "Imported")
        editor.set_capture_file(str(theirs))

        controller._close_editor_tab_with_capture(0)

        self.assertTrue(theirs.is_file())


class TestOtherCloseKeepsTheFile(CaptureTabCase):
    """
    Verifies closing that is not the X.
    """

    def test_closing_the_current_tab_keeps_the_file(self) -> None:
        """
        Ensures the keyboard close leaves the capture in the folder.
        """

        controller = self._controller()
        self._capture(controller)

        controller._close_current_editor_tab()

        self.assertEqual(controller.editor_tabs.count(), 0)
        self.assertEqual(len(self._files()), 1)

    def test_a_kept_file_is_not_brought_back_as_a_tab(self) -> None:
        """
        Ensures closing a tab means it stays closed after a restart.
        """

        controller = self._controller()
        self._capture(controller)
        controller._close_current_editor_tab()

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 0)
        self.assertEqual(len(self._files()), 1)

    def test_quitting_deletes_nothing(self) -> None:
        """
        Ensures the files survive the application ending.
        """

        controller = self._controller()
        self._capture(controller)
        controller._is_quitting = True

        controller._close_editor_tab_by_index(0)

        self.assertEqual(len(self._files()), 1)


class TestStartRestoresTabs(CaptureTabCase):
    """
    Verifies what the next start does with the folder.
    """

    def test_open_tabs_come_back_bound_to_their_files(self) -> None:
        """
        Ensures a restored tab can still delete its file with the X.
        """

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        restored = restarted.editors[-1]
        self.assertEqual(Path(restored.capture_file()), self.folder / self._files()[0])
        restarted._close_editor_tab_with_capture(0)
        self.assertEqual(self._files(), [])

    def test_a_lost_tab_is_rebuilt_from_the_folder(self) -> None:
        """
        Ensures a capture whose session is gone still gets its tab.
        """

        from src.session_recovery import clear_editor_session

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()
        clear_editor_session()
        self.assertEqual(len(self._files()), 1)

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        self.assertEqual(
            Path(restarted.editors[-1].capture_file()), self.folder / self._files()[0]
        )

    def test_a_lost_tab_keeps_its_annotations_when_recovery_survives(self) -> None:
        """
        Ensures the drawing is not lost just because the manifest was.
        """

        controller = self._controller()
        editor = self._capture(controller)
        self._draw(editor)
        controller._save_editor_session()
        manifest = Path(self.home) / ".snappix" / "session.json"
        manifest.unlink()

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        self.assertTrue(restarted.editors[-1].has_drawn_annotations())

    def test_a_lost_tab_opens_from_the_file_when_recovery_is_gone(self) -> None:
        """
        Ensures the picture alone is enough to bring the tab back.
        """

        import shutil

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()
        shutil.rmtree(Path(self.home) / ".snappix")

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        tab = restarted.editors[-1]
        self.assertEqual(Path(tab.capture_file()), self.folder / self._files()[0])
        self.assertFalse(tab.canvas.screenshot().isNull())

    def test_a_file_that_is_not_ours_gets_no_tab(self) -> None:
        """
        Ensures older screenshots and other files in the folder stay untouched.
        """

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()
        controller._close_current_editor_tab()
        pixmap = QPixmap(30, 30)
        pixmap.fill(QColor(0, 0, 255))
        pixmap.save(str(self.folder / "older.png"))

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 0)
        self.assertTrue((self.folder / "older.png").is_file())

    def test_a_tab_already_open_is_not_opened_twice(self) -> None:
        """
        Ensures the folder scan skips captures a restored tab shows.
        """

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        self.assertEqual(restarted._lost_capture_tabs([]), ([], []))


class TestRecordings(CaptureTabCase):
    """
    Verifies that a recording leaves the scratch folder as a capture file.
    """

    def test_a_finished_recording_moves_into_the_folder(self) -> None:
        """
        Ensures the recording is a capture file and the tab uses it.
        """

        controller = self._controller()
        scratch = self.folder / "tmp"
        scratch.mkdir(parents=True)
        recording = scratch / "snappix-recording_2026-10-28_08-00-00.mp4"
        recording.write_bytes(b"video")
        controller._video_recorder = MagicMock()
        controller._recording_rect = MagicMock(width=lambda: 320, height=lambda: 200)
        controller._close_recording_border_overlay = MagicMock()
        controller._recording_fits_editor_limit = MagicMock(return_value=True)
        controller._create_video_editor_tab = MagicMock()

        controller._on_recording_finished(str(recording))

        target = self.folder / recording.name
        self.assertTrue(target.is_file())
        self.assertFalse(recording.exists())
        args, kwargs = controller._create_video_editor_tab.call_args
        self.assertEqual(args[0], str(target))
        self.assertEqual(kwargs["capture_file"], str(target))

    def test_a_clashing_name_gets_a_counter(self) -> None:
        """
        Ensures an earlier recording of the same second survives.
        """

        controller = self._controller()
        self.folder.mkdir(parents=True)
        (self.folder / "clip.mp4").write_bytes(b"old")
        scratch = self.folder / "tmp"
        scratch.mkdir()
        recording = scratch / "clip.mp4"
        recording.write_bytes(b"new")

        moved = controller._move_recording_to_capture_folder(str(recording))

        self.assertEqual(Path(moved).name, "clip-1.mp4")
        self.assertEqual((self.folder / "clip.mp4").read_bytes(), b"old")

    def test_a_video_tab_releases_its_player_before_the_file_goes(self) -> None:
        """
        Ensures the open file is let go first; Windows cannot delete it otherwise.
        """

        import run
        from src.capture_files import register_capture

        self.folder.mkdir(parents=True)
        clip = self.folder / "clip.mp4"
        clip.write_bytes(b"video")
        register_capture(clip, "video")
        order: list[str] = []
        tab = MagicMock()
        tab._capture_file = str(clip)
        tab.shutdown_playback.side_effect = lambda: order.append(
            f"release:{clip.exists()}"
        )

        run.AppController._release_capture_file(tab, delete=True)

        self.assertEqual(order, ["release:True"])
        self.assertFalse(clip.exists())


class TestEditorWindowAroundCaptures(CaptureTabCase):
    """
    Verifies when the whole editor goes away and comes back.
    """

    def _start_capture(self, controller):
        """
        Starts a screenshot with the grab itself stubbed out.

        Args:
            controller: Controller under test.

        Returns:
            dict: The ``on_capture`` and ``on_cancel`` callbacks the capture got.
        """

        from src.capture import CaptureMode, CaptureRequest

        callbacks: dict = {}

        def fake_execute(*, request, on_capture, on_cancel) -> None:
            callbacks["capture"] = on_capture
            callbacks["cancel"] = on_cancel

        with patch("src.capture.execute_capture_request", fake_execute):
            controller.start_capture(CaptureRequest(mode=CaptureMode.REGION, delay_seconds=0))
        return callbacks

    def test_closing_the_last_tab_closes_the_editor(self) -> None:
        """
        Ensures no empty editor window is left behind.
        """

        controller = self._controller()
        self._capture(controller)
        self.assertTrue(controller.editor_host.isVisible())

        controller._close_editor_tab_with_capture(0)

        self.assertFalse(controller.editor_host.isVisible())
        self.assertTrue(controller.capture_panel.isVisible())

    def test_closing_a_tab_with_others_left_keeps_the_editor(self) -> None:
        """
        Ensures only the last tab takes the window with it.
        """

        controller = self._controller()
        self._capture(controller)
        self._capture(controller)

        controller._close_editor_tab_with_capture(0)

        self.assertEqual(controller.editor_tabs.count(), 1)
        self.assertTrue(controller.editor_host.isVisible())

    def test_the_editor_is_minimized_while_a_screenshot_is_taken(self) -> None:
        """
        Ensures an open editor cannot cover what the capture is meant to grab.
        """

        controller = self._controller()
        self._capture(controller)
        self.assertFalse(controller.editor_host.isMinimized())

        self._start_capture(controller)

        self.assertTrue(controller.editor_host.isMinimized())

    def test_the_editor_returns_once_the_screenshot_is_done(self) -> None:
        """
        Ensures the finished screenshot is on screen to be looked at.
        """

        controller = self._controller()
        self._capture(controller)
        callbacks = self._start_capture(controller)
        pixmap = QPixmap(50, 40)
        pixmap.fill(QColor(0, 120, 0))

        callbacks["capture"](pixmap)
        self._app.processEvents()

        self.assertFalse(controller.editor_host.isMinimized())
        self.assertTrue(controller.editor_host.isVisible())
        self.assertEqual(controller.editor_tabs.count(), 2)

    def test_the_editor_returns_when_the_screenshot_goes_to_the_clipboard(self) -> None:
        """
        Ensures the editor comes back even when no new tab opens.
        """

        controller = self._controller()
        self._capture(controller)
        controller.config.post_capture_action = "clipboard"
        callbacks = self._start_capture(controller)
        pixmap = QPixmap(50, 40)
        pixmap.fill(QColor(0, 120, 0))

        callbacks["capture"](pixmap)
        self._app.processEvents()

        self.assertEqual(controller.editor_tabs.count(), 1)
        self.assertFalse(controller.editor_host.isMinimized())

    def test_the_editor_returns_after_a_cancelled_screenshot(self) -> None:
        """
        Ensures cancelling leaves the editor as it was.
        """

        controller = self._controller()
        self._capture(controller)
        callbacks = self._start_capture(controller)

        callbacks["cancel"]()
        self._app.processEvents()

        self.assertFalse(controller.editor_host.isMinimized())
        self.assertTrue(controller.editor_host.isVisible())

    def test_a_closed_editor_is_not_opened_by_a_screenshot_that_is_cancelled(self) -> None:
        """
        Ensures only an editor that was showing is brought back.
        """

        controller = self._controller()
        self.assertFalse(controller.editor_host.isVisible())
        callbacks = self._start_capture(controller)

        callbacks["cancel"]()
        self._app.processEvents()

        self.assertFalse(controller.editor_host.isVisible())

    def test_an_editor_the_user_minimized_stays_minimized(self) -> None:
        """
        Ensures the capture does not pop up a window the user put away.
        """

        controller = self._controller()
        self._capture(controller)
        controller.editor_host.showMinimized()
        self._app.processEvents()
        callbacks = self._start_capture(controller)

        callbacks["cancel"]()
        self._app.processEvents()

        self.assertTrue(controller.editor_host.isMinimized())


if __name__ == "__main__":
    unittest.main()
